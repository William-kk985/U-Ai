import os
import sys
import json
import time
import re
import math
import difflib
import hashlib
from typing import List, Dict, Tuple
import importlib.util
from collections import Counter
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, StreamingResponse
from services.detector import get_hardware_info
from llama_cpp import Llama

# 动态导入核心模块 (解决文件夹以数字开头的问题)
CORE_DIR = os.path.join(os.path.dirname(__file__), '..', '04_Core')

def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

session_manager_module = load_module("session_manager", os.path.join(CORE_DIR, "session_manager.py"))
prompt_builder = load_module("prompt_builder", os.path.join(CORE_DIR, "prompt_builder.py"))

ChatSession = session_manager_module.ChatSession
SessionManager = session_manager_module.SessionManager
PromptBuilder = prompt_builder.PromptBuilder

# 初始化 FastAPI
app = FastAPI(title="Portable AI Assistant")

# 获取项目根目录路径
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 加载配置文件
def load_config():
    """加载配置文件，如果不存在则使用默认值"""
    config_path = os.path.join(ROOT_DIR, "config.json")
    default_config = {
        "server": {"host": "0.0.0.0", "port": 8000, "reload": False, "log_level": "info"},
        "model": {
            "default_model_pattern": "qwen.*coder.*7b",
            "fallback_patterns": ["qwen.*7b", "llama.*8b", "gemma.*9b", "phi.*3"],
            "context_window": 8192,
            "max_tokens": 2048,
            "temperature": 0.7,
            "top_p": 0.9,
            "n_gpu_layers": -1,
            "use_mlock": True,
            "n_threads": 0
        },
        "session": {
            "max_history_messages": 10,
            "auto_save_interval": 30,
            "storage_dir": "05_Data/sessions",
            "index_cache_dir": "05_Data/sessions/index_cache"
        },
        "cache": {
            "enable_file_index_cache": True,
            "cache_dir": "05_Data/cache",
            "max_cache_size_mb": 500
        },
        "cleanup": {
            "enable_auto_cleanup": True,
            "max_sessions": 50,
            "cleanup_days": 30,
            "log_retention_days": 7
        },
        "hardware": {
            "min_memory_gb": 4,
            "recommended_memory_gb": 16,
            "memory_buffer_gb": 2
        }
    }
    
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            # 合并默认配置（防止缺少某些字段）
            for key in default_config:
                if key not in config:
                    config[key] = default_config[key]
            print(f"✅ 配置文件已加载: {config_path}")
            return config
        except Exception as e:
            print(f"⚠️ 配置文件加载失败: {e}，使用默认配置")
            return default_config
    else:
        print(f"ℹ️  未找到配置文件，使用默认配置")
        print(f"💡 提示：复制 config.example.json 为 config.json 可自定义配置")
        return default_config

config = load_config()

MODELS_DIR = os.path.join(ROOT_DIR, "01_Models")
FRONTEND_DIR = os.path.join(ROOT_DIR, "03_Frontend", "dist")
DATA_DIR = os.path.join(ROOT_DIR, config["session"]["storage_dir"])
os.makedirs(DATA_DIR, exist_ok=True)

# 全局变量
llm = None
current_model_name = None
prompt_engine = PromptBuilder()

# O. 流式响应优化：停止生成标志
generation_stop_flag = False

# 文件索引缓存 {file_hash: {"structures": [...], "chunks": [...], "tfidf_index": {...}}}
file_index_cache = {}

# 检索结果缓存 {cache_key: {"result": str, "timestamp": float}}
# cache_key = hash(query + file_contents)
retrieval_cache = {}
RETRIEVAL_CACHE_TTL = 300  # 缓存有效期 5 分钟
RETRIEVAL_CACHE_MAX_SIZE = 50  # 最多缓存 50 个结果

# 磁盘缓存路径
INDEX_CACHE_DIR = os.path.join(DATA_DIR, os.path.basename(config["session"]["index_cache_dir"]))
os.makedirs(INDEX_CACHE_DIR, exist_ok=True)

# 初始化会话管理器
manager = SessionManager(
    storage_dir=DATA_DIR,
    max_sessions=config["cleanup"]["max_sessions"],
    cleanup_days=config["cleanup"]["cleanup_days"]
)

# 定义对话模式预设
MODE_PRESETS = {
    "precise": {"temperature": 0.1, "max_tokens": 1024, "system": "你是一个严谨的AI助手。"}, 
    "balanced": {"temperature": 0.7, "max_tokens": 512, "system": "你是一个乐于助人的AI助手。"}, 
    "creative": {"temperature": 0.95, "max_tokens": 2048, "system": "你是一个富有创造力的AI助手。"},
    # 代码模式预设
    "code_review": {"temperature": 0.2, "max_tokens": 1024, "system": "你是一位资深代码审查专家。请指出代码中的潜在Bug、性能瓶颈和安全漏洞，并给出优化建议。"},
    "code_refactor": {"temperature": 0.3, "max_tokens": 1024, "system": "你是一位重构大师。请在保持功能不变的前提下，优化代码结构，提高可读性和可维护性。"},
    "code_explain": {"temperature": 0.5, "max_tokens": 1024, "system": "你是一位耐心的编程导师。请用通俗易懂的语言解释这段代码的逻辑和原理。"},
    "code_generate": {"temperature": 0.2, "max_tokens": 2048, "system": "你是一位全栈工程师。请根据需求编写高质量、健壮且带有注释的代码。"},
    "code_architecture": {"temperature": 0.6, "max_tokens": 2048, "system": "你是一位资深系统架构师。请从可扩展性、性能、安全性等维度给出专业建议，并对比不同方案的优缺点。"}
}

def split_code_into_chunks(code: str, max_chunk_size: int = 1500) -> List[str]:
    """按函数/类进行语义切片，确保逻辑完整性"""
    pattern = r'^(\s*(?:def |class |function |async def |public |private |protected |static |void |int |const |let |var ))'
    lines = code.split('\n')
    chunks = []
    current_chunk = []
    current_size = 0
    
    for line in lines:
        if re.match(pattern, line, re.MULTILINE) and current_chunk:
            chunks.append('\n'.join(current_chunk))
            current_chunk = [line]
            current_size = len(line)
        else:
            current_chunk.append(line)
            current_size += len(line)
            if current_size > max_chunk_size:
                chunks.append('\n'.join(current_chunk))
                current_chunk = []
                current_size = 0
    
    if current_chunk:
        chunks.append('\n'.join(current_chunk))
    
    return chunks if chunks else [code]

# ==================== 方案 D: 多文件依赖分析 ====================

def analyze_file_dependencies(files: List[Dict]) -> List[Dict]:
    """
    分析 C/C++ 文件的 #include 依赖关系，自动排序
    返回按依赖顺序排列的文件列表（被依赖的在前）
    """
    if len(files) <= 1:
        return files
    
    # 1. 构建文件名到内容的映射
    file_map = {f['name']: f for f in files}
    
    # 2. 解析每个文件的 #include 语句
    dependencies = {}  # {filename: [dependent_files]}
    
    for f in files:
        f_name = f['name']
        f_content = f.get('content', '')
        
        # 提取 #include "xxx" 语句（本地头文件）
        includes = re.findall(r'#include\s+"([^"]+)"', f_content)
        
        # 只保留已上传的文件
        relevant_includes = [inc for inc in includes if inc in file_map]
        dependencies[f_name] = relevant_includes
    
    # 3. 拓扑排序（被依赖的在前）
    sorted_files = []
    visited = set()
    
    def dfs(filename):
        if filename in visited:
            return
        visited.add(filename)
        
        # 先处理依赖的文件
        for dep in dependencies.get(filename, []):
            dfs(dep)
        
        # 然后添加当前文件
        if filename in file_map:
            sorted_files.append(file_map[filename])
    
    # 对所有文件执行 DFS
    for f in files:
        dfs(f['name'])
    
    print(f"📊 依赖关系:")
    for f_name, deps in dependencies.items():
        if deps:
            print(f"  {f_name} → 依赖: {', '.join(deps)}")
    
    return sorted_files

# ==================== 方案 A: 文件索引磁盘缓存 ====================

def save_index_to_disk(code_hash: str, index: Dict):
    """将索引保存到磁盘"""
    try:
        # 检查缓存大小限制
        max_cache_mb = config.get("cache", {}).get("max_cache_size_mb", 500)
        cache_dir_size = sum(
            os.path.getsize(os.path.join(INDEX_CACHE_DIR, f))
            for f in os.listdir(INDEX_CACHE_DIR)
            if os.path.isfile(os.path.join(INDEX_CACHE_DIR, f))
        ) / (1024 * 1024)  # 转换为 MB
        
        if cache_dir_size > max_cache_mb:
            print(f"⚠️  缓存目录已满 ({cache_dir_size:.1f}MB > {max_cache_mb}MB)，清理旧缓存...")
            cleanup_old_cache()
        
        cache_file = os.path.join(INDEX_CACHE_DIR, f"{code_hash}.json")
        # Counter 对象需要序列化
        serializable_index = {
            "structures": index["structures"],
            "chunks": index["chunks"],
            "chunk_tokens": [dict(tokens) for tokens in index["chunk_tokens"]],
            "idf": index["idf"]
        }
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(serializable_index, f, ensure_ascii=False)
    except Exception as e:
        print(f"⚠️ 保存索引到磁盘失败: {e}")

def cleanup_old_cache():
    """清理最旧的缓存文件"""
    try:
        cache_files = [
            os.path.join(INDEX_CACHE_DIR, f)
            for f in os.listdir(INDEX_CACHE_DIR)
            if f.endswith('.json')
        ]
        
        if not cache_files:
            return
        
        # 按修改时间排序，删除最旧的 20%
        cache_files.sort(key=lambda x: os.path.getmtime(x))
        files_to_delete = cache_files[:max(1, len(cache_files) // 5)]
        
        for file_path in files_to_delete:
            os.remove(file_path)
            print(f"   🗑️  删除: {os.path.basename(file_path)}")
    except Exception as e:
        print(f"⚠️ 清理缓存失败: {e}")

def load_index_from_disk(code_hash: str) -> Dict:
    """从磁盘加载索引"""
    try:
        cache_file = os.path.join(INDEX_CACHE_DIR, f"{code_hash}.json")
        if os.path.exists(cache_file):
            with open(cache_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            # 恢复 Counter 对象
            data["chunk_tokens"] = [Counter(tokens) for tokens in data["chunk_tokens"]]
            return data
    except Exception as e:
        print(f"⚠️ 从磁盘加载索引失败: {e}")
    return None

# ==================== 方案 D: 文件预处理缓存 ====================

def build_file_index(code: str) -> Dict:
    """为文件建立索引（结构 + 切片 + TF-IDF）"""
    structures = extract_code_structure(code)
    chunks = split_code_into_chunks(code)
    
    # 构建简单的 TF-IDF 索引
    chunk_tokens = []
    for chunk in chunks:
        tokens = re.findall(r'\w+', chunk.lower())
        chunk_tokens.append(Counter(tokens))
    
    # 计算文档频率
    doc_freq = Counter()
    for tokens in chunk_tokens:
        for token in set(tokens.keys()):
            doc_freq[token] += 1
    
    total_chunks = len(chunks)
    idf = {token: math.log(total_chunks / (freq + 1)) + 1 for token, freq in doc_freq.items()}
    
    return {
        "structures": structures,
        "chunks": chunks,
        "chunk_tokens": chunk_tokens,
        "idf": idf
    }

def get_or_build_index(code: str) -> Dict:
    """获取或构建文件索引（内存 + 磁盘双层缓存）"""
    # 检查是否启用缓存
    if not config.get("cache", {}).get("enable_file_index_cache", True):
        # 缓存禁用，直接构建
        return build_file_index(code)
    
    # 使用代码哈希作为缓存键
    code_hash = str(hash(code))
    
    # 1. 先查内存缓存
    if code_hash in file_index_cache:
        return file_index_cache[code_hash]
    
    # 2. 再查磁盘缓存
    disk_index = load_index_from_disk(code_hash)
    if disk_index:
        file_index_cache[code_hash] = disk_index
        print(f"📚 从磁盘加载索引: {len(disk_index['chunks'])} 个代码块")
        return disk_index
    
    # 3. 构建新索引
    file_index_cache[code_hash] = build_file_index(code)
    print(f"📚 建立文件索引: {len(file_index_cache[code_hash]['chunks'])} 个代码块")
    
    # 4. 保存到磁盘
    save_index_to_disk(code_hash, file_index_cache[code_hash])
    
    return file_index_cache[code_hash]

# ==================== 方案 B: 代码感知加权 BM25 检索 ====================

def bm25_score(query_tokens: Counter, doc_tokens: Counter, idf: Dict, k1: float = 1.5, b: float = 0.75) -> float:
    """计算 BM25 分数（支持权重）"""
    score = 0.0
    doc_len = sum(doc_tokens.values())
    avg_doc_len = 100  # 简化：假设平均文档长度
    
    for token, weight in query_tokens.items():
        if token in doc_tokens:
            tf = doc_tokens[token]
            idf_val = idf.get(token, 0)
            score += weight * idf_val * (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * doc_len / avg_doc_len))
    
    return score

def extract_weighted_query_tokens(query: str) -> Counter:
    """提取查询词并赋予权重（代码感知）"""
    tokens = Counter()
    query_lower = query.lower()
    
    # 1. 识别可能的函数名/类名（驼峰、下划线分隔）
    code_symbols = re.findall(r'\b([a-z][a-z0-9_]*[A-Z]\w*|[a-z][a-z0-9_]{2,})\b', query_lower)
    for symbol in code_symbols:
        if len(symbol) > 2:  # 忽略太短的词
            tokens[symbol] = 3.0  # 代码符号权重 x3
    
    # 2. 普通词汇
    words = re.findall(r'\b\w+\b', query_lower)
    for word in words:
        if word not in tokens:  # 已经识别为代码符号的不再重复
            if word in ['if', 'else', 'for', 'while', 'return', 'def', 'class', 'function', 'void', 'int']:
                tokens[word] = 0.5  # 关键词降权
            else:
                tokens[word] = 1.0  # 普通词
    
    # 3. 注释内容降权（检测到“注释”、“说明”、“//”等）
    if any(kw in query_lower for kw in ['comment', '注释', '说明', 'note']):
        for token in list(tokens.keys()):
            tokens[token] *= 0.5
    
    return tokens

def detect_code_dependencies(code: str) -> Dict[str, List[str]]:
    """检测代码中的依赖关系（import/include）"""
    dependencies = {
        "imports": [],
        "includes": []
    }
    
    for line in code.split('\n'):
        line_stripped = line.strip()
        # Python import
        if line_stripped.startswith(('import ', 'from ')):
            dependencies["imports"].append(line_stripped)
        # C/C++ include
        elif line_stripped.startswith('#include'):
            dependencies["includes"].append(line_stripped)
    
    return dependencies

def extract_context_comments(code: str, start_line: int, end_line: int, context_lines: int = 5) -> List[str]:
    """提取函数/类定义前后的注释"""
    lines = code.split('\n')
    comments = []
    
    # 向前查找注释
    for i in range(start_line - 1, max(0, start_line - context_lines - 1), -1):
        line = lines[i].strip()
        if line.startswith(('#', '//', '/*', '*', '*/', '* ')) or not line:
            comments.insert(0, lines[i])
        else:
            break
    
    return comments

def count_comment_ratio(chunk: str) -> float:
    """计算代码块的注释比例"""
    lines = chunk.split('\n')
    if not lines:
        return 0.0
    
    comment_lines = 0
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(('#', '//', '/*', '*', '* ')) or (stripped.startswith('"""') or stripped.startswith("'''")):
            comment_lines += 1
    
    return comment_lines / len(lines)

def extract_header_comments(code: str) -> str:
    """提取文件头部的文档注释"""
    lines = code.split('\n')
    header = []
    
    for i, line in enumerate(lines[:30]):  # 只检查前 30 行
        stripped = line.strip()
        # 支持多种注释格式
        if stripped.startswith(('#', '//', '/*', '* ', '*')) or stripped.startswith('"""') or stripped.startswith("'''"):
            header.append(line)
        elif stripped and not header:  # 遇到第一个非空非注释行，停止
            break
        elif stripped and header:  # 已经有注释，遇到非注释行
            # 如果是空行，继续
            if not stripped:
                header.append(line)
            else:
                break
    
    return '\n'.join(header)

# ==================== 方案 A: 智能动态上下文预算分配 ====================

def calculate_context_budget(total_file_size: int, history_size: int, model_ctx: int = 32768) -> Dict:
    """动态计算上下文预算分配（适配 32K 窗口）"""
    # 转换为 token 估算（1 token ≈ 4 chars）
    total_tokens = model_ctx
    
    # 历史最多占 35%（16K 窗口可以更激进）
    history_tokens = min(history_size // 4, int(total_tokens * 0.35))
    system_tokens = 200  # 系统提示词预留
    
    # 剩余给文件内容
    file_budget = total_tokens - history_tokens - system_tokens - 300  # 300 buffer
    
    # 根据文件大小决定策略
    if total_file_size < 3000:  # 小文件
        strategy = "full_include"
        file_tokens = file_budget
    elif total_file_size < 20000:  # 中等文件
        strategy = "smart_retrieval"
        file_tokens = min(file_budget, int(total_tokens * 0.55))  # 最多 55%
    else:  # 超大文件
        strategy = "hierarchical_search"
        file_tokens = min(file_budget, int(total_tokens * 0.5))  # 最多 50%
    
    return {
        "strategy": strategy,
        "history_tokens": history_tokens,
        "file_tokens": file_tokens,
        "total_available": file_budget,
        "model_ctx": total_tokens
    }

# ==================== 增强版智能检索（代码感知） ====================

def find_relevant_chunks_enhanced(query: str, code: str, budget: Dict) -> str:
    """深度优化：分层检索 + BM25加权 + 动态策略 + 依赖感知 + 注释提取 + 缓存"""
    if not code or len(code) < 200:
        return code
    
    # B. 检索结果缓存检查
    cache_key = hashlib.md5(f"{query}{code[:1000]}{budget['strategy']}".encode()).hexdigest()
    
    # 检查缓存是否有效
    if cache_key in retrieval_cache:
        cached = retrieval_cache[cache_key]
        if time.time() - cached["timestamp"] < RETRIEVAL_CACHE_TTL:
            print(f"💾 使用缓存的检索结果 (命中率提升)")
            return cached["result"]
    
    # 获取或构建索引
    index = get_or_build_index(code)
    structures = index["structures"]
    chunks = index["chunks"]
    chunk_tokens = index["chunk_tokens"]
    idf = index["idf"]
    
    strategy = budget["strategy"]
    max_chars = budget["file_tokens"] * 4  # token 转字符
    
    # 使用加权查询词
    query_tokens = extract_weighted_query_tokens(query)
    query_lower = query.lower()
    
    scored_chunks = []
    
    # 策略 1: 小文件 - 完整包含
    if strategy == "full_include":
        return code[:max_chars]
    
    # 策略 2 & 3: 结构匹配 + BM25加权 + 依赖感知 + 注释提取
    
    # A. 结构匹配（超高权重）
    for struct in structures:
        struct_name_lower = struct['name'].lower()
        # 精确匹配或包含匹配
        if struct_name_lower in query_lower or any(token in struct_name_lower for token in query_tokens.keys()):
            start_line = struct['line']
            # 找到该函数的结束位置
            end_line = start_line + 1
            for i in range(start_line + 1, len(code.split('\n'))):
                line = code.split('\n')[i]
                if re.match(r'^\S', line) and not line.startswith(' '):  # 新顶层定义
                    break
                end_line = i + 1
            
            # 提取该结构前后的注释（增加上下文）
            context_lines = extract_context_comments(code, start_line, end_line)
            chunk_content = '\n'.join(code.split('\n')[start_line:end_line])
            
            # 添加注释上下文
            if context_lines:
                chunk_content = '\n'.join(context_lines) + '\n' + chunk_content
            
            scored_chunks.append((500, chunk_content))  # 超高优先级
    
    # B. 加权 BM25 语义检索
    for i, chunk in enumerate(chunks):
        score = bm25_score(query_tokens, chunk_tokens[i], idf)
        if score > 0:
            # 根据代码结构给予额外加权
            chunk_lower = chunk.lower()
            structure_bonus = 0
            for struct in structures:
                if struct['name'].lower() in chunk_lower:
                    structure_bonus += 50  # 包含结构定义的 chunk 额外加分
            
            # 注释密度加权（有注释的代码块更重要）
            comment_ratio = count_comment_ratio(chunk)
            comment_bonus = comment_ratio * 20  # 注释比例越高，权重越高
            
            scored_chunks.append((score * 10 + structure_bonus + comment_bonus, chunk))
    
    # C. 依赖关系辅助（如果查询提到特定模块）
    dependencies = detect_code_dependencies(code)
    dep_keywords = ['import', 'include', 'using', 'require', '依赖', '引用']
    if any(kw in query_lower for kw in dep_keywords):
        # 添加 import/include 语句到结果
        dep_lines = dependencies["imports"] + dependencies["includes"]
        if dep_lines:
            dep_content = '\n'.join(dep_lines[:15])  # 最多 15 条
            scored_chunks.append((100, dep_content))  # 中等优先级
    
    # D. 提取文件头部注释（文档说明）
    header_comments = extract_header_comments(code)
    if header_comments and len(header_comments) > 50:
        scored_chunks.append((80, header_comments))  # 文档注释优先级
    
    # E. 关键词回退（如果 BM25 没找到）
    if len(scored_chunks) < 3:
        query_words = set(query_tokens.keys())
        for i, chunk in enumerate(chunks):
            chunk_words = set(re.findall(r'\w+', chunk.lower()))
            overlap = len(query_words.intersection(chunk_words))
            if overlap > 0:
                scored_chunks.append((overlap * 5, chunk))
    
    # 去重、排序、拼接
    seen = set()
    unique_chunks = []
    total_size = 0
    
    for score, chunk in sorted(scored_chunks, key=lambda x: x[0], reverse=True):
        if chunk not in seen and total_size < max_chars:
            seen.add(chunk)
            unique_chunks.append(chunk)
            total_size += len(chunk)
    
    if not unique_chunks:
        return code[:min(2000, max_chars)]
    
    return "\n\n--- [相关代码片段] ---\n\n".join(unique_chunks)

def extract_code_structure(code: str) -> List[Dict]:
    """提取代码的结构化信息（类名、函数名）"""
    structures = []
    lines = code.split('\n')
    for i, line in enumerate(lines):
        # 匹配 Python/JS/Java/C++ 等常见定义
        match = re.match(r'\s*(?:def |class |function |async def |public |private |protected |static |void |int |const |let |var )\s+([\w]+)', line)
        if match:
            structures.append({"name": match.group(1), "line": i, "content": line.strip()})
    return structures

# ==================== 方案 C: 智能分层摘要 ====================

def compress_history_with_llm(messages: List[Dict], llm_instance) -> str:
    """使用 LLM 对早期对话进行智能摘要"""
    if len(messages) <= 6:
        return manager.active_session.get_formatted_history()
    
    # 提取需要压缩的部分（保留最近 4 轮）
    to_compress = messages[:-4]
    
    # 先尝试规则提取关键信息
    key_info = extract_key_information(to_compress)
    history_text = "\n".join([f"{m['role']}: {m['content']}" for m in to_compress])
    
    try:
        # 构造摘要指令
        summary_prompt = f"""请简要总结以下技术对话的核心内容。
要求：
1. 保留所有关键的代码逻辑、函数名、类名和结论
2. 丢弃寒暄、重复解释和无关内容
3. 控制在 200 字以内

历史对话：
{history_text}

已提取的关键信息：
{key_info}

摘要："""
        
        summary_response = llm_instance(summary_prompt, max_tokens=256, stop=["\nUser:", "\nAI:"], temperature=0.1)
        summary_text = summary_response['choices'][0]['text'].strip()
        
        # 拼接保留的最近对话
        recent_history = manager.active_session.get_formatted_history(limit=4)
        return f"[历史对话摘要]: {summary_text}\n\n[最近的对话]:\n{recent_history}"
    except Exception as e:
        print(f"⚠️ 摘要生成失败: {e}，回退到规则压缩")
        # 回退：只保留关键信息 + 最近对话
        recent_history = manager.active_session.get_formatted_history(limit=4)
        return f"[历史关键信息]: {key_info}\n\n[最近的对话]:\n{recent_history}"

def extract_key_information(messages: List[Dict]) -> str:
    """从历史消息中提取关键信息（规则方法）"""
    key_items = []
    
    for msg in messages:
        content = msg.get('content', '')
        role = msg.get('role', '')
        
        # 提取代码相关的函数名、类名
        code_patterns = re.findall(r'(?:def |class |function |struct |interface )\s+(\w+)', content)
        if code_patterns:
            key_items.append(f"代码定义: {', '.join(code_patterns)}")
        
        # 提取错误信息
        error_patterns = re.findall(r'(?:Error|Exception|Bug|Issue|Failed):\s*(.+)', content)
        if error_patterns:
            key_items.append(f"问题: {', '.join(error_patterns)}")
        
        # 提取结论性语句
        if role == 'assistant' and any(kw in content.lower() for kw in ['建议', '推荐', '最佳实践', '总结', '结论']):
            sentences = content.split('。')
            for sent in sentences:
                if any(kw in sent for kw in ['建议', '推荐', '应该', '最佳']):
                    key_items.append(f"结论: {sent.strip()}"[:50])
    
    return "\n".join(key_items) if key_items else "无特殊关键信息"

def find_relevant_chunks(query: str, code: str, top_k: int = 3) -> str:
    """深度优化：基于结构和语义的智能检索"""
    if not code or len(code) < 200:
        return code
    
    # 1. 结构化提取
    structures = extract_code_structure(code)
    query_lower = query.lower()
    
    # 2. 评分逻辑
    scored_chunks = []
    
    # A. 结构匹配加分（权重高）
    for struct in structures:
        if struct['name'].lower() in query_lower:
            # 找到对应的代码块（简单起见，取该行及其后 50 行）
            start_line = struct['line']
            end_line = min(start_line + 50, len(code.split('\n')))
            chunk_content = '\n'.join(code.split('\n')[start_line:end_line])
            scored_chunks.append((100, chunk_content)) # 高分
    
    # B. 语义/关键词匹配（权重中）
    if len(scored_chunks) < top_k:
        chunks = split_code_into_chunks(code)
        query_words = set(re.findall(r'\w+', query_lower))
        
        for chunk in chunks:
            chunk_words = set(re.findall(r'\w+', chunk.lower()))
            # 计算交集
            score = len(query_words.intersection(chunk_words))
            if score > 0:
                scored_chunks.append((score, chunk))
    
    # 3. 去重并排序
    seen = set()
    unique_chunks = []
    for score, chunk in sorted(scored_chunks, key=lambda x: x[0], reverse=True):
        if chunk not in seen:
            seen.add(chunk)
            unique_chunks.append(chunk)
            if len(unique_chunks) >= top_k:
                break
                
    if not unique_chunks:
        return code[:2000] # 兜底：返回开头部分
    
    result = "\n\n--- [相关代码片段] ---\n\n".join(unique_chunks)
    
    # B. 保存检索结果到缓存
    retrieval_cache[cache_key] = {
        "result": result,
        "timestamp": time.time()
    }
    
    # 清理过期或超出限制的缓存
    if len(retrieval_cache) > RETRIEVAL_CACHE_MAX_SIZE:
        # 删除最旧的 20% 缓存
        sorted_keys = sorted(retrieval_cache.keys(), key=lambda k: retrieval_cache[k]["timestamp"])
        to_remove = sorted_keys[:int(len(sorted_keys) * 0.2)]
        for key in to_remove:
            del retrieval_cache[key]
        print(f"🧹 清理缓存：删除 {len(to_remove)} 个旧条目")
    
    return result

def get_available_models():
    """扫描模型文件夹，返回可用模型列表"""
    models = []
    for f in sorted(os.listdir(MODELS_DIR)):
        if f.endswith('.gguf'):
            size_gb = os.path.getsize(os.path.join(MODELS_DIR, f)) / (1024**3)
            # 简单的命名美化
            name = f.replace('.gguf', '').replace('instruct-', '').replace('qwen2.5-', 'Qwen2.5-')
            models.append({"filename": f, "name": name, "size": f"{size_gb:.1f}GB"})
    return models

def load_model(model_filename):
    """加载指定模型"""
    global llm, current_model_name
    model_path = os.path.join(MODELS_DIR, model_filename)
    
    if not os.path.exists(model_path):
        raise FileNotFoundError(f"Model not found: {model_path}")
    
    print(f"⏳ 正在切换模型: {model_filename} ...")
    
    # 硬件自适应逻辑
    hw_info = get_hardware_info()
    n_gpu_layers = 0
    
    # 根据模型类型动态设置 n_ctx
    if 'gemma' in model_filename.lower():
        # Gemma-2 只支持 8K
        n_ctx = 8192
        print(f"💡 Gemma-2 模型检测到，使用 8K 上下文窗口")
    elif '32b' in model_filename.lower() or '34b' in model_filename.lower():
        # 超大模型（32B+），32GB 内存可以尝试 32K
        n_ctx = 32768
        print(f"💡 32B 超大模型检测到，使用 32K 上下文窗口（注意内存占用）")
    elif '14b' in model_filename.lower():
        # 中型模型（14B），32GB 内存完全可以用 32K
        n_ctx = 32768
        print(f"💡 14B 模型检测到，使用 32K 上下文窗口")
    else:
        # 7B/8B 小模型，可以使用 32K
        n_ctx = 32768
        print(f"💡 7B/8B 模型检测到，使用 32K 上下文窗口")
    
    # 只有当检测到显存且大于 4GB 时才尝试使用 GPU
    if hw_info.get('vram_gb', 0) >= 4:
        if '7b' in model_filename or '8b' in model_filename or 'phi' in model_filename:
            n_gpu_layers = -1 
        else:
            n_gpu_layers = 20 
    else:
        print("💡 未检测到可用 GPU，将强制使用 CPU 模式运行")
        n_gpu_layers = 0
    
    try:
        llm = Llama(
            model_path=model_path,
            n_gpu_layers=n_gpu_layers,
            n_ctx=n_ctx,
            n_threads=8,
            n_batch=512,
            use_mlock=True,  # 恢复原始配置
            verbose=False,
            offload_kqv=True,  # 恢复原始配置
            # A. KV Cache 优化：复用已计算的注意力矩阵
            cache_type_k="f16",
            cache_type_v="f16",
            logits_all=False
        )
        current_model_name = model_filename
        print(f"✅ 模型 {model_filename} 加载成功！(n_ctx={n_ctx}, KV Cache 已启用)")
    except Exception as e:
        error_msg = str(e) if str(e) else f"{type(e).__name__}: {repr(e)}"
        print(f"❌ 模型加载失败: {error_msg}")
        print("💡 尝试使用较小的上下文窗口...")
        try:
            llm = Llama(
                model_path=model_path,
                n_gpu_layers=n_gpu_layers,
                n_ctx=8192,  # 降级到 8K
                n_threads=4,
                n_batch=256,
                use_mlock=False,
                verbose=False,
                cache_type_k="f16",
                cache_type_v="f16"
            )
            current_model_name = model_filename
            print(f"✅ 模型 {model_filename} 加载成功（降级模式）！(n_ctx=8192)")
        except Exception as e2:
            error_msg2 = str(e2) if str(e2) else f"{type(e2).__name__}: {repr(e2)}"
            print(f"❌ 降级加载也失败: {error_msg2}")
            raise Exception(f"模型加载失败: {error_msg2}")

@app.on_event("startup")
async def startup_event():
    import sys
    
    def print_info(msg):
        """强制输出到终端"""
        sys.stdout.write(msg + "\n")
        sys.stdout.flush()
    
    print_info("🚀 便携式 AI 助手启动中...")
    print_info("="*60)
    
    # ==================== 硬件检测 ====================
    import psutil
    
    print_info("\n📊 硬件配置检测：")
    
    # CPU 信息
    cpu_cores = psutil.cpu_count(logical=True)
    cpu_physical = psutil.cpu_count(logical=False)
    cpu_freq = psutil.cpu_freq()
    print_info(f"  🖥️  CPU: {cpu_physical} 物理核心 / {cpu_cores} 逻辑核心")
    if cpu_freq:
        print_info(f"      频率: {cpu_freq.current:.0f} MHz (最大 {cpu_freq.max:.0f} MHz)")
    
    # 内存信息
    memory = psutil.virtual_memory()
    memory_gb = memory.total / (1024**3)
    print_info(f"  💾  内存: {memory_gb:.1f} GB (可用 {memory.available / (1024**3):.1f} GB)")
    
    # GPU 信息
    gpu_available = False
    gpu_name = "无"
    gpu_memory = 0
    try:
        import torch
        if torch.cuda.is_available():
            gpu_available = True
            gpu_name = torch.cuda.get_device_name(0)
            gpu_memory = torch.cuda.get_device_properties(0).total_memory / (1024**3)
            print_info(f"  🎮  GPU: {gpu_name}")
            print_info(f"      显存: {gpu_memory:.1f} GB")
        else:
            print_info(f"  🎮  GPU: 未检测到 NVIDIA GPU（将使用 CPU 推理）")
    except:
        print_info(f"  🎮  GPU: 未检测到 NVIDIA GPU（将使用 CPU 推理）")
    
    # 磁盘信息
    disk = psutil.disk_usage('/')
    disk_free_gb = disk.free / (1024**3)
    print_info(f"  💿  磁盘: 剩余 {disk_free_gb:.1f} GB")
    
    # 硬件评估与建议
    print_info("\n📋 硬件评估与建议：")
    
    # 内存评估
    if memory_gb >= 30:  # 32GB 实际显示约 31GB
        print_info("  ✅ 内存充足：可以运行 7B-14B 模型，推荐 32K 上下文")
        recommended_ctx = 32768
        recommended_model_size = "7B-14B"
    elif memory_gb >= 15:  # 16GB 实际显示约 15GB
        print_info("  ⚠️  内存适中：建议运行 3B-7B 模型，推荐 16K 上下文")
        recommended_ctx = 16384
        recommended_model_size = "3B-7B"
    elif memory_gb >= 7:  # 8GB 实际显示约 7.5GB
        print_info("  ⚠️  内存有限：建议运行 1B-3B 模型，推荐 8K 上下文")
        recommended_ctx = 8192
        recommended_model_size = "1B-3B"
    else:
        print_info("  ❌ 内存不足：建议至少 8GB，当前可能无法正常运行")
        recommended_ctx = 4096
        recommended_model_size = "<1B"
    
    # GPU 评估
    if gpu_available and gpu_memory >= 8:
        print_info("  ✅ GPU 显存充足：可以使用 GPU 加速，速度提升 5-10 倍")
        print_info("  💡 建议：优先使用 GPU 推理")
    elif gpu_available and gpu_memory >= 4:
        print_info("  ⚠️  GPU 显存适中：可以部分卸载到 GPU")
        print_info("  💡 建议：7B 模型可以尝试全 GPU，大模型需 CPU+GPU 混合")
    elif gpu_available:
        print_info("  ⚠️  GPU 显存较小：建议仅卸载部分层")
    else:
        print_info("  ℹ️  CPU 推理：速度较慢但稳定，适合 7B 以下模型")
    
    # 综合推荐
    print_info(f"\n🎯 综合推荐配置：")
    print_info(f"  • 推荐模型大小: {recommended_model_size}")
    print_info(f"  • 推荐上下文窗口: {recommended_ctx} tokens")
    print_info(f"  • 推理模式: {'GPU 加速' if gpu_available else 'CPU 推理'}")
    
    print_info("\n" + "="*60)
    
    # 默认加载 Qwen2.5-7B Coder 模型（代码专用，平衡性能与速度）
    models = get_available_models()
    if models:
        # 1. 优先加载 Qwen2.5-7B Coder
        qwen7b_coder_models = [m for m in models if 'qwen' in m['filename'].lower() and 'coder' in m['filename'].lower() and '7b' in m['filename'].lower()]
        if qwen7b_coder_models:
            print(f"💡 检测到 Qwen2.5-7B Coder 模型，优先加载: {qwen7b_coder_models[0]['filename']}")
            load_model(qwen7b_coder_models[0]['filename'])
        else:
            # 2. 其次加载其他 Qwen2.5-7B 模型
            qwen7b_models = [m for m in models if 'qwen' in m['filename'].lower() and '7b' in m['filename'].lower()]
            if qwen7b_models:
                print(f"💡 未找到 Qwen2.5-7B Coder，加载其他 Qwen2.5-7B 模型: {qwen7b_models[0]['filename']}")
                load_model(qwen7b_models[0]['filename'])
            else:
                # 3. 最后加载其他 7B/8B 模型
                medium_models = [m for m in models if '7b' in m['filename'].lower() or '8b' in m['filename'].lower()]
                if medium_models:
                    print(f"⚠️  未找到 Qwen2.5-7B，加载其他 7B/8B 模型: {medium_models[0]['filename']}")
                    load_model(medium_models[0]['filename'])
                else:
                    # 4. 最后加载小模型
                    small_models = [m for m in models if 'phi' in m['filename'].lower() or '2b' in m['filename'].lower() or '1b' in m['filename'].lower()]
                    if small_models:
                        print(f"💡 未找到 7B/8B 模型，加载小模型: {small_models[0]['filename']}")
                        load_model(small_models[0]['filename'])
                    else:
                        print(f"💡 加载默认模型: {models[0]['filename']}")
                        load_model(models[0]['filename'])
    
    if os.path.exists(FRONTEND_DIR):
        app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")

@app.get("/api/status")
async def get_status():
    return {
        "status": "running",
        "hardware": get_hardware_info(),
        "message": "AI Assistant is ready!"
    }

@app.post("/api/files/upload")
async def upload_files(request: Request):
    """单独的文件上传接口，用于持久化文件到当前会话"""
    if not manager.active_session:
        manager.get_or_create_session("default")
    
    data = await request.json()
    files = data.get("files", [])
    
    # 始终保存文件列表（包括空列表）
    manager.active_session.attached_files = files
    manager.active_session.save_history()
    
    return JSONResponse(content={"status": "success", "files": files})

@app.post("/api/chat")
async def chat_completion(request: Request):
    if llm is None:
        return JSONResponse(status_code=503, content={"response": "模型尚未加载完成"})
    
    # 确保有活跃会话
    if not manager.active_session:
        manager.get_or_create_session("default")

    data = await request.json()
    prompt = data.get("prompt", "")
    mode = data.get("mode", "balanced")
    files = data.get("files", [])
    load_more = data.get("load_more", False)  # 方案 E：渐进式加载标记
    
    # 获取预设参数
    preset = MODE_PRESETS.get(mode, MODE_PRESETS["balanced"])
    temperature = preset["temperature"]
    max_tokens = preset["max_tokens"]
    system_prompt = preset.get("system", "")
    
    # 1. 记录用户输入
    manager.active_session.add_message("user", prompt)
    
    # 2. 更新 Prompt 引擎
    if current_model_name:
        prompt_engine.model_name = current_model_name
    
    # 3. 计算总文件大小，决定策略
    total_file_size = sum(len(f.get('content', '')) for f in files) if files else 0
    history_size = len(manager.active_session.get_formatted_history())
    
    # D. 多文件依赖分析
    if files and len(files) > 1:
        files = analyze_file_dependencies(files)
        print(f"🔗 依赖分析完成：{len(files)} 个文件已按依赖关系排序")
    
    # 使用动态预算分配
    budget = calculate_context_budget(total_file_size, history_size)
    
    # 方案 E：渐进式加载
    if load_more:
        # 用户请求加载更多信息，使用更大的预算
        budget["file_tokens"] = int(budget["model_ctx"] * 0.6)  # 提升到 60%
        print(f"🔄 渐进式加载：扩展文件预算到 {budget['file_tokens']} tokens")
    else:
        print(f"📊 上下文策略: {budget['strategy']}, 文件预算: {budget['file_tokens']} tokens")
    
    # 4. 跨文件智能检索（使用增强版）
    file_contexts = []
    if files and len(files) > 0:
        for f in files:
            f_name = f.get('name')
            f_content = f.get('content')
            if f_content and f_name:
                # 使用增强版检索，传入预算
                relevant_code = find_relevant_chunks_enhanced(prompt, f_content, budget)
                file_contexts.append(f"\n\n[上传的文件: {f_name} (相关片段)]\n```\n{relevant_code}\n```")
    
    # 5. 构建完整 Prompt
    history_text = manager.active_session.get_formatted_history()
    full_prompt = prompt_engine.build_prompt(history_text, prompt + "".join(file_contexts), system_prompt)
    
    # 6. 安全检查与智能摘要
    max_safe_length = 7000
    if len(full_prompt) > max_safe_length:
        print("⚠️ 检测到上下文过长，正在执行智能历史压缩...")
        compressed_history = compress_history_with_llm(manager.active_session.history, llm)
        full_prompt = prompt_engine.build_prompt(compressed_history, prompt + "".join(file_contexts), system_prompt)
        
        # 如果依然超长，强制截断
        if len(full_prompt) > max_safe_length:
            full_prompt = full_prompt[:max_safe_length] + "\n\n[⚠️ 上下文过长，已智能截断]"
            print("⚠️ 执行了强制截断")
    
    # 7. 流式生成
    def generate():
        global generation_stop_flag
        generation_stop_flag = False  # 重置停止标志
        
        # 添加更多停止词，防止模型无限循环
        stop_words = ["<end_of_turn>", "<think>", "</think>", "user:", "assistant:"]
        
        # O. 速度统计
        import time
        start_time = time.time()
        token_count = 0
        
        output = llm(
            full_prompt, 
            max_tokens=max_tokens, 
            stop=stop_words,
            echo=False,
            temperature=temperature,
            stream=True,
            repeat_penalty=1.2,  # 重复惩罚，防止模型重复生成相同内容
            frequency_penalty=0.5,  # 频率惩罚
            presence_penalty=0.5   # 存在惩罚
        )
        
        # 重复检测：记录最近生成的内容
        recent_text = ""
        repeat_threshold = 50  # 如果连续 50 个字符重复，停止生成
        
        for chunk in output:
            # O. 检查停止标志
            if generation_stop_flag:
                print("⚠️ 用户停止生成")
                yield "data: [DONE]\n\n"
                break
            
            text = chunk['choices'][0]['text']
            token_count += 1
            
            # O. 每 10 个 token 发送一次速度信息
            if token_count % 10 == 0:
                elapsed = time.time() - start_time
                speed = token_count / elapsed if elapsed > 0 else 0
                yield f"data: [SPEED] {speed:.1f}\n\n"
            
            # 检测重复：如果当前文本在最近内容中出现多次，停止
            recent_text += text
            if len(recent_text) > 200:
                recent_text = recent_text[-200:]
            
            # 简单重复检测：相同字符连续重复超过 10 次
            if len(text) > 10 and all(c == text[0] for c in text[:10]):
                print("⚠️ 检测到重复字符，停止生成")
                yield "data: [DONE]\n\n"
                break
            
            manager.active_session.append_to_current_response(text)
            yield f"data: {text}\n\n"
        
        # O. 最终速度统计
        elapsed = time.time() - start_time
        speed = token_count / elapsed if elapsed > 0 else 0
        print(f"✅ 生成完成: {token_count} tokens, {elapsed:.1f}s, {speed:.1f} tok/s")
        yield f"data: [SPEED] {speed:.1f}\n\n"
        yield f"data: [DONE]\n\n"
        
        manager.active_session.finalize_ai_response()

    return StreamingResponse(generate(), media_type="text/event-stream")

# ==================== 方案 O: 流式响应优化 ====================

@app.post("/api/chat/stop")
async def stop_generation():
    """停止当前生成"""
    global generation_stop_flag
    generation_stop_flag = True
    return JSONResponse(content={"status": "stopped"})

@app.post("/api/clear")
async def clear_chat():
    """清空当前会话历史"""
    if manager.active_session:
        manager.active_session.clear()
    return JSONResponse(content={"status": "success", "message": "对话已清空"})

@app.get("/api/history")
async def get_history():
    """获取当前会话的历史记录"""
    if manager.active_session:
        return JSONResponse(content={"history": manager.active_session.history})
    return JSONResponse(content={"history": []})

@app.get("/api/context/stats")
async def get_context_stats():
    """获取当前上下文使用情况（方案 C：上下文可视化）"""
    if not manager.active_session:
        return JSONResponse(content={
            "history_tokens": 0,
            "file_tokens": 0,
            "total_used": 0,
            "total_available": 8192,
            "usage_percent": 0,
            "strategy": "unknown"
        })
    
    # 计算历史 tokens
    history_text = manager.active_session.get_formatted_history()
    history_tokens = len(history_text) // 4
    
    # 获取当前文件
    files = manager.active_session.attached_files
    total_file_size = sum(len(f.get('content', '')) for f in files) if files else 0
    
    # 计算预算
    budget = calculate_context_budget(total_file_size, len(history_text))
    
    # 估算当前使用的 tokens（只计算实际使用量）
    # 历史 tokens 是实际使用的
    # 文件 tokens 是预算上限，不是实际使用量
    # 实际文件使用量 = 文件总大小 / 4
    actual_file_tokens = total_file_size // 4 if files else 0
    
    total_used = history_tokens + actual_file_tokens
    usage_percent = int((total_used / budget["model_ctx"]) * 100)
    
    return JSONResponse(content={
        "history_tokens": history_tokens,
        "file_tokens": actual_file_tokens,  # 返回实际使用量
        "file_budget": budget["file_tokens"],  # 返回预算上限
        "total_used": total_used,
        "total_available": budget["total_available"],
        "usage_percent": min(usage_percent, 100),
        "strategy": budget["strategy"],
        "file_count": len(files) if files else 0,
        "total_file_size": total_file_size
    })

# ==================== 方案 M: 资源监控面板 ====================

@app.get("/api/system/resources")
async def get_system_resources():
    """获取系统资源使用情况（实时）"""
    import psutil
    
    # CPU 信息
    cpu_percent = psutil.cpu_percent(interval=0.1)
    cpu_freq = psutil.cpu_freq()
    
    # 内存信息
    memory = psutil.virtual_memory()
    
    # 磁盘信息
    disk = psutil.disk_usage('/')
    
    # 进程信息（当前 Python 进程）
    process = psutil.Process()
    process_memory = process.memory_info()
    
    # GPU 信息（如果有）
    gpu_info = {
        "available": False,
        "name": "None",
        "memory_used_gb": 0,
        "memory_total_gb": 0,
        "utilization": 0
    }
    
    try:
        import torch
        if torch.cuda.is_available():
            gpu_info["available"] = True
            gpu_info["name"] = torch.cuda.get_device_name(0)
            gpu_memory = torch.cuda.memory_allocated(0) / (1024**3)
            gpu_total = torch.cuda.get_device_properties(0).total_mem / (1024**3)
            gpu_info["memory_used_gb"] = round(gpu_memory, 2)
            gpu_info["memory_total_gb"] = round(gpu_total, 2)
            gpu_info["utilization"] = torch.cuda.utilization(0) if hasattr(torch.cuda, 'utilization') else 0
    except:
        pass
    
    return JSONResponse(content={
        "cpu": {
            "percent": cpu_percent,
            "cores": psutil.cpu_count(logical=True),  # 显示逻辑核心数（含超线程）
            "frequency_mhz": round(cpu_freq.current, 0) if cpu_freq else 0
        },
        "memory": {
            "total_gb": round(memory.total / (1024**3), 2),
            "used_gb": round(memory.used / (1024**3), 2),
            "available_gb": round(memory.available / (1024**3), 2),
            "percent": memory.percent
        },
        "process": {
            "memory_mb": round(process_memory.rss / (1024**2), 2),
            "cpu_percent": process.cpu_percent(interval=0.1),
            "threads": process.num_threads()
        },
        "disk": {
            "total_gb": round(disk.total / (1024**3), 2),
            "used_gb": round(disk.used / (1024**3), 2),
            "free_gb": round(disk.free / (1024**3), 2),
            "percent": disk.percent
        },
        "gpu": gpu_info,
        "model": {
            "loaded": current_model_name is not None,
            "name": current_model_name or "未加载",
            "context_window": llm.n_ctx() if llm else 0
        }
    })

@app.get("/api/sessions")
async def list_sessions():
    """获取所有会话列表"""
    return JSONResponse(content={"sessions": manager.list_sessions()})

# ==================== 方案 N: 模型热切换 ====================

@app.get("/api/models")
async def list_models():
    """获取可用模型列表"""
    import glob
    models = []
    for ext in ['*.gguf', '*.bin']:
        models.extend(glob.glob(os.path.join(MODELS_DIR, ext)))
    
    model_list = []
    for path in models:
        filename = os.path.basename(path)
        size_mb = os.path.getsize(path) / (1024 * 1024)
        size_gb = size_mb / 1024
        
        # 生成友好的名称
        name = filename.replace('.gguf', '').replace('.bin', '')
        if 'qwen' in filename.lower():
            if 'coder' in filename.lower():
                name = 'Qwen2.5-Coder-7B'
            elif '14b' in filename.lower():
                name = 'Qwen2.5-14B'
            elif '32b' in filename.lower():
                name = 'Qwen2.5-32B'
            else:
                name = 'Qwen2.5-7B'
        elif 'llama' in filename.lower():
            name = 'Llama3.1-8B'
        elif 'gemma' in filename.lower():
            name = 'Gemma2-9B'
        elif 'phi' in filename.lower():
            name = 'Phi3.5-Mini'
        
        model_list.append({
            "filename": filename,
            "name": name,
            "size": f"{size_gb:.1f}GB",
            "size_mb": round(size_mb, 0),
            "current": filename == current_model_name
        })
    
    return JSONResponse(content={"models": model_list})

@app.post("/api/model/switch")
async def switch_model(request: Request):
    """热切换模型（所有模型都尝试直接切换）"""
    global llm, current_model_name
    
    data = await request.json()
    model_filename = data.get("model")
    
    if not model_filename:
        return JSONResponse(status_code=400, content={"error": "Missing model filename"})
    
    try:
        # 保存当前会话状态
        if manager.active_session:
            manager.active_session.save_history()
        
        # 直接加载新模型（llama-cpp-python 0.3.20 支持更好的热切换）
        print(f"🔄 正在切换模型: {model_filename} ...")
        load_model(model_filename)
        
        return JSONResponse(content={
            "status": "success",
            "model": current_model_name,
            "message": f"模型已切换至 {model_filename}",
            "need_restart": False
        })
        
    except Exception as e:
        error_msg = str(e) if str(e) else f"{type(e).__name__}"
        print(f"❌ 模型切换失败: {error_msg}")
        return JSONResponse(status_code=500, content={"error": error_msg})

@app.post("/api/session/switch")
async def switch_session(request: Request):
    """切换当前会话"""
    data = await request.json()
    session_id = data.get("session_id")
    if session_id:
        manager.get_or_create_session(session_id)
        return JSONResponse(content={
            "status": "success", 
            "history": manager.active_session.history,
            "files": manager.active_session.attached_files # 返回关联文件
        })
    return JSONResponse(status_code=400, content={"error": "Missing session_id"})

# ==================== 方案 J: 导出对话记录 ====================

@app.get("/api/session/export/{session_id}")
async def export_session(session_id: str):
    """导出指定会话为 Markdown 格式"""
    from fastapi.responses import Response
    
    # 临时切换到该会话
    original_session = manager.active_session
    target_session = None
    
    try:
        # 加载目标会话
        target_session = manager.get_or_create_session(session_id)
        
        # 构建 Markdown 内容
        md_content = f"# AI 对话记录\n\n"
        md_content += f"**导出时间**: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        md_content += f"**会话 ID**: {session_id}\n\n"
        md_content += "---\n\n"
        
        for msg in target_session.history:
            role = msg.get('role', 'unknown')
            content = msg.get('content', '')
            timestamp = msg.get('timestamp', 0)
            time_str = time.strftime('%H:%M:%S', time.localtime(timestamp))
            
            if role == 'user':
                md_content += f"## 👤 用户 ({time_str})\n\n{content}\n\n"
            elif role == 'assistant':
                md_content += f"## 🤖 AI ({time_str})\n\n{content}\n\n"
            
            md_content += "---\n\n"
        
        # 如果有附件文件，也导出
        if target_session.attached_files:
            md_content += "## 📎 附加文件\n\n"
            for f in target_session.attached_files:
                f_name = f.get('name', 'unknown')
                f_size = len(f.get('content', ''))
                md_content += f"- **{f_name}** ({f_size} 字节)\n"
            md_content += "\n"
        
        # 恢复原始会话
        if original_session:
            manager.active_session = original_session
        
        # 返回 Markdown 文件
        filename = f"conversation_{session_id}_{int(time.time())}.md"
        return Response(
            content=md_content.encode('utf-8'),
            media_type="text/markdown",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
        
    except Exception as e:
        if original_session:
            manager.active_session = original_session
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.post("/api/session/create")
async def create_session(request: Request):
    """创建新会话"""
    data = await request.json()
    name = data.get("name", "新对话")
    session_id = f"session_{int(time.time())}"
    manager.get_or_create_session(session_id, name=name)
    return JSONResponse(content={"status": "success", "session_id": session_id})

@app.post("/api/session/delete")
async def delete_session(request: Request):
    """删除指定会话"""
    data = await request.json()
    session_id = data.get("session_id")
    if manager.delete_session(session_id):
        return JSONResponse(content={"status": "success"})
    return JSONResponse(status_code=404, content={"error": "Session not found"})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
