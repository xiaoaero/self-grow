# Self Grow — 个人成长系统

> 一个原生 HTML/CSS/JS 单页应用 + FastAPI 后端的个人成长追踪系统。包含等级段位体系、习惯追踪、任务管理、目标规划、八维属性雷达图、奖励商城（含条件解锁/领取双重校验）、可视化技能树编辑器（支持 AI 生成节点）。

---

## 项目结构

```
self_grow_system/
├── README.md                         # 项目文档
├── CLAUDE.md                         # Claude Code 代码指引
├── 后端迁移模块.md                    # 后端迁移规划（P0-P7，已完成 P0-P6）
│
├── index.html                        # 根入口 → 自动跳转 login.html
├── login.html                        # 登录页（调用后端 API 选择用户）
│
├── frontend/                         # 前端 SPA（无框架，纯原生 JS）
│   ├── index.html                    # SPA 主入口（登录后进入）
│   │
│   ├── css/                          # 样式文件（按层分拆，共 5 个文件）
│   │   ├── variables.css             # CSS 变量 / 主题（暖色调：翡翠绿+琥珀金）
│   │   ├── layout.css                # 布局（侧边栏 + 主内容区）
│   │   ├── sidebar.css               # 侧边栏样式
│   │   ├── components.css            # 组件样式（卡片、进度条、经验条等）
│   │   └── pages.css                 # 各页面独立样式（~113 KB，待拆分）
│   │
│   ├── js/                           # JavaScript（加载顺序严格）
│   │   ├── data.js                   # AppData 全局数据模型 + 8 维 SVG 图标定义
│   │   ├── router.js                 # SPA 路由 + 页面 JS 懒加载（PAGE_JS_MAP）
│   │   ├── utils.js                  # 工具函数（toast、模态框、等级公式、段位配色、后端 API 封装 60+ 函数）
│   │   ├── components.js             # 可复用渲染函数（统计卡片、经验条、进度条）
│   │   ├── app.js                    # 应用入口初始化（并行加载 8 个后端 API，降级容错）
│   │   └── pages/                    # 每页一个渲染器，首次访问时动态加载
│   │       ├── dashboard.js          # 仪表盘 — 打卡习惯列表、EXP 进度条、统计卡片、近期动态
│   │       ├── action.js             # 行动中心 — 计时器、维度进度、动态播报、本周任务
│   │       ├── history.js            # 成长记录 — 年度热力图、雷达图、30 天 EXP 趋势
│   │       ├── attributes.js         # 属性 — 8 维度等级 & EXP 进度、详细介绍
│   │       ├── goals.js              # 目标 — 创建/编辑/删除、里程碑、EXP 奖励领取
│   │       ├── tasks.js              # 任务 — 本日/本周三栏（todo/doing/done）、历史、模板
│   │       ├── habits.js             # 习惯 — 7 天周视图三态打卡、统计卡片、智能洞察
│   │       ├── skills.js             # 技能 — 技能卡片列表 → 技能树查看器（iframe）
│   │       └── rewards.js            # 奖励商城 — 8 分类筛选、解锁/领取双重条件、图片上传
│   │
│   ├── skill-tree/                   # 技能树编辑器（独立 SPA，支持查看器/编辑/管理三模式）
│   │   ├── index.html                # 编辑器入口（角色模式：viewer/editor/admin）
│   │   ├── viewer.html               # 查看器（可嵌入 iframe，用于 skills 页面）
│   │   ├── css/
│   │   │   ├── style.css             # 主样式
│   │   │   ├── sidebar.css           # 侧边栏样式
│   │   │   └── detail-panel.css      # 详情弹窗样式
│   │   └── js/
│   │       ├── app.js                # 主控制器 — CRUD、撤销/重做、AI 集成
│   │       ├── tree-renderer.js      # DOM + SVG 渲染引擎
│   │       ├── ai-bridge.js          # AI 集成（通过后端 /api/chat 代理）
│   │       ├── detail-panel.js       # 节点详情弹窗
│   │       ├── interaction.js        # 拖拽、缩放、连线交互
│   │       ├── sidebar.js            # 侧边栏 UI
│   │       ├── history.js            # 撤销/重做历史
│   │       └── utils.js              # 工具函数
│   │
│   └── assets/                       # 静态资源
│       └── icons/                    # 属性图标 SVG（8 维 + 行动 + 成长记录 + 标题等）
│
├── backend/                          # 后端 FastAPI 服务（模块化架构）
│   ├── main.py                       # 入口点：app 工厂、生命周期、路由注册、定时任务
│   ├── config.py                     # 配置从 .env 加载（AI 端点、Key、模型、端口）
│   ├── database.py                   # 向后兼容层（re-export from db/ 子模块）
│   │
│   ├── models/                       # 数据模型
│   │   ├── level.py                  # 等级公式（唯一来源）
│   │   └── constants.py              # 8 维分类定义、10 段位表、颜色映射
│   ├── schemas/                      # Pydantic 请求/响应模型
│   │   └── api.py                    # 22 个模型定义
│   │
│   ├── db/                           # 数据访问层（每模块一个功能域）
│   │   ├── connection.py             # DB_PATH + get_conn()
│   │   ├── init.py                   # 建表（15 张）+ 默认用户/奖励 + 数据迁移
│   │   ├── users.py                  # 用户 + 每日统计 CRUD
│   │   ├── habits.py                 # 习惯 + 打卡记录 CRUD
│   │   ├── actions.py                # 行动记录 CRUD
│   │   ├── goals.py                  # 目标 CRUD
│   │   ├── tasks.py                  # 任务 CRUD
│   │   ├── scheduled_tasks.py        # 定时任务模板 CRUD
│   │   ├── dimensions.py             # 8 维属性经验 CRUD
│   │   ├── stats.py                  # 统计查询（热力图、EXP 趋势、profile）
│   │   ├── rewards.py                # 奖励 CRUD + 条件评估引擎
│   │   └── batch.py                  # 定时批处理函数
│   │
│   ├── services/                     # 业务逻辑层
│   │   ├── exp_service.py            # EXP 奖励编排（消除 5 次重复模式）
│   │   └── ai_service.py             # AI 代理（9 个 Tool Use + 系统提示词）
│   │
│   ├── routers/                      # API 路由层
│   │   ├── deps.py                   # 依赖注入（get_current_user 消除 ~31 次重复验证）
│   │   ├── health.py                 # GET /api/health
│   │   ├── users.py                  # 用户 API（5 个端点）
│   │   ├── habits.py                 # 习惯 API（8 个端点）
│   │   ├── actions.py                # 行动记录 API（4 个端点）
│   │   ├── goals.py                  # 目标 API（5 个端点）
│   │   ├── tasks.py                  # 任务 API（8 个端点）
│   │   ├── scheduled_tasks.py        # 定时任务模板 API（4 个端点）
│   │   ├── stats.py                  # 统计 API（5 个端点）
│   │   ├── rewards.py                # 奖励商城 API（8 个端点）
│   │   └── ai.py                     # AI 聊天 API（1 个端点）
│   │
│   ├── .env                          # AI 配置（端点、Key、模型）
│   ├── .env.example                  # 配置模板
│   ├── pixi.toml                     # pixi 环境（Python 3.12 + FastAPI + httpx + APScheduler）
│   └── data.db                       # SQLite 数据库文件（首次启动自动创建）
│
└── memory/                           # 开发记录
    ├── MEMORY.md                     # 记忆索引
    └── ...
```

---

## 功能板块

| 页面 | 说明 |
|------|------|
| **仪表盘** | 欢迎横幅、连续打卡天数、等级 EXP 进度条（10 段位渐变色，Lv.200 满级特效）、今日概览统计卡片、待打卡习惯列表、近期活动动态 |
| **行动** | 开始行动（计时器 + 8 分类 + EXP 结算）、行动中心（维度进度条、动态播报、目标追踪、本周任务）、行动历史（筛选+排序+分页） |
| **成长记录** | 年度热力图（365 天 EXP 分布）、八维属性雷达图、30 天 EXP 趋势折线图 |
| **属性** | 8 维度等级 & EXP 进度、属性详细介绍卡片 |
| **目标** | 创建/编辑/删除目标、里程碑列表、EXP 奖励领取 |
| **任务** | 本日任务（todo/doing/done 三栏）、本周任务（同上三栏）、历史任务（已完成/超期）、定时任务模板 + 每周任务模板 |
| **习惯** | 7 天周视图（三态循环打卡：done/skipped/pending）、统计卡片、4 条智能洞察 |
| **技能** | 我的技能（技能卡片列表，点击进入技能树查看器）、技能库（预设模板） |
| **技能树编辑器** | 独立 SPA，支持 view/editor/admin 三模式，可视化节点编辑（拖拽、缩放、连线）、学习状态管理（locked/available/learning/completed）、前置条件检查、撤销/重做、AI 智能生成节点（9 种 Tool Use） |
| **奖励商城** | 8 分类筛选、解锁条件 + 领取条件双重验证、图片上传、手动确认条件 |

---

## 快速启动

> ⚠️ 必须使用 HTTP 服务器打开，不要直接双击 HTML 文件

### 1. 后端（必须优先启动）

```bash
cd backend
pixi run python main.py
# 服务运行在 http://localhost:3001
```

后端首次运行自动创建 SQLite 数据库 `data.db`，初始化两个用户：
- `test`（普通用户，Lv.188，含完整模拟数据）
- `admin`（管理员，Lv.99，技能树编辑权限）

后端启动时自动启动 **APScheduler 定时任务**（每日 03:00 归档任务/刷新模板/习惯结算/统计快照，每周一 03:00 刷新周模板任务）。

### 2. 前端

```bash
# 项目根目录
cd D:\pycharm\projec\self_grow_system

# 方式 A：npx http-server（推荐）
npx http-server -p 3000 -c-1

# 方式 B：Python HTTP 服务器
python -m http.server 3000

# 浏览器打开 http://localhost:3000
# 流程：/ → login.html → 选择用户 → frontend/index.html（SPA 主页）
```

### 3. AI 代理配置（可选，仅技能树编辑器需要）

```bash
cd backend
cp .env.example .env    # 编辑 .env 填写 AI 配置
```

AI 配置（`backend/.env`）：
```
AI_API_BASE_URL=https://one.loll.xyz/v1
AI_API_KEY=sk-你的key
AI_MODEL=gemini-2.5-pro-exp-03-25
PORT=3001
```

---

## 技术栈

| 层级 | 技术 |
|------|------|
| **前端** | 原生 HTML/CSS/JS，零框架依赖 |
| **图表** | Chart.js 4.4.0（雷达图、折线图、热力图） |
| **状态管理** | AppData 全局对象 + localStorage（仅登录状态）+ 后端 SQLite 持久化 |
| **后端** | Python FastAPI + httpx + SQLite |
| **定时任务** | APScheduler 3.x（每日 03:00 / 每周一 03:00） |
| **环境** | pixi（conda-forge，Python 3.12） |
| **AI** | OpenAI 兼容 API + Function Calling / Tool Use（9 个工具） |

---

## 架构特点

### 等级系统

- 等级公式：`expForLevel(L) = round(5.5632 × (L-1)² + 300)`，上限 **200 级**
- **10 个段位**（每 20 级一段）：初阶 → 历练 → 资深 → 荒野 → 征途 → 秘境 → 破晓 → 星途 → 传奇 → 不朽
- 每个段位有独立渐变色方案（10 套视觉主题），满级 Lv.200 有专属高光特效
- **经验系统已重构**：全局总经验 = 8 维经验之和（`get_total_exp_from_dimensions()`），每次行动/任务/习惯结算时从维度表实时 SUM 并重新计算等级

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

### 性能优化

项目已在以下方面做了性能优化：

| 优化项 | 说明 |
|--------|------|
| **页面 JS 懒加载** | 首次只加载 core（data.js/router.js/utils.js/components.js/app.js ~30 KB），页面 JS 按需动态加载 |
| **后端请求并行化** | 启动时 8 个后端 API 请求通过 `Promise.all` 并行发出 |
| **失败容错** | 后端不可用时降级使用模拟数据，页面 JS 加载失败显示友好提示 |
| **APScheduler 定时任务** | 每日归档/刷新/结算由后端定时执行，前端无需轮询 |

### 数据迁移进度

项目正从前端模拟数据向后端服务迁移。详见 [`后端迁移模块.md`](后端迁移模块.md)。

| 优先级 | 模块 | 状态 |
|--------|------|------|
| P0 | 用户数据 + 统计 | ✅ 已完成 |
| P1 | 习惯板块 | ✅ 已完成 |
| P2 | 行动记录 | ✅ 已完成 |
| P3 | 目标任务 | ✅ 已完成 |
| P4 | 等级系统 | ✅ 已完成（经验系统重构：8 维之和=全局总经验） |
| P5 | 仪表盘 + 成长记录 | ✅ 已完成（统计 API、热力图、EXP 趋势） |
| P6 | 奖励商城 | ✅ 已完成（含条件评估引擎、图片上传） |
| P7 | 全端联调 | ✅ 已完成（含后端模块化重构） |

### 后端数据库

共 **15 张表**：

| 表名 | 说明 |
|------|------|
| `users` | 用户信息（等级、经验、连续天数） |
| `user_stats_daily` | 每日统计（专注分钟、任务完成、习惯打卡、EXP） |
| `habits` | 习惯定义 |
| `habit_checkins` | 每日打卡记录 |
| `action_logs` | 行动记录 |
| `user_dimensions` | 八维属性经验 |
| `goals` | 目标 |
| `goal_milestones` | 目标里程碑 |
| `tasks` | 任务（含历史） |
| `scheduled_tasks` | 定时任务模板 |
| `rewards` | 奖励商城 |
| （`categories` | 8 维分类定义 — 硬编码在 `models/constants.py` 中） |

### 后端定时任务

| 触发时间 | 任务 |
|----------|------|
| 每日 03:00 | 归档未完成任务、从 daily 模板创建今日任务、结算昨日习惯 EXP、统计快照 |
| 每周一 03:00 | 从 weekly 模板创建本周任务 |

---

## 开发指引

### 新增页面

1. 在 `frontend/index.html` 中添加 `<div id="page-{name}" class="page">`
2. 创建 `frontend/js/pages/{name}.js`，导出 `render{Name}()` 函数（全局 function 声明即可）
3. 在 `router.js` 的 `PAGE_JS_MAP` 和 `navigateTo` 的 `renderers` 映射表中添加条目
4. 在 `index.html` 侧边栏添加导航项
5. 在正确的加载顺序位置添加 `<script>` 标签（在 `app.js` 之前）

### 修改等级/段位系统

- 前端公式：`frontend/js/utils.js` 第 116-170 行
- 后端公式：`backend/models/level.py`（等级公式唯一来源）
- 数据库：`backend/db/dimensions.py`（维度经验管理）+ `backend/db/init.py`（建表）
- 视觉主题：`frontend/js/utils.js` 第 142-170 行（10 个段位的渐变色方案）

### 技能树开发

- 编辑器入口：`frontend/skill-tree/index.html`（独立页面，不依赖主 SPA，支持 role 参数）
- 查看器：`frontend/skill-tree/viewer.html`（通过 iframe 嵌入技能页面）
- 主控制器：`skill-tree/js/app.js`（App 类，包含 CRUD、撤销/重做、AI 集成）
- 渲染引擎：`skill-tree/js/tree-renderer.js`（DOM + SVG 渲染）
- AI 集成：`skill-tree/js/ai-bridge.js`（通过后端 `/api/chat` 代理）

### 后端 API 路由一览

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/health` | 心跳检查 |
| POST | `/api/users/login` | 用户登录 |
| GET | `/api/users` | 获取所有用户列表 |
| GET | `/api/users/profile` | 获取用户完整数据 |
| POST | `/api/users/stats/sync` | 同步今日统计 |
| POST | `/api/users/exp/add` | 增加经验值 |
| GET/POST | `/api/habits` | 习惯列表/创建 |
| PUT/DELETE | `/api/habits/{id}` | 更新/删除习惯 |
| POST | `/api/habits/{id}/toggle` | 打卡三态切换 |
| GET | `/api/habits/stats` | 习惯统计卡片 |
| GET | `/api/habits/insights` | 4 条智能洞察 |
| GET | `/api/habits/last-week` | 上周打卡数据 |
| GET/POST | `/api/actions` | 行动记录查询/提交 |
| GET | `/api/actions/today-stats` | 今日行动统计 |
| GET | `/api/activities/feed` | 动态播报列表 |
| GET | `/api/activities/recent` | 仪表盘近期动态 |
| GET/POST | `/api/goals` | 目标列表/创建 |
| PUT/DELETE | `/api/goals/{id}` | 更新/删除目标 |
| POST | `/api/goals/{id}/claim` | 领取目标奖励 |
| GET/POST | `/api/tasks` | 今日任务/创建 |
| GET | `/api/tasks/all` | 所有任务分页 |
| PUT/PATCH/DELETE | `/api/tasks/{id}` | 更新/状态变更/删除 |
| POST | `/api/tasks/{id}/claim` | 领取任务 EXP |
| DELETE | `/api/tasks/history` | 清空历史任务 |
| GET/POST | `/api/scheduled-tasks` | 定时任务模板 |
| PUT/DELETE | `/api/scheduled-tasks/{id}` | 更新/删除模板 |
| GET | `/api/stats/profile` | 6 项统计 + 8 维进度 |
| GET | `/api/stats/yearly-activity` | 年度热力图 |
| GET | `/api/stats/daily-exp` | 每日 EXP 趋势 |
| POST | `/api/stats/recalc-dimensions` | 重算维度经验 |
| GET/POST | `/api/rewards` | 奖励列表/创建 |
| PUT/DELETE | `/api/rewards/{id}` | 更新/删除奖励 |
| POST | `/api/rewards/{id}/claim` | 领取奖励 |
| POST | `/api/rewards/{id}/manual-confirm` | 手动确认条件 |
| POST | `/api/rewards/reevaluate` | 重新评估所有奖励 |
| POST | `/api/rewards/{id}/image` | 上传奖励图片 |
| POST | `/api/chat` | AI 代理（技能树编辑） |

### 后端开发

- API 路由在 `backend/routers/` — 每个模块一个资源域（`health.py`、`users.py`、`habits.py` 等）
- 数据库操作在 `backend/db/` — 每个模块一个功能域（`users.py`、`habits.py`、`tasks.py` 等）
- AI 代理端点 `POST /api/chat` 转发到可配置的 LLM API，支持 9 个 Tool Use（定义在 `backend/services/ai_service.py`）
- AI 配置通过 `backend/.env`：`AI_API_BASE_URL`、`AI_API_KEY`、`AI_MODEL`
- 等级公式唯一来源：`backend/models/level.py`

---

## 8 个属性维度

| 维度 | ID | 颜色 | EXP 倍率 | 说明 |
|------|-----|-------|----------|------|
| 健康 | health | `#FF7B72` | 10× | 运动、睡眠、饮食、冥想 |
| 学习 | study | `#58D5C9` | 10× | 读书、课程、研究、刷信息 |
| 关系 | relation | `#FF91A8` | 8× | 家人、朋友、社交、社群 |
| 工作 | work | `#FFCA40` | 12× | 本职工作、项目推进、任务执行 |
| 创作 | create | `#B794F6` | 8× | 写作、出内容、做模板、录视频 |
| 财务 | finance | `#4ADE80` | 6× | 记账、理财、副业变现 |
| 爱好 | hobby | `#F472B6` | 7× | 游戏、音乐、旅行、放松 |
| 魅力 | soul | `#FBBF24` | 9× | 穿搭、气质、社交表达、个人形象 |