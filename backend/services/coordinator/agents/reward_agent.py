"""
奖励子图 — 基于 base.py 共享基座 + ask_user 反问

工具：create_reward / list_rewards / update_reward / delete_reward / claim_reward。
缺少标题时反问用户；领取时系统自动校验条件。
"""

import operator
from typing import Annotated, TypedDict
from langchain_core.tools import tool

from services.coordinator.agents.base import build_subgraph
from prompts.coordinator import REWARD_AGENT_SYSTEM_PROMPT


# ── 状态定义 ──────────────────────────────────────────

class RewardSubgraphState(TypedDict):
    """奖励管理子图状态"""
    messages: Annotated[list, operator.add]
    user_id: int
    instruction: str
    result: dict | None
    error: str | None
    ask_rounds: int


# ── 工具定义 ──────────────────────────────────────────

@tool
def create_reward(title: str, desc: str = "", icon: str = "🎁",
                  category: str = "", unlock_conditions: list = None,
                  claim_conditions: list = None, user_id: int = ...) -> dict:
    """创建新奖励。"""
    from db.rewards import create_reward as db_create_reward
    if user_id is None or user_id <= 0:
        return {"success": False, "message": "缺少有效用户身份（user_id 必填），已拒绝执行"}
    try:
        reward_id = db_create_reward(
            user_id=user_id,
            title=title,
            desc=desc,
            icon=icon,
            category=category,
            unlock_conditions=unlock_conditions or [],
            claim_conditions=claim_conditions or [],
        )
        return {
            "success": True,
            "reward_id": reward_id,
            "message": f"已创建奖励「{title}」"
        }
    except Exception as e:
        return {"success": False, "message": f"创建失败：{str(e)}"}


@tool
def list_rewards(user_id: int = ...) -> list:
    """查看所有奖励。"""
    from db.rewards import get_rewards
    if user_id is None or user_id <= 0:
        return []
    rewards = get_rewards(user_id)
    return [
        {
            "id": r["id"],
            "title": r["title"],
            "desc": r.get("desc", ""),
            "icon": r.get("icon", "🎁"),
            "category": r.get("category", ""),
            "unlocked": r.get("unlocked", False),
            "claimed": r.get("claimed", False),
        }
        for r in rewards
    ]


@tool
def update_reward(reward_id: int, title: str = None, desc: str = None,
                  icon: str = None, category: str = None,
                  unlock_conditions: list = None, claim_conditions: list = None,
                  user_id: int = ...) -> dict:
    """更新奖励信息。"""
    from db.rewards import update_reward as db_update_reward
    if user_id is None or user_id <= 0:
        return {"success": False, "message": "缺少有效用户身份（user_id 必填），已拒绝执行"}
    updates = {}
    if title is not None: updates["title"] = title
    if desc is not None: updates["desc"] = desc
    if icon is not None: updates["icon"] = icon
    if category is not None: updates["category"] = category
    if unlock_conditions is not None: updates["unlock_conditions"] = unlock_conditions
    if claim_conditions is not None: updates["claim_conditions"] = claim_conditions
    try:
        db_update_reward(reward_id, **updates)
        return {"success": True, "message": "奖励已更新"}
    except Exception as e:
        return {"success": False, "message": f"更新失败：{str(e)}"}


@tool
def delete_reward(reward_id: int, user_id: int = ...) -> dict:
    """删除奖励。"""
    from db.rewards import delete_reward as db_delete_reward
    if user_id is None or user_id <= 0:
        return {"success": False, "message": "缺少有效用户身份（user_id 必填），已拒绝执行"}
    try:
        db_delete_reward(reward_id)
        return {"success": True, "message": "奖励已删除"}
    except Exception as e:
        return {"success": False, "message": f"删除失败：{str(e)}"}


@tool
def claim_reward(reward_id: int, user_id: int = ...) -> dict:
    """领取奖励（需满足解锁和领取条件）。"""
    from db.rewards import claim_reward as db_claim
    if user_id is None or user_id <= 0:
        return {"success": False, "message": "缺少有效用户身份（user_id 必填），已拒绝执行"}
    try:
        result = db_claim(reward_id, user_id)
        return {"success": True, "message": "奖励已领取"}
    except Exception as e:
        return {"success": False, "message": f"领取失败：{str(e)}"}


TOOLS = [create_reward, list_rewards, update_reward, delete_reward, claim_reward]


# ── 子图构建 ──────────────────────────────────────────

def create_reward_agent():
    """创建奖励管理子图（自定义 StateGraph + interrupt）"""
    return build_subgraph(
        state_class=RewardSubgraphState,
        tools=TOOLS,
        domain="reward",
        domain_label="🎁 奖励管理",
        system_prompt=REWARD_AGENT_SYSTEM_PROMPT,
    )
