"""
Self Grow — 请求可观测中间件

做四件事：

1. **request_id 贯穿全链路** —— 每个请求一个短 id，写进 ContextVar，
   于是全链路日志（含 `asyncio.to_thread` 里跑的同步 DB 代码）都自动带上它。
   同时把 id 回写到响应头 `X-Request-ID`，前端报错时能把这个 id 报出来。
2. **访问日志** —— 一行一条：方法 / 路径 / 状态码 / 耗时 / 用户。
   慢请求按路径分档升级为 WARNING。
3. **未处理异常兜底** —— 记完整 traceback（带路径与用户），
   返回固定文案 + request_id，**不把 `str(e)` 吐给前端**。
4. **健康检查降噪** —— `/api/health` 每 60 秒一次，一天 1440 条，不留。

为什么用**纯 ASGI 中间件**而不是 `BaseHTTPMiddleware`
-----------------------------------------------------
本项目有 SSE 长连接（协调 Agent 流式回复）和 WebSocket（`/ws/asr`）。
`BaseHTTPMiddleware` 会在中间件层再包一层 anyio 内存流，对这类响应引入
额外的缓冲与取消语义差异。纯 ASGI 中间件只包装 `send` / `receive`，
对响应体零额外拷贝。

⚠️ 注册顺序（见 main.py）：必须**先** `add_middleware(RequestContextMiddleware)`
再 `add_middleware(CORSMiddleware)`。Starlette 的 `add_middleware` 是
`insert(0, ...)`，后加的在外层 —— 我们需要 CORS 在外，
这样本中间件兜底返回的 500 响应才会被 CORS 补上跨域头
（否则前端只能看到 CORS 错误，看不到我们返回的 request_id）。
"""

from __future__ import annotations

import logging
import time
import uuid

from starlette.datastructures import MutableHeaders
from starlette.responses import JSONResponse

from services.logging_setup import request_id_var

__all__ = ["RequestContextMiddleware", "REQUEST_ID_HEADER", "is_ai_path"]

log = logging.getLogger("access")

REQUEST_ID_HEADER = "X-Request-ID"

# ── 慢请求阈值（毫秒）──
# **必须按路径分档**：协调 Agent 一次请求要跑 N 个子 Agent + LLM 总结，
# 几十秒是正常耗时。用统一阈值的话满屏都是「慢请求」告警，等于没有告警。
SLOW_MS_DEFAULT = 3000
SLOW_MS_AI = 60000

# 会调用 LLM / 外部搜索的路径，按 AI 档位放宽
_AI_PATH_PREFIXES = (
    "/api/coordinator",
    "/api/expression",
    "/api/skill-trees",
    "/api/aiconsult",
    "/api/model-configs",
    "/api/actions/ai-chat",
    "/api/actions/ai-submit",
    "/api/habits/ai-icon",
)

# 容器健康检查（每 60s 一次）与浏览器自动请求，不值得留日志
_QUIET_PATHS = frozenset({"/api/health", "/favicon.ico"})

# 客户端传进来的 request id 只接受这个长度的 ASCII，避免把任意串写进日志
_MAX_INCOMING_ID = 32


def is_ai_path(path: str) -> bool:
    """该路径是否属于「天生就慢」的 AI 链路"""
    return path.startswith(_AI_PATH_PREFIXES)


def _scope_user_id(scope: dict) -> str:
    """从 ASGI scope 里取当前用户 id

    由 `routers/deps.py::get_current_user` 写入 `request.state.user_id`；
    未鉴权 / 鉴权失败的请求取不到，返回 "-"。
    """
    try:
        state = scope.get("state") or {}
        return state.get("user_id", "-")
    except Exception:  # noqa: BLE001
        return "-"


class RequestContextMiddleware:
    """纯 ASGI 中间件：request_id 注入 + 访问日志 + 异常兜底"""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        # WebSocket / lifespan 事件原样透传（它们不走 HTTP 响应语义）
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        request_id = _resolve_request_id(scope)
        token = request_id_var.set(request_id)

        # 同时也写进 scope["state"]，让 `request.state.request_id` 读得到。
        #
        # ⚠️ 两个地方都写是有意的：ContextVar 是**唯一来源**（日志 filter 读它，
        #    且能穿过 asyncio.to_thread），但很多人的直觉是写
        #    `request.state.request_id` —— 只写 ContextVar 的话那个读法会
        #    静默拿到默认值（实测：main.py 的 422 handler 里就这么写过，
        #    日志里 req 正常、响应体里却是 "-"，用户贴出来的 id 对不上日志）。
        #    值是同一个，不存在不一致。
        scope.setdefault("state", {})["request_id"] = request_id

        method = scope.get("method", "-")
        path = scope.get("path", "-")
        start = time.perf_counter()
        # 用 dict 而非闭包变量：闭包里的赋值对 finally 不可见
        outcome = {"status": 500, "started": False}

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                outcome["status"] = message["status"]
                outcome["started"] = True
                # 回写 request_id，前端报错时能直接把它贴出来
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            # 走到了这里说明异常一路冒到了中间件层 ——
            # 默认情况下只有 uvicorn 打一行裸 traceback，没有路径也没有用户，
            # 根本对不上是哪次请求
            log.exception(
                "未处理异常 %s %s (user=%s)", method, path, _scope_user_id(scope)
            )
            if outcome["started"]:
                # 响应已经开始发送（典型：SSE 流中途失败）。
                # 不能再发第二个响应，只能记完日志往上抛。
                raise
            outcome["status"] = 500
            response = JSONResponse(
                {
                    "detail": "服务器内部错误，请稍后重试",
                    "request_id": request_id,
                },
                status_code=500,
            )
            await response(scope, receive, send_wrapper)
            # 已返回兜底响应，异常就此消化，不再交给外层重复记录
        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000
            _log_access(method, path, outcome["status"], elapsed_ms, scope)
            request_id_var.reset(token)


def _resolve_request_id(scope: dict) -> str:
    """沿用客户端传入的 X-Request-ID（便于前后端串联），否则新生成一个"""
    try:
        for key, value in scope.get("headers") or []:
            if key == b"x-request-id":
                incoming = value.decode("latin-1").strip()
                if incoming and incoming.isascii():
                    return incoming[:_MAX_INCOMING_ID]
                break
    except Exception:  # noqa: BLE001
        pass
    return uuid.uuid4().hex[:12]


def _log_access(method: str, path: str, status: int, elapsed_ms: float, scope: dict) -> None:
    """输出一条访问日志，按状态码与耗时分档"""
    if path in _QUIET_PATHS:
        return

    line = f"{method} {path} -> {status} {elapsed_ms:.0f}ms user={_scope_user_id(scope)}"

    if status >= 500:
        log.error(line)
    elif status >= 400:
        log.warning(line)
    else:
        limit = SLOW_MS_AI if is_ai_path(path) else SLOW_MS_DEFAULT
        if elapsed_ms >= limit:
            log.warning("%s  [慢请求 >%dms]", line, limit)
        else:
            log.info(line)
