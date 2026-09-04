"""
Self Grow — 后端配置
从 .env 加载配置，提供全局常量。
支持开发模式和数据目录独立模式（Docker/部署时通过 SELF_GROW_DATA_DIR 指定）。
"""

import os
import logging
import subprocess
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
# 数据目录：默认开发目录，可通过 SELF_GROW_DATA_DIR 覆盖
# ================================================================

def get_data_dir():
    """
    获取数据存储目录。
    - 默认：backend 源码目录（data.db、uploads、.env 都在 backend/ 下）
    - 覆盖：设置 SELF_GROW_DATA_DIR 后，数据存到独立目录（Docker/部署时用）
    """
    data_dir = os.getenv('SELF_GROW_DATA_DIR')
    if data_dir:
        os.makedirs(data_dir, exist_ok=True)
        return data_dir
    # 默认：使用 backend 源码目录
    return os.path.dirname(os.path.abspath(__file__))

DATA_DIR = get_data_dir()

# .env 加载：数据目录里的 .env 优先；无则回退到代码目录
env_path = os.path.join(DATA_DIR, '.env')
if not os.path.exists(env_path):
    # backend 目录存在 .env（开发模式）则用它；否则用数据目录
    code_env = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
    if os.path.exists(code_env):
        env_path = code_env
    elif os.getenv('SELF_GROW_DATA_DIR'):
        # 首次运行时创建 .env 模板（仅当指定了独立数据目录）
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

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

# AI 配置
AI_BASE_URL = os.getenv("AI_API_BASE_URL", "https://one.loll.xyz/v1")
AI_API_KEY = os.getenv("AI_API_KEY", "")
AI_MODEL = os.getenv("AI_MODEL", "gemini-2.5-pro-exp-03-25")

# ASR 配置（paraformer 实时语音识别）
DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY", "") or AI_API_KEY

if not AI_API_KEY:
    log.warning("⚠️ AI_API_KEY 未设置，AI 功能不可用")
elif not AI_API_KEY.isascii():
    log.warning("⚠️ AI_API_KEY 包含非 ASCII 字符，AI 功能不可用（请填入有效的 API Key）")
    AI_API_KEY = ""

# 系统版本号（跟随 git 记录）
def get_version() -> str:
    """从 git 获取版本号（git describe --tags --always），失败则返回默认值。

    - 有 tag 时返回 tag 名（如 v1.0.0）
    - tag 之后有提交时返回 v1.0.0-3-g0df2e08（tag-提交数-短commit）
    - 非 git 环境（如 Docker 无 .git）回退到默认 "1.1.0"
    """
    try:
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        out = subprocess.run(
            ["git", "describe", "--tags", "--always"],
            capture_output=True, text=True, timeout=3, cwd=repo_root,
        )
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except Exception:
        pass
    return "1.1.0"

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

# 前端目录（由环境变量指定，为空则不 serve 前端——开发模式下前端由独立 HTTP 服务器提供）
FRONTEND_DIR = os.getenv("SELF_GROW_FRONTEND_DIR", "")