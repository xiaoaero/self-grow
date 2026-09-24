"""
Self Grow — AI 资讯板块路由（资讯只读 + AI 分析 + 手动刷新）

⚠️ 路由顺序有讲究：`/{category}` 是通配的，**必须放在最后**，
   否则 `/analysis`、`/board` 会被它先匹配走（然后因为不在 CATEGORIES 里报 404）。
"""
import asyncio

from fastapi import APIRouter, Depends, Query, HTTPException

from routers.deps import get_current_user
from services.aiconsult_service import (
    get_all, get_items, run_all_now, run_github_round_now,
    fetch_domestic_news, fetch_international_news, CATEGORIES,
)
from services.aiconsult_analysis_service import (
    ensure_analysis, build_analysis_payload, get_board_payload,
)

router = APIRouter(prefix="/api/aiconsult", tags=["aiconsult"])


@router.get("/all")
async def api_get_all(_user=Depends(get_current_user)):
    """一次返回 4 类最新一轮数据 + 各源 configured 标记（前端一屏拉完）。"""
    # 库读写是同步阻塞的，统一走线程池，避免卡事件循环
    return await asyncio.to_thread(get_all)


@router.get("/analysis")
async def api_analysis(user=Depends(get_current_user)):
    """AI 分析（懒触发）。

    - 今天还没生成过 → 起一个**后台任务**去跑 LLM，立刻返回 {"status":"generating"}
      （前端显示「生成中」并轮询，避免请求挂几十秒）
    - 已经生成过 → 直接返回摘要 + 三个榜（本周/本日/资讯热度）默认期
    - 每天最多生成一次；结果**所有用户共享**
      （但生成时用**触发者**的模型配置 —— 所以要把 user_id 传下去）
    """
    res = await ensure_analysis(user["id"])
    if res.get("status") != "ready":
        return res
    return await asyncio.to_thread(build_analysis_payload, res)


@router.get("/board")
async def api_board(kind: str = Query(...), period: str = Query(None),
                    _user=Depends(get_current_user)):
    """单个榜单（供周 / 日切换器使用）：kind = weekly | daily | news_hot"""
    res = await asyncio.to_thread(get_board_payload, kind, period)
    if res is None:
        raise HTTPException(status_code=404, detail="未知榜单")
    return res


@router.get("/{category}")
async def api_get_category(category: str, _user=Depends(get_current_user)):
    if category not in CATEGORIES:
        raise HTTPException(status_code=404, detail="未知分类")
    return await asyncio.to_thread(get_items, category)


@router.post("/refresh")
async def api_refresh(category: str = Query(None), _user=Depends(get_current_user)):
    """手动立即触发一轮抓取（调试用，不用等 cron）。

    - 不传 category：四类全部刷新
    - github_weekly / github_daily：单搜 ai 取 16，并派生榜单/快照
    - domestic / international：单源刷新
    """
    # ⚠️ 这些函数是同步阻塞的（网络请求 + 最多 3 次、每次 60~90s 的重试等待）。
    # 直接在 async 端点里调用会卡死整个 FastAPI 事件循环 → 全站无响应；
    # 必须丢进线程池执行。
    if category == "github_weekly":
        await asyncio.to_thread(run_github_round_now, "github_weekly")
    elif category == "github_daily":
        await asyncio.to_thread(run_github_round_now, "github_daily")
    elif category == "domestic":
        await asyncio.to_thread(fetch_domestic_news)
    elif category == "international":
        await asyncio.to_thread(fetch_international_news)
    else:
        await asyncio.to_thread(run_all_now)
    return await asyncio.to_thread(get_all)
