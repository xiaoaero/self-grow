"""
Self Grow — 2026-09-23 加固项的回归测试

覆盖四件事，都是这两天审查中改掉的、**改回去就会静默退化**的行为：

  1. MySQL 连接代理的 `close()` 是「归还这一个连接」而不是「关闭整个池」
  2. aiconsult 的重试只对**值得重试**的错误生效（4xx 立刻失败）
  3. LLM 实例缓存有上限（LRU 淘汰）
  4. 用户输入有长度上限

为什么这些测试全部是纯逻辑、不碰数据库
======================================
它们要钉的是**判据本身**，不是端到端行为：

  · 连接代理的 bug 只在 MySQL 后端才走得到，而跑 MySQL 全量测试需要
    先把库名指向含 `test` 的库（`db/testing.py` 有保护，那道保护是对的）。
    用假的 raw / pool 直接测类，任何后端下都能跑，而且断言更精确 ——
    我们真正要断的就是「没调 pool.close()」这一件事。
  · 重试分类、缓存淘汰、长度校验都是纯函数/纯逻辑。
"""

import gc
import time
from collections import OrderedDict

import pytest
import requests
from fastapi import HTTPException
from pydantic import ValidationError


# ================================================================
# 1. MySQL 连接代理：close() 的语义
# ================================================================
class _FakeRawConn:
    """假的底层单连接（对应 PooledDedicatedDBConnection）"""

    def __init__(self):
        self.close_calls = 0

    def close(self):
        self.close_calls += 1


class _FakePool:
    """假的连接池（对应 PooledDB）"""

    def __init__(self):
        self.close_calls = 0

    def close(self):
        self.close_calls += 1


def _mk_conn():
    from db.backend import MysqlConn

    raw, pool = _FakeRawConn(), _FakePool()
    return MysqlConn(raw, pool), raw, pool


def test_close_returns_connection_and_never_closes_the_pool():
    """close() 归还**这一个**连接，绝不能顺手关掉整个池

    ⚠️ 这是本次修掉的真 bug，别改回去。

    原来写的是 `self._pool.close()`，而 `self._pool` 存的是 **PooledDB 池对象**
    （`self._raw` 才是单个连接）。后果是：**每次 `conn.close()` 都在清空整个池**
    （实测 idle 缓存 1 → 0），下一个请求只能重新建 TCP 连接 + MySQL 认证 +
    `init_command` 里的 `SET time_zone / lock_wait_timeout`。

    连接池等于白建，高并发下多个请求还会互相清空缓存。
    最坑的是它**不报错、功能正常、只是慢**，所以能一直潜伏。
    """
    conn, raw, pool = _mk_conn()
    conn.close()

    assert raw.close_calls == 1, "应当归还底层那一个连接"
    assert pool.close_calls == 0, "绝不能关闭整个池"


def test_close_is_idempotent():
    """重复 close 只归还一次（项目里有分支重复 close 的写法）"""
    conn, raw, pool = _mk_conn()
    conn.close()
    conn.close()
    conn.close()

    assert raw.close_calls == 1
    assert pool.close_calls == 0


def test_del_returns_connection_when_caller_forgets_to_close():
    """调用方忘了 close 时，GC 要兜底归还

    背景：全项目有 100+ 处是 `conn = get_conn() ... conn.close()` 的顺序写法，
    `close()` 不在 `finally` 里 —— 中途抛异常就跳过。而池是
    `PooledDB(blocking=True)`，**池满时无限等待**，每泄漏一个就永久少一个，
    最终表现为「接口不报错也不返回、整站静默卡死」。
    """
    conn, raw, pool = _mk_conn()
    del conn
    gc.collect()

    assert raw.close_calls == 1, "__del__ 应当兜底归还连接"
    assert pool.close_calls == 0


def test_pool_is_created_only_once_under_concurrency(monkeypatch):
    """并发首次取连接时，连接池只能被创建一次

    ⚠️ `_get_pool()` 原本是裸的 `if _pool is None: _pool = PooledDB(...)`，
    这是典型的 check-then-act 竞态：服务刚起来、一批请求同时首次查库时，
    **每个线程都会各建一个完整连接池**，只有最后赋值的那个存活，
    其余的连同已建立的连接一起被丢弃（那些连接要等 GC 才关，
    期间一直占着 MySQL 的连接数）。

    实测症状很好认：16 线程并发首次取连接时，「MySQL 连接池就绪」
    这行日志被打印了 **16 次**。修好后实测降为 1 次，
    建连数 47 → 16、复用率 63% → 88%。
    """
    import threading

    import dbutils.pooled_db as pdb

    import db.backend as B

    created = []

    class _SlowFakePool:
        """构造时故意慢一点，把竞态窗口拉大 —— 否则单线程调度太快测不出来"""

        def __init__(self, **kwargs):
            time.sleep(0.03)
            created.append(kwargs)

    monkeypatch.setattr(pdb, "PooledDB", _SlowFakePool)
    monkeypatch.setattr(B, "_pool", None)

    threads = [threading.Thread(target=B._get_pool) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(created) == 1, f"连接池被创建了 {len(created)} 次（应当只有 1 次）"


# ================================================================
# 2. aiconsult 重试：只重试值得重试的
# ================================================================
def _http_error(code, headers=None):
    resp = requests.Response()
    resp.status_code = code
    resp.headers.update(headers or {})
    return requests.HTTPError(f"{code} error", response=resp)


@pytest.mark.parametrize(
    "err,should_retry,why",
    [
        (requests.Timeout("timed out"), True, "网络超时"),
        (requests.ConnectionError("refused"), True, "连接被拒"),
        (_http_error(500), True, "服务端 5xx"),
        (_http_error(503), True, "服务端 5xx"),
        (_http_error(429), True, "明确限流"),
        (
            _http_error(403, {"X-RateLimit-Remaining": "0"}),
            True,
            "GitHub 用 403 + 配额耗尽表达限流",
        ),
        (_http_error(401), False, "鉴权失败，重试也没用"),
        (_http_error(403), False, "无权限，重试也没用"),
        (_http_error(404), False, "资源不存在，重试也没用"),
        (_http_error(422), False, "参数错误，重试也没用"),
        (ValueError("bad json"), False, "本地代码问题"),
    ],
)
def test_retry_classification(err, should_retry, why):
    """只有网络错误 / 5xx / 限流才重试，4xx 立刻失败

    ⚠️ 原来是一律 `except Exception` 重试 3 次、每次固定等 60~90 秒。
    APScheduler 的工作线程池只有 4 个，一个 4xx 任务能耗掉 4.5 分钟，
    后面排队的定时抓取全被推迟。
    """
    from services.aiconsult_service import _classify_error

    assert _classify_error(err)[0] is should_retry, why


def test_retry_after_header_is_respected():
    """服务端明确要求等待时以它为准（限流场景）"""
    from services.aiconsult_service import _classify_error

    retryable, wait = _classify_error(_http_error(429, {"Retry-After": "45"}))
    assert retryable is True
    assert wait == 45.0


def test_absurd_rate_limit_reset_is_rejected():
    """荒谬的 X-RateLimit-Reset 要被 sanity check 挡掉

    第三方响应头不可信是常态：实测一个夸张的时间戳会算出
    980 亿秒的等待（虽然最终仍会被 RETRY_MAX_SEC 封顶到 60s，
    但日志里出现这种数字很容易让人以为程序算错了）。
    """
    from services.aiconsult_service import _classify_error

    _, wait = _classify_error(
        _http_error(403, {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "99999999999"})
    )
    assert wait is None

    # 合理的值（未来 2 分钟）要认
    _, wait_ok = _classify_error(
        _http_error(
            403,
            {
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(int(time.time()) + 120),
            },
        )
    )
    assert wait_ok is not None and 100 < wait_ok <= 120


def test_every_request_uses_its_own_session():
    """每个线程用各自的 requests.Session

    `requests.Session` 官方不保证线程安全（连接池与 cookie 可能串）。
    定时抓取跑在 APScheduler 工作线程、手动刷新跑在请求线程，确实并发。

    ⚠️ 断言用 `is not` 而不是比 `id()`。
    线程是先后跑完的，前一个线程结束后它的 thread-local 数据会被回收，
    下一个线程新建的 Session **可能恰好落在同一块内存地址上** ——
    比 id() 会假通过（第一版就是这么写的，实测踩到了）。
    持有对象引用（`sessions.append(...)`）既能防止被回收，比较也更直接。
    """
    import threading

    from services.aiconsult_service import _get_session

    sessions = []
    lock = threading.Lock()

    def worker():
        first = _get_session()
        second = _get_session()          # 同一线程内必须复用
        assert first is second, "同一线程内应复用同一个 Session"
        with lock:
            sessions.append(first)       # 持有引用，避免被 GC 回收后复用地址

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(sessions) == 2
    assert sessions[0] is not sessions[1], "不同线程必须拿到不同的 Session"


# ================================================================
# 3. LLM 实例缓存：有上限
# ================================================================
@pytest.fixture
def fake_llm(monkeypatch):
    """把 ChatOpenAI 与配置读取都替换掉，专测缓存逻辑"""
    import services.llm as L

    monkeypatch.setattr(L, "_llm_cache", OrderedDict())
    monkeypatch.setattr(
        L, "get_active_config",
        lambda *a, **k: {"model": "m", "api_key": "k", "base_url": "u"},
    )
    monkeypatch.setattr(L, "ChatOpenAI", lambda **kw: object())
    return L


def test_llm_cache_is_bounded(fake_llm):
    """缓存不会无限增长（原来是个只增不减的普通 dict）

    每个缓存项都是一个带自己 httpx 连接池的 ChatOpenAI 实例，
    而 key 里含 (temperature, max_tokens, timeout, model, base_url, api_key) ——
    「改一次配置多一个常驻实例」这件事原先没有任何东西拦着。
    """
    L = fake_llm
    for i in range(L._MAX_LLM_CACHE + 20):
        L.get_llm(temperature=round(0.01 * i, 2))

    assert len(L._llm_cache) == L._MAX_LLM_CACHE


def test_llm_cache_hit_refreshes_and_does_not_grow(fake_llm):
    """同参数命中不新增；命中会把该项移到队尾（LRU 语义）"""
    L = fake_llm
    L.get_llm(temperature=0.1)
    L.get_llm(temperature=0.2)
    n = len(L._llm_cache)

    for _ in range(5):
        L.get_llm(temperature=0.1)
    assert len(L._llm_cache) == n, "相同参数不应产生新实例"

    oldest = next(iter(L._llm_cache))       # 当前最久未用
    L.get_llm(temperature=oldest[0])
    assert list(L._llm_cache.keys())[-1] == oldest, "命中后应移到队尾"


# ================================================================
# 4. 输入长度上限
# ================================================================
def test_check_length_allows_and_rejects():
    from schemas.limits import MAX_ANSWER_TEXT, check_length

    assert check_length("正常回答", MAX_ANSWER_TEXT, "回答内容") == "正常回答"
    assert check_length(None, MAX_ANSWER_TEXT, "回答内容") == ""

    # 边界值应当通过（上限是「不超过」）
    assert len(check_length("x" * MAX_ANSWER_TEXT, MAX_ANSWER_TEXT, "回答内容")) == MAX_ANSWER_TEXT

    with pytest.raises(HTTPException) as e:
        check_length("x" * (MAX_ANSWER_TEXT + 1), MAX_ANSWER_TEXT, "回答内容")
    assert e.value.status_code == 400
    # 文案要带实际长度，否则用户不知道超了多少
    assert str(MAX_ANSWER_TEXT + 1) in e.value.detail
    assert str(MAX_ANSWER_TEXT) in e.value.detail


def test_check_history_limits_both_count_and_total():
    """条数与总字符数都要卡：只卡一个会被另一个维度绕过"""
    from schemas.limits import (
        MAX_HISTORY_MESSAGES, MAX_HISTORY_TOTAL_CHARS, check_history,
    )

    ok = [{"role": "user", "content": "你好"}]
    assert check_history(ok) == ok

    # 条数超限
    with pytest.raises(HTTPException):
        check_history([{"role": "user", "content": "x"}] * (MAX_HISTORY_MESSAGES + 1))

    # 单条极长（条数没超，但总量超）
    with pytest.raises(HTTPException):
        check_history([{"role": "user", "content": "x" * (MAX_HISTORY_TOTAL_CHARS + 1)}])

    # 不是数组
    with pytest.raises(HTTPException):
        check_history("not a list")


def test_chat_request_rejects_overlong_message():
    """coordinator 的 ChatRequest 在模型层就挡住超长消息（→ 422）"""
    from routers.coordinator import ChatRequest
    from schemas.limits import MAX_USER_MESSAGE

    ChatRequest(message="x" * MAX_USER_MESSAGE)          # 边界值通过
    with pytest.raises(ValidationError):
        ChatRequest(message="x" * (MAX_USER_MESSAGE + 1))


def test_skill_tree_chat_request_rejects_overlong_message():
    """技能树 AI 的 ChatRequest 同样有上限"""
    from routers.skill_tree_ai import ChatRequest
    from schemas.limits import MAX_USER_MESSAGE

    ChatRequest(tree={}, message="正常指令")
    with pytest.raises(ValidationError):
        ChatRequest(tree={}, message="x" * (MAX_USER_MESSAGE + 1))


def test_asr_limit_is_reachable_in_expression_router():
    """语音识别的音频上限确实接在了接收循环上（不是只定义了常量没用）

    用源码断言而不是跑 WebSocket：真跑要 DashScope 凭据，
    而这里要防的正是「常量加了、循环里忘了用」这种退化。
    """
    import io

    from schemas.limits import MAX_ASR_AUDIO_BYTES

    src = io.open("routers/expression.py", encoding="utf-8").read()
    assert "MAX_ASR_AUDIO_BYTES" in src, "上限常量必须真的被接收循环引用"

    # 且确实在 receive_audio 里做了累计与判断
    start = src.find("async def receive_audio")
    assert start > 0
    body = src[start:start + 1200]
    assert "received += len(data)" in body
    assert "MAX_ASR_AUDIO_BYTES" in body
