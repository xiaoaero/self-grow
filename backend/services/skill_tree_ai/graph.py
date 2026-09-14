"""
Self Grow — 技能树 AI 编辑图

编译 LangGraph StateGraph，提供：
- build_skill_tree_chat_graph(): 构建图
- run_skill_tree_chat(): 一次性运行
- resume_skill_tree_chat(): 恢复对话（用于用户确认/回答）
"""

import json
import logging
import uuid

from langchain_core.messages import HumanMessage
from langgraph.graph import StateGraph, END

from services.coordinator.checkpointer import get_checkpointer
from services.llm import get_llm
from services.skill_tree_ai.state import SkillTreeChatState
from services.skill_tree_ai.node import make_agent_node
from services.skill_tree_ai.tools import SKILL_TREE_AI_TOOLS

log = logging.getLogger(__name__)


def build_skill_tree_chat_graph():
    """构建并编译技能树 AI 编辑图。"""
    graph = StateGraph(SkillTreeChatState)

    agent_node = make_agent_node(
        tools=SKILL_TREE_AI_TOOLS,
        llm_factory=lambda: get_llm(temperature=0.3),
    )

    graph.add_node("agent", agent_node)
    graph.set_entry_point("agent")
    graph.add_edge("agent", END)

    return graph.compile(checkpointer=get_checkpointer())


# 全局单例：避免每次请求重新编译
_skill_tree_chat_graph = None


def get_skill_tree_chat_graph():
    """获取编译后的图单例。"""
    global _skill_tree_chat_graph
    if _skill_tree_chat_graph is None:
        _skill_tree_chat_graph = build_skill_tree_chat_graph()
    return _skill_tree_chat_graph


async def run_skill_tree_chat(
    tree: dict,
    user_message: str,
    user_id: int,
    tree_id: str,
    selected_node_ids: list[str] | None = None,
    thread_id: str = None,
) -> dict:
    """启动一次新的 AI 编辑对话。"""
    graph = get_skill_tree_chat_graph()
    # 每次新会话生成独立 thread_id（编入 user_id，避免跨用户会话串号）；
    # 同一会话由前端回传 thread_id 续接
    thread_id = thread_id or f"stc_{user_id}_{uuid.uuid4().hex[:12]}"
    config = {"configurable": {"thread_id": thread_id}}

    initial_state = {
        "user_id": user_id,
        "tree_id": tree_id,
        "tree": tree,
        "selected_node_ids": list(selected_node_ids or []),
        "messages": [HumanMessage(content=user_message)],
        "diffs": [],
        "executed_tools": [],
        "reply": None,
        "pending_confirmation": None,
        "ask_rounds": 0,
    }

    result = await graph.ainvoke(initial_state, config=config)
    return _format_result(result, thread_id)


async def resume_skill_tree_chat(
    thread_id: str,
    user_message: str,
    confirm: bool = False,
    tree: dict = None,
) -> dict:
    """恢复对话：用户回答反问或确认操作。

    Args:
        tree: 前端当前的树状态（可选）。传入时会覆盖 checkpoint 里的旧树，
              否则 AI 会基于旧快照继续编辑，把用户期间的手动改动覆盖掉。
    """
    graph = get_skill_tree_chat_graph()
    config = {"configurable": {"thread_id": thread_id}}

    # 如果有待确认的操作，先注入确认状态
    state = await graph.aget_state(config)
    pending = state.values.get("pending_confirmation") if state else None

    if pending and confirm:
        # 把「操作 + 原始参数」一起回灌：不带上参数，LLM 重新调用时可能
        # 生成与用户确认内容不一致的参数（确认的是删 A，结果删了 B）
        args_text = json.dumps(pending.get("args") or {}, ensure_ascii=False)
        content = (
            f"[系统] 用户已确认执行「{pending['tool']}」，原始参数：{args_text}。"
            f"请原样使用这些参数并附加 confirm=True 重新调用该工具。\n{user_message}"
        )
    else:
        content = user_message

    # tree 是普通字段（非 operator.add），放进 input 即整体覆盖
    invoke_input = {"messages": [HumanMessage(content=content)]}
    if tree is not None:
        invoke_input["tree"] = tree

    result = await graph.ainvoke(invoke_input, config=config)
    return _format_result(result, thread_id)


def _format_result(result: dict, thread_id: str) -> dict:
    """格式化图为前端可用的响应。"""
    reply = result.get("reply")
    if not reply:
        # 兜底：工具执行成功但没有 send_reply 时，用工具结果拼一个摘要
        msgs = [t.get("message", "") for t in (result.get("executed_tools") or []) if t.get("message")]
        reply = "\n".join(msgs) if msgs else "操作已完成。"
    return {
        "thread_id": thread_id,
        "reply": reply,
        "diffs": result.get("diffs", []),
        "executed_tools": result.get("executed_tools", []),
        "pending_confirmation": result.get("pending_confirmation"),
        "tree": result.get("tree", {}),
    }
