"""
Self Grow — 统一协调 Agent API

三段式：
  POST /api/coordinator/chat   — 用户发送消息 → 主 agent 路由 + 并行派发 + （全部完成时）总结
  POST /api/coordinator/resume — 用户回答反问 → 直接接回对应子图继续（不重新路由）

**/chat 与 /resume 是流式（SSE）的**，响应不再是 JSON 而是 `text/event-stream`：

    data: {"type": "stage", "stage": "routing", "label": "正在理解你的意图…"}
    data: {"type": "stage", "stage": "domain_start", "domain": "habit", ...}
    data: {"type": "token", "text": "已"}
    data: {"type": "done", "thread_id": "...", "reply": "...", "interrupts": [...], ...}

前端的契约是：**`done` 事件里带着与改造前完全相同的字段**，
所以原来读 `resp.json()` 的地方只要改成「读流、等 done」，
拿到 done 之后的处理逻辑可以一字不改。

同一个 `thread_id` 同时只允许一个写请求（见 `_acquire_session`），冲突返回 409 ——
防止「连点 / 重试 / 多标签页」让子图重复执行（写库型工具会重复写入）。

已删除的两个端点（2026-09-17 清理，都是零调用方）：
  · `GET /stream/{thread_id}` —— 只发一个 done，**而且没挂鉴权**（任何人知道
    thread_id 就能查），又因为是 GET 所以浏览器带不了 token
  · `GET /status/{thread_id}` —— 调试用的编排状态快照，没有调用方
"""

import time
import uuid
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from routers.deps import get_current_user
from services.coordinator.state import CoordinatorState
from services.coordinator.graph import (
    run_coordinator_stream, resume_subgraph, finalize_record,
)
from services.coordinator.synthesize_node import synthesize_node
from services.coordinator.agents.ask_user_tool import DOMAIN_LABELS
from services.sse import (
    stream_events, sse_response, immediate_response,
    use_emitter, emit_stage, emit_token,
)

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/coordinator", tags=["coordinator"])

# ── 带 TTL 的编排状态存储 ─────────────────────────────
# 每条记录存储编排状态（pending_tasks/results/interrupts/completed_domains/final_reply）
# 子图会话历史由 LangGraph checkpointer 按 sub_thread_id 持久化。
_THREAD_TTL_SECONDS = 30 * 60  # 30 分钟

_thread_store: dict[str, dict] = {}


def _store_state(thread_id: str, state: CoordinatorState) -> None:
    """存储编排状态（带 TTL）"""
    _thread_store[thread_id] = {
        "state": state,
        "expires_at": time.time() + _THREAD_TTL_SECONDS,
    }


def _get_state(thread_id: str) -> CoordinatorState | None:
    """获取编排状态，过期则删除并返回 None"""
    entry = _thread_store.get(thread_id)
    if entry is None:
        return None
    if time.time() > entry["expires_at"]:
        del _thread_store[thread_id]
        return None
    # 活跃续期
    entry["expires_at"] = time.time() + _THREAD_TTL_SECONDS
    return entry["state"]


def _extract_domain(sub_thread_id: str) -> str:
    """从 sub_thread_id（格式 {main_uuid}:{domain}）提取域标识"""
    parts = sub_thread_id.split(":")
    if len(parts) < 2:
        raise HTTPException(status_code=400, detail="sub_thread_id 格式无效")
    return parts[-1]


# ── 会话级「处理中」锁（串行化同一 thread_id 的写请求）──────
#
# 为什么必须在**服务端**做（而不是只靠前端禁按钮）：
#   /chat 与 /resume 都是「读 state → await 子图 → 写 state」。
#   两次并发请求会在 await 点交错：两个都读到「该域还没完成」，
#   于是**子图被重复执行**。真实后果是写库型工具跑两次
#   （比如连点发送按钮 → 创建两个任务 / 打卡两次）。
#   实测证据：只有 1 个域时并发提交两次 → `results` 变成 2 条、
#   两个请求都拿到了最终回复。
#
# 前端加防抖/禁用按钮只能挡住「手滑连点」，挡不住重试、多标签页、
# 脚本调用 —— 所以服务端必须自己兜住。
#
# 用「逻辑锁」不是线程锁：请求处理是异步的，锁的持有期跨越 await，
# 只能用「集合标记 + 用后即除」。集合本身不做并发保护，但因为
# 判定与插入之间没有 await，事件循环里是原子的。
_inflight: set[str] = set()


def _acquire_session(thread_id: str) -> None:
    """占用会话；已被占用则抛 409

    ⚠️ 调用时机很关键：必须在**返回流式响应之前**占用
    （否则第二个请求要等流建立才知道冲突，拿不到干净的 409 状态码），
    而释放要放在 runner 的 `finally` 里 —— StreamingResponse 是「返回即开始」，
    在端点函数里释放等于业务还没跑就把锁丢了。
    """
    if thread_id in _inflight:
        raise HTTPException(
            status_code=409,
            detail="上一条内容还在处理中，请等它结束再提交",
        )
    _inflight.add(thread_id)


def _release_session(thread_id: str) -> None:
    """释放会话（幂等，可以重复调）"""
    _inflight.discard(thread_id)


class ChatRequest(BaseModel):
    message: str
    thread_id: Optional[str] = None


class ResumeRequest(BaseModel):
    thread_id: str
    sub_thread_id: str
    answer: str = ""
    # 用户点「跳过」时置 true：**不重新执行子图**，直接把这个域标记为已完成。
    # 必须有这个语义，否则「跳过一个提问」会让该域永远完不成 →
    # pending_domains 永远不是 completed 的子集 → 这条记录的总结**永远不会生成**。
    skip: bool = False


def _state_payload(thread_id: str, state: CoordinatorState, **overrides) -> dict:
    """组装编排结果（`done` 事件与历史版本 JSON 的字段完全一致）"""
    payload = {
        "thread_id": thread_id,
        "reply": state.get("final_reply", ""),
        "interrupts": state.get("interrupts", []),
        "results": state.get("results", []),
        "completed_domains": state.get("completed_domains", []),
        "pending_tasks": state.get("pending_tasks", []),
        "records": state.get("records", []),
    }
    payload.update(overrides)
    return payload


@router.post("/chat")
async def chat(request: ChatRequest, user=Depends(get_current_user)):
    """用户发送消息：主 agent 路由 → 并行派发子图 → （全部完成时）总结

    流式返回（SSE）。事件类型见模块 docstring；最后一条 `done` 里是完整结果。
    """
    thread_id = request.thread_id or str(uuid.uuid4())

    # 复用同一会话的历史记录（配合前端 sessionStorage 持久化 thread_id，实现"刷新不丢"）
    existing = _get_state(thread_id)
    records = existing.get("records", []) if existing else []

    state = CoordinatorState(
        user_id=user["id"],
        user_message=request.message,
        thread_id=thread_id,
        pending_tasks=[],
        results=[],
        interrupts=[],
        completed_domains=[],
        final_reply="",
        records=records,
    )
    _store_state(thread_id, state)

    _acquire_session(thread_id)

    async def runner(emit):
        try:
            # use_emitter 让深层代码（graph / agent / tool）也能推阶段事件
            with use_emitter(emit):
                await run_coordinator_stream(state)
            _store_state(thread_id, state)
            await emit({"type": "done", **_state_payload(thread_id, state)})
        finally:
            # 客户端中途断开时 stream_events 会 cancel 这个任务，
            # CancelledError 也会走 finally —— 不会把会话锁死
            _release_session(thread_id)

    return sse_response(stream_events(runner))


@router.post("/resume")
async def resume(request: ResumeRequest, user=Depends(get_current_user)):
    """用户回答反问：直接接回对应子图继续执行（不重新路由）

    流程：
    1. 校验编排状态与用户归属
    2. 解析 sub_thread_id → domain，调用 resume_subgraph 追加回答
       （`skip=True` 时跳过这步，直接把该域标记为已完成）
    3. 若子图又反问 → 返回新 interrupt；若完成 → 记录结果并标记域完成
    4. 所有域完成 → 触发 synthesize 生成最终总结

    ⚠️ 同一 thread_id 同时只允许一个写请求（见 `_acquire_session`），
    冲突时返回 **409**。这是为了防止「连点 / 重试 / 多标签页」导致
    子图被重复执行（写库型工具会重复写入）。
    """
    state = _get_state(request.thread_id)
    if not state:
        raise HTTPException(status_code=404, detail="对话不存在或已过期")

    if state.get("user_id") != user["id"]:
        raise HTTPException(status_code=403, detail="无权访问该对话")

    domain = _extract_domain(request.sub_thread_id)

    # 幂等保护：该域已完成且无待处理反问时，直接返回当前状态
    pending_interrupt_ids = {i.get("sub_thread_id") for i in state.get("interrupts", [])}
    if request.sub_thread_id not in pending_interrupt_ids and domain in set(state.get("completed_domains", [])):
        # 幂等命中：没有任何异步工作，发一个 done 就结束
        # （注意：这里**不占锁** —— 它不读改共享 state，也就没有竞态）
        return await immediate_response(
            _state_payload(request.thread_id, state, results=[])
        )

    # 占用会话；已被占用会抛 409（干净的 HTTP 状态码，前端能区分）
    _acquire_session(request.thread_id)

    async def runner(emit):
        # 字段与改造前的 JSON 返回**逐字一致**（interrupts / results 只含本次新增的，
        # 前端据此追加反问，不要"顺手"改成累计值），另外多带一个 pending_domains
        done_payload = None
        label = DOMAIN_LABELS.get(domain, domain)

        try:
            with use_emitter(emit):
                await emit_stage(
                    "domain_start",
                    f"{label}：已跳过这个提问" if request.skip
                    else f"{label}：处理你的回答…",
                    domain=domain,
                )

                if request.skip:
                    # 跳过：不重新执行子图（用户没提供信息，再问也问不出来），
                    # 只把该域标记成"已完成"，让编排还能走到总结那一步
                    new_results = [{
                        "domain": domain,
                        "message": f"{label}：已跳过",
                        "success": None,
                        "sub_thread_id": request.sub_thread_id,
                        "skipped": True,
                    }]
                    new_interrupts = []
                else:
                    try:
                        new_results, new_interrupts = await resume_subgraph(
                            domain, request.sub_thread_id, request.answer
                        )
                    except Exception as e:
                        log.error(f"恢复执行失败：{e}")
                        await emit({"type": "error", "message": f"恢复失败：{str(e)}"})
                        return

                # ── 下面这段「读 → 改 → 写」靠 _acquire_session 的会话锁保证
                #    不会与另一个写请求交错（它内部有 await emit_stage）──
                remaining_interrupts = [
                    i for i in state.get("interrupts", [])
                    if i.get("sub_thread_id") != request.sub_thread_id
                ]
                state["interrupts"] = remaining_interrupts + new_interrupts

                # 累积结果 + 更新完成域
                state["results"] = list(state.get("results", [])) + new_results
                completed = set(state.get("completed_domains", []))
                if not new_interrupts:
                    completed.add(domain)
                state["completed_domains"] = list(completed)

                # 判断是否所有域都完成 → 阶段三总结（这一步逐 token 推给前端）
                pending_domains = {t["domain"] for t in state.get("pending_tasks", [])}
                if pending_domains and pending_domains.issubset(completed):
                    await emit_stage("synthesize", "正在整理回复…")
                    syn = await synthesize_node(state, on_token=emit_token)
                    state["final_reply"] = syn.get("final_reply", "")
                    # 三阶段走完 → 压入近 5 条历史
                    finalize_record(state)
                else:
                    state["final_reply"] = ""

                if new_interrupts:
                    await emit_stage("domain_ask", f"{label}：还需要补充信息", domain=domain)
                else:
                    await emit_stage("domain_done", f"{label}：已完成", domain=domain)

                _store_state(request.thread_id, state)
                done_payload = _state_payload(
                    request.thread_id, state,
                    interrupts=new_interrupts,
                    results=new_results,
                    pending_domains=list(pending_domains),
                )

            # 出错时上面已经发过 error 事件（前端把 error 当终止信号），不再补 done
            if done_payload is not None:
                await emit({"type": "done", **done_payload})
        finally:
            _release_session(request.thread_id)

    return sse_response(stream_events(runner))


# 注：这里原来有个 `GET /status/{thread_id}`（查询编排状态），
# 已于 2026-09-17 删除 —— 全项目零调用方。想看编排过程有更好的办法：
# `/chat` 的 SSE 流本身就是完整的阶段回放（routing → domain_start → tool →
# synthesize → token），比读一份内存快照直观。要排查内存态就打日志：
# `services/coordinator/graph.py` 里 `_thread_store` 的读写都有 log。
