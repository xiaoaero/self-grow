@echo off
chcp 65001 >nul
echo ========================================
echo   Self Grow 桌面应用构建脚本
echo ========================================
echo.

:: Step 1: 安装 PyInstaller
echo [1/4] 安装 PyInstaller...
cd backend
pixi run pip install pyinstaller >nul 2>&1

:: Step 2: 打包后端
echo [2/4] 打包 Python 后端...
pixi run pyinstaller --clean --noconfirm self_grow_server.spec
if errorlevel 1 (
    echo ❌ 后端打包失败！
    pause
    exit /b 1
)
cd ..

:: Step 3: 安装 Electron 依赖
echo [3/4] 安装 Electron 依赖...
cd desktop
call npm install
if errorlevel 1 (
    echo ❌ npm install 失败！
    pause
    exit /b 1
)
cd ..

:: Step 4: 打包 Electron 应用
echo [4/4] 打包桌面应用...
cd desktop
call npm run build
if errorlevel 1 (
    echo ❌ Electron 打包失败！
    pause
    exit /b 1
)
cd ..

echo.
echo ========================================
echo   ✅ 构建完成！
echo   安装包位置: desktop\dist\
echo ========================================
pause
