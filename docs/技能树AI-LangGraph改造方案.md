# 技能树 AI 辅助编辑改造方案

> 目标：1）将现有手写 LLM 调用迁移到 LangChain/LangGraph；2）系统修复当前 AI 编辑模块的问题。

---

## 一、现状诊断：问题清单

### 1.1 架构层问题

| 编号 | 问题 | 影响 | 位置 |
|------|------|------|------|
| A1 | 后端 `ai_service.py` 使用原始 `httpx` 调用 `/chat/completions`，与项目已有的 LangChain/LangGraph 栈不统一 | 重复实现、缺少 LangGraph 的 checkpoint / 流式 / 工具循环能力 | `backend/services/ai_service.py` |
| A2 | 前端自己维护对话历史并驱动多轮 Tool Use 循环 | 前后端责任混杂；前端逻辑重，易出竞态/无限循环 | `frontend/skill-tree/js/ai-bridge.js:74-136` |
| A3 | 没有持久化 AI 会话状态 | 刷新页面后对话丢失，无法 resume | 全局 |
| A4 | 工具执行在前端完成，后端只做「透传」 | 后端无法校验、拦截危险操作；网络中断时操作状态不一致 | `backend/routers/ai.py`, `frontend/skill-tree/js/ai-bridge.js` |
| A5 | AI 调用没有用户身份隔离 | `/api/chat` 目前未鉴权（router 里没有 `Depends(get_current_user)`），任何人可调用 | `backend/routers/ai.py:13` |

### 1.2 工具层问题

| 编号 | 问题 | 影响 | 位置 |
|------|------|------|------|
| T1 | 所有工具按 `node.name` 匹配 | 同名节点时操作错对象；改名后 AI 上下文失效 | `ai-bridge.js:188-300` |
| T2 | `get_tree_state` 工具无实际作用 | 浪费 LLM token，AI 可能误调用 | `prompts/skill_tree.py:11-19`, `ai-bridge.js:182-185` |
| T3 | `send_message` 工具在前端无实际发送逻辑 | 系统提示词要求「每次操作后发消息」，但 `send_message` 只是返回占位文本 | `ai-bridge.js:312-315` |
| T4 | `replace_tree` 没有前置确认/预览 | AI 一句话可清空整棵树，风险高 | `ai-bridge.js:304-310` |
| T5 | `delete_node` 没有前置确认 | 可能误删重要节点 | `ai-bridge.js:242-255` |
| T6 | `move_node` 未入撤销历史栈 | 用户无法撤销 AI 移动 | `ai-bridge.js:288-302` |
| T7 | `create_node` 中 `saveHistory()` 调用位置过早 | 父节点查找失败后仍多一次无用历史 | `ai-bridge.js:188` |
| T8 | 工具参数未校验 | AI 可能传非法坐标、空名称、非法优先级，直接报错或产生脏数据 | `ai-bridge.js` 各 case |
| T9 | 没有批量操作工具 | AI 一次生成多个节点时前端需多次 `create_node`，增加请求/渲染开销 | `prompts/skill_tree.py` |

### 1.3 前端交互问题

| 编号 | 问题 | 影响 | 位置 |
|------|------|------|------|
| F1 | 快捷按钮 `"主题名"` 替换后句子不完整 | AI 收到 `请为生成一个完整的知识树...`，生成质量下降 | `ai-bridge.js:38` |
| F2 | 快捷按钮没有主题输入框 | 用户无法直接输入主题，只能先点按钮再改文案 | `index.html:166-168` |
| F3 | AI 面板消息使用 `textContent`，不支持 Markdown/代码块 | 长描述、列表、代码难以阅读 | `ai-bridge.js:335-340` |
| F4 | 加载状态只有旋转点，无进度/步骤提示 | 多轮 Tool Use 时用户不知道 AI 在做什么 | `ai-bridge.js:343-355` |
| F5 | 无取消按钮 | 长生成时无法中断 | `ai-bridge.js:80`（只有 abortController，无 UI 按钮） |
| F6 | 未处理 AI 返回的重名节点 | 创建同名节点后只标红，未主动改名 | `app.js:375-391` |

### 1.4 提示词/AI 行为问题

| 编号 | 问题 | 影响 | 位置 |
|------|------|------|------|
| P1 | 系统提示词过短，缺少 few-shot | AI 对工具参数、布局规则理解不稳定 | `prompts/skill_tree.py:175-195` |
| P2 | 没有区分「生成整棵树」和「扩展子节点」的专用提示 | 扩展节点时 AI 可能误生成根节点或层级混乱 | `ai-bridge.js:362-365` |
| P3 | 没有要求 AI 返回节点 ID | 前后端只能依赖 name 匹配 | `prompts/skill_tree.py` |
| P4 | 没有要求 AI 做布局规划 | 大节点生成后全部堆叠，需靠前端 `autoLayout` 补救 | `app.js:767-806` |
| P5 | `tree_state` 序列化整棵树，长树超出上下文 | 节点多时 token 爆炸、响应变慢 | `ai-bridge.js:141-162` |

---

## 二、LangChain/LangGraph 迁移架构

### 2.1 迁移后整体数据流

```
┌─────────────────────────────────────────────────────────────────┐
│                         前端 (skill-tree)                        │
│  AI 面板 ──► 发送 user_message + thread_id ──► 接收事件流       │
│     ▲                                          │                │
│     └──────── 渲染 tool-executed / reply ──────┘                │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                         后端 (FastAPI)                           │
│  /api/skill-trees/{tree_id}/chat                                │
│  /api/skill-trees/{tree_id}/chat/stream  (SSE)                  │
│        │                                                        │
│        ▼                                                        │
│  ┌─────────────────────────────────────┐                        │
│  │  SkillTreeChatGraph (LangGraph)     │                        │
│  │  - 校验用户权限 & tree_id 存在性    │                        │
│  │  - 构建当前树状态（摘要/截断）      │                        │
│  │  - LLM 规划工具调用                 │                        │
│  │  - 后端本地执行工具（操作内存树）   │                        │
│  │  - 生成自然语言回复                 │                        │
│  └─────────────────────────────────────┘                        │
│        │                                                        │
│        ▼                                                        │
│  MemorySaver checkpointer（按 thread_id 持久化对话）             │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 关键设计决策

| 决策 | 说明 |
|------|------|
| **后端持有树状态** | 请求时前端把整棵树 `nodes/connections` 传给后端，后端在 graph state 中维护；AI 工具只操作后端内存状态，最后一次性返回「树 diff + 自然语言」 |
| **工具在后端执行** | 所有 `create_node`/`update_node`/`replace_tree` 等改为后端 `@tool` 函数，执行结果写入 graph state |
| **节点使用 ID** | 工具参数从 `name` 改为 `node_id`（UUID），彻底摆脱同名歧义 |
| **返回 diff 而非操作指令** | 后端不返回 `tool_calls` 让前端执行，而是返回 `{tree_diff, reply, executed_tools}`，前端一次性应用 |
| **SSE 流式事件** | Tool planning → tool execution → reply 每个阶段都通过 SSE 事件推送到前端，提升等待体验 |
| **checkpointer 持久化** | 使用 `MemorySaver`，30min TTL；支持刷新后继续对话 |
| **用户鉴权** | 新路由挂 `Depends(get_current_user)`，校验 `user_id` 与树的归属 |

### 2.3 复用现有基础设施

项目 `pixi.toml` 已经包含：

```toml
langchain-openai = ">=1.3.5,<2"
langgraph      = ">=0.2.0"
langchain-core = ">=0.3.0"
```

可直接复用：
- `services.coordinator.llm.get_llm()`：统一 LLM 实例
- `services.coordinator.checkpointer.get_checkpointer()`：全局 MemorySaver
- `services.coordinator.agents.base.build_subgraph()`：子图构建模式

### 2.4 新模块规划

```
backend/
├── services/
│   └── skill_tree_ai/
│       ├── __init__.py
│       ├── graph.py          # SkillTreeChatGraph 编译
│       ├── state.py          # SkillTreeChatState TypedDict
│       ├── tools.py          # 9 个 @tool 函数（操作内存树）
│       ├── node.py           # LangGraph 节点（agent / summarize）
│       └── prompts.py        # 系统提示词 + few-shot
├── routers/
│   └── skill_tree_ai.py      # /api/skill-trees/{tree_id}/chat (SSE)
└── prompts/
    └── skill_tree.py         # 现有提示词文件，改造后仍从这里导出
```

---

## 三、修复方案与预期效果

### 3.1 架构改造

| 修复项 | 具体做法 | 预期效果 |
|--------|----------|----------|
| 后端 LangGraph 化 | 新建 `services/skill_tree_ai/graph.py`，用 `StateGraph` 构建单 agent 循环 | 复用项目现有 LangGraph 能力；支持 checkpoint、流式、自然多轮 |
| 路由鉴权 | 新路由挂 `Depends(get_current_user)`，校验树归属 | 防止未授权调用；用户数据隔离 |
| 前端解耦 | `AIBridge` 只负责：发消息、收 SSE、渲染消息、应用 diff | 前端代码减少约 40%，逻辑清晰 |
| 状态持久化 | 后端 checkpointer 按 `thread_id` 保存对话 | 刷新页面后可 resume；支持中断恢复 |
| 后端执行工具 | 所有树操作在后端 `@tool` 完成，不暴露给前端 | 可统一校验、拦截、撤销 |

### 3.2 工具层改造

| 修复项 | 具体做法 | 预期效果 |
|--------|----------|----------|
| ID 化 | 工具参数 `name` → `node_id`；`create_node` 返回新 ID | 消除同名歧义；改名后仍可操作 |
| 删除无用工具 | 移除 `get_tree_state`、`send_message` | 减少 token 浪费和误调用 |
| 增加批量工具 | 新增 `create_nodes_batch` | AI 一次生成整棵树只需一次调用 |
| 危险操作确认 | `replace_tree` / `delete_node` 工具内部先标记 `needs_confirmation`，LLM 生成确认问题；用户确认后再执行 | 避免误删/误清空 |
| 撤销历史 | 后端每次修改前 push snapshot；工具执行后返回 `undoable: true` | AI 操作可撤销 |
| 参数校验 | `@tool` 函数内校验坐标、名称非空、优先级枚举、progress 范围 | 非法参数直接返回错误给 LLM，不产生脏数据 |
| 布局规划 | `replace_tree`/`create_nodes_batch` 要求 AI 同时返回建议坐标，后端再微调 | 减少节点堆叠，前端 `autoLayout` 只做兜底 |

### 3.3 前端交互改造

| 修复项 | 具体做法 | 预期效果 |
|--------|----------|----------|
| 快捷按钮占位符 | 点击「生成知识树」弹出输入框让用户填主题；扩展子节点自动用选中节点 | 句子完整、主题明确 |
| Markdown 渲染 | AI 消息使用轻量 Markdown 解析（代码块/列表/粗体） | 长描述可读性提升 |
| 流式事件展示 | SSE 每阶段推送 `{"type":"thinking"/"tool"/"diff"/"reply"}` | 用户知道 AI 当前在做什么 |
| 取消按钮 | 发送后显示「取消」按钮，调用 `abortController.abort()` | 长生成可中断 |
| 重名自动处理 | 后端 `create_node` 检测到重名时自动追加序号，或返回错误让 AI 重试 | 不再出现红色重复光圈 |
| 操作确认弹窗 | 前端收到 `needs_confirmation` 事件时弹出确认框 | 危险操作二次确认 |

### 3.4 提示词优化

| 修复项 | 具体做法 | 预期效果 |
|--------|----------|----------|
| 增加 few-shot | 在 `SKILL_TREE_SYSTEM_PROMPT` 中加入 2-3 个生成/扩展示例 | AI 输出更稳定 |
| 状态截断 | 大树只传「层级摘要 + 当前选中节点附近子树」，不传全部 description | 控制 token，提升速度 |
| 布局约束 | 明确要求 AI 返回 `x/y` 坐标，遵循「父节点在左、子节点在右」 | 生成布局更合理 |
| 输出格式约束 | 要求 AI 在生成回复时同时说明操作列表 | 用户明确知道 AI 做了什么 |

---

## 四、改造阶段（建议执行顺序）

### Phase 1：后端新 graph 搭建（无侵入）

1. 新建 `backend/services/skill_tree_ai/` 模块。
2. 定义 `SkillTreeChatState`（含 `tree: dict`、`messages`、`diffs`、`reply`）。
3. 实现 9 个 `@tool` 函数，操作内存树。
4. 实现 `build_skill_tree_chat_graph()`，使用 `MemorySaver`。
5. 新增 `backend/routers/skill_tree_ai.py`，提供 `POST /api/skill-trees/{tree_id}/chat` 和 `/chat/stream`。
6. 在 `main.py` 注册新路由。

**本阶段不删旧代码**，只并行新增。

### Phase 2：前端对接新 API

1. 改造 `AIBridge`：
   - 删除 `executeToolCalls` 中的具体操作逻辑。
   - 改为 SSE 客户端，接收 `diff`/`reply`/`confirmation` 事件。
   - 新增 `applyTreeDiff()` 统一应用后端返回的树变更。
2. 改造快捷按钮：增加主题输入框。
3. AI 消息支持 Markdown 渲染。
4. 增加取消按钮和操作确认弹窗。

### Phase 3：修复前端遗留问题

1. `move_node` 入撤销历史。
2. `create_node` 调整 `saveHistory()` 位置。
3. 重名节点自动处理。

### Phase 4：下线旧代码

1. 删除 `backend/services/ai_service.py` 中的 `call_ai`（或仅保留给可能的其他调用方检查）。
2. 删除 `backend/routers/ai.py` 中的 `/api/chat`。
3. 前端删除旧 `executeToolCalls` 死代码。
4. 运行 `pixi run test` 回归测试。

---

## 五、风险评估

| 风险 | 等级 | 缓解措施 |
|------|------|----------|
| LangGraph 与当前 `ai_service.py` 行为不一致 | 中 | Phase 1/2 并行运行，灰度切流；保留旧接口一段时间 |
| 前端 `AIBridge` 重构引入新 bug | 中 | 小步提交，每步验证基础生成/扩展/删除 |
| SSE 在前端某些环境不稳定 | 低 | 同时保留非流式 fallback endpoint |
| AI 仍可能生成非法坐标/重名 | 低 | 后端 `@tool` 内强制校验和自动修正 |
| 会话状态占用内存 | 低 | `MemorySaver` 已有 TTL；后续可换 SQLite/Redis checkpointer |

---

## 六、工作量估算

| 阶段 | 预估工时 |
|------|----------|
| Phase 1 后端 graph | 4-6h |
| Phase 2 前端对接 | 3-4h |
| Phase 3 前端修复 | 1-2h |
| Phase 4 下线旧代码 + 测试 | 1-2h |
| **合计** | **9-14h** |

---

*文档生成时间：2026-08-28*
*依据代码版本：当前 workspace HEAD*
