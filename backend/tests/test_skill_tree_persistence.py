"""
Self Grow — 技能树持久化的回归测试（2026-09-23 补）

为什么专门补这个文件
--------------------
用户报「AI 一直回复我技能树不存在」。查下去发现**整条持久化链都是坏的**，
而当时 241 个用例全绿 —— `skill_trees` 这条链路一个用例都没有
（和同日下午 `model_configs` 那次 500 一个病：**接口有没有被测试打到，
和"测试是不是绿的"是两件事**）。

四个真 bug，全部在这个文件里钉死：

  ① `skill_trees.data` 是 `varchar(255)` —— SQLite 无类型，迁移后固化成硬限制，
     真实树 JSON（几 KB）写进去直接 `1406 Data too long`。
     ⚠️ **空对象存得进去**，所以"建一条空记录"的冒烟永远测不出来 → 用例 1 用真实体量。
  ② `json.loads(row.get("published_data", "null"))` —— `dict.get` 的默认值只在
     「键不存在」时生效，MySQL 给的是"键存在、值 None" → `json.loads(None)` → 500。
  ③ `save_skill_tree_draft` 无条件 `return True`（UPDATE 改到 0 行也算成功）→
     前端一直以为存上了，服务器上一行都没有。
  ④ 写操作异常时 `close()` 没执行 → 事务和行锁留在连接池里，
     之后对该行任何 DELETE 都 `Lock wait timeout`（实测踩到过）。

另外还有一条静态护栏：**`json.loads(x.get(k, "[]"))` 这种"假兜底"不许再出现**
（见文件末尾，带自测）。
"""

import ast
import json
import os
import re
import sys
import uuid

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from db.skill_tree import (               # noqa: E402
    create_skill_tree, save_skill_tree_draft, get_skill_tree_by_tree_id,
    get_skill_trees, delete_skill_tree, publish_skill_tree, get_published_skill_tree,
    save_learner_progress,
)

ADMIN_ID = 2      # db/init.py 播种的 admin
USER_ID = 1       # db/init.py 播种的 test


def _big_tree_bytes(n_nodes=60) -> dict:
    """一棵**真实体量**的树 —— 60 个节点、每个带中文描述，约 6KB

    ⚠️ 必须用真实体量：这条 bug 的隐蔽之处就在于空树（`{}`，几十字节）存得进去。
    """
    return {
        "name": "pytest-大体量技能树",
        "description": "回归用",
        "nodes": [
            {"id": f"n{i}", "name": f"节点{i}", "x": i * 10, "y": i * 5,
             "desc": "描述" * 30, "progress": i % 101}
            for i in range(n_nodes)
        ],
        "connections": [{"from": f"n{i}", "to": f"n{i+1}"} for i in range(n_nodes - 1)],
    }


@pytest.fixture
def tree_id():
    """每个用例一个独立的 tree_id，用完必删（失败也要删）"""
    tid = "tree_pytest_" + uuid.uuid4().hex[:10]
    yield tid
    delete_skill_tree(tid, ADMIN_ID)
    delete_skill_tree(tid, USER_ID)


# ================================================================
# 1. 真实体量写入 / 读回（对应 bug ①）
# ================================================================
def test_save_and_read_back_realistic_tree(tree_id):
    """几 KB 的树必须存得进去、读回来一模一样（曾经的 1406）"""
    data = _big_tree_bytes()
    payload_len = len(json.dumps(data, ensure_ascii=False))
    assert payload_len > 255, "用例本身要够大，否则测不出列宽问题"

    assert create_skill_tree(ADMIN_ID, tree_id, data["name"], data["description"]) > 0
    assert save_skill_tree_draft(tree_id, ADMIN_ID, data["name"], data["description"],
                                 data, len(data["nodes"]), 0) is True

    row = get_skill_tree_by_tree_id(tree_id, ADMIN_ID)
    assert row is not None
    assert row["data"] == data, "读回来的树和写进去的不一致（列宽/编码问题）"
    assert row["node_count"] == len(data["nodes"]) == 60


def test_list_returns_tree_without_crashing(tree_id):
    """列表接口也要能读（它读 update_history，历史为 NULL 时曾 500）"""
    create_skill_tree(ADMIN_ID, tree_id, "pytest-列表", "")
    trees = get_skill_trees(ADMIN_ID)
    mine = [t for t in trees if t["tree_id"] == tree_id]
    assert len(mine) == 1
    assert mine[0]["update_history"] == []


def test_list_exposes_tree_id_as_id(tree_id):
    """列表里的 `id` 必须是 **tree_id 字符串**，不能是数据库自增主键

    踩过（2026-09-24）：两个前端到处都用 `t.id` 当树的标识（侧边栏选中项、
    localStorage key、API 路径 `/api/skill-trees/{id}/...`），而 API 要的是 tree_id。
    服务器上第一次有数据之后，编辑器 currentId 变成 `3` →
    `POST /api/skill-trees/3/chat` → 404「技能树不存在」——
    **症状和"树没存上"一模一样，但树明明在库里**，很容易又查错方向。
    自增主键改名为 `db_id` 保留。
    """
    create_skill_tree(ADMIN_ID, tree_id, "pytest-id契约", "")
    row = [t for t in get_skill_trees(ADMIN_ID) if t["tree_id"] == tree_id]
    assert row, "列表里找不到刚建的树"
    assert row[0]["id"] == tree_id, "对外 id 不是 tree_id 字符串 —— 前端拼出来的 API 路径会 404"
    assert row[0]["db_id"] != tree_id, "自增主键应改名为 db_id 保留"


def test_save_is_idempotent_and_updates(tree_id):
    """保存两次：第二次是更新，不是重复插入"""
    create_skill_tree(ADMIN_ID, tree_id, "pytest-两次", "")
    small = {"name": "两次", "description": "", "nodes": [{"id": "a", "name": "A"}],
             "connections": []}
    assert save_skill_tree_draft(tree_id, ADMIN_ID, "两次", "", small, 1, 0) is True
    assert save_skill_tree_draft(tree_id, ADMIN_ID, "两次改名", "", small, 1, 0) is True

    row = get_skill_tree_by_tree_id(tree_id, ADMIN_ID)
    assert row["name"] == "两次改名"
    assert len([t for t in get_skill_trees(ADMIN_ID) if t["tree_id"] == tree_id]) == 1


# ================================================================
# 2. 「树只存在于浏览器」的自愈（对应 bug ③）
# ================================================================
def test_save_creates_tree_when_missing_on_server(tree_id):
    """服务器上没有这棵树时，保存应当**顺手把它建出来**

    这正是用户那个场景：编辑器把树捏在 localStorage 里，
    服务器一行都没有 → AI 编辑按 tree_id 校验归属，每次 404「技能树不存在」。
    保存时补建 = 用户点一次「保存」就自愈。
    """
    data = _big_tree_bytes(5)
    assert get_skill_tree_by_tree_id(tree_id, ADMIN_ID) is None   # 前置：确实不存在

    assert save_skill_tree_draft(tree_id, ADMIN_ID, "pytest-补建", "", data, 5, 0) is True
    row = get_skill_tree_by_tree_id(tree_id, ADMIN_ID)
    assert row is not None and row["data"] == data


def test_create_is_idempotent(tree_id):
    """同一个 tree_id 重复 create 不报错（原来裸 INSERT → 1062）"""
    first = create_skill_tree(ADMIN_ID, tree_id, "pytest-幂等", "")
    second = create_skill_tree(ADMIN_ID, tree_id, "pytest-幂等", "")
    assert first > 0 and first == second


def test_concurrent_first_save_does_not_raise(tree_id):
    """并发首次保存不能报 1062

    实测踩到（2026-09-24 用户贴的 traceback）：
        pymysql.err.IntegrityError: (1062, "Duplicate entry 'tree_muf2xtz5_20v4'
        for key 'skill_trees.tree_id'")
    根因是「先 SELECT 判存在、再 INSERT」这种 check-then-act ——
    编辑器的保存与「本地树补传」几乎同时发出时，两个请求都查到"不存在"，
    后一个 INSERT 就撞唯一键。窗口很窄，所以这里用线程把它扯开。

    现在实现是一条原子 upsert，所以：**不抛异常 + 结果一致 + 只有一行**。
    """
    from concurrent.futures import ThreadPoolExecutor

    data = _big_tree_bytes(3)

    def save(i):
        return save_skill_tree_draft(tree_id, ADMIN_ID, f"并发{i}", "",
                                     data, 3, 0)

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(save, range(4)))

    assert all(r is True for r in results), f"有并发请求没写成功：{results}"
    rows = [t for t in get_skill_trees(ADMIN_ID) if t["tree_id"] == tree_id]
    assert len(rows) == 1, f"同一个 tree_id 出现了 {len(rows)} 行"


def test_create_returns_zero_when_taken_by_other_user(tree_id):
    """tree_id 被别人占了 → 返回 0（路由层据此报 409，不能假装成功）"""
    assert create_skill_tree(ADMIN_ID, tree_id, "pytest-占位", "") > 0
    assert create_skill_tree(USER_ID, tree_id, "想抢别人的", "") == 0


# ================================================================
# 3. 归属校验：不许写到别人名下
# ================================================================
def test_cannot_save_into_another_users_tree(tree_id):
    create_skill_tree(ADMIN_ID, tree_id, "pytest-归属", "")
    assert save_skill_tree_draft(tree_id, USER_ID, "越权", "", {}, 0, 0) is False

    row = get_skill_tree_by_tree_id(tree_id, ADMIN_ID)
    assert row["name"] == "pytest-归属", "别人不该改得动"
    assert get_skill_tree_by_tree_id(tree_id, USER_ID) is None


def test_publish_requires_existing_tree(tree_id):
    """发布会话里没有这棵树时返回 False（原来无条件 True）"""
    assert publish_skill_tree(tree_id, ADMIN_ID, {"nodes": []}, 0, 0) is False


# ================================================================
# 4. JSON 列读 NULL 不能炸（对应 bug ②）
# ================================================================
def test_read_tree_with_null_published_data(tree_id):
    """`published_data` 为 NULL 时必须能读出来（`json.loads(None)` 曾是 500）"""
    create_skill_tree(ADMIN_ID, tree_id, "pytest-NULL", "")
    row = get_skill_tree_by_tree_id(tree_id, ADMIN_ID)
    assert row["published_data"] is None       # NULL → None，而不是抛异常
    assert row["update_history"] == []

    # 发布之后才有值
    published = {"nodes": [{"id": "a"}], "publishedAt": "2026-09-23 23:00:00"}
    assert publish_skill_tree(tree_id, ADMIN_ID, published, 1, 0) is True
    row = get_skill_tree_by_tree_id(tree_id, ADMIN_ID)
    assert row["published_data"]["nodes"] == [{"id": "a"}]
    assert len(row["update_history"]) == 1
    assert row["update_history"][0]["type"] == "publish"

    # /published 端点（不需要登录）也要能读，且**不许把未发布的草稿带出去**
    pub = get_published_skill_tree(tree_id)
    assert pub is not None and pub["published_data"]["nodes"] == [{"id": "a"}]
    assert "data" not in pub, "草稿 data 不该出现在这个无需登录的端点里"


def test_learner_progress_on_null_published_data(tree_id):
    """对一个还没发布过的树写学习进度：不能因为 published_data 是 NULL 就炸"""
    create_skill_tree(ADMIN_ID, tree_id, "pytest-学习进度", "")
    assert save_learner_progress(tree_id, USER_ID, {"n1": 100}) is True


def test_jloads_semantics():
    """jloads 的语义（这是所有 JSON 列的统一入口）"""
    from db.jsoncols import jloads

    assert jloads(None, []) == []              # NULL
    assert jloads("", []) == []                # 空串
    assert jloads("[]", ["x"]) == []           # 合法 JSON 优先于默认值
    assert jloads('{"a": 1}', {}) == {"a": 1}
    assert jloads(b'{"a": 1}', {}) == {"a": 1}
    assert jloads("坏 json", {"fallback": True}) == {"fallback": True}
    assert jloads({"already": "parsed"}, {}) == {"already": "parsed"}
    # ⚠️ 每次返回新对象：否则调用方 append 会污染下一次的默认值
    assert jloads(None, []) is not jloads(None, [])


# ================================================================
# 5. HTTP 层：PUT 保存曾经是 500（1406）
# ================================================================
def test_save_endpoint_returns_200_for_realistic_tree():
    """`PUT /api/skill-trees/{id}` 存一棵真实体量的树 → 200

    这是用户那条路上的确切请求：以前它 500（1406 Data too long），
    而前端不看返回值，于是「保存成功」和「保存失败」长得一模一样。
    """
    from fastapi.testclient import TestClient
    from main import app
    from helpers import get_auth_headers

    client = TestClient(app)
    headers = get_auth_headers("admin")
    tid = "tree_pytest_http_" + uuid.uuid4().hex[:8]
    data = _big_tree_bytes(40)
    try:
        r = client.post("/api/skill-trees", headers=headers,
                        json={"tree_id": tid, "name": "pytest-HTTP", "description": ""})
        assert r.status_code == 200, r.text[:300]

        r = client.put(f"/api/skill-trees/{tid}", headers=headers,
                       json={"name": "pytest-HTTP", "description": "", "data": data,
                             "node_count": 40, "completed_count": 0,
                             "image": "", "remark": ""})
        assert r.status_code == 200, r.text[:300]
        assert r.json()["success"] is True

        # 读回来确认真的写进去了（不是"200 但没写"）
        r = client.get(f"/api/skill-trees/{tid}", headers=headers)
        assert r.status_code == 200, r.text[:300]
        assert r.json()["data"]["nodes"] == data["nodes"]
    finally:
        client.delete(f"/api/skill-trees/{tid}", headers=headers)
        delete_skill_tree(tid, ADMIN_ID)


def test_save_endpoint_rejects_other_users_tree():
    """改别人名下的树 → 403（不是静默成功）"""
    from fastapi.testclient import TestClient
    from main import app
    from helpers import get_auth_headers

    client = TestClient(app)
    tid = "tree_pytest_http_" + uuid.uuid4().hex[:8]
    try:
        create_skill_tree(ADMIN_ID, tid, "pytest-越权", "")
        r = client.put(f"/api/skill-trees/{tid}", headers=get_auth_headers("user"),
                       json={"name": "越权", "description": "", "data": {},
                             "node_count": 0, "completed_count": 0})
        assert r.status_code == 403, r.text[:300]
        assert get_skill_tree_by_tree_id(tid, ADMIN_ID)["name"] == "pytest-越权"
    finally:
        delete_skill_tree(tid, ADMIN_ID)


# ================================================================
# 6. 静态护栏：列宽 + 「假兜底」
# ================================================================
def test_json_columns_are_wide_enough():
    """存 JSON 的列不许退回成 varchar(255)（SQLite 无类型，迁移后必须显式加宽）

    判据直接读 `information_schema`，不靠"记得改过"。
    """
    from db.connection import get_conn
    from db.init import JSON_COLUMN_TARGETS

    conn = get_conn()
    try:
        for table, col, _target, ok_types, min_len in JSON_COLUMN_TARGETS:
            row = conn.execute(
                """SELECT DATA_TYPE AS dtype, CHARACTER_MAXIMUM_LENGTH AS maxlen
                   FROM information_schema.columns
                   WHERE table_schema = DATABASE() AND table_name = %s AND column_name = %s""",
                (table, col),
            ).fetchone()
            assert row is not None, f"{table}.{col} 不存在 —— 建表语句/迁移有问题"
            dtype = row["dtype"].lower()
            assert dtype in ok_types, (
                f"{table}.{col} 是 {dtype}，应为 {sorted(ok_types)} —— "
                "SQLite 无类型，改窄了照样能建表，但写真实数据会 1406"
            )
            if min_len is not None:
                assert (row["maxlen"] or 0) >= min_len, f"{table}.{col} 长度不足 {min_len}"
    finally:
        conn.close()


def test_no_json_loads_on_dict_get_with_default():
    """静态护栏：不许写 `json.loads(x.get(k, "[]"))` 这种**假兜底**

    `dict.get` 的默认值只在「键不存在」时生效，而 MySQL 的 NULL 是
    「键存在、值 None」→ `json.loads(None)` → TypeError → 500。
    正确写法：`jloads(x.get(k), [])`。

    同时确认「正确写法不会被误报」（第五条规则那条教训：每条静态规则都要正反两个样本）。
    """
    pattern = re.compile(r'json\.loads\(\s*[\w\.\[\]"\']+\.get\([^)]*,\s*"\[\]"|'
                         r'json\.loads\(\s*[\w\.\[\]"\']+\.get\([^)]*,\s*"\{\}"|'
                         r'json\.loads\(\s*[\w\.\[\]"\']+\.get\([^)]*,\s*"null"')

    dbs = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "db")
    problems = []
    for name in sorted(os.listdir(dbs)):
        if not name.endswith(".py"):
            continue
        path = os.path.join(dbs, name)
        src = open(path, encoding="utf-8").read()
        # 只看真正的**字符串字面量**：docstring 里会出现这个"反例"（`db/jsoncols.py`
        # 的开头就拿它当反面教材），注释同理 —— 那是文档，不是代码。
        for lineno, text in _string_literals(src):
            if pattern.search(text):
                problems.append(f"  db/{name}:{lineno}  {text.strip()[:70]}")
    assert not problems, (
        "还有 json.loads(...get(k, \"[]\")) 这种假兜底（NULL 会炸 500），"
        "请改成 jloads(...get(k), []):\n" + "\n".join(problems)
    )

    # 反向：正确写法与普通 JSON 解析不该被误报
    assert not pattern.search('jloads(d.get("published_data"), None)')
    assert not pattern.search('json.loads(row["skill_ids"])')


def _string_literals(src):
    """源码里所有非 docstring 的字符串字面量（含整条 f-string）"""
    tree = ast.parse(src)
    docs = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            d = ast.get_docstring(node, clean=False)
            if d:
                docs.add(d)
    for node in ast.walk(tree):
        if isinstance(node, ast.JoinedStr):
            seg = ast.get_source_segment(src, node)
            if seg:
                yield node.lineno, seg
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.value in docs:
                continue
            yield node.lineno, node.value
