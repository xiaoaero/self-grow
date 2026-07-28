# Self Grow — 个人成长系统

> 一个原生 HTML/CSS/JS 单页应用 + FastAPI 后端 + Electron 桌面的个人成长追踪系统。包含等级段位体系、习惯追踪、任务管理、目标规划、八维属性雷达图、奖励商城（含条件解锁/领取双重校验）、可视化技能树编辑器（支持 AI 生成节点）、**表达训练系统（AI 出题 + 实时评分 + 填充词检测）**，已完成桌面版打包（绿色版 zip）。

---

## 项目结构

```
self_grow_system/
├── README.md                         # 项目文档（本文件）
├── CLAUDE.md                         # Claude Code 代码指引
├── build.bat                         # 桌面应用一键构建脚本（Windows）
├── dev.bat                           # 开发模式一键启动（Windows）
├── dev.sh                            # 开发模式一键启动（Unix）
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
│   │   └── pages.css                 # 各页面独立样式（~122 KB，含表达训练 ~300 行）
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
│   │       ├── skills.js             # 技能 — 技能卡片列表 → 技能树查看器（iframe）+ 技能库
│   │       ├── rewards.js            # 奖励商城 — 8 分类筛选、解锁/领取双重条件、图片上传
│   │       └── agent.js              # 表达训练 — AI 出题、答题计时、填充词检测、AI 评分（四维打分）
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
│   ├── config.py                     # 配置从 .env 加载（AI 端点、Key、模型、端口），支持打包模式
│   ├── database.py                   # 向后兼容层（re-export from db/ 子模块）
│   │
│   ├── models/                       # 数据模型
│   │   ├── level.py                  # 等级公式（唯一来源，含满级处理）
│   │   └── constants.py              # 8 维分类定义、10 段位表、颜色映射、维度经验计算规则
│   ├── schemas/                      # Pydantic 请求/响应模型
│   │   └── api.py                    # 26+ 个模型定义
│   │
│   ├── db/                           # 数据访问层（每模块一个功能域）
│   │   ├── connection.py             # DB_PATH + get_conn()
│   │   ├── init.py                   # 建表（17 张）+ 默认用户/奖励 + 数据迁移
│   │   ├── users.py                  # 用户 + 每日统计 CRUD
│   │   ├── habits.py                 # 习惯 + 打卡记录 CRUD
│   │   ├── actions.py                # 行动记录 CRUD + 今日统计 + 动态播报 + 睡眠/复盘限制检测
│   │   ├── routines.py               # 规律作息持久化（SQLite 替代内存缓存）
│   │   ├── goals.py                  # 目标 CRUD
│   │   ├── tasks.py                  # 任务 CRUD
│   │   ├── scheduled_tasks.py        # 定时任务模板 CRUD
│   │   ├── dimensions.py             # 8 维属性经验 CRUD
│   │   ├── stats.py                  # 统计查询（热力图、EXP 趋势、profile）
│   │   ├── rewards.py                # 奖励 CRUD + 条件评估引擎
│   │   ├── batch.py                  # 定时批处理函数
│   │   ├── skill_tree.py             # 技能树 CRUD（替代 localStorage）
│   │   └── expressions.py            # 表达训练题目/回答 CRUD + 用户统计
│   │
│   ├── services/                     # 业务逻辑层
│   │   ├── exp_service.py            # EXP 奖励编排（消除重复模式）
│   │   ├── ai_service.py             # 技能树 AI 代理（9 个 Tool Use）
│   │   ├── ai_client.py             # AI HTTP 客户端封装
│   │   ├── ai_action_service.py      # 行动记录 AI 解析（对话式提取）
│   │   ├── ai_habit_service.py       # 习惯 AI 分析（智能洞察 + 图标分配）
│   │   └── expression_service.py     # 表达训练 AI 出题/评分 + 提示生成
│   │
│   ├── prompts/                      # AI 系统提示词模板
│   │   ├── action_parse.py           # 行动解析提示词
│   │   ├── habit_analysis.py         # 习惯分析提示词
│   │   ├── habit_icon.py             # 习惯图标分配提示词
│   │   ├── skill_tree.py             # 技能树 AI 提示词
│   │   └── expression.py             # 表达训练出题/评分/提示生成提示词
│   │
│   ├── routers/                      # API 路由层
│   │   ├── deps.py                   # 依赖注入（get_current_user 消除 ~31 次重复验证）
│   │   ├── health.py                 # GET /api/health
│   │   ├── users.py                  # 用户 API（5 个端点）
│   │   ├── habits.py                 # 习惯 API（9 个端点，含 AI 分析）
│   │   ├── actions.py                # 行动记录 API（7 个端点，含 AI 对话 + 作息状态 + CSV 导出）
│   │   ├── goals.py                  # 目标 API（5 个端点）
│   │   ├── tasks.py                  # 任务 API（8 个端点）
│   │   ├── scheduled_tasks.py        # 定时任务模板 API（4 个端点）
│   │   ├── stats.py                  # 统计 API（5 个端点）
│   │   ├── rewards.py                # 奖励商城 API（8 个端点）
│   │   ├── ai.py                     # 技能树 AI 聊天 API（1 个端点）
│   │   ├── skill_tree.py             # 技能树 CRUD API（9 个端点）
│   │   └── expression.py             # 表达训练 API（10 个端点）
│   │
│   ├── tests/                        # 测试
│   │   ├── conftest.py               # pytest 配置
│   │   ├── test_ai_action.py         # AI 行动解析测试
│   │   └── test_sleep_action.py      # 睡眠行动测试
│   │
│   ├── .env                          # AI 配置（端点、Key、模型）
│   ├── .env.example                  # 配置模板
│   ├── pixi.toml                     # pixi 环境（Python 3.12 + FastAPI + httpx + APScheduler）
│   ├── test_hints.json               # 表达训练提示测试数据
│   └── data.db                       # SQLite 数据库文件（首次启动自动创建）
│
├── desktop/                          # Electron 桌面应用
│   ├── main.js                       # 主进程：启动后端 exe、创建窗口、进程管理
│   ├── preload.js                    # 预加载脚本
│   ├── package.json                  # Electron 应用配置
│   ├── make-portable.js              # 绿色版构建脚本
│   └── dist/                         # 构建产出（gitignored）
│       └── SelfGrow/                 # 绿色版应用目录
│
├── docs/                             # 项目文档
│   ├── 1.0版本审查报告.md            # v1.0 上线前全面审查（23 条发现）
│   ├── 1.0版本修复方案.md            # 修复方案文档
│   ├── 打包与更新指南.md             # 桌面应用打包与更新流程
│   ├── 维度经验计分规则.md           # 8 维经验计算规则详情
│   ├── 项目开发规划.md              # 后续开发规划
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
| **技能树编辑器** | 独立 SPA，支持 view/editor/admin 三模式，可视化节点编辑（拖拽、缩放、连线）、学习状态管理（locked/available/learning/completed）、前置条件检查、撤销/重做、AI 智能生成节点（9 种 Tool Use） |
| **奖励商城** | 8 分类筛选、解锁条件 + 领取条件双重验证、图片上传、手动确认条件 |
| **表达训练** | 扩展 → AI Agent，AI 出题（4 种题型，实时查重避免重复）、答题计时器（开始/暂停/完成）、实时填充词高亮检测（密度+重复+句首+簇拥四重规则）、AI 评分（流畅度/逻辑性/内容质量/语言表达四维 0-100 分）、双层展开提示面板 |

---

## 快速启动

> ⚠️ 开发模式必须使用 HTTP 服务器打开，不要直接双击 HTML 文件

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

### 3. 一键启动（开发模式）

```bash
# Windows
dev.bat

# Unix/Mac
bash dev.sh
```

### 4. AI 代理配置（可选）

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

AI 功能支持四个场景：
- **技能树编辑器**：AI 智能生成节点、修改节点、前置条件分析（9 个 Tool Use 工具）
- **行动记录**：通过 AI 对话自然语言记录行动（解析为结构化数据存入后端）
- **习惯分析**：智能洞察分析 + 自动推荐习惯图标
- **表达训练**：AI 出题（查重避免重复）+ AI 评分（四维打分 + 填充词统计）+ 智能提示生成

### 5. 桌面应用打包

```bash
build.bat
# 构建产出：desktop/dist/SelfGrow/Self Grow.exe（绿色版）
```

详细打包指南见 [`docs/打包与更新指南.md`](docs/打包与更新指南.md)。

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
| **AI** | OpenAI 兼容 API + Function Calling / Tool Use（4 个 AI 服务） |
| **桌面** | Electron 主进程 + PyInstaller 后端 exe + 绿色版打包 |

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

| AI 服务 | 文件 | 工具数量 | 说明 |
|---------|------|----------|------|
| 技能树 | `ai_service.py` | 9 个 Tool Use | 生成/修改节点、前置条件分析、批量编辑 |
| 行动解析 | `ai_action_service.py` | 对话式提取 | 自然语言 → 结构化行动记录，支持多轮交互 |
| 习惯分析 | `ai_habit_service.py` | 智能洞察 + 图标 | 数据分析 + 习惯建议 + 自动分配图标 |
| 表达训练 | `expression_service.py` | 出题 + 评分 + 提示 | AI 出题（查重）、四维评分、智能提示生成 |

### 表达训练系统

**表达训练** 是扩展插件中的 AI 功能模块，帮助用户提升口头表达能力：

- **题型选择**：4 种题型（热门事件观点、情感表达、生活感悟、职场沟通），可多选
- **AI 出题**：调用 LLM 生成题目，自动查重（`query_history_questions` 工具），避免重复
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

### 性能优化

| 优化项 | 说明 |
|--------|------|
| **页面 JS 懒加载** | 首次只加载 core（data.js/router.js/utils.js/components.js/app.js ~30 KB），页面 JS 按需动态加载 |
| **后端请求并行化** | 启动时 8 个后端 API 请求通过 `Promise.all` 并行发出 |
| **失败容错** | 后端不可用时降级使用模拟数据，页面 JS 加载失败显示友好提示 |
| **APScheduler 定时任务** | 每日归档/刷新/结算由后端定时执行，前端无需轮询 |

### v1.0 开发里程碑

| 阶段 | 内容 | 状态 |
|------|------|------|
| P0 | 用户数据 + 统计持久化 | ✅ 已完成 |
| P1 | 习惯板块完整迁移 | ✅ 已完成 |
| P2 | 行动记录迁移 | ✅ 已完成 |
| P3 | 目标任务迁移 | ✅ 已完成 |
| P4 | 等级系统重构（8 维之和=全局总经验） | ✅ 已完成 |
| P5 | 仪表盘 + 成长记录统计 API | ✅ 已完成 |
| P6 | 奖励商城（条件评估引擎 + 图片上传） | ✅ 已完成 |
| P7 | 全端联调 + 后端模块化重构 | ✅ 已完成 |
| — | v1.0 上线前审查修复（17 条） | ✅ 已完成 |
| — | 桌面应用打包（Electron + PyInstaller） | ✅ 已完成 |
| — | AI 行动解析服务 | ✅ 已完成 |
| — | 习惯 AI 分析服务 | ✅ 已完成 |
| — | 技能树后端持久化（替代 localStorage） | ✅ 已完成 |
| — | 表达训练系统（AI 出题 + 评分 + 填充词检测） | ✅ 已完成 |

### 后端数据库

共 **17 张表**：

| 表名 | 说明 |
|------|------|
| `users` | 用户信息（等级、经验、连续天数） |
| `user_stats_daily` | 每日统计（专注分钟、任务完成、习惯打卡、EXP） |
| `habits` | 习惯定义 |
| `habit_checkins` | 每日打卡记录 |
| `action_logs` | 行动记录（含 sub_type/sleep 字段） |
| `routine_streak` | 规律作息连续天数持久化 |
| `user_dimensions` | 八维属性经验 |
| `goals` | 目标 |
| `goal_milestones` | 目标里程碑 |
| `tasks` | 任务（含历史） |
| `scheduled_tasks` | 定时任务模板 |
| `rewards` | 奖励商城 |
| `reward_drafts` | 奖励创建草稿 |
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
- 查看器：`frontend/skill-tree/viewer.html`（通过 iframe 嵌入技能页面）
- 主控制器：`skill-tree/js/app.js`（App 类，CRUD、撤销/重做、AI 集成）
- 渲染引擎：`skill-tree/js/tree-renderer.js`（DOM + SVG 渲染）
- AI 集成：`skill-tree/js/ai-bridge.js`（通过后端 `/api/chat` 代理）
- 后端持久化：`backend/routers/skill_tree.py` + `backend/db/skill_tree.py`

### 表达训练开发

- 前端页面：`frontend/js/pages/agent.js`（`renderAgent()`，两视图：训练/历史）
- 后端路由：`backend/routers/expression.py`（10 个端点）
- 数据库操作：`backend/db/expressions.py`（题目 CRUD + 回答 CRUD + 统计）
- 业务逻辑：`backend/services/expression_service.py`（出题/评分/提示生成）
- AI 提示词：`backend/prompts/expression.py`（出题 + 评分 + 提示三套提示词）
- 样式：`frontend/css/pages.css`（`.expr__*` 类，~300 行）

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
| GET | `/api/habits/insights` | 4 条智能洞察（AI 分析） |
| GET | `/api/habits/last-week` | 上周打卡数据 |
| POST | `/api/habits/ai-analyze` | AI 习惯分析 |
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
| GET/POST/PUT/DELETE | `/api/skill-trees` | 技能树 CRUD |
| GET/PUT | `/api/skill-trees/user-skills/list` | 用户技能 ID 管理 |
| POST | `/api/expression/generate` | 表达训练出题 |
| POST | `/api/expression/answer` | 创建回答记录 |
| POST | `/api/expression/generate-hints` | 生成答题提示 |
| POST | `/api/expression/answer/{id}/text` | 更新回答文本 |
| POST | `/api/expression/evaluate/{id}` | AI 评分 |
| GET | `/api/expression/stats` | 训练统计 |
| GET | `/api/expression/history` | 回答历史 |
| GET | `/api/expression/question/{id}` | 题目详情 |
| GET | `/api/expression/answer/{id}` | 回答详情 |

### 后端开发

- API 路由在 `backend/routers/` — 每个模块一个资源域（`health.py`、`users.py`、`habits.py` 等）
- 数据库操作在 `backend/db/` — 每个模块一个功能域（`users.py`、`habits.py`、`tasks.py` 等）
- AI 服务在 `backend/services/` — 四个 AI 服务场景独立封装
- AI 提示词在 `backend/prompts/` — 每个功能独立文件
- 等级公式唯一来源：`backend/models/level.py`
- 运行测试：`cd backend && pixi run pytest`

### 桌面应用打包

详细打包指南见 [`docs/打包与更新指南.md`](docs/打包与更新指南.md)。

**架构**：Electron 主进程启动 PyInstaller 打包的后端 exe → 轮询 `/api/health` 等待就绪 → 加载前端页面

| 产物 | 路径 | 大小 |
|------|------|------|
| 后端 exe | `backend/dist/self-grow-backend/` | ~56 MB |
| 绿色版目录 | `desktop/dist/SelfGrow/` | ~325 MB |
| 绿色版 zip | `desktop/dist/SelfGrow-v{版本}-portable.zip` | ~136 MB |

**按改动范围分步打包**：
- 仅前端 → 替换 `desktop/dist/SelfGrow/resources/frontend/` 后 `node make-portable.js`
- 仅后端 → 重新 `pixi run pyinstaller --clean --noconfirm self_grow_server.spec` 后替换
- 前后端都改 → `build.bat` 一键完成

**打包模式数据目录**：`%APPDATA%/SelfGrow/`（独立于安装目录，更新不丢失）

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

---

## v1.0 已知限制

参见 [`docs/1.0版本审查报告.md`](docs/1.0版本审查报告.md) 完整 23 条发现。主要未修复项：

- 作息规律连续天数持久化已修复（`routine_streak` 表替代内存缓存）
- 异步渲染函数缺少 `await` 可能引发竞态（**中优先级，待修复**）
- `int(dimension_exp)` 截断而非四舍五入（**中优先级，待修复**）
- 数据库连接未使用上下文管理器（**低优先级**）
- CORS 允许所有来源（**低优先级，本地开发无影响**）