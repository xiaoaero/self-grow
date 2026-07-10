"""
Self Grow — 统计/数据看板 API 路由
"""

from fastapi import APIRouter, Depends
from datetime import datetime

from db.stats import get_profile_stats, get_yearly_activity, get_daily_exp_trend, get_recent_activities
from db.dimensions import get_user_dimensions, recalc_dimensions_from_actions
from routers.deps import get_current_user

router = APIRouter()


@router.get("/api/stats/profile")
async def stats_profile(user=Depends(get_current_user)):
    """6 项统计卡片 + 8 维进度"""
    stats = get_profile_stats(user["id"])
    return stats


@router.get("/api/stats/yearly-activity")
async def stats_yearly_activity(user=Depends(get_current_user), year: int = None):
    """365 天热力图数据"""
    if year is None:
        year = datetime.now().year
    days = get_yearly_activity(user["id"], year)
    return {"year": year, "days": days}


@router.get("/api/stats/daily-exp")
async def stats_daily_exp(user=Depends(get_current_user), days: int = 30):
    """每日 EXP 趋势"""
    result = get_daily_exp_trend(user["id"], days)
    return {"days": result}


@router.get("/api/activities/recent")
async def recent_activities(user=Depends(get_current_user), limit: int = 10):
    """仪表盘近期动态"""
    activities = get_recent_activities(user["id"], limit)
    return {"activities": activities}


@router.post("/api/stats/recalc-dimensions")
async def recalc_dimensions(user=Depends(get_current_user)):
    """从 action_logs 重算所有维度经验"""
    recalc_dimensions_from_actions(user["id"])
    dims = get_user_dimensions(user["id"])
    return {"dimensions": dims}