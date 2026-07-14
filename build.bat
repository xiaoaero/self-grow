@echo off
chcp 65001 >nul
echo ========================================
echo   Self Grow 桌面应用构建脚本
echo ========================================
echo.

:: Step 1: 打包后端
echo [1/4] 打包 Python 后端...
cd backend
pixi run pyinstaller --clean --noconfirm self_grow_server.spec
if errorlevel 1 (
    echo ❌ 后端打包失败！
    pause
    exit /b 1
)
cd ..
echo ✅ 后端打包完成

:: Step 2: 安装 Electron 依赖
echo [2/4] 安装 Electron 依赖...
cd desktop
call npm install
if errorlevel 1 (
    echo ❌ npm install 失败！
    pause
    exit /b 1
)
cd ..
echo ✅ Electron 依赖安装完成

:: Step 3: 打包 Electron 应用（--dir 模式，生成绿色版目录）
echo [3/4] 打包 Electron 应用...
cd desktop
call npm run build:dir
if errorlevel 1 (
    echo ❌ Electron 打包失败！
    echo.
    echo 💡 如果是 winCodeSign 符号链接错误，请开启 Windows 开发者模式：
    echo    设置 → 更新和安全 → 开发者选项 → 开启开发人员模式
    echo    然后重新运行此脚本。
    pause
    exit /b 1
)
cd ..
echo ✅ Electron 打包完成

:: Step 4: 生成绿色版 zip
echo [4/4] 生成绿色版安装包...
cd desktop
node make-portable.js
if errorlevel 1 (
    echo ⚠️ 绿色版打包失败，但 dist/SelfGrow/ 目录已可用
)
cd ..

echo.
echo ========================================
echo   ✅ 构建完成！
echo   绿色版目录: desktop\dist\SelfGrow\
echo   压缩包:     desktop\dist\SelfGrow-v1.0-portable.zip
echo.
echo   💡 如需生成 NSIS 安装包，请先开启 Windows 开发者模式
echo      然后运行: cd desktop && npm run build
echo ========================================
pause
