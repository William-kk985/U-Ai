#!/bin/bash
# Portable AI Assistant 桌面启动脚本

PROJECT_DIR="/home/rm/AI"
LOG_FILE="$PROJECT_DIR/05_Data/logs/startup.log"

# 检查服务是否已经在运行
if curl -s http://localhost:8000/api/models > /dev/null 2>&1; then
    # 服务已在运行，直接打开浏览器
    echo "✅ 服务已在运行，打开应用..."
    xdg-open http://localhost:8000
    exit 0
fi

# 启动服务
echo "🚀 正在启动 Portable AI Assistant..."
echo "[$(date)] 启动服务..." >> "$LOG_FILE"

cd "$PROJECT_DIR"
bash 99_Scripts/start.sh >> "$LOG_FILE" 2>&1 &

# 等待服务就绪
echo "⏳ 等待服务启动..."
for i in {1..15}; do
    if curl -s http://localhost:8000/api/models > /dev/null 2>&1; then
        echo "✅ 服务已就绪，打开应用..."
        sleep 1
        xdg-open http://localhost:8000
        exit 0
    fi
    sleep 1
done

# 如果超时，显示错误
echo "❌ 服务启动超时，请检查日志"
notify-send "91情趣" "服务启动失败，请查看日志" -i error
