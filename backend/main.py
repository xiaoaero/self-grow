"""
Self Grow — 后端入口点

FastAPI 应用创建、生命周期管理、路由注册、启动入口。
"""

import os
import json
import logging
import datetime
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from config import (
    PORT, log, UPLOAD_DIR, FRONTEND_DIR,
    CORS_ORIGINS, CORS_ALLOW_CREDENTIALS, CORS_ALLOW_ORIGIN_REGEX,
    SELF_GROW_TRUSTED_MODE,
)
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
    # 缺少 JWT 密钥就拒绝启动 —— 否则服务能起来、一登录才 500，排查成本高
    from services import auth_service
    auth_service.ensure_jwt_secret()

    # 打印真正可用的访问地址（0.0.0.0 是监听地址，浏览器打不开）
    log.info("─" * 56)
    if _find_login_page():
        log.info(f"🌐 登录页：   http://localhost:{PORT}/login.html")
    else:
        log.info(f"🌐 接口地址： http://localhost:{PORT}/docs （未配置前端目录，仅 API）")
    log.info(f"📖 API 文档： http://localhost:{PORT}/docs")

    # 时区自检：全项目时间口径统一为**本地时间**（见 docs/时间口径统一方案.md）。
    # 容器忘记设 TZ 就会整体偏 8 小时（打卡日期错位、定时任务晚 8 小时），
    # 而且这类问题不报错、只让数据慢慢错掉 —— 所以启动时把偏移打出来。
    _tz = datetime.datetime.now().astimezone()
    _offset = _tz.utcoffset()
    _hours = _offset.total_seconds() / 3600 if _offset else 0
    if _hours == 0:
        log.warning("🕐 当前时区：UTC（偏移 +0.0h）—— 若你在中国，请检查容器是否漏设 TZ=Asia/Shanghai！")
    else:
        log.info(f"🕐 当前时区：{_tz.tzname()}（偏移 {_hours:+.1f}h）  当前时间 {_tz:%Y-%m-%d %H:%M}")

    if SELF_GROW_TRUSTED_MODE:
        log.warning("⚠️  本地免鉴权模式已开启（SELF_GROW_TRUSTED_MODE=1），任何人可免登录访问！")
    log.info("─" * 56)

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
    # 前端要带 Authorization 头，且同源部署时依赖 refresh Cookie，
    # 因此不能用 "*"（浏览器会拒绝携带凭证的响应）。
    allow_origins=CORS_ORIGINS,
    # 开发态前端端口不固定，再放行所有 localhost / 127.0.0.1 来源
    allow_origin_regex=CORS_ALLOW_ORIGIN_REGEX,
    allow_credentials=CORS_ALLOW_CREDENTIALS,
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
    stats_router, rewards_router, auth_router, skill_tree_router,
    skill_tree_ai_router, expression_router, coordinator_router, model_configs_router,
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
app.include_router(auth_router)
app.include_router(skill_tree_router)
app.include_router(skill_tree_ai_router)
app.include_router(expression_router)
app.include_router(coordinator_router)
app.include_router(model_configs_router)


# ================================================================
# API 配置端点（供前端动态获取 API_BASE）
# ================================================================

from fastapi.responses import Response, FileResponse

# 站点图标：浏览器每个页面都会自动请求 /favicon.ico，
# 没有它的话每次访问都刷一条 404 日志。优先用前端目录里的 favicon.svg，
# 取不到（前端由独立服务器提供时）则回落内联的同款图标。
_FAVICON_INLINE = (
    b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 40 40" fill="none">'
    b'<circle cx="20" cy="20" r="18" stroke="#4fc3f7" stroke-width="2"/>'
    b'<path d="M12 28 L20 12 L28 28" stroke="#4fc3f7" stroke-width="2"'
    b' stroke-linecap="round" stroke-linejoin="round"/>'
    b'<circle cx="20" cy="18" r="3" fill="#4fc3f7"/></svg>'
)


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    if FRONTEND_DIR:
        path = os.path.join(FRONTEND_DIR, "favicon.svg")
        if os.path.isfile(path):
            return FileResponse(path, media_type="image/svg+xml")
    return Response(
        content=_FAVICON_INLINE,
        media_type="image/svg+xml",
        headers={"Cache-Control": "public, max-age=86400"},
    )


# 站点根：直接给登录页。
# 之前根路径没有路由，启动后打开 http://localhost:3001/ 只会看到 404，
# 很容易让人误以为"服务没起来"。
_BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_BACKEND_DIR)


def _find_login_page():
    """定位 login.html（项目根），找不到再退到前端首页"""
    for p in (
        os.path.join(_PROJECT_ROOT, "login.html"),
        os.path.join(FRONTEND_DIR or "", "index.html"),
    ):
        if p and os.path.isfile(p):
            return p
    return None


@app.get("/", include_in_schema=False)
async def root():
    path = _find_login_page()
    if path:
        return FileResponse(path)
    return {
        "app": "Self Grow",
        "docs": "/docs",
        "health": "/api/health",
        "hint": "未配置 SELF_GROW_FRONTEND_DIR，后端未提供前端页面。"
                "开发模式下请用前端独立服务器打开 login.html。",
    }


@app.get("/login.html", include_in_schema=False)
async def login_page():
    """项目根的 login.html 不在 frontend/ 目录下，这里单独提供"""
    path = os.path.join(_PROJECT_ROOT, "login.html")
    if os.path.isfile(path):
        return FileResponse(path)
    raise HTTPException(status_code=404, detail="未找到 login.html")


@app.get("/api/config.js")
async def serve_api_config(request: Request):
    """返回 JavaScript 配置，让前端知道后端地址（API_BASE）

    ⚠️ 这里**绝对不能写死 127.0.0.1 / localhost** —— 这段 JS 是在**用户的浏览器**里执行的，
    写死回环地址等于让浏览器去访问「用户自己那台电脑」的 3001 端口。

    远程部署时的典型症状（很容易误判成"后端没起来"）：
      · 页面能打开，CSS/JS/字体全部 200
      · 之后**一个 API 请求都发不出去**，服务端日志里干干净净
      · 前端提示「无法连接到后端服务」

    正确做法：按**本次请求的 Host** 反推后端地址。同源部署下，浏览器是用哪个地址访问的
    后端，它就用哪个地址发 API 请求 —— 用 IP、用域名、带不带端口都自洽。
    """
    trusted = "true" if SELF_GROW_TRUSTED_MODE else "false"

    # 反向代理（Nginx 终止 HTTPS）时 scheme 由 X-Forwarded-Proto 给出，可能是 "https,http" 形式
    scheme = (request.headers.get("x-forwarded-proto") or request.url.scheme).split(",")[0].strip()
    host = request.headers.get("host") or f"127.0.0.1:{PORT}"
    api_base = f"{scheme}://{host}"

    content = (
        f"window.__SELF_GROW_API_BASE__ = {json.dumps(api_base)};\n"
        f"window.__SELF_GROW_TRUSTED_MODE__ = {trusted};\n"
    )
    return Response(
        content=content,
        media_type="application/javascript",
        # 不能缓存：换域名/换端口后必须立刻生效，否则浏览器会一直用旧的 API_BASE
        headers={"Cache-Control": "no-store"},
    )


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