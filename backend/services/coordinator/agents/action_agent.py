"""
行动记录子图 — 基于 base.py 共享基座 + ask_user 反问

工具：record_action。缺少 category/detail/duration 时反问用户。
"""

import operator
from typing import Annotated, TypedDict
from langchain_core.tools import tool

from services.coordinator.agents.base import build_subgraph
from prompts.coordinator import ACTION_AGENT_SYSTEM_PROMPT


# ── 状态定义 ──────────────────────────────────────────

class ActionSubgraphState(TypedDict):
    """行动记录子图状态"""
    messages: Annotated[list, operator.add]
    user_id: int
    instruction: str
    result: dict | None
    error: str | None
    ask_rounds: int


# ── 工具定义 ──────────────────────────────────────────

@tool
def record_action(category: str, detail: str, duration: int, start_time: str,
                  exp: int = None, sub_type: str = None, user_id: int = ...) -> dict:
    """记录用户的行动并计算经验值。

    Args:
        category: 行动类别（health/study/relation/work/create/finance/hobby/soul）
        detail: 行动内容描述
        duration: 时长（分钟）
        start_time: 开始时间 ISO 字符串（duration > 0 时必须提供）
        exp: 经验值（可选，为空则后端按 sub_type 自动计算）
        sub_type: 子类型，用于精确计分：
            health → health-sport / health-sleep
            relation → relation-offline / relation-online
            work → work-daily / work-overtime-weekday / work-overtime-weekend
            create → create-output / create-material / create-publish
            finance → finance-study / finance-review
            其余维度（study/hobby/soul）无需 sub_type
        user_id: 用户ID（必填，从 [user_id=N] 前缀中提取）

    Returns:
        {"success": True, "exp_earned": 实际获得的经验值, "message": "已记录..."}
    """
    from services.exp_service import create_action_and_award_exp

    try:
        if user_id is None or user_id <= 0:
            return {"success": False, "message": "缺少有效用户身份（user_id 必填），已拒绝执行"}

        result = create_action_and_award_exp(
            user_id=user_id,
            category=category,
            duration=duration,
            start_time=start_time,
            detail=detail,
            exp=exp,
            sub_type=sub_type,
        )

        return result
    except Exception as e:
        return {"success": False, "message": f"记录失败：{str(e)}"}


TOOLS = [record_action]


# ── 子图构建 ──────────────────────────────────────────

def create_action_agent():
    """创建行动记录子图（自定义 StateGraph + interrupt）"""
    return build_subgraph(
        state_class=ActionSubgraphState,
        tools=TOOLS,
        domain="action",
        domain_label="🏃 行动记录",
        system_prompt=ACTION_AGENT_SYSTEM_PROMPT,
    )
