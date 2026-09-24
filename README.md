# Self Grow — 个人成长系统

> 一个原生 HTML/CSS/JS 单页应用 + FastAPI 后端的个人成长追踪系统。包含等级段位体系、习惯追踪、任务管理、目标规划、八维属性雷达图、奖励商城（含条件解锁/领取双重校验）、可视化技能树编辑器（AI 生成节点走 **LangGraph**）、**表达训练系统（AI 出题 + 实时语音 + 评分 + 填充词检测）**、**统一协调 Agent（多智能体 + 反问机制 + 悬浮球对话）**、**MCP 插件（24 个业务工具暴露）**、**用户中心（多模型管理 + 账户安全）**、**JWT 登录鉴权（Access/Refresh 双令牌 + RBAC + API Key）**。部署方式为纯 Web + Docker。

**三项能力定位**：
- **28 张表 / 101 个 HTTP 端点 / 6 个 AI 场景**的完整业务后端
- **两套 LangGraph Agent**：统一协调 Agent（多智能体 + 反问）+ 技能树 AI（工具调用 + 危险操作确认）
- **完整的登录鉴权**：JWT 双令牌 + 角色授权 + 可撤销 API Key，覆盖浏览器 / MCP / 脚本三类客户端

---

## 项目结构

```
self_grow_system/
├── README.md                         # 项目文档（本文件）
├── CLAUDE.md                         # Claude Code 代码指引
├── index.html                        # 根入口 → 自动跳转 login.html
├── login.html                        # 登录页（用户名 + 密码；免鉴权模式下点卡片直进）
│
├── frontend/                         # 前端 SPA（无框架，纯原生 JS）
│   ├── index.html                    # SPA 主入口（登录后进入）
│   ├── favicon.svg                   # 站点图标（后端 /favicon.ico 也用它）
│   │
│   ├── css/                          # 样式文件（按层分拆，共 5 个文件）
│   │   ├── variables.css             # CSS 变量 / 主题（暖色调：翡翠绿+琥珀金）
│   │   ├── layout.css                # 布局（侧边栏 + 主内容区）
│   │   ├── sidebar.css               # 侧边栏样式
│   │   ├── components.css            # 组件样式（卡片、进度条、经验条等）
│   │   └── pages.css                 # 各页面独立样式（~165 KB，含表达训练 ~300 行）
│   │
│   ├── js/                           # JavaScript（加载顺序严格）
│   │   ├── auth.js                   # ★ 登录态管理：包装 window.fetch 自动带凭证 + 401 自动续期（必须最先加载）
│   │   ├── data.js                   # AppData 全局数据模型 + 8 维 SVG 图标定义
│   │   ├── router.js                 # SPA 路由 + 页面 JS 懒加载（PAGE_JS_MAP）
│   │   ├── utils.js                  # 工具函数（toast、模态框、等级公式、段位配色、后端 API 封装 60+ 函数）
│   │   ├── sse.js                    # ★ SSE 流式读取（fetch + getReader，零依赖；主应用与 skill-tree 共用）
│   │   ├── components.js             # 可复用渲染函数（统计卡片、经验条、进度条）
│   │   ├── chat.js                   # 协调 Agent 悬浮球对话框（流式渲染 + 反问卡片串行队列）
│   │   ├── app.js                    # 应用入口初始化（并行加载 8 个后端 API，降级容错 + 全局版本号）
│   │   └── pages/                    # 每页一个渲染器，首次访问时动态加载
│   │       ├── dashboard.js          # 仪表盘 — 打卡习惯列表、EXP 进度条、统计卡片、近期动态
│   │       ├── action.js             # 行动中心 — 计时器、维度进度、动态播报、本周任务
│   │       ├── history.js            # 成长记录 — 年度热力图、雷达图、30 天 EXP 趋势
│   │       ├── attributes.js         # 属性 — 8 维度等级 & EXP 进度、详细介绍
│   │       ├── goals.js              # 目标 — 创建/编辑/删除、里程碑、EXP 奖励领取
│   │       ├── tasks.js              # 任务 — 本日/本周三栏（todo/doing/done）、历史、模板
│   │       ├── habits.js             # 习惯 — 7 天周视图三态打卡、统计卡片、智能洞察
│   │       ├── skills.js             # 技能 — 技能卡片列表 → 技能树查看器（iframe）+ 技能库
│   │       ├── rewards.js            # 奖励商城 — 8 分类筛选、解锁/领取双重条件、图片上传
│   │       ├── agent.js              # 表达训练 — AI 出题、答题计时、填充词检测、AI 评分（四维打分）
│   │       └── usercenter.js         # 用户中心 — 基础信息 + 账户安全（改密/API Key/登出）+ 多模型管理
│   │
│   ├── skill-tree/                   # 技能树编辑器（独立 SPA，支持查看器/编辑/管理三模式）
│   │   ├── index.html                # 入口（角色模式：?role=user 查看 / editor 编辑 / admin 管理）
│   │   ├── css/
│   │   │   ├── style.css             # 主样式
│   │   │   ├── sidebar.css           # 侧边栏样式
│   │   │   └── detail-panel.css      # 详情弹窗样式
│   │   └── js/
│   │       ├── app.js                # 主控制器 — CRUD、撤销/重做、AI 集成
│   │       ├── tree-renderer.js      # DOM + SVG 渲染引擎
│   │       ├── ai-bridge.js          # AI 集成（LangGraph 端点 /api/skill-trees/{id}/chat）
│   │       ├── detail-panel.js       # 节点详情弹窗
│   │       ├── interaction.js        # 拖拽、缩放、连线交互
│   │       ├── sidebar.js            # 侧边栏 UI
│   │       ├── history.js            # 撤销/重做历史
│   │       └── utils.js              # 工具函数
│   │
│   ├── tests/                        # 前端逻辑回归测试（Node + 极简假 DOM，零依赖不开浏览器）
│   │   └── interrupt-submit.test.mjs # 反问卡片提交逻辑：连点防抖 / 串行队列 / 草稿保留 / 跳过（7 组场景）
│   │
│   └── assets/                       # 静态资源
│       └── icons/                    # 属性图标 SVG（8 维 + 行动 + 成长记录 + 标题等）
│
├── backend/                          # 后端 FastAPI 服务（模块化架构）
│   ├── main.py                       # 入口点：app 工厂、生命周期、路由注册、定时任务
│   ├── config.py                     # 配置从 .env 加载（AI 端点、Key、模型、端口、前端目录、git 版本号）
│   ├── mcp_server.py                 # MCP 插件 — FastMCP v2，24 个业务工具（stdio/HTTP 双传输）
│   │
│   ├── models/                       # 数据模型
│   │   ├── level.py                  # 等级公式（唯一来源，含满级处理）
│   │   └── constants.py              # 8 维分类定义、10 段位表、颜色映射、维度经验计算规则
│   ├── schemas/                      # Pydantic 请求/响应模型
│   │   └── api.py                    # 20 个请求模型（响应都是直接返回 dict，未挂 response_model）
│   │
│   ├── db/                           # 数据访问层（每模块一个功能域）
│   │   ├── backend.py                # ★ MySQL 连接池 + 连接代理（2026-09-23 起单后端）
│   │   ├── connection.py             # 对外门面：get_conn / now_str（时间口径的落地点）
│   │   ├── connection.py             # 门面：re-export get_conn / now_str（业务代码只认它）
│   │   ├── testing.py                # 测试库隔离（MySQL 下无文件可换 → 删表重建，带安全闸）
│   │   ├── init.py                   # 建表（22 张）+ 默认用户/奖励 + 数据迁移
│   │   ├── auth.py                   # 登录鉴权 SQL（refresh_tokens / api_keys / 密码与 token_version）
│   │   ├── users.py                  # 用户 + 每日统计 CRUD
│   │   ├── habits.py                 # 习惯 + 打卡记录 CRUD
│   │   ├── actions.py                # 行动记录 CRUD + 今日统计 + 动态播报 + 睡眠/复盘限制检测
│   │   ├── routines.py               # 规律作息持久化（落库替代内存缓存）
│   │   ├── goals.py                  # 目标 CRUD
│   │   ├── tasks.py / task_history.py # 任务 CRUD + 历史归档
│   │   ├── scheduled_tasks.py        # 定时任务模板 CRUD
│   │   ├── dimensions.py             # 8 维属性经验 CRUD
│   │   ├── stats.py                  # 统计查询（热力图、EXP 趋势、profile）
│   │   ├── rewards.py                # 奖励 CRUD + 条件评估引擎
│   │   ├── batch.py                  # 定时批处理函数
│   │   ├── model_configs.py          # 模型配置 CRUD + 同类型互斥切换
│   │   ├── skill_tree.py             # 技能树 CRUD（替代 localStorage）
│   │   └── expressions.py            # 表达训练题目/回答 CRUD + 用户统计
│   │
│   ├── services/                     # 业务逻辑层
│   │   ├── auth_service.py           # ★ 登录鉴权：bcrypt 哈希、JWT 签发/验签、Refresh 轮换、API Key、失败锁定
│   │   ├── exp_service.py            # EXP 奖励编排（幂等防重复结算）
│   │   ├── ai_client.py              # 统一 AI HTTP 客户端（动态读取启用模型配置）
│   │   ├── ai_action_service.py      # 行动记录 AI 解析（对话式提取）
│   │   ├── ai_habit_service.py       # 习惯 AI 分析（智能洞察 + 图标分配）
│   │   ├── asr_service.py            # 语音识别（DashScope paraformer 实时转写）
│   │   ├── expression_service.py     # 表达训练 AI 出题/评分 + 提示生成
│   │   │
│   │   ├── coordinator/              # 统一协调 Agent（LangGraph 多智能体）
│   │   │   ├── graph.py              # 主图编译 + run/resume
│   │   │   ├── router_node.py        # LLM 路由决策
│   │   │   ├── synthesize_node.py    # 汇总回复
│   │   │   ├── llm.py                # 动态 LLM 实例（读 model_configs，缓存自动失效）
│   │   │   ├── checkpointer.py       # 全局 MemorySaver（thread_id 隔离）
│   │   │   └── agents/               # 6 个子 Agent（action/query/goal/task/habit/reward）+ ask_user 反问工具
│   │   │
│   │   └── skill_tree_ai/            # 技能树 AI 编辑（LangGraph）
│   │       ├── graph.py              # StateGraph 编译 + chat/resume + 结果格式化
│   │       ├── node.py               # Agent 节点（LLM + 工具循环，消息截断防孤儿 ToolMessage）
│   │       ├── tools.py              # 9 个工具（按节点 ID 操作 + 危险操作确认守卫）
│   │       ├── state.py              # 会话状态定义（checkpointer 持久化）
│   │       └── prompts.py            # 系统提示词 + 树状态动态注入
│   │
│   ├── prompts/                      # AI 系统提示词模板
│   │   ├── coordinator.py            # 协调 Agent 路由/汇总提示词
│   │   ├── action_parse.py           # 行动解析提示词
│   │   ├── habit_icon.py             # 习惯图标分配提示词
│   │   ├── expression.py             # 表达训练出题/评分/提示生成提示词
│   │   └── action_parse.py           # AI 行动解析提示词 + 工具定义
│   │
│   ├── routers/                      # API 路由层（各文件端点数按 OpenAPI 实测）
│   │   ├── deps.py                   # ★ 依赖注入：get_current_user（凭证解析链）+ require_admin（角色授权）
│   │   ├── auth.py                   # ★ 登录鉴权 API（8：login/refresh/logout/password/me + api-keys 增删查）
│   │   ├── health.py                 # GET /api/health（含 git 版本号）
│   │   ├── users.py                  # 用户 API（3：用户列表 + 个人资料 + 今日统计同步）
│   │   ├── habits.py                 # 习惯 API（9 个端点，含 AI 图标生成）
│   │   ├── actions.py                # 行动记录 API（9 个端点，含 AI 对话 + 作息状态 + CSV 导出）
│   │   ├── goals.py                  # 目标 API（5 个端点）
│   │   ├── tasks.py                  # 任务 API（9 个端点）
│   │   ├── scheduled_tasks.py        # 定时任务模板 API（4 个端点）
│   │   ├── stats.py                  # 统计 API（4 个端点）
│   │   ├── rewards.py                # 奖励商城 API（11 个端点）
│   │   ├── coordinator.py            # 协调 Agent API（2：chat/resume，都是 SSE 流式）
│   │   ├── model_configs.py          # 模型配置 API（6 个端点：CRUD + 切换启用 + 连通性测试）
│   │   ├── skill_tree.py             # 技能树 CRUD API（10 个端点，写操作仅管理员）
│   │   ├── skill_tree_ai.py          # 技能树 AI API（2：chat/resume，SSE 流式，LangGraph，仅管理员）
│   │   └── expression.py             # 表达训练 API（11 个端点）
│   │
│   ├── tests/                        # pytest 测试（227 passed，LLM 全打桩、不联网）
│   │   ├── conftest.py               # pytest 配置（★ 在此设置 SELF_GROW_JWT_SECRET，早于 config 导入）
│   │   ├── helpers.py                # 测试用公共方法（ensure_test_accounts / get_auth_headers）
│   │   ├── test_auth.py              # 登录鉴权（17）
│   │   ├── test_sleep_action.py      # 睡眠行动 + 经验计算（38）
│   │   ├── test_ai_action.py         # AI 行动解析（20）
│   │   ├── test_streaming.py         # SSE 流式：事件协议 / 心跳 / 发射器并发隔离 / 端点契约（21）
│   │   ├── test_skill_tree_permissions.py  # 技能树角色权限 / 越权拦截（11）
│   │   ├── test_time_consistency.py  # 时间口径统一（任意时区下成立，10）
│   │   ├── test_dimension_invariant.py     # 维度数据不变式：xp_to_next == exp_for_level（6）
│   │   ├── test_coordinator_interrupt.py   # 反问交互：会话锁 / 连点 409 / skip 语义（10）
│   │   ├── test_skill_tree_ai_tools.py     # 技能树 AI 工具（9）
│   │   ├── test_mcp_auth.py          # MCP HTTP 传输的 API Key 鉴权（6）
│   │   ├── test_expression_endpoints.py    # 表达训练接口 / 派生表别名（12）
│   │   ├── test_sql_dialect_lint.py  # 静态护栏：拦 SQLite 残留写法 / 派生表别名 / 保留字反引号（11）
│   │   └── locustfile.py             # 压测脚本（非 pytest）
│   │
│   ├── .env                          # AI 配置 + 鉴权密钥 + 前端目录（不入 git）
│   ├── .env.example                  # 配置模板
│   ├── pixi.toml                     # pixi 环境（Python 3.12 + FastAPI + LangGraph + FastMCP + PyJWT + bcrypt）— 依赖唯一事实源
│   ├── requirements.txt              # 由 pixi 锁定的版本导出（供 pip / Docker 安装）
│   ├── tools/export_reqs.py          # 从 pixi 导出 requirements.txt
│   ├── tools/init_password.py        # 初始化 / 重置账号密码（pixi run init-password）
│   └── tools/archive/                # 已归档的一次性脚本（SQLite → MySQL 迁移工具）
│
├── docs/                             # 项目文档（24 篇）
│   ├── 登录鉴权方案选型.md            # ★ 9 种登录方式对比 + JWT 落地方案 + 实施进度
│   ├── 安全设计说明.md                # ★ 威胁模型 / 令牌设计 / RBAC / 已知风险清单 10 条
│   ├── 技能树编辑器技术详解.md         # ★ 1700+ 行：编辑器渲染与交互 + Agent 全解析
│   ├── 技能树AI-LangGraph改造方案.md  # 技能树 AI LangGraph 架构设计
│   ├── 统一协调Agent设计方案.md       # 统一协调 Agent 设计
│   ├── 代码学习顺序.md（backend/services/）# services 层 6 阶段学习路线
│   ├── MCP插件说明.md                # MCP 插件安装/挂载/验证/鉴权
│   ├── 面试展示待补充清单.md           # 求职向：缺口分析 + P0~P2 分级 + 两周排期
│   ├── 求职材料-简历条目与面经.md      # 简历条目 + 高频追问
│   ├── 项目坑与面试讲解.md            # 踩坑复盘
│   ├── 维度经验计分规则.md           # 8 维经验计算规则详情
│   ├── 前端浏览器缓存与存储详解.md     # 浏览器缓存与存储
│   ├── 数据库知识深入学习指南.md       # 数据库学习资料
│   ├── SQLite迁移MySQL方案.md         # ★ 迁移实录：改动面实测 / 分阶段步骤 / 8 项验证清单（历史）
│   ├── 彻底移除SQLite完整方案.md      # ★ 移除 SQLite 的完整方案（六批实施 + 验收清单）
│   ├── 网络知识深入学习指南.md         # 网络学习资料
│   ├── 异步编程学习指南.md            # asyncio 学习资料
│   ├── 性能优化学习指南.md            # 性能优化学习资料
│   ├── 设计模式学习指南.md            # 设计模式学习资料
│   ├── FastAPI与FastMCP学习指南.md    # FastAPI / FastMCP 学习资料
│   ├── Docker技术详解与部署实战.md    # Docker 原理讲解 + 生产部署实战（含 Nginx/HTTPS）
│   ├── 压测说明.md                   # Locust 压测方案与结果
│   └── 手机版部署方案.md            # 移动端部署方案
│
└── memory/                           # 开发记录（Claude Code 自动管理）
    ├── MEMORY.md                     # 记忆索引
    └── ...
```

---

## 功能板块

| 页面 | 说明 |
|------|------|
| **仪表盘** | 欢迎横幅、连续打卡天数、等级 EXP 进度条（10 段位渐变色，Lv.200 满级特效）、今日概览统计卡片、待打卡习惯列表、近期活动动态 |
| **行动** | 开始行动（计时器 + 8 分类 + EXP 结算）、行动中心（维度进度条、动态播报、目标追踪、本周任务）、行动历史（筛选+排序+分页+CSV 导出）、AI 对话式记录 |
| **成长记录** | 年度热力图（365 天 EXP 分布）、八维属性雷达图、30 天 EXP 趋势折线图 |
| **属性** | 8 维度等级 & EXP 进度、属性详细介绍卡片 |
| **目标** | 创建/编辑/删除目标、里程碑列表、EXP 奖励领取 |
| **任务** | 本日任务（todo/doing/done 三栏）、本周任务（同上三栏）、历史任务（已完成/超期）、定时任务模板 + 每周任务模板 |
| **习惯** | 7 天周视图（三态循环打卡：done/skipped/pending）、统计卡片、4 条智能洞察（AI 分析）、AI 推荐习惯 |
| **技能** | 我的技能（技能卡片列表，点击进入技能树查看器）、技能库（预设模板） |
| **技能树编辑器** | 独立 SPA，**仅管理员可进入**（普通用户无入口，只能查看已发布内容并学习）。可视化节点编辑（拖拽、缩放、连线）、学习状态管理（locked/available/learning/completed）、前置条件检查、撤销/重做、**AI 智能编辑（LangGraph Agent，按节点 ID 操作 + 危险操作确认卡片）** |
| **奖励商城** | 8 分类筛选、解锁条件 + 领取条件双重验证、图片上传、手动确认条件 |
| **表达训练** | 扩展 → AI Agent，AI 出题（4 种题型，实时查重避免重复）、答题计时器（开始/暂停/完成）、实时语音识别输入（paraformer）、实时填充词高亮检测（密度+重复+句首+簇拥四重规则）、AI 评分（流畅度/逻辑性/内容质量/语言表达四维 0-100 分）、双层展开提示面板 |
| **用户中心** | 基础信息卡（等级徽章/总经验/注册时间/用户 ID）、**账户安全卡（登录状态 / 修改密码 / API Key 管理 / 退出登录）**、模型信息卡（LLM/ASR 增删改 + 切换启用 + 连通性测试），切换模型即时生效 |
| **登录页** | 用户名 + 密码表单，上方用户卡片点击即填用户名；本地免鉴权模式（`SELF_GROW_TRUSTED_MODE=1`）下隐藏表单、点卡片直进 |
| **AI 悬浮球** | 全局悬浮球对话框，自然语言直达协调 Agent（6 域 24 工具），反问卡片 FIFO 队列（最多 2 张）+ 域名标签 + 跳过 + 输入框 |

---

## 快速启动

> ⚠️ 必须用 HTTP 服务器打开，不要直接双击 HTML（`file://` 下浏览器禁止跨域请求）

### 1. 后端（必须优先启动）

```bash
cd backend
pixi install                 # 首次
pixi run init-password        # 初始化账号密码（默认 test / admin）
pixi run start
# 服务运行在 http://localhost:3001
```

启动后控制台会打印真正可访问的地址（**不要点 `0.0.0.0`，那是监听地址**）：

```
🌐 登录页：   http://localhost:3001/login.html
📖 API 文档： http://localhost:3001/docs
```

**必须配置 `SELF_GROW_JWT_SECRET`**（缺失会拒绝启动）：

```bash
# Linux / macOS
echo "SELF_GROW_JWT_SECRET=$(openssl rand -hex 32)" >> backend/.env
# Windows PowerShell
"SELF_GROW_JWT_SECRET=$( -join ((1..32)|%{ '{0:x2}' -f (Get-Random -Max 256) }) )" | Out-File -Append backend\.env
```

默认账号（由 `pixi run init-password` 写入）：

| 用户名 | 密码 | 角色 | 权限 |
|---|---|---|---|
| `test` | `test123456` | user | 查看与学习；**无技能树编辑器入口** |
| `admin` | `admin123456` | admin | 全部功能，含技能树编辑与 AI 编辑 |

> 改密码：`pixi run init-password admin 新密码`，或在「用户中心 → 账户安全」自助修改。

后端首次运行自动建表（22 张）。**数据库有两个后端，靠环境变量切换**：

```bash
# SELF_GROW_DB_BACKEND 已于 2026-09-23 废弃：项目只支持 MySQL。
# 该变量仍会被读取但**不生效**（读到会打一条 WARNING），避免老部署以为切了库。
```

项目**只支持 MySQL**（2026-09-23 移除 SQLite）。源码里写的就是 MySQL 原生 SQL ——
原来的方言自动转换层已删除，`tests/test_sql_dialect_lint.py` 负责拦住 SQLite 写法的回退。

启动时自动拉起 **APScheduler 定时任务**（每日 03:00 归档任务/刷新模板/习惯结算/统计快照，每周一 03:00 刷新周模板任务）。

### 2. 前端（两种形态任选）

**方式 A：后端同源提供（推荐，零跨域问题）**

```bash
# backend/.env
SELF_GROW_FRONTEND_DIR=D:/pycharm/projec/self_grow_system/frontend
```
浏览器直接打开 **http://localhost:3001** → 登录页。

**方式 B：前端独立服务器（开发时改代码免重启后端）**

```bash
# 项目根目录
npx http-server -p 3000 -c-1        # 或 python -m http.server 3000
# 浏览器打开 http://localhost:3000 → login.html
```

> CORS 已默认放行 **localhost / 127.0.0.1 的任意端口**（`allow_origin_regex`），
> 所以 3000 / 5173 / 5500 都能直连；**公网部署请用 `SELF_GROW_CORS_ORIGINS` 显式指定来源**。

流程：`/login.html` → 用户名密码登录 → `frontend/index.html`（SPA 主页）

### 3. AI 代理配置（可选）

```bash
cd backend
cp .env.example .env    # 编辑 .env 填写 AI 配置
```

AI 配置（`backend/.env`）：
```
AI_API_BASE_URL=https://ws-ihdcftaqkyq514nr.cn-beijing.maas.aliyuncs.com/compatible-mode/v1
AI_API_KEY=sk-你的key
AI_MODEL=qwen3
PORT=3001
SELF_GROW_JWT_SECRET=用 openssl rand -hex 32 生成
```

> `.env` 只是兜底配置 — 运行时优先读 `model_configs` 表中当前启用的模型（用户中心可视化切换，即时生效）。

AI 功能支持六个场景：
- **技能树编辑器**：LangGraph Agent，按节点 ID 操作（生成/修改/删除/连线/批量子树），危险操作二次确认（9 个工具）
- **统一协调 Agent**：主图 LLM 路由 → 6 个子 Agent（行动/查询/目标/任务/习惯/奖励），支持反问澄清，前端悬浮球交互
- **行动记录**：通过 AI 对话自然语言记录行动（解析为结构化数据存入后端）
- **习惯分析**：智能洞察分析 + 自动推荐习惯图标
- **表达训练**：AI 出题（查重避免重复）+ AI 评分（四维打分 + 填充词统计）+ 智能提示生成 + 实时语音识别
- **MCP 插件**：24 个业务工具通过 MCP 协议暴露给 Claude Desktop / Cursor / WorkBuddy 等客户端

### 4. MCP 插件（可选）

```bash
cd backend
pixi run mcp        # stdio 模式（本地客户端 spawn，免鉴权）

# HTTP 远程模式：必须带 API Key（在「用户中心 → 账户安全」生成）
MCP_TRANSPORT=streamable-http MCP_PORT=8000 pixi run mcp
curl -X POST http://localhost:8000/mcp -H "X-API-Key: sgk_xxx" \
     -H "Content-Type: application/json" -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
```

详细安装/挂载/验证见 [`docs/MCP插件说明.md`](docs/MCP插件说明.md)。

### 5. 生产部署（Docker）

详细步骤见 [`docs/Docker技术详解与部署实战.md`](docs/Docker技术详解与部署实战.md)：

```bash
# 在项目根目录（与 .gitignore 同级）放置 Dockerfile / .dockerignore / docker-compose.yml
cp .env.example .env
sed -i "s|^SELF_GROW_JWT_SECRET=.*|SELF_GROW_JWT_SECRET=$(openssl rand -hex 32)|" .env
# 顺手改掉 MySQL 口令（模板里是占位值）：MYSQL_ROOT_PASSWORD / MYSQL_PASSWORD

docker compose up -d          # 会拉起 mysql + app + mcp
docker compose exec app python tools/init_password.py
# 浏览器访问 http://服务器IP:3001
```

> ⚠️ **历史说明（2026-09-23 之前的版本适用）**：当时若已在跑 SQLite 版本、想切到 MySQL，先迁数据再切，否则 app 会在空库里
> 重建 28 张表、看起来像「数据全丢了」：
>
> ```bash
> docker compose up -d mysql
> docker compose run --rm app python tools/archive/migrate_sqlite_to_mysql.py
> docker compose up -d app mcp
> ```

镜内依赖安装走 `backend/requirements.txt`（由 `pixi run export-reqs` 从 pixi 锁定版本生成，与开发环境版本一致）。

---

## 技术栈

| 层级 | 技术 |
|------|------|
| **前端** | 原生 HTML/CSS/JS，零框架依赖 |
| **图表** | Chart.js 4.4.0（雷达图、折线图、热力图） |
| **状态管理** | AppData 全局对象 + 后端持久化；localStorage 仅存登录凭证（Access/Refresh） |
| **后端** | Python FastAPI + httpx |
| **数据库** | **MySQL 8.0**（PyMySQL + DBUtils 连接池）—— 单后端，源码即 MySQL 原生 SQL，方言层已移除 |
| **登录鉴权** | PyJWT（HS256 Access 2h + Refresh 30d 轮换）+ bcrypt(cost=12) + API Key（SHA-256 落库） |
| **AI 编排** | LangGraph（协调 Agent 多智能体图 + 技能树 AI 工具调用图，MemorySaver checkpointer） |
| **MCP** | FastMCP（24 业务工具，stdio 免鉴权 / HTTP 强制 X-API-Key） |
| **语音识别** | DashScope paraformer（WebSocket 实时转写） |
| **定时任务** | APScheduler 3.x（每日 03:00 / 每周一 03:00） |
| **环境** | pixi（conda-forge，Python 3.12）— 依赖唯一事实源 |
| **AI** | OpenAI 兼容 API + Function Calling / Tool Use（多模型可切换） |
| **部署** | Docker（FastAPI 同时提供 API 与前端静态资源） |

---

## 架构特点

### 等级系统

- 等级公式：`expForLevel(L) = round(5.5632 × (L-1)² + 300)`，上限 **200 级**
- **10 个段位**（每 20 级一段）：初阶 → 历练 → 资深 → 荒野 → 征途 → 秘境 → 破晓 → 星途 → 传奇 → 不朽
- 每个段位有独立渐变色方案（10 套视觉主题），满级 Lv.200 有专属高光特效
- **经验系统已重构**：全局总经验 = 8 维经验之和（`get_total_exp_from_dimensions()`），每次行动/任务/习惯结算时从维度表实时 SUM 并重新计算等级
- 满级时 `expForLevel(200) = 0`，进度条显示"🏆 满级达成"

### 经验系统设计

```
总经验(TotalEXP) = Σ(8 维维度经验)
维度经验 = 该维度 level 累计经验 + 当前 xp
等级计算：从 level=1 开始累加 expForLevel，直到 sum > TotalEXP
```

每次获得经验时：
1. 更新对应维度的 `user_dimensions` 表（增量 + 自动升级检测）
2. 从 8 维表 SUM 出全局总经验
3. 反算新等级，更新 `users` 表
4. 更新 `user_stats_daily` 今日统计
5. 幂等保护：`exp_earned` 先占位 0，结算后回写真实值，防重复结算被跳过

### 维度经验计算规则（v1.0 精细化）

| 维度 | 子类型 | 计算规则 |
|------|--------|----------|
| 健康-运动 | health-sport | `floor(duration/15) × 3.75`，最小 15 分钟 |
| 健康-睡眠 | health-sleep | 6~9 小时有效：`max(0, 20 - 晚分/4)`，23:00~00:00 + 07:00~08:00 符合作息规律 +15 |
| 学习 | study | `floor(duration/20) × 10`，最小 20 分钟 |
| 关系-线下 | relation-offline | 每次 +80 |
| 关系-线上 | relation-online | `floor(duration/30) × 20` |
| 工作-日常 | work-daily | 每次 +10 |
| 工作-加班平日 | work-overtime-weekday | 每次 +20 |
| 工作-加班周末 | work-overtime-weekend | 每次 +30 |
| 创作-产出 | create-output | `duration × 2`（120/h） |
| 创作-素材 | create-material | `floor(duration/30) × 20`（40/h） |
| 创作-发布 | create-publish | 每次 +160 |
| 财务-梳理 | finance-study | `duration × 4/3`（80/h） |
| 财务-复盘 | finance-review | 每次 +50（每半月限 1 次） |
| 爱好 | hobby | `duration × 2/3`（40/h） |
| 魅力 | soul | `duration × 5/6`（50/h） |

### 作息规律系统

- **定义**：23:00~00:00 睡觉 + 07:00~08:00 起床，6~9 小时有效睡眠
- **连续机制**：连续 >=6 天规律作息，每天睡眠额外 +15 EXP
- **护盾机制**：连续 >=10 天获得一次"保护"机会，断一天消耗保护不重置连续天数
- **持久化**：`routine_streak` 表存储，服务重启不丢失

### AI 功能体系

| AI 服务 | 位置 | 架构 | 说明 |
|---------|------|------|------|
| 技能树 AI | `services/skill_tree_ai/` | LangGraph 单 Agent 图 | 9 个工具按节点 ID 操作，checkpointer 会话，危险操作确认卡片，`/api/skill-trees/{id}/chat` |
| 统一协调 Agent | `services/coordinator/` | LangGraph 多智能体 | 主图 LLM 路由 → 6 子 Agent，ask_user 反问机制，`/api/coordinator/chat` |
| 行动解析 | `ai_action_service.py` | 对话式提取 | 自然语言 → 结构化行动记录，支持多轮交互 |
| 习惯分析 | `ai_habit_service.py` | 智能洞察 + 图标 | 数据分析 + 习惯建议 + 自动分配 SVG 图标 |
| 表达训练 | `expression_service.py` | 出题 + 评分 + 提示 | AI 出题（查重）、四维评分、智能提示生成 |
| MCP 插件 | `mcp_server.py` | FastMCP | 6 域 24 工具，Literal 枚举约束 + 数值校验；stdio 免鉴权（本地进程可信）/ HTTP 强制 `X-API-Key` 且身份随 Key 走 |

**多模型动态切换**：`model_configs` 表按用户存 LLM/ASR 配置，所有 AI 服务经 `get_llm(user_id)` 动态读取启用配置，用户中心切换即时生效（缓存 key 含模型三元组，自动重建实例）。

### 表达训练系统

**表达训练** 是扩展插件中的 AI 功能模块，帮助用户提升口头表达能力：

- **题型选择**：4 种题型（热门事件观点、情感表达、生活感悟、职场沟通），可多选
- **AI 出题**：调用 LLM 生成题目，自动查重（`query_history_questions` 工具），避免重复
- **实时语音识别**：DashScope paraformer WebSocket 实时转写替代打字输入（含麦克风诊断弹窗）
- **答题计时器**：开始 → 暂停/继续 → 完成，记录回答耗时
- **实时填充词检测**：四重规则（密度、高频重复、句首堵词、簇拥），实时高亮标记
  - 一级填充词：然后、就是说、所以说（严重口头禅）
  - 二级填充词：就是、反正、基本上（滥用时标记）
  - 三级语气词：嗯、呃、啊（极度宽松，密度 > 15% 且次数 >= 5 才标记）
  - 语境敏感词：这个、那个（密度 > 12% 且次数 >= 5 才标记）
- **AI 评分**：流畅度(25%) + 逻辑性(25%) + 内容质量(35%) + 语言表达(15%) = 总分
- **智能提示**：异步加载，双层展开（方向 → 例子），不阻塞答题
- **数据统计**：累计回答数、训练天数、平均分、各题型分布
- **降级策略**：AI 不可用时使用预设题目和默认评分，系统不崩溃

### 统一协调 Agent

全局悬浮球入口，自然语言直接操作全部业务数据：

```
用户消息 → 主图 router_node（LLM 路由）
        → 域 Agent（action/query/goal/task/habit/reward）
        → 需要澄清时 ask_user 反问（前端 FIFO 卡片队列，最多 2 张）
        → synthesize_node 汇总回复
```

- 上下文管理：近 5 条记录 + 3 轮反问窗口 + sessionStorage 持久化 thread_id
- 会话由服务端 MemorySaver checkpointer 维护，thread_id 隔离

### 登录鉴权（JWT）

三类客户端、三条凭证通道，解析优先级写在 `routers/deps.py` 一处：

```
① SELF_GROW_TRUSTED_MODE=1      → 固定用户（本地开发/演示，启动打告警）
② Authorization: Bearer <jwt>   → 验签 + token_version 校验
③ X-API-Key: sgk_xxx            → 查 api_keys 表（MCP / 脚本）
④ 都没有                         → 401 + WWW-Authenticate: Bearer
```

| 令牌 | 有效期 | 存储 | 撤销方式 |
|---|---|---|---|
| Access | 2h | 前端 localStorage | 靠 `token_version` 间接失效 |
| Refresh | 30d | 前端 localStorage + httpOnly Cookie | 落表直接撤销；**用掉即轮换**（重放可检测） |
| API Key | 不过期 | 客户端配置 | 用户中心一键撤销 |

- **密码**：bcrypt(cost=12)，超 72 字节先 SHA-256；登录失败统一文案 + 5 次锁 10 分钟
- **角色授权**：`require_admin` 挂到技能树的 create/update/publish/delete + AI 的 chat/resume（AI 能改树，按写操作管）
- **技能树编辑器三道防线**：入口不渲染（UX）→ 页面启动查 `/api/auth/me`（兜底，非 admin 不初始化 App）→ 后端 `require_admin`（**真正的锁**）
- **前端零改动接入**：`frontend/js/auth.js` 包装 `window.fetch` 自动带 `Authorization` 并处理 401 自动续期，**52 处 `fetch(...?user_id=)` 一行未改**
- 旧 `?user_id=` 参数**不再作为身份依据**

详见 [`docs/登录鉴权方案选型.md`](docs/登录鉴权方案选型.md) 与 [`docs/安全设计说明.md`](docs/安全设计说明.md)。

### 性能优化

| 优化项 | 说明 |
|--------|------|
| **页面 JS 懒加载** | 首次只加载 core（data.js/router.js/utils.js/components.js/app.js ~30 KB），页面 JS 按需动态加载 |
| **后端请求并行化** | 启动时 8 个后端 API 请求通过 `Promise.all` 并行发出 |
| **失败容错** | 后端不可用时降级使用模拟数据，页面 JS 加载失败显示友好提示 |
| **MySQL 连接池** | `DBUtils.PooledDB` 复用连接，省掉每次请求的 TCP + 认证握手（池大小 20，须 ≥ 并发线程数） |
| **连接池自愈** | `MysqlConn.__del__` 兜底归还 + 池状态可观测（避免"忘 close"静默耗尽连接池） |
| **APScheduler 定时任务** | 每日归档/刷新/结算由后端定时执行，前端无需轮询 |

### 开发里程碑

| 阶段 | 内容 | 状态 |
|------|------|------|
| P0~P7 | 数据持久化 + 板块迁移 + 等级重构 + 模块化 | ✅ 已完成 |
| — | v1.0 上线前审查修复（17 条） | ✅ 已完成 |
| — | AI 行动解析 / 习惯分析 / 技能树持久化 | ✅ 已完成 |
| — | 表达训练系统（出题 + 评分 + 填充词 + 语音识别） | ✅ 已完成 |
| — | 统一协调 Agent（多智能体 + 反问机制 + 悬浮球） | ✅ 已完成 |
| — | MCP 插件（24 工具 + 参数约束校验） | ✅ 已完成 |
| — | 用户中心 + 多模型动态切换 + git 版本号 | ✅ 已完成 |
| — | 技能树 AI 重写为 LangGraph（下线无鉴权旧端点） | ✅ 已完成 |
| — | 技能树编辑器 14 项 bug 修复（撤销栈污染/连线残留/节点叠在原点等） | ✅ 已完成 |
| — | 技能树编辑器权限管控（仅管理员可进入，普通用户无入口） | ✅ 已完成 |
| — | **JWT 登录鉴权全栈落地**（双令牌 + RBAC + API Key + MCP 鉴权，101 tests passed） | ✅ 已完成 |
| — | `docs/安全设计说明.md`、`docs/技能树编辑器技术详解.md`、`docs/代码学习顺序.md` | ✅ 已完成 |

### 后端数据库

共 **28 张表**：

| 表名 | 说明 |
|------|------|
| `users` | 用户信息（等级、经验、连续天数、**密码哈希 / token_version / 最后登录**） |
| `refresh_tokens` | Refresh Token（**只存 SHA-256**，支持轮换与撤销） |
| `api_keys` | API Key（**只存 SHA-256**，MCP / 脚本用，可撤销） |
| `user_stats_daily` | 每日统计（专注分钟、任务完成、习惯打卡、EXP） |
| `user_monthly_stats` | 月度统计持久化 |
| `habits` | 习惯定义 |
| `habit_checkins` | 每日打卡记录 |
| `action_logs` | 行动记录（含 sub_type/sleep 字段） |
| `routine_streak` | 规律作息连续天数持久化 |
| `user_dimensions` | 八维属性经验 |
| `goals` | 目标 |
| `goal_milestones` | 目标里程碑 |
| `tasks` | 任务 |
| `task_history` | 已归档历史任务 |
| `scheduled_tasks` | 定时任务模板 |
| `rewards` | 奖励商城 |
| `reward_drafts` | 奖励创建草稿 |
| `model_configs` | 多模型配置（LLM/ASR，同类型互斥启用） |
| `skill_trees` | 技能树定义 |
| `user_skills` | 用户技能关联 |
| `expression_questions` | 表达训练题目 |
| `expression_answers` | 表达训练回答记录（含 AI 评分） |

（`categories` 8 维分类定义硬编码在 `models/constants.py` 中，不作为数据库表）

### 后端定时任务

| 触发时间 | 任务 |
|----------|------|
| 每日 03:00 | 归档未完成任务、从 daily 模板创建今日任务、结算昨日习惯 EXP、统计快照 |
| 每周一 03:00 | 从 weekly 模板创建本周任务 |
| 启动时 | 补归档机制（错过的定时任务补偿执行） |

---

## 开发指引

### 新增页面

1. 在 `frontend/index.html` 中添加 `<div id="page-{name}" class="page">`
2. 创建 `frontend/js/pages/{name}.js`，导出 `render{Name}()` 函数（全局 function 声明即可）
3. 在 `router.js` 的 `PAGE_JS_MAP` 和 `navigateTo` 的 `renderers` 映射表中添加条目
4. 在 `index.html` 侧边栏添加导航项
5. 在正确的加载顺序位置添加 `<script>` 标签（在 `app.js` 之前）

### 修改等级/段位系统

- 前端公式：`frontend/js/utils.js`（`expForLevel` / `getRankInfo` / `getRankColors`）
- 后端公式：`backend/models/level.py`（等级公式唯一来源）
- 数据库：`backend/db/dimensions.py`（维度经验管理）+ `backend/db/init.py`（建表）
- 视觉主题：`frontend/js/utils.js`（10 个段位的渐变色方案）

### 修改经验计算规则

- 后端规则引擎：`backend/models/constants.py`（`calculate_exp()` 及各维度子函数）
- 维度经验值在此计算，由 `exp_service.py` 汇总到 total_exp 并重算等级
- 完整计分规则文档见 [`docs/维度经验计分规则.md`](docs/维度经验计分规则.md)

### 技能树开发

- 编辑器入口：`frontend/skill-tree/index.html`（独立 SPA，支持 role 参数）
- 查看器：**没有独立的查看器页面** —— 用 `frontend/skill-tree/index.html?role=user`，
  由 `js/pages/skills.js` 通过 iframe 嵌入（技能详情预览 `?preview=true`、我的技能全屏）。
  历史上曾有一个 `viewer.html`（649 行），已于 2026-09-17 删除：它零引用、
  功能被 `?role=user` 完全覆盖，且只加载 utils/tree-renderer 两个 js（不含交互层），是更早的实现。
- 主控制器：`skill-tree/js/app.js`（App 类，CRUD、撤销/重做、AI 集成）
- 渲染引擎：`skill-tree/js/tree-renderer.js`（DOM + SVG 渲染）
- AI 集成：`skill-tree/js/ai-bridge.js`（LangGraph 端点 `/api/skill-trees/{id}/chat`，服务端会话 + 确认卡片）
- 后端持久化：`backend/routers/skill_tree.py` + `backend/db/skill_tree.py`
- 后端 AI 图：`backend/routers/skill_tree_ai.py` + `backend/services/skill_tree_ai/`
- 撤销/重做约定：历史栈为「改后快照」语义；`loadData()` 清空历史并压入基线快照（防跨树数据污染）
- 设计文档：[`docs/技能树AI-LangGraph改造方案.md`](docs/技能树AI-LangGraph改造方案.md)

### 统一协调 Agent 开发

- 前端：`frontend/js/chat.js`（悬浮球 + 对话框 + 流式渲染 + 反问卡片串行队列）
- 后端主图：`backend/services/coordinator/graph.py`（`run_coordinator` 非流式 / `run_coordinator_stream` 流式）
- 子 Agent：`backend/services/coordinator/agents/`（6 个域 Agent + ask_user 工具）
- SSE 统一层：`backend/services/sse.py`（事件协议 + 心跳 + ContextVar 发射器）
- 提示词：`backend/prompts/coordinator.py`
- 设计文档：[`docs/统一协调Agent设计方案.md`](docs/统一协调Agent设计方案.md)

> ⚠️ 改反问相关逻辑前先看设计文档的 §6.1/§6.2：`/chat` 与 `/resume` 有**会话级处理中锁**
> （同一 `thread_id` 并发写返回 409），前端配套**串行提交队列**，两边是配套的。
> `skip: true` 表示跳过提问 —— 不告诉后端的话该域永远完不成，这条记录的总结不会生成。
>
> 回归测试：`backend/tests/test_coordinator_interrupt.py` +
> `frontend/tests/interrupt-submit.test.mjs`

### 表达训练开发

- 前端页面：`frontend/js/pages/agent.js`（`renderAgent()`，两视图：训练/历史）
- 后端路由：`backend/routers/expression.py`（10 个端点）
- 数据库操作：`backend/db/expressions.py`（题目 CRUD + 回答 CRUD + 统计）
- 业务逻辑：`backend/services/expression_service.py`（出题/评分/提示生成）
- AI 提示词：`backend/prompts/expression.py`（出题 + 评分 + 提示三套提示词）
- 语音识别：`backend/services/asr_service.py`（DashScope paraformer WebSocket）
- 样式：`frontend/css/pages.css`（`.expr__*` 类，~300 行）

### 后端 API 路由一览

> ⚡ = **SSE 流式端点**（`text/event-stream`）。统一实现在 `backend/services/sse.py`，
> 事件只有四种：`stage`（阶段进度）/ `token`（逐字文本）/ `error` / `done`（最终结果）。
> 前端的读取工具是 `frontend/js/sse.js` 的 `streamSSE()`。
>
> ⚠️ 为什么不用原生 `EventSource`：它**不能自定义请求头**，而本项目的身份是
> `js/auth.js` 包装 `fetch` 注入的 `Authorization: Bearer` —— 用 EventSource 必然 401。
> 所以走 `fetch` + `resp.body.getReader()` 自己解析（也正因如此端点都做成 POST）。
> 部署侧注意：Nginx 必须关 `proxy_buffering`，否则事件会被攒着一次性发。

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/health` | 心跳检查（含 git 版本号） |
| GET | `/api/config.js` | 动态注入前端 API 基址（**按请求 Host 反推**，不写死 127.0.0.1） |
| GET | `/favicon.ico` | 站点图标 |
| **POST** | **`/api/auth/login`** | **用户名 + 密码登录 → Access（body）+ Refresh（Cookie + body）** |
| **POST** | **`/api/auth/refresh`** | **用 Refresh 换新 Access（旧的立即作废）** |
| **POST** | **`/api/auth/logout`** | **登出（撤销当前 Refresh）** |
| **POST** | **`/api/auth/password`** | **修改密码（token_version+1，旧 token 全失效）** |
| **GET** | **`/api/auth/me`** | **当前身份与角色（权威来源）** |
| **POST/GET** | **`/api/auth/api-keys`** | **API Key 创建 / 列表（MCP 用）** |
| **DELETE** | **`/api/auth/api-keys/{id}`** | **撤销 API Key** |
| GET | `/api/users` | 获取所有用户列表（登录页用，无需登录） |
| GET | `/api/users/profile` | 获取用户完整数据 |
| POST | `/api/users/stats/sync` | 同步今日统计 |
| GET/POST | `/api/habits` | 习惯列表/创建 |
| PUT/DELETE | `/api/habits/{id}` | 更新/删除习惯 |
| POST | `/api/habits/{id}/toggle` | 打卡三态切换 |
| GET | `/api/habits/stats` | 习惯统计卡片 |
| GET | `/api/habits/insights` | 4 条智能洞察（AI 分析） |
| GET | `/api/habits/last-week` | 上周打卡数据 |
| POST | `/api/habits/ai-icon` ⚡ | AI 生成习惯图标（SSE 流式） |
| GET/POST | `/api/actions` | 行动记录查询/提交 |
| GET | `/api/actions/export` | 行动记录 CSV 导出 |
| GET | `/api/actions/today-stats` | 今日行动统计 |
| POST | `/api/actions/ai-chat` | AI 行动解析对话 |
| POST | `/api/actions/ai-submit` | 批量提交 AI 解析的行动 |
| GET | `/api/actions/routine-status` | 作息规律状态 |
| GET | `/api/actions/finance-review-status` | 财务复盘状态 |
| GET | `/api/activities/feed` | 动态播报列表 |
| GET | `/api/activities/recent` | 仪表盘近期动态 |
| GET/POST | `/api/goals` | 目标列表/创建 |
| PUT/DELETE | `/api/goals/{id}` | 更新/删除目标 |
| POST | `/api/goals/{id}/claim` | 领取目标奖励 |
| GET/POST | `/api/tasks` | 今日任务/创建 |
| GET | `/api/tasks/week` | 本周任务 |
| GET | `/api/tasks/all` | 所有任务分页 |
| GET | `/api/tasks/history` | 历史任务分页 |
| PUT/DELETE | `/api/tasks/{id}` | 更新/删除任务 |
| PATCH | `/api/tasks/{id}/status` | 变更任务状态 |
| POST | `/api/tasks/{id}/claim` | 领取任务 EXP |
| GET/POST | `/api/scheduled-tasks` | 定时任务模板 |
| PUT/DELETE | `/api/scheduled-tasks/{id}` | 更新/删除模板 |
| GET | `/api/stats/profile` | 6 项统计 + 8 维进度 |
| GET | `/api/stats/yearly-activity` | 年度热力图 |
| GET | `/api/stats/daily-exp` | 每日 EXP 趋势 |
| GET/POST | `/api/rewards` | 奖励列表/创建 |
| PUT/DELETE | `/api/rewards/{id}` | 更新/删除奖励 |
| POST | `/api/rewards/{id}/claim` | 领取奖励 |
| POST | `/api/rewards/{id}/manual-confirm` | 手动确认条件 |
| POST | `/api/rewards/reevaluate` | 重新评估所有奖励 |
| POST | `/api/rewards/{id}/image` | 上传奖励图片 |
| DELETE | `/api/rewards/draft` | 清除奖励草稿 |
| **POST** | **`/api/coordinator/chat`** ⚡ | **协调 Agent 对话（路由到子 Agent）｜SSE 流式** |
| **POST** | **`/api/coordinator/resume`** ⚡ | **恢复协调 Agent 会话（回答反问 / `skip` 跳过）｜SSE 流式** |
| **GET/POST** | **`/api/model-configs`** | **模型配置列表/新增** |
| **PUT/DELETE** | **`/api/model-configs/{id}`** | **更新/删除模型配置** |
| **POST** | **`/api/model-configs/{id}/activate`** | **切换启用模型（即时生效）** |
| **POST** | **`/api/model-configs/test`** | **模型连通性测试** |
| GET/POST | `/api/skill-trees` | 技能树列表 / 创建 |
| GET/PUT/DELETE | `/api/skill-trees/{id}` | 技能树详情 / 更新 / 删除 |
| GET/PUT | `/api/skill-trees/user-skills/list` | 用户技能 ID 管理 |
| PUT | `/api/skill-trees/{id}/publish` | 发布技能树 |
| GET | `/api/skill-trees/{id}/published` | 获取已发布技能树 |
| PUT | `/api/skill-trees/{id}/learner` | 保存学习进度 |
| **POST** | **`/api/skill-trees/{id}/chat`** ⚡ | **技能树 AI 编辑对话（LangGraph）｜SSE 流式** |
| **POST** | **`/api/skill-trees/{id}/chat/resume`** ⚡ | **技能树 AI 确认/恢复｜SSE 流式** |
| POST | `/api/expression/generate` ⚡ | 表达训练出题（SSE 流式） |
| POST | `/api/expression/answer` | 创建回答记录 |
| POST | `/api/expression/generate-hints` ⚡ | 生成答题提示（SSE 流式） |
| POST | `/api/expression/answer/{id}/text` | 更新回答文本 |
| POST | `/api/expression/evaluate/{id}` ⚡ | AI 评分（SSE 流式） |
| GET | `/api/expression/stats` | 训练统计 |
| GET | `/api/expression/history` | 回答历史 |
| GET | `/api/expression/question/{id}` | 题目详情 |
| POST | `/api/expression/beautify` ⚡ | AI 美化自定义题目（SSE 流式） |
| GET | `/api/expression/history/questions` | 出题历史（按题目聚合） |
| GET | `/api/expression/history/questions/{id}/answers` | 某道题目的全部回答 |

> 旧 `POST /api/chat`（无鉴权的技能树 AI 代理）已于 2026-09-03 下线，由 `/api/skill-trees/{id}/chat` 替代。

### 登录鉴权开发

- 凭证解析链：`backend/routers/deps.py`（`get_current_user` + `require_admin`）
- 鉴权端点：`backend/routers/auth.py`（9 个）
- 业务逻辑：`backend/services/auth_service.py`（哈希 / 签发 / 轮换 / API Key / 失败锁定）
- SQL：`backend/db/auth.py`；表定义在 `backend/db/init.py`
- 前端：`frontend/js/auth.js` —— **必须在其他脚本之前加载**（主应用 `js/auth.js`、技能树 `../js/auth.js`）
- 环境变量：`SELF_GROW_JWT_SECRET`（缺失拒绝启动）、`SELF_GROW_JWT_OLD_SECRET`、`SELF_GROW_ACCESS_TTL`、`SELF_GROW_REFRESH_TTL`、`SELF_GROW_TRUSTED_MODE`、`SELF_GROW_CORS_ORIGINS`
- **测试约定**：`SELF_GROW_JWT_SECRET` 必须在 `tests/conftest.py` 里设置（config 在 import 时读 env）；公共登录方法放 `tests/helpers.py`（conftest 不在 sys.path，不能直接 import）

### 后端开发

- API 路由在 `backend/routers/` — 每个模块一个资源域（`health.py`、`auth.py`、`users.py`、`habits.py` 等）
- 数据库操作在 `backend/db/` — 每个模块一个功能域（`auth.py`、`users.py`、`habits.py`、`tasks.py` 等）
- AI 服务在 `backend/services/` — 六个 AI 服务场景独立封装（含 coordinator/、skill_tree_ai/ 两个 LangGraph 包）
- AI 提示词在 `backend/prompts/` — 每个功能独立文件
- 等级公式唯一来源：`backend/models/level.py`
- 运行后端测试：`cd backend && pixi run test`（当前 **227 passed**，AI 调用全打桩，不联网）
- 运行前端逻辑测试：`node frontend/tests/interrupt-submit.test.mjs`（零依赖，不用开浏览器）
- 依赖唯一事实源：`backend/pixi.toml`；导出锁定版到 pip/Docker：`cd backend && pixi run export-reqs`

### 数据库（MySQL，唯一后端）

项目 **只支持 MySQL**。2026-09-19 从 SQLite 迁过来，2026-09-23 **彻底移除**了 SQLite 通路 ——
不再有 `SELF_GROW_DB_BACKEND` 开关、没有 `DB_PATH`、没有 `data.db`，
`backend/db/dialect.py`（方言自动转换层）整文件删除。

```bash
SELF_GROW_MYSQL_HOST/PORT/USER/PASSWORD/DATABASE   # 唯一的数据源配置
```

> 老部署里若还留着 `SELF_GROW_DB_BACKEND`，启动时会打一条 WARNING 提示它已废弃
> （读但不认，避免"改了没生效"这种困惑）。

**连接层做了什么**

| 层 | 文件 | 作用 |
|---|---|---|
| 连接池 | `backend/db/backend.py` | `DBUtils.PooledDB` + `MysqlConn`/`MysqlCursor` 代理。代理补上 `sqlite3.Connection` 才有的 `execute()` 便利方法，让项目里 190+ 处 `get_conn()` / `conn.execute(...)` 写法不用改（`close()` = 归还连接） |
| 门面 | `backend/db/connection.py` | 对外只暴露 `get_conn()` / `now_str()` / `backend_name()` / `close_pool()` |
| 测试隔离 | `backend/db/testing.py` | MySQL 没有文件可换 → **删表重建**（带「库名必须含 test」安全闸，**不要绕过**） |
| 静态护栏 | `backend/tests/test_sql_dialect_lint.py` | 拦住 SQLite 写法与 MySQL 硬性限制回退，见下 |

**六个必须知道的点**

1. **连接池不能小。** 协调 Agent 会用 `asyncio.gather` 并行跑多个子 Agent，每个工具调用都
   `to_thread` + `get_conn()`。池满时 `DBUtils` 的 `blocking=True` 是**无限等待（没有超时）**
   → 整站卡死。默认 20，别往下调
2. **时区靠连接层补偿，那一行不能删。** MySQL 服务端已设 `--default-time-zone=+08:00`（compose），
   连接层再 `SET time_zone='+08:00'` 兜一层 —— 与容器/宿主机时区**解耦**。
   建表默认值用的 `now()` 也走这个连接时区，删了就整体偏 8 小时
3. **MySQL 的 `TEXT` 不能有默认值、也不能进索引**（errno 1101 / 1170）。
   写 SQL 时：短文本用 `VARCHAR(n) DEFAULT ''`，长文本用 `TEXT NULL`（去掉 `NOT NULL DEFAULT`）
4. ⚠️ **保留字列名必须手写反引号**（以前是方言层自动加的）。
   库里撞上保留字的列只有两个：`` `year_month` `` 与 `` `desc` ``。
   漏加就是运行时 1064，且只有真的走到那条 SQL 才会炸 ——
   所以 `test_reserved_column_names_are_backquoted` 会扫全项目 SQL 兜住
5. **`ON DUPLICATE KEY UPDATE` 的触发范围比 SQLite 的 `ON CONFLICT (col)` 宽**：
   SQLite 只在**指定的那组列**冲突时 upsert，MySQL 是**任意唯一键**冲突都触发。
   现有表都只有一组相关唯一约束所以行为一致 —— 将来给这些表加第二组 `UNIQUE` 时要重新确认
6. **派生表必须有别名**（MySQL errno 1248，SQLite 不报）。
   这条踩过：`/api/expression/stats` 曾在 MySQL 下 500 而**测试全绿**。现在有 lint 兜

**静态护栏（`tests/test_sql_dialect_lint.py`）**

SQLite 移除后没有自动转换兜底了，这份 lint 就成了唯一的防回退机制。它拦：

| 类别 | 拦什么 |
|---|---|
| SQLite 残留写法 | `?` 占位符、`AUTOINCREMENT`、`INSERT OR IGNORE`、`ON CONFLICT`、`datetime('now')`、`CREATE INDEX IF NOT EXISTS`、`PRAGMA`、`sqlite_master`、`excluded.col`、`INSERT OR REPLACE` |
| SQLite 依赖 | `import sqlite3` / `sqlite3.Row` |
| MySQL 硬性限制 | 派生表缺别名（1248）、保留字列名未加反引号（1064） |

每条规则都配一条**灵敏度自测**（故意造违规，确认抓得到；再造正确写法，确认不误报）。

**测试**

```bash
cd backend
SELF_GROW_MYSQL_DATABASE=自建一个库名含 test 的库 pytest tests/ -q
```

- ⚠️ **库名必须含 `test`** —— `db/testing.py` 会拒绝重置其它库（这是保护真实数据的安全闸）
- ⚠️ **全量约 2.5 分钟**（每个用例都要 DROP + 重建 28 张表），必要时分批跑
- 当前全量：**227 passed**

**历史材料**（迁移过程，非当前用法）

- 迁移实录：[`docs/SQLite迁移MySQL方案.md`](docs/SQLite迁移MySQL方案.md)
- 移除方案与实施结果：[`docs/彻底移除SQLite完整方案.md`](docs/彻底移除SQLite完整方案.md)
- 数据迁移脚本已归档到 `backend/tools/archive/migrate_sqlite_to_mysql.py`
  （SQLite 已不存在，它不再需要，留着是为了记录当时怎么迁的）

### 生产部署（Docker）

详细方案见 [`docs/Docker技术详解与部署实战.md`](docs/Docker技术详解与部署实战.md)，根目录已提供 `Dockerfile` / `.dockerignore` / `docker-compose.yml` / `.env.example`。

**架构**：FastAPI 同时提供 API 与前端静态资源，通过 `SELF_GROW_FRONTEND_DIR` 环境变量指向容器内 `/app/frontend`。

| 环节 | 说明 |
|------|------|
| 镜像 | `python:3.12-slim`，`pip install -r backend/requirements.txt`（版本与 pixi 开发环境一致） |
| 数据库 | **MySQL 8.0 容器**（`mysql_data` 卷；utf8mb4 + 时区 `+08:00`；**不对外发布端口**，只有 compose 网络内可连）。**唯一的数据源，没有回退选项** |
| 附件与日志 | `uploads/` 与 `logs/` 存在 `data` 卷，容器删除数据不丢 |
| 前端 | `SELF_GROW_FRONTEND_DIR=/app/frontend`，由 FastAPI 自动 serve |
| AI 配置 | `.env` 传入 `AI_API_KEY` 等，不写入镜像 |

**依赖同步流程**（避免开发/生产版本漂移）：
```bash
cd backend
pixi update            # 更新 pixi 环境 & 锁定
pixi run export-reqs   # 将锁定版本写入 requirements.txt
cd .. && docker compose build --no-cache && docker compose up -d --force-recreate
```

---

## 8 个属性维度

| 维度 | ID | 颜色 | 全局倍率 | 说明 |
|------|-----|-------|----------|------|
| 健康 | health | `#FF7B72` | 1.0 | 运动、睡眠、饮食、冥想 |
| 学习 | study | `#58D5C9` | 1.0 | 读书、课程、研究、刷信息 |
| 关系 | relation | `#FF91A8` | 0.5 | 家人、朋友、社交、社群 |
| 工作 | work | `#FFCA40` | 1.0 | 本职工作、项目推进、任务执行 |
| 创作 | create | `#B794F6` | 0.5 | 写作、出内容、做模板、录视频 |
| 财务 | finance | `#4ADE80` | 0.5 | 记账、理财、副业变现 |
| 爱好 | hobby | `#F472B6` | 0.75 | 游戏、音乐、旅行、放松 |
| 魅力 | soul | `#FBBF24` | 0.5 | 穿搭、气质、社交表达、个人形象 |

> **全局倍率（`global_rate`）** 是真正生效的系数：全局经验 = `dimension_exp × global_rate`。
> 各维度的具体分值由 `models/constants.py` 的 `_calc_*` 系列函数按「时长 / 子类型 /
> 作息 / 连击」硬编码算出。
>
> 这里原来列的是另一个字段 `exp_rate`（10/10/8/12/8/6/7/9）——它**从来没有被任何
> 计分函数读取过**，属于「设计了却没落地」的技术债，已于 2026-09-17 从代码里删除。
> 详见 [`docs/维度经验计分规则.md`](docs/维度经验计分规则.md) §1。

---

## 已知限制

> 完整清单（含改进方案与优先级）见 [`docs/安全设计说明.md`](docs/安全设计说明.md) §10。

**遗留技术问题**

- 异步渲染函数缺少 `await` 可能引发竞态（中优先级）
- 数据库连接未使用上下文管理器（低优先级）
- 编排状态存内存（`_thread_store`，TTL 30min）→ 重启即失，多实例不通用（中优先级）
- 技能树 AI 未做资源级隔离：所有 admin 可改所有技能树（中优先级）

**已完成（不再是限制）**

- ~~协调 Agent / 技能树 AI 的 `/stream` SSE 端点为占位实现~~ →
  **2026-09-16 已全部改为真流式**。原来那两个 `GET .../stream` 占位端点已删除
  （其中一个还没挂鉴权），改由 `/chat` 与 `/resume` 本身推 SSE。
  协调 Agent 是**真逐 token**；技能树 AI 与表达训练只推**阶段进度** ——
  前者回复是 LLM 通过 `send_reply` 工具参数生成、后者的产物是 JSON，
  逐字符传过去等于逼前端做增量 JSON 解析，是负优化。
- ~~反问并发提交会重复执行子图~~ → **2026-09-16 已加会话锁**：
  同一 `thread_id` 同时只允许一个写请求（冲突 409），前端配套串行队列
