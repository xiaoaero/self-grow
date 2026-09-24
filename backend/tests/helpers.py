"""
Self Grow — 测试辅助

提供登录取 token 的公共方法（JWT 改造后所有业务端点都需要凭证）。
"""

from fastapi.testclient import TestClient

# 测试用的固定密码（由 ensure_test_accounts 保证落库）
TEST_PASSWORDS = {"admin": "admin123456", "user": "test123456"}

# 上次设过密码时的「库指纹」—— 见 ensure_test_accounts 的说明
_accounts_signature = None


def ensure_test_accounts():
    """保证 admin / 普通用户都有已知密码（幂等）

    ⚠️⚠️ 这里**不能**用「只执行一次」的模块级布尔缓存（原来是 `_accounts_ready`）。
    原因：`db/testing.py::reset_test_database()` 会清空测试库所有表再重建 ——
    密码随之消失，而布尔缓存还以为"已经设过了"，
    于是**后面所有测试都会在 `get_auth_headers()` 这一步登录失败**。

    实测：`test_sleep_action`（它带 reset）之后跑的 `test_streaming` 11 个用例全挂，
    报的都是"登录拿不到 token"，而不是被测逻辑的问题。

    ⇒ 改用**库指纹**判断：只要「用户集合」或「密码列有无」发生变化就重设。
    正常情况下签名不变 → 直接返回（不用每次都跑 bcrypt，那会很慢）。
    """
    global _accounts_signature

    from db.init import init_db
    from db.users import get_all_users
    from db.auth import set_password_hash
    from services.auth_service import hash_password

    init_db()
    users = get_all_users()
    # 指纹只取用户 id 集合。
    # ⚠️ **不要**用 `u.get("password_hash")` 参与指纹 —— `get_all_users()` 不返回该列，
    #    取到的永远是 None，指纹就变成了常量，之后无论库被重置多少次都会跳过设置，
    #    表现为"后面所有测试登录 401"（实测踩过）。
    #    库被重置时由 `invalidate_test_accounts()` 主动把指纹清掉。
    signature = tuple(sorted(u["id"] for u in users))
    if signature == _accounts_signature:
        return

    for u in users:
        role = u.get("role") or "user"
        pwd = TEST_PASSWORDS.get(role, TEST_PASSWORDS["user"])
        set_password_hash(u["id"], hash_password(pwd))
    _accounts_signature = signature


def invalidate_test_accounts() -> None:
    """让下次 `ensure_test_accounts()` 重新设置密码

    `db/testing.py::reset_test_database()` 清库重建后会调用它 ——
    密码随库一起没了，而缓存还以为"设过了"。
    """
    global _accounts_signature
    _accounts_signature = None


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
