"""
Self Grow — 用户 API 路由

包含登录、用户列表、个人资料、统计同步、手动加经验。
"""

from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime, timedelta

from db.users import get_user, get_user_by_name, get_all_users, get_user_stats, upsert_user_stats, update_user_exp
from db.dimensions import upsert_dimension, get_total_exp_from_dimensions
from models.level import exp_for_level, total_exp_for_level, level_from_total_exp
from models.constants import get_rank_info
from schemas.api import LoginRequest, StatsSyncRequest, ExpAddRequest
from routers.deps import get_current_user

router = APIRouter()


@router.post("/api/users/login")
async def login(req: LoginRequest):
    """通过 user_id 登录"""
    user = get_user(req.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    return {"id": user["id"], "name": user["name"], "role": user["role"]}


@router.get("/api/users")
async def list_users():
    """获取所有用户列表"""
    return get_all_users()


@router.get("/api/users/profile")
async def user_profile(user=Depends(get_current_user)):
    """获取用户完整资料（含今日/昨日统计）"""
    user_id = user["id"]
    level = user["level"]
    current_exp = user["exp"]

    total_exp = get_total_exp_from_dimensions(user_id)
    exp_to_next = exp_for_level(level)
    is_max_level = level >= 200
    rank_info = get_rank_info(level)

    today = datetime.now().strftime('%Y-%m-%d')
    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    today_row = get_user_stats(user_id, today)
    yesterday_row = get_user_stats(user_id, yesterday)

    return {
        "user": {
            "id": user["id"],
            "name": user["name"],
            "role": user["role"],
            "level": level,
            "exp": current_exp,
            "expToNext": exp_to_next,
            "isMaxLevel": is_max_level,
            "rank": rank_info["name"],
            "rankTier": rank_info["tier"],
            "totalExp": total_exp,
            "streak": user["streak"],
            "joined": user["joined"],
        },
        "todayStats": {
            "focusMinutes": today_row["focus_minutes"],
            "tasksDone": today_row["tasks_done"],
            "habitsChecked": today_row["habits_checked"],
            "expEarned": today_row["exp_earned"],
        },
        "yesterdayStats": {
            "focusMinutes": yesterday_row["focus_minutes"],
            "tasksDone": yesterday_row["tasks_done"],
            "habitsChecked": yesterday_row["habits_checked"],
            "expEarned": yesterday_row["exp_earned"],
        },
    }


@router.post("/api/users/stats/sync")
async def sync_stats(req: StatsSyncRequest, user=Depends(get_current_user)):
    """同步今日统计"""
    user_id = user["id"]
    today = datetime.now().strftime('%Y-%m-%d')
    upsert_user_stats(
        user_id, today,
        focus_minutes=req.focus_minutes,
        tasks_done=req.tasks_done,
        habits_checked=req.habits_checked,
        exp_earned=req.exp_earned,
    )

    today_row = get_user_stats(user_id, today)
    return {
        "focusMinutes": today_row["focus_minutes"],
        "tasksDone": today_row["tasks_done"],
        "habitsChecked": today_row["habits_checked"],
        "expEarned": today_row["exp_earned"],
    }


@router.post("/api/users/exp/add")
async def add_exp(req: ExpAddRequest, user=Depends(get_current_user)):
    """手动增加经验值（后端计算等级变化）"""
    user_id = user["id"]
    old_level = user["level"]

    # 如果有分类，同时更新对应维度的经验
    if req.category:
        upsert_dimension(user_id, req.category, req.amount)

    # 从维度表实时 SUM 总经验
    new_total = get_total_exp_from_dimensions(user_id)
    new_level = level_from_total_exp(new_total)
    new_current = new_total - total_exp_for_level(new_level)

    update_user_exp(user_id, new_level, new_current)

    rank_info = get_rank_info(new_level)
    return {
        "level": new_level,
        "exp": new_current,
        "expToNext": exp_for_level(new_level),
        "totalExp": new_total,
        "isMaxLevel": new_level >= 200,
        "rank": rank_info["name"],
        "rankTier": rank_info["tier"],
        "leveledUp": new_level > old_level,
        "oldLevel": old_level,
    }


