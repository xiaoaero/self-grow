"""
Self Grow — 行动记录 API 路由
"""

from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime, timedelta

from db.actions import create_action_log, get_action_logs, get_today_action_stats, get_activity_feed
from db.users import get_user_stats
from models.constants import get_category, calculate_exp
from schemas.api import CreateActionRequest
from routers.deps import get_current_user

router = APIRouter()


@router.post("/api/actions")
async def create_action(req: CreateActionRequest, user=Depends(get_current_user)):
    """提交行动记录 — 后端计算 EXP、更新等级和今日统计"""
    user_id = user["id"]

    # 校验分类
    cat = get_category(req.category_id)
    if not cat:
        raise HTTPException(status_code=400, detail=f"无效分类: {req.category_id}")

    # 计算 end_time
    try:
        start_dt = datetime.fromisoformat(req.start_time)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="无效的 start_time 格式，需要 ISO 8601")

    end_dt = start_dt + timedelta(minutes=req.duration)
    end_time = end_dt.isoformat()

    # 计算 EXP
    exp_earned = calculate_exp(req.category_id, req.duration)

    # 插入行动记录
    new_id = create_action_log(
        user_id, req.category_id, req.start_time, end_time,
        req.duration, req.note or "", exp_earned,
    )

    # 使用服务层统一处理 EXP 奖励
    from services.exp_service import award_exp_and_recalc
    result = award_exp_and_recalc(
        user_id, req.category_id, exp_earned,
        extra_focus_minutes=req.duration,
        extra_tasks_done=1,
    )

    return {
        "id": new_id,
        "category_id": req.category_id,
        "category_name": cat["name"],
        "start_time": req.start_time,
        "end_time": end_time,
        "duration": req.duration,
        "note": req.note or "",
        "exp_earned": exp_earned,
        "exp_result": result["exp_result"],
        "today_stats": result["today_stats"],
    }


@router.get("/api/actions")
async def list_actions(
    user=Depends(get_current_user),
    page: int = 1,
    page_size: int = 20,
    category: str = None,
    sort: str = "newest",
    search: str = None,
    date_from: str = None,
    date_to: str = None,
):
    """分页查询行动历史"""
    user_id = user["id"]
    return get_action_logs(
        user_id, page=page, page_size=page_size,
        category=category, sort=sort, search=search,
        date_from=date_from, date_to=date_to,
    )


@router.get("/api/actions/today-stats")
async def today_action_stats(user=Depends(get_current_user)):
    """今日行动统计（分类分布 + 最近行动）"""
    user_id = user["id"]
    today = datetime.now().strftime('%Y-%m-%d')
    today_row = get_user_stats(user_id, today)
    action_stats = get_today_action_stats(user_id)

    return {
        "today_stats": {
            "focusMinutes": today_row["focus_minutes"],
            "tasksDone": today_row["tasks_done"],
            "habitsChecked": today_row["habits_checked"],
            "expEarned": today_row["exp_earned"],
        },
        "category_dist": action_stats["category_dist"],
        "recent_actions": action_stats["recent_actions"],
    }


@router.get("/api/activities/feed")
async def activity_feed(user=Depends(get_current_user)):
    """动态播报列表"""
    user_id = user["id"]
    activities = get_activity_feed(user_id)
    return {"activities": activities}