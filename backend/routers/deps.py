"""
Self Grow — 路由依赖注入

提供 FastAPI 公用依赖，如 get_current_user 验证。
"""

from fastapi import HTTPException, Query
from db.users import get_user


async def get_current_user(user_id: int = Query(..., description="用户 ID")):
    """
    验证用户存在的依赖注入函数。
    替代 server.py 中 ~31 次重复的"用户不存在"检查。
    """
    user = get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    return user