"""
目标子图 — 基于 base.py 共享基座 + ask_user 反问

工具：create_goal / list_goals / update_goal / delete_goal / claim_goal_reward。
缺少标题或里程碑时反问用户。
"""

import operator
from typing import Annotated, TypedDict
from langchain_core.tools import tool

from services.coordinator.agents.base import build_subgraph
from prompts.coordinator import GOAL_AGENT_SYSTEM_PROMPT


# ── 状态定义 ──────────────────────────────────────────

class GoalSubgraphState(TypedDict):
    """目标管理子图状态"""
    messages: Annotated[list, operator.add]
    user_id: int
    instruction: str
    result: dict | None
    error: str | None
    ask_rounds: int


# ── 工具定义 ──────────────────────────────────────────

@tool
def create_goal(title: str, intro: str, category: str, deadline: str,
                reward_exp: int, milestones: list, user_id: int = ...) -> dict:
    """创建新目标及里程碑。"""
    from db.goals import create_goal as db_create_goal
    try:
        if user_id is None or user_id <= 0:
            return {"success": False, "message": "缺少有效用户身份（user_id 必填），已拒绝执行"}
        goal_id = db_create_goal(
            user_id=user_id,
            title=title,
            intro=intro,
            category=category,
            deadline=deadline,
            reward_exp=reward_exp,
            category_image="",
            milestones=milestones,
        )
        return {
            "success": True,
            "goal_id": goal_id,
            "message": f"已创建目标「{title}」，包含 {len(milestones)} 个里程碑"
        }
    except Exception as e:
        return {"success": False, "message": f"创建失败：{str(e)}"}


@tool
def list_goals(user_id: int = ...) -> list:
    """查看所有目标。"""
    from db.goals import get_goals
    if user_id is None or user_id <= 0:
        return []
    goals = get_goals(user_id)
    return [
        {
            "id": g["id"],
            "title": g["title"],
            "intro": g.get("intro", ""),
            "category": g["category"],
            "deadline": g["deadline"],
            "reward_exp": g["reward_exp"],
            "status": g.get("status", "active"),
        }
        for g in goals
    ]


@tool
def update_goal(goal_id: int, title: str = None, intro: str = None,
                category: str = None, deadline: str = None,
                reward_exp: int = None, user_id: int = ...) -> dict:
    """更新目标信息。"""
    from db.goals import update_goal as db_update_goal
    if user_id is None or user_id <= 0:
        return {"success": False, "message": "缺少有效用户身份（user_id 必填），已拒绝执行"}
    updates = {}
    if title is not None: updates["title"] = title
    if intro is not None: updates["intro"] = intro
    if category is not None: updates["category"] = category
    if deadline is not None: updates["deadline"] = deadline
    if reward_exp is not None: updates["reward_exp"] = reward_exp
    try:
        db_update_goal(goal_id, user_id, **updates)
        return {"success": True, "message": "目标已更新"}
    except Exception as e:
        return {"success": False, "message": f"更新失败：{str(e)}"}


@tool
def delete_goal(goal_id: int, user_id: int = ...) -> dict:
    """删除目标。"""
    from db.goals import delete_goal as db_delete_goal
    if user_id is None or user_id <= 0:
        return {"success": False, "message": "缺少有效用户身份（user_id 必填），已拒绝执行"}
    try:
        db_delete_goal(goal_id, user_id)
        return {"success": True, "message": "目标已删除"}
    except Exception as e:
        return {"success": False, "message": f"删除失败：{str(e)}"}


@tool
def claim_goal_reward(goal_id: int, user_id: int = ...) -> dict:
    """领取目标奖励（经验）。"""
    from db.goals import claim_goal_reward as db_claim
    if user_id is None or user_id <= 0:
        return {"success": False, "message": "缺少有效用户身份（user_id 必填），已拒绝执行"}
    try:
        db_claim(goal_id, user_id)
        return {"success": True, "message": "目标奖励已领取"}
    except Exception as e:
        return {"success": False, "message": f"领取失败：{str(e)}"}


TOOLS = [create_goal, list_goals, update_goal, delete_goal, claim_goal_reward]


# ── 子图构建 ──────────────────────────────────────────

def create_goal_agent():
    """创建目标管理子图（自定义 StateGraph + interrupt）"""
    return build_subgraph(
        state_class=GoalSubgraphState,
        tools=TOOLS,
        domain="goal",
        domain_label="🎯 目标管理",
        system_prompt=GOAL_AGENT_SYSTEM_PROMPT,
    )
