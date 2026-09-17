"""
Self Grow — 用户 API 路由

包含用户列表、个人资料、今日统计同步。

注（2026-09-17 清理）：
  · `POST /api/users/login`（[已废弃] 的 user_id 卡片登录）已删除 ——
    登录页的卡片登录**根本不调后端**（只把用户信息写进 localStorage 再跳转），
    正式登录一律走 `POST /api/auth/login`，这个端点全项目零调用。
  · `POST /api/users/exp/add`（手动加经验）已删除 —— 开发调试用的，
    真实经验都由 action_logs / 任务 / 习惯走 `services/exp_service.py` 发放。
  · 注意 `GET /api/users`（裸列表）**是活的**：登录页用它渲染可选用户卡片，
    所以它故意不挂鉴权 —— 删代码时别看它没鉴权就当成漏洞顺手删掉。
"""

from fastapi import APIRouter, Depends
from datetime import datetime, timedelta

from db.users import get_all_users, get_user_stats, upsert_user_stats
from db.dimensions import get_total_exp_from_dimensions
from models.level import exp_for_level
from models.constants import get_rank_info
from schemas.api import StatsSyncRequest
from routers.deps import get_current_user

router = APIRouter()


@router.get("/api/users")
def list_users():
    """获取所有用户列表"""
    return get_all_users()


@router.get("/api/users/profile")
def user_profile(user=Depends(get_current_user)):
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
def sync_stats(req: StatsSyncRequest, user=Depends(get_current_user)):
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


