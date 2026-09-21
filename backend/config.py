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
            "\n"
            "# 登录鉴权（JWT 签名密钥，务必改成随机值：openssl rand -hex 32）\n"
            "SELF_GROW_JWT_SECRET=\n"
            "\n"
            "# 本地免鉴权模式（1 = 跳过登录，仅供开发/演示，生产务必留空）\n"
            "SELF_GROW_TRUSTED_MODE=\n"
        )
        with open(env_path, 'w', encoding='utf-8') as f:
            f.write(template)
load_dotenv(env_path)

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

# AI 配置
AI_BASE_URL = os.getenv("AI_API_BASE_URL", "")
AI_API_KEY = os.getenv("AI_API_KEY", "")
AI_MODEL = os.getenv("AI_MODEL", "")

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

    - 有 tag 时返回 tag 名（如 v1.2）
    - tag 之后有提交时返回 v1.2-3-g0df2e08（tag-提交数-短commit）
    - 非 git 环境（如 Docker 无 .git）回退到默认 "1.2"
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
    return "1.2"

# 服务端口
try:
    PORT = int(os.getenv("PORT", "3001"))
except (ValueError, TypeError):
    log.warning("⚠️ PORT 环境变量格式错误，使用默认端口 3001")
    PORT = 3001

# 数据库路径（sqlite 后端用；mysql 后端不看这个）
DB_PATH = os.path.join(DATA_DIR, "data.db")

# ================================================================
# 数据库后端选择（2026-09-19 加入）
# ================================================================
#   SELF_GROW_DB_BACKEND=sqlite  → 走原来的 data.db（默认，行为完全不变）
#   SELF_GROW_DB_BACKEND=mysql   → 走 MySQL
#
# 保留两条通路是**有意为之**：迁移期任何一步出问题，把这个变量改回 sqlite
# 就能整体回退。详见 docs/SQLite迁移MySQL方案.md 第九节。
DB_BACKEND = os.getenv("SELF_GROW_DB_BACKEND", "sqlite").strip().lower()

MYSQL_HOST = os.getenv("SELF_GROW_MYSQL_HOST", "127.0.0.1")
MYSQL_PORT = int(os.getenv("SELF_GROW_MYSQL_PORT", "3306") or 3306)
MYSQL_USER = os.getenv("SELF_GROW_MYSQL_USER", "self_grow")
MYSQL_PASSWORD = os.getenv("SELF_GROW_MYSQL_PASSWORD", "")
MYSQL_DATABASE = os.getenv("SELF_GROW_MYSQL_DATABASE", "self_grow")

# 连接池上限。⚠️ 必须 ≥ 并发线程数：协调 Agent 会用 asyncio.gather 并行跑多个
# 子 Agent，每个工具调用都 asyncio.to_thread + get_conn()。
#
# **池太小会死锁，而且没有超时**：DBUtils 的 blocking=True 在池满时无限等待，
# 而等待者本身可能正持有连接（嵌套调用），于是谁也拿不到连接。
# 实测踩过：池设 12 时，跑 tests/test_sleep_action.py（每个用例都要
# DROP+CREATE 22 张表）会**卡死**；提到 40 立刻通过。
# 生产侧的并发没测试那么夸张，取 20 留足余量。
MYSQL_POOL_SIZE = int(os.getenv("SELF_GROW_MYSQL_POOL_SIZE", "20") or 20)

# 会话时区。MySQL 容器默认跑 UTC，而本项目全项目统一「本地时间」——
# 不设这个，NOW() / CURRENT_TIMESTAMP 会比本地时间早 8 小时，重演当年
# 「刚记录完却显示 8 小时前」的坑（见 docs/时间口径统一方案.md）。
# 在连接层设而不是改容器，好处是与容器/服务器时区**解耦**。
MYSQL_TIME_ZONE = os.getenv("SELF_GROW_MYSQL_TIME_ZONE", "+08:00")

# 上传目录
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")

# 前端目录（由环境变量指定，为空则不 serve 前端——开发模式下前端由独立 HTTP 服务器提供）
FRONTEND_DIR = os.getenv("SELF_GROW_FRONTEND_DIR", "")

# CORS 允许的来源：
# - 未配置 → 同源 + 常见前端开发端口（携带凭证必须显式列来源，不能用 "*"）
# - 配置 "*" → 完全放开，此时关闭凭证支持（仅供无鉴权的本地调试）
_raw_cors = [o.strip() for o in (os.getenv("SELF_GROW_CORS_ORIGINS", "") or "").split(",") if o.strip()]
if _raw_cors == ["*"]:
    CORS_ORIGINS = ["*"]
    CORS_ALLOW_CREDENTIALS = False
elif _raw_cors:
    CORS_ORIGINS = _raw_cors
    CORS_ALLOW_CREDENTIALS = True
else:
    CORS_ORIGINS = [
        f"http://localhost:{PORT}",
        f"http://127.0.0.1:{PORT}",
        "http://localhost:5173", "http://127.0.0.1:5173",   # Vite
        "http://localhost:5500", "http://127.0.0.1:5500",   # VS Code Live Server
        "http://localhost:8080", "http://127.0.0.1:8080",
        "http://localhost:8000", "http://127.0.0.1:8000",   # python -m http.server
        "http://localhost:3000", "http://127.0.0.1:3000",   # npx http-server 常用端口
    ]
    CORS_ALLOW_CREDENTIALS = True

# 本机来源一律放行（开发态前端端口不固定，逐个列永远列不全：
# http-server / Vite / Live Server / 自写脚本端口千变万化）。
# 只匹配 localhost 与 127.0.0.1，不含局域网 IP —— 公网环境请用
# SELF_GROW_CORS_ORIGINS 显式指定。
CORS_ALLOW_ORIGIN_REGEX = r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$"

# ─────────────────────────────────────────────────────────────
# 登录鉴权（JWT）
# ─────────────────────────────────────────────────────────────

# JWT 签名密钥。生产环境必须设置（用 openssl rand -hex 32 生成）。
# 未设置时按 TRUSTED_MODE 处理：本地模式自动生成临时密钥并告警，
# 否则由 auth_service 在启动时抛错，避免"默认密钥"这种致命配置。
SELF_GROW_JWT_SECRET = os.getenv("SELF_GROW_JWT_SECRET", "")

# 密钥轮换用：填写旧密钥后，旧 token 仍可验签一段时间
SELF_GROW_JWT_OLD_SECRET = os.getenv("SELF_GROW_JWT_OLD_SECRET", "")

# Access Token 有效期（秒，默认 2 小时）
try:
    SELF_GROW_ACCESS_TTL = int(os.getenv("SELF_GROW_ACCESS_TTL", "7200"))
except (ValueError, TypeError):
    SELF_GROW_ACCESS_TTL = 7200

# Refresh Token 有效期（秒，默认 30 天）
try:
    SELF_GROW_REFRESH_TTL = int(os.getenv("SELF_GROW_REFRESH_TTL", "2592000"))
except (ValueError, TypeError):
    SELF_GROW_REFRESH_TTL = 2592000

# 可信模式：跳过鉴权，固定为指定用户（本地开发 / 演示用）。
# 开启后所有请求都以 SELF_GROW_TRUSTED_USER_ID 身份执行 —— 绝不用于生产。
SELF_GROW_TRUSTED_MODE = os.getenv("SELF_GROW_TRUSTED_MODE", "0") == "1"

try:
    SELF_GROW_TRUSTED_USER_ID = int(os.getenv("SELF_GROW_TRUSTED_USER_ID", "1"))
except (ValueError, TypeError):
    SELF_GROW_TRUSTED_USER_ID = 1