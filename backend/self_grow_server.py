"""
Self Grow — PyInstaller 打包入口

当作为 PyInstaller bundle 运行时，此脚本：
1. 解析用户数据目录 (%APPDATA%/SelfGrow/)
2. 设置 SELF_GROW_PACKAGED=1 等环境变量，让 config.py 使用正确的路径
3. 启动 FastAPI 应用
"""
import os
import sys


def get_user_data_dir():
    """获取用户数据目录"""
    if sys.platform == 'win32':
        base = os.environ.get('APPDATA', os.path.expanduser('~'))
    elif sys.platform == 'darwin':
        base = os.path.expanduser('~/Library/Application Support')
    else:
        base = os.path.expanduser('~/.local/share')
    data_dir = os.path.join(base, 'SelfGrow')
    os.makedirs(data_dir, exist_ok=True)
    return data_dir


def main():
    data_dir = get_user_data_dir()

    # 设置环境变量，让 config.py 在导入时识别打包模式
    os.environ['SELF_GROW_PACKAGED'] = '1'
    os.environ['SELF_GROW_DATA_DIR'] = data_dir
    os.environ['SELF_GROW_DB_PATH'] = os.path.join(data_dir, 'data.db')
    os.environ['SELF_GROW_UPLOAD_DIR'] = os.path.join(data_dir, 'uploads')

    # 确保上传目录存在
    os.makedirs(os.environ['SELF_GROW_UPLOAD_DIR'], exist_ok=True)

    # 解析端口（支持 --port 命令行参数）
    port = 3001
    for i, arg in enumerate(sys.argv):
        if arg == '--port' and i + 1 < len(sys.argv):
            try:
                port = int(sys.argv[i + 1])
            except ValueError:
                pass
    os.environ['PORT'] = str(port)

    # 解析前端目录（支持 --frontend-dir 命令行参数）
    for i, arg in enumerate(sys.argv):
        if arg == '--frontend-dir' and i + 1 < len(sys.argv):
            os.environ['SELF_GROW_FRONTEND_DIR'] = sys.argv[i + 1]

    # 导入并启动应用（必须在设置环境变量之后）
    from main import app
    import uvicorn

    print(f"🌱 Self Grow 后端启动中...")
    print(f"   数据目录: {data_dir}")
    print(f"   端口: {port}")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")


if __name__ == '__main__':
    main()
