# FastAPI 与 FastMCP 学习指南

> 结合 Self Grow 项目，从原理到实践系统讲解 FastAPI 与 FastMCP 两个框架。
> 核实时间：2026-09-06，代码引用均来自项目真实文件。

---

## 目录

- [第一部分：FastAPI](#第一部分fastapi)
- [第二部分：FastMCP](#第二部分fastmcp)
- [第三部分：FastAPI 与 FastMCP 的协作](#第三部分fastapi-与-fastmcp-的协作)
- [附录：术语表](#附录术语表)

---

# 第一部分：FastAPI

## 1.1 什么是 FastAPI？

### 大白话

FastAPI 是一个用 Python 写后端接口（API）的框架。它的核心工作就一句话：**把浏览器/客户端发来的 HTTP 请求，翻译成对 Python 函数的调用，再把函数的返回值打包成 JSON 发回去。**

想象你开了一家快递收发站：

- 客户端（浏览器、手机 App）是**寄件人**，寄来一个请求
- FastAPI 是**收发站**，负责拆包裹、检查地址对不对、把包裹交给对应的处理人
- 你的 Python 函数是**处理人**，干活（查数据库、调 AI），把结果交给收发站
- 收发站再把结果打包寄回给寄件人

**项目结合**：Self Grow 的后端就是 FastAPI。浏览器点一下"记录跑步 30 分钟"，FastAPI 收到 `POST /api/actions` 请求，调用对应的处理函数，查库、结算经验，最后返回 `{success: true, exp_earned: 15, ...}`。

### 为什么叫 "Fast"？

FastAPI 有两个"快"：

1. **运行快**：底层用了 Starlette（一个高性能异步 Web 框架）+ Pydantic（数据校验），性能接近 Node.js / Go 的水平，是 Python Web 框架里最快的之一。
2. **开发快**：类型注解自动生成文档和校验，写代码量远少于 Django / Flask。

### 为什么不用 Django / Flask？

| 框架 | 定位 | 异步 | 自动文档 | 数据校验 |
|------|------|------|---------|---------|
| **Django** | 全家桶（自带 ORM、后台、认证） | 弱 | 需插件 | 需手写 |
| **Flask** | 极简微框架 | 弱 | 需插件 | 需手写 |
| **FastAPI** | 现代 API 框架 | ✅ 原生 | ✅ 自动生成 Swagger | ✅ Pydantic 自动 |

**项目结合**：Self Grow 是前后端分离的个人应用，只需要干净的 REST API + 一点点静态文件服务，不需要 Django 那套庞大的后台系统，所以 FastAPI 最合适。

---

## 1.2 项目里的 FastAPI 骨架

整个后端入口在 `backend/main.py`（197 行）。我们把它拆成几块逐段讲解。

### ① 创建应用

```python
app = FastAPI(title="Self Grow Backend", version="1.0.0", lifespan=lifespan)
```

`FastAPI(...)` 创建了应用实例 `app`，之后所有路由都挂在这个 `app` 上。

- `title` / `version`：显示在自动文档页面上
- `lifespan`：应用启动/关闭时要做的额外事情（见下）

**自动文档**：启动后访问 `http://localhost:3001/docs` 能看到自动生成的交互式 API 文档（Swagger UI），访问 `/redoc` 是另一个风格的文档。**这是 FastAPI 最省心的特性——你写完代码，文档自动就有了，不用额外维护。**

### ② 生命周期（lifespan）

```python
@asynccontextmanager
async def lifespan(app_instance):
    scheduler = AsyncIOScheduler(...)      # 启动定时任务
    scheduler.add_job(run_daily_refresh, CronTrigger(hour=3, minute=0))
    scheduler.start()
    yield                                 # ← 应用正常运行期间
    scheduler.shutdown(wait=False)        # 关闭时停止定时任务
```

`lifespan` 是一个**上下文管理器**：`yield` 之前的代码在应用启动时执行，`yield` 之后在关闭时执行。Self Grow 用它来启动 APScheduler 定时任务（每日 03:00 归档任务、结算习惯经验）。

**为什么要用 lifespan 而不是写在模块顶部？** 因为要保证"应用启动 → 定时任务启动"、"应用关闭 → 定时任务停止"严格配对，模块顶部的代码在 import 时就执行了，无法控制关闭时机。

### ③ 中间件（CORS）

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
```

**中间件**是"请求进来、路由处理之前"和"响应出去之前"的钩子。CORS 中间件解决的是**跨域**问题：

- 前端跑在 `localhost:3000`（`python -m http.server`）
- 后端跑在 `localhost:3001`

浏览器安全策略规定：`3000` 端口的页面默认**不能**请求 `3001` 端口的接口，除非后端明确"允许"（响应头里带 `Access-Control-Allow-Origin`）。CORS 中间件就是自动加这个头。

> ⚠️ `allow_origins=["*"]` 表示允许**任何**来源访问，开发方便，但生产环境应该改成具体域名。

### ④ 静态文件服务

```python
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")
```

`app.mount` 把某个 URL 路径"挂载"到一个静态文件目录。访问 `/uploads/xxx.png` 就会返回磁盘上 `UPLOAD_DIR/xxx.png`。Self Grow 用它服务奖励图片上传。

```python
if FRONTEND_DIR and os.path.isdir(FRONTEND_DIR):
    app.mount("/frontend", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend_static")
    @app.get("/")
    async def serve_login():
        return FileResponse(...)
```

生产/Docker 部署时，后端**顺便把前端也 serve 了**——同一个进程、同一个端口，不用单独起 nginx。这是"同源模式"。

### ⑤ 注册路由

```python
from routers import health_router, users_router, habits_router, ...

app.include_router(health_router)
app.include_router(users_router)
# ... 共 14 个
```

FastAPI 推荐**按功能拆分路由**：每个领域一个文件、一个 `APIRouter`，最后在 `main.py` 统一 `include_router`。Self Grow 的 14 个 router 分布在 `backend/routers/` 下，对应 habits、actions、goals、tasks、rewards、skill_tree、coordinator 等模块。

**好处**：`main.py` 保持清爽，新增功能只要新建一个 router 文件再注册一行，互不干扰。

---

## 1.3 路由与依赖注入

### 路由怎么写

看一个真实端点（`backend/routers/coordinator.py`）：

```python
router = APIRouter(prefix="/api/coordinator", tags=["coordinator"])

@router.post("/chat")
async def chat(request: ChatRequest, user=Depends(get_current_user)):
    ...
    return {"thread_id": thread_id, "reply": ..., "interrupts": ...}
```

- `APIRouter(prefix=...)`：这个文件里所有路径都自动加 `/api/coordinator` 前缀
- `@router.post("/chat")`：声明一个 POST 端点，完整路径是 `/api/coordinator/chat`
- 返回值是 dict → FastAPI 自动转成 JSON

### 依赖注入（Depends）

`user=Depends(get_current_user)` 是 FastAPI 的**依赖注入**——在真正执行 `chat` 之前，先执行 `get_current_user`，把结果作为 `user` 参数传进来。

项目里的实现（`backend/routers/deps.py`）：

```python
async def get_current_user(user_id: int = Query(..., description="用户 ID")):
    user = get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    return user
```

这段代码做的事：从 URL 查询参数里取 `user_id`，查数据库，不存在就返回 404。

**依赖注入的价值**：把"验证用户"这个通用逻辑抽出来，用 `Depends(...)` 一行挂到任何端点，不用在每个函数里重复写一遍。

> ⚠️ **重要认知**：这个 `get_current_user` **不是真正的身份认证**（没有 token/password，只检查 `user_id` 存不存在）。详见 `docs/压测说明.md` §2.1.1。这也是本项目最大的安全缺口。

### 补充：三种参数类型（Query / Path / Body）

FastAPI 里，函数参数按来源分成三类，靠默认值声明：

| 参数类型 | 来源 | 声明方式 | 例子 |
|---------|------|---------|------|
| **查询参数** | URL `?key=value` | 普通参数或 `Query(...)` | `user_id: int = Query(...)` |
| **路径参数** | URL 路径 `/users/{id}` | 路径模板占位 | `user_id: int`（在路径里） |
| **请求体** | HTTP body（JSON） | `BaseModel` | `request: ChatRequest` |

**项目结合**：看 `backend/routers/users.py`，三种都有：

```python
# ① 请求体：CreateHabitRequest 是 Pydantic 模型
@router.post("/api/habits")
def create_habit(req: CreateHabitRequest, user=Depends(get_current_user)):
    ...

# ② 查询参数：limit 从 URL ?limit= 来（有默认值即为可选）
@router.get("/api/activities/recent")
def recent_activities(user=Depends(get_current_user), limit: int = 10):
    ...

# ③ 路径参数：task_id 从 URL 路径里来
@router.get("/api/tasks/{task_id}")
def get_task(task_id: int, user=Depends(get_current_user)):
    ...
```

### 补充：HTTPException 错误处理

FastAPI 用 `HTTPException` 抛错误，框架会自动转成对应状态码的 JSON 响应。

**项目结合**：`expression.py` 的题目详情（资源不存在就 404）：

```python
@router.get("/api/expression/question/{question_id}")
def api_get_question(question_id: int, user=Depends(get_current_user)):
    question = get_question(question_id)
    if not question:
        raise HTTPException(status_code=404, detail="题目不存在")   # 404
    return _format_question(question)
```

客户端收到 404 时，响应体是 `{"detail": "用户不存在"}`。

**常见的状态码约定**：

| 状态码 | 含义 | 什么时候用 |
|--------|------|-----------|
| 200 | 成功 | 正常返回 |
| 400 | 请求错误 | 参数格式不对 |
| 404 | 未找到 | 查的资源不存在 |
| 422 | 校验失败 | Pydantic 校验不过（FastAPI 自动返回） |
| 500 | 服务器错误 | 代码抛了未捕获异常 |

> ⚠️ **注意**：`login` 只校验 `user_id` 存在就返回用户信息，**没有密码验证**——这也是"无真正鉴权"的体现。任何人传一个存在的 `user_id` 就能"登录"。

### 补充：一个完整的端点长什么样

**项目结合**：`users.py` 的 `user_profile` 是一个完整的、真实的端点：

```python
@router.get("/api/users/profile")
async def user_profile(user=Depends(get_current_user)):
    user_id = user["id"]
    level = user["level"]

    total_exp = get_total_exp_from_dimensions(user_id)   # 从 8 维 SUM 反推总经验
    exp_to_next = exp_for_level(level)
    is_max_level = level >= 200
    rank_info = get_rank_info(level)

    today_row = get_user_stats(user_id, today)           # 查今日统计
    yesterday_row = get_user_stats(user_id, yesterday)   # 查昨日统计

    return {
        "user": { "level": level, "exp": ..., "rank": rank_info["name"], ... },
        "todayStats": { "focusMinutes": ..., "tasksDone": ..., ... },
        "yesterdayStats": { ... },
    }
```

这个端点展示了 FastAPI 的完整套路：

1. `Depends(get_current_user)` 先验证用户存在
2. 从 `user` 里拿到 `user_id`
3. 调用业务层（`get_total_exp_from_dimensions`、`get_user_stats`）拿数据
4. 组装成一个**嵌套的 dict** 返回（FastAPI 自动转 JSON）

前端 `app.js` 启动时就是调这个端点拿 `profile.user` + `todayStats` + `yesterdayStats` 的。

---

## 1.4 Pydantic 数据模型

FastAPI 用 **Pydantic** 自动校验请求体。看 `coordinator.py`：

```python
from pydantic import BaseModel

class ChatRequest(BaseModel):
    message: str
    thread_id: Optional[str] = None

@router.post("/chat")
async def chat(request: ChatRequest, ...):
    ...
```

当客户端 `POST /chat` 时，FastAPI 会：

1. 把请求体 JSON 解析成 `ChatRequest` 对象
2. **自动校验**：`message` 必须是字符串且必填；`thread_id` 可选，缺省为 `None`
3. 校验失败（比如 `message` 传了个数字）→ 自动返回 422 错误，附上"哪里错了"的详细说明

**没有 Pydantic 时**，你得手动 `request.json()`、手动检查每个字段类型、手动写错误响应。Pydantic 把这些全包了。

### Pydantic 进阶：字段约束

除了声明类型，Pydantic 还能给字段加**约束**：

```python
from pydantic import BaseModel, Field

class CreateActionRequest(BaseModel):
    category: str = Field(..., description="维度ID")      # ... 表示必填
    duration: int = Field(..., ge=0, le=1440)            # 时长 0~1440 分钟
    detail: str = Field("", max_length=200)              # 默认空，最长 200 字
    sub_type: Optional[str] = None                        # 可选
```

| 约束 | 含义 |
|------|------|
| `...` | 必填（没有默认值） |
| `ge` / `le` | 大于等于 / 小于等于（数值范围） |
| `min_length` / `max_length` | 字符串长度限制 |
| `Optional[...]` | 可空 |
| `Field(default=...)` | 默认值 |

### 嵌套模型

Pydantic 支持模型套模型，用于表达复杂结构：

```python
class Address(BaseModel):
    city: str
    street: str

class User(BaseModel):
    name: str
    address: Address   # 嵌套模型
```

**项目结合**：`coordinator.py` 的 `ChatRequest`、`ResumeRequest` 都是 Pydantic 模型，虽然简单，但校验了请求体结构。

---

## 1.5 异步 async/await 基础

FastAPI 支持 `async def` 端点。看项目里的写法：

```python
@router.post("/chat")
async def chat(request: ChatRequest, user=Depends(get_current_user)):
    state = await run_coordinator(state)   # await 一个异步函数
```

### 大白话解释 async

想象一个餐厅：

- **同步（sync）**：服务员点完一桌菜，就一直站在厨房门口等菜做好，才去招呼下一桌。一个人同时只能服务一桌。
- **异步（async）**：服务员点完菜就立刻去招呼下一桌，厨房做好了会"叫号"，服务员再回来上菜。一个人能同时服务很多桌。

`await` 就是"厨房在忙，我先去干别的，好了叫我"。

### 什么操作值得 await？

只有**会等待 I/O 的操作**（读数据库、调外部 API、读文件）才值得 await——等待期间 CPU 是空闲的，可以去处理别的请求。纯计算操作（算经验值、排序）await 了也没用，反而阻塞。

### ⚠️ 项目里的一个真实坑（已于 2026-09-08 修复）

`backend/services/coordinator/agents/base.py` 里，子 Agent 执行工具原本用的是**同步**调用：

```python
tool_result = tool_fn.invoke(args)   # ❌ 同步，不是 await
```

在一个 `async` 函数里执行同步的数据库操作，会把整个事件循环**卡住**——就像服务员明明在等菜，却把身体横在门口，其他客人也进不来。

**现在的写法**（丢线程池）：

```python
import asyncio

# 工具是同步的（内部是同步 sqlite3），丢线程池避免阻塞事件循环
tool_result = await asyncio.to_thread(tool_fn.invoke, args)   # ✅
```

> 注意：工具函数本身仍是同步的（24 个工具全是 `def`，Python 的 sqlite3 没有异步 API），改的是**调用方式**。

详见 `docs/异步编程学习指南.md` §4.1 和 `docs/性能优化学习指南.md` §3.2.2。

---

## 1.6 流式响应（SSE）

对于 AI 应用，等 AI 生成完一整段话再一次性返回，用户体验很差（等半天没反应）。更好的做法是**边生成边推送**，这叫流式响应（Server-Sent Events，SSE）。

FastAPI 用 `StreamingResponse` 实现：

```python
@router.get("/stream/{thread_id}")
async def stream_events(thread_id: str):
    async def event_generator():
        state = _get_state(thread_id)
        if state:
            yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
```

关键点：

- `event_generator` 是一个**异步生成器**（有 `yield` 的函数）
- `yield` 一次，客户端就收到一块数据
- `media_type="text/event-stream"` 告诉浏览器这是 SSE 流

**项目结合**：`/api/coordinator/stream/{thread_id}` 目前只是**占位实现**（只吐一条 `done`），前端也还没接 SSE，走的是普通 POST 等完整响应。这是"技能树 AI 改造"和"协调 Agent"两个模块都列出的待办项。

> SSE 和 WebSocket 的区别：SSE 是**单向**的（服务器→客户端持续推送），WebSocket 是**双向**的。AI 生成、实时日志、进度条用 SSE 就够，聊天室、游戏才需要 WebSocket。

---

# 第二部分：FastMCP

## 2.1 什么是 MCP？

### 大白话

MCP（Model Context Protocol，模型上下文协议）是 Anthropic 在 2024 年底推出的一个**开放标准**，解决的核心问题是：

> **如何让 AI 大模型（Claude、GPT 等）调用你写的工具？**

在没有 MCP 之前，每个 AI 客户端调用工具的方式都不一样——Claude Desktop 一套、Cursor 一套、自研 Agent 又一套。你想让 AI 调用你的"记录行动"工具，得给每个客户端单独写适配代码。

MCP 就像 **AI 界的 USB-C 接口**：把工具用统一协议暴露一次，所有支持 MCP 的客户端都能零适配接入。

### 类比：语言服务器协议（LSP）

程序员对 LSP 很熟——编辑器（VS Code、Vim、Sublime）用同一个 LSP 就能获得代码补全、跳转定义等能力，不用为每个语言单独写插件。

MCP 就是 **AI 版的 LSP**：AI 客户端（Claude Desktop、Cursor、WorkBuddy）用同一个 MCP 就能调用你的工具。

### MCP 的三个核心要素

| 要素 | 作用 | Self Grow 用了哪个 |
|------|------|-------------------|
| **Tools（工具）** | 让 AI 执行动作（查数据、写数据） | ✅ 24 个业务工具 |
| **Resources（资源）** | 让 AI 读取文件/数据 | ❌ 未用 |
| **Prompts（提示词模板）** | 预定义的提示词 | ❌ 未用 |

### 架构：Client-Server

```
┌──────────────────┐        MCP 协议        ┌──────────────────┐
│  MCP Client      │  ◄──────────────────►  │  MCP Server      │
│  (Claude Desktop │     (JSON-RPC)         │  (你的 mcp_server)│
│   / Cursor 等)    │                       │  (Self Grow 工具) │
└──────────────────┘                        └──────────────────┘
```

- **Client**：发起请求的一方（AI 客户端）
- **Server**：提供工具的一方（你的代码）
- 通信用 **JSON-RPC**（就是"发 JSON 字符串、收 JSON 字符串"）

### 补充：Resources 和 Prompts 是什么？

MCP 三大要素里，Self Grow 只用了 **Tools**。另外两个虽然没用，但值得了解：

**Resources（资源）**：让 AI **读取**数据（文件、数据库内容），只读不改。

```python
@mcp.resource("file://notes/{name}")
def get_note(name: str) -> str:
    return read_file(name)   # 让 AI 读取笔记内容
```

**Prompts（提示词模板）**：预定义好的提示词，用户/客户端可以直接调用。

```python
@mcp.prompt()
def review_prompt() -> str:
    return "请以专业工程师视角评审以下代码..."
```

| 要素 | 方向 | 类比 | Self Grow |
|------|------|------|----------|
| Tools | AI 主动调用，可读可写 | 给 AI 一个"工具箱" | ✅ 24 个 |
| Resources | AI 读取数据 | 给 AI 一个"资料库" | ❌ |
| Prompts | 预定义提示词 | 给 AI 一个"常用话术本" | ❌ |

> **为什么 Self Grow 只用 Tools**：个人成长系统的核心需求是"让 AI 操作数据"（记行动、打卡），这是 Tools 的典型场景。Resources（读资料）和 Prompts（话术模板）暂时没有对应需求。

### 补充：MCP 工具调用的完整流程

AI 客户端到底是怎么"发现并调用"你的工具的？完整流程分四步：

```
① 发现（Discovery）
   客户端连接 MCP Server → 问"你有哪些工具？"
   Server 返回工具列表（名称 + 描述 + 参数 schema）

② AI 决策（LLM 决定）
   用户说"记录跑步30分钟"
   LLM 看到工具列表，判断该调 record_action，并生成参数

③ 调用（Call）
   客户端通过 JSON-RPC 调用 record_action(category="health", duration=30, ...)
   Server 执行函数，返回结果

④ 反馈（Feedback）
   客户端把工具返回结果喂回 LLM
   LLM 根据结果生成自然语言回复："已记录跑步，+15 经验"
```

**关键认知**：MCP Server 本身**不调用 AI**，它只负责"定义工具 + 执行工具"。**决定调哪个工具、传什么参数，是客户端那边的 LLM 干的**。

这就是为什么工具描述（docstring）和参数 schema（类型注解）那么重要——它们是 LLM 决策的**唯一依据**。描述写得烂，LLM 就不知道该不该调、怎么调。

---

## 2.2 什么是 FastMCP？

FastMCP 是 MCP 官方 Python SDK v2 的**高级封装**。类比：

| 层 | 类比 |
|---|---|
| MCP 协议规范 | USB 接口的标准文档 |
| MCP Python SDK | 底层驱动（要自己处理握手、JSON-RPC、类型注册） |
| **FastMCP** | 高级封装（就像 FastAPI 之于 ASGI，几行代码搞定） |

FastMCP 之于 MCP，就像 **FastAPI 之于 HTTP**：把繁琐的协议细节藏起来，让你专注于"定义工具函数"。

**项目结合**：Self Grow 的 `backend/mcp_server.py` 用的就是 FastMCP，在 `pixi.toml` 的 `[pypi-dependencies]` 段声明 `fastmcp = ">=2.0"`。

---

## 2.3 项目里的 FastMCP 骨架

### ① 创建 Server

```python
from fastmcp import FastMCP

mcp = FastMCP("Self Grow")
```

一行就创建了一个 MCP Server，名字是 `"Self Grow"`（客户端里显示的名字）。

### ② 注册工具

```python
@mcp.tool()
def query_user_stats() -> dict:
    """查询当前用户的等级、总经验、连续打卡天数等基本信息。"""
    user = get_user(DEFAULT_USER_ID)
    if not user:
        return {"error": "用户不存在"}
    return {
        "level": user["level"],
        "total_exp": user["total_exp"],
        "streak": user["streak"],
    }
```

`@mcp.tool()` 装饰器把一个普通 Python 函数变成 MCP 工具。关键点：

- **函数 docstring 自动成为工具描述** —— AI 就是靠这个描述判断"什么时候该调用这个工具"
- **类型注解自动生成参数 schema** —— AI 靠这个知道"这个工具要什么参数"
- **返回值 dict 自动序列化成 JSON** 发给客户端

### ③ 运行

```python
if __name__ == "__main__":
    transport = os.getenv("MCP_TRANSPORT", "stdio")
    if transport == "stdio":
        mcp.run()                                        # stdio 模式
    else:
        mcp.run(transport=transport, host=host, port=port)  # HTTP 模式
```

`mcp.run()` 启动服务器，开始监听客户端请求。

---

## 2.4 类型约束：Literal → enum

这是本项目 MCP 工具最值得学的一招。看 `mcp_server.py`：

```python
CategoryId = Literal["health", "study", "relation", "work", "create", "finance", "hobby", "soul"]

@mcp.tool()
def record_action(category: CategoryId, detail: str, duration: int, ...) -> dict:
    ...
```

`typing.Literal["health", "study", ...]` 的意思是：这个参数**只能是**这 8 个值之一。

FastMCP 会把 Literal 类型自动转成 JSON Schema 的 `enum`：

```json
{
  "category": {
    "type": "string",
    "enum": ["health", "study", "relation", "work", "create", "finance", "hobby", "soul"]
  }
}
```

**为什么重要**？因为 AI 大模型看到这个 schema 后，会**在生成参数之前就知道**只能传这 8 个值，从而避免传错（比如把"健康"传成 `"jiankang"` 或 `"sport"`）。

> 这是"从协议层约束 AI"的思想——不在代码里被动地 `if category not in [...]` 报错，而是用类型系统主动告诉 AI 边界。详见 `docs/MCP插件说明.md`。

---

## 2.5 传输方式：stdio vs streamable-http

MCP 有两种传输方式，Self Grow 都支持：

| 传输方式 | 场景 | 通信方式 | 客户端配置 |
|---------|------|---------|-----------|
| **stdio** | 本地 | 客户端 spawn 你的 Python 进程，通过标准输入/输出通信 | 配置命令 `python mcp_server.py` |
| **streamable-http** | 远程 | 起一个 HTTP 服务，客户端通过 URL 访问 | 配置 URL `http://host:port/mcp` |

```bash
# stdio（默认，本地客户端）
python mcp_server.py

# streamable-http（远程，多端接入）
MCP_TRANSPORT=streamable-http MCP_PORT=8000 python mcp_server.py
```

**stdio 的原理**：Claude Desktop 启动时，会执行你配置的 `python mcp_server.py` 命令，把这个进程的 stdin/stdout 当成一条"管道"，用 JSON-RPC 在这个管道里收发消息。进程生命周期由客户端管理。

**streamable-http 的原理**：起一个独立 HTTP 服务器，客户端用 HTTP 请求连过来。适合把 MCP 服务部署到服务器上供多个客户端共享。

## 2.6 工具的返回值与错误处理

### 返回值类型

FastMCP 工具可以返回多种类型，会自动序列化：

| 返回类型 | 序列化结果 | 适用场景 |
|---------|-----------|---------|
| `dict` | JSON 对象 | 结构化数据（查询结果） |
| `str` | 文本 | 简单说明 |
| `int` / `float` | 数字 | 计数、等级 |
| `list` | JSON 数组 | 列表 |
| Pydantic 模型 | JSON（按 schema） | 强类型结构 |

**项目结合**：`mcp_server.py` 的工具基本都返回 `dict`：

```python
@mcp.tool()
def query_user_stats() -> dict:
    user = get_user(DEFAULT_USER_ID)
    if not user:
        return {"error": "用户不存在"}
    return {"level": user["level"], "total_exp": user["total_exp"], ...}
```

### 错误处理模式

MCP 工具出错了怎么办？项目用的是**"返回错误信息而不是抛异常"**：

```python
@mcp.tool()
def record_action(category: CategoryId, detail: str, duration: int, ...) -> dict:
    if duration < 0:
        return {"success": False, "message": "时长不能为负数"}   # 返回错误，不抛异常
    return create_action_and_award_exp(...)
```

**为什么要返回错误而非抛异常**？

- MCP 工具是"给 LLM 用"的。LLM 看到 `{"success": false, "message": "时长不能为负数"}` 后，能**理解错误原因并自己纠正**（比如改成合法值重试）。
- 如果直接抛异常，LLM 拿到的是晦涩的堆栈信息，很难自我纠错。

**通用约定**（本项目采用）：

```python
# 成功
{"success": true, "data": ...}
# 失败（可理解的错误）
{"success": false, "message": "人类可读的错误原因"}
```

## 2.7 FastAPI 和 FastMCP 的对比总结

| 维度 | FastAPI | FastMCP |
|------|---------|---------|
| 协议 | HTTP（REST） | MCP（JSON-RPC） |
| 服务对象 | 浏览器/App（人） | AI 客户端（大模型） |
| 入口粒度 | 路由（URL + 方法） | 工具（函数 + 描述） |
| 参数来源 | 路径/查询/请求体 | 类型注解自动生成 schema |
| 文档 | Swagger UI（`/docs`） | 工具描述（docstring） |
| 校验 | Pydantic | Literal + 类型注解 |
| 鉴权 | 依赖注入（本项目较弱） | 环境变量（单用户） |

**一句话总结**：FastAPI 是"给人用的 HTTP 接口"，FastMCP 是"给 AI 用的工具接口"。同一个业务逻辑，用不同的"门面"对外暴露。

---

# 第三部分：FastAPI 与 FastMCP 的协作

Self Grow 里，FastAPI 和 FastMCP 是**一内一外**的两个入口，互补不冲突：

| 维度 | FastAPI（HTTP API） | FastMCP（MCP 工具） |
|------|--------------------|---------------------|
| 服务对象 | 浏览器前端（`localhost:3000`） | AI 客户端（Claude Desktop 等） |
| 交互方式 | 人点按钮、填表单 | AI 用自然语言调用 |
| 请求格式 | HTTP + JSON（REST 风格） | JSON-RPC（MCP 协议） |
| 用户身份 | URL 上的 `user_id` | `SELF_GROW_USER_ID` 环境变量 |
| 代码位置 | `backend/routers/*` + `main.py` | `backend/mcp_server.py` |

**关键设计**：两者**共享同一套业务层**（`db/`、`services/`），没有重复代码。比如"记录行动"这个业务逻辑：

- FastAPI 路径：`POST /api/actions` → `routers/actions.py` → `services/exp_service.py`
- MCP 路径：`record_action` 工具 → `mcp_server.py` → **同一个** `services/exp_service.py`

```python
# mcp_server.py 的 record_action 工具，直接复用业务层
return create_action_and_award_exp(
    user_id=DEFAULT_USER_ID,
    category=category,
    duration=duration,
    ...
)
```

这就是好的架构分层：**协议层（HTTP / MCP）薄薄一层，业务逻辑沉在 services 层**，多一个入口就多一层适配，不改业务核心。

### 选型决策树

新增一个"入口"时，该用 FastAPI 还是 FastMCP？

```
这个入口给谁用？
  ├─ 给人用（浏览器、App、脚本）→ FastAPI（HTTP 接口）
  └─ 给 AI 用（Claude、Cursor、Agent）→ FastMCP（MCP 工具）
        │
        └─ 两种都要？→ 都建，共享同一个 services 层（本项目就是这样）
```

**项目现状**：Self Grow 的"记录行动"能力同时暴露在两个入口——FastAPI 的 `POST /api/actions`（给前端页面）和 FastMCP 的 `record_action` 工具（给 AI 客户端），两者共享 `services/exp_service.py`。

---

# 第四部分：常见问题 Q&A

**Q1：FastAPI 一定要用 async 吗？**

不是。FastAPI 同时支持 `def`（同步，丢线程池）和 `async def`（异步，事件循环）。但如果端点里有 `await`（等 I/O），就该用 `async def` 发挥并发优势。详见 `docs/异步编程学习指南.md`。

**Q2：FastMCP 的工具能被 ChatGPT 调用吗？**

取决于 ChatGPT 的客户端是否支持 MCP。MCP 是开放协议，目前 Claude Desktop、Cursor、Cline、WorkBuddy 等都支持。OpenAI 官方也在跟进 MCP 支持。只要客户端支持 MCP 协议，就能调用你的工具。

**Q3：MCP Server 里能不能调用 AI（反过来）？**

能，但要注意区分角色：

- **MCP Server 本身通常不调 AI**，它只是"定义 + 执行工具"
- 但你的工具函数**内部可以调 AI**——比如 Self Grow 的 `record_action` 工具内部会走经验结算，如果将来加"AI 自动分类行动"，工具内部就会调 AI

**Q4：为什么我的 MCP 工具没被 AI 正确调用？**

90% 是**描述（docstring）写得不够清楚**。AI 靠 docstring 判断"什么时候该调这个工具"。改进方向：

- docstring 写清"这个工具做什么、什么时候用、参数各是什么意思"
- 用 `Literal` 约束枚举参数（本项目就是这么做的）
- 提供参数示例（如"跑步 30 分钟"）

**Q5：FastAPI 和 Flask 能混用吗？**

不建议。一个项目选一个 Web 框架就好。本项目统一用 FastAPI，所有 router 都挂在一个 `app` 上。

**Q6：CORS 的 `allow_origins=["*"]` 有什么风险？**

`*` 表示允许任何网站的前端调用你的 API，包括恶意网站。开发阶段方便，生产环境应该改成具体域名（如 `https://yourdomain.com`）。

---

## 附录：术语表

| 术语 | 大白话解释 |
|------|-----------|
| **API** | 程序之间通信的接口，定义了"发什么、收到什么" |
| **REST** | 一种 API 设计风格，用 HTTP 动词（GET/POST/PUT/DELETE）+ 路径表达操作 |
| **路由（Route）** | 一条"URL → 处理函数"的映射规则 |
| **依赖注入（Depends）** | 在函数执行前自动准备它需要的参数 |
| **中间件（Middleware）** | 夹在"请求进来"和"响应出去"之间的钩子 |
| **Pydantic** | FastAPI 内置的数据校验库，靠类型注解自动校验 |
| **async/await** | Python 的异步编程语法，让等待 I/O 时能处理别的任务 |
| **SSE** | 服务器向浏览器单向持续推送数据的技术 |
| **MCP** | 让 AI 调用工具的开放标准协议（模型上下文协议） |
| **FastMCP** | MCP Python SDK 的高级封装，类似 FastAPI 之于 HTTP |
| **JSON-RPC** | 用 JSON 字符串调远程函数的一种简单协议 |
| **stdio** | 标准输入/输出，MCP 的一种本地通信方式 |
| **Literal** | Python 类型注解，限定参数只能取某几个值 |
| **enum** | JSON Schema 里的"可选值列表"，AI 靠它知道参数边界 |
