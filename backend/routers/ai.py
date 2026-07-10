"""
Self Grow — AI 聊天 API 路由
"""

from fastapi import APIRouter, HTTPException, Depends

from schemas.api import ChatRequest, ChatResponse
from services.ai_service import call_ai

router = APIRouter()


@router.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """代理 AI 请求，支持 Tool Use"""
    result = await call_ai(req.messages, req.tree_state)
    if "tool_calls" in result:
        return ChatResponse(tool_calls=result["tool_calls"])
    return ChatResponse(content=result.get("content", ""))