"""
Self Grow — 登录鉴权数据访问层

只负责 SQL，业务逻辑（哈希 / 签发 / 校验）在 services/auth_service.py。
"""

from datetime import datetime

from db.connection import get_conn


# ─────────────────────────────────────────────────────────────
# users 相关
# ─────────────────────────────────────────────────────────────

def get_user_auth(user_id: int):
    """取鉴权需要的用户字段"""
    conn = get_conn()
    row = conn.execute(
        "SELECT id, name, role, password_hash, token_version FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_user_auth_by_name(name: str):
    """按用户名取鉴权字段（登录用）"""
    conn = get_conn()
    row = conn.execute(
        "SELECT id, name, role, password_hash, token_version FROM users WHERE name = ?",
        (name,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def set_password_hash(user_id: int, password_hash: str):
    conn = get_conn()
    conn.execute(
        "UPDATE users SET password_hash = ? WHERE id = ?",
        (password_hash, user_id),
    )
    conn.commit()
    conn.close()


def update_last_login(user_id: int):
    conn = get_conn()
    conn.execute(
        "UPDATE users SET last_login = ? WHERE id = ?",
        (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), user_id),
    )
    conn.commit()
    conn.close()


def bump_token_version(user_id: int) -> int:
    """token_version +1（改密码 / 强制下线时使用），返回新值"""
    conn = get_conn()
    conn.execute(
        "UPDATE users SET token_version = COALESCE(token_version, 1) + 1 WHERE id = ?",
        (user_id,),
    )
    row = conn.execute(
        "SELECT token_version FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    conn.commit()
    conn.close()
    return row["token_version"] if row else 1


# ─────────────────────────────────────────────────────────────
# refresh_tokens
# ─────────────────────────────────────────────────────────────

def create_refresh_token(user_id: int, token_hash: str, user_agent: str, expires_at: str) -> int:
    conn = get_conn()
    cur = conn.execute(
        """INSERT INTO refresh_tokens (user_id, token_hash, user_agent, expires_at)
           VALUES (?, ?, ?, ?)""",
        (user_id, token_hash, user_agent or "", expires_at),
    )
    token_id = cur.lastrowid
    conn.commit()
    conn.close()
    return token_id


def find_valid_refresh(token_hash: str):
    """按哈希找一条未过期、未撤销的 refresh token"""
    conn = get_conn()
    row = conn.execute(
        """SELECT id, user_id, expires_at FROM refresh_tokens
           WHERE token_hash = ? AND revoked = 0""",
        (token_hash,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def revoke_refresh(token_id: int):
    conn = get_conn()
    conn.execute("UPDATE refresh_tokens SET revoked = 1 WHERE id = ?", (token_id,))
    conn.commit()
    conn.close()


def revoke_all_refresh(user_id: int):
    conn = get_conn()
    conn.execute(
        "UPDATE refresh_tokens SET revoked = 1 WHERE user_id = ?", (user_id,)
    )
    conn.commit()
    conn.close()


# ─────────────────────────────────────────────────────────────
# api_keys（MCP / 脚本用）
# ─────────────────────────────────────────────────────────────

def create_api_key(user_id: int, name: str, key_hash: str) -> int:
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO api_keys (user_id, name, key_hash) VALUES (?, ?, ?)",
        (user_id, name, key_hash),
    )
    key_id = cur.lastrowid
    conn.commit()
    conn.close()
    return key_id


def find_api_key(key_hash: str):
    conn = get_conn()
    row = conn.execute(
        "SELECT id, user_id FROM api_keys WHERE key_hash = ? AND revoked = 0",
        (key_hash,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def touch_api_key(key_id: int):
    conn = get_conn()
    conn.execute(
        "UPDATE api_keys SET last_used_at = ? WHERE id = ?",
        (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), key_id),
    )
    conn.commit()
    conn.close()


def list_api_keys(user_id: int):
    conn = get_conn()
    rows = conn.execute(
        """SELECT id, name, last_used_at, created_at, revoked
           FROM api_keys WHERE user_id = ? ORDER BY id DESC""",
        (user_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def revoke_api_key(key_id: int, user_id: int):
    conn = get_conn()
    conn.execute(
        "UPDATE api_keys SET revoked = 1 WHERE id = ? AND user_id = ?",
        (key_id, user_id),
    )
    conn.commit()
    conn.close()
