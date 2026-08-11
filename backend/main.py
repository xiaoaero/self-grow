"""
Self Grow — 后端入口点

FastAPI 应用创建、生命周期管理、路由注册、启动入口。
"""

import os
import logging
import datetime
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from config import PORT, log, UPLOAD_DIR, FRONTEND_DIR
from db.init import init_db
from db.users import get_all_users
from db.batch import archive_daily_tasks, archive_weekly_tasks, refresh_daily_tasks, refresh_weekly_tasks, settle_habit_exp_for_user, snapshot_daily_stats, catch_up_missed_archives

# 初始化数据库
init_db()


# ================================================================
# 定时任务
# ================================================================

def update_monthly_stats(user_id: int, count: int, xp: int):
    """增量更新当月习惯统计"""
    if count <= 0 and xp <= 0:
        return
    from db.connection import get_conn
    year_month = datetime.date.today().strftime("%Y-%m")
    conn = get_conn()
    conn.execute("""
        INSERT INTO user_monthly_stats (user_id, year_month, habit_count, habit_xp)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(user_id, year_month) DO UPDATE SET
            habit_count = habit_count + excluded.habit_count,
            habit_xp = habit_xp + excluded.habit_xp
    """, (user_id, year_month, count, xp))
    conn.commit()
    conn.close()


def run_daily_refresh():
    """每日 03:00 执行：归档昨日任务 + 任务刷新 + 习惯结算 + 统计快照 + 月度习惯累计"""
    log.info("⏰ 执行每日定时任务...")
    for user in get_all_users():
        uid = user["id"]
        try:
            archived = archive_daily_tasks(uid)
            refresh_daily_tasks(uid)
            count, xp = settle_habit_exp_for_user(uid)
            update_monthly_stats(uid, count, xp)
            snapshot_daily_stats(uid)
            if archived:
                log.info(f"  用户 {uid}: 归档 {archived} 条日任务")
            if xp > 0:
                log.info(f"  用户 {uid}: 习惯结算 +{xp} EXP（{count} 次打卡）")
        except Exception as e:
            log.error(f"  用户 {uid} 定时任务失败: {e}")
    log.info("✅ 每日定时任务完成")


def run_weekly_refresh():
    """每周一 03:05 执行：归档上周周任务 + 从 weekly 模板创建新任务"""
    log.info("⏰ 执行每周定时任务...")
    for user in get_all_users():
        uid = user["id"]
        try:
            archived = archive_weekly_tasks(uid)
            refresh_weekly_tasks(uid)
            if archived:
                log.info(f"  用户 {uid}: 归档 {archived} 条周任务")
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
        from apscheduler.executors.pool import ThreadPoolExecutor

        scheduler = AsyncIOScheduler(executors={'default': ThreadPoolExecutor(1)})
        scheduler.add_job(run_daily_refresh, CronTrigger(hour=3, minute=0))
        scheduler.add_job(run_weekly_refresh, CronTrigger(day_of_week='mon', hour=3, minute=5))
        scheduler.start()
        log.info("⏰ 定时任务调度器已启动")

        # 启动时补归档：检查凌晨3点的任务是否因关机未执行
        log.info("🔍 检查是否有未归档的任务...")
        for user in get_all_users():
            try:
                catch_up_missed_archives(user["id"])
            except Exception as e:
                log.error(f"  用户 {user['id']} 补归档失败: {e}")
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
    stats_router, rewards_router, ai_router, skill_tree_router,
    expression_router,
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
app.include_router(skill_tree_router)
app.include_router(expression_router)


# ================================================================
# API 配置端点（供前端动态获取 API_BASE）
# ================================================================

from fastapi.responses import Response, FileResponse

@app.get("/api/config.js")
async def serve_api_config():
    """返回 JavaScript 配置，让前端知道 API_BASE 地址"""
    content = f"window.__SELF_GROW_API_BASE__ = 'http://127.0.0.1:{PORT}';"
    return Response(content=content, media_type="application/javascript")


# ================================================================
# 同源模式：后端直接 serve 前端静态文件（Docker 部署 / 生产）
# ================================================================

if FRONTEND_DIR and os.path.isdir(FRONTEND_DIR):
    # 前端静态文件挂载在 /frontend/ 路径下
    # 这样 login.html 中的 frontend/css/... 和 frontend/index.html 跳转都能正常工作
    app.mount("/frontend", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend_static")

    # 登录页（根路径）
    @app.get("/")
    async def serve_login():
        login_path = os.path.join(os.path.dirname(FRONTEND_DIR), "login.html")
        if os.path.exists(login_path):
            return FileResponse(login_path)
        return {"message": "Self Grow API running"}

    log.info(f"同源模式：前端文件从 {FRONTEND_DIR} 提供")


# ================================================================
# 启动入口
# ================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)