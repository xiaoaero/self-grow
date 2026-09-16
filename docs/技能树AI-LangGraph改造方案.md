# 技能树 AI 辅助编辑改造方案

> 目标：1）将现有手写 LLM 调用迁移到 LangChain/LangGraph；2）系统修复当前 AI 编辑模块的问题。
>
> **方案生成时间**：2026-08-28
> **落地核实时间**：2026-09-04（对照 `backend/services/skill_tree_ai/`、`backend/routers/skill_tree_ai.py`、`frontend/skill-tree/js/ai-bridge.js`）

---

## 〇、落地进度总览

**Phase 1（后端 LangGraph 化）已全部完成，Phase 2 完成约七成，Phase 3/4 未启动。**

| 阶段 | 状态 | 说明 |
|------|------|------|
| Phase 1 后端 graph | ✅ **完成** | `services/skill_tree_ai/` 五个模块齐全，`routers/skill_tree_ai.py` 已注册到 `main.py` |
| Phase 2 前端对接 | 🟡 **部分完成** | 已对接 chat / resume / thread_id / 确认弹窗 / 取消按钮；**SSE 流式、Markdown 渲染、diff 应用未做** |
| Phase 3 前端遗留修复 | ❌ 未启动 | 撤销历史、重名处理等 |
| Phase 4 下线旧代码 | 🟡 半完成 | 旧 `/api/chat` 已加鉴权 + 标记 `deprecated=True` + `include_in_schema=False`，但代码未删 |

### 与方案的两处偏差

| 方案设计 | 实际实现 |
|---|---|
| 9 个工具 | **8 个**（`get_tree_state` 按方案移除，`send_message` 改造为 `send_reply`） |
| 前端通过 SSE 接收事件流 | ✅ **2026-09-16 已接入**：`/chat` 与 `/chat/resume` 本身改为 **POST + SSE**（原来的 `GET /{tree_id}/chat/stream` 是假占位，已删除），前端用共享的 `js/sse.js` 读取，阶段事件显示成「第 N 轮推理 / 正在执行哪个工具 / 需要确认」 |
| 返回「树 diff」由前端 `applyTreeDiff()` 应用 | 前端无 diff 应用逻辑（`diff` 关键字 0 命中），实际走整树覆盖 |

---

## 一、现状诊断：问题清单（含修复状态）

图例：✅ 已修复 · 🟡 部分完成 · ❌ 未实现 · ❓ 未核实

### 1.1 架构层问题

| 编号 | 问题 | 影响 | 位置 | 状态 |
|------|------|------|------|------|
| A1 | 后端 `ai_service.py` 用原始 `httpx` 调 `/chat/completions` | 与 LangGraph 栈不统一 | 旧 `services/ai_service.py` | ✅ 新链路已用 `ChatOpenAI` + `StateGraph`；旧文件保留未删 |
| A2 | 前端自己维护对话历史并驱动多轮 Tool Use | 前后端责任混杂，易出竞态 | `ai-bridge.js`（现 317 行） | ✅ 前端已不执行工具，只发消息 + 渲染 |
| A3 | 无 AI 会话状态持久化 | 刷新后对话丢失 | 全局 | ✅ 复用 coordinator 的 `MemorySaver`，按 `thread_id` 隔离（前端 6 处引用 thread_id） |
| A4 | 工具在前端执行，后端只透传 | 后端无法校验拦截 | 旧链路 | ✅ 8 个工具全部在后端 `@tool` 内执行（`tools.py` 648 行） |
| A5 | `/api/chat` 未鉴权 | 任何人可调用 | `routers/ai.py` | ✅ 旧接口已加 `get_current_user`；新接口 3 个端点全部鉴权 |

### 1.2 工具层问题

| 编号 | 问题 | 状态 | 实际情况 |
|------|------|------|---------|
| T1 | 所有工具按 `node.name` 匹配 | ✅ | 已 ID 化，`node_id` 出现 25 次；`update_node` / `delete_node` / `move_node` / `add_connection` 均改用 ID |
| T2 | `get_tree_state` 无实际作用 | ✅ | 已从工具集中移除 |
| T3 | `send_message` 无实际发送逻辑 | ✅ | 改造为 `send_reply(reply: str, state)`，作为 LLM 回复通道 |
| T4 | `replace_tree` 无前置确认 | ✅ | `replace_tree(..., confirm: bool = False)` |
| T5 | `delete_node` 无前置确认 | ✅ | `delete_node(node_id, confirm: bool = False, ...)` |
| T6 | `move_node` 未入撤销历史 | ❓ | 未核实（撤销栈在前端 `history.js`） |
| T7 | `create_node` 的 `saveHistory()` 位置过早 | 🟡 | 新链路无单个 `create_node`，改为 `create_nodes_batch`，历史交由前端 `applyTree` 时统一处理 |
| T8 | 工具参数未校验 | ❌ | **未实现**：`tools.py` 中 `raise ValueError` 0 次、"校验"仅 1 处。非法坐标 / 空名称 / 非法优先级目前无拦截 |
| T9 | 无批量操作工具 | ✅ | 已新增 `create_nodes_batch(nodes, connections, parent_id, state)` |

### 1.3 前端交互问题

| 编号 | 问题 | 状态 | 实际情况 |
|------|------|------|---------|
| F1 | 快捷按钮主题替换后句子不完整 | ❓ | 未核实 |
| F2 | 快捷按钮无主题输入框 | ❓ | 未核实 |
| F3 | AI 消息用 `textContent`，不支持 Markdown | ❌ | **未实现**：`ai-bridge.js` 中 markdown/Markdown/marked 均 0 命中 |
| F4 | 加载状态无进度提示 | ✅ | 2026-09-16 已完成：靠 SSE 阶段事件推送「第 N 轮推理 / 正在执行 xxx 工具」 |
| F5 | 无取消按钮 | ✅ | `cancel` 2 处 + `取消` 4 处 |
| F6 | 未处理重名节点 | ❌ | 未实现 |

### 1.4 提示词 / AI 行为问题

| 编号 | 问题 | 状态 | 实际情况 |
|------|------|------|---------|
| P1 | 提示词过短，缺 few-shot | ❓ | 未逐行核实 `prompts.py` |
| P2 | 未区分「生成整棵树」与「扩展子节点」 | ❓ | 未核实 |
| P3 | 未要求 AI 返回节点 ID | ✅ | 已 ID 化 |
| P4 | 未要求 AI 做布局规划 | ❓ | `tools.py` 中"坐标"出现 3 次，可能有部分约束 |
| P5 | `tree_state` 序列化整棵树，token 爆炸 | ❌ | **未实现**：`tools.py` 中摘要/截断相关关键字 0 命中 |

---

## 二、LangChain/LangGraph 迁移架构（已落地）

### 2.1 实际数据流

```
前端 (skill-tree)                     后端 (FastAPI)
AI 面板                               POST /api/skill-trees/{tree_id}/chat
  │ 发送 message + thread_id     ──►  POST /api/skill-trees/{tree_id}/chat/resume
  │                                   （旧的 GET .../chat/stream 假占位已删除；
  │                                     /chat 与 /chat/resume 本身即 POST + SSE）
  │                                          │
  │                                          ▼
  │                                   SkillTreeChatGraph (LangGraph StateGraph)
  │                                   - 校验用户权限 & 树归属
  │                                   - LLM 规划工具调用
  │                                   - 后端 @tool 执行（操作内存树）
  │                                   - send_reply 生成自然语言回复
  │                                          │
  │  ◄── 返回整棵树 + reply ─────────────────┘
  ▼
应用树变更 + 渲染消息
（持久化：MemorySaver checkpointer，按 thread_id）
```

### 2.2 关键设计决策（落地情况）

| 决策 | 状态 | 说明 |
|------|------|------|
| **后端持有树状态** | ✅ | 请求时前端传整棵树，后端在 graph state 中维护 |
| **工具在后端执行** | ✅ | 8 个 `@tool` 函数，用 `InjectedState` 注入树状态 |
| **节点使用 ID** | ✅ | 参数从 `name` 改为 `node_id` / `from_id` / `to_id` |
| **返回 diff 而非操作指令** | 🟡 | 后端确实返回树变更，但前端没有 `applyTreeDiff()`，按整树覆盖应用 |
| **SSE 流式事件** | ✅ | 2026-09-16 落地：后端 POST + SSE（阶段事件），前端 `js/sse.js` 接入 |
| **checkpointer 持久化** | ✅ | 复用 `services.coordinator.checkpointer.get_checkpointer()`（全局 MemorySaver） |
| **用户鉴权** | ✅ | 3 个端点全部 `Depends(get_current_user)` |

### 2.3 复用的基础设施（已生效）

```toml
# pixi.toml
langchain-openai = ">=1.3.5,<2"
langgraph      = ">=0.2.0"
langchain-core = ">=0.3.0"
```

`services/skill_tree_ai/graph.py` 实际复用了：

- `services.coordinator.llm.get_llm()` —— 统一 LLM 实例
- `services.coordinator.checkpointer.get_checkpointer()` —— 全局 MemorySaver

> 注意：**没有**复用 `coordinator/agents/base.py:build_subgraph()`，技能树单独实现了 `node.py:make_agent_node()`（192 行），因为它不需要反问机制（`interrupt` / `ask_user` / `needs_user` 在 `node.py` 中均为 0 命中）。

### 2.4 实际模块结构

```
backend/
├── services/
│   └── skill_tree_ai/
│       ├── __init__.py
│       ├── graph.py      # 125 行 — build_skill_tree_chat_graph / run / resume
│       ├── state.py      # SkillTreeChatState TypedDict
│       ├── tools.py      # 648 行 — 8 个 @tool（操作内存树）
│       ├── node.py       # 192 行 — make_agent_node，自研 ReAct 循环
│       └── prompts.py    # 系统提示词
├── routers/
│   └── skill_tree_ai.py  # 113 行 — 3 个端点（chat / resume / stream）
└── prompts/
    └── skill_tree.py     # 提示词导出
```

**8 个工具**：

| 工具 | 签名要点 |
|------|---------|
| `create_nodes_batch` | `nodes: list[dict], connections, parent_id` —— 一次生成整棵树 |
| `update_node` | `node_id: str, changes: dict` |
| `delete_node` | `node_id: str, confirm: bool = False` |
| `add_connection` | `from_id: str, to_id: str` |
| `delete_connection` | — |
| `move_node` | `node_id: str, x: int, y: int` |
| `replace_tree` | `nodes: list[dict], connections, confirm: bool = False` |
| `send_reply` | `reply: str` —— LLM 的文本回复通道 |

全部工具用 `Annotated[dict, InjectedState(...)]` 注入树状态，避免把树塞进 LLM 上下文。

---

## 三、剩余待办（按优先级）

### 3.1 高优先级

| # | 事项 | 对应问题 | 说明 |
|---|------|---------|------|
| 1 | **工具参数校验** | T8 | `tools.py` 内补坐标范围、名称非空、优先级枚举、progress 0~100 校验，非法值返回错误给 LLM 而非抛异常 |
| 2 | **树状态摘要/截断** | P5 | 大树只传「层级摘要 + 当前子树」，`tools.py` 与 `prompts.py` 两侧都要改 |
| 3 | **Markdown 渲染** | F3 | `ai-bridge.js` 接入轻量 Markdown 解析（代码块 / 列表 / 粗体） |

### 3.2 中优先级

| # | 事项 | 对应问题 |
|---|------|---------|
| 4 | ~~前端接入 SSE 流式~~ ✅ **已完成**（2026-09-16） | F4 |
| 5 | 前端 `applyTreeDiff()` 替代整树覆盖 | 2.2 偏差 |
| 6 | 重名节点自动处理 | F6 |
| 7 | `move_node` 入撤销历史 | T6 |
| 8 | 提示词补 few-shot + 布局约束 | P1 / P2 / P4 |

### 3.3 收尾

| # | 事项 | 对应问题 |
|---|------|---------|
| 9 | 删除 `routers/ai.py` 的 `/api/chat`（已 deprecated + 鉴权，确认无调用方后可删） | Phase 4 |
| 10 | 删除 `services/ai_service.py` 中仅服务旧链路的 `call_ai` | Phase 4 |
| 11 | 快捷按钮加主题输入框 | F1 / F2 |

---

## 四、风险评估（现状）

| 风险 | 等级 | 现状 |
|------|------|------|
| 旧链路与新链路行为不一致 | 低 | 旧 `/api/chat` 已 deprecated 且鉴权，前端已切新链路 |
| 工具参数无校验导致脏数据 | **中** | T8 未实现，当前主要风险点 |
| 大树 token 爆炸导致响应慢 | **中** | P5 未实现，节点多时明显 |
| 前端整树覆盖而非 diff 应用 | 低 | 功能正确，但大树上性能与撤销体验较差 |
| 会话状态占用内存 | 低 | MemorySaver 无淘汰策略，后续可换 SQLite/Redis checkpointer |

---

## 五、工作量回顾

| 阶段 | 原估算 | 实际状态 |
|------|--------|---------|
| Phase 1 后端 graph | 4-6h | ✅ 完成 |
| Phase 2 前端对接 | 3-4h | 🟢 约九成（SSE ✅；缺 Markdown / diff 应用） |
| Phase 3 前端修复 | 1-2h | ❌ 未启动 |
| Phase 4 下线旧代码 + 测试 | 1-2h | 🟡 旧接口已标记 deprecated，代码未删 |

**剩余工作量估算**：高优先级 3 项约 3-5h，中优先级 5 项约 5-8h，收尾 3 项约 1-2h。

---

*方案生成：2026-08-28 · 落地核实：2026-09-04*
