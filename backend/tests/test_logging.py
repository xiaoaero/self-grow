"""
Self Grow — 日志系统回归测试

覆盖 docs/日志系统方案.md 里承诺的几件事，防止以后被改回去：

1. root handler 的格式带时间戳（原来 basicConfig 的默认格式没有）
2. X-Request-ID 回写响应头，**且同一个 id 出现在日志文本里**（串起来的关键）
3. 未处理异常 → 500 且 body 不含内部异常信息，只给 request_id
4. request_id 能穿过 asyncio.to_thread（本项目大量用它调同步 DB）
5. 敏感串脱敏（sk-xxx / Bearer xxx）
6. 全局开到 DEBUG 时，httpx / langchain 仍然不输出 DEBUG
7. /api/health 不产生访问日志（每 60s 一次，一天 1440 条）
"""

import asyncio
import io
import logging
import re

import pytest
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

from services.logging_setup import (
    _ContextFilter,
    request_id_var,
    setup_logging,
)
from services.middleware import REQUEST_ID_HEADER, RequestContextMiddleware


# ================================================================
# 工具
# ================================================================

class _LogCapture:
    """往 root 挂一个 StringIO handler，顺便复用生产用的 _ContextFilter

    复用同一个 filter 很关键：这样测的是真实链路（含 request_id 注入
    与脱敏），而不是只测一个孤立函数。
    """

    def __init__(self):
        self.stream = io.StringIO()
        self.handler = logging.StreamHandler(self.stream)
        self.handler.setFormatter(
            logging.Formatter("%(request_id)s|%(name)s|%(message)s")
        )
        self.handler.addFilter(_ContextFilter())
        self.root = logging.getLogger()
        self._old_level = None

    def __enter__(self):
        self._old_level = self.root.level
        # 测试期间放开级别，否则被前面用例调低的 level 会让日志抓不到
        self.root.setLevel(logging.INFO)
        self.root.addHandler(self.handler)
        return self

    def __exit__(self, *exc):
        self.root.removeHandler(self.handler)
        if self._old_level is not None:
            self.root.setLevel(self._old_level)
        return False

    def text(self) -> str:
        return self.stream.getvalue()


def _build_probe_app() -> FastAPI:
    """搭一个最小 app 来验证中间件行为

    刻意**不**用 main.app：那边的路由会连带 DB、鉴权、APScheduler，
    测中间件本身不需要这些，也不该被它们影响。
    """
    probe = FastAPI()

    # 与 main.py 保持同样的注册顺序（先 RequestContext，后 CORS）
    probe.add_middleware(RequestContextMiddleware)
    probe.add_middleware(CORSMiddleware, allow_origins=["*"], expose_headers=["X-Request-ID"])

    @probe.get("/ok")
    async def ok():
        return {"ok": True}

    @probe.get("/boom")
    async def boom():
        raise RuntimeError("SECRET_INTERNAL_DETAIL_9f2c")

    @probe.get("/api/health")
    async def health():
        return {"status": "healthy"}

    return probe


# ================================================================
# 1. 格式带时间戳
# ================================================================

def test_root_handler_format_has_timestamp():
    """root handler 的格式必须带时间戳

    原来 `logging.basicConfig(level=INFO)` 的默认格式是
    `LEVEL:name:message` —— **完全没有时间**，排查时序问题时无从下手。
    """
    setup_logging()
    root = logging.getLogger()
    assert root.handlers, "root 上应该有 handler（setup_logging 没生效）"

    record = logging.LogRecord("probe", logging.INFO, __file__, 1, "hello", (), None)
    record.request_id = "abc123"
    rendered = [h.formatter.format(record) for h in root.handlers if h.formatter]
    assert rendered, "handler 必须带 formatter"
    assert re.search(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", rendered[0]), rendered[0]


def test_file_handler_enabled():
    """必须同时有 stderr 与文件两个 handler —— 只有 stderr 的话容器重建即丢"""
    setup_logging()
    root = logging.getLogger()
    kinds = {type(h).__name__ for h in root.handlers}
    assert "StreamHandler" in kinds
    assert "RotatingFileHandler" in kinds


# ================================================================
# 2. request_id 贯穿
# ================================================================

def test_request_id_echoed_in_header_and_present_in_logs():
    """响应头回写 X-Request-ID，且同一个 id 出现在日志行里

    这是「把一次请求的日志串起来」的核心断言：
    光有响应头没用，光有日志也没用，必须**能对上**。
    """
    rid = "pytest-rid-0001"
    with _LogCapture() as cap:
        client = TestClient(_build_probe_app())
        resp = client.get("/ok", headers={REQUEST_ID_HEADER: rid})

    assert resp.status_code == 200
    assert resp.headers[REQUEST_ID_HEADER] == rid
    assert f"{rid}|" in cap.text(), cap.text()


def test_request_id_generated_when_absent():
    """客户端没传时要自动生成一个，不能是空字符串"""
    with _LogCapture():
        client = TestClient(_build_probe_app())
        resp = client.get("/ok")

    rid = resp.headers[REQUEST_ID_HEADER]
    assert rid and rid != "-"
    assert len(rid) >= 8


def test_request_id_propagates_into_to_thread():
    """request_id 必须能穿过 asyncio.to_thread

    本项目的大量同步 DB 逻辑都跑在 to_thread 里（151 处 get_conn）。
    如果 ContextVar 不能传播，那些日志就会全部丢掉 request_id ——
    而这恰恰是最需要排查的部分。
    """
    async def main():
        request_id_var.set("thread-check-42")

        def sync_worker():
            # 模拟同步 DB 代码里的 log.info
            return request_id_var.get()

        return await asyncio.to_thread(sync_worker)

    assert asyncio.run(main()) == "thread-check-42"


# ================================================================
# 3. 未处理异常兜底
# ================================================================

def test_unhandled_exception_hides_internals_and_reports_request_id():
    """未处理异常：500 + 固定文案 + request_id，且 body 不含 str(e)"""
    with _LogCapture() as cap:
        client = TestClient(_build_probe_app(), raise_server_exceptions=False)
        resp = client.get("/boom")

    assert resp.status_code == 500
    body = resp.text

    # 不能把内部异常信息吐给前端
    assert "SECRET_INTERNAL_DETAIL_9f2c" not in body
    # 但要把 request_id 给出去，方便对日志
    payload = resp.json()
    assert payload.get("request_id")
    assert resp.headers.get(REQUEST_ID_HEADER) == payload["request_id"]

    # 日志里必须有完整信息（含堆栈）
    logs = cap.text()
    assert "未处理异常" in logs
    assert "SECRET_INTERNAL_DETAIL_9f2c" in logs
    assert "Traceback" in logs


def test_main_app_has_request_context_middleware():
    """main.py 必须真的把中间件装配上（顺序：RequestContext 在内，CORS 在外）"""
    from main import app

    names = [m.cls.__name__ for m in app.user_middleware]
    assert "RequestContextMiddleware" in names
    assert "CORSMiddleware" in names
    assert names.index("CORSMiddleware") < names.index("RequestContextMiddleware"), (
        "CORS 必须在 RequestContext 外层，否则中间件兜底返回的 500 "
        "不会被补上跨域头，前端只能看到 CORS 错误、拿不到 request_id"
    )


# ================================================================
# 4. 脱敏
# ================================================================

@pytest.mark.parametrize(
    "raw, forbidden",
    [
        ("调用失败 key=sk-abcdef1234567890xyz", "sk-abcdef1234567890xyz"),
        ("headers={'Authorization': 'Bearer eyJhbGciOiJIUzI1NiJ9.abc'}", "eyJhbGciOiJIUzI1NiJ9.abc"),
        ("api_key=supersecretvalue123", "supersecretvalue123"),
    ],
)
def test_secret_redaction(raw, forbidden):
    """敏感串在落盘前必须被替换掉"""
    record = logging.LogRecord("probe", logging.INFO, __file__, 1, raw, (), None)
    _ContextFilter().filter(record)
    assert forbidden not in record.getMessage(), record.getMessage()
    assert "***" in record.getMessage(), record.getMessage()


def test_redaction_keeps_normal_message_intact():
    """普通消息不能被误伤（脱敏只能改敏感片段）"""
    record = logging.LogRecord(
        "probe", logging.INFO, __file__, 1, "用户 %s 打卡成功，+%d EXP", ("test", 30), None
    )
    _ContextFilter().filter(record)
    assert record.getMessage() == "用户 test 打卡成功，+30 EXP"


# ================================================================
# 5. 第三方库降噪
# ================================================================

def test_noisy_libraries_capped_even_in_debug():
    """全局开 DEBUG 时，第三方库仍然不能跟着刷 DEBUG"""
    setup_logging()
    root = logging.getLogger()
    old_level = root.level
    root.setLevel(logging.DEBUG)
    try:
        for name in ("httpx", "httpcore", "langchain", "langchain_core", "pymysql"):
            logger = logging.getLogger(name)
            assert not logger.isEnabledFor(logging.DEBUG), (
                f"{name} 在全局 DEBUG 下漏出了 DEBUG 日志"
            )
    finally:
        root.setLevel(old_level)


# ================================================================
# 6. 健康检查降噪
# ================================================================

def test_health_check_not_logged():
    """/api/health 每 60 秒一次，不该产生访问日志"""
    with _LogCapture() as cap:
        client = TestClient(_build_probe_app())
        resp = client.get("/api/health")

    assert resp.status_code == 200
    assert "GET /api/health" not in cap.text()


def test_normal_request_is_logged():
    """反向断言：普通请求**必须**留痕（否则上面那条测试等于在测「啥都没记」）"""
    with _LogCapture() as cap:
        client = TestClient(_build_probe_app())
        client.get("/ok")

    assert "GET /ok -> 200" in cap.text()
