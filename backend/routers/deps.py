"""
Self Grow — 路由依赖注入

提供 FastAPI 公用依赖。

鉴权优先级（2026-09-13 JWT 改造）：
  ① TRUSTED_MODE 开启 → 直接使用配置里的默认用户（本地开发 / 演示）
  ② Authorization: Bearer <access_token> → 验签 + token_version 校验
  ③ X-API-Key: <key> → MCP / 脚本等非浏览器客户端
  ④ 都没有 → 401

注意：旧的 `?user_id=` 参数**不再作为身份依据**（那是"只校验 ID 是否存在"的伪鉴权），
保留参数本身无害，但后端一律以上述凭证为准。
"""

from fastapi import Depends, HTTPException, Request, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from config import SELF_GROW_TRUSTED_MODE, SELF_GROW_TRUSTED_USER_ID
from db.users import get_user
from services import auth_service

# auto_error=False：没带 token 时不由 security 直接抛错，交给下面的逻辑返回统一 401
bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Security(bearer_scheme),
) -> dict:
    """解析当前请求身份。失败一律 401，不再接受 URL 参数指定用户。"""
    # ① 可信模式（本地开发 / 演示）
    if SELF_GROW_TRUSTED_MODE:
        user = get_user(SELF_GROW_TRUSTED_USER_ID)
        if not user:
            raise HTTPException(
                status_code=500,
                detail=f"TRUSTED_MODE 配置的默认用户 {SELF_GROW_TRUSTED_USER_ID} 不存在",
            )
        return user

    # ② Bearer Access Token
    if credentials and credentials.credentials:
        payload = auth_service.decode_access_token(credentials.credentials)
        user = auth_service.resolve_token_user(payload) if payload else None
        if not user:
            raise HTTPException(
                status_code=401,
                detail="登录状态无效或已过期",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return user

    # ③ API Key（MCP / 脚本）
    api_key = request.headers.get("X-API-Key")
    if api_key:
        user = auth_service.resolve_api_key(api_key)
        if not user:
            raise HTTPException(status_code=401, detail="API Key 无效或已撤销")
        return user

    # ④ 无凭证
    raise HTTPException(
        status_code=401,
        detail="未登录",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def require_admin(user=Depends(get_current_user)) -> dict:
    """
    管理员校验：技能树的写操作（创建/保存/上线/删除/AI 编辑）必须挂这个依赖。

    - 未登录 / 凭证无效 → 401（由 get_current_user 抛出）
    - 已登录但非管理员 → 403
    - 前端"入口不渲染"只是 UX，这里才是真正的安全边界
    """
    if (user.get("role") or "user") != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user
