# Self Grow · 个人成长系统

> 一个把「记录 → 结算 → 反馈」做成游戏的个人成长追踪系统。
> 原生 HTML/CSS/JS 单页应用 + FastAPI 后端，八维属性 / 等级段位 / 习惯任务 / 奖励商城 / 可视化技能树，
> 内置两套 LangGraph Agent（统一协调 Agent + 技能树 AI）与 MCP 插件。

在线体验：<https://xiaoaero.com>

---

## 目录

- [核心功能](#核心功能)
- [技术栈](#技术栈)
- [快速启动](#快速启动)
- [项目结构](#项目结构)
- [架构要点](#架构要点)
- [文档](#文档)

---

## 核心功能

| 模块 | 说明 |
|---|---|
| **仪表盘** | 连续打卡天数、等级 EXP 进度条、今日概览、待打卡习惯、近期动态 |
| **行动** | 计时器 + 8 分类行动记录、维度进度、CSV 导出、**AI 对话式记录** |
| **成长记录** | 年度热力图、八维雷达图、30 天 EXP 趋势 |
| **属性** | 8 个维度各自的等级与 EXP 进度 |
| **目标 / 任务** | 目标里程碑与 EXP 奖励；本日 / 本周 / 历史任务三栏看板、定时任务模板 |
| **习惯** | 7 天周视图三态打卡、统计卡片、**AI 智能洞察** |
| **技能树** | 独立 SPA 可视化编辑器（拖拽 / 连线 / 撤销重做），**AI 按节点 ID 自动编辑** |
| **奖励商城** | 8 分类筛选、解锁条件 + 领取条件双重校验、图片上传 |
| **表达训练** | **AI 出题 + 实时语音识别 + 四维评分 + 填充词实时高亮** |
| **AI 资讯** | GitHub 趋势 + 国内/国际资讯抓取，**每日 AI 情报摘要**与三个榜单 |
| **用户中心** | 账户安全（改密 / API Key）+ **多模型配置，切换即时生效** |
| **AI 悬浮球** | 自然语言直达协调 Agent，缺信息时**反问澄清** |

规模：**29 张表** · **101 个 HTTP 端点** · **7 个 AI 场景** · **24 个 MCP 工具** · 8 个 SSE 流式端点 ·
后端 17.5k 行 + 测试 6.1k 行（295 passed）· 前端 19k 行 JS。

---

## 技术栈

| 层级 | 技术 |
|---|---|
| 前端 | 原生 HTML/CSS/JS，零框架；Chart.js 4.4 |
| 后端 | Python 3.12 + FastAPI + httpx |
| 数据库 | MySQL 8.0（PyMySQL + DBUtils 连接池） |
| 鉴权 | PyJWT 双令牌（Access 2h / Refresh 30d 轮换）+ bcrypt + API Key |
| AI 编排 | LangGraph（协调 Agent 多智能体图 + 技能树 AI 工具调用图） |
| MCP | FastMCP（stdio 免鉴权 / HTTP 强制 `X-API-Key`） |
| 语音 | DashScope paraformer 实时转写 |
| 定时任务 | APScheduler |
| 环境 | pixi（依赖唯一事实源） |
| 部署 | Docker Compose（app / mcp / mysql + 可选 nginx + HTTPS） |

---

## 快速启动

> ⚠️ 请用 HTTP 服务器访问，不要直接双击 HTML（`file://` 下浏览器禁止跨域请求）。

### 方式一：Docker（推荐）

```bash
cp .env.example .env
# 必填：SELF_GROW_JWT_SECRET=$(openssl rand -hex 32)
# 并修改 .env 里的 MySQL 口令（模板是占位值）

docker compose up -d
docker compose exec app python tools/init_password.py
```

访问 `http://服务器IP:3001`。详细方案见 [docs/Docker技术详解与部署实战.md](docs/Docker技术详解与部署实战.md)。

### 方式二：本地开发（pixi）

```bash
cd backend
pixi install
pixi run init-password        # 初始化账号，默认 test / admin
pixi run start                # http://localhost:3001
```

必需环境变量：

```bash
SELF_GROW_JWT_SECRET=...                  # 缺失拒绝启动
SELF_GROW_MYSQL_HOST/PORT/USER/PASSWORD/DATABASE
SELF_GROW_FRONTEND_DIR=.../frontend       # 让后端同源提供前端
AI_API_BASE_URL / AI_API_KEY / AI_MODEL   # .env 只是兜底，运行时优先读 model_configs 表
```

默认账号：`test / test123456`（普通用户）、`admin / admin123456`（管理员，含技能树编辑）。

前端也可独立起服务（改代码免重启后端），CORS 默认放行 localhost 任意端口：

```bash
npx http-server -p 3000 -c-1     # 打开 http://localhost:3000
```

### MCP 插件（可选）

```bash
cd backend
pixi run mcp                                                  # stdio，本地客户端免鉴权
MCP_TRANSPORT=streamable-http MCP_PORT=8000 pixi run mcp     # HTTP，需 X-API-Key
```

详见 [docs/MCP插件说明.md](docs/MCP插件说明.md)。

### 测试

```bash
# 后端（库名必须含 test，否则测试库重置被安全闸拦住）
cd backend && SELF_GROW_MYSQL_DATABASE=self_grow_test pytest tests/ -q
# 前端逻辑测试（零依赖，不开浏览器）
node frontend/tests/*.test.mjs
```

---

## 项目结构

```
self_grow_system/
├── frontend/                # SPA（无框架）
│   ├── index.html           # 主入口
│   ├── js/                  # auth / data / router / utils / sse / chat / app + pages/
│   ├── css/                 # variables / layout / sidebar / components / pages
│   ├── skill-tree/          # 技能树编辑器（独立 SPA）
│   ├── tests/               # Node 逻辑回归测试
│   └── assets/icons/        # 属性图标 SVG
├── backend/
│   ├── main.py              # app 工厂 / 生命周期 / 路由注册 / 定时任务
│   ├── config.py            # 配置与日志初始化
│   ├── mcp_server.py        # MCP 服务（24 个业务工具）
│   ├── models/              # 等级公式（唯一来源）、8 维常量
│   ├── schemas/             # Pydantic 请求模型
│   ├── db/                  # MySQL 连接池 + 各功能域 SQL
│   ├── services/            # 业务逻辑（含 coordinator/ 与 skill_tree_ai/ 两套 LangGraph）
│   ├── prompts/             # 各场景系统提示词
│   ├── routers/             # API 路由（按资源域拆分）
│   ├── tests/               # pytest（含 SQL 方言静态护栏）
│   └── pixi.toml            # 依赖唯一事实源
├── docs/                    # 项目文档 12 篇
├── memory/                  # 开发记录（按日期）
├── docker-compose.yml / Dockerfile / .env.example
└── CLAUDE.md                # 给 AI 编程工具的代码指引
```

---

## 架构要点

**两套 LangGraph Agent**
- **统一协调 Agent**：主图 LLM 路由 → 6 个子 Agent（行动 / 查询 / 目标 / 任务 / 习惯 / 奖励）→ 需要澄清时用 `ask_user` 反问 → 汇总回复。前端以全局悬浮球呈现，SSE 流式输出。
- **技能树 AI**：单 Agent 工具调用图，8 个工具按节点 ID 增删改节点与连线，危险操作弹确认卡片。

**经验系统**：全局总经验 = 8 维经验之和，等级公式 `expForLevel(L) = round(5.5632 × (L-1)² + 300)`，上限 200 级、10 个段位。结算走「先占位 `exp_earned=0`、结算后回写」的幂等流程，防重复发放。

**登录鉴权**：三类客户端三条凭证通道（JWT Bearer / API Key / 本地可信模式），解析集中在 `routers/deps.py`。前端 `auth.js` 包装 `window.fetch` 自动带凭证并处理 401 续期。技能树编辑器三道防线：入口不渲染 → 启动查 `/api/auth/me` → 后端 `require_admin`。

**SSE 流式**：`fetch` + `getReader` 自实现（原生 `EventSource` 不能带自定义请求头，必然 401）。统一实现于 `services/sse.py`，事件四类：`stage` / `token` / `error` / `done`。Nginx 部署需关 `proxy_buffering`。

**数据库**：MySQL 单后端，源码即 MySQL 原生 SQL。`tests/test_sql_dialect_lint.py` 作为静态护栏，拦 SQLite 写法回退、派生表缺别名、保留字未加反引号、手搓 `IN` 占位符。

---

## 文档

**项目设计类**
- [登录鉴权方案选型](docs/登录鉴权方案选型.md) — 9 种登录方式对比 + JWT 落地方案
- [维度经验计分规则](docs/维度经验计分规则.md) — 8 维经验计算规则与等级公式推导
- [MCP 插件说明](docs/MCP插件说明.md) — 安装 / 挂载 / 验证 / 鉴权
- [Docker 技术详解与部署实战](docs/Docker技术详解与部署实战.md) — 原理讲解 + 生产部署（含 Nginx / HTTPS / 备份）

**技术学习类**
[LangGraph](docs/LangGraph学习指南.md) · [FastAPI 与 FastMCP](docs/FastAPI与FastMCP学习指南.md) ·
[异步编程](docs/异步编程学习指南.md) · [性能优化](docs/性能优化学习指南.md) ·
[数据库](docs/数据库知识深入学习指南.md) · [网络](docs/网络知识深入学习指南.md) ·
[设计模式](docs/设计模式学习指南.md) · [浏览器缓存与存储](docs/前端浏览器缓存与存储详解.md)

---

## 已知限制

- LangGraph checkpointer 为内存实现，后端重启会话丢失（技能树对话已改为前端按树持久化）；调度器多实例部署会重复执行。
- 技能树 AI 未做资源级隔离，所有管理员可编辑全部技能树。

## License

仅供学习与交流使用。