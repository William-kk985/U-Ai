@echo off
echo ==========================================
echo   Starting Portable AI Assistant...
echo ==========================================

:: 设置环境变量
set PYTHONPATH=%~dp002_Backend
set PATH=%~dp000_Env\Scripts;%PATH%

:: 启动后端服务
cd 02_Backend
start "" python main.py

:: 等待几秒让服务启动
timeout /t 3 /nobreak >nul

:: 打开浏览器
start http://localhost:8000

echo Service started. Check the console for details.
pause
