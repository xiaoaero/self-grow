"""
Self Grow — 子 agent 共享基座

提供 make_agent_node 工厂，统一构建「LLM + Tools 循环 + ask_user 反问」的 agent 节点。
所有域子 agent 复用此基座，仅传入 tools / domain / domain_label / system_prompt。

核心机制（对应三段式中的「第二阶段：子 agent 反问与执行」）：
- LLM 决定调用业务工具 → 执行 → 成功则返回 result
- LLM 调用 ask_user → 反问：把问题与工具结果写入 messages 持久化，
  返回 result.needs_user=True（子图正常结束，不挂起）
- 用户回答后，dispatch/resume 层把回答作为 HumanMessage 追加回该子图的
  checkpoint，重新 ainvoke，LLM 在完整上下文中接着调用业务工具

子 agent 上下文窗口（一条记录内）：
- 反问最多 MAX_ASK_ROUNDS 轮，超限后移除 ask_user 工具，逼 LLM 用已有信息
  执行（默认值）或输出最终回复（放弃），实现「超限降级」
- 消息历史读取时做窗口截断，保留首条 instruction + 最近几轮，防膨胀

相比 LangGraph interrupt() 方案的优势：
- 反问问题作为普通消息持久化在 checkpoint，resume 时不丢失、不重问
- 无挂起状态，「跳过/放弃」零成本
- 单一状态源（checkpointer），不依赖额外线程存储
"""

import asyncio
import json
import logging
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

from services.coordinator.agents.ask_user_tool import ask_user
from services.tool_args import coerce_json_args
from services.sse import emit_stage

log = logging.getLogger(__name__)

# 防止 LLM 无限循环的安全上限（限制业务工具失败重试的轮数）
MAX_ITERS = 8

# 子 agent 反问次数上限（一条记录内最多 3 轮输入与反问）
MAX_ASK_ROUNDS = 3

# 消息窗口：首条 instruction(1) + 最近 MAX_ASK_ROUNDS 轮 × 每轮约 3 条
# （AIMessage 反问 + ToolMessage 结果 + HumanMessage 回答）= 10
MAX_HISTORY = 1 + MAX_ASK_ROUNDS * 3


def make_agent_node(tools, domain: str, domain_label: str, system_prompt: str):
    """构建 agent 节点函数

    Args:
        tools: 业务工具列表（langchain @tool 函数，不含 ask_user）
        domain: 域标识（action/query/goal/task/habit/reward）
        domain_label: 前端显示标签（如 "🏃 行动记录"）
        system_prompt: 系统 prompt 文本

    Returns:
        agent_node(state) async 函数，用于 StateGraph 节点
    """
    # ask_user 是公共反问工具，所有子 agent 统一接入
    all_tools = list(tools) + [ask_user]
    tools_by_name = {t.name: t for t in all_tools}

    async def agent_node(state):
        from services.llm import get_llm
        llm = get_llm(temperature=0.3, user_id=state.get("user_id", 0))

        # 消息历史（checkpointer 持久化），读取时做窗口截断
        messages = list(state.get("messages", []))
        if len(messages) > MAX_HISTORY:
            messages = messages[:1] + messages[-(MAX_HISTORY - 1):]

        ask_rounds = int(state.get("ask_rounds", 0) or 0)

        # 反问轮数满 → 移除 ask_user，逼 LLM 降级（用已有信息执行或输出最终回复放弃）
        if ask_rounds >= MAX_ASK_ROUNDS:
            active_tools = list(tools)
        else:
            active_tools = all_tools
        llm_with_tools = llm.bind_tools(active_tools)

        full = [SystemMessage(content=system_prompt)] + messages

        for _ in range(MAX_ITERS):
            response = await llm_with_tools.ainvoke(full)

            # 1. LLM 决定调用工具
            if response.tool_calls:
                new_messages = [response]
                for tc in response.tool_calls:
                    name = tc["name"]
                    args = tc.get("args") or {}

                    # 1a. 反问工具
                    if name == "ask_user":
                        # 保险：轮数已满仍被反问 → 强制降级（正常情况 ask_user 已被移除）
                        if ask_rounds >= MAX_ASK_ROUNDS:
                            result = {
                                "success": False,
                                "message": "信息不足，本次放弃，请重新发起并补充完整信息",
                                "domain": domain,
                            }
                            new_messages.append(ToolMessage(
                                content=json.dumps(result, ensure_ascii=False),
                                tool_call_id=tc["id"],
                            ))
                            return {
                                "messages": new_messages,
                                "result": result,
                                "ask_rounds": ask_rounds,
                            }

                        ask_rounds += 1
                        result = {
                            "needs_user": True,
                            "question": args.get("question", "请补充信息"),
                            "options": args.get("options") or [],
                            "domain": args.get("domain") or domain,
                            "domain_label": args.get("domain_label") or domain_label,
                        }
                        new_messages.append(ToolMessage(
                            content=json.dumps(result, ensure_ascii=False),
                            tool_call_id=tc["id"],
                        ))
                        return {
                            "messages": new_messages,
                            "result": result,
                            "ask_rounds": ask_rounds,
                        }

                    # 1b. 业务工具：注入 user_id 后执行
                    if "user_id" not in args or args["user_id"] is None:
                        args["user_id"] = state.get("user_id", 0)

                    tool_fn = tools_by_name.get(name)
                    if tool_fn:
                        # 推「正在执行 xxx」阶段事件（不流式时是空操作）。
                        # 注意必须在主协程里发，不能在 asyncio.to_thread 的线程里 ——
                        # ContextVar 在线程池里语义不保证
                        await emit_stage(
                            "tool",
                            f"{domain_label}：正在执行 {name}",
                            domain=domain, tool=name,
                        )
                        try:
                            # 工具是同步的（内部是同步 sqlite3），丢线程池避免阻塞事件循环
                            tool_result = await asyncio.to_thread(
                                tool_fn.invoke,
                                # 参数容错：模型常把 list/dict 传成 JSON 字符串，
                                # 不解析就是 ValidationError（详见 services/tool_args.py）
                                coerce_json_args(tool_fn, args),
                            )
                        except Exception as e:
                            log.error(f"工具 {name} 执行异常：{e}")
                            tool_result = {"success": False, "message": f"工具执行异常：{e}"}
                        new_messages.append(ToolMessage(
                            content=json.dumps(tool_result, ensure_ascii=False, default=str),
                            tool_call_id=tc["id"],
                        ))
                        # 业务工具成功 → 子图完成
                        if isinstance(tool_result, dict) and tool_result.get("success"):
                            return {
                                "messages": new_messages,
                                "result": tool_result,
                                "ask_rounds": ask_rounds,
                            }
                    else:
                        new_messages.append(ToolMessage(
                            content=f"未知工具：{name}",
                            tool_call_id=tc["id"],
                        ))

                # 工具未成功（或非成功类工具），拼回上下文继续循环让 LLM 决策
                full = full + new_messages
                continue

            # 2. LLM 输出纯文本（无 tool_calls）：视为最终回复
            content = response.content or ""
            return {
                "messages": [response],
                "result": {"message": content, "domain": domain},
                "ask_rounds": ask_rounds,
            }

        # 循环用尽仍未完成
        return {
            "messages": [],
            "result": {"message": "处理轮次超限，请稍后重试", "domain": domain},
            "ask_rounds": ask_rounds,
        }

    return agent_node


def build_subgraph(state_class, tools, domain: str, domain_label: str, system_prompt: str):
    """构建子图（单节点 StateGraph + 全局 checkpointer）

    Args:
        state_class: TypedDict 子图状态类（需含 ask_rounds 字段）
        tools: 业务工具列表
        domain: 域标识
        domain_label: 前端显示标签
        system_prompt: 系统 prompt

    Returns:
        编译后的 StateGraph（带 checkpointer，用于持久化消息历史）
    """
    from langgraph.graph import StateGraph, END
    from services.coordinator.checkpointer import get_checkpointer

    graph = StateGraph(state_class)
    graph.add_node("agent", make_agent_node(tools, domain, domain_label, system_prompt))
    graph.set_entry_point("agent")
    graph.add_edge("agent", END)
    return graph.compile(checkpointer=get_checkpointer())
