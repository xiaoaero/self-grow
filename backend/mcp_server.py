"""
Self Grow — MCP Server（Model Context Protocol）

把 Self Grow 的 24 个业务工具通过 MCP 协议暴露，让任何支持 MCP 的客户端
（Claude Desktop / Cursor / WorkBuddy / 自研 Agent）都能用自然语言管理
个人成长数据（记行动、打卡、查等级、管任务目标奖励等）。

工具清单（按域）：
  action  : record_action
  query   : query_user_stats / query_dimension_stats / query_action_history
  goal    : create_goal / list_goals / update_goal / delete_goal / claim_goal_reward
  task    : create_task / list_tasks / update_task / delete_task / claim_task_reward
  habit   : create_habit / list_habits / update_habit / delete_habit / checkin_habit
  reward  : create_reward / list_rewards / update_reward / delete_reward / claim_reward

枚举参数均用 typing.Literal 约束（生成 JSON Schema 的 enum），LLM 传非法值
会在调用前被 schema 拦截。

────────────────────────────────────────────────────────────
运行（stdio 传输，本地客户端 spawn）：
    cd backend
    python mcp_server.py

运行（HTTP / Streamable HTTP，远程客户端用 URL）：
    MCP_TRANSPORT=streamable-http MCP_PORT=8000 python mcp_server.py

依赖：fastmcp（详见 docs/MCP插件说明.md）
────────────────────────────────────────────────────────────
"""

import os
import sys
from datetime import date
from pathlib import Path
from typing import Literal, Optional

# 确保能 import backend 下的 db / services 模块（不依赖启动时的 cwd）
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastmcp import FastMCP  # noqa: E402

# ── 数据层导入（用 db_ 前缀避免与 MCP 工具函数重名）─────────
from db.users import get_user  # noqa: E402
from db.dimensions import get_user_dimensions  # noqa: E402
from db.actions import get_action_logs  # noqa: E402
from services.exp_service import create_action_and_award_exp  # noqa: E402

from db.goals import (  # noqa: E402
    get_goals as db_get_goals,
    create_goal as db_create_goal,
    update_goal as db_update_goal,
    delete_goal as db_delete_goal,
    claim_goal_reward as db_claim_goal_reward,
)
from db.tasks import (  # noqa: E402
    get_today_tasks as db_get_today_tasks,
    get_week_tasks as db_get_week_tasks,
    get_tasks_paginated as db_get_tasks_paginated,
    create_task as db_create_task,
    update_task as db_update_task,
    delete_task as db_delete_task,
    claim_task_reward as db_claim_task_reward,
)
from db.habits import (  # noqa: E402
    get_habits as db_get_habits,
    create_habit as db_create_habit,
    update_habit as db_update_habit,
    delete_habits as db_delete_habits,
    upsert_checkin as db_upsert_checkin,
)
from db.rewards import (  # noqa: E402
    get_rewards as db_get_rewards,
    create_reward as db_create_reward,
    update_reward as db_update_reward,
    delete_reward as db_delete_reward,
    claim_reward as db_claim_reward,
)

# ── 单用户模式 ──────────────────────────────────────────
# MCP 是工具协议，没有内置「用户」概念。个人使用固定一个 user_id，
# 可通过环境变量 SELF_GROW_USER_ID 覆盖（默认 1 = test 用户）。
DEFAULT_USER_ID = int(os.getenv("SELF_GROW_USER_ID", "1"))

# ── 枚举类型约束（生成 JSON Schema 的 enum）──────────────
CategoryId = Literal["health", "study", "relation", "work", "create", "finance", "hobby", "soul"]
SubType = Literal[
    "health-sport", "health-sleep",
    "relation-offline", "relation-online",
    "work-daily", "work-overtime-weekday", "work-overtime-weekend",
    "create-output", "create-material", "create-publish",
    "finance-study", "finance-review",
]
Priority = Literal["low", "mid", "high"]
TaskStatus = Literal["todo", "doing", "done"]
TaskSourceType = Literal["today", "weekly", "all"]
TaskCreateSourceType = Literal["today", "weekly"]
CheckinStatus = Literal["done", "skipped"]
ActiveFlag = Literal[0, 1]

mcp = FastMCP("Self Grow")


# ================================================================
# action 域
# ================================================================

@mcp.tool()
def record_action(category: CategoryId, detail: str, duration: int,
                  start_time: str, sub_type: Optional[SubType] = None) -> dict:
    """记录一条个人行动并自动结算经验值。例如"跑步 30 分钟"。

    Args:
        category: 维度ID（health/study/relation/work/create/finance/hobby/soul）
        detail: 行动内容描述（如"跑步"、"读《xx》"、"写周报"）
        duration: 时长（分钟）
        start_time: 开始时间 ISO 字符串（如 2026-08-27T10:00:00，必填）
        sub_type: 子类型（可选），用于精确计分：
            health → health-sport / health-sleep
            relation → relation-offline / relation-online
            work → work-daily / work-overtime-weekday / work-overtime-weekend
            create → create-output / create-material / create-publish
            finance → finance-study / finance-review
            其余维度（study/hobby/soul）无需 sub_type
    """
    if duration < 0:
        return {"success": False, "message": "时长不能为负数"}

    return create_action_and_award_exp(
        user_id=DEFAULT_USER_ID,
        category=category,
        duration=duration,
        start_time=start_time,
        detail=detail,
        sub_type=sub_type,
    )


# ================================================================
# query 域
# ================================================================

@mcp.tool()
def query_user_stats() -> dict:
    """查询当前用户的等级、总经验、连续打卡天数等基本信息。"""
    user = get_user(DEFAULT_USER_ID)
    if not user:
        return {"error": "用户不存在"}
    return {
        "level": user["level"],
        "total_exp": user["total_exp"],
        "streak": user["streak"],
        "joined": str(user.get("joined", "")),
    }


@mcp.tool()
def query_dimension_stats(dimension_key: CategoryId) -> dict:
    """查询某个维度的等级和经验进度。

    Args:
        dimension_key: 维度ID（health/study/relation/work/create/finance/hobby/soul）
    """
    dims = get_user_dimensions(DEFAULT_USER_ID)
    for d in dims:
        if d.get("dimension_key") == dimension_key:
            return {
                "dimension_key": d.get("dimension_key"),
                "level": d.get("level"),
                "xp": d.get("xp"),
                "xp_to_next": d.get("xp_to_next"),
            }
    return {"error": f"维度 {dimension_key} 不存在"}


@mcp.tool()
def query_action_history(limit: int = 10) -> list:
    """查询最近的行动记录。

    Args:
        limit: 返回条数（1~100），默认 10
    """
    limit = max(1, min(int(limit), 100))
    result = get_action_logs(DEFAULT_USER_ID, page=1, page_size=limit)
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


# ================================================================
# goal 域
# ================================================================

@mcp.tool()
def create_goal(title: str, intro: str, category: CategoryId, deadline: str,
                reward_exp: int, milestones: list) -> dict:
    """创建新目标及里程碑。

    Args:
        title: 目标标题
        intro: 目标描述
        category: 所属维度ID（health/study/relation/work/create/finance/hobby/soul）
        deadline: 截止日期（YYYY-MM-DD）
        reward_exp: 完成后可领取的经验值（0~9999）
        milestones: 里程碑列表，5~20 个，每项 {"note": "里程碑内容", "done": false}
    """
    ms = milestones or []
    if len(ms) < 5:
        return {"success": False, "message": f"里程碑至少需要 5 个，当前只有 {len(ms)} 个"}
    if len(ms) > 20:
        return {"success": False, "message": f"里程碑最多 20 个，当前有 {len(ms)} 个"}
    if reward_exp < 0 or reward_exp > 9999:
        return {"success": False, "message": "奖励经验值需在 0~9999 之间"}

    try:
        goal_id = db_create_goal(
            user_id=DEFAULT_USER_ID,
            title=title,
            intro=intro,
            category=category,
            deadline=deadline,
            reward_exp=reward_exp,
            category_image="",
            milestones=ms,
        )
        return {"success": True, "goal_id": goal_id,
                "message": f"已创建目标「{title}」，包含 {len(ms)} 个里程碑"}
    except Exception as e:
        return {"success": False, "message": f"创建失败：{e}"}


@mcp.tool()
def list_goals() -> list:
    """查看所有目标及其里程碑。"""
    goals = db_get_goals(DEFAULT_USER_ID)
    return [
        {
            "id": g["id"],
            "title": g["title"],
            "intro": g.get("intro", ""),
            "category": g.get("category", ""),
            "deadline": g.get("deadline", ""),
            "reward_exp": g.get("reward_exp", 0),
            "progress": g.get("progress", 0),
            "claimed": g.get("claimed", 0),
            "milestones": g.get("milestones", []),
        }
        for g in goals
    ]


@mcp.tool()
def update_goal(goal_id: int, title: str = None, intro: str = None,
                category: Optional[CategoryId] = None, deadline: str = None,
                reward_exp: int = None, milestones: list = None) -> dict:
    """更新目标信息或里程碑进度。

    Args:
        goal_id: 目标ID（先调 list_goals 查询获取）
        title/intro/category/deadline/reward_exp: 要更新的字段（不传则不改）
        milestones: 更新后的里程碑列表（每项 {"note", "done"}），不传则不改
    """
    try:
        db_update_goal(
            goal_id,
            title=title, intro=intro, category=category,
            deadline=deadline, reward_exp=reward_exp, milestones=milestones,
        )
        return {"success": True, "message": "目标已更新"}
    except Exception as e:
        return {"success": False, "message": f"更新失败：{e}"}


@mcp.tool()
def delete_goal(goal_id: int) -> dict:
    """删除目标（及其里程碑）。

    Args:
        goal_id: 目标ID（先调 list_goals 查询获取）
    """
    try:
        db_delete_goal(goal_id)
        return {"success": True, "message": "目标已删除"}
    except Exception as e:
        return {"success": False, "message": f"删除失败：{e}"}


@mcp.tool()
def claim_goal_reward(goal_id: int) -> dict:
    """领取目标完成奖励（经验）。

    Args:
        goal_id: 目标ID（先调 list_goals 查询获取）
    """
    try:
        result = db_claim_goal_reward(goal_id)
        if result:
            return {"success": True, "message": f"目标奖励已领取，+{result['exp_earned']} EXP"}
        return {"success": False, "message": "领取失败：目标不存在或已领取"}
    except Exception as e:
        return {"success": False, "message": f"领取失败：{e}"}


# ================================================================
# task 域
# ================================================================

@mcp.tool()
def create_task(title: str, category: CategoryId, exp: int,
                priority: Priority = "mid", intro: str = "",
                source_type: TaskCreateSourceType = "today") -> dict:
    """创建新任务。

    Args:
        title: 任务标题
        category: 任务类别（health/study/relation/work/create/finance/hobby/soul）
        exp: 任务完成后可获得的经验值（10~500，由用户指定）
        priority: 优先级 low/mid/high，默认 mid
        intro: 任务描述（可选）
        source_type: today=今日任务 / weekly=每周任务，默认 today
    """
    if exp < 10 or exp > 500:
        return {"success": False, "message": "任务经验值需在 10~500 之间"}

    try:
        task_id = db_create_task(
            user_id=DEFAULT_USER_ID,
            title=title,
            category=category,
            priority=priority,
            exp=exp,
            intro=intro,
            source_type=source_type,
        )
        return {"success": True, "task_id": task_id,
                "message": f"已创建任务「{title}」，完成可获得 {exp} EXP"}
    except Exception as e:
        return {"success": False, "message": f"创建失败：{e}"}


@mcp.tool()
def list_tasks(source_type: TaskSourceType = "today") -> dict:
    """查看任务列表。

    Args:
        source_type: today（今日）/ weekly（本周）/ all（全部历史），默认 today
    """
    try:
        if source_type == "today":
            return db_get_today_tasks(DEFAULT_USER_ID)
        elif source_type == "weekly":
            return db_get_week_tasks(DEFAULT_USER_ID)
        else:
            return db_get_tasks_paginated(DEFAULT_USER_ID, page=1, page_size=50).get("records", [])
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def update_task(task_id: int, title: str = None,
                category: Optional[CategoryId] = None,
                priority: Optional[Priority] = None, exp: int = None,
                intro: str = None, status: Optional[TaskStatus] = None) -> dict:
    """更新任务信息或状态。

    Args:
        task_id: 任务ID（先调 list_tasks 查询获取）
        title/category/priority/exp/intro: 要更新的字段（不传则不改）
        status: todo（待办）/ doing（进行中）/ done（已完成）
    """
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
        return {"success": False, "message": f"更新失败：{e}"}


@mcp.tool()
def delete_task(task_id: int) -> dict:
    """删除任务。

    Args:
        task_id: 任务ID（先调 list_tasks 查询获取）
    """
    try:
        db_delete_task(task_id)
        return {"success": True, "message": "任务已删除"}
    except Exception as e:
        return {"success": False, "message": f"删除失败：{e}"}


@mcp.tool()
def claim_task_reward(task_id: int) -> dict:
    """领取任务完成奖励（经验）。

    Args:
        task_id: 任务ID（先调 list_tasks 查询获取）
    """
    try:
        result = db_claim_task_reward(task_id)
        if result:
            return {"success": True, "message": f"任务奖励已领取，+{result['exp_earned']} EXP"}
        return {"success": False, "message": "领取失败：任务不存在或已领取"}
    except Exception as e:
        return {"success": False, "message": f"领取失败：{e}"}


# ================================================================
# habit 域
# ================================================================

@mcp.tool()
def create_habit(name: str, category: CategoryId = "health", icon: str = "",
                 intro: str = "", weekly_target: int = 7, xp_reward: int = 15) -> dict:
    """创建新习惯。

    Args:
        name: 习惯名称
        category: 所属维度ID（health/study/relation/work/create/finance/hobby/soul），默认 health
        icon: 图标（emoji 或文本，可选）
        intro: 描述（可选）
        weekly_target: 每周目标天数（1~14），默认 7
        xp_reward: 每次打卡经验值（5~100），默认 15
    """
    if weekly_target < 1 or weekly_target > 14:
        return {"success": False, "message": "每周目标天数需在 1~14 之间"}
    if xp_reward < 5 or xp_reward > 100:
        return {"success": False, "message": "每次打卡经验值需在 5~100 之间"}

    try:
        habit_id = db_create_habit(
            user_id=DEFAULT_USER_ID,
            name=name,
            icon=icon or "",
            intro=intro or "",
            category=category,
            weekly_target=weekly_target,
            xp_reward=xp_reward,
        )
        return {"success": True, "habit_id": habit_id,
                "message": f"已创建习惯「{name}」，每周目标 {weekly_target} 天"}
    except Exception as e:
        return {"success": False, "message": f"创建失败：{e}"}


@mcp.tool()
def list_habits() -> list:
    """查看所有习惯。"""
    habits = db_get_habits(DEFAULT_USER_ID)
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


@mcp.tool()
def update_habit(habit_id: int, name: str = None, icon: str = None,
                 intro: str = None, category: Optional[CategoryId] = None,
                 weekly_target: int = None, xp_reward: int = None,
                 active: Optional[ActiveFlag] = None) -> dict:
    """更新习惯信息。

    Args:
        habit_id: 习惯ID（先调 list_habits 查询获取）
        name/icon/intro/category/weekly_target/xp_reward: 要更新的字段
        active: 1=启用 / 0=停用
    """
    try:
        db_update_habit(
            habit_id, name=name, icon=icon, intro=intro, category=category,
            weekly_target=weekly_target, xp_reward=xp_reward, active=active,
        )
        return {"success": True, "message": "习惯已更新"}
    except Exception as e:
        return {"success": False, "message": f"更新失败：{e}"}


@mcp.tool()
def delete_habit(habit_id: int) -> dict:
    """删除习惯（及其打卡记录）。

    Args:
        habit_id: 习惯ID（先调 list_habits 查询获取）
    """
    try:
        db_delete_habits([habit_id])
        return {"success": True, "message": "习惯已删除"}
    except Exception as e:
        return {"success": False, "message": f"删除失败：{e}"}


@mcp.tool()
def checkin_habit(habit_id: int, status: CheckinStatus = "done") -> dict:
    """给习惯打卡（只能打卡今天，不支持补打历史日期）。

    Args:
        habit_id: 习惯ID（先调 list_habits 查询获取）
        status: done（完成）/ skipped（跳过），默认 done
    """
    today = date.today().isoformat()
    try:
        db_upsert_checkin(habit_id, today, status)
        return {"success": True, "message": f"打卡成功（{today}）"}
    except Exception as e:
        return {"success": False, "message": f"打卡失败：{e}"}


# ================================================================
# reward 域
# ================================================================

@mcp.tool()
def create_reward(title: str, desc: str = "", icon: str = "🎁",
                  category: str = "", unlock_conditions: list = None,
                  claim_conditions: list = None) -> dict:
    """创建新奖励（奖励商城）。

    Args:
        title: 奖励标题
        desc: 奖励描述（可选）
        icon: 图标（emoji，默认 🎁）
        category: 分类（可选，自由文本）
        unlock_conditions: 解锁条件列表（结构化条件，可选）
        claim_conditions: 领取条件列表（结构化条件，可选）
    """
    try:
        reward_id = db_create_reward(
            user_id=DEFAULT_USER_ID,
            title=title,
            desc=desc or "",
            icon=icon or "🎁",
            category=category or "",
            unlock_conditions=unlock_conditions or [],
            claim_conditions=claim_conditions or [],
        )
        return {"success": True, "reward_id": reward_id, "message": f"已创建奖励「{title}」"}
    except Exception as e:
        return {"success": False, "message": f"创建失败：{e}"}


@mcp.tool()
def list_rewards() -> list:
    """查看所有奖励及其解锁/领取状态。"""
    rewards = db_get_rewards(DEFAULT_USER_ID)
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


@mcp.tool()
def update_reward(reward_id: int, title: str = None, desc: str = None,
                  icon: str = None, category: str = None,
                  unlock_conditions: list = None, claim_conditions: list = None) -> dict:
    """更新奖励信息。

    Args:
        reward_id: 奖励ID（先调 list_rewards 查询获取）
        title/desc/icon/category: 要更新的字段
        unlock_conditions/claim_conditions: 更新的条件列表
    """
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
        return {"success": False, "message": f"更新失败：{e}"}


@mcp.tool()
def delete_reward(reward_id: int) -> dict:
    """删除奖励。

    Args:
        reward_id: 奖励ID（先调 list_rewards 查询获取）
    """
    try:
        db_delete_reward(reward_id)
        return {"success": True, "message": "奖励已删除"}
    except Exception as e:
        return {"success": False, "message": f"删除失败：{e}"}


@mcp.tool()
def claim_reward(reward_id: int) -> dict:
    """领取奖励（后端自动校验解锁/领取条件是否满足）。

    Args:
        reward_id: 奖励ID（先调 list_rewards 查询获取）
    """
    try:
        result = db_claim_reward(reward_id, DEFAULT_USER_ID)
        if result:
            return {"success": True, "message": "奖励已领取"}
        return {"success": False, "message": "领取失败：条件未满足或已领取"}
    except Exception as e:
        return {"success": False, "message": f"领取失败：{e}"}


# ================================================================

if __name__ == "__main__":
    # 传输方式：默认 stdio（本地客户端 spawn 进程）；设 MCP_TRANSPORT 可切换为 HTTP
    #   - streamable-http：MCP 新规范，远程访问（客户端 URL: http://host:port/mcp）
    #   - sse：旧方式（客户端 URL: http://host:port/sse）
    transport = os.getenv("MCP_TRANSPORT", "stdio")

    if transport == "stdio":
        # stdio：WorkBuddy / Claude Desktop / Cursor 等本地客户端直接 spawn 本进程通信
        mcp.run()
    else:
        host = os.getenv("MCP_HOST", "0.0.0.0")
        port = int(os.getenv("MCP_PORT", "8000"))
        mcp.run(transport=transport, host=host, port=port)
