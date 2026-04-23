#!/bin/bash

echo "=========================================="
echo "  Starting Portable AI Assistant..."
echo "=========================================="

# 获取脚本所在目录
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
PID_FILE="$ROOT_DIR/05_Data/server.pid"
LOG_FILE="$ROOT_DIR/05_Data/logs/server.log"

# 创建日志目录
mkdir -p "$ROOT_DIR/05_Data/logs"

# 检查是否已经在运行
if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if ps -p $PID > /dev/null 2>&1; then
        echo "⚠️  服务已在运行 (PID: $PID)"
        echo "💡 如需重启，请先运行: bash stop.sh"
        exit 1
    else
        echo "⚠️  清理过期的 PID 文件"
        rm -f "$PID_FILE"
    fi
fi

# 检查端口是否被占用
PORT=8000
if command -v lsof &> /dev/null; then
    if lsof -i :$PORT > /dev/null 2>&1; then
        echo "❌ 端口 $PORT 已被占用"
        echo "💡 请检查并停止占用端口的进程，或修改 config.json 中的端口配置"
        exit 1
    fi
fi

# 检查 Python 环境
PYTHON_PATH="$ROOT_DIR/00_Env/portable/bin/python"
if [ ! -f "$PYTHON_PATH" ]; then
    echo "❌ 未找到 Python 环境: $PYTHON_PATH"
    echo "💡 请确认 00_Env/portable 目录存在且完整"
    exit 1
fi

# 检查主程序文件
if [ ! -f "$ROOT_DIR/02_Backend/main.py" ]; then
    echo "❌ 未找到主程序: 02_Backend/main.py"
    exit 1
fi

echo "✅ 环境检查通过"
echo "📝 启动服务..."

# 设置环境变量
export PYTHONPATH="$ROOT_DIR/02_Backend"
export PATH="$ROOT_DIR/00_Env/portable/bin:$PATH"
export LD_LIBRARY_PATH="$ROOT_DIR/00_Env/portable/lib:$LD_LIBRARY_PATH"

# 后台启动服务并重定向日志
cd "$ROOT_DIR/02_Backend"
nohup python main.py > "$LOG_FILE" 2>&1 &
SERVER_PID=$!

# 记录 PID
echo $SERVER_PID > "$PID_FILE"

echo "🕐 等待服务就绪..."

# 等待服务启动（最多等待 30 秒）
MAX_WAIT=30
WAIT_COUNT=0
while [ $WAIT_COUNT -lt $MAX_WAIT ]; do
    if curl -s http://localhost:$PORT > /dev/null 2>&1; then
        echo ""
        echo "=========================================="
        echo "  ✅ 服务启动成功！"
        echo "=========================================="
        echo "🌐 访问地址: http://localhost:$PORT"
        echo "📋 进程 PID: $SERVER_PID"
        echo "📝 日志文件: $LOG_FILE"
        echo ""
        echo "💡 常用命令:"
        echo "   查看状态: bash status.sh"
        echo "   查看日志: tail -f $LOG_FILE"
        echo "   停止服务: bash stop.sh"
        echo "=========================================="
        exit 0
    fi
    
    # 检查进程是否还在运行
    if ! ps -p $SERVER_PID > /dev/null 2>&1; then
        echo ""
        echo "❌ 服务启动失败，请查看日志:"
        echo "   tail -f $LOG_FILE"
        rm -f "$PID_FILE"
        exit 1
    fi
    
    sleep 1
    WAIT_COUNT=$((WAIT_COUNT + 1))
    printf "\r   等待中... ($WAIT_COUNT/$MAX_WAIT 秒)"
done

echo ""
echo "⚠️  服务启动超时，可能仍在初始化"
echo "📝 请查看日志确认状态: tail -f $LOG_FILE"
echo "📋 进程 PID: $SERVER_PID"
