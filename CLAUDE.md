# CLAUDE.md

本文件为 Claude Code (claude.ai/code) 提供本仓库的代码指引。

## 项目概述

**Self Grow (个人成长系统)** — 基于原生 HTML/CSS/JS 的单页应用 + FastAPI 后端的个人成长追踪系统。核心功能包括：等级段位体系、习惯追踪、任务管理、目标规划、八维属性雷达图、奖励商城（含条件解锁/领取双重校验）、可视化技能树编辑器（AI 生成节点走 **LangGraph**）、**表达训练系统（AI 出题 + 实时语音 + 评分 + 填充词检测）**、**统一协调 Agent（多智能体 + 反问机制 + 悬浮球对话）**、**AI 资讯板块（GitHub 趋势 + 国内/国际资讯 + 每日 AI 分析）**、**MCP 插件（24 个业务工具暴露）**、**用户中心（多模型管理 + 账户安全）**、**JWT 登录鉴权（Access/Refresh 双令牌 + RBAC + API Key）**。部署方式为纯 Web + [Docker 技术详解与部署实战](docs/Docker技术详解与部署实战.md)。

**规模速查（2026-09-24 实测，引用前先自己跑一遍）**

| 项 | 值 |
|---|---|
| 后端 | **91 py 文件 / 17.5k 行**（不含 `tests/`）；测试另有 **22 文件 / 6.1k 行** |
| 前端 | **28 js 文件 / 19.0k 行** + 9 css / 10.5k 行 + 3 html |
| 数据 / 接口 | **29 张表** + **101 个 HTTP 端点**（用 `app.openapi()` 数，别 grep 装饰器） |
| 测试 | **295 passed**（pytest，AI 全打桩）+ 前端 5 个 Node 逻辑测试文件 |
| 集成 | 24 个 MCP 工具 · 8 个 SSE 流式端点 · 7 个 AI 场景 · 8 维 + 10 段位 |

> 数据库是 **MySQL 8.0，单后端**。2026-09-23 已**彻底移除 SQLite**（方言层删除、
> SQL 固化为 MySQL 原生）—— 见下方「数据库（MySQL，唯一后端）」。

**动手改代码前，先看这两条最容易犯的**：

1. **调 `get_llm()` 必须显式传 `user_id`** —— 内部是 `user_id or 1`，漏传会**静默**用错用户
   的模型配置（症状："我在用户中心换了模型，这个功能却没变"）。图/工厂是模块级单例时最易犯，
   工厂必须**接收 state**。测试里有一条项目级护栏扫全部调用点。
2. **工具执行前必须过 `coerce_json_args()`**（`services/tool_args.py`）—— 模型常把 list/dict
   参数序列化成 JSON 字符串，LangChain 校验直接拒收 → 工具永远执行不了、模型反复重试
   （实测一轮烧 93 秒只建出 1 个节点）。两处执行点：`skill_tree_ai/node.py`、
   `coordinator/agents/base.py`。

## 架构概览

```
self_grow_system/
├── frontend/              # SPA（无框架，纯原生 JS）
│   ├── index.html         # 应用壳 — 侧边栏、页面容器、模态框、SVG 渐变色定义
│   ├── favicon.svg        # 站点图标（后端 /favicon.ico 也读它）
│   ├── css/               # 加载顺序：variables → layout → sidebar → components → pages
│   ├── js/                # 加载顺序：auth → data → router → utils → components → pages → app
│   │   ├── auth.js        # ★ 登录态：包装 window.fetch 自动带凭证 + 401 自动续期（必须最先）
│   │   ├── data.js        # AppData 全局数据模型 + 8 维 SVG 图标定义
│   │   ├── router.js      # navigateTo() — SPA 路由，PAGE_JS_MAP 懒加载映射
│   │   ├── utils.js       # 工具函数（toast、模态框、等级公式、段位配色、后端 API 封装 60+ 函数）
│   │   ├── components.js  # 可复用渲染函数（统计卡片、经验条、进度条）
│   │   ├── sse.js         # ★ SSE 流式读取（fetch + getReader；主应用与 skill-tree 共用）
│   │   ├── chat.js        # 协调 Agent 悬浮球对话框（流式渲染 + 反问卡片串行队列）
│   │   ├── pages/         # 每页一个文件，通过 router.js 动态加载
│   │   │   ├── agent.js   # 表达训练 — AI 出题、答题计时、填充词检测、AI 评分（四维打分）
│   │   │   ├── usercenter.js # 用户中心 — 基础信息 + 账户安全（改密/API Key/登出）+ 多模型管理
│   │   │   └── ...        # 其他 9 个页面文件
│   │   └── app.js         # 启动初始化 + 全局版本号显示
│   └── skill-tree/        # 技能树编辑器（独立 SPA；查看模式人人可进，编辑模式仅管理员）
├── backend/               # Python FastAPI 服务（模块化架构）
│   ├── main.py            # 入口点：app 工厂、生命周期、路由注册、定时任务、/ 与 /favicon.ico
│   ├── config.py          # 配置：AI 端点/Key/模型、端口、DB_BACKEND + MySQL 连接参数、前端目录、JWT、CORS、git 版本号
│   ├── mcp_server.py      # MCP 插件 — FastMCP，24 个业务工具（stdio 免鉴权 / HTTP 强制 X-API-Key）
│   ├── tools/init_password.py  # 初始化/重置账号密码（pixi run init-password）
│   ├── pixi.toml          # pixi 环境（唯一依赖事实源，见 tools/export_reqs.py）
│   ├── models/            # 数据模型（等级公式、常量、段位表）
│   ├── schemas/           # Pydantic 请求/响应模型（limits.py = 输入长度上限集中管理）
│   ├── db/                # 数据访问层（每个模块一个功能域，含 auth.py、model_configs.py、task_history.py）
│   │   ├── backend.py      # ★ MySQL 连接池（PooledDB）+ 连接/游标代理 + 锁等待超时
│   │   ├── connection.py   # 门面：get_conn / now_str / placeholders（IN 占位符唯一入口）
│   │   ├── jsoncols.py     # JSON 列统一读法 jloads()（`dict.get` 的默认值对 NULL 无效！）
│   │   ├── init.py         # 建表（29 张）+ 默认数据 + 幂等迁移（含 JSON 列加宽）
│   │   └── testing.py      # 测试库隔离（删表重建，带「库名须含 test」安全闸）
│   ├── services/          # 业务逻辑层
│   │   ├── auth_service.py # ★ 登录鉴权：bcrypt 哈希、JWT 签发/验签、Refresh 轮换、API Key、失败锁定
│   │   ├── logging_setup.py # ★ 日志唯一配置入口（config.py 模块尾部调用；刻意不 import 项目模块）
│   │   ├── middleware.py   # 纯 ASGI 中间件：request_id 注入 + 访问日志（保 SSE 不被缓冲）
│   │   ├── llm.py         # ★ 多模型热切换（六元组缓存；**调用必须带 user_id**）
│   │   ├── tool_args.py   # 工具参数容错 coerce_json_args()（见上文第 2 条硬约定）
│   │   ├── aiconsult_service.py / aiconsult_analysis_service.py  # AI 资讯抓取 + 每日分析
│   │   ├── ai_client.py   # 统一 AI HTTP 客户端（动态读取启用模型配置）
│   │   ├── coordinator/   # 统一协调 Agent — 主图路由 + 6 子 Agent + ask_user 反问
│   │   │   ├── graph.py   # 主图编译 + run/resume
│   │   │   ├── router_node.py    # LLM 路由决策
│   │   │   ├── synthesize_node.py # 汇总回复
│   │   │   ├── agents/    # action/query/goal/task/habit/reward 6 个子 Agent
│   │   │   └── (LLM 实例见 services/llm.py — 跨协调 Agent 与技能树 AI 共用)
│   │   ├── skill_tree_ai/ # 技能树 AI 编辑（LangGraph）
│   │   │   ├── graph.py   # StateGraph 编译 + run/resume + _format_result
│   │   │   ├── node.py    # Agent 节点（LLM + 工具循环 + 上下文按「轮」裁剪）
│   │   │   ├── tools.py   # 8 个工具（按节点 ID 操作 + 确认守卫）
│   │   │   ├── state.py   # SkillTreeChatState（checkpointer 持久化）
│   │   │   └── prompts.py # ★ 技能树 AI 的提示词在**这里**（不在根 prompts/），保持精简
│   │   ├── expression_service.py  # 表达训练 AI 出题/评分 + 提示生成
│   │   └── ...            # 其他服务模块
│   ├── prompts/           # AI 系统提示词模板（**除技能树外**：coordinator / action_parse / habit_icon / expression）
│   ├── routers/           # API 路由层（共 101 个端点，OpenAPI 实测）
│   │   ├── deps.py            # ★ get_current_user（凭证解析链）+ require_admin（角色授权）
│   │   ├── auth.py            # ★ 登录鉴权 API（login/refresh/logout/password/me/api-keys）
│   │   ├── coordinator.py     # 协调 Agent API（chat/resume，**都是 SSE 流式**）
│   │   ├── skill_tree_ai.py   # 技能树 AI API（chat/resume，SSE 流式，替代旧 /api/chat，仅管理员）
│   │   ├── model_configs.py   # 模型配置 API（6 端点，含连通性测试）
│   │   ├── skill_tree.py      # 技能树 CRUD API（10 个端点，写操作仅管理员）
│   │   ├── aiconsult.py       # AI 资讯 API（5 端点；⚠️ `/{category}` 通配路由必须放最后）
│   │   └── ...            # 其他 10 个路由模块
│   └── tests/             # 测试（295 passed，LLM 全打桩、不联网；22 个文件）
│       ├── conftest.py    # ★ 在此设置 SELF_GROW_JWT_SECRET（必须早于 config 导入）
│       ├── helpers.py     # ensure_test_accounts / get_auth_headers
│       ├── test_auth.py                    # 登录鉴权
│       ├── test_sleep_action.py            # 睡眠行动 + 经验计算
│       ├── test_ai_action.py               # AI 行动解析
│       ├── test_streaming.py               # SSE 流式：协议/心跳/发射器并发隔离
│       ├── test_skill_tree_permissions.py  # 角色权限与越权拦截
│       ├── test_skill_tree_persistence.py  # 技能树持久化（真实体量写读 / 并发 upsert / id 契约）
│       ├── test_skill_tree_ai_tools.py     # 技能树 AI：工具 / 参数容错 / 提示词 / 上下文窗口
│       ├── test_model_configs.py           # 模型配置（"切了模型不生效"的回归）
│       ├── test_aiconsult_analysis.py      # AI 分析：提示词约束 / token 上限 / user_id 传递
│       ├── test_hardening.py / test_logging.py / test_security_fixes.py
│       ├── test_time_consistency.py        # 时间口径统一
│       ├── test_dimension_invariant.py     # 维度不变式
│       ├── test_coordinator_interrupt.py   # 反问交互：会话锁/skip
│       ├── test_mcp_auth.py                # MCP HTTP API Key 鉴权
│       ├── test_expression_endpoints.py    # 表达训练接口（派生表别名）
│       └── test_sql_dialect_lint.py        # ★ 静态护栏 15 项（唯一的防回退机制）
├── docs/                  # 项目文档（17 篇，见 README「项目结构」）
│   ├── 技能树编辑器技术详解.md / 统一协调Agent设计方案.md / 登录鉴权方案选型.md  # ★ 主力文档
│   ├── 维度经验计分规则.md / MCP插件说明.md / 项目坑与面试讲解.md
│   └── 其余 8 篇为技术学习指南（LangGraph / FastAPI / 异步 / 性能 / 数据库 / 网络 / 设计模式 / 浏览器）
└── memory/                # 开发记录（按日期，57 篇）
```

### 关键架构决策

- **前端路由**：手写 SPA 路由 `navigateTo()`（`router.js`），页面是 `<div class="page">` 容器，通过 `.page--active` 切换。侧边栏支持"行动"/"任务"/"技能"/"扩展"四级子导航。
- **数据层**：前端 `AppData` 对象（`data.js`）启动时通过 `Promise.all` 并行加载 8 个后端 API。后端不可用时降级使用模拟数据。后端 profile API（`/api/users/profile`）覆盖 `AppData.user` + `AppData.todayStats` + `AppData.yesterdayStats`。
- **经验系统**：全局总经验 = 8 维经验之和（`get_total_exp_from_dimensions()`），每次获得经验时实时 SUM 并重新计算等级。等级公式唯一来源：`backend/models/level.py`。
- **技能树**：独立 SPA 位于 `skill-tree/`，使用自定义 `TreeRenderer`（DOM + SVG）渲染节点和连线。AI 集成（`AIBridge`）通过 LangGraph 端点 `/api/skill-trees/{id}/chat` 调用后端 Agent 图（服务端 checkpointer 维护会话），工具按节点 ID 操作，危险操作走确认卡片（`pending_confirmation` + `/chat/resume`）。后端持久化替代了 localStorage。
- **统一协调 Agent**：三段式线性编排（**不是 LangGraph StateGraph**）：LLM 路由 → `asyncio.gather` 并行派发 6 个子 Agent（action/query/goal/task/habit/reward）→ 汇总；子 Agent 内部各自是独立 ReAct 循环。反问**不用官方 `interrupt()`**，而是普通 `ask_user` 工具 + `needs_user` 标志 + resume 时追加 HumanMessage（官方 interrupt 在多域并行下无法表达「各域独立中断」）。防循环三闸：`MAX_ITERS=8` / `MAX_ASK_ROUNDS=3` / `MAX_HISTORY=10`。
- **SSE 流式**：全部 8 个 AI 端点都是 `POST + SSE`，统一实现在 `services/sse.py`（事件只有 `stage`/`token`/`error`/`done` 四种，`done` 携带与改造前逐字相同的字段）。阶段事件靠 **`ContextVar` 发射器**穿透 router→graph→agent→tool 的深层调用链；未启用流式时是完全 no-op。**前端不能用原生 `EventSource`**（不能自定义请求头，而身份靠 `auth.js` 包装 fetch 注入 Bearer），统一走 `js/sse.js` 的 `streamSSE()`。
- **会话级处理中锁**：`/api/coordinator/chat` 与 `/resume` 对同一 `thread_id` 只允许一个写请求，冲突返回 **409** —— 防「连点/多标签页导致子图重复执行、写库类工具重复写入」。占用在返回流**之前**（才拿得到干净的 409），释放在 runner 的 `finally`。前端配套**串行提交队列**（`chat.js::_answerJobs`），`/resume` 的 `skip: true` 表示跳过提问（不重跑子图，直接标记该域完成）。
- **多模型动态切换**：`model_configs` 表按用户存储 LLM/ASR 配置，`coordinator/llm.py` 的 `get_llm(user_id)` 动态读取启用配置（缓存 key 含 model/base_url/api_key），切换后自动重建实例。`ai_client.py` / `asr_service.py` / 习惯 AI / 表达训练 WebSocket 同样动态读取。
- **表达训练**：扩展侧边栏 → AI Agent 页面，前端 `agent.js` 渲染两视图（训练/历史），后端 `expression_service.py` 处理 AI 出题/评分逻辑，`expressions.py` 管理数据库题目/回答。
- **JS 加载顺序**：`auth.js` → `data.js` → `router.js` → `utils.js` → `components.js` → 页面脚本 → `app.js`。顺序重要：`auth.js` 必须先包装 `window.fetch`，后面的脚本才会自动带凭证。
- **登录鉴权**：凭证解析优先级 ① `SELF_GROW_TRUSTED_MODE` ② `Authorization: Bearer` ③ `X-API-Key` ④ 401，全部收敛在 `routers/deps.py` —— 当初把 `get_current_user` 抽出来，这次 73 个业务端点一行未改就完成了全局鉴权升级。**旧的 `?user_id=` 不再作为身份依据**。
- **角色授权**：`require_admin` 依赖挂到技能树的 create/update/publish/delete 与 AI 的 chat/resume（AI 能改树，按写操作管）。技能树编辑器三道防线：入口不渲染（UX）→ 页面启动查 `/api/auth/me`，非 admin 不 `new App()`（兜底）→ 后端 `require_admin`（**真正的锁**）。
- **日志与请求上下文**：`services/middleware.py` 是纯 ASGI 中间件（不破坏 SSE），负责生成
  `request_id` 并写访问日志；`ContextVar` + `LogFilter`（挂 handler）让它能穿过 `asyncio.to_thread`。
  配置入口只有 `services/logging_setup.py` 一个，由 `config.py` 模块尾部调用。
- **输入长度上限集中在 `schemas/limits.py`**：pydantic 模型用 `Field(max_length=)`，
  裸 `dict` 参数用 `check_length()` / `check_history()`。**条数与总字符数两个维度都要卡**。
- **AI 功能的两条硬约定**（见文首）：`get_llm()` 必须传 `user_id`；工具执行前过 `coerce_json_args()`。

## 启动方式

后端统一用 pixi 管理环境与任务（依赖来源见 [依赖管理](#依赖管理)）：

```bash
# 开发模式：后端（backend/ 下运行）
cd backend
pixi install                 # 首次
pixi run init-password       # 初始化账号密码（test / admin）
pixi run start               # http://localhost:3001（自动拉起 APScheduler 定时任务）
pixi run test                # 运行 pytest（当前 295 passed；MySQL 后端建议分批跑，见「数据库」）
pixi run mcp                 # MCP 插件服务器（stdio，见 docs/MCP插件说明.md）
pixi run export-reqs         # 导出锁定版 requirements.txt
```

> **必须配置 `SELF_GROW_JWT_SECRET`**，缺失会在启动时直接拒绝（不会"能启动但一登录就 500"）。
> 生成：`openssl rand -hex 32`（Windows 可用 PowerShell 随机串）。
> 启动后控制台打印的是 `http://localhost:3001` —— **不要用 `0.0.0.0` 访问，那是监听地址**。

前端两种形态：

```bash
# 方式 A（推荐）：后端同源提供 —— backend/.env 里设置
SELF_GROW_FRONTEND_DIR=D:/pycharm/projec/self_grow_system/frontend
# 然后浏览器打开 http://localhost:3001 → 登录页

# 方式 B：前端独立服务器（改前端免重启后端）
cd D:\pycharm\projec\self_grow_system
npx http-server -p 3000 -c-1     # 或 python -m http.server 3000
# 浏览器打开 http://localhost:3000/login.html
```

> CORS 默认放行 **localhost / 127.0.0.1 的任意端口**（`allow_origin_regex`），所以 3000 / 5173 / 5500 都能直连。
> `file://` 直接双击打开会被浏览器拦（Origin 为 null），登录页会给出明确提示。
> 公网部署请用 `SELF_GROW_CORS_ORIGINS` 显式指定来源。

默认账号：`test / test123456`（普通用户，无技能树编辑器入口）、`admin / admin123456`（管理员）。

### 依赖管理

**`backend/pixi.toml` 的 `[dependencies]` / `[pypi-dependencies]` 是唯一事实源**，开发环境由 pixi 提供。

- `requirements.txt` 不是手写清单，而是由 pixi 锁定版本导出的产物（供 pip / Docker 安装，保证与开发环境版本一致）。
- 重新生成：`pixi run export-reqs`（即 `backend/tools/export_reqs.py`）。
- 改依赖：编辑 `pixi.toml` → `pixi update` → 必要时 `pixi run export-reqs`。不要在 requirements.txt 里裸改版本。

后端首次运行自动建表（**29 张**），包含两个默认用户：`test`（Lv.188，普通用户，含完整模拟数据）和 `admin`（Lv.99，管理员，技能树编辑权限）。密码需用 `pixi run init-password` 初始化。

**数据库只支持 MySQL**，配置就是这五个环境变量：

```bash
SELF_GROW_MYSQL_HOST / PORT / USER / PASSWORD / DATABASE
```

> ⚠️ `SELF_GROW_MYSQL_HOST` 在 docker-compose 里必须是 **服务名 `mysql`**，写 `127.0.0.1` 会指向 app 容器自己。
>
> `SELF_GROW_DB_BACKEND` / `DB_PATH` / `data.db` 都**不存在了**（2026-09-23 移除 SQLite）。
> 老部署里若还留着 `SELF_GROW_DB_BACKEND`，启动时会打一条 WARNING —— 读但不认，
> 避免"改了没生效"的困惑（那段兼容代码在 `config.py` 尾部）。

> ⚠️ 踩过的坑：`passlib[bcrypt]` 与 bcrypt ≥ 4.1 不兼容（bcrypt 移除 `__about__`），连普通密码都 hash 失败。
> 项目改用**直接调 bcrypt 官方 API**。另外 `pixi update` 会超时无输出，`pixi install` 才正常完成。

## 核心数据模型（AppData）

前端全部状态集中在全局 `AppData` 对象中：

- `AppData.user` — 用户信息（name、level、exp、streak、joined）
- `AppData.todayStats` / `AppData.yesterdayStats` — 今日/昨日统计
- `AppData.categories` — 8 个属性维度定义（健康/学习/关系/工作/创作/财务/爱好/魅力）
- `AppData.attributes` / `AppData.advancedAttributes` — 雷达图各维度数值
- `AppData.attributeDetails` — 各维度等级/经验/备注/描述
- `AppData.habits` — 习惯列表（含 status 今日打卡状态）
- `AppData.lastWeekHabits` — 上周习惯打卡数据（热力图用）
- `AppData.goals` — 目标列表（含里程碑）
- `AppData.tasks` — todo/doing/done 三栏任务
- `AppData.taskHistory` — 已完成/超期任务
- `AppData.rewards` — 奖励商城
- `AppData.actionCenter` — 行动中心数据（维度进度、动态播报、本周任务）
- `AppData.profile` — 个人统计、年度热力图数据、维度等级
- `AppData.recentActivities` — 近期活动动态
- `AppData.scheduledTasks` — 每日定时任务模板
- `AppData.weeklyTaskTemplates` — 每周任务模板

## 常用开发任务

### 新增页面
1. 在 `frontend/index.html` 中添加 `<div id="page-{name}" class="page">`
2. 创建 `frontend/js/pages/{name}.js`，导出 `render{Name}()` 函数
3. 在 `router.js` 的 `PAGE_JS_MAP` 和 `navigateTo()` 的 `renderers` 映射表添加条目
4. 在 `index.html` 侧边栏添加导航项
5. 在正确的加载顺序位置添加 `<script>` 标签（在 `app.js` 之前）

### 修改等级/段位系统
- 前端公式：`frontend/js/utils.js`（`expForLevel` / `getRankInfo` / `getRankColors`）
- 后端公式：`backend/models/level.py`（等级公式唯一来源）
- 数据库：`backend/db/dimensions.py`（维度经验管理）+ `backend/db/init.py`（建表）
- 视觉主题：`frontend/js/utils.js`（10 个段位的渐变色方案）

### 修改经验计算规则
- 后端规则引擎：`backend/models/constants.py`（`calculate_exp()` 函数，各维度子函数）
- 维度经验值在此计算，然后由 `exp_service.py` 汇总到 total_exp 并重算等级
- 注意幂等：`create_action_log` 写入时 `exp_earned` 先占位 0，`award_exp_and_recalc` 后回写（防重复结算跳过）
- 计分规则文档：`docs/维度经验计分规则.md`

### 技能树开发
- 编辑器入口：`frontend/skill-tree/index.html`（独立页面，不依赖主 SPA，支持 role 参数）
- 查看器：`frontend/skill-tree/index.html?role=user`（由 skills.js 通过 iframe 嵌入；
  历史上的 `viewer.html` 已于 2026-09-17 删除，功能被它完全覆盖）
- 主控制器：`skill-tree/js/app.js`（App 类，包含 CRUD、撤销/重做、AI 集成）
- 渲染引擎：`skill-tree/js/tree-renderer.js`（DOM + SVG 渲染）
- AI 集成：`skill-tree/js/ai-bridge.js`（LangGraph 端点 `/api/skill-trees/{id}/chat`，服务端会话 + 确认卡片）
- 后端持久化：`backend/routers/skill_tree.py` + `backend/db/skill_tree.py`
- 后端 AI 图：`backend/routers/skill_tree_ai.py` + `backend/services/skill_tree_ai/`（LangGraph StateGraph，单 agent 节点 + **8 个工具**，按节点 ID 操作）
- **编辑器交互的硬约定**（用户明确要求过，别改回去）：
  - **拖节点必须 `Ctrl/Cmd + 左键`**；左键只选中不拖；框选整组也一样要按 Ctrl；Shift 是加减选；空格/中键平移
  - 网格是「**单位区域**」制（`unit=300` 画布 px）：区域 = 内容包围盒按 unit 取整外扩，空树给视口中心一格；
    接缝只画内部且很淡（`.grid-unit-seam`，opacity 0.18）—— 画成和外框一样明显会像"几块板子拼接"
  - 多选右键菜单 = 移动（跟随鼠标 + 再点放下 + 0.1s 防抖）/ 删除边（`edgesAmong` 只删两端都在选中集合里的）/ 删除结点
  - `#selection-box` 是 **SVG `<rect>`**：定位必须用 `setAttribute('x'/'y'/'width'/'height')`，
    `style.left/top` 对 SVG **无效**（这个框曾经因此从来没显示过）；框选层还要 `overflow: visible`
  - 快捷键在输入框聚焦时**不劫持**（在 AI 面板打字按 Ctrl+Z 不该回滚整棵树）
  - 列表对外的 `id` 必须是 **tree_id 字符串**（不是自增主键），否则前端拼出的
    `/api/skill-trees/{id}/chat` 会 404，**症状和"树没存上"一模一样**
  - 列表字段后端 snake_case → 前端 camelCase 的映射在 `utils.js::normalizeTreeEntry()`（不映射会显示"0 节点 + 日期空白"）
  - 全页面请求统一走 `utils.js::apiBase()` 绝对地址 + 显式带 token（相对路径跨源必失败）
  - AI 对话记录按树存 localStorage；上下文只带最近 **5 个来回**（按 HumanMessage 切点 —— 按条数切会产生孤儿 ToolMessage → LLM 400）
- 旧 `/api/chat`（原 `routers/ai.py` + `services/ai_service.py`）已彻底删除（无鉴权，2026-09-11 清理）
- 撤销/重做约定：历史栈为「改后快照」语义——所有操作先修改再 `saveHistory()`；`loadData()` 时清空历史并压入基线快照（防跨树污染）
- 权限约定：**仅管理员可进入编辑器**——三道防线：① `skills.js` 非 admin 不渲染入口 ② 编辑器启动调 `/api/auth/me` 校验，非 admin 不 `new App()` ③ 后端 `require_admin`（`routers/deps.py`）才是真正边界
- 详细文档：`docs/技能树编辑器技术详解.md`（编辑器 + Agent 全解析，1700+ 行）、`docs/技能树AI-LangGraph改造方案.md`

### 登录鉴权（JWT，2026-09-13 落地）
- 凭证解析链：`backend/routers/deps.py` —— ① TRUSTED_MODE ② `Authorization: Bearer` ③ `X-API-Key` ④ 401。**旧的 `?user_id=` 不再作为身份依据**
- 端点：`backend/routers/auth.py`（login / refresh / logout / password / me / api-keys）
- 服务：`backend/services/auth_service.py`（bcrypt 哈希、JWT 签发验签、Refresh 轮换、API Key）；SQL 在 `backend/db/auth.py`
- 前端：`frontend/js/auth.js` —— **包装 `window.fetch` 自动带 `Authorization` 并处理 401 自动续期**，因此 52 处 `fetch(...?user_id=)` 无需修改。**必须最先加载**（主应用 `js/auth.js`、技能树 `../js/auth.js`）
- 环境变量：`SELF_GROW_JWT_SECRET`（缺失即拒绝启动）、`SELF_GROW_JWT_OLD_SECRET`、`SELF_GROW_ACCESS_TTL`、`SELF_GROW_REFRESH_TTL`、`SELF_GROW_TRUSTED_MODE`、`SELF_GROW_CORS_ORIGINS`
- 注意：CORS 不能用 `*`（浏览器会拒绝携带凭证的响应）；refresh 走「Cookie + 响应体」双通道（`SameSite=Lax` 在跨域开发态不发 Cookie）
- 初始密码：`pixi run init-password`（默认 test→test123456、admin→admin123456）
- MCP：`mcp_server.py` 的 HTTP 传输强制 `X-API-Key`（stdio 模式不鉴权，本地进程可信）
- 测试：`tests/test_auth.py`(17) + `tests/test_skill_tree_permissions.py`(11) + `tests/test_mcp_auth.py`(6)
- **测试约定**：`SELF_GROW_JWT_SECRET` 必须在 `tests/conftest.py` 里设置（config 在 import 时读 env，写在测试文件里全量跑会失效）；公共登录方法放 `tests/helpers.py`（conftest 不在 sys.path，不能直接 import）
- 详细文档：`docs/登录鉴权方案选型.md`（选型论证）、`docs/安全设计说明.md`（威胁模型 + 已知风险清单）

### 统一协调 Agent 开发
- 前端：`frontend/js/chat.js`（悬浮球 + 对话框 + 流式渲染 + 反问卡片**串行提交队列**）
- 后端主图：`backend/services/coordinator/graph.py`（`run_coordinator` 非流式 / `run_coordinator_stream` 流式）
- 回归测试：`backend/tests/test_coordinator_interrupt.py` + `frontend/tests/interrupt-submit.test.mjs`
- 子 Agent：`backend/services/coordinator/agents/`（6 个域 Agent，基类 `base.py`）
- 反问机制：`agents/ask_user_tool.py` 公共工具 + dispatch interrupt 检测
- 提示词：`backend/prompts/coordinator.py`
- 设计文档：`docs/统一协调Agent设计方案.md`

### MCP 插件开发
- 服务器：`backend/mcp_server.py`（FastMCP，6 域 24 工具，复用 `db/`、`services/` 层）
- 枚举约束用 `typing.Literal`（category/sub_type/priority/status 等），数值范围函数内校验
- **两种传输的鉴权差异**（2026-09-13）：
  - `stdio`（默认）：**不鉴权（刻意）**——本地 spawn 的子进程，进程边界即信任边界；身份由 `SELF_GROW_USER_ID` 决定
  - `HTTP`（`MCP_TRANSPORT=streamable-http`）：**强制 `X-API-Key`**——`ApiKeyMiddleware`（文件底部）+ `build_http_app()` + `uvicorn.run`；身份由 Key 解析后写入 `_mcp_user_id` ContextVar，24 个工具通过 `current_user_id()` 读取 → **HTTP 模式支持多用户**，`SELF_GROW_TRUSTED_MODE=1` 可关闭
- 测试：`tests/test_mcp_auth.py`；文档：`docs/MCP插件说明.md`
- （原来的 `backend/test_mcp_client.py` 手动脚本已于 2026-09-17 删除，改用 `pixi run mcp` 直接试）

### 表达训练开发
- 前端页面：`frontend/js/pages/agent.js`（`renderAgent()`，两视图，训练/历史滑块切换）
- 填充词检测：`agent.js` 中 `detectFillerWordsV2()` — 四重规则（密度、高频重复、句首、簇拥）
- 后端路由：`backend/routers/expression.py`（11 个端点）
- 数据库操作：`backend/db/expressions.py`（题目 CRUD + 回答 CRUD + 用户统计）
- 业务逻辑：`backend/services/expression_service.py`（出题/评分/提示生成，含 LLM 调用）
- AI 提示词：`backend/prompts/expression.py`（三套提示词：出题、评分、提示生成）
- 样式：`frontend/css/pages.css`（`.expr__*` 类，~300 行）
- 出题流程：AI 调用 `query_history_questions` 工具查重 → 生成新题 → 存入数据库
- 评分流程：回填填充词统计 → AI 四维评分 → 缓存结果到数据库

### 日志系统（2026-09-23 补，原来完全没有）

- 唯一配置入口：`backend/services/logging_setup.py`，由 **`config.py` 在模块尾部**调用
  （config 是所有模块的必经入口，能保证早于那几条 import 期 warning）。
  ⚠️ 它**刻意不 import 任何项目模块** —— 想加 import 前先想清楚是不是会成环
- 请求链路：`services/middleware.py` 是**纯 ASGI 中间件**（不是 `BaseHTTPMiddleware`，
  那个会把 SSE 缓冲住）。它给每个请求生成 `request_id` 塞进 `ContextVar`，
  `LogFilter` 挂在 **handler** 上（挂 logger 上，子 logger 冒泡的记录不生效）
- 日志文件按组件分：`app.log` + `mcp.log`（两个容器共享 `/data` 卷）；
  `mcp_server.py` 在 import config **之前**设 `SELF_GROW_LOG_COMPONENT=mcp`
- 排查"模型收到了什么提示词"：把 `SELF_GROW_LOG_LEVEL` 调成 `DEBUG` 再重启
  （技能树 `node.py` 有 DEBUG 分支会打出两条 SystemMessage 原文）
- ⚠️ 别在代码里再调 `logging.basicConfig()`（会和这里的配置打架）

### AI 资讯板块开发

- 数据抓取：`services/aiconsult_service.py`（GitHub 三段错峰：H-20 / H-10 / H:00 暂存，H:05 合并去重；
  另有国内 / 国际资讯）；调度在 `main.py`
- 榜单：`weekly`（本周涨幅 Top5）/ `daily`（本日涨幅）/ `news_hot`（资讯热度）。
  ⚠️ `daily` 需要**同一天至少两次快照**才有内容（语义是"今天涨了多少"）——
  白天才开的开发环境只攒到一两轮，榜为空是正常的
- 每日分析：`services/aiconsult_analysis_service.py`，**懒触发**（用户点进页面才生成，每天一份全局共享），
  两路 LLM 并发：摘要 + 翻译/打分
- 提示词要点：必须告诉模型"**这批材料本身就是按 AI/Agent/LLM 检索来的**"，
  否则它必然把检索条件当发现写（"GitHub 出现大量 Agent 项目"这种废话）。
  禁止清单要给**具体例句**，抽象规则对模型没用
- ⚠️ 翻译/打分任务的 `TRANSLATE_MAX_TOKENS` 是 `None`（不限），**别改回具体数字**
- ⚠️ 该模块所有 `get_llm(` 调用都必须带 `user_id=`（有一条项目级护栏扫全部调用点）

### 用户中心 / 模型配置开发
- 前端：`frontend/js/pages/usercenter.js`（基础信息卡 + **账户安全卡**：登录状态/改密/API Key/登出 + 模型信息卡，添加/编辑/删除/切换启用/连通性测试）
- 账户安全的四个全局函数：`doLogout()` / `openChangePasswordModal()` + `submitChangePassword()` / `openApiKeysModal()` + `createApiKey()` / `revokeApiKey()`
- 弹窗约定：主应用 `openModal(title, contentHtml, clickOutsideToClose)` **只有 3 个参数、没有 onConfirm**，提交按钮要写在 content 的 `onclick` 里；二次确认用 `utils.js` 的 `showConfirm()`（技能树那边也有同名函数）
- 数据层：`backend/db/model_configs.py`（CRUD + `set_active` 同类型互斥 + `get_active_config`）
- 路由：`backend/routers/model_configs.py`（6 个端点，含 POST /test 连通性测试）
- 动态生效：所有 AI 服务经 `get_llm(user_id)` / `ai_client.py` 读取启用配置，切换即生效（缓存 key 机制）
- 版本号：`config.get_version()`（git describe），`/api/health` 返回，前端右下角显示

### 后端 AI 服务
- **技能树 AI** → `backend/services/skill_tree_ai/`（LangGraph 图，**8 个工具**，配合 `routers/skill_tree_ai.py` 的 chat / chat/resume 两个 **SSE 流式**端点；旧的 GET `chat/stream` 假占位已删）
- **AI 资讯分析** → `backend/services/aiconsult_analysis_service.py`（懒触发；两路 LLM 并发：摘要 + 翻译/打分；
  ⚠️ 翻译/打分类任务**不限制输出 token** —— 撞上限会被截断 → JSON 没闭合 → 解析失败 →
  资讯榜整块消失，而且**日志里只有一句"生成成功"**）
- **统一协调 Agent** → `backend/services/coordinator/`（主/次多智能体架构 + ask_user 反问）
- **行动解析 AI** → `backend/services/ai_action_service.py`（对话式提取行动记录）
- **习惯分析 AI** → `backend/services/ai_habit_service.py`（智能洞察 + 图标分配）
- **表达训练 AI** → `backend/services/expression_service.py`（出题 + 评分 + 提示生成）
- AI 提示词在 `backend/prompts/`（技能树旧提示词在 `services/skill_tree_ai/prompts.py`）
- AI 配置通过 `backend/.env` 兜底：`AI_API_BASE_URL`、`AI_API_KEY`、`AI_MODEL`；实际运行时优先读 `model_configs` 表中当前启用的配置（用户中心可切换）

### 数据库（MySQL，唯一后端；2026-09-23 彻底移除 SQLite）

```bash
SELF_GROW_MYSQL_HOST / PORT / USER / PASSWORD / DATABASE   # 唯一的数据源配置
```

⚠️ **`SELF_GROW_DB_BACKEND` / `DB_PATH` / `data.db` / `db/dialect.py` 全都不存在了。**
源码里写的就是 MySQL 原生 SQL —— **不要再按 SQLite 风格写 SQL**（以前那句"写 SQLite 风格就够了、
连接层会自动转换"已经作废，那个转换层整文件删除了）。

**写 SQL 必须自己写对的（每一条都真炸过）**

1. **保留字列名手写反引号** —— 全库只有 `` `year_month` `` 与 `` `desc` `` 撞上。
   漏加 = 1064，且只有真走到那条 SQL 才炸。⚠️ 但别把 `ORDER BY x DESC` 的 `DESC` 也加反引号
2. **派生表必须有别名**（1248）—— 踩过 `/api/expression/stats` 曾 500 而**测试全绿**
3. **`TEXT` 不能有 DEFAULT（1101）、不能进键（1170）** —— 短文本 `VARCHAR(n) DEFAULT ''`，长文本 `TEXT NULL`
4. **`IN (...)` 占位符走唯一入口 `db.connection.placeholders(n)`** —— 手搓 `",".join("?" * n)`
   会报 `not all arguments converted during string formatting`，而且**静态护栏扫不到**
   （`?` 是运行时拼出来的）。实测：AI 分析每次打开都失败，空库时却一切正常
5. **JSON 列用 `db/jsoncols.py::jloads()`** —— `dict.get(k, default)` 对 NULL 无效
   （键存在、值是 None），`json.loads(None)` 会让读路径 500
6. **别用 `rowcount` 判归属/成败** —— MySQL 返回「实际改变行数」，内容没变时是 0
7. **「先 SELECT 判存在再写」是竞态** → 并发撞唯一键 **1062**。写成一条原子 upsert：
   建记录 `ON DUPLICATE KEY UPDATE id = LAST_INSERT_ID(id)`；
   改记录 ODKU + 每个 SET 里写归属守卫 `IF(user_id = VALUES(user_id), 新值, 旧值)`
8. **迁移后短列会吃数据** —— SQLite 无类型，`varchar(255)` 存几 KB JSON 也不报错；
   MySQL 下必然 **1406 Data too long**（空对象却存得进去，所以"建一条空记录"的冒烟测不出来）。
   `db/init.py::migrate_json_column_widths()` 读 `information_schema` 判类型自动加宽

**连接层**

- **连接池不能小**：协调 Agent 用 `asyncio.gather` 并行跑子 Agent，每个工具调用都
  `to_thread` + `get_conn()`。池满时 DBUtils 的 `blocking=True` 是**无限等待（无超时）** → 整站卡死。
  默认 20（`SELF_GROW_MYSQL_POOL_SIZE`）
- ⚠️ **`lock_wait_timeout` / `innodb_lock_wait_timeout` 在连接层设成 30 秒**
  （`db/backend.py::_INIT_COMMAND`）。MySQL 默认 `lock_wait_timeout` 是 **31536000 秒（一年）**，
  配合 `blocking=True`（同样无超时），一旦有锁竞争就是「不报错也不返回、整站挂死」——**实测卡过且无任何日志**
- ⚠️ **时区那行不能删**：连接层 `SET time_zone='+08:00'`，建表默认值 `now()` 走的就是它。
  删了就整体偏 8 小时（表现为"刚记录完却显示 8 小时前"）
- ⚠️ **写操作的 `close()` 必须在 `finally`** —— 失败时跳过就会留下"锁坟场"：
  事务挂着不结束、行锁不释放，之后对该行任何 `DELETE` 都 `Lock wait timeout`
  （而 `SELECT` 照常成功，因为 MVCC 快照读）。判据：
  `information_schema.innodb_trx` 里有 `age_s` 很大、`trx_query` 是 `(idle)` 的事务

**测试**

```bash
cd backend
SELF_GROW_MYSQL_DATABASE=<自建一个库名含 test 的库> .pixi/envs/default/python.exe -m pytest tests/ -q -p no:randomly
```

- ⚠️ **库名必须含 `test`** —— `db/testing.py` 会拒绝重置其它库（保护真实数据的安全闸，**不要绕过**）
- 每个用 `tmp_db` fixture 的用例都会 DROP + 重建 29 张表 → **全量约 3 分钟**
- 当前全量：**295 passed**

**静态护栏 `tests/test_sql_dialect_lint.py`（15 项）= 唯一的防回退机制**

| 规则组 | 拦什么 |
|---|---|
| A | SQLite 残留写法（`?` 占位符、`AUTOINCREMENT`、`INSERT OR IGNORE/REPLACE`、`ON CONFLICT`、`datetime('now')`、`PRAGMA`…） |
| B | MySQL 硬性限制：派生表缺别名（1248）、保留字列名未加反引号（1064） |
| C | **手搓 `?` 占位符生成器**（`join("?"` / `"?" *` / `"?" for`）—— 扫 SQL 文本看不见的那类 |

⚠️ **取样别只看 `ast.Constant`**：Python 3.12 起 f-string 是 `JoinedStr`，会被拆成多个片段，
「有 SQL 关键字」与「有 SQLite 写法」被切进两个片段 → 准入判断一挡，**违规整条溜过**。
而动态 SET 子句只能用 f-string 拼 ⇒ 盲区正好开在所有动态 UPDATE 上。
（真事故：`PUT /api/model-configs/{id}` 500 而当时全量测试是绿的。）现在走 `_sql_text_units()`。
每条规则都配**灵敏度自测**（造违规要抓到 + 造正确写法不能误报）。

**历史材料**：SQLite→MySQL 迁移脚本已归档到 `backend/tools/archive/migrate_sqlite_to_mysql.py`
（SQLite 已不存在，留着是为了记录当时怎么迁的）。

### 生产部署（Docker）
- 详细方案：`docs/Docker技术详解与部署实战.md`；根目录已有 `Dockerfile` / `docker-compose.yml` / `.env.example` / `nginx/self-grow.conf.example`
- 依赖安装走 `requirements.txt`（由 `pixi run export-reqs` 从 pixi 锁定版本生成）
- **compose 服务**：`mysql`（8.0，不发布端口）+ `app` + `mcp` + 可选 `nginx`（`--profile with-nginx`）
  - `app` / `mcp` 都 `depends_on: mysql: condition: service_healthy` —— 用 `mysqladmin ping` 而不是 TCP 探测，因为初始化期间会有临时 server 监听 3306（TCP 通但 SQL 还不能跑）
  - MySQL 数据在 `mysql_data` 卷；`data` 卷保留 `uploads/`（奖励图片）与 `logs/`（`app.log` / `mcp.log`）—— **别删**
  - 备份：`docker compose exec mysql sh -c 'mysqldump -uroot -p"$MYSQL_ROOT_PASSWORD" --single-transaction --databases "$MYSQL_DATABASE"' > backup.sql`
- 测试：`cd backend && pixi run test`（当前 295 passed；MySQL 后端建议分批跑）
- 上线前检查清单见 `docs/安全设计说明.md` §11（密钥、TRUSTED_MODE、CORS、HTTPS、备份）

## 8 个属性维度的颜色约定

| 维度 | ID | 颜色 | 全局倍率 |
|------|-----|-------|----------|
| 健康 | health | `#FF7B72` | 1.0 |
| 学习 | study | `#58D5C9` | 1.0 |
| 关系 | relation | `#FF91A8` | 0.5 |
| 工作 | work | `#FFCA40` | 1.0 |
| 创作 | create | `#B794F6` | 0.5 |
| 财务 | finance | `#4ADE80` | 0.5 |
| 爱好 | hobby | `#F472B6` | 0.75 |
| 魅力 | soul | `#FBBF24` | 0.5 |

> **全局倍率（`global_rate`）** 是真正生效的系数：全局经验 = `dimension_exp × global_rate`。
> 各维度的具体分值由 `models/constants.py` 的 `_calc_*` 系列函数按「时长 / 子类型 / 作息 / 连击」硬编码算出。
>
> 这张表原来列的是另一个字段 `exp_rate`（10/10/8/12/8/6/7/9）—— 它**从来没被任何计分函数读取过**，
> 属于「设计了却没落地」的技术债，已于 2026-09-17 从代码里删除。
