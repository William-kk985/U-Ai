@echo off
echo ==========================================
echo   Stopping Portable AI Assistant...
echo ==========================================

REM 检查 PID 文件
if exist "..\05_Data\server.pid" (
    set /p PID=<..\05_Data\server.pid
    echo Stopping process PID: %PID%
    taskkill /PID %PID% /T /F >nul 2>&1
    
    if %errorlevel% equ 0 (
        echo ✅ Service stopped successfully
    ) else (
        echo ⚠️  Process not found or already stopped
    )
    
    del "..\05_Data\server.pid" >nul 2>&1
) else (
    REM 通过进程名查找并停止
    echo Searching for running processes...
    tasklist /FI "IMAGENAME eq python.exe" | findstr /I "main.py" >nul 2>&1
    
    if %errorlevel% equ 0 (
        echo 🛑 Found running processes, stopping...
        taskkill /F /IM python.exe /FI "WINDOWTITLE eq *main.py*" >nul 2>&1
        echo ✅ All services stopped
    ) else (
        echo ℹ️  No running service found
    )
)

REM 检查端口
netstat -ano | findstr ":8000" >nul 2>&1
if %errorlevel% equ 0 (
    echo ⚠️  Port 8000 still in use, may need manual check
) else (
    echo ✅ Port 8000 released
)

echo ==========================================
pause
