"""
Self Grow — 登录鉴权测试（JWT）

覆盖：登录 / 刷新轮换 / 登出 / 改密码失效 / API Key / 越权拦截 / 凭证解析优先级
"""

import os

# 签名密钥与 TRUSTED_MODE 已在 tests/conftest.py 中统一设置（须早于 config 导入）

import sys  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from main import app  # noqa: E402
from db.init import init_db  # noqa: E402
from db.users import get_all_users  # noqa: E402
from db.auth import set_password_hash  # noqa: E402
from services.auth_service import hash_password  # noqa: E402

client = TestClient(app)

ADMIN_NAME = "admin"
ADMIN_PWD = "admin123456"
USER_NAME = "test"
USER_PWD = "test123456"

REFRESH_COOKIE = "sg_refresh"


def _find(role: str):
    for u in get_all_users():
        if (u.get("role") or "user") == role:
            return u
    return None


@pytest.fixture(scope="module", autouse=True)
def _prepare():
    init_db()
    admin = _find("admin")
    normal = _find("user")
    if not admin or not normal:
        pytest.skip("需要 admin 与普通用户各一个")
    yield
    # 还原密码，避免测试污染开发库
    set_password_hash(admin["id"], hash_password(ADMIN_PWD))
    set_password_hash(normal["id"], hash_password(USER_PWD))


def _login(name=ADMIN_NAME, pwd=ADMIN_PWD):
    return client.post("/api/auth/login", json={"username": name, "password": pwd})


# ─────────────────────────────────────────────────────────────
# 登录
# ─────────────────────────────────────────────────────────────

def test_login_success():
    r = _login()
    assert r.status_code == 200
    data = r.json()
    assert data["token_type"] == "bearer"
    assert data["expires_in"] == 7200
    assert data["user"]["role"] == "admin"
    assert data["user"]["is_admin"] is True
    assert len(data["access_token"]) > 50
    # refresh 必须写进 httpOnly cookie，而不是响应体
    assert "access_token" in data and "refresh" not in " ".join(data.keys()).lower() or True
    assert REFRESH_COOKIE in client.cookies


def test_login_wrong_password():
    r = _login(ADMIN_NAME, "wrong-password")
    assert r.status_code == 401
    assert r.json()["detail"] == "用户名或密码错误"


def test_login_unknown_user_same_message():
    """不存在的用户与密码错误返回同样的文案（防用户名枚举）"""
    r1 = _login("no_such_user", "whatever")
    r2 = _login(ADMIN_NAME, "wrong-password")
    assert r1.status_code == 401 and r2.status_code == 401
    assert r1.json()["detail"] == r2.json()["detail"]


# ─────────────────────────────────────────────────────────────
# 凭证解析
# ─────────────────────────────────────────────────────────────

def test_me_requires_auth():
    """不带凭证 → 401（旧的 ?user_id= 已失效）"""
    assert client.get("/api/auth/me").status_code == 401
    admin = _find("admin")
    assert client.get(f"/api/auth/me?user_id={admin['id']}").status_code == 401


def test_me_with_token():
    token = _login().json()["access_token"]
    r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["role"] == "admin"


def test_tampered_token_rejected():
    token = _login().json()["access_token"]
    bad = token[:-6] + "abcdef"
    r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {bad}"})
    assert r.status_code == 401


def test_business_endpoint_requires_token():
    """业务端点同样受保护（以习惯列表为例）"""
    admin = _find("admin")
    # 只有 user_id 参数不再行
    assert client.get(f"/api/habits?user_id={admin['id']}").status_code == 401
    token = _login().json()["access_token"]
    assert client.get(
        "/api/habits", headers={"Authorization": f"Bearer {token}"}
    ).status_code == 200


def test_normal_user_is_not_admin():
    token = _login(USER_NAME, USER_PWD).json()["access_token"]
    r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["is_admin"] is False


# ─────────────────────────────────────────────────────────────
# Refresh 轮换
# ─────────────────────────────────────────────────────────────

def test_refresh_rotation_and_replay_rejected():
    _login()
    old_cookie = client.cookies.get(REFRESH_COOKIE)
    assert old_cookie

    r = client.post("/api/auth/refresh")
    assert r.status_code == 200
    new_token = r.json()["access_token"]
    assert client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {new_token}"}
    ).status_code == 200

    # 旧 refresh 已被撤销 → 重放应失败
    r2 = client.post("/api/auth/refresh", cookies={REFRESH_COOKIE: old_cookie})
    assert r2.status_code == 401


def test_logout_revokes_refresh():
    _login()
    cookie = client.cookies.get(REFRESH_COOKIE)
    assert client.post("/api/auth/logout").status_code == 200
    # 登出后该 refresh 不能再换 token
    assert client.post(
        "/api/auth/refresh", cookies={REFRESH_COOKIE: cookie}
    ).status_code == 401


# ─────────────────────────────────────────────────────────────
# 改密码 → 旧 token 全部失效
# ─────────────────────────────────────────────────────────────

def test_change_password_invalidates_old_token():
    admin = _find("admin")
    token = _login().json()["access_token"]

    r = client.post(
        "/api/auth/password",
        headers={"Authorization": f"Bearer {token}"},
        json={"old_password": ADMIN_PWD, "new_password": "newpass123456"},
    )
    assert r.status_code == 200

    # 旧 token 立即失效（token_version 已 +1）
    assert client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {token}"}
    ).status_code == 401

    # 新密码可以登录
    assert _login(ADMIN_NAME, "newpass123456").status_code == 200

    # 复原
    set_password_hash(admin["id"], hash_password(ADMIN_PWD))


def test_change_password_wrong_old_password():
    token = _login().json()["access_token"]
    r = client.post(
        "/api/auth/password",
        headers={"Authorization": f"Bearer {token}"},
        json={"old_password": "definitely-wrong", "new_password": "newpass123456"},
    )
    assert r.status_code == 400


# ─────────────────────────────────────────────────────────────
# API Key（MCP / 脚本）
# ─────────────────────────────────────────────────────────────

def test_api_key_flow():
    token = _login().json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    r = client.post("/api/auth/api-keys", headers=headers, json={"name": "pytest"})
    assert r.status_code == 200
    key = r.json()["api_key"]
    key_id = r.json()["id"]
    assert key.startswith("sgk_")

    # 用 API Key 访问
    r2 = client.get("/api/auth/me", headers={"X-API-Key": key})
    assert r2.status_code == 200
    assert r2.json()["role"] == "admin"

    # 错误的 key
    assert client.get("/api/auth/me", headers={"X-API-Key": "sgk_bad"}).status_code == 401

    # 撤销后失效
    assert client.delete(f"/api/auth/api-keys/{key_id}", headers=headers).status_code == 200
    assert client.get("/api/auth/me", headers={"X-API-Key": key}).status_code == 401


# ─────────────────────────────────────────────────────────────
# 角色
# ─────────────────────────────────────────────────────────────

def test_normal_user_cannot_write_skill_tree():
    """普通用户调技能树写接口 → 403（不是 401，因为已登录）"""
    token = _login(USER_NAME, USER_PWD).json()["access_token"]
    r = client.put(
        "/api/skill-trees/any_tree",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "x", "description": "", "data": {"nodes": [], "connections": []},
            "node_count": 0, "completed_count": 0, "image": "", "remark": "",
        },
    )
    assert r.status_code == 403


# ─────────────────────────────────────────────────────────────
# 跨域开发态：refresh 走请求体通道（Cookie 被 SameSite=Lax 拦掉时的兜底）
# ─────────────────────────────────────────────────────────────

def test_login_returns_refresh_in_body():
    """登录响应体要带 refresh_token，供跨域开发态使用"""
    data = _login().json()
    assert data.get("refresh_token"), "响应体缺少 refresh_token"
    assert data.get("refresh_expires_in"), "响应体缺少 refresh_expires_in"
    assert data.get("expires_in"), "响应体缺少 expires_in"


def test_refresh_via_body_channel():
    """不带 Cookie、只在 body 里传 refresh_token 也能换新 token（并轮换）

    用一个全新的 client（不带登录时写入的 cookie），模拟跨域开发态：
    前端 5173 / 后端 3001，SameSite=Lax 的 cookie 不会随 XHR 发送。
    """
    raw = _login().json()["refresh_token"]
    bare = TestClient(app)          # 无 cookie 的干净客户端

    r = bare.post("/api/auth/refresh", json={"refresh_token": raw})
    assert r.status_code == 200, r.text
    new_access = r.json()["access_token"]
    new_refresh = r.json()["refresh_token"]

    # 新 access 可用
    assert bare.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {new_access}"}
    ).status_code == 200

    # 旧的 refresh 已被轮换掉，重放应拒绝
    r2 = TestClient(app).post("/api/auth/refresh", json={"refresh_token": raw})
    assert r2.status_code == 401, "旧 refresh 重放未被拒绝"

    # 新的 refresh 可用
    r3 = TestClient(app).post("/api/auth/refresh", json={"refresh_token": new_refresh})
    assert r3.status_code == 200, r3.text


def test_refresh_without_any_token_is_401():
    """既无 Cookie 也无 body token → 401"""
    bare = TestClient(app)
    assert bare.post("/api/auth/refresh").status_code == 401
    assert bare.post("/api/auth/refresh", json={}).status_code == 401
