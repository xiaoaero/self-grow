"""
习惯子图 — 基于 base.py 共享基座 + ask_user 反问

工具：create_habit / list_habits / update_habit / delete_habit / checkin_habit。
缺少名称时反问用户；打卡/更新时先列出习惯供用户选择。
"""

import operator
from typing import Annotated, TypedDict
from langchain_core.tools import tool

from services.coordinator.agents.base import build_subgraph
from prompts.coordinator import HABIT_AGENT_SYSTEM_PROMPT


# ── 状态定义 ──────────────────────────────────────────

class HabitSubgraphState(TypedDict):
    """习惯管理子图状态"""
    messages: Annotated[list, operator.add]
    user_id: int
    instruction: str
    result: dict | None
    error: str | None
    ask_rounds: int


# ── 工具定义 ──────────────────────────────────────────

@tool
def create_habit(name: str, category: str = "health", icon: str = "",
                 intro: str = "", weekly_target: int = 7, xp_reward: int = 15,
                 user_id: int = ...) -> dict:
    """创建新习惯。category 可选 health/study/relation/work/create/finance/hobby/soul。"""
    from db.habits import create_habit as db_create_habit
    if user_id is None or user_id <= 0:
        return {"success": False, "message": "缺少有效用户身份（user_id 必填），已拒绝执行"}
    try:
        habit_id = db_create_habit(
            user_id=user_id,
            name=name,
            icon=icon,
            intro=intro,
            category=category,
            weekly_target=weekly_target,
            xp_reward=xp_reward,
        )
        return {
            "success": True,
            "habit_id": habit_id,
            "message": f"已创建习惯「{name}」，每周目标 {weekly_target} 天"
        }
    except Exception as e:
        return {"success": False, "message": f"创建失败：{str(e)}"}


@tool
def list_habits(user_id: int = ...) -> list:
    """查看所有习惯。"""
    from db.habits import get_habits
    if user_id is None or user_id <= 0:
        return []
    habits = get_habits(user_id)
    return [
        {
            "id": h["id"],
            "name": h["name"],
            "icon": h.get("icon", ""),
            "category": h.get("category", ""),
            "weekly_target": h.get("weekly_target", 7),
            "xp_reward": h.get("xp_reward", 15),
            "active": h.get("active", 1),
        }
        for h in habits
    ]


@tool
def update_habit(habit_id: int, name: str = None, icon: str = None,
                 intro: str = None, category: str = None,
                 weekly_target: int = None, xp_reward: int = None,
                 active: int = None, user_id: int = ...) -> dict:
    """更新习惯信息。active: 1=启用, 0=停用。"""
    from db.habits import update_habit as db_update_habit
    if user_id is None or user_id <= 0:
        return {"success": False, "message": "缺少有效用户身份（user_id 必填），已拒绝执行"}
    try:
        db_update_habit(
            habit_id,
            name=name, icon=icon, intro=intro, category=category,
            weekly_target=weekly_target, xp_reward=xp_reward, active=active,
        )
        return {"success": True, "message": "习惯已更新"}
    except Exception as e:
        return {"success": False, "message": f"更新失败：{str(e)}"}


@tool
def delete_habit(habit_id: int, user_id: int = ...) -> dict:
    """删除习惯。"""
    from db.habits import delete_habits
    if user_id is None or user_id <= 0:
        return {"success": False, "message": "缺少有效用户身份（user_id 必填），已拒绝执行"}
    try:
        delete_habits([habit_id])
        return {"success": True, "message": "习惯已删除"}
    except Exception as e:
        return {"success": False, "message": f"删除失败：{str(e)}"}


@tool
def checkin_habit(habit_id: int, date: str = None, status: str = "done",
                  user_id: int = ...) -> dict:
    """打卡记录习惯。date 格式 YYYY-MM-DD，默认今天。status: done/skipped。"""
    from db.habits import upsert_checkin
    import datetime
    if user_id is None or user_id <= 0:
        return {"success": False, "message": "缺少有效用户身份（user_id 必填），已拒绝执行"}
    if date is None:
        date = datetime.date.today().isoformat()
    try:
        upsert_checkin(habit_id, date, status)
        return {"success": True, "message": f"打卡成功（{date}）"}
    except Exception as e:
        return {"success": False, "message": f"打卡失败：{str(e)}"}


TOOLS = [create_habit, list_habits, update_habit, delete_habit, checkin_habit]


# ── 子图构建 ──────────────────────────────────────────

def create_habit_agent():
    """创建习惯管理子图（自定义 StateGraph + interrupt）"""
    return build_subgraph(
        state_class=HabitSubgraphState,
        tools=TOOLS,
        domain="habit",
        domain_label="✅ 习惯管理",
        system_prompt=HABIT_AGENT_SYSTEM_PROMPT,
    )
