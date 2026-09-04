"""
统计查询子图 — 基于 base.py 共享基座 + ask_user 反问

工具：query_user_stats / query_dimension_stats / query_action_history。
查询类子图通常不反问，但保留反问能力（如维度未指定时确认）。
"""

import operator
from typing import Annotated, TypedDict
from langchain_core.tools import tool

from services.coordinator.agents.base import build_subgraph
from prompts.coordinator import QUERY_AGENT_SYSTEM_PROMPT


# ── 状态定义 ──────────────────────────────────────────

class QuerySubgraphState(TypedDict):
    """统计查询子图状态"""
    messages: Annotated[list, operator.add]
    user_id: int
    instruction: str
    result: dict | None
    error: str | None
    ask_rounds: int


# ── 工具定义 ──────────────────────────────────────────

@tool
def query_user_stats(user_id: int) -> dict:
    """查询用户基本信息（等级、经验值、连续打卡天数）。"""
    from db.users import get_user
    user = get_user(user_id)
    if not user:
        return {"error": "用户不存在"}
    return {
        "level": user["level"],
        "total_exp": user["total_exp"],
        "streak": user["streak"],
        "joined": user["joined"],
    }


@tool
def query_dimension_stats(dimension_key: str, user_id: int) -> dict:
    """查询某个维度的详细数据（等级、经验值、进度）。"""
    from db.dimensions import get_user_dimensions
    dims = get_user_dimensions(user_id)
    for d in dims:
        if d["dimension_key"] == dimension_key:
            return d
    return {"error": f"维度 {dimension_key} 不存在"}


@tool
def query_action_history(user_id: int, limit: int = 10) -> list:
    """查询最近的行动记录。"""
    from db.actions import get_action_logs
    result = get_action_logs(user_id, page=1, page_size=limit)
    actions = result.get("records", [])
    return [
        {
            "id": a["id"],
            "category": a["category"],
            "detail": a.get("detail", ""),
            "duration": a.get("duration", 0),
            "exp": a.get("exp_earned", 0),
            "date": a.get("start_time", ""),
        }
        for a in actions
    ]


TOOLS = [query_user_stats, query_dimension_stats, query_action_history]


# ── 子图构建 ──────────────────────────────────────────

def create_query_agent():
    """创建统计查询子图（单节点 StateGraph + ask_user 反问）"""
    return build_subgraph(
        state_class=QuerySubgraphState,
        tools=TOOLS,
        domain="query",
        domain_label="📊 统计查询",
        system_prompt=QUERY_AGENT_SYSTEM_PROMPT,
    )
