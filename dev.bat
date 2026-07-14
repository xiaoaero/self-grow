@echo off
chcp 65001 >nul
echo ========================================
echo   Self Grow 开发模式启动
echo ========================================
echo.

:: 启动后端（后台）
echo [1/2] 启动后端...
cd backend
start "Self Grow 后端" cmd /k "pixi run python main.py"
cd ..

:: 等待后端启动
timeout /t 3 /nobreak >nul

:: 启动前端
echo [2/2] 启动前端...
start "Self Grow 前端" cmd /k "python -m http.server 3000"

:: 等待前端启动
timeout /t 2 /nobreak >nul

:: 打开浏览器
echo 正在打开浏览器...
start http://localhost:3000/login.html

echo.
echo ✅ 启动完成！关闭命令行窗口即可停止服务。
