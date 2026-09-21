"""
表达训练接口的回归测试（2026-09-20 迁移 MySQL 时补上）

为什么专门补这个文件
--------------------
迁移到 MySQL 后 `/api/expression/stats` 直接返回 **500**：

    pymysql.err.OperationalError: (1248, 'Every derived table must have its own alias')

根因是 SQL 里有个派生表没写别名 —— `FROM (SELECT ... ORDER BY ... LIMIT 5)`。
**MySQL 强制要求派生表有别名，SQLite 不要求**，所以本地用 SQLite 开发时一直
没暴露；而当时 150 个用例里**没有任何一个打表达训练 API**，于是测试全绿、
接口却是坏的。同文件里还有第二处（`history/questions` 的动态 count_sql），
也一并修了。

这一组用例把表达训练的**全部 GET 路径**跑一遍。它们都不依赖 AI（纯 DB 查询），
所以不用打桩、不联网 —— 即使 MySQL 下也能跑。

配套：`tests/test_sql_dialect_lint.py` 是静态扫描，能在两个后端下都拦住
「派生表没别名」这类 MySQL 专属语法。
"""

import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from main import app                      # noqa: E402
from helpers import get_auth_headers      # noqa: E402


@pytest.fixture(scope="module")
def auth():
    """表达训练的查询都按 `user["name"]` 过滤，用普通用户即可"""
    return get_auth_headers("user")


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


# ================================================================
# 曾经 500 的两条路径
# ================================================================

def test_stats_does_not_500(client, auth):
    """`/api/expression/stats` —— 就是这条在 MySQL 下 500 的

    它的 `avg_score` 用了 `FROM (SELECT ... LIMIT 5)`，
    MySQL 没别名直接报 1248。
    """
    r = client.get("/api/expression/stats", headers=auth)
    assert r.status_code == 200, f"stats 挂了：{r.status_code} {r.text[:300]}"

    body = r.json()
    # 字段契约：前端「训练历史」页顶部三个统计卡读的就是这些
    for key in ("total_answered", "total_days", "type_summary", "avg_score"):
        assert key in body, f"stats 少字段 {key}：{body}"
    assert isinstance(body["total_answered"], int)
    assert isinstance(body["total_days"], int)
    assert isinstance(body["type_summary"], dict)


def test_history_questions_does_not_500(client, auth):
    """分页的「按题目聚合」列表 —— 第二处没别名的 SQL 在这里

    它的 count 用的是 f-string 拼出来的
    `SELECT COUNT(*) FROM ({base_sql} {having})`，同样缺别名。
    """
    r = client.get("/api/expression/history/questions",
                   params={"page": 1, "page_size": 5}, headers=auth)
    assert r.status_code == 200, f"history/questions 挂了：{r.status_code} {r.text[:300]}"

    body = r.json()
    for key in ("total", "page", "page_size", "items"):
        assert key in body, f"history/questions 少字段 {key}：{body}"
    assert isinstance(body["items"], list)
    assert body["page"] == 1
    assert body["page_size"] == 5


@pytest.mark.parametrize("answer_count", ["1", "2", "3", "gt3"])
def test_history_questions_answer_count_filter(client, auth, answer_count):
    """`answer_count` 走的是 HAVING 分支 —— 拼进 count_sql 的那段 SQL

    四种取值都要过一遍：gt3 走 `HAVING answer_count > 3`，
    其余走 `HAVING answer_count = N`。这条分支在 MySQL 下也是拼接出来的，
    单独覆盖一下。
    """
    r = client.get("/api/expression/history/questions",
                   params={"page": 1, "page_size": 5, "answer_count": answer_count},
                   headers=auth)
    assert r.status_code == 200, f"answer_count={answer_count} 挂了：{r.text[:300]}"
    assert "total" in r.json()


# ================================================================
# 其余 GET 路径（同一个文件里的其它查询）
# ================================================================

def test_history_list(client, auth):
    r = client.get("/api/expression/history", params={"limit": 5}, headers=auth)
    assert r.status_code == 200, r.text[:300]
    records = r.json()["records"]
    assert isinstance(records, list)
    assert len(records) <= 5


def test_custom_question_then_detail(client, auth):
    """自定义题目走的是**不走 AI** 的分支，可以顺手当成"造一条数据"的手段

    然后拿它的 id 去查详情 —— 覆盖 `/api/expression/question/{id}`。
    """
    r = client.post("/api/expression/generate",
                    json={"custom_question": "回归测试用的自定义题目",
                          "custom_type": "custom"},
                    headers=auth)
    # 自定义题目是流式端点（SSE），200 即可
    assert r.status_code == 200, r.text[:300]

    # 从 SSE 里取 done 的 JSON
    import json as _json
    payload = None
    for line in r.text.splitlines():
        if line.startswith("data: "):
            obj = _json.loads(line[6:])
            if obj.get("type") == "done":
                payload = obj
    assert payload, f"没拿到 done 事件：{r.text[:300]}"
    qid = payload["id"]
    assert payload["question"] == "回归测试用的自定义题目"
    assert payload["hints"] == []

    r2 = client.get(f"/api/expression/question/{qid}", headers=auth)
    assert r2.status_code == 200, r2.text[:300]
    assert r2.json()["question"] == "回归测试用的自定义题目"


def test_question_detail_404(client, auth):
    r = client.get("/api/expression/question/99999999", headers=auth)
    assert r.status_code == 404


# ================================================================
# 鉴权
# ================================================================

@pytest.mark.parametrize("path", [
    "/api/expression/stats",
    "/api/expression/history",
    "/api/expression/history/questions",
])
def test_requires_auth(client, path):
    """/api/auth/me 之外都得带凭证 —— 别在重构时不小心放开"""
    assert client.get(path).status_code == 401
