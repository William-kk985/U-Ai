#!/bin/bash
echo "=========================================="
echo "  Stopping Portable AI Assistant..."
echo "=========================================="

# 获取脚本所在目录
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

# 尝试从 PID 文件停止
if [ -f "$ROOT_DIR/05_Data/server.pid" ]; then
    PID=$(cat "$ROOT_DIR/05_Data/server.pid")
    if ps -p $PID > /dev/null 2>&1; then
        echo "🛑 停止进程 PID: $PID"
        kill $PID
        sleep 2
        
        # 检查是否还在运行
        if ps -p $PID > /dev/null 2>&1; then
            echo "⚠️  进程未响应，强制终止..."
            kill -9 $PID
        fi
        
        rm -f "$ROOT_DIR/05_Data/server.pid"
        echo "✅ 服务已停止"
    else
        echo "⚠️  PID 文件存在但进程不存在: $PID"
        rm -f "$ROOT_DIR/05_Data/server.pid"
    fi
else
    # 通过进程名查找并停止
    PIDS=$(ps aux | grep "[p]ython main.py" | awk '{print $2}')
    if [ -n "$PIDS" ]; then
        echo "🛑 发现运行中的进程: $PIDS"
        echo $PIDS | xargs kill
        sleep 2
        
        # 检查是否还有残留
        REMAINING=$(ps aux | grep "[p]ython main.py" | awk '{print $2}')
        if [ -n "$REMAINING" ]; then
            echo "⚠️  强制终止残留进程..."
            echo $REMAINING | xargs kill -9
        fi
        
        echo "✅ 所有服务已停止"
    else
        echo "ℹ️  没有发现运行中的服务"
    fi
fi

# 清理端口占用（可选）
if netstat -tuln 2>/dev/null | grep -q ":8000 "; then
    echo "⚠️  端口 8000 仍被占用，可能需要手动检查"
else
    echo "✅ 端口 8000 已释放"
fi

echo "=========================================="
