"""
Self Grow — 技能树 AI 编辑 API 路由

提供新的 LangGraph 驱动 AI 编辑接口，替代旧的 /api/chat。

**两个对话端点都是流式（SSE）**：

    POST /api/skill-trees/{tree_id}/chat          — 发起对话
    POST /api/skill-trees/{tree_id}/chat/resume   — 回答反问 / 确认操作

事件格式与协调 Agent 一致（见 `services/sse.py`）：

    data: {"type": "stage", "stage": "thinking", "label": "第 2 轮推理…"}
    data: {"type": "stage", "stage": "tool", "label": "正在执行 update_node", "tool": "..."}
    data: {"type": "done", ...与改造前完全相同的字段...}

## 为什么这里只有「阶段事件」，没有「逐 token」

技能树 AI 的回复走的是 **`send_reply` 工具**（LLM 把回复文本当作工具参数生成），
以及工具执行结果拼装；都不是「一条纯文本流」，逐 token 拿不到可直接显示的内容。
所以这里给的是**工具级进度**（第几轮推理、正在执行哪个工具、是否需要确认），
用户能看到"它在干什么"，而不是一个不动的转圈。

原来那个 `GET /{tree_id}/chat/stream` 是**占位实现**（只把最终 reply 一次性塞进去，
没有任何增量），已删除并用上面两个 POST 端点取代 —— 顺带解决了
「GET 端点浏览器没法带 Authorization 头」的问题。
"""

import logging

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field

from db.skill_tree import get_skill_tree_by_tree_id
from routers.deps import require_admin
from services.skill_tree_ai import run_skill_tree_chat, resume_skill_tree_chat
from services.sse import stream_events, sse_response, use_emitter

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
    """启动或继续技能树 AI 编辑对话（流式 SSE）。仅管理员可用。

    注意：图是**模块级单例**（编译一次复用），没法在编译时把每个请求的事件
    回调烘进去，所以这里靠 `use_emitter` 把发射器放进 ContextVar，
    `node.py` 里就能透明地推阶段事件 —— asyncio 任务会复制上下文，
    因此并发请求之间不会串。
    """
    # 校验用户是否拥有该技能树
    tree_record = get_skill_tree_by_tree_id(tree_id, user["id"])
    if not tree_record:
        raise HTTPException(status_code=404, detail="技能树不存在")

    async def runner(emit):
        with use_emitter(emit):
            result = await run_skill_tree_chat(
                tree=req.tree,
                user_message=req.message,
                user_id=user["id"],
                tree_id=tree_id,
                selected_node_ids=req.selected_node_ids,
                thread_id=req.thread_id,
            )
        await emit({"type": "done", **result})

    # 注意：这里是「流已经开始之后」才可能失败，所以异常由 stream_events 兜住
    # 并发成 error 事件（而不是 500）—— 前端把 error 当终止信号处理
    return sse_response(stream_events(runner))


@router.post("/{tree_id}/chat/resume")
async def resume(
    tree_id: str,
    req: ResumeRequest,
    user=Depends(require_admin),
):
    """恢复对话：用户回答反问或确认操作（流式 SSE）。仅管理员可用。"""
    # 校验归属
    tree_record = get_skill_tree_by_tree_id(tree_id, user["id"])
    if not tree_record:
        raise HTTPException(status_code=404, detail="技能树不存在")

    async def runner(emit):
        with use_emitter(emit):
            result = await resume_skill_tree_chat(
                thread_id=req.thread_id,
                user_message=req.message,
                confirm=req.confirm,
                tree=req.tree,
            )
        await emit({"type": "done", **result})

    return sse_response(stream_events(runner))


# 说明：原来这里有一个 `GET /{tree_id}/chat/stream` 的**占位**端点
# （只 yield 一次 aget_state 的结果 + 一个 done，没有任何增量事件）。
# 它已随本次改造删除，原因有两个：
#   1. 上面两个 POST 端点现在本身就是流式的，功能完全覆盖
#   2. 它是 GET —— 浏览器的 EventSource 带不了 Authorization 头，
#      前端根本没法用它（只能裸奔或走 query 参数传 token，两种都不可取）
# 需要回看旧实现可以 `git log -p -- backend/routers/skill_tree_ai.py`。
