"""
Self Grow — SSE（Server-Sent Events）统一工具

本项目所有流式端点都走这里，保证「事件格式」与「响应头」只有一份定义。

## 事件协议（全项目统一）

每条事件 = 一行 `data:` + JSON + 一个空行：

    data: {"type": "stage", "stage": "routing", "label": "正在理解你的意图…"}
    data: {"type": "token", "text": "已"}
    data: {"type": "done",  ...原同步接口的全部字段...}
    data: {"type": "error", "message": "..."}

把类型放在 `data` 的 JSON 里、而不是用 SSE 原生的 `event:` 字段，是为了让前端
只有一个解析分支（项目里原有那两个占位端点也是这个约定）。

## ⚠️ 为什么必须用 fetch，不能用 EventSource

浏览器原生的 `EventSource` **不能自定义请求头**；而本项目的身份凭证是
`frontend/js/auth.js` 包装 `window.fetch` 注入的 `Authorization: Bearer`。
用 `EventSource` 会 100% 拿到 401。

所以前端统一用 `fetch` + `resp.body.getReader()` 自己解析（见 `utils.js::streamSSE`）。
反过来这也要求流式端点做成 **POST** —— `EventSource` 只支持 GET，
而 GET 又带不了 token，这也是原来两个 GET 占位端点要么没鉴权、
要么浏览器根本连不上的原因。

## 长任务的两个保活手段

单次 LLM 调用可能 30~60s 没有任何输出，中间隔着 Nginx 会被空闲超时掐断：

1. `X-Accel-Buffering: no` 响应头 —— 让 Nginx **对这个响应**关掉缓冲。
   比改 Nginx 配置更可靠，因为它跟着代码走，换部署方式也不会丢
2. `keepalive()` —— 等待期间周期性发 SSE 注释行（`: ping`）把空闲计时器顶掉
"""

import asyncio
import contextlib
import json
import logging
from contextlib import contextmanager
from contextvars import ContextVar
from typing import AsyncIterator, Callable, Optional

from fastapi.responses import StreamingResponse

log = logging.getLogger(__name__)

SSE_MEDIA_TYPE = "text/event-stream"

SSE_HEADERS = {
    # 别让浏览器/中间层缓存事件流
    "Cache-Control": "no-cache, no-transform",
    # 让 Nginx 对这个响应关缓冲（关键：不关的话事件会被攒着一次性发出，
    # 表现成「流式看起来没生效」）
    "X-Accel-Buffering": "no",
    "Connection": "keep-alive",
}


# ================================================================
# 事件编码
# ================================================================

def sse(payload: dict) -> str:
    """把一个 dict 编码成一条 SSE 事件"""
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def sse_comment(text: str = "ping") -> str:
    """SSE 注释行（心跳）

    形如 `: ping\\n\\n`。客户端解析时会忽略它，但**字节确实发过去了**，
    作用是把中间代理的空闲计时器顶掉。
    """
    return f": {text}\n\n"


def sse_response(gen: AsyncIterator[str]) -> StreamingResponse:
    """把异步生成器包成 StreamingResponse（自动带正确的响应头）"""
    return StreamingResponse(gen, media_type=SSE_MEDIA_TYPE, headers=SSE_HEADERS)


async def stream_events(runner, heartbeat: float = 15.0) -> AsyncIterator[str]:
    """跑一个「用 emit 主动推事件」的协程，把事件与心跳合流成 SSE 文本

    Args:
        runner: `async def runner(emit) -> None`，内部自己 `await emit(payload)`
        heartbeat: 静默超过这么多秒就发一次 SSE 注释心跳（顶掉代理的空闲超时）

    Yields:
        str: SSE 文本片段（事件或心跳）

    为什么不是「await 完协程再一次性编码」：
        阶段事件是在**很深的调用链里**产生的（router → graph → agent → tool），
        还发生在 `asyncio.gather` 的多个并发子任务中，没法靠一个返回值拿到。
        所以统一用队列把 emit 与「产出 SSE」解耦。

    这是本项目所有流式端点的唯一入口，端点都长这样：

        async def runner(emit):
            with use_emitter(emit):        # 让深层代码能用 emit_stage 推事件
                await do_something_streaming()
            await emit({"type": "done", **payload})

        return sse_response(stream_events(runner))
    """
    queue: asyncio.Queue = asyncio.Queue()

    async def emit(payload: dict) -> None:
        await queue.put(payload)

    async def _run():
        try:
            await runner(emit)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            log.exception("流式任务执行失败")
            await queue.put({"type": "error", "message": str(e)})
        finally:
            await queue.put(None)          # 结束哨兵

    task = asyncio.ensure_future(_run())
    try:
        while True:
            try:
                payload = await asyncio.wait_for(queue.get(), timeout=heartbeat)
            except asyncio.TimeoutError:
                yield sse_comment()        # 长时间没事件 → 发心跳保活
                continue
            if payload is None:
                return
            yield sse(payload)
    finally:
        # 客户端断开时 FastAPI 会取消这个生成器；把内层任务一起收掉，
        # 否则会留下「Task was destroyed but it is pending」告警 + 悬挂的子 Agent
        if not task.done():
            task.cancel()
            with contextlib.suppress(BaseException):
                await task


async def immediate_response(payload: dict) -> StreamingResponse:
    """已经拿到结果的场景：发一条 done 就结束

    仍然是 SSE（而不是直接返回 JSON），目的是让前端**只有一条解析路径** ——
    否则同一份前端代码要写「有时候读 JSON、有时候读流」两个分支。

    典型用例：命中缓存的评分结果、幂等命中的 resume。
    """
    async def runner(emit):
        await emit({"type": "done", **payload})

    return sse_response(stream_events(runner))


async def keepalive(coro, interval: float = 15.0):
    """等待一个协程完成，期间周期性产出心跳

    Yields:
        ("tick", None)      —— 该发心跳了
        ("result", value)   —— 协程完成，最后一个产出

    用法：

        async for kind, value in keepalive(some_async_call()):
            if kind == "tick":
                yield sse_comment()
            else:
                result = value

    注意 coro 必须**已经是协程对象**（调用时不要 await）。
    若调用方中途不迭代了，finally 里会 cancel 掉它，不留悬挂任务。
    """
    task = asyncio.ensure_future(coro)
    try:
        while True:
            done, _ = await asyncio.wait({task}, timeout=interval)
            if task in done:
                yield ("result", task.result())   # 异常会在这里原样抛出
                return
            yield ("tick", None)
    finally:
        if not task.done():
            task.cancel()


# ================================================================
# 阶段事件发射器（ContextVar）
# ================================================================

# 为什么用 ContextVar 而不是「把回调传进函数」：
#   分层调用链太深（router → graph → agent → tools），一路加参数会污染所有签名；
#   而技能树 AI 的图是**模块级单例**（get_skill_tree_chat_graph 缓存了编译结果），
#   更没法在编译时把每个请求的回调烘进去。
#   ContextVar 天然按 asyncio 任务隔离 —— asyncio.gather / create_task 会复制当前
#   上下文，所以并发子 Agent 各自的事件不会串。
#
# 重要：没设置发射器时 emit_stage 是**完全空操作**，
# 同步路径（不流式）的行为一个字都不会变。
_emitter: ContextVar[Optional[Callable]] = ContextVar("sse_emitter", default=None)


@contextmanager
def use_emitter(emit: Optional[Callable]):
    """在 with 块内启用阶段发射器

    emit 是 `async def emit(payload: dict) -> None`。
    """
    token = _emitter.set(emit)
    try:
        yield
    finally:
        _emitter.reset(token)


async def emit_event(payload: dict) -> None:
    """发一条任意事件；没有启用流式时静默丢弃"""
    emit = _emitter.get()
    if emit is None:
        return
    try:
        await emit(payload)
    except Exception as e:
        # 推送失败绝不能影响主流程（典型场景：客户端已经断开连接）
        log.debug(f"事件推送失败（已忽略）：{e}")


async def emit_stage(stage: str, label: str = "", **extra) -> None:
    """发一个阶段事件；没有启用流式时静默丢弃

    Args:
        stage: 阶段标识（前端可按需分支，如 routing / dispatch / tool / synthesize）
        label: 给用户看的中文提示
        extra: 附加字段（如 domain / tool / index）
    """
    await emit_event({"type": "stage", "stage": stage, "label": label, **extra})


async def emit_token(text: str) -> None:
    """发一个文本增量事件；没有启用流式时静默丢弃

    可以直接当 `synthesize_node(state, on_token=emit_token)` 的回调用。
    """
    if not text:
        return
    await emit_event({"type": "token", "text": text})
