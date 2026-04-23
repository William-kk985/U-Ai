# 🤖 便携式 AI U盘助手

一个完全离线、可放入 U 盘的本地 AI 助手，支持多种开源大语言模型。

## ✨ 特性

- 🔌 **即插即用**：无需安装，插入 U 盘即可使用
- 🌐 **完全离线**：所有数据处理在本地，保护隐私
- 🔄 **多模型热切换**：无需重启服务，秒级切换不同模型
- 💻 **跨平台**：支持 Linux/Windows/macOS
- 📁 **文件分析**：拖拽上传代码文件，智能检索相关片段
- 🎨 **代码高亮**：专业的语法高亮显示
- 💾 **会话管理**：自动保存对话历史，支持多会话隔离
- 📤 **导出功能**：一键导出对话为 Markdown 格式

## 🚀 快速开始

### **方式一：已有打包环境（推荐）**

如果你已经有完整的 U 盘文件（包含 `00_Env/` 和 `01_Models/`）：

#### Linux/macOS
```bash
cd 02_Backend
../00_Env/portable/bin/python main.py
```

#### Windows
双击 `99_Scripts/start.bat`

#### 访问界面
浏览器打开：http://localhost:8000

---

### **方式二：从源码构建环境**

如果你只有代码仓库，需要先构建运行环境：

#### 步骤 1：安装 Miniconda
```bash
# 下载 Miniconda 安装器
wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh

# 安装到 ~/miniconda3
bash Miniconda3-latest-Linux-x86_64.sh -b -p $HOME/miniconda3

# 初始化
$HOME/miniconda3/bin/conda init bash
source ~/.bashrc
```

#### 步骤 2：创建 Conda 环境
```bash
conda create -n ai_env python=3.10 -y
conda activate ai_env
```

#### 步骤 3：安装依赖
```bash
cd /path/to/AI
pip install fastapi uvicorn llama-cpp-python==0.3.20 markdown
```

#### 步骤 4：下载模型
```bash
# 创建模型目录
mkdir -p 01_Models

# 下载示例模型（Qwen2.5-Coder-7B）
# 从 HuggingFace 下载 GGUF 格式模型到 01_Models/
# 推荐：https://huggingface.co/Qwen/Qwen2.5-Coder-7B-Instruct-GGUF
```

#### 步骤 5：启动服务
```bash
cd 02_Backend
python main.py
```

---

### **方式三：打包便携环境（用于 U 盘分发）**

如果你想创建可分发的便携环境：

```bash
# 在 conda 环境中执行
cd 99_Scripts
bash pack_portable.sh

# 这会创建 portable_env_packed.tar.gz
# 解压后即可得到 00_Env/portable/ 目录
```

## 📦 项目结构

```
AI/
├── 00_Env/              # Python 运行环境（需要打包或从源码构建）
│   └── portable/        # 便携式 Python（约 2-3 GB）
├── 01_Models/           # LLM 模型文件（GGUF 格式，需自行下载）
├── 02_Backend/          # FastAPI 后端服务
├── 03_Frontend/         # 前端界面（原生 JS）
├── 04_Core/             # AI 核心逻辑
├── 05_Data/             # 会话数据（自动生成）
└── 99_Scripts/          # 启动/停止/打包脚本
```

详见 [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md)

## ✅ 首次使用检查清单

在第一次使用前，请确认：

- [ ] **已安装 Python 环境**
  - 方式一：已有 `00_Env/portable/` 目录
  - 方式二：已从源码构建 Conda 环境
  
- [ ] **已下载至少一个模型**
  - 模型文件放在 `01_Models/` 目录
  - 推荐首选：Qwen2.5-Coder-7B（约 5GB）
  - 下载地址：https://huggingface.co/Qwen/Qwen2.5-Coder-7B-Instruct-GGUF
  
- [ ] **已安装依赖包**
  ```bash
  pip install fastapi uvicorn llama-cpp-python==0.3.20 markdown
  ```
  
- [ ] **端口 8000 未被占用**
  ```bash
  # 检查端口
  lsof -i :8000
  ```

## 🎯 支持的模型

| 模型 | 大小 | 用途 | CPU 速度 |
|------|------|------|---------|
| Qwen2.5-Coder-7B | ~5GB | 代码生成/解释 | ~18 tok/s |
| Qwen2.5-14B | ~9GB | 通用对话 | ~10 tok/s |
| Qwen2.5-32B | ~20GB | 复杂任务 | ~5 tok/s |
| Llama-3.1-8B | ~5GB | 英文对话 | ~18 tok/s |
| Gemma-2-9B | ~6GB | 轻量级对话 | ~15 tok/s |
| Phi-3.5-Mini | ~2GB | 快速响应 | ~25 tok/s |

*速度基于 Intel i7-14700K CPU 测试*

## 🔧 高级用法

### **添加新模型**
1. 下载 GGUF 格式模型到 `01_Models/` 目录
2. 刷新浏览器，模型自动出现在下拉列表中
3. 点击即可切换

推荐下载站点：
- HuggingFace: https://huggingface.co/models
- TheBloke: https://huggingface.co/TheBloke

### **GPU 加速（可选）**
如果有 NVIDIA GPU，可以启用 CUDA 加速：

```bash
cd 99_Scripts
bash upgrade_to_gpu.sh
```

速度提升：**5-7 倍**（RTX 4070 可达 90-120 tok/s）

### **自定义配置**
编辑 `02_Backend/main.py`：
- 修改默认模型（第 847 行）
- 调整上下文窗口（第 700 行）
- 更改端口号（第 1380 行）

## 📊 系统要求

### **最低配置**
- CPU：4 核心
- 内存：8GB
- 磁盘：10GB 可用空间

### **推荐配置**
- CPU：8+ 核心
- 内存：16GB+
- GPU：NVIDIA RTX 3060+（可选）
- 磁盘：50GB+ SSD

## 🛠️ 技术栈

- **后端**：FastAPI + Uvicorn
- **推理引擎**：llama-cpp-python 0.3.20
- **前端**：原生 JavaScript + CDN
- **UI 组件**：Marked.js + Highlight.js
- **环境管理**：Conda + Portable Python

## 📝 常见问题

### **Q: 为什么启动这么慢？**
A: 首次加载模型需要 10-60 秒（取决于模型大小），后续切换会快很多。

### **Q: 可以在没有网络的电脑上使用吗？**
A: 可以！所有依赖都已打包，完全离线运行。

### **Q: 如何备份会话数据？**
A: 复制 `05_Data/sessions/` 目录即可。

### **Q: 模型切换失败怎么办？**
A: llama-cpp-python 0.3.20 支持所有主流模型的热切换。如果失败，请检查日志：
```bash
tail -f /tmp/ai_server.log
```

## 📄 许可证

本项目仅供学习和研究使用。使用的开源模型遵循各自的许可证。

## 🙏 致谢

- [llama.cpp](https://github.com/ggerganov/llama.cpp) - 高效的 LLM 推理引擎
- [HuggingFace](https://huggingface.co/) - 开源模型社区
- [FastAPI](https://fastapi.tiangolo.com/) - 现代化的 Python Web 框架

---

**Made with ❤️ for Portable AI**
