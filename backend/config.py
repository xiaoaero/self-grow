"""
Self Grow — 后端配置
从 .env 加载配置，提供全局常量。
"""

import os
import logging
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

# AI 配置
AI_BASE_URL = os.getenv("AI_API_BASE_URL", "https://one.loll.xyz/v1")
AI_API_KEY = os.getenv("AI_API_KEY", "")
AI_MODEL = os.getenv("AI_MODEL", "gemini-2.5-pro-exp-03-25")

if not AI_API_KEY:
    log.warning("⚠️ AI_API_KEY 未设置，AI 功能不可用")

# 服务端口
PORT = int(os.getenv("PORT", "3001"))

# 数据库路径
DB_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(DB_DIR, "data.db")

# 上传目录
UPLOAD_DIR = os.path.join(DB_DIR, "uploads")