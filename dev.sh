#!/bin/bash
echo "========================================"
echo "  Self Grow 开发模式启动"
echo "========================================"
echo ""

# 清理旧后端进程
echo "清理旧进程..."
kill "$(lsof -ti:3001)" 2>/dev/null || true

# 启动后端（后台）
echo "[1/2] 启动后端 :3001..."
cd "$(dirname "$0")/backend" || exit
pixi run python main.py &
BACKEND_PID=$!
cd ..

# 等待后端启动
sleep 3

# 启动前端（前台）
echo "[2/2] 启动前端 :3000..."
echo ""
echo "前端地址: http://localhost:3000/login.html"
echo "按 Ctrl+C 停止服务"
echo ""
npx http-server -p 3000 -c-1

# 前端停止后清理后端
echo "停止后端服务..."
kill $BACKEND_PID 2>/dev/null
kill "$(lsof -ti:3001)" 2>/dev/null || true