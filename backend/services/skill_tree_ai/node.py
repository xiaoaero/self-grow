"""
Self Grow — 技能树 AI 编辑 Agent 节点

提供 agent_node 工厂，构建 LLM + Tools 循环。
"""

import json
import logging

from langchain_core.messages import (
    HumanMessage,
    SystemMessage,
    ToolMessage,
    AIMessage,
)

from services.skill_tree_ai.prompts import (
    SKILL_TREE_AI_SYSTEM_PROMPT,
    build_tree_state_prompt,
)
from services.skill_tree_ai.state import SkillTreeChatState
from services.sse import emit_stage

log = logging.getLogger(__name__)

# 安全上限
MAX_ITERS = 10
MAX_ASK_ROUNDS = 3


def _truncate_messages(messages: list, max_recent: int = 10) -> list:
    """截断消息历史，保留首条 + 最近若干条。

    截断边界必须落在「完整对话轮」上：若切在 AIMessage(tool_calls) 与其
    ToolMessage 之间，会产生孤儿 ToolMessage，导致 LLM API 返回 400。
    因此起始位置向后推进，直到不是 ToolMessage 为止。
    """
    if len(messages) <= max_recent + 1:
        return list(messages)
    start = len(messages) - max_recent
    while start < len(messages) and isinstance(messages[start], ToolMessage):
        start += 1
    return [messages[0]] + messages[start:]


def make_agent_node(tools: list, llm_factory):
    """构建技能树 AI 编辑 agent 节点。

    Args:
        tools: 工具列表（@tool 函数）
        llm_factory: 返回 ChatOpenAI 实例的可调用对象

    Returns:
        agent_node(state) async 函数
    """
    tools_by_name = {t.name: t for t in tools}

    async def agent_node(state: SkillTreeChatState):
        llm = llm_factory()
        llm_with_tools = llm.bind_tools(tools)

        # 截断消息历史，保留首条 + 最近若干条（保持 tool_calls 配对完整）
        messages = _truncate_messages(list(state.get("messages", [])))

        # 每次 agent 节点执行时动态注入当前树状态
        tree_prompt = build_tree_state_prompt(
            state.get("tree", {}),
            state.get("selected_node_ids", []),
        )

        full_messages = [
            SystemMessage(content=SKILL_TREE_AI_SYSTEM_PROMPT),
            SystemMessage(content=tree_prompt),
        ] + messages

        ask_rounds = int(state.get("ask_rounds", 0) or 0)

        for i in range(MAX_ITERS):
            # 阶段事件（不流式时是空操作）：一个 ReAct 循环里 LLM 会被调用多次，
            # 把轮次报出来，用户才知道「它还在干活」而不是卡住了
            await emit_stage("thinking", "正在分析…" if i == 0 else f"第 {i + 1} 轮推理…")
            response = await llm_with_tools.ainvoke(full_messages)

            # 1. LLM 调用工具
            if response.tool_calls:
                new_messages = [response]
                reply_text = None
                pending_confirmation = None
                diffs = []
                executed = []

                for tc in response.tool_calls:
                    name = tc["name"]
                    args = tc.get("args") or {}

                    tool_fn = tools_by_name.get(name)
                    if not tool_fn:
                        new_messages.append(ToolMessage(
                            content=f"未知工具：{name}",
                            tool_call_id=tc["id"],
                        ))
                        continue

                    await emit_stage("tool", f"正在执行 {name}", tool=name)
                    try:
                        # 手动注入 state（InjectedState 已把 state 从工具 schema 中排除）
                        result = tool_fn.invoke({**args, "state": state})
                    except Exception as e:
                        log.error(f"工具 {name} 执行异常：{e}")
                        result = {"success": False, "message": f"工具执行异常：{e}"}

                    # 处理需要确认的操作
                    if isinstance(result, dict) and result.get("needs_confirmation"):
                        pending_confirmation = {
                            "tool": name,
                            "args": args,
                            "message": result.get("message", "请确认此操作"),
                            "confirmed": False,
                        }
                        await emit_stage(
                            "confirm", result.get("message", "请确认此操作"), tool=name
                        )
                        new_messages.append(ToolMessage(
                            content=json.dumps({
                                "success": False,
                                "message": result.get("message", "请确认此操作"),
                            }, ensure_ascii=False),
                            tool_call_id=tc["id"],
                        ))
                        # 返回确认请求，中断本轮循环
                        return {
                            "messages": new_messages,
                            "reply": result.get("message", "请确认此操作"),
                            "pending_confirmation": pending_confirmation,
                            "diffs": [],
                            "executed_tools": [{
                                "tool": name,
                                "args": args,
                                "status": "needs_confirmation",
                            }],
                            "tree": state["tree"],
                        }

                    # 处理 send_reply 工具
                    if name == "send_reply" and isinstance(result, dict) and result.get("reply"):
                        reply_text = result["reply"]

                    # 收集 diff
                    if isinstance(result, dict) and result.get("diff"):
                        diffs.append(result["diff"])

                    executed.append({
                        "tool": name,
                        "args": args,
                        "success": result.get("success", False) if isinstance(result, dict) else False,
                        "message": result.get("message", "") if isinstance(result, dict) else str(result),
                    })

                    new_messages.append(ToolMessage(
                        content=json.dumps(result, ensure_ascii=False, default=str),
                        tool_call_id=tc["id"],
                    ))

                # 如果本次工具调用产生了 diffs 或 reply，结束本轮
                if reply_text or diffs:
                    return {
                        "messages": new_messages,
                        "reply": reply_text,
                        "diffs": diffs,
                        "executed_tools": executed,
                        "pending_confirmation": None,
                        "tree": state["tree"],
                    }
                # 否则继续循环，让 LLM 根据工具结果继续决策
                full_messages = full_messages + new_messages
                continue

            # 2. LLM 输出纯文本
            content = response.content or ""
            return {
                "messages": [response],
                "reply": content,
                "diffs": [],
                "executed_tools": [],
                "pending_confirmation": None,
                "tree": state["tree"],
            }

        # 循环用尽
        return {
            "messages": [],
            "reply": "处理轮次超限，请稍后重试",
            "diffs": [],
            "executed_tools": [],
            "pending_confirmation": None,
            "tree": state["tree"],
        }

    return agent_node
