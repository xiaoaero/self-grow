# CLAUDE.md

本文件为 Claude Code (claude.ai/code) 提供本仓库的代码指引。

## 项目概述

**Self Grow (个人成长系统)** — 基于原生 HTML/CSS/JS 的单页应用 + FastAPI 后端的个人成长追踪系统。核心功能包括：等级段位体系、习惯追踪、任务管理、目标规划、八维属性雷达图、奖励商城（含条件解锁/领取双重校验）、可视化技能树编辑器（支持 AI 生成节点）、桌面端 Electron 打包。

## 架构概览

```
self_grow_system/
├── frontend/              # SPA（无框架，纯原生 JS）
│   ├── index.html         # 应用壳 — 侧边栏、页面容器、模态框、SVG 渐变色定义
│   ├── css/               # 加载顺序：variables → layout → sidebar → components → pages
│   ├── js/                # 加载顺序：data → router → utils → components → pages → app
│   │   ├── data.js        # AppData 全局数据模型 + 8 维 SVG 图标定义
│   │   ├── router.js      # navigateTo() — SPA 路由，PAGE_JS_MAP 懒加载映射
│   │   ├── utils.js       # 工具函数（toast、模态框、等级公式、段位配色、后端 API 封装 60+ 函数）
│   │   ├── components.js  # 可复用渲染函数（统计卡片、经验条、进度条）
│   │   └── pages/         # 每页一个文件，通过 router.js 动态加载
│   └── skill-tree/        # 技能树编辑器（独立 SPA，支持 view/editor/admin 三模式）
├── desktop/               # Electron 桌面应用
│   ├── main.js            # 主进程：启动后端 exe、创建窗口、进程管理
│   ├── preload.js         # 预加载脚本
│   ├── package.json       # Electron 应用配置
│   ├── make-portable.js   # 绿色版构建脚本
│   └── build.bat          # 一键构建批处理
├── backend/               # Python FastAPI 服务（模块化架构）
│   ├── main.py            # 入口点：app 工厂、生命周期、路由注册、定时任务
│   ├── config.py          # 配置：AI 端点/Key/模型、端口、数据库路径（含打包模式检测）
│   ├── database.py        # 向后兼容层（re-export from db/ 子模块）
│   ├── models/            # 数据模型（等级公式、常量、段位表）
│   │   ├── level.py       # 等级公式（唯一来源：exp_for_level / total_exp_for_level / level_from_total_exp）
│   │   └── constants.py   # CATEGORIES（8维）、RANK_TABLE（10段位）、维度经验计算规则、作息规律检测
│   ├── schemas/           # Pydantic 请求/响应模型
│   │   └── api.py         # 26+ 个 Pydantic 模型定义
│   ├── db/                # 数据访问层（每个模块一个功能域）
│   │   ├── connection.py  # DB_PATH + get_conn()
│   │   ├── init.py        # 建表（16张表）+ 默认用户/奖励 + 数据迁移
│   │   ├── users.py       # 用户 CRUD + 每日统计 CRUD
│   │   ├── habits.py      # 习惯 CRUD + 打卡记录 + 连续计算
│   │   ├── actions.py     # 行动记录 CRUD + 今日统计 + 动态播报 + 睡眠/复盘限制检测
│   │   ├── routines.py    # 规律作息持久化（SQLite 替代内存缓存）
│   │   ├── goals.py       # 目标 CRUD + 里程碑
│   │   ├── tasks.py       # 任务 CRUD + 领取奖励
│   │   ├── scheduled_tasks.py  # 定时任务模板 CRUD
│   │   ├── dimensions.py  # 8维属性经验 CRUD
│   │   ├── stats.py       # 统计查询（热力图、EXP趋势、profile）
│   │   ├── rewards.py     # 奖励 CRUD + 条件评估引擎
│   │   └── batch.py       # 定时批处理（archive/refresh/settle/snapshot）
│   ├── services/          # 业务逻辑层
│   │   ├── exp_service.py # EXP 奖励编排（消除5次重复模式）
│   │   ├── ai_service.py  # 技能树 AI 代理（9个 Tool Use 工具 + 系统提示词 + HTTP 调用）
│   │   ├── ai_client.py   # AI HTTP 客户端封装（通用）
│   │   ├── ai_action_service.py  # 行动记录 AI 解析（对话式提取行动）
│   │   └── ai_habit_service.py   # 习惯 AI 分析（智能洞察 + 图标分配）
│   ├── prompts/           # AI 系统提示词模板
│   │   ├── action_parse.py       # 行动解析提示词
│   │   ├── habit_analysis.py     # 习惯分析提示词
│   │   ├── habit_icon.py         # 习惯图标分配提示词
│   │   └── skill_tree.py         # 技能树 AI 提示词
│   ├── routers/           # API 路由层
│   │   ├── deps.py        # FastAPI 依赖注入（get_current_user 消除 ~31 次重复验证）
│   │   ├── health.py      # GET /api/health
│   │   ├── users.py       # 用户 API（5个端点）
│   │   ├── habits.py      # 习惯 API（9个端点，含 AI 分析）
│   │   ├── actions.py     # 行动记录 API（7个端点，含 AI 对话 + 作息规律状态）
│   │   ├── goals.py       # 目标 API（5个端点）
│   │   ├── tasks.py       # 任务 API（8个端点）
│   │   ├── scheduled_tasks.py  # 定时任务模板 API（4个端点）
│   │   ├── stats.py       # 统计 API（5个端点）
│   │   ├── rewards.py     # 奖励商城 API（8个端点）
│   │   └── ai.py          # 技能树 AI 聊天 API（1个端点）
│   ├── tests/             # 测试
│   │   ├── conftest.py    # pytest 配置
│   │   ├── test_ai_action.py    # AI 行动解析测试
│   │   └── test_sleep_action.py # 睡眠行动测试
│   ├── uploads/           # 奖励图片上传目录
│   ├── pixi.toml          # pixi 环境（Python 3.12 + FastAPI + httpx + APScheduler）
│   └── .env               # AI 配置（端点、Key、模型）
├── docs/                  # 项目文档
│   ├── 1.0版本审查报告.md     # v1.0 上线前全面审查（23条发现）
│   ├── 1.0版本修复方案.md     # 修复方案文档
│   ├── 打包与更新指南.md      # 桌面应用打包与更新流程
│   ├── 维度经验计分规则.md     # 8 维经验计算规则详情
│   └── 项目开发规划.md        # 后续开发规划
├── login.html             # 登录页（调用后端 /api/users 列表）
├── index.html             # 根入口 → 自动跳转 login.html
├── build.bat              # 桌面应用一键构建脚本
├── README.md              # 项目文档
├── CLAUDE.md              # 本文件
└── memory/                # 开发记录
    ├── MEMORY.md          # 记忆索引
    └── ...
```

### 关键架构决策

- **前端路由**：手写 SPA 路由 `navigateTo()`（`router.js`），页面是 `<div class="page">` 容器，通过 `.page--active` 切换。侧边栏支持"行动"/"任务"/"技能"三级子导航。
- **数据层**：前端 `AppData` 对象（`data.js`）启动时通过 `Promise.all` 并行加载 8 个后端 API。后端不可用时降级使用模拟数据。后端 profile API（`/api/users/profile`）覆盖 `AppData.user` + `AppData.todayStats` + `AppData.yesterdayStats`。
- **经验系统**：全局总经验 = 8 维经验之和（`get_total_exp_from_dimensions()`），每次获得经验时实时 SUM 并重新计算等级。等级公式唯一来源：`backend/models/level.py`。
- **技能树**：独立 SPA 位于 `skill-tree/`，使用自定义 `TreeRenderer`（DOM + SVG）渲染节点和连线。AI 集成（`AIBridge`）通过后端 `/api/chat` 代理调用 LLM，支持 9 个 Tool Use 工具。
- **JS 加载顺序**：`data.js` → `router.js` → `utils.js` → `components.js` → 页面脚本 → `app.js`。顺序重要，因为后面的脚本引用前面的全局变量。
- **桌面端**：Electron 主进程启动 PyInstaller 打包的后端 exe，轮询 `/api/health` 等待就绪后加载前端。数据目录分离：开发模式在 `backend/`，打包模式在 `%APPDATA%/SelfGrow/`。

## 启动方式

```bash
# 1. 后端（必须先启动）
cd backend
pixi run python main.py     # 运行在 http://localhost:3001
# 自动启动 APScheduler 定时任务（每日 03:00 归档/结算，每周一 03:00 刷新）

# 2. 前端（项目根目录）
cd D:\pycharm\projec\self_grow_system
python -m http.server 3000    # 运行在 http://localhost:3000

# 3. 打开 http://localhost:3000/login.html 选择用户登录

# 或一键桌面应用
build.bat                     # 打包 → 运行 desktop/dist/SelfGrow/Self Grow.exe
```

后端首次运行自动创建 `data.db`，包含两个默认用户：`test`（Lv.188，含完整模拟数据）和 `admin`（Lv.99, 管理员权限）。

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
- 计分规则文档：`docs/维度经验计分规则.md`

### 技能树开发
- 编辑器入口：`frontend/skill-tree/index.html`（独立页面，不依赖主 SPA，支持 role 参数）
- 查看器：`frontend/skill-tree/viewer.html`（通过 iframe 嵌入技能页面）
- 主控制器：`skill-tree/js/app.js`（App 类，包含 CRUD、撤销/重做、AI 集成）
- 渲染引擎：`skill-tree/js/tree-renderer.js`（DOM + SVG 渲染）
- AI 集成：`skill-tree/js/ai-bridge.js`（通过后端 `/api/chat` 代理）

### 后端 AI 服务
- **技能树 AI** → `backend/services/ai_service.py`（9 个 Tool Use 工具）
- **行动解析 AI** → `backend/services/ai_action_service.py`（对话式提取行动记录）
- **习惯分析 AI** → `backend/services/ai_habit_service.py`（智能洞察 + 图标分配）
- AI 提示词在 `backend/prompts/`，每个 AI 功能一个独立文件
- AI 配置通过 `backend/.env`：`AI_API_BASE_URL`、`AI_API_KEY`、`AI_MODEL`

### 桌面应用打包
- 详细指南：`docs/打包与更新指南.md`
- 一键构建：`build.bat`（PyInstaller 打包后端 → Electron 打包 → 绿色版 zip）
- 按改动范围分步打包：仅前端改 / 仅后端改 / 前后端都改
- 打包模式数据目录：`%APPDATA%/SelfGrow/`（独立于安装目录，更新不丢失）
- 测试：`cd backend && pixi run pytest`

## 8 个属性维度的颜色约定

| 维度 | ID | 颜色 | EXP 倍率 |
|------|-----|-------|----------|
| 健康 | health | `#FF7B72` | 10× |
| 学习 | study | `#58D5C9` | 10× |
| 关系 | relation | `#FF91A8` | 8× |
| 工作 | work | `#FFCA40` | 12× |
| 创作 | create | `#B794F6` | 8× |
| 财务 | finance | `#4ADE80` | 6× |
| 爱好 | hobby | `#F472B6` | 7× |
| 魅力 | soul | `#FBBF24` | 9× |
