"""
MCP Server HTTP 传输的 API Key 鉴权测试（2026-09-13）

背景：
- stdio 模式 = 本地 spawn 的子进程，进程边界即信任边界，不做鉴权（业界通行做法）
- HTTP  模式 = 监听端口，任何能访问该端口的人都能调 24 个业务工具读写数据库
              → 必须校验 X-API-Key，且身份由 Key 决定（不再固定为 user 1）

测试重点：
1. 无 Key / 错 Key → 401
2. 合法 Key → 放行
3. 撤销后的 Key → 401（可撤销性是关键）
4. 身份注入：Key 属于谁，MCP 工具就操作谁的数据
"""


import pytest
from fastapi.testclient import TestClient

from main import app as rest_app
from helpers import ensure_test_accounts

from services import auth_service


pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


@pytest.fixture(scope="module")
def mcp_app():
    """构造带鉴权的 MCP HTTP ASGI 应用"""
    import mcp_server as M
    return M.build_http_app("streamable-http")


@pytest.fixture(scope="module")
def admin_api_key():
    """为 admin 生成一个 API Key"""
    ensure_test_accounts()
    client = TestClient(rest_app)
    r = client.post(
        "/api/auth/login", json={"username": "admin", "password": "admin123456"}
    )
    assert r.status_code == 200, r.text
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

    r = client.post("/api/auth/api-keys", json={"name": "pytest-mcp"}, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()["api_key"]


# ─────────────────────────────────────────────────────────────
# 鉴权拦截
# ─────────────────────────────────────────────────────────────

def test_mcp_http_requires_api_key(mcp_app):
    """不带 Key 访问 MCP 端点 → 401"""
    c = TestClient(mcp_app)
    r = c.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "ping"})
    assert r.status_code == 401, f"期望 401，实际 {r.status_code} {r.text}"
    assert r.headers.get("WWW-Authenticate") == "Bearer"


def test_mcp_http_rejects_bad_key(mcp_app):
    """错误 / 伪造的 Key → 401"""
    c = TestClient(mcp_app)
    for bad in ["sgk_notexist", "abc", "Bearer xxx"]:
        r = c.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "ping"},
            headers={"X-API-Key": bad},
        )
        assert r.status_code == 401, f"{bad} 未被拒绝"


def test_mcp_http_accepts_valid_key(mcp_app, admin_api_key):
    """合法 Key → 通过鉴权（不再是 401；MCP 协议层可能返回别的码）"""
    # 用 with 触发 lifespan：MCP 的 session manager 需要 startup 才初始化
    with TestClient(mcp_app) as c:
        r = c.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "ping"},
            headers={"X-API-Key": admin_api_key},
        )
    assert r.status_code != 401, "合法 Key 被误拦"


def test_mcp_http_accepts_bearer_style(mcp_app, admin_api_key):
    """也支持 Authorization: Bearer sgk_... 形式"""
    with TestClient(mcp_app) as c:
        r = c.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "ping"},
            headers={"Authorization": f"Bearer {admin_api_key}"},
        )
    assert r.status_code != 401, "Bearer 形式被误拦"


def test_mcp_http_revoked_key_rejected(mcp_app):
    """撤销后的 Key 立即失效（可撤销性是选 API Key 而非静态口令的核心理由）"""
    ensure_test_accounts()
    rest = TestClient(rest_app)
    r = rest.post("/api/auth/login", json={"username": "admin", "password": "admin123456"})
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

    key = rest.post(
        "/api/auth/api-keys", json={"name": "pytest-revoke"}, headers=headers
    ).json()["api_key"]

    with TestClient(mcp_app) as c:
        assert c.post(
            "/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "ping"},
            headers={"X-API-Key": key},
        ).status_code != 401

    # 撤销
    keys = rest.get("/api/auth/api-keys", headers=headers).json()["keys"]
    target = next(k for k in keys if k["name"] == "pytest-revoke")
    assert rest.delete(f"/api/auth/api-keys/{target['id']}", headers=headers).status_code == 200

    # 再次访问应被拒
    with TestClient(mcp_app) as c2:
        assert c2.post(
            "/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "ping"},
            headers={"X-API-Key": key},
        ).status_code == 401


# ─────────────────────────────────────────────────────────────
# 身份注入
# ─────────────────────────────────────────────────────────────

def test_mcp_user_identity_comes_from_key(admin_api_key):
    """Key 属于谁，current_user_id() 就返回谁 —— 而不是固定的 DEFAULT_USER_ID"""
    import mcp_server as M

    user = auth_service.resolve_api_key(admin_api_key)
    assert user, "Key 解析失败"

    token = M._mcp_user_id.set(user["id"])
    try:
        assert M.current_user_id() == user["id"]
    finally:
        M._mcp_user_id.reset(token)

    # 未注入时应回落环境变量默认值
    assert M.current_user_id() == M.DEFAULT_USER_ID
