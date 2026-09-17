"""
Self Grow — 统计/数据看板 API 路由
"""

from fastapi import APIRouter, Depends
from datetime import datetime

from db.stats import get_profile_stats, get_yearly_activity, get_daily_exp_trend, get_recent_activities
from routers.deps import get_current_user

router = APIRouter()


@router.get("/api/stats/profile")
def stats_profile(user=Depends(get_current_user)):
    """6 项统计卡片 + 8 维进度"""
    stats = get_profile_stats(user["id"])
    return stats


@router.get("/api/stats/yearly-activity")
def stats_yearly_activity(user=Depends(get_current_user), year: int = None):
    """365 天热力图数据"""
    if year is None:
        year = datetime.now().year
    days = get_yearly_activity(user["id"], year)
    return {"year": year, "days": days}


@router.get("/api/stats/daily-exp")
def stats_daily_exp(user=Depends(get_current_user), days: int = 30):
    """每日 EXP 趋势"""
    result = get_daily_exp_trend(user["id"], days)
    return {"days": result}


@router.get("/api/activities/recent")
def recent_activities(user=Depends(get_current_user), limit: int = 10):
    """仪表盘近期动态"""
    activities = get_recent_activities(user["id"], limit)
    return {"activities": activities}


# 注：这里原来有个 `POST /api/stats/recalc-dimensions`（从 action_logs 重算所有维度），
# 已于 2026-09-17 删除 —— 全项目零调用方（前端没有任何入口、测试也不打它）。
# 它在 db/dimensions.py 里的实现 `recalc_dimensions_from_actions()` 也一起删了。
# 现在的自愈走另一条路：db/init.py 的 `normalize_dimension_rows()` 在每次
# `init_db()` 时把违反不变式的行修正回来，不需要人工触发。