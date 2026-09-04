# CLAUDE.md

本文件为 Claude Code (claude.ai/code) 提供本仓库的代码指引。

## 项目概述

**Self Grow (个人成长系统)** — 基于原生 HTML/CSS/JS 的单页应用 + FastAPI 后端的个人成长追踪系统。核心功能包括：等级段位体系、习惯追踪、任务管理、目标规划、八维属性雷达图、奖励商城（含条件解锁/领取双重校验）、可视化技能树编辑器（AI 生成节点走 **LangGraph**）、**表达训练系统（AI 出题 + 实时语音 + 评分 + 填充词检测）**、**统一协调 Agent（多智能体 + 反问机制 + 悬浮球对话）**、**MCP 插件（24 个业务工具暴露）**、**用户中心（多模型管理 + 动态切换）**。部署方式为纯 Web + [Docker 部署方案](docs/Docker部署方案.md)。

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
│   │   ├── chat.js        # 协调 Agent 悬浮球对话框（FIFO 反问卡片队列）
│   │   ├── pages/         # 每页一个文件，通过 router.js 动态加载
│   │   │   ├── agent.js   # 表达训练 — AI 出题、答题计时、填充词检测、AI 评分（四维打分）
│   │   │   ├── usercenter.js # 用户中心 — 基础信息 + 多模型管理（LLM/ASR 增删改切换）
│   │   │   └── ...        # 其他 9 个页面文件
│   │   └── app.js         # 启动初始化 + 全局版本号显示
│   └── skill-tree/        # 技能树编辑器（独立 SPA，支持 view/editor/admin 三模式）
├── backend/               # Python FastAPI 服务（模块化架构）
│   ├── main.py            # 入口点：app 工厂、生命周期、路由注册、定时任务
│   ├── config.py          # 配置：AI 端点/Key/模型、端口、数据库路径、前端目录、git 版本号
│   ├── mcp_server.py      # MCP 插件 — FastMCP v2，24 个业务工具（stdio/HTTP 双传输）
│   ├── pixi.toml          # pixi 环境（唯一依赖事实源，见 tools/export_reqs.py）
│   ├── database.py        # 向后兼容层（re-export from db/ 子模块）
│   ├── models/            # 数据模型（等级公式、常量、段位表）
│   ├── schemas/           # Pydantic 请求/响应模型
│   ├── db/                # 数据访问层（每个模块一个功能域，含 model_configs.py、task_history.py）
│   ├── services/          # 业务逻辑层
│   │   ├── ai_client.py   # 统一 AI HTTP 客户端（动态读取启用模型配置）
│   │   ├── coordinator/   # 统一协调 Agent — 主图路由 + 6 子 Agent + ask_user 反问
│   │   │   ├── graph.py   # 主图编译 + run/resume
│   │   │   ├── router_node.py    # LLM 路由决策
│   │   │   ├── synthesize_node.py # 汇总回复
│   │   │   ├── agents/    # action/query/goal/task/habit/reward 6 个子 Agent
│   │   │   └── llm.py     # 动态 LLM 实例（get_llm，缓存 key 含模型配置）
│   │   ├── skill_tree_ai/ # 技能树 AI 编辑（LangGraph）
│   │   │   ├── graph.py   # StateGraph 编译 + run/resume + _format_result
│   │   │   ├── node.py    # Agent 节点（LLM + 工具循环 + 消息截断防孤儿 ToolMessage）
│   │   │   ├── tools.py   # 9 个工具（按节点 ID 操作 + 确认守卫）
│   │   │   ├── state.py   # SkillTreeChatState（checkpointer 持久化）
│   │   │   └── prompts.py # 系统提示词 + 树状态注入
│   │   ├── expression_service.py  # 表达训练 AI 出题/评分 + 提示生成
│   │   └── ...            # 其他服务模块
│   ├── prompts/           # AI 系统提示词模板（技能树 AI 的在新链路 services/skill_tree_ai/prompts.py）
│   ├── routers/           # API 路由层
│   │   ├── coordinator.py     # 协调 Agent API（chat/resume/stream）
│   │   ├── skill_tree_ai.py   # 技能树 AI API（chat/resume/stream，替代旧 /api/chat）
│   │   ├── model_configs.py   # 模型配置 API（5 端点 + 连通性测试）
│   │   ├── skill_tree.py      # 技能树 CRUD API（9 个端点）
│   │   ├── ai.py              # [已废弃] 旧 /api/chat，已从 main.py 注销（无鉴权）
│   │   └── ...            # 其他 11 个路由模块
│   └── tests/             # 测试
├── docs/                  # 项目文档（含 MCP插件说明.md、技能树AI-LangGraph改造方案.md）
└── memory/                # 开发记录
    └── MEMORY.md          # 记忆索引
```

### 关键架构决策

- **前端路由**：手写 SPA 路由 `navigateTo()`（`router.js`），页面是 `<div class="page">` 容器，通过 `.page--active` 切换。侧边栏支持"行动"/"任务"/"技能"/"扩展"四级子导航。
- **数据层**：前端 `AppData` 对象（`data.js`）启动时通过 `Promise.all` 并行加载 8 个后端 API。后端不可用时降级使用模拟数据。后端 profile API（`/api/users/profile`）覆盖 `AppData.user` + `AppData.todayStats` + `AppData.yesterdayStats`。
- **经验系统**：全局总经验 = 8 维经验之和（`get_total_exp_from_dimensions()`），每次获得经验时实时 SUM 并重新计算等级。等级公式唯一来源：`backend/models/level.py`。
- **技能树**：独立 SPA 位于 `skill-tree/`，使用自定义 `TreeRenderer`（DOM + SVG）渲染节点和连线。AI 集成（`AIBridge`）通过 LangGraph 端点 `/api/skill-trees/{id}/chat` 调用后端 Agent 图（服务端 checkpointer 维护会话），工具按节点 ID 操作，危险操作走确认卡片（`pending_confirmation` + `/chat/resume`）。后端持久化替代了 localStorage。
- **统一协调 Agent**：主图（LangGraph）LLM 路由到 6 个子 Agent（action/query/goal/task/habit/reward），子 Agent 通过公共 `ask_user` 工具反问用户；前端 `chat.js` 悬浮球维护 FIFO 反问卡片队列（最多 2 张）。上下文管理：近 5 条记录 + 3 轮反问窗口 + sessionStorage 持久化 thread_id。
- **多模型动态切换**：`model_configs` 表按用户存储 LLM/ASR 配置，`coordinator/llm.py` 的 `get_llm(user_id)` 动态读取启用配置（缓存 key 含 model/base_url/api_key），切换后自动重建实例。`ai_client.py` / `asr_service.py` / 习惯 AI / 表达训练 WebSocket 同样动态读取。
- **表达训练**：扩展侧边栏 → AI Agent 页面，前端 `agent.js` 渲染两视图（训练/历史），后端 `expression_service.py` 处理 AI 出题/评分逻辑，`expressions.py` 管理数据库题目/回答。
- **JS 加载顺序**：`data.js` → `router.js` → `utils.js` → `components.js` → 页面脚本 → `app.js`。顺序重要，因为后面的脚本引用前面的全局变量。

## 启动方式

后端统一用 pixi 管理环境与任务（依赖来源见 [依赖管理](#依赖管理)）：

```bash
# 开发模式：后端（backend/ 下运行）
cd backend
pixi run start     # 运行在 http://localhost:3001（自动启动 APScheduler 定时任务：每日 03:00 归档/结算，每周一 03:00 刷新）
pixi run test      # 运行 pytest
pixi run mcp       # 启动 MCP 插件服务器（stdio 模式，见 docs/MCP插件说明.md）
```

前端（项目根目录，需一个 HTTP 服务器；开发模式不要直接打开 HTML 文件）：

```bash
cd D:\pycharm\projec\self_grow_system
python -m http.server 3000    # 运行在 http://localhost:3000
```

打开 http://localhost:3000/login.html 选择用户登录。生产部署见 [Docker 部署方案](docs/Docker部署方案.md)。

### 依赖管理

**`backend/pixi.toml` 的 `[dependencies]` / `[pypi-dependencies]` 是唯一事实源**，开发环境由 pixi 提供。

- `requirements.txt` 不是手写清单，而是由 pixi 锁定版本导出的产物（供 pip / Docker 安装，保证与开发环境版本一致）。
- 重新生成：`pixi run export-reqs`（即 `backend/tools/export_reqs.py`）。
- 改依赖：编辑 `pixi.toml` → `pixi update` → 必要时 `pixi run export-reqs`。不要在 requirements.txt 里裸改版本。

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
- 注意幂等：`create_action_log` 写入时 `exp_earned` 先占位 0，`award_exp_and_recalc` 后回写（防重复结算跳过）
- 计分规则文档：`docs/维度经验计分规则.md`

### 技能树开发
- 编辑器入口：`frontend/skill-tree/index.html`（独立页面，不依赖主 SPA，支持 role 参数）
- 查看器：`frontend/skill-tree/viewer.html`（通过 iframe 嵌入技能页面）
- 主控制器：`skill-tree/js/app.js`（App 类，包含 CRUD、撤销/重做、AI 集成）
- 渲染引擎：`skill-tree/js/tree-renderer.js`（DOM + SVG 渲染）
- AI 集成：`skill-tree/js/ai-bridge.js`（LangGraph 端点 `/api/skill-trees/{id}/chat`，服务端会话 + 确认卡片）
- 后端持久化：`backend/routers/skill_tree.py` + `backend/db/skill_tree.py`
- 后端 AI 图：`backend/routers/skill_tree_ai.py` + `backend/services/skill_tree_ai/`（LangGraph StateGraph，单 agent 节点 + 9 个工具，按节点 ID 操作）
- 旧 `/api/chat`（`routers/ai.py` + `services/ai_service.py`）已下线（无鉴权），仅保留文件作参考
- 撤销/重做约定：历史栈为「改后快照」语义——所有操作先修改再 `saveHistory()`；`loadData()` 时清空历史并压入基线快照（防跨树污染）

### 统一协调 Agent 开发
- 前端：`frontend/js/chat.js`（悬浮球 + 对话框 + 反问卡片 FIFO 队列）
- 后端主图：`backend/services/coordinator/graph.py`（路由 → 子 Agent → 汇总）
- 子 Agent：`backend/services/coordinator/agents/`（6 个域 Agent，基类 `base.py`）
- 反问机制：`agents/ask_user_tool.py` 公共工具 + dispatch interrupt 检测
- 提示词：`backend/prompts/coordinator.py`
- 设计文档：`docs/统一协调Agent设计方案.md`

### MCP 插件开发
- 服务器：`backend/mcp_server.py`（FastMCP v2，6 域 24 工具，复用 `db/`、`services/` 层）
- 枚举约束用 `typing.Literal`（category/sub_type/priority/status 等），数值范围函数内校验
- 单用户模式：`SELF_GROW_USER_ID` 环境变量（默认 1）；`MCP_TRANSPORT=streamable-http` 切 HTTP
- 验证脚本：`backend/test_mcp_client.py`；文档：`docs/MCP插件说明.md`

### 表达训练开发
- 前端页面：`frontend/js/pages/agent.js`（`renderAgent()`，两视图，训练/历史滑块切换）
- 填充词检测：`agent.js` 中 `detectFillerWordsV2()` — 四重规则（密度、高频重复、句首、簇拥）
- 后端路由：`backend/routers/expression.py`（10 个端点）
- 数据库操作：`backend/db/expressions.py`（题目 CRUD + 回答 CRUD + 用户统计）
- 业务逻辑：`backend/services/expression_service.py`（出题/评分/提示生成，含 LLM 调用）
- AI 提示词：`backend/prompts/expression.py`（三套提示词：出题、评分、提示生成）
- 样式：`frontend/css/pages.css`（`.expr__*` 类，~300 行）
- 出题流程：AI 调用 `query_history_questions` 工具查重 → 生成新题 → 存入数据库
- 评分流程：回填填充词统计 → AI 四维评分 → 缓存结果到数据库

### 用户中心 / 模型配置开发
- 前端：`frontend/js/pages/usercenter.js`（基础信息卡 + 模型信息卡，添加/编辑/删除/切换启用/连通性测试）
- 数据层：`backend/db/model_configs.py`（CRUD + `set_active` 同类型互斥 + `get_active_config`）
- 路由：`backend/routers/model_configs.py`（5 端点 + POST /test）
- 动态生效：所有 AI 服务经 `get_llm(user_id)` / `ai_client.py` 读取启用配置，切换即生效（缓存 key 机制）
- 版本号：`config.get_version()`（git describe），`/api/health` 返回，前端右下角显示

### 后端 AI 服务
- **技能树 AI** → `backend/services/skill_tree_ai/`（LangGraph 图，9 个工具，配合 `routers/skill_tree_ai.py` 的 chat/resume/stream 端点）
- **统一协调 Agent** → `backend/services/coordinator/`（主/次多智能体架构 + ask_user 反问）
- **行动解析 AI** → `backend/services/ai_action_service.py`（对话式提取行动记录）
- **习惯分析 AI** → `backend/services/ai_habit_service.py`（智能洞察 + 图标分配）
- **表达训练 AI** → `backend/services/expression_service.py`（出题 + 评分 + 提示生成）
- AI 提示词在 `backend/prompts/`（技能树旧提示词在 `services/skill_tree_ai/prompts.py`）
- AI 配置通过 `backend/.env` 兜底：`AI_API_BASE_URL`、`AI_API_KEY`、`AI_MODEL`；实际运行时优先读 `model_configs` 表中当前启用的配置（用户中心可切换）

### 生产部署（Docker）
- 详细方案：`docs/Docker部署方案.md`
- 依赖安装走 `requirements.txt`（由 `pixi run export-reqs` 从 pixi 锁定版本生成）
- 测试：`cd backend && pixi run test`

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
