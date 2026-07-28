@echo off
chcp 65001 >nul
title Self Grow 开发环境
echo ========================================
echo   Self Grow 开发模式启动
echo ========================================
echo.

:: 清理残留的后端进程
echo 清理旧进程...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":3001" 2^>nul') do (
    taskkill /f /pid %%a 2>nul
)

:: 启动后端（独立窗口，方便看日志）
echo [1/2] 启动后端 :3001...
start "Self Grow 后端" cmd /c "cd /d D:\pycharm\projec\self_grow_system\backend && pixi run python main.py"

:: 等待后端启动
timeout /t 3 /nobreak >nul

:: 启动前端（npx http-server，推荐方式）
echo [2/2] 启动前端 :3000...
echo.
echo 前端地址: http://localhost:3000/login.html
echo 关闭此窗口即可停止服务
echo.
cd /d D:\pycharm\projec\self_grow_system
npx http-server -p 3000 -c-1

:: 前端关闭后，自动清理后端进程
taskkill /fi "WINDOWTITLE eq Self Grow 后端" /f 2>nul
pause
