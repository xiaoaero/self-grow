"""
Self Grow — AI 聊天 API 路由（已下线）

⚠️ 本路由已于 2026-09-03 停用，不再在 main.py 注册。
原因：
1. 无用户鉴权（全后端唯一没有 Depends(get_current_user) 的 AI 端点）
2. 功能已被 /api/skill-trees/{tree_id}/chat（LangGraph 版）完全替代
   —— 见 routers/skill_tree_ai.py + services/skill_tree_ai/
文件保留仅作历史参考。
"""

from fastapi import APIRouter, HTTPException, Depends

from schemas.api import ChatRequest, ChatResponse
from services.ai_service import call_ai

router = APIRouter()


@router.post("/api/chat", response_model=ChatResponse, include_in_schema=False, deprecated=True)
async def chat(req: ChatRequest):
    """[已废弃] 代理 AI 请求，支持 Tool Use"""
    result = await call_ai(req.messages, req.tree_state)
    if "tool_calls" in result:
        return ChatResponse(tool_calls=result["tool_calls"])
    return ChatResponse(content=result.get("content", ""))