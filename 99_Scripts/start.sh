#!/bin/bash
echo "=========================================="
echo "  Starting Portable AI Assistant..."
echo "=========================================="

# 获取脚本所在目录
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

# 设置环境变量 (指向打包后的便携环境)
export PYTHONPATH="$ROOT_DIR/02_Backend"
export PATH="$ROOT_DIR/00_Env/portable/bin:$PATH"
export LD_LIBRARY_PATH="$ROOT_DIR/00_Env/portable/lib:$LD_LIBRARY_PATH"

# 启动后端服务
cd "$ROOT_DIR/02_Backend"
python main.py &

# 记录 PID 以便停止
echo $! > "$ROOT_DIR/05_Data/server.pid"

echo "Service started at http://localhost:8000"
