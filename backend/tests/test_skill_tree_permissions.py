"""
Self Grow — 技能树权限测试

需求：技能树编辑器仅管理员可用。
- 普通用户：可以查看已发布内容、保存学习进度，但不能创建/保存/上线/删除/AI 编辑
- 管理员：全部写操作放行

这些用例是「后端才是安全边界」的证据：前端隐藏入口只是 UX，
真正拦截必须在服务端（routers/deps.py 的 require_admin）。
"""

import pytest
from fastapi.testclient import TestClient

from main import app
from db.users import get_all_users
from helpers import get_auth_headers   # JWT 改造后所有端点都需要凭证

client = TestClient(app)

ADMIN_ID = None
USER_ID = None


def _setup_roles():
    """从库中取一个 admin 和一个普通用户"""
    global ADMIN_ID, USER_ID
    if ADMIN_ID is not None:
        return
    for u in get_all_users():
        role = u.get("role") or "user"
        if role == "admin" and ADMIN_ID is None:
            globals()["ADMIN_ID"] = u["id"]
        elif role != "admin" and USER_ID is None:
            globals()["USER_ID"] = u["id"]


_setup_roles()

pytestmark = pytest.mark.skipif(
    ADMIN_ID is None or USER_ID is None,
    reason="需要库中同时存在 admin 与普通用户",
)

TREE_ID = "tree_permission_test"


# ─────────────────────────────────────────────────────────────
# /api/auth/me —— 角色权威来源
# ─────────────────────────────────────────────────────────────

def test_auth_me_admin():
    r = client.get(f"/api/auth/me?user_id={ADMIN_ID}", headers=get_auth_headers('admin'))
    assert r.status_code == 200
    data = r.json()
    assert data["role"] == "admin"
    assert data["is_admin"] is True


def test_auth_me_normal_user():
    r = client.get(f"/api/auth/me?user_id={USER_ID}", headers=get_auth_headers('user'))
    assert r.status_code == 200
    data = r.json()
    assert data["is_admin"] is False


# ─────────────────────────────────────────────────────────────
# 写操作 —— 普通用户必须 403
# ─────────────────────────────────────────────────────────────

def test_user_cannot_create_tree():
    r = client.post(
        f"/api/skill-trees?user_id={USER_ID}",
        json={"tree_id": TREE_ID, "name": "越权测试", "description": ""},
        headers=get_auth_headers('user'),
    )
    assert r.status_code == 403


def test_user_cannot_save_draft():
    r = client.put(
        f"/api/skill-trees/{TREE_ID}?user_id={USER_ID}",
        json={
            "name": "越权测试",
            "description": "",
            "data": {"nodes": [], "connections": []},
            "node_count": 0,
            "completed_count": 0,
            "image": "",
            "remark": "",
        },
        headers=get_auth_headers('user'),
    )
    assert r.status_code == 403


def test_user_cannot_publish():
    r = client.put(
        f"/api/skill-trees/{TREE_ID}/publish?user_id={USER_ID}",
        json={"published_data": {"nodes": []}, "node_count": 0, "completed_count": 0},
        headers=get_auth_headers('user'),
    )
    assert r.status_code == 403


def test_user_cannot_delete_tree():
    r = client.delete(f"/api/skill-trees/{TREE_ID}?user_id={USER_ID}", headers=get_auth_headers('user'))
    assert r.status_code == 403


def test_user_cannot_use_ai_edit():
    """AI 编辑能改树，必须和写操作一样要求管理员"""
    r = client.post(
        f"/api/skill-trees/{TREE_ID}/chat?user_id={USER_ID}",
        json={"tree": {"name": "t", "nodes": [], "connections": []}, "message": "加个节点"},
        headers=get_auth_headers('user'),
    )
    assert r.status_code == 403


def test_user_cannot_resume_ai_edit():
    r = client.post(
        f"/api/skill-trees/{TREE_ID}/chat/resume?user_id={USER_ID}",
        json={"thread_id": "stc_x", "message": "确认", "confirm": True},
        headers=get_auth_headers('user'),
    )
    assert r.status_code == 403


# ─────────────────────────────────────────────────────────────
# 读操作 —— 普通用户可用（技能库的意义就是给别人学）
# ─────────────────────────────────────────────────────────────

def test_user_can_read_tree_list():
    r = client.get(f"/api/skill-trees?user_id={USER_ID}", headers=get_auth_headers('user'))
    assert r.status_code == 200


def test_user_can_save_learner_progress():
    """学习进度是普通用户的正当权利，不能被 require_admin 误伤"""
    r = client.put(
        f"/api/skill-trees/{TREE_ID}/learner?user_id={USER_ID}",
        json={"learner": {}},
        headers=get_auth_headers('user'),
    )
    assert r.status_code != 403


# ─────────────────────────────────────────────────────────────
# 管理员 —— 不应被 403 拦住（不存在时是 404，而非 403）
# ─────────────────────────────────────────────────────────────

def test_admin_not_blocked_on_delete():
    r = client.delete(f"/api/skill-trees/{TREE_ID}?user_id={ADMIN_ID}", headers=get_auth_headers('admin'))
    assert r.status_code != 403
