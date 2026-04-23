#!/bin/bash
# macOS 启动脚本
# 双击此文件即可启动（需要先在终端执行一次：chmod +x start.command）

echo "=========================================="
echo "  Starting Portable AI Assistant (macOS)..."
echo "=========================================="

# 获取脚本所在目录
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

# 检查便携环境是否存在
if [ ! -d "$ROOT_DIR/00_Env/portable" ]; then
    echo "❌ Portable environment not found!"
    echo "Please run setup first."
    read -p "Press Enter to exit..."
    exit 1
fi

# 设置环境变量
export PYTHONPATH="$ROOT_DIR/02_Backend"
export PATH="$ROOT_DIR/00_Env/portable/bin:$PATH"
export DYLD_LIBRARY_PATH="$ROOT_DIR/00_Env/portable/lib:$DYLD_LIBRARY_PATH"

# 启动后端服务
cd "$ROOT_DIR/02_Backend"
echo "🚀 Starting backend service..."
python main.py &

# 记录 PID
echo $! > "$ROOT_DIR/05_Data/server.pid"

echo ""
echo "✅ Service started!"
echo "🌐 Open browser: http://localhost:8000"
echo ""
echo "ℹ️  To stop the service, run:"
echo "   ./stop.command"
echo ""
echo "=========================================="

# 保持窗口打开
read -p "Press Enter to close this window (service will continue running)..."
