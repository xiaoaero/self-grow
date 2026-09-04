"""
Self Grow — 统一协调 Agent API

三段式：
  POST /api/coordinator/chat   — 用户发送消息 → 主 agent 路由 + 并行派发 + （全部完成时）总结
  POST /api/coordinator/resume — 用户回答反问 → 直接接回对应子图继续（不重新路由）
  GET  /api/coordinator/status/{thread_id} — 查询对话编排状态
  GET  /api/coordinator/stream/{thread_id}  — SSE（占位）
"""

import json
import time
import uuid
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from routers.deps import get_current_user
from services.coordinator.state import CoordinatorState
from services.coordinator.graph import run_coordinator, resume_subgraph, finalize_record
from services.coordinator.synthesize_node import synthesize_node

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


class ChatRequest(BaseModel):
    message: str
    thread_id: Optional[str] = None


class ResumeRequest(BaseModel):
    thread_id: str
    sub_thread_id: str
    answer: str


@router.post("/chat")
async def chat(request: ChatRequest, user=Depends(get_current_user)):
    """用户发送消息：主 agent 路由 → 并行派发子图 → （全部完成时）总结"""
    thread_id = request.thread_id or str(uuid.uuid4())

    # 复用同一会话的历史记录（配合前端 sessionStorage 持久化 thread_id，实现"刷新不丢"）
    existing = _get_state(thread_id)
    records = existing.get("records", []) if existing else []

    state = CoordinatorState(
        user_id=user["id"],
        user_message=request.message,
        thread_id=thread_id,
        messages=[],
        pending_tasks=[],
        results=[],
        interrupts=[],
        completed_domains=[],
        final_reply="",
        records=records,
    )
    _store_state(thread_id, state)

    try:
        state = await run_coordinator(state)
    except Exception as e:
        log.error(f"主编排执行失败：{e}")
        raise HTTPException(status_code=500, detail=f"执行失败：{str(e)}")

    _store_state(thread_id, state)

    return {
        "thread_id": thread_id,
        "reply": state.get("final_reply", ""),
        "interrupts": state.get("interrupts", []),
        "results": state.get("results", []),
        "completed_domains": state.get("completed_domains", []),
        "pending_tasks": state.get("pending_tasks", []),
        "records": state.get("records", []),
    }


@router.post("/resume")
async def resume(request: ResumeRequest, user=Depends(get_current_user)):
    """用户回答反问：直接接回对应子图继续执行（不重新路由）

    流程：
    1. 校验编排状态与用户归属
    2. 解析 sub_thread_id → domain，调用 resume_subgraph 追加回答
    3. 若子图又反问 → 返回新 interrupt；若完成 → 记录结果并标记域完成
    4. 所有域完成 → 触发 synthesize 生成最终总结
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
        return {
            "thread_id": request.thread_id,
            "reply": state.get("final_reply", ""),
            "interrupts": state.get("interrupts", []),
            "results": [],
            "completed_domains": state.get("completed_domains", []),
        }

    try:
        new_results, new_interrupts = await resume_subgraph(domain, request.sub_thread_id, request.answer)
    except Exception as e:
        log.error(f"恢复执行失败：{e}")
        raise HTTPException(status_code=500, detail=f"恢复失败：{str(e)}")

    # 移除该子图旧的 interrupt，追加新 interrupt（其它域的反问保留）
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

    # 判断是否所有域都完成 → 阶段三总结
    pending_domains = {t["domain"] for t in state.get("pending_tasks", [])}
    if pending_domains and pending_domains.issubset(completed):
        syn = await synthesize_node(state)
        state["final_reply"] = syn.get("final_reply", "")
        # 三阶段走完 → 压入近 5 条历史
        finalize_record(state)
    else:
        state["final_reply"] = ""

    _store_state(request.thread_id, state)

    return {
        "thread_id": request.thread_id,
        "reply": state.get("final_reply", ""),
        "interrupts": new_interrupts,
        "results": new_results,
        "completed_domains": list(completed),
        "pending_domains": list(pending_domains),
    }


@router.get("/status/{thread_id}")
async def get_status(thread_id: str, user=Depends(get_current_user)):
    """查询对话编排状态"""
    state = _get_state(thread_id)
    if not state:
        raise HTTPException(status_code=404, detail="对话不存在或已过期")

    if state.get("user_id") != user["id"]:
        raise HTTPException(status_code=403, detail="无权访问该对话")

    return {
        "thread_id": thread_id,
        "pending_tasks": state.get("pending_tasks", []),
        "completed_domains": state.get("completed_domains", []),
        "results": state.get("results", []),
        "interrupts": state.get("interrupts", []),
        "final_reply": state.get("final_reply", ""),
    }


@router.get("/stream/{thread_id}")
async def stream_events(thread_id: str):
    """SSE 流式推送事件（占位）"""
    async def event_generator():
        state = _get_state(thread_id)
        if state:
            yield f"data: {json.dumps({'type': 'done', 'thread_id': thread_id})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
    )
