"""
Self Grow — 协调 Agent 主编排（三段式）

三段式流程：
  1. 主 agent 路由（router_node）：自然语言 → 决定启动哪些次 agent + 定制指令
  2. 子 agent 反问与执行（dispatch / resume）：并行派发各域子图，缺信息时子图
     通过 ask_user 工具反问，用户回答后「直接接回该子图上下文」继续 —— 不再重新路由
  3. 主 agent 总结（synthesize_node）：所有子图完成后整合生成最终回复

本模块只做编排，不再使用 LangGraph StateGraph（主流程是线性三段，无分支/循环，
LangGraph 的 operator.add 状态合并反而会引入跨轮累积问题）。子图的 ReAct 循环
与消息历史持久化由 agents/base.py + checkpointer 负责。
"""

import logging
import uuid
import asyncio
from langchain_core.messages import HumanMessage

from services.coordinator.router_node import router_node
from services.coordinator.synthesize_node import synthesize_node
from services.coordinator.agents import SUBGRAPH_BUILDERS

log = logging.getLogger(__name__)

# 主 agent 跨记录上下文：保留近 5 条记录
MAX_RECORDS = 5


def finalize_record(state: dict) -> dict:
    """三阶段走完（总结完成）后，把 {用户说的话, 主agent总结} 压入历史（FIFO 5）

    只在 final_reply 非空时压入 —— 有 pending 反问时 final_reply 为空，不压入，
    等价于「三阶段都走过一遍才算一条记录」。
    """
    summary = state.get("final_reply", "")
    if summary:
        records = list(state.get("records", []))
        records.append({
            "user_message": state.get("user_message", ""),
            "summary": summary,
        })
        state["records"] = records[-MAX_RECORDS:]
    return state


def _parse_agent_outcome(agent_result: dict, domain: str, sub_thread_id: str):
    """从子图 ainvoke 结果中提取 (results, interrupts)

    - 子图 result.needs_user=True → 反问（interrupt）
    - 否则 → 完成（result 带 message/success）
    """
    if not isinstance(agent_result, dict):
        return [], []

    result_field = agent_result.get("result")
    if isinstance(result_field, dict) and result_field.get("needs_user"):
        interrupt = {
            "id": str(uuid.uuid4()),
            "domain": result_field.get("domain") or domain,
            "sub_thread_id": sub_thread_id,
            "question": result_field.get("question", "请补充信息"),
            "options": result_field.get("options", []),
            "domain_label": result_field.get("domain_label", "🤖 AI 助手"),
        }
        return [], [interrupt]

    # 完成：提取 message / success
    message = ""
    success = None
    if isinstance(result_field, dict):
        message = result_field.get("message", "")
        success = result_field.get("success")

    return [{
        "domain": domain,
        "message": message,
        "success": success,
        "sub_thread_id": sub_thread_id,
    }], []


async def _run_one_subgraph(domain: str, instruction: str, user_id: int, main_thread_id: str):
    """首次执行单个子图，返回 (results, interrupts)"""
    builder = SUBGRAPH_BUILDERS.get(domain)
    if not builder:
        log.warning(f"未知域：{domain}")
        return [], []

    agent = builder()
    sub_thread_id = f"{main_thread_id}:{domain}"
    config = {"configurable": {"thread_id": sub_thread_id}}

    try:
        agent_result = await agent.ainvoke({
            # instruction 以 HumanMessage 注入，作为子图会话的首条消息
            "messages": [HumanMessage(content=f"[user_id={user_id}]\n{instruction}")],
            "user_id": user_id,
            "instruction": instruction,
        }, config=config)
        return _parse_agent_outcome(agent_result, domain, sub_thread_id)
    except Exception as e:
        log.error(f"子图 {domain} 执行失败：{e}")
        return [{
            "domain": domain,
            "message": f"执行失败：{str(e)}",
            "error": True,
            "sub_thread_id": sub_thread_id,
        }], []


async def resume_subgraph(domain: str, sub_thread_id: str, answer: str):
    """恢复特定子图：追加用户回答后重新执行，返回 (results, interrupts)

    关键点：用户回答直接接回该子图的 checkpoint 历史（不重新路由、不重新分发）。
    子图在完整上下文（instruction + 反问 + 回答）中继续，可能再次反问或完成。
    """
    builder = SUBGRAPH_BUILDERS.get(domain)
    if not builder:
        log.warning(f"未知域：{domain}")
        return [], []

    agent = builder()
    config = {"configurable": {"thread_id": sub_thread_id}}

    try:
        agent_result = await agent.ainvoke(
            {"messages": [HumanMessage(content=answer)]},
            config=config,
        )
        return _parse_agent_outcome(agent_result, domain, sub_thread_id)
    except Exception as e:
        log.error(f"子图 {domain} 恢复失败：{e}")
        return [{
            "domain": domain,
            "message": f"恢复失败：{str(e)}",
            "error": True,
            "sub_thread_id": sub_thread_id,
        }], []


async def dispatch_subgraphs(state: dict) -> dict:
    """阶段二：并行派发所有待执行子图"""
    pending_tasks = state.get("pending_tasks", [])
    user_id = state.get("user_id")
    main_thread_id = state.get("thread_id") or str(uuid.uuid4())

    if not pending_tasks:
        return {"results": [], "interrupts": [], "completed_domains": []}

    coros = [
        _run_one_subgraph(task["domain"], task.get("instruction", ""), user_id, main_thread_id)
        for task in pending_tasks
    ]
    outcomes = await asyncio.gather(*coros, return_exceptions=True)

    results, interrupts, completed = [], [], []
    for outcome in outcomes:
        if isinstance(outcome, Exception):
            log.error(f"子图执行异常：{outcome}")
            continue
        r, i = outcome
        results.extend(r)
        interrupts.extend(i)
        # 完成且无反问的域 → 标记完成
        if r and not i:
            completed.extend(item["domain"] for item in r if "domain" in item)

    return {
        "results": results,
        "interrupts": interrupts,
        "completed_domains": completed,
    }


async def run_coordinator(state: dict) -> dict:
    """三阶段主编排（一次性）：router → dispatch → synthesize

    返回更新后的 state。注意：仅当所有域都已完成（无 pending 反问）时才总结；
    有反问时 final_reply 置空，等待用户逐条回答。
    """
    # 阶段一：主 agent 路由
    routing = await router_node(state)
    state["pending_tasks"] = routing.get("pending_tasks", [])

    # 阶段二：并行派发子图
    disp = await dispatch_subgraphs(state)
    state["results"] = disp.get("results", [])
    state["interrupts"] = disp.get("interrupts", [])
    state["completed_domains"] = disp.get("completed_domains", [])

    # 阶段三：全部完成才总结；否则等待用户回答反问
    pending_domains = {t["domain"] for t in state["pending_tasks"]}
    if pending_domains and (pending_domains - set(state["completed_domains"])):
        state["final_reply"] = ""
    else:
        syn = await synthesize_node(state)
        state["final_reply"] = syn.get("final_reply", "")
        # 三阶段走完 → 压入近 5 条历史
        finalize_record(state)

    return state
