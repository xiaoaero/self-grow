"""
Self Grow — 后端配置
从 .env 加载配置，提供全局常量。
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
DB_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(DB_DIR, "data.db")

# 上传目录
UPLOAD_DIR = os.path.join(DB_DIR, "uploads")