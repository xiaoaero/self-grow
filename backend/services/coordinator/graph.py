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
from services.coordinator.agents.ask_user_tool import DOMAIN_LABELS
from services.sse import emit_stage, emit_token

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
        # 用 exception 保留堆栈：子 Agent 内部是 ReAct 循环（多轮 LLM + 工具），
        # 只打一行 str(e) 根本看不出是哪一轮、哪个工具出的问题
        log.exception("子图 %s 执行失败", domain)
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
        log.exception("子图 %s 恢复失败", domain)
        return [{
            "domain": domain,
            "message": f"恢复失败：{str(e)}",
            "error": True,
            "sub_thread_id": sub_thread_id,
        }], []


async def _run_one_subgraph_reported(task: dict, user_id: int, main_thread_id: str):
    """跑一个子图，并在开始/结束/反问时各推一个阶段事件

    这几个事件很有价值：阶段二是整条链路**等待最久**的一段（每个子 Agent 内部
    都是若干轮 LLM + 工具调用），而子图是**并行**跑的，所以事件会交错出现，
    用户能看到「两个域同时在动」。

    不流式时 emit_stage 是空操作，行为与直接调 _run_one_subgraph 完全一致。
    """
    domain = task["domain"]
    label = DOMAIN_LABELS.get(domain, domain)
    await emit_stage("domain_start", f"{label}：开始处理", domain=domain)

    results, interrupts = await _run_one_subgraph(
        domain, task.get("instruction", ""), user_id, main_thread_id
    )

    if interrupts:
        await emit_stage("domain_ask", f"{label}：需要你补充信息", domain=domain)
    else:
        await emit_stage("domain_done", f"{label}：已完成", domain=domain)
    return results, interrupts


async def dispatch_subgraphs(state: dict) -> dict:
    """阶段二：并行派发所有待执行子图"""
    pending_tasks = state.get("pending_tasks", [])
    user_id = state.get("user_id")
    main_thread_id = state.get("thread_id") or str(uuid.uuid4())

    if not pending_tasks:
        return {"results": [], "interrupts": [], "completed_domains": []}

    coros = [
        _run_one_subgraph_reported(task, user_id, main_thread_id)
        for task in pending_tasks
    ]
    outcomes = await asyncio.gather(*coros, return_exceptions=True)

    results, interrupts, completed = [], [], []
    for outcome in outcomes:
        if isinstance(outcome, Exception):
            # exc_info=outcome 才能打出这个异常的堆栈 ——
            # asyncio.gather(return_exceptions=True) 把异常当值返回，
            # 此时 sys.exc_info() 是空的，必须显式传
            log.error("子图执行异常：%r", outcome, exc_info=outcome)
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


async def run_coordinator_stream(state: dict) -> dict:
    """三段式主编排的**流式版**：与 run_coordinator 逻辑等价，只多了过程推送

    推出去的东西：
      · 阶段事件：routing / routing_done / domain_start / domain_done /
        domain_ask / tool / synthesize
      · 阶段三的回复改成**逐 token**推送（等待最长的就是这一段）

    事件通过 `services.sse` 的 ContextVar 发射器送出（由路由层用
    `use_emitter` 启用）；**没有启用流式时全部是空操作**，
    所以这个函数在非流式场景下也能安全调用（只是浪费一次 astream）。

    返回值与 run_coordinator 完全一致，路由层照旧把 state 存进 _thread_store。
    """
    # ── 阶段一：主 agent 路由 ──
    await emit_stage("routing", "正在理解你的意图…")
    routing = await router_node(state)
    state["pending_tasks"] = routing.get("pending_tasks", [])
    domains = [t["domain"] for t in state["pending_tasks"]]
    if domains:
        labels = "、".join(DOMAIN_LABELS.get(d, d) for d in domains)
        await emit_stage(
            "routing_done", f"已规划 {len(domains)} 项：{labels}", domains=domains
        )
    else:
        await emit_stage("routing_done", "直接生成回复…")

    # ── 阶段二：并行派发子图（每个域的起止/反问由 _run_one_subgraph_reported 推送）──
    disp = await dispatch_subgraphs(state)
    state["results"] = disp.get("results", [])
    state["interrupts"] = disp.get("interrupts", [])
    state["completed_domains"] = disp.get("completed_domains", [])

    # ── 阶段三：全部完成才总结 ──
    pending_domains = {t["domain"] for t in state["pending_tasks"]}
    if pending_domains and (pending_domains - set(state["completed_domains"])):
        # 还有域在等用户回答，final_reply 置空（与 run_coordinator 一致）
        state["final_reply"] = ""
    else:
        await emit_stage("synthesize", "正在整理回复…")
        syn = await synthesize_node(state, on_token=emit_token)
        state["final_reply"] = syn.get("final_reply", "")
        finalize_record(state)

    return state
