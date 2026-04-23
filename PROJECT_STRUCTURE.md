# 便携式 AI U盘助手 - 项目结构

## 📁 目录说明

```
AI/
├── 00_Env/                      # 环境管理
│   ├── portable/                # 便携式 Python 环境（已解压）
│   ├── ai_env_packed.tar.gz     # Conda 环境备份
│   └── portable_env_packed.tar.gz # 便携环境备份
│
├── 01_Models/                   # LLM 模型文件
│   ├── qwen2.5-coder-7b-q6_k.gguf
│   ├── qwen2.5-14b-instruct-q4_k_m.gguf
│   ├── qwen2.5-32b-instruct-q6_k.gguf
│   ├── llama-3.1-8b-instruct-q6_k.gguf
│   ├── gemma-2-9b-it-q4_k_m.gguf
│   └── phi-3.5-mini-instruct-q4_k_m.gguf
│
├── 02_Backend/                  # 后端服务
│   ├── main.py                  # FastAPI 主程序
│   ├── services/                # 服务模块
│   │   ├── detector.py          # 硬件检测
│   │   └── ...
│   └── config/                  # 配置文件
│
├── 03_Frontend/                 # 前端界面
│   └── dist/
│       └── index.html           # 单页应用（原生 JS + CDN）
│
├── 04_Core/                     # AI 核心逻辑
│   ├── prompt_builder.py        # 提示词构建
│   ├── session_manager.py       # 会话管理
│   └── ...
│
├── 05_Data/                     # 数据文件
│   └── sessions/                # 会话历史记录
│       ├── *.json               # 各会话数据
│       └── next_model.txt       # （已废弃）
│
├── 99_Scripts/                  # 工具脚本
│   ├── start.sh                 # 启动服务
│   ├── stop.sh                  # 停止服务
│   ├── restart_server.sh        # 重启服务（可选）
│   └── upgrade_to_gpu.sh        # GPU 升级脚本
│
├── Portable_AI_Architecture_Guide.md  # 架构设计文档
├── README.md                    # 项目说明（待创建）
└── .gitignore                   # Git 忽略规则
```

## 🚀 快速开始

### **启动服务**
```bash
cd /home/rm/AI/02_Backend
../00_Env/portable/bin/python main.py
```

### **访问界面**
浏览器打开：http://localhost:8000

### **停止服务**
```bash
pkill -f "python.*main.py"
```

## 📦 环境说明

### **llama-cpp-python**
- 版本：0.3.20
- 安装方式：pip
- 特性：支持所有主流模型架构的热切换

### **Python 环境**
- 版本：3.10
- 位置：`00_Env/portable/`
- 打包格式：tar.gz（308MB）

## 🎯 核心功能

1. **多模型热切换**：所有模型无需重启，直接切换
2. **流式响应**：实时显示生成速度和停止按钮
3. **会话管理**：多对话隔离，自动保存
4. **文件上传**：拖拽上传，智能检索
5. **代码高亮**：highlight.js 语法高亮
6. **导出对话**：Markdown 格式导出

## 🔧 开发说明

### **添加新模型**
1. 下载 GGUF 格式模型到 `01_Models/`
2. 重启服务，自动识别

### **修改前端**
编辑 `03_Frontend/dist/index.html`，刷新浏览器即可

### **修改后端**
编辑 `02_Backend/main.py`，重启服务生效

## 📝 注意事项

- 模型文件较大（4-20GB），建议使用外部存储
- 首次加载模型需要 10-60 秒（取决于模型大小）
- CPU 推理速度约 15-20 token/s
- RTX 4070 GPU 加速可达 90-120 token/s
