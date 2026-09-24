"""
Self Grow — 技能树 AI 编辑 Agent 节点

提供 agent_node 工厂，构建 LLM + Tools 循环。
"""

import json
import logging

from langchain_core.messages import (
    SystemMessage,
    ToolMessage,
    AIMessage,
    HumanMessage,
)

from services.skill_tree_ai.prompts import (
    SKILL_TREE_AI_SYSTEM_PROMPT,
    build_tree_state_prompt,
)
from services.skill_tree_ai.state import SkillTreeChatState
from services.sse import emit_stage
from services.tool_args import coerce_json_args

log = logging.getLogger(__name__)

# 安全上限
MAX_ITERS = 10
MAX_ASK_ROUNDS = 3
MAX_CONTEXT_ROUNDS = 5      # 上下文只带最近 5 个「来回」（用户要求）


def _truncate_messages(messages: list, max_rounds: int = MAX_CONTEXT_ROUNDS) -> list:
    """只保留最近 `max_rounds` 个「来回」

    一个来回 = 从**一条 HumanMessage** 开始，到下一条 HumanMessage 之前，
    中间含 AIMessage / AIMessage(tool_calls) / ToolMessage。

    ⚠️ 必须按**轮**切，不能按「条数」切：一轮 ReAct 里会有
    `AIMessage(tool_calls)` + N 条 `ToolMessage` + `AIMessage`，
    按条数切很容易切在 tool_calls 和它的 ToolMessage 之间 →
    产生**孤儿 ToolMessage** → LLM API 直接 400。
    切点落在 HumanMessage 上天然安全：它前面那一轮的工具消息已经配完对了。

    （以前的实现是「保留首条 + 最近 10 条」，两个毛病：
      ① 10 **条**不是 10 轮，工具消息会把窗口吃光，实际只带 1~2 个来回；
      ② 把最早那条 HumanMessage 硬塞回开头，会出现「第 1 轮的问题 + 最新一轮的回答」
         这种错位上下文。现在按轮切，不做这个拼接。）
    """
    msgs = list(messages or [])
    human_pos = [i for i, m in enumerate(msgs) if isinstance(m, HumanMessage)]
    if len(human_pos) <= max_rounds:
        return msgs
    start = human_pos[-max_rounds]
    # 防御：切点理论上一定是 HumanMessage，万一不是就往后推到非 ToolMessage
    while start < len(msgs) and isinstance(msgs[start], ToolMessage):
        start += 1
    return msgs[start:]


def make_agent_node(tools: list, llm_factory):
    """构建技能树 AI 编辑 agent 节点。

    Args:
        tools: 工具列表（@tool 函数）
        llm_factory: `state -> ChatOpenAI` —— **接收 state**（不是无参）。
            必须能拿到 `state["user_id"]`，否则 `get_llm()` 会退化成
            「恒定读 user_id=1 的模型配置」（见 graph.py 里的说明）。

    Returns:
        agent_node(state) async 函数
    """
    tools_by_name = {t.name: t for t in tools}

    async def agent_node(state: SkillTreeChatState):
        # 传入 state：工厂要用它读**当前用户**在「用户中心 → 模型信息」里
        # 启用的模型配置（见 graph.py 里 llm_factory 的说明）
        llm = llm_factory(state)
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

        # 想核对「模型到底收到了什么」时：把 SELF_GROW_LOG_LEVEL 调成 DEBUG 再重启，
        # 这里会把两条 SystemMessage 的**原文**打出来（平时不打印，避免刷日志）。
        if log.isEnabledFor(logging.DEBUG):
            log.debug("系统提示词（%d 字）：\n%s", len(SKILL_TREE_AI_SYSTEM_PROMPT),
                      SKILL_TREE_AI_SYSTEM_PROMPT)
            log.debug("当前树状态提示词（%d 字）：\n%s", len(tree_prompt), tree_prompt)

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
                        # ⚠️ 先做参数容错：模型常把 list/dict 参数传成 JSON 字符串，
                        #    不解析的话这里必抛 ValidationError（工具永远执行不了，
                        #    模型还会反复重试）。详见 services/tool_args.py
                        safe_args = coerce_json_args(tool_fn, args)
                        result = tool_fn.invoke({**safe_args, "state": state})
                    except Exception as e:
                        log.error(f"工具 {name} 执行异常：{e}")
                        result = {"success": False, "message": f"工具执行异常：{e}"}

                    # 处理需要确认的操作
                    if isinstance(result, dict) and result.get("needs_confirmation"):
                        pending_confirmation = {
                            "tool": name,
                            # 回放确认时要用**解析后**的参数，否则确认后还是跑不起来
                            "args": safe_args,
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
