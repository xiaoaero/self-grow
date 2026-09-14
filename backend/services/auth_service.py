"""
Self Grow — 登录鉴权服务

职责：
- 密码哈希与校验（passlib + bcrypt）
- Access Token 签发 / 验签（PyJWT，HS256）
- Refresh Token 生成、轮换、撤销（数据库存哈希）
- API Key 生成与校验（MCP / 脚本用）
- 登录失败锁定（内存计数器）

设计要点：
- Access 载荷带 `role` 与 `ver`（token_version），角色随凭证走，后端校验角色零查询
- Refresh 只存哈希，且"用掉即换新的"（Rotation），重放可检测
- 改密码 / 强制下线 → token_version +1 → 所有旧 Access 立即失效
   （补上"JWT 无法主动失效"的短板）
"""

import base64
import hashlib
import logging
import secrets
import uuid
from datetime import datetime, timedelta

import jwt
import bcrypt

from config import (
    SELF_GROW_JWT_SECRET,
    SELF_GROW_JWT_OLD_SECRET,
    SELF_GROW_ACCESS_TTL,
    SELF_GROW_REFRESH_TTL,
    SELF_GROW_TRUSTED_MODE,
)
from db import auth as auth_db
from db.users import get_user

log = logging.getLogger(__name__)

ALGORITHM = "HS256"

# bcrypt 只取密码前 72 字节，超长密码先做一次 SHA-256 摘要（避免报错/静默截断）
BCRYPT_MAX_BYTES = 72
# 哈希强度（cost factor 12 ≈ 每次校验 250ms 量级，兼顾安全与体验）
BCRYPT_ROUNDS = 12

# 登录失败锁定（进程内计数，够用；多实例部署应换成共享存储）
_failed_attempts: dict[str, tuple[int, float]] = {}   # username -> (次数, 首次时间)
MAX_FAILURES = 5
LOCK_SECONDS = 600


# ─────────────────────────────────────────────────────────────
# 启动配置校验
# ─────────────────────────────────────────────────────────────

def ensure_jwt_secret() -> str:
    """返回可用的签名密钥。

    - 配了 SELF_GROW_JWT_SECRET → 直接用
    - 没配但开了 TRUSTED_MODE → 生成临时密钥并告警（本地开发 / 演示）
    - 都没 → 抛错拒绝启动（绝不静默使用默认密钥）
    """
    if SELF_GROW_JWT_SECRET:
        return SELF_GROW_JWT_SECRET

    if SELF_GROW_TRUSTED_MODE:
        log.warning(
            "⚠️ SELF_GROW_JWT_SECRET 未配置，且已开启 TRUSTED_MODE —— "
            "使用随机临时密钥，服务重启后所有 token 失效（仅供本地开发）"
        )
        return "dev-insecure-" + secrets.token_hex(16)

    raise RuntimeError(
        "SELF_GROW_JWT_SECRET 未配置，拒绝启动。"
        "请用 openssl rand -hex 32 生成并写入 backend/.env，"
        "或设置 SELF_GROW_TRUSTED_MODE=1 以本地免鉴权模式运行。"
    )


# ─────────────────────────────────────────────────────────────
# 密码
# ─────────────────────────────────────────────────────────────

def _prehash_if_long(password: str) -> str:
    """bcrypt 只取前 72 字节，超长时先 SHA-256（base64）"""
    if len(password.encode("utf-8")) > BCRYPT_MAX_BYTES:
        digest = hashlib.sha256(password.encode("utf-8")).digest()
        return base64.b64encode(digest).decode("ascii")
    return password


def hash_password(password: str) -> str:
    """生成 bcrypt 哈希（自带随机盐，无需单独存盐）"""
    data = _prehash_if_long(password).encode("utf-8")
    return bcrypt.hashpw(data, bcrypt.gensalt(rounds=BCRYPT_ROUNDS)).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    if not password_hash:
        return False
    try:
        data = _prehash_if_long(password).encode("utf-8")
        return bcrypt.checkpw(data, password_hash.encode("ascii"))
    except Exception:
        return False


# ─────────────────────────────────────────────────────────────
# Access Token
# ─────────────────────────────────────────────────────────────

def _now() -> datetime:
    return datetime.now()


def create_access_token(user: dict) -> tuple[str, int]:
    """签发 Access Token，返回 (token, 有效期秒数)

    载荷：
      sub  用户 ID
      role 角色（admin / user）—— 后端校验角色时零查询
      ver  token_version —— 改密码后旧 token 全部失效
      typ  固定 access（防止 refresh 当 access 用）
    """
    secret = ensure_jwt_secret()
    now = _now()
    payload = {
        "sub": str(user["id"]),
        "role": user.get("role") or "user",
        "ver": int(user.get("token_version") or 1),
        "typ": "access",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=SELF_GROW_ACCESS_TTL)).timestamp()),
    }
    token = jwt.encode(payload, secret, algorithm=ALGORITHM)
    return token, SELF_GROW_ACCESS_TTL


def decode_access_token(token: str) -> dict | None:
    """验签 Access Token，失败返回 None

    先试当前密钥，再试旧密钥（支持密钥平滑轮换）。
    """
    if not token:
        return None
    for secret in filter(None, [SELF_GROW_JWT_SECRET, SELF_GROW_JWT_OLD_SECRET]):
        try:
            payload = jwt.decode(token, secret, algorithms=[ALGORITHM])
            if payload.get("typ") != "access":
                return None
            return payload
        except jwt.ExpiredSignatureError:
            return None
        except jwt.PyJWTError:
            continue
    return None


def resolve_token_user(payload: dict):
    """由 token 载荷解析出用户，并校验 token_version

    payload 验签通过后必须再查一次库：
    - 用户可能已被删除
    - token_version 可能已被改密码刷新
    """
    try:
        user_id = int(payload.get("sub"))
    except (TypeError, ValueError):
        return None

    auth_row = auth_db.get_user_auth(user_id)
    if not auth_row:
        return None
    if int(auth_row.get("token_version") or 1) != int(payload.get("ver") or 1):
        return None     # 已改密码 / 已强制下线

    user = get_user(user_id)
    return user


# ─────────────────────────────────────────────────────────────
# Refresh Token
# ─────────────────────────────────────────────────────────────

def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def create_refresh_token(user_id: int, user_agent: str = "") -> tuple[str, int]:
    """生成 Refresh Token，返回 (明文 token, 有效期秒数)。数据库中只存哈希。"""
    raw = secrets.token_urlsafe(48)
    expires_at = (_now() + timedelta(seconds=SELF_GROW_REFRESH_TTL)).strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    auth_db.create_refresh_token(user_id, _hash_token(raw), user_agent, expires_at)
    return raw, SELF_GROW_REFRESH_TTL


def consume_refresh_token(raw: str):
    """校验并"用掉"一个 Refresh Token（Rotation）

    成功返回 user dict，并把旧 token 作废（调用方随后签发新的）。
    失败（不存在 / 已撤销 / 已过期）返回 None。
    """
    if not raw:
        return None
    row = auth_db.find_valid_refresh(_hash_token(raw))
    if not row:
        return None

    # 过期检查（字符串比较，格式 YYYY-MM-DD HH:MM:SS）
    if row.get("expires_at", "") < _now().strftime("%Y-%m-%d %H:%M:%S"):
        auth_db.revoke_refresh(row["id"])
        return None

    # Rotation：旧的立即作废
    auth_db.revoke_refresh(row["id"])
    return get_user(row["user_id"])


def revoke_refresh_token(raw: str):
    """登出：撤销当前 refresh"""
    if not raw:
        return
    row = auth_db.find_valid_refresh(_hash_token(raw))
    if row:
        auth_db.revoke_refresh(row["id"])


def revoke_all_refresh(user_id: int):
    auth_db.revoke_all_refresh(user_id)


# ─────────────────────────────────────────────────────────────
# API Key（MCP / 脚本）
# ─────────────────────────────────────────────────────────────

def create_api_key(user_id: int, name: str = "default") -> tuple[str, int]:
    """生成 API Key，返回 (明文 key, 记录 id)。明文只在创建时返回一次。"""
    raw = "sgk_" + uuid.uuid4().hex + secrets.token_hex(8)
    key_id = auth_db.create_api_key(user_id, name, _hash_token(raw))
    return raw, key_id


def resolve_api_key(raw: str):
    """校验 API Key，成功返回 user dict"""
    if not raw or not raw.startswith("sgk_"):
        return None
    row = auth_db.find_api_key(_hash_token(raw))
    if not row:
        return None
    auth_db.touch_api_key(row["id"])
    return get_user(row["user_id"])


# ─────────────────────────────────────────────────────────────
# 登录
# ─────────────────────────────────────────────────────────────

def is_locked(username: str) -> bool:
    """登录失败是否处于锁定状态"""
    item = _failed_attempts.get(username)
    if not item:
        return False
    count, first_ts = item
    if count < MAX_FAILURES:
        return False
    if _now().timestamp() - first_ts > LOCK_SECONDS:
        del _failed_attempts[username]      # 锁定已过期
        return False
    return True


def record_login_failure(username: str):
    count, first_ts = _failed_attempts.get(username, (0, _now().timestamp()))
    _failed_attempts[username] = (count + 1, first_ts)


def clear_login_failures(username: str):
    _failed_attempts.pop(username, None)


def authenticate(username: str, password: str):
    """校验用户名 + 密码，成功返回用户，失败返回 None

    注意：不区分"用户不存在"与"密码错误"，统一返回 None，
    避免通过错误提示枚举出哪些用户名存在。
    """
    if not username or not password:
        return None
    if is_locked(username):
        return None

    row = auth_db.get_user_auth_by_name(username.strip())
    if not row or not row.get("password_hash"):
        record_login_failure(username)      # 未设置密码的账号一律拒绝
        return None

    if not verify_password(password, row["password_hash"]):
        record_login_failure(username)
        return None

    clear_login_failures(username)
    auth_db.update_last_login(row["id"])
    return get_user(row["id"])
