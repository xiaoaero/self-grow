"""
Self Grow — 测试辅助

提供登录取 token 的公共方法（JWT 改造后所有业务端点都需要凭证）。
"""

from fastapi.testclient import TestClient

# 测试用的固定密码（由 ensure_test_accounts 保证落库）
TEST_PASSWORDS = {"admin": "admin123456", "user": "test123456"}

_accounts_ready = False


def ensure_test_accounts():
    """保证 admin / 普通用户都有已知密码

    使登录类测试不依赖开发者本机的数据库状态（幂等，只执行一次）。
    """
    global _accounts_ready
    if _accounts_ready:
        return

    from db.init import init_db
    from db.users import get_all_users
    from db.auth import set_password_hash
    from services.auth_service import hash_password

    init_db()
    for u in get_all_users():
        role = u.get("role") or "user"
        pwd = TEST_PASSWORDS.get(role, TEST_PASSWORDS["user"])
        set_password_hash(u["id"], hash_password(pwd))
    _accounts_ready = True


def get_auth_headers(role: str = "admin") -> dict:
    """登录并返回带 Bearer token 的请求头

    Args:
        role: "admin" → 管理员账号；其他 → 普通用户（test）
    """
    ensure_test_accounts()
    from main import app

    client = TestClient(app)
    is_admin = role == "admin"
    username = "admin" if is_admin else "test"
    password = TEST_PASSWORDS["admin"] if is_admin else TEST_PASSWORDS["user"]

    resp = client.post("/api/auth/login", json={"username": username, "password": password})
    if resp.status_code != 200:
        raise RuntimeError(
            f"测试登录失败（{username}）：{resp.status_code} {resp.text}"
        )
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}
