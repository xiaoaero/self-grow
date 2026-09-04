# Self Grow MCP 插件说明

> 把 Self Grow 的业务工具通过 **MCP（Model Context Protocol）** 暴露，让任何支持 MCP 的客户端（Claude Desktop / Cursor / Cline / 自研 Agent）都能用自然语言管理个人成长数据。

## 1. 这是什么

MCP ≈ **AI 应用的「USB-C 接口」**：把工具用统一协议暴露，一次编写、所有兼容客户端零适配接入。

本项目的协调 Agent（`backend/services/coordinator/`）负责**内部工具编排**（主 Agent 路由 + 6 个子 Agent 并行 + 反问），而 MCP Server 负责**对外工具暴露**——两者一内一外，互补。

## 2. 当前实现

`backend/mcp_server.py` 是最小骨架，先注册了 3 个代表性工具：

| 工具 | 类型 | 说明 |
|------|------|------|
| `record_action` | 写 | 记录行动 + 自动结算经验（复用 `services/exp_service`） |
| `query_user_stats` | 读 | 查询等级/总经验/连续天数（复用 `db/users`） |
| `query_dimension_stats` | 读 | 查询某维度等级与经验（复用 `db/dimensions`） |

**关键点**：工具内部直接复用现有 `db/`、`services/` 业务层，**没有重写任何业务逻辑**。

## 3. 安装与运行

```bash
cd backend

# 安装依赖（fastmcp 是 MCP Python SDK v2 的高级封装）
pixi install            # 读取 pixi.toml 的 [pypi-dependencies]

# 运行（stdio 传输，供本地客户端 spawn）
pixi run mcp
```

> 若 pixi 装 PyPI 依赖不便，也可直接用带 pip 的 Python 环境：`pip install "fastmcp>=2.0"`，然后 `python mcp_server.py`（需保证 db/services 依赖的 fastapi、httpx 等已装）。

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

重启 Claude Desktop 后，就能对它说：「帮我记录跑步 30 分钟」「我现在的等级是多少」等。

> `SELF_GROW_USER_ID` 环境变量指定操作哪个用户（默认 1 = test 用户）。

## 5. 验证

- Claude Desktop 里看到 `self-grow` 服务器 + 3 个工具 = 挂载成功。
- 让它「记录跑步 30 分钟」→ 打开系统行动历史，能看到一条新记录且 EXP 正确。
- 让它「查我的等级」→ 返回等级和总经验。

## 6. 后续扩展

### 6.1 补全全部 25 个工具（工具级暴露）

把 `backend/services/coordinator/agents/` 下 6 个域的工具逐个用 `@mcp.tool()` 包一层：
action / query / goal / task / habit / reward 共 25 个工具 + 经验计算。

### 6.2 Agent 级暴露（进阶）

把整个 coordinator（多智能体编排 + 反问机制）暴露成一个 MCP 工具，让外部客户端获得「多智能体编排」能力。

### 6.3 远程部署

stdio 仅限本地；换成 **Streamable HTTP** 传输后，可部署成远程 MCP 服务，供多端接入。

## 7. 三个需要提前想清楚的点

1. **用户身份**：MCP 是工具协议，没有内置用户概念。当前用单用户模式（固定 `user_id`）；多用户需接入 MCP 的 `context` / session 机制传 user_id。
2. **反问**：MCP 的 tool 是「请求→响应」，不适合中途挂起反问。两种做法：
   - 工具返回 `needs_user` 标记 + 客户端再调 `resume` 工具（复刻 coordinator 现有机制）；
   - 直接返回「缺参数」错误，让客户端 LLM 看工具 schema 自行追问补齐（更简单）。
3. **安全**：写库操作暴露后，任何连上来的客户端都能调。建议加写操作确认、限制可写范围。

## 8. 参考

- MCP Python SDK v2.0.0：https://github.com/modelcontextprotocol/python-sdk/releases/tag/v2.0.0
- FastMCP 文档：https://gofastmcp.com
- SDK v1→v2 迁移指南：https://raw.githubusercontent.com/modelcontextprotocol/python-sdk/main/docs/migration.md
