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

from fastapi import Depends, HTTPException, Request, Security, WebSocket
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from config import SELF_GROW_TRUSTED_MODE, SELF_GROW_TRUSTED_USER_ID
from db.users import get_user
from services import auth_service

# auto_error=False：没带 token 时不由 security 直接抛错，交给下面的逻辑返回统一 401
bearer_scheme = HTTPBearer(auto_error=False)


def _bind_request_user(request: Request, user: dict) -> dict:
    """把登录用户 id 挂到 request.state

    访问日志中间件（services/middleware.py）在请求收尾时读它，
    否则日志里只能看到路径、看不出是谁在访问。

    ⚠️ 必须在 get_current_user 的每个成功分支都调用一次 —— 中间件跑在
    路由之外，没有别的地方能拿到「本请求的身份」。
    """
    if user and request is not None:
        try:
            request.state.user_id = user.get("id", "-")
        except Exception:  # noqa: BLE001
            pass   # 记日志用，失败不能影响鉴权本身
    return user


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Security(bearer_scheme),
) -> dict:
    """解析当前请求身份。失败一律 401，不再接受 URL 参数指定用户。

    ⚠️ 这里是**同步 def，不是 async def** —— 不要"顺手"改回去。

    原因：本函数内部要查库（`get_user` / `auth_service.resolve_token_user` /
    `resolve_api_key` 全是同步 DB），而它是**每个请求都必须经过**的依赖。
    写成 async def 的话，这些同步查询会在**事件循环**里执行 ——
    只要有一次查询卡住（典型：MySQL 锁等待 30 秒，或连接池被占满），
    整个服务就停止响应，而且日志里看不出任何异常。

    写成同步 def 后 FastAPI 会自动把它丢进线程池，事件循环不受影响。
    （与 `services/` 里 `await asyncio.to_thread(...)` 是同一条规矩的两种写法：
      端点/依赖本身就是同步的 → 用 def；已经是 async 的函数里 → 用 to_thread。）
    """
    # ① 可信模式（本地开发 / 演示）
    if SELF_GROW_TRUSTED_MODE:
        user = get_user(SELF_GROW_TRUSTED_USER_ID)
        if not user:
            raise HTTPException(
                status_code=500,
                detail=f"TRUSTED_MODE 配置的默认用户 {SELF_GROW_TRUSTED_USER_ID} 不存在",
            )
        return _bind_request_user(request, user)

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
        return _bind_request_user(request, user)

    # ③ API Key（MCP / 脚本）
    api_key = request.headers.get("X-API-Key")
    if api_key:
        user = auth_service.resolve_api_key(api_key)
        if not user:
            raise HTTPException(status_code=401, detail="API Key 无效或已撤销")
        return _bind_request_user(request, user)

    # ④ 无凭证
    raise HTTPException(
        status_code=401,
        detail="未登录",
        headers={"WWW-Authenticate": "Bearer"},
    )


def require_admin(user=Depends(get_current_user)) -> dict:
    """
    管理员校验：技能树的写操作（创建/保存/上线/删除/AI 编辑）必须挂这个依赖。

    - 未登录 / 凭证无效 → 401（由 get_current_user 抛出）
    - 已登录但非管理员 → 403
    - 前端"入口不渲染"只是 UX，这里才是真正的安全边界

    同样用同步 def：与 get_current_user 保持一致，避免
    「同步依赖 + 异步依赖」混用带来的调度歧义（本函数无 IO，开销可忽略）。
    """
    if (user.get("role") or "user") != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user


def ensure_owner(resource: dict, user: dict, what: str = "该数据") -> None:
    """校验资源归属：不属于当前用户就直接 403。

    为什么"挂了 get_current_user"还不够
    ----------------------------------
    鉴权只回答「你是谁」，不回答「这条数据是不是你的」。
    只挂鉴权的话，**任何已登录用户都能改别人的数据** ——
    改他人目标、替他人打卡、领他人任务的奖励（经验还进自己账户）。

    用法（拿到单条资源之后、动它之前）：
        goal = get_goal(goal_id)
        if not goal:
            raise HTTPException(404, "目标不存在")
        ensure_owner(goal, user, "他人的目标")

    适用范围：goals / tasks / habits / scheduled_tasks / rewards 这些表都有
    `user_id INTEGER NOT NULL`，且单条查询都是 `SELECT *`（返回完整行），
    所以直接比对 `resource["user_id"]` 即可。
    """
    owner = resource.get("user_id")
    # owner 为 None 说明查询没带出 user_id —— 这种情况放行而不是误杀，
    # 但属于实现疏漏，调用点应当保证能取到
    if owner is not None and int(owner) != int(user["id"]):
        raise HTTPException(status_code=403, detail=f"无权操作{what}")


# WebSocket 的关闭码：1008 = policy violation（鉴权失败用它）
WS_POLICY_VIOLATION = 1008


def authenticate_websocket(websocket: WebSocket) -> dict | None:
    """WebSocket 连接的鉴权，成功返回用户 dict，失败返回 None

    为什么不能直接用 `Depends(get_current_user)`
    ------------------------------------------
    那是 HTTP 依赖，WebSocket 握手走的是另一套流程，FastAPI 不会为它注入。
    必须自己在握手时解析身份。

    为什么用 query param 而不是 header
    --------------------------------
    浏览器原生的 `WebSocket` 构造函数**不支持自定义 header**
    （与 EventSource 的 SSE 是同一个限制），所以 token 只能挂 URL。

    ⚠️ 原来的实现是直接读 `?user_id=` 并且**默认 1**：
    任何人都能指定任意 user_id，于是能
      · 冒用他人身份
      · 用掉他人配置的 ASR 模型与密钥（本项目支持每个用户配自己的 ASR key）
    现在改成读 `?token=<access_token>` 并走真实的 JWT 校验。
    """
    # 可信模式（本地开发 / 演示）：与 HTTP 侧保持一致的短路逻辑
    if SELF_GROW_TRUSTED_MODE:
        return get_user(SELF_GROW_TRUSTED_USER_ID)

    token = websocket.query_params.get("token")
    if not token:
        return None

    payload = auth_service.decode_access_token(token)
    if not payload:
        return None
    return auth_service.resolve_token_user(payload)
