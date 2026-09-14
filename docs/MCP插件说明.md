# Self Grow MCP 插件说明

> 把 Self Grow 的业务工具通过 **MCP（Model Context Protocol）** 暴露，让任何支持 MCP 的客户端（Claude Desktop / Cursor / Cline / 自研 Agent）都能用自然语言管理个人成长数据。
>
> 最后核实：2026-09-04，对照 `backend/mcp_server.py`（651 行）

## 1. 这是什么

MCP ≈ **AI 应用的「USB-C 接口」**：把工具用统一协议暴露，一次编写、所有兼容客户端零适配接入。

本项目的两套 AI 能力一内一外，互补：

| | 协调 Agent | MCP Server |
|---|---|---|
| 位置 | `backend/services/coordinator/` | `backend/mcp_server.py` |
| 职责 | **内部**多智能体编排（主 Agent 路由 + 6 子 Agent 并行 + 反问） | **对外**工具暴露 |
| 适用 | 本项目自己的对话面板 | 任意第三方 MCP 客户端 |

## 2. 当前实现：24 个工具

`backend/mcp_server.py` 已覆盖全部业务域，**工具内部直接复用现有 `db/`、`services/` 业务层，没有重写任何业务逻辑**。

### 行动与统计（4）

| 工具 | 类型 | 说明 |
|------|------|------|
| `record_action` | 写 | 记录行动 + 自动结算经验（复用 `services/exp_service`） |
| `query_user_stats` | 读 | 查询等级/总经验/连续天数 |
| `query_dimension_stats` | 读 | 查询某维度等级与经验 |
| `query_action_history` | 读 | 查询历史行动记录 |

### 目标域（5）

| 工具 | 类型 | 说明 |
|------|------|------|
| `create_goal` | 写 | 创建目标及里程碑 |
| `list_goals` | 读 | 列出目标 |
| `update_goal` | 写 | 更新目标信息或里程碑进度 |
| `delete_goal` | 写 | 删除目标（含里程碑） |
| `claim_goal_reward` | 写 | 领取目标完成奖励 |

### 任务域（5）

| 工具 | 类型 | 说明 |
|------|------|------|
| `create_task` | 写 | 创建任务 |
| `list_tasks` | 读 | 列出今日/本周/全部任务 |
| `update_task` | 写 | 更新任务信息或状态 |
| `delete_task` | 写 | 删除任务 |
| `claim_task_reward` | 写 | 领取任务完成奖励 |

### 习惯域（5）

| 工具 | 类型 | 说明 |
|------|------|------|
| `create_habit` | 写 | 创建习惯 |
| `list_habits` | 读 | 列出习惯 |
| `update_habit` | 写 | 更新习惯信息 |
| `delete_habit` | 写 | 删除习惯（含打卡记录） |
| `checkin_habit` | 写 | 习惯打卡 |

### 奖励域（5）

| 工具 | 类型 | 说明 |
|------|------|------|
| `create_reward` | 写 | 创建奖励 |
| `list_rewards` | 读 | 列出奖励及解锁状态 |
| `update_reward` | 写 | 更新奖励信息 |
| `delete_reward` | 写 | 删除奖励 |
| `claim_reward` | 写 | 领取奖励（后端校验解锁条件） |

### 参数约束

枚举参数全部用 `typing.Literal` 声明，FastMCP 会自动生成带 `enum` 的 JSON Schema，**从协议层限制大模型传入非法值**：

```python
CategoryId   = Literal["health", "study", "relation", "work", "create", "finance", "hobby", "soul"]
SubType      = Literal["health-sport", "health-sleep", "relation-offline", ..., "finance-review"]
Priority     = Literal["low", "mid", "high"]
TaskStatus   = Literal["todo", "doing", "done"]
TaskSourceType      = Literal["today", "weekly", "all"]
TaskCreateSourceType = Literal["today", "weekly"]
CheckinStatus = Literal["done", "skipped"]
```

## 3. 安装与运行

```bash
cd backend

# 安装依赖（fastmcp 是 MCP Python SDK v2 的高级封装，在 [pypi-dependencies] 段）
pixi install

# 运行（默认 stdio 传输，供本地客户端 spawn）
pixi run mcp
```

> `pixi.toml` 已内置 `mcp = "python mcp_server.py"` 任务。
> 若 pixi 装 PyPI 依赖不便，也可直接用带 pip 的 Python 环境：`pip install "fastmcp>=2.0"`，然后 `python mcp_server.py`（需保证 db/services 依赖的 fastapi、httpx 等已装）。

### 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `SELF_GROW_USER_ID` | `1` | **stdio 模式**下操作哪个用户（本地进程可信） |
| `MCP_TRANSPORT` | `stdio` | 传输方式，设为 `streamable-http` 切远程模式 |
| `MCP_HOST` | `0.0.0.0` | HTTP 模式监听地址 |
| `MCP_PORT` | `8000` | HTTP 模式监听端口 |
| `SELF_GROW_TRUSTED_MODE` | `0` | 设为 `1` 可关闭 HTTP 模式的鉴权（**仅供本地开发**） |

### 两种传输的鉴权差异（2026-09-13 新增）

| 传输 | 是否需要凭证 | 身份来自 |
|------|------------|---------|
| **stdio**（默认） | ❌ 不需要 | `SELF_GROW_USER_ID` 环境变量 |
| **HTTP / streamable-http** | ✅ **必须** `X-API-Key` | API Key 解析出的用户（写入请求级 ContextVar） |

理由：**stdio 是用户自己 spawn 的子进程，进程边界即信任边界**，加 Key 只会让配置变麻烦——这也是 MCP 生态的通行做法。
但**一旦监听端口，任何能访问该端口的人都能调用 24 个业务工具读写数据库**，必须鉴权。

HTTP 模式用法：

1. 在「用户中心 → 账户安全 → API Key」生成一个 `sgk_...` 密钥（明文仅显示一次）
2. 客户端请求时带上：`X-API-Key: sgk_...`（也支持 `Authorization: Bearer sgk_...`）
3. 未带 / 无效 / 已撤销 → 返回 `401` + `WWW-Authenticate: Bearer`

```bash
curl -X POST http://localhost:8000/mcp \
  -H "X-API-Key: sgk_xxx" -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
```

> 实现见 `mcp_server.py` 底部的 `ApiKeyMiddleware`（Starlette `BaseHTTPMiddleware`），
> 校验复用 REST API 的 `auth_service.resolve_api_key()` —— 同一张 `api_keys` 表，
> 可在用户中心统一撤销。鉴权通过后用户 ID 写入 `_mcp_user_id` ContextVar，
> 24 个工具内部调用的 `current_user_id()` 会读到它，因此**身份随 Key 走，不再是固定值**。

## 4. 挂载到 Claude Desktop

编辑 `claude_desktop_config.json`（Claude Desktop → Settings → Developer → Edit Config）：

```json
{
  "mcpServers": {
    "self-grow": {
      "command": "python",
      "args": ["D:/pycharm/projec/self_grow_system/backend/mcp_server.py"],
      "env": { "SELF_GROW_USER_ID": "1" }
    }
  }
}
```

重启 Claude Desktop 后，就能对它说：「帮我记录跑步 30 分钟」「我现在的等级是多少」「把明天的任务列出来」等。

> `SELF_GROW_USER_ID` 指定操作哪个用户（默认 1 = test 用户）。

## 5. 验证

- 客户端里看到 `self-grow` 服务器 + **24 个工具** = 挂载成功。
- 让它「记录跑步 30 分钟」→ 打开系统行动历史，能看到一条新记录且 EXP 正确。
- 让它「查我的等级」→ 返回等级和总经验。

## 6. 远程部署（已支持）

stdio 仅限本地。设置环境变量即可切换为 **Streamable HTTP**（MCP 新规范），部署成远程 MCP 服务供多端接入：

```bash
MCP_TRANSPORT=streamable-http MCP_PORT=8000 python mcp_server.py
```

客户端连接地址：`http://host:port/mcp`

## 7. 待办与已知限制

### 7.1 Agent 级暴露（未实现）

当前暴露的是**工具**。若要把整个 coordinator（多智能体编排 + 反问机制）也暴露成一个 MCP 工具，让外部客户端获得"多智能体编排"能力，尚未实现。

### 7.2 三个需要提前想清楚的点

1. **用户身份**：MCP 是工具协议，没有内置用户概念。
   - **stdio 模式**：`SELF_GROW_USER_ID` 环境变量固定 `user_id`（单用户，符合本地进程可信的前提）
   - **HTTP 模式**（2026-09-13 已解决）：由 `X-API-Key` 解析出真实用户，写入请求级 ContextVar，
     24 个工具通过 `current_user_id()` 读取 → **多用户已支持，且可在用户中心随时撤销 Key**
   > 注意：主站的协调 Agent 已有完整鉴权（见 [统一协调Agent设计方案](./统一协调Agent设计方案.md) §6.1）。
2. **反问**：MCP 的 tool 是「请求→响应」，不适合中途挂起反问。两种做法：
   - 工具返回 `needs_user` 标记 + 客户端再调 `resume` 工具（复刻 coordinator 现有机制）；
   - 直接返回「缺参数」错误，让客户端 LLM 看工具 schema 自行追问补齐（更简单）。
3. **安全**：写库操作暴露后，任何连上来的客户端都能调。建议加写操作确认、限制可写范围。

## 8. 参考

- MCP Python SDK v2.0.0：https://github.com/modelcontextprotocol/python-sdk/releases/tag/v2.0.0
- FastMCP 文档：https://gofastmcp.com
- SDK v1→v2 迁移指南：https://raw.githubusercontent.com/modelcontextprotocol/python-sdk/main/docs/migration.md
