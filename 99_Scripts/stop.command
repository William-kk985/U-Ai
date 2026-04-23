#!/bin/bash
# macOS 停止脚本
# 双击此文件即可停止服务

echo "=========================================="
echo "  Stopping Portable AI Assistant (macOS)..."
echo "=========================================="

# 获取脚本所在目录
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

# 尝试从 PID 文件停止
if [ -f "$ROOT_DIR/05_Data/server.pid" ]; then
    PID=$(cat "$ROOT_DIR/05_Data/server.pid")
    if ps -p $PID > /dev/null 2>&1; then
        echo "🛑 Stopping process PID: $PID"
        kill $PID
        sleep 2
        
        # 检查是否还在运行
        if ps -p $PID > /dev/null 2>&1; then
            echo "⚠️  Process not responding, force killing..."
            kill -9 $PID
        fi
        
        rm -f "$ROOT_DIR/05_Data/server.pid"
        echo "✅ Service stopped"
    else
        echo "⚠️  PID file exists but process not found: $PID"
        rm -f "$ROOT_DIR/05_Data/server.pid"
    fi
else
    # 通过进程名查找并停止
    PIDS=$(ps aux | grep "[p]ython main.py" | awk '{print $2}')
    if [ -n "$PIDS" ]; then
        echo "🛑 Found running processes: $PIDS"
        echo $PIDS | xargs kill
        sleep 2
        
        # 检查是否还有残留
        REMAINING=$(ps aux | grep "[p]ython main.py" | awk '{print $2}')
        if [ -n "$REMAINING" ]; then
            echo "⚠️  Force killing remaining processes..."
            echo $REMAINING | xargs kill -9
        fi
        
        echo "✅ All services stopped"
    else
        echo "ℹ️  No running service found"
    fi
fi

# 检查端口
if lsof -i :8000 > /dev/null 2>&1; then
    echo "⚠️  Port 8000 still in use, may need manual check"
else
    echo "✅ Port 8000 released"
fi

echo "=========================================="
read -p "Press Enter to close this window..."
