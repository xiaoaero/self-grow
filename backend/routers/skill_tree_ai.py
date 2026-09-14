"""
Self Grow — 技能树 AI 编辑 API 路由

提供新的 LangGraph 驱动 AI 编辑接口，替代旧的 /api/chat。
"""

import json
import logging

from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from db.skill_tree import get_skill_tree_by_tree_id
from routers.deps import get_current_user, require_admin
from services.skill_tree_ai import run_skill_tree_chat, resume_skill_tree_chat
from services.skill_tree_ai.graph import get_skill_tree_chat_graph

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/skill-trees", tags=["skill-tree-ai"])


class ChatRequest(BaseModel):
    tree: dict = Field(..., description="当前树状态 {name, description, nodes, connections}")
    message: str = Field(..., description="用户输入")
    selected_node_ids: list[str] = Field(default_factory=list, description="当前选中的节点 ID")
    thread_id: str | None = Field(None, description="会话 ID，首次为空")


class ResumeRequest(BaseModel):
    thread_id: str = Field(..., description="会话 ID")
    message: str = Field(default="", description="用户输入")
    confirm: bool = Field(default=False, description="是否确认待处理的操作")
    tree: dict | None = Field(
        None,
        description="当前树状态（可选）。传入时用它刷新会话中的树，"
                    "避免 AI 基于旧的 checkpoint 快照继续编辑，覆盖掉用户手动改动。",
    )


@router.post("/{tree_id}/chat")
async def chat(
    tree_id: str,
    req: ChatRequest,
    user=Depends(require_admin),
):
    """启动或继续技能树 AI 编辑对话（非流式）。仅管理员可用。"""
    # 校验用户是否拥有该技能树
    tree_record = get_skill_tree_by_tree_id(tree_id, user["id"])
    if not tree_record:
        raise HTTPException(status_code=404, detail="技能树不存在")

    try:
        result = await run_skill_tree_chat(
            tree=req.tree,
            user_message=req.message,
            user_id=user["id"],
            tree_id=tree_id,
            selected_node_ids=req.selected_node_ids,
            thread_id=req.thread_id,
        )
        return result
    except Exception as e:
        log.exception("技能树 AI 对话失败")
        raise HTTPException(status_code=500, detail=f"AI 对话失败: {str(e)}")


@router.post("/{tree_id}/chat/resume")
async def resume(
    tree_id: str,
    req: ResumeRequest,
    user=Depends(require_admin),
):
    """恢复对话：用户回答反问或确认操作。仅管理员可用。"""
    # 校验归属
    tree_record = get_skill_tree_by_tree_id(tree_id, user["id"])
    if not tree_record:
        raise HTTPException(status_code=404, detail="技能树不存在")

    try:
        result = await resume_skill_tree_chat(
            thread_id=req.thread_id,
            user_message=req.message,
            confirm=req.confirm,
            tree=req.tree,
        )
        return result
    except Exception as e:
        log.exception("技能树 AI 对话恢复失败")
        raise HTTPException(status_code=500, detail=f"恢复失败: {str(e)}")


@router.get("/{tree_id}/chat/stream")
async def stream_chat(
    tree_id: str,
    thread_id: str = Query(..., description="会话 ID"),
    user=Depends(get_current_user),
):
    """SSE 流式推送 AI 编辑事件（占位实现）。"""
    # 校验归属
    tree_record = get_skill_tree_by_tree_id(tree_id, user["id"])
    if not tree_record:
        raise HTTPException(status_code=404, detail="技能树不存在")

    async def event_generator():
        # TODO: 接入 graph.astream_events 实现真正的流式事件
        state = await get_skill_tree_chat_graph().aget_state(
            {"configurable": {"thread_id": thread_id}}
        )
        if state:
            yield f"data: {json.dumps({'type': 'state', 'reply': state.values.get('reply', '')}, ensure_ascii=False)}\n\n"
        yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
    )
