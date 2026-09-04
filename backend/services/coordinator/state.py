"""
Self Grow — Coordinator Agent 状态定义

主流程已改为纯函数编排（不再用 LangGraph StateGraph），因此 CoordinatorState
是普通的编排状态 dict；子图状态由各域 agent 模块自行定义（含 operator.add 用于
checkpointer 的消息历史累积）。
"""

from typing import TypedDict


# ── 路由决策（router_node 输出）───────────────────────

class SubgraphTask(TypedDict):
    """单个子图任务描述"""
    domain: str            # action / query / goal / task / habit / reward
    reason: str            # 为何路由至此域
    instruction: str       # 主图动态生成的子图定制指令


# ── 主 agent 上下文（跨记录记忆）──────────────────────

class RecordSummary(TypedDict):
    """一条完整记录在主 agent 上下文中的摘要（只记用户说的话 + 主 agent 总结）"""
    user_message: str      # 用户说的话（触发本次记录）
    summary: str           # 主 agent 的总结（三阶段走完后的 final_reply）


# ── 主编排状态（纯 dict，run_coordinator 读写）────────

class CoordinatorState(TypedDict, total=False):
    """协调 Agent 一次任务的编排状态"""
    # 用户输入
    user_id: int
    user_message: str
    thread_id: str

    # 对话历史（预留，供主 agent 上下文管理）
    messages: list[dict]

    # 路由决策（router_node 输出）
    pending_tasks: list[SubgraphTask]

    # 各子图返回结果
    results: list[dict]

    # 反问事件队列（推送给前端）
    interrupts: list[dict]

    # 已完成的域列表
    completed_domains: list[str]

    # 最终整合回复
    final_reply: str

    # 主 agent 跨记录上下文：近 5 条记录的 {用户说的话, 主agent总结}
    records: list[RecordSummary]
