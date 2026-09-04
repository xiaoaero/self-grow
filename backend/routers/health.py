"""
Self Grow — 健康检查路由
"""

from fastapi import APIRouter
from config import AI_MODEL, AI_BASE_URL, get_version

router = APIRouter()


@router.get("/api/health")
async def health():
    return {"status": "ok", "version": get_version(), "model": AI_MODEL, "base_url": AI_BASE_URL}