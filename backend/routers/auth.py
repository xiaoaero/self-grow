"""
Self Grow — 登录鉴权 API

端点：
    POST /api/auth/login       用户名 + 密码登录
    POST /api/auth/refresh     用 refresh cookie 换新的 access token（轮换）
    POST /api/auth/logout      登出（撤销当前 refresh）
    POST /api/auth/password    修改密码（旧 token 全部失效，等价于"登出所有设备"）
    GET  /api/auth/me          当前身份（权威来源）
    GET/POST/DELETE /api/auth/api-keys  API Key 管理（MCP 用）

注：原来的 `POST /api/auth/logout-all`（登出所有设备）已于 2026-09-17 删除 ——
全项目零调用方（用户中心没有对应按钮）。它的能力并没有丢：
底层 `auth_service.revoke_all_refresh()` 仍被「修改密码」使用。

凭证设计（见 docs/登录鉴权方案选型.md）：
    Access  → 响应体返回，前端存内存 + localStorage，请求时放 Authorization 头
    Refresh → ① httpOnly Cookie（同源部署时自动带上，JS 拿不到 = 防 XSS 窃取）
              ② 响应体同时返回（仅 Cookie 会在**跨域开发**场景下因 SameSite=Lax
                 被浏览器丢弃，此时前端以 body 中的 refresh 为准走 Authorization 之外的通道）

    取舍说明：生产同源部署（Docker，后端 serve 前端）下 Cookie 生效，
    即使 localStorage 里的副本被 XSS 读取，攻击者仍需同一浏览器环境；
    开发态前后端分离时（前端 5173 / 后端 3001）Lax Cookie 不发，靠 body 通道兜底。
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from db.auth import bump_token_version, set_password_hash
from routers.deps import get_current_user
from services import auth_service

log = logging.getLogger(__name__)

router = APIRouter()

REFRESH_COOKIE = "sg_refresh"
COOKIE_PATH = "/api/auth"


# ─────────────────────────────────────────────────────────────
# 请求模型
# ─────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str = Field(..., description="用户名")
    password: str = Field(..., description="密码")


class PasswordChangeRequest(BaseModel):
    old_password: str = Field(..., description="当前密码")
    new_password: str = Field(..., min_length=8, description="新密码（至少 8 位）")


class RefreshRequest(BaseModel):
    """refresh_token 可省略（同源时读 Cookie）；跨域开发时由前端从 body 传入"""
    refresh_token: str = Field("", description="可选，Cookie 不可用时的兜底通道")


class ApiKeyCreateRequest(BaseModel):
    name: str = Field("default", description="用途备注，如 Claude Desktop")


# ─────────────────────────────────────────────────────────────
# 工具
# ─────────────────────────────────────────────────────────────

def _public_user(user: dict) -> dict:
    return {
        "id": user["id"],
        "name": user["name"],
        "role": user.get("role") or "user",
        "is_admin": (user.get("role") or "user") == "admin",
    }


def _set_refresh_cookie(response: Response, raw: str, max_age: int):
    response.set_cookie(
        key=REFRESH_COOKIE,
        value=raw,
        max_age=max_age,
        httponly=True,          # JS 读不到 = XSS 偷不走
        samesite="lax",         # 同源部署足够；跨站场景需 none + secure
        path=COOKIE_PATH,
    )


def _issue_tokens(response: Response, user: dict, user_agent: str = "") -> dict:
    """签发 access + refresh（refresh 写入 cookie）"""
    access, ttl = auth_service.create_access_token(user)
    refresh, rttl = auth_service.create_refresh_token(user["id"], user_agent)
    _set_refresh_cookie(response, refresh, rttl)
    return {
        "access_token": access,
        "refresh_token": refresh,     # 跨域开发态的兜底通道（Cookie 被 SameSite 拦掉时）
        "token_type": "bearer",
        "expires_in": ttl,
        "refresh_expires_in": rttl,
        "user": _public_user(user),
    }


# ─────────────────────────────────────────────────────────────
# 端点
# ─────────────────────────────────────────────────────────────

@router.post("/api/auth/login")
def login(req: LoginRequest, request: Request, response: Response):
    """用户名 + 密码登录"""
    if auth_service.is_locked(req.username):
        raise HTTPException(status_code=429, detail="登录失败次数过多，请 10 分钟后重试")

    # authenticate 内部已完成密码校验；不区分"用户不存在"与"密码错误"，避免用户名枚举
    user = auth_service.authenticate(req.username, req.password)
    if not user:
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    log.info(f"用户登录：{user['name']}（id={user['id']}, role={user.get('role')}）")
    return _issue_tokens(response, user, request.headers.get("User-Agent", ""))


@router.post("/api/auth/refresh")
def refresh(request: Request, response: Response, req: RefreshRequest | None = None):
    """用 refresh token 换新的 access token（旧的立即作废 = 轮换）

    取值顺序：Cookie（同源部署）→ 请求体（跨域开发态兜底）。
    """
    body_token = req.refresh_token if req else ""
    raw = request.cookies.get(REFRESH_COOKIE) or body_token
    if not raw:
        raise HTTPException(status_code=401, detail="缺少 refresh token")

    user = auth_service.consume_refresh_token(raw)     # 内部已撤销旧的
    if not user:
        response.delete_cookie(REFRESH_COOKIE, path=COOKIE_PATH)
        raise HTTPException(status_code=401, detail="refresh token 无效或已过期")

    return _issue_tokens(response, user, request.headers.get("User-Agent", ""))


@router.post("/api/auth/logout")
def logout(request: Request, response: Response, req: RefreshRequest | None = None):
    """登出：撤销当前 refresh 并清除 cookie"""
    body_token = req.refresh_token if req else ""
    raw = request.cookies.get(REFRESH_COOKIE) or body_token
    if raw:
        auth_service.revoke_refresh_token(raw)
    response.delete_cookie(REFRESH_COOKIE, path=COOKIE_PATH)
    return {"success": True}


@router.post("/api/auth/password")
def change_password(req: PasswordChangeRequest, user=Depends(get_current_user)):
    """修改密码 → token_version+1 → 所有旧 access 立即失效"""
    if not auth_service.verify_password(req.old_password, _get_password_hash(user["id"])):
        raise HTTPException(status_code=400, detail="当前密码不正确")

    set_password_hash(user["id"], auth_service.hash_password(req.new_password))
    bump_token_version(user["id"])          # 旧 token 全部失效
    auth_service.revoke_all_refresh(user["id"])   # 所有设备需重新登录
    return {"success": True, "message": "密码已修改，请重新登录"}


@router.get("/api/auth/me")
def me(user=Depends(get_current_user)):
    """当前登录用户（角色权威来源）"""
    return _public_user(user)


# ─────────────────────────────────────────────────────────────
# API Key（MCP / 脚本）
# ─────────────────────────────────────────────────────────────

@router.post("/api/auth/api-keys")
def create_api_key(req: ApiKeyCreateRequest, user=Depends(get_current_user)):
    """生成 API Key（明文仅在创建时返回一次）"""
    raw, key_id = auth_service.create_api_key(user["id"], req.name)
    return {"id": key_id, "name": req.name, "api_key": raw}


@router.get("/api/auth/api-keys")
def list_api_keys(user=Depends(get_current_user)):
    """列出当前用户的 API Key（不含明文）"""
    from db.auth import list_api_keys as _list
    return {"keys": _list(user["id"])}


@router.delete("/api/auth/api-keys/{key_id}")
def revoke_api_key(key_id: int, user=Depends(get_current_user)):
    """撤销 API Key"""
    from db.auth import revoke_api_key as _revoke
    _revoke(key_id, user["id"])
    return {"success": True}


# ─────────────────────────────────────────────────────────────
# 内部辅助
# ─────────────────────────────────────────────────────────────

def _get_password_hash(user_id: int) -> str:
    """取密码哈希（authenticate 已校验过一次，这里仅供修改密码等场景二次确认）"""
    from db.auth import get_user_auth
    row = get_user_auth(user_id)
    return (row or {}).get("password_hash") or ""
