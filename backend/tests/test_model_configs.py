"""
Self Grow — 模型配置 CRUD 的回归测试（2026-09-23 补）

为什么专门补这个文件
--------------------
`PUT /api/model-configs/{id}` 在 2026-09-23 报了一次 **500**，而当时
230 个用例是**全绿**的 —— model_configs 这条链路一个用例都没有。
（同上一次 `/api/expression/stats` 500 的教训：接口有没有被测试打到，
和"测试是不是绿的"是两件事。）

那次 500 的根因不在这个模块本身，而在它踩中了一个**静态护栏的盲区**：

    db/model_configs.py 的 SET 子句是 f-string 动态拼的，里面残留了 SQLite 的
    `datetime('now','localtime')`。项目已只支持 MySQL，`datetime()` 这个函数
    MySQL 根本没有 → 1064，`near '('now','localtime') WHERE id = 3'`。

    SQLite 通路移除时方言层（原来会把 `datetime('now','localtime')` 自动转成
    `now()`）一起删了，**没有兜底**；而 `tests/test_sql_dialect_lint.py` 当时只扫
    `ast.Constant`，f-string 被 AST 拆成多个片段 —— 「有 SQL 关键字」与
    「有 SQLite 写法」落在不同片段，准入判断一挡，违规整条溜过。
    ⇒ 那条护栏也一并补了（`_sql_text_units` + `test_lint_sees_inside_fstrings`）。

这个文件钉住两件事：
  1. **动态 UPDATE 真的能执行**（就是上面那个 500 的路径）
  2. `updated_at` 走的是**本地时间** —— 它依赖连接层的 `SET time_zone='+08:00'`，
     那条一旦被删就会静默偏 8 小时（`now()` 是容器默认的 UTC）

另外顺带补上越权校验：`PUT/DELETE/activate` 都必须校验配置归属。
"""

import os
import sys
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from main import app                      # noqa: E402
from helpers import get_auth_headers      # noqa: E402


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def owner(client):
    """普通用户（测试账号保证存在）"""
    return get_auth_headers("user")


def _mk_config(name="pytest-临时配置", api_key="sk-pytest-0123456789"):
    """直接建一条配置，返回 id —— 用 db 层，省掉一次 HTTP 往返的噪音"""
    from db.model_configs import create_config
    from db.users import get_user_by_name
    from helpers import ensure_test_accounts

    ensure_test_accounts()
    uid = get_user_by_name("test")["id"]
    return create_config(uid, "llm", name, "qwen3.7-flash",
                         "https://dashscope.example.com/v1", api_key)


@pytest.fixture
def temp_config():
    """建一条临时配置，用例结束后删掉（不留在用户数据里）"""
    cfg_id = _mk_config()
    yield cfg_id
    from db.model_configs import delete_config
    delete_config(cfg_id)


# ================================================================
# 1. 动态 UPDATE：就是 500 掉的那条路径
# ================================================================
def test_update_config_runs(temp_config):
    """`update_config` 会拼一句动态 SET 的 UPDATE —— 它必须能真的执行

    历史：SQL 里残留 `datetime('now','localtime')` → MySQL 1064 → 接口 500。
    这类错误**静态层就该拦住**（护栏已补），这条用例是端到端的第二道锁。
    """
    from db.model_configs import update_config, get_config

    assert update_config(temp_config, name="pytest-改过名字", model="qwen3.7-plus") is True
    row = get_config(temp_config)
    assert row["name"] == "pytest-改过名字"
    assert row["model"] == "qwen3.7-plus"


def test_update_config_writes_local_time(temp_config):
    """`updated_at` 必须是**本地时间**（不是 UTC）

    `now()` 走的是连接时区，靠 `db/backend.py::_INIT_COMMAND` 里那句
    `SET time_zone='+08:00'` 撑着。那句话被删掉的话，容器默认 UTC →
    这里会直接偏 8 小时。所以这条断言同时也是那句 init command 的看门人。
    """
    from db.model_configs import update_config, get_config

    update_config(temp_config, name="pytest-时间戳")
    raw = get_config(temp_config)["updated_at"]
    assert raw, "updated_at 为空 —— 说明 UPDATE 里的时间函数没生效"

    written = datetime.strptime(str(raw)[:19], "%Y-%m-%d %H:%M:%S")
    drift = abs((datetime.now() - written).total_seconds())
    assert drift < 600, (
        f"updated_at={raw} 与本地时间差 {drift / 3600:.1f} 小时 —— "
        "时间口径不是本地时间（检查连接层的 SET time_zone）"
    )


def test_update_config_ignores_unknown_fields(temp_config):
    """非白名单字段不能被写进 SET 子句（否则就是注入口子）"""
    from db.model_configs import update_config, get_config

    before = get_config(temp_config)
    assert update_config(temp_config, user_id=999, drop_table="x") is False
    assert get_config(temp_config) == before


# ================================================================
# 2. HTTP 端点：曾经 500 的那一个
# ================================================================
def test_edit_config_endpoint_returns_200(client, owner, temp_config):
    """`PUT /api/model-configs/{id}` —— 就是这个端点报的 500"""
    r = client.put(f"/api/model-configs/{temp_config}", headers=owner,
                   json={"name": "pytest-接口改名"})
    assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"
    assert r.json().get("success") is True

    listed = client.get("/api/model-configs", headers=owner).json()
    mine = [c for c in listed if c["id"] == temp_config]
    assert mine and mine[0]["name"] == "pytest-接口改名"


def test_create_and_delete_config_endpoint(client, owner):
    r = client.post("/api/model-configs", headers=owner,
                    json={"type": "asr", "name": "pytest-临时ASR",
                          "model": "whisper", "base_url": "", "api_key": "sk-x"})
    assert r.status_code == 200, r.text[:300]
    cfg_id = r.json()["id"]

    assert client.delete(f"/api/model-configs/{cfg_id}", headers=owner).status_code == 200
    assert client.get(f"/api/model-configs", headers=owner).status_code == 200


def test_create_config_rejects_bad_type(client, owner):
    r = client.post("/api/model-configs", headers=owner,
                    json={"type": "video", "name": "x", "model": "y"})
    assert r.status_code == 400


def test_list_masks_api_key(client, owner, temp_config):
    """列表接口必须脱敏 —— 密钥不能吐给前端"""
    listed = client.get("/api/model-configs", headers=owner).json()
    mine = [c for c in listed if c["id"] == temp_config][0]
    assert "0123456789" not in mine["api_key"]
    assert mine["api_key"].endswith("6789") and "****" in mine["api_key"]


# ================================================================
# 3. 越权：别人的配置一律不认
# ================================================================
def test_cannot_edit_others_config(client, temp_config):
    """admin 也不能改 test 用户的配置（按 id 操作的写端点必须校验归属）"""
    other = get_auth_headers("admin")
    assert client.put(f"/api/model-configs/{temp_config}", headers=other,
                      json={"name": "越权改名"}).status_code == 404
    assert client.delete(f"/api/model-configs/{temp_config}",
                         headers=other).status_code == 404
    assert client.post(f"/api/model-configs/{temp_config}/activate",
                       headers=other).status_code == 404


def test_endpoints_require_auth(client, temp_config):
    assert client.get("/api/model-configs").status_code == 401
    assert client.put(f"/api/model-configs/{temp_config}",
                      json={"name": "x"}).status_code == 401


# ================================================================
# 4. 启用互斥（同 type 下只能有一条 active）
# ================================================================
def test_set_active_is_exclusive(temp_config):
    from db.model_configs import set_active, get_active_config, get_config
    from db.users import get_user_by_name

    uid = get_user_by_name("test")["id"]
    # 记住原来的 active，用例结束恢复 —— 别把用户真实的模型切换搞乱
    original = get_active_config(uid, "llm")

    a = _mk_config(name="pytest-A")
    b = _mk_config(name="pytest-B")
    try:
        set_active(uid, "llm", a)
        assert get_active_config(uid, "llm")["id"] == a

        set_active(uid, "llm", b)
        assert get_active_config(uid, "llm")["id"] == b
        assert get_config(a)["is_active"] == 0, "同 type 下的另一条没被置 0"
    finally:
        if original:
            set_active(uid, "llm", original["id"])
        from db.model_configs import delete_config
        delete_config(a)
        delete_config(b)
