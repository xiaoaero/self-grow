"""
任务子图 — 基于 base.py 共享基座 + ask_user 反问

工具：create_task / list_tasks / update_task / delete_task / claim_task_reward。
缺少标题时反问用户。
"""

import operator
from typing import Annotated, TypedDict
from langchain_core.tools import tool

from services.coordinator.agents.base import build_subgraph
from prompts.coordinator import TASK_AGENT_SYSTEM_PROMPT


# ── 状态定义 ──────────────────────────────────────────

class TaskSubgraphState(TypedDict):
    """任务管理子图状态"""
    messages: Annotated[list, operator.add]
    user_id: int
    instruction: str
    result: dict | None
    error: str | None
    ask_rounds: int


# ── 工具定义 ──────────────────────────────────────────

@tool
def create_task(title: str, category: str, exp: int, priority: str = "mid",
                intro: str = "", source_type: str = "today", user_id: int = ...) -> dict:
    """创建新任务。

    Args:
        title: 任务标题（必填）
        category: 任务类别（必填），只能是以下之一：
            health/study/relation/work/create/finance/hobby/soul
        exp: 任务完成后可获得的经验值（必填，由用户指定，不可用默认值）
        priority: 优先级（low/mid/high，默认 mid）
        intro: 任务描述（可选）
        source_type: 任务类型（today=今日任务 / weekly=每周任务，默认 today）
        user_id: 用户ID（必填，后端注入）
    """
    from db.tasks import create_task as db_create_task
    if user_id is None or user_id <= 0:
        return {"success": False, "message": "缺少有效用户身份（user_id 必填），已拒绝执行"}
    try:
        task_id = db_create_task(
            user_id=user_id,
            title=title,
            category=category,
            priority=priority,
            exp=exp,
            intro=intro,
            source_type=source_type,
        )
        return {
            "success": True,
            "task_id": task_id,
            "message": f"已创建任务「{title}」，完成可获得 {exp} EXP"
        }
    except Exception as e:
        return {"success": False, "message": f"创建失败：{str(e)}"}


@tool
def list_tasks(user_id: int = ..., source_type: str = "today") -> dict:
    """查看任务列表。source_type 可选 today/weekly/all。"""
    from db.tasks import get_today_tasks, get_week_tasks, get_tasks_paginated
    if user_id is None or user_id <= 0:
        return {"error": "缺少有效用户身份（user_id 必填），已拒绝执行"}
    try:
        if source_type == "today":
            return get_today_tasks(user_id)
        elif source_type == "weekly":
            return get_week_tasks(user_id)
        else:
            result = get_tasks_paginated(user_id, page=1, page_size=50)
            return result.get("records", [])
    except Exception as e:
        return {"error": str(e)}


@tool
def update_task(task_id: int, title: str = None, category: str = None,
                priority: str = None, exp: int = None, intro: str = None,
                status: str = None, user_id: int = ...) -> dict:
    """更新任务信息或状态。"""
    from db.tasks import update_task as db_update_task
    if user_id is None or user_id <= 0:
        return {"success": False, "message": "缺少有效用户身份（user_id 必填），已拒绝执行"}
    updates = {}
    if title is not None: updates["title"] = title
    if category is not None: updates["category"] = category
    if priority is not None: updates["priority"] = priority
    if exp is not None: updates["exp"] = exp
    if intro is not None: updates["intro"] = intro
    if status is not None: updates["status"] = status
    try:
        db_update_task(task_id, **updates)
        return {"success": True, "message": "任务已更新"}
    except Exception as e:
        return {"success": False, "message": f"更新失败：{str(e)}"}


@tool
def delete_task(task_id: int, user_id: int = ...) -> dict:
    """删除任务。"""
    from db.tasks import delete_task as db_delete_task
    if user_id is None or user_id <= 0:
        return {"success": False, "message": "缺少有效用户身份（user_id 必填），已拒绝执行"}
    try:
        db_delete_task(task_id)
        return {"success": True, "message": "任务已删除"}
    except Exception as e:
        return {"success": False, "message": f"删除失败：{str(e)}"}


@tool
def claim_task_reward(task_id: int, user_id: int = ...) -> dict:
    """领取任务奖励（经验）。"""
    from db.tasks import claim_task_reward as db_claim
    if user_id is None or user_id <= 0:
        return {"success": False, "message": "缺少有效用户身份（user_id 必填），已拒绝执行"}
    try:
        result = db_claim(task_id)
        if result:
            return {"success": True, "message": f"任务奖励已领取，+{result['exp_earned']} EXP"}
        return {"success": False, "message": "领取失败：任务不存在或已领取"}
    except Exception as e:
        return {"success": False, "message": f"领取失败：{str(e)}"}


TOOLS = [create_task, list_tasks, update_task, delete_task, claim_task_reward]


# ── 子图构建 ──────────────────────────────────────────

def create_task_agent():
    """创建任务管理子图（自定义 StateGraph + interrupt）"""
    return build_subgraph(
        state_class=TaskSubgraphState,
        tools=TOOLS,
        domain="task",
        domain_label="📋 任务管理",
        system_prompt=TASK_AGENT_SYSTEM_PROMPT,
    )
