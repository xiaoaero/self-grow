"""
Self Grow — 后端入口点

FastAPI 应用创建、生命周期管理、路由注册、启动入口。
"""

import os
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from config import PORT, log, UPLOAD_DIR
from db.init import init_db
from db.users import get_all_users
from db.batch import archive_incomplete_tasks, refresh_daily_tasks, refresh_weekly_tasks, settle_habit_exp_for_user, snapshot_daily_stats

# 初始化数据库
init_db()


# ================================================================
# 定时任务
# ================================================================

def run_daily_refresh():
    """每日 03:00 执行：任务刷新 + 习惯结算 + 统计快照"""
    log.info("⏰ 执行每日定时任务...")
    for user in get_all_users():
        uid = user["id"]
        try:
            archive_incomplete_tasks(uid)
            refresh_daily_tasks(uid)
            xp = settle_habit_exp_for_user(uid)
            snapshot_daily_stats(uid)
            if xp > 0:
                log.info(f"  用户 {uid}: 习惯结算 +{xp} EXP")
        except Exception as e:
            log.error(f"  用户 {uid} 定时任务失败: {e}")
    log.info("✅ 每日定时任务完成")


def run_weekly_refresh():
    """每周一 03:00 执行：从 weekly 模板创建任务"""
    log.info("⏰ 执行每周定时任务...")
    for user in get_all_users():
        uid = user["id"]
        try:
            refresh_weekly_tasks(uid)
        except Exception as e:
            log.error(f"  用户 {uid} 每周任务刷新失败: {e}")
    log.info("✅ 每周定时任务完成")


# ================================================================
# 应用生命周期
# ================================================================

@asynccontextmanager
async def lifespan(app_instance):
    """应用生命周期：启动时初始化定时任务，关闭时停止"""
    scheduler = None
    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from apscheduler.triggers.cron import CronTrigger

        scheduler = AsyncIOScheduler()
        scheduler.add_job(run_daily_refresh, CronTrigger(hour=3, minute=0))
        scheduler.add_job(run_weekly_refresh, CronTrigger(day_of_week='mon', hour=3, minute=5))
        scheduler.start()
        log.info("⏰ 定时任务调度器已启动")
    except ImportError:
        log.warning("⚠️ APScheduler 未安装，定时任务不可用")
    except Exception as e:
        log.warning(f"⚠️ 定时任务启动失败: {e}")
    yield
    if scheduler:
        scheduler.shutdown(wait=False)


# ================================================================
# FastAPI 应用
# ================================================================

app = FastAPI(title="Self Grow Backend", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 静态文件挂载（奖励图片上传）
os.makedirs(UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

# 注册路由
from routers import (
    health_router, users_router, habits_router, actions_router,
    goals_router, tasks_router, scheduled_tasks_router,
    stats_router, rewards_router, ai_router,
)

app.include_router(health_router)
app.include_router(users_router)
app.include_router(habits_router)
app.include_router(actions_router)
app.include_router(goals_router)
app.include_router(tasks_router)
app.include_router(scheduled_tasks_router)
app.include_router(stats_router)
app.include_router(rewards_router)
app.include_router(ai_router)


# ================================================================
# 启动入口
# ================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)