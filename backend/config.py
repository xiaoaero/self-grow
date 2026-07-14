"""
Self Grow — 后端配置
从 .env 加载配置，提供全局常量。
支持开发模式和 PyInstaller 打包模式。
"""

import os
import logging
import sys
from dotenv import load_dotenv

# 设置 UTF-8 编码（解决 Windows 上 httpx 等库的中文编码问题）
if hasattr(sys, 'stdout') and sys.stdout:
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except (AttributeError, ValueError):
        pass
if hasattr(sys, 'stderr') and sys.stderr:
    try:
        sys.stderr.reconfigure(encoding='utf-8')
    except (AttributeError, ValueError):
        pass
os.environ.setdefault("LANG", "en_US.UTF-8")
os.environ.setdefault("LC_ALL", "en_US.UTF-8")

# ================================================================
# 数据目录：开发模式 vs PyInstaller 打包模式
# ================================================================

def get_data_dir():
    """
    获取数据存储目录。
    - 开发模式：backend 源码目录（data.db、uploads、.env 都在 backend/ 下）
    - 打包模式：%APPDATA%/SelfGrow/（用户数据独立于安装目录）
    """
    if os.getenv('SELF_GROW_PACKAGED') == '1':
        # PyInstaller 打包模式：用户数据目录
        data_dir = os.getenv('SELF_GROW_DATA_DIR')
        if data_dir:
            os.makedirs(data_dir, exist_ok=True)
            return data_dir
        # 降级：使用 APPDATA
        appdata = os.getenv('APPDATA', os.path.expanduser('~'))
        data_dir = os.path.join(appdata, 'SelfGrow')
        os.makedirs(data_dir, exist_ok=True)
        return data_dir
    else:
        # 开发模式：使用 backend 源码目录
        return os.path.dirname(os.path.abspath(__file__))

DATA_DIR = get_data_dir()

# .env 加载：打包模式从数据目录加载，开发模式从代码目录加载
if os.getenv('SELF_GROW_PACKAGED') == '1':
    env_path = os.path.join(DATA_DIR, '.env')
    # 首次运行时创建 .env 模板
    if not os.path.exists(env_path):
        template = (
            "# Self Grow AI 配置\n"
            "AI_API_BASE_URL=https://api.sfkey.cn/v1\n"
            "AI_API_KEY=\n"
            "AI_MODEL=glm-5.2\n"
            "\n"
            "# 服务端口\n"
            "PORT=3001\n"
        )
        with open(env_path, 'w', encoding='utf-8') as f:
            f.write(template)
    load_dotenv(env_path)
else:
    load_dotenv()

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

# AI 配置
AI_BASE_URL = os.getenv("AI_API_BASE_URL", "https://one.loll.xyz/v1")
AI_API_KEY = os.getenv("AI_API_KEY", "")
AI_MODEL = os.getenv("AI_MODEL", "gemini-2.5-pro-exp-03-25")

if not AI_API_KEY:
    log.warning("⚠️ AI_API_KEY 未设置，AI 功能不可用")
elif not AI_API_KEY.isascii():
    log.warning("⚠️ AI_API_KEY 包含非 ASCII 字符，AI 功能不可用（请填入有效的 API Key）")
    AI_API_KEY = ""

# 服务端口
try:
    PORT = int(os.getenv("PORT", "3001"))
except (ValueError, TypeError):
    log.warning("⚠️ PORT 环境变量格式错误，使用默认端口 3001")
    PORT = 3001

# 数据库路径
DB_PATH = os.path.join(DATA_DIR, "data.db")

# 上传目录
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")

# 前端目录（打包模式由环境变量指定，开发模式为 None 不 serve 前端）
FRONTEND_DIR = os.getenv("SELF_GROW_FRONTEND_DIR", "")