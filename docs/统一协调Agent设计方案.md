# 统一协调 Agent（Coordinator Agent）设计方案

> 项目：Self Grow 个人成长系统
> 文档状态：设计方案（含落地指引）
> 关联文档：[前端浏览器缓存与存储详解](./前端浏览器缓存与存储详解.md) · [数据库知识深入学习指南](./数据库知识深入学习指南.md)
>
> **v2 架构调整**：由单一大 Agent + 一套工具 → **主 Agent（Router）+ 一组无状态次 Agent 并行**。
> **v3 技术选型**：引入 LangGraph 实现多智能体编排，替代手写 tool-call 循环与反问队列。

---

## 1. 背景与目标

### 1.1 现状痛点

当前系统是一个「多表单孤岛」结构：

| 模块 | 输入方式 | 示例 |
|------|----------|------|
| 行动记录 | 行动页表单 | 记一笔"跑了30分钟" |
| 习惯打卡 | 习惯页按钮 | 打勾"早睡" |
| 任务 | 任务页表单 | 新增"明天交报告" |
| 技能树 | 技能树编辑器 | 加一个节点 |
| 表达训练 | 独立对话 | 出题 → 答题 |

用户想完成一件事，必须先**找到正确的页面 → 找对表单 → 逐项填写**。系统没有统一的对话入口。

### 1.2 解决方案

给整个系统装一个 **统一协调 Agent**：用户用自然语言在侧边栏输入，主 Agent 先理解意图并调度，再由对应模块的**次 Agent** 完成操作，最后返回结果。

例如，同样是记一笔行动，原来是：

```
打开行动页 → 选维度"健康" → 选子类型"运动" → 填时长"30" → 填备注 → 提交
```

现在是：

```
输入："我下午跑了半小时步"
→ 主 Agent 识别 [记录行动] → 派发行动次 Agent → 自动写库 + 返回"+15 EXP，健康维度"
```

### 1.3 面试叙事版本

> **我构建了一个基于 Tool-Use 的多智能体网关：主 Agent 负责任意输入的路由与跨任务关联，并按运行时为每个次 Agent 动态生成定制指令；次 Agent 无状态、可并行，各自维护独立上下文并通过全局反问题队列与用户交互。**

四层递进的技术亮点：
1. **Tool-Use 工程**：手动实现 OpenAI 式多工具轮询协议，非简单调 API。
2. **多智能体协调**：从 3 个单域 Agent 抽象出「主 Agent 路由 + 次 Agent 并行执行」架构。
3. **上下文架构**：次 Agent 无状态（任务完即清）、主 Agent 唯一长上下文、关联耦合由主 Agent 负责。
4. **产品 sense**：理解"用户不填表单，用户说话"。

---

## 2. 核心架构（v3 LangGraph）

### 2.1 角色分工

| 角色 | 职责 | 上下文 | 状态 |
|------|------|--------|------|
| **主图（Coordinator Graph）** | 意图识别、路由、并行派发子图、整合结果、处理跨任务关联 | **唯一长上下文**（LangGraph checkpoint 持久化） | 有状态 |
| **子图（各域 SubGraph）** | 专注单一数据域。吃主图给的定制指令 → 判定参数是否齐 → `interrupt` 反问或执行工具 → 返回 | **单次任务生命周期**，任务完即清 | **无状态** |

### 2.2 核心流程

```
用户输入
  ▼
主图 router_node：解析意图，决定调用 N 个子图
   · 延续上一任务？→ 相关历史摘要塞进指令
   · 新任务？     → 写一份干净的新指令
  ▼
并行派发（LangGraph 自动并行执行匹配的子图）
  ▼
子图_i：{ 判定参数 → interrupt 反问 | 执行工具 }
  ├─ interrupt → 前端渲染反问卡片 → Command(resume) 恢复
  └─ 完成 → 任务结束，清除该子图上下文
  ▼
主图 synthesize_node：收集 N 个结果 → 整合成一句回复
```

**关键分工原则**：
- **子图不背业务逻辑，也不背跨任务上下文** —— 每次被调用时只拿主图提炼过的「本次任务的定制指令」，而非整个对话历史。
- **上下文传递＝主图运行时榨取** —— 主图把相关历史压缩进任务 prompt 传给子图，子图因此可以**完全无状态**。
- **边界判断上移主图** —— "用户这一句是延续某域未完成的任务，还是开新任务？"由主图语义判断。
- **interrupt 天然解决反问** —— 子图遇到缺参数直接 `interrupt`，框架自动管理中断/恢复，无需手写队列。

由此自动推论：**「任务完成即清子图上下文」完全正确** —— 因为关联性已由主图保证，子图没有保留上下文的必要（省 token、防串味、防无限堆积）。

---

## 3. 关键设计

### 3.1 主图派发指令的动态生成

主图在派发子图时的 Prompt 里执行两件事（伪代码）：

```
1. 边界判断：
   "本次用户输入，是延续之前未完成的某域任务，还是开新任务?"
   ├─ 延续 → 把相关历史摘要塞进该子图的指令
   └─ 新任务 → 干净利落写一份新指令

2. 提炼定制指令：
   "根据整个对话历史，为用户这条『记跑步』提炼一份子图专用指令，
   包括：维度、可能缺的参数、用户偏好的表述习惯"
```

这样，跨任务关联的边界担忧落地为**主图的一次决策**，而非散落在各子图里。

### 3.2 子图反问机制（LangGraph interrupt）

LangGraph 原生支持 human-in-the-loop，子图遇到缺参数直接调用 `interrupt`：

```python
from langgraph.types import interrupt

def action_subgraph(state):
    # ... 执行中发现缺参数
    answer = interrupt({
        "question": "跑了多久?",
        "type": "parameter_missing"
    })
    # answer = 前端通过 Command(resume) 传回的用户回答
```

**对比手写队列的优势**：
| 手写 FIFO 队列 | LangGraph interrupt |
|---------------|---------------------|
| 手动维护队列入队/出队 | 框架自动管理 |
| 前端轮询检查状态 | 后端推送中断事件 |
| 需要 task_id 关联 | `Command(resume)` 自动关联 |
| 并发控制复杂 | 框架天然支持并行中断 |

### 3.3 主图路由（轻量）

主图 `router_node` 用正则 + 关键词快速分类，模糊语义交给 LLM 兜底：

```
输入 → 快速分类（正则 + 关键词，非重活）
  ├─ 行动记录域：  含 记/跑了/睡了/运动/工作/创作/复盘 → 行动子图
  ├─ 习惯域：      含 打卡/习惯/坚持/每天              → 习惯子图
  ├─ 任务域：      含 任务/待办/今天做/安排             → 任务子图
  ├─ 统计查询域：  含 怎么/怎么样/报告/统计/进度        → 只读查询，免确认
  ├─ 技能树域：    含 技能树/节点/技能                  → 技能树子图
  ├─ 纯聊天域：    闲聊 / 无系统操作意图                → 纯文本回复，不进子图
  └─ 关键词全不中： → 交 LLM 语义判断兜底
```

**价值**：
- 简单指令直接走轻路径短路，省 token。
- 模糊语义交给 LLM 兜底，保证灵活。
- 用户输入可能**同时命中多个域**（如"记跑步 + 加个明天交报告的任务"）→ 并行派发多个子图。

### 3.4 并行多意图

一个用户输入可能包含多个意图，主图判断后**并行派发多个子图**，各子图独立补齐参数。前端通过来源标注（agent_id）区分各自的答案。

### 3.5 写操作确认

写库操作（记行动/打卡/建任务/改技能树）默认**先确认后执行**：

```
子图: 识别到「跑步 30 分钟 · 健康维度 +15 EXP」，是否提交？
用户: 确认 → 走业务层写库 → 回显经验/等级变化
```

实现：子图调用 `interrupt` 发起确认，用户通过 `Command(resume)` 传回确认结果。可提供"免确认模式"开关。

---

## 4. 技术选型：LangGraph 多智能体编排

**结论：引入 LangGraph 实现主图 + 子图编排，替代手写 tool-call 循环与反问队列。**

### 4.1 选型理由

| 维度 | 裸 httpx（原方案） | LangGraph（新方案） |
|------|-------------------|---------------------|
| tool-call 循环 | 手写 while loop | `create_react_agent` 内置 |
| 反问队列 | 手写 FIFO + 前端滑动窗口 | `interrupt/resume` 原生支持 |
| 并行执行 | 手动 async/await 编排 | 声明式并行节点 |
| 状态管理 | 手动传递 dict | `TypedDict` + `operator.add` 自动合并 |
| 可观测性 | 无 | checkpoint + 回放 |
| 代码量 | ~800 行 | ~480 行（减少约 40%） |

### 4.2 与项目现有代码的集成

| 现有资产 | LangGraph 对接方式 |
|----------|-------------------|
| `ai_action_service.py` | 包装成 `action_agent` 子图，工具函数复用业务层 |
| `ai_service.py`（技能树） | 包装成 `skill_tree_agent` 子图 |
| `expression_service.py` | 包装成 `expression_agent` 子图 |
| `_call_llm_with_tools` | 替换为 `create_react_agent`，LangGraph 内部处理 tool-call 循环 |
| `call_ai_text_stream` | 用 LangChain 的 `ChatOpenAI.stream()` 替代 |

### 4.3 依赖变更

```toml
# backend/pyproject.toml 新增
langgraph = ">=0.2.0"
langchain-openai = ">=0.2.0"  # 已有
```

**LangChain 定位调整**：不再仅用于纯文本流式，而是作为 LangGraph 的底层 LLM 接口统一使用。

---

## 5. 项目现状盘点（可复用资产）

已有 3 套成熟的 AI 引擎可复用为次 Agent 子图：

| 引擎 | 文件 | 现状 | 复用为 |
|------|------|------|--------|
| 技能树 AI | `backend/services/ai_service.py` + `prompts/skill_tree.py` | 9 工具多工具轮询 | 技能树次 Agent 子图 |
| 行动解析 AI | `backend/services/ai_action_service.py` + `prompts/action_parse.py` | 对话提取 + 批量提交 | 行动次 Agent 子图 |
| 表达训练 AI | `expression_service.py` 的 `_call_llm_with_tools` | 分轮执行工具 + 容错 | 表达训练次 Agent 子图 |

### 5.1 LangGraph 子图化改造路径

现有引擎的 tool-call 循环 → `create_react_agent` 替换：

```python
# 原：手写 while loop（expression_service.py:171-266）
messages = [system_msg, user_msg]
while rounds < max_rounds:
    resp = call_llm_with_tools(messages, tools)
    if resp.tool_calls:
        # 手动执行工具、回填结果...
    else:
        return resp.content

# 新：LangGraph 内置
agent = create_react_agent(
    model=ChatOpenAI(model="gpt-4o-mini"),
    tools=[record_action, ask_user, ...],
    prompt="你是行动记录次 Agent...",
)
result = agent.invoke({"messages": [user_msg]})
```

次 Agent 子图在其上加两层：① 接受主 Agent 的定制指令作为 system prompt；② 缺失参数时用 `interrupt` 反问而非直接放弃。

---

## 6. 前端交互设计（LangGraph interrupt 机制）

LangGraph 原生支持 **human-in-the-loop**，通过 `interrupt` + `Command(resume)` 实现反问队列：

### 6.1 反问流程

```
用户输入
  ▼
主图 router → 并行派发子图
  ▼
子图执行中... 遇到缺参数
  ▼
interrupt({ question: "跑了多久?", type: "parameter_missing" })
  ▼
前端收到中断事件 → 渲染反问卡片
  ▼
用户回答 → POST /api/coordinator/resume { answer: "30分钟" }
  ▼
LangGraph Command(resume="30分钟") → 子图继续执行
```

### 6.2 前端渲染

```
┌────────────────────────────┐
│ 🤖 行动域 · "跑了多久?"      │  ← interrupt 事件（含 agent_id）
│ [输入框]  [提交]            │
└────────────────────────────┘
│ 🤖 任务域 · "明天几点?"      │  ← 另一个子图的 interrupt
│ [输入框]  [提交]            │
└────────────────────────────┘
（最多同时展示 2 格；提交一个 → 恢复对应子图）
```

### 6.3 关键优势

| 手写队列（原方案） | LangGraph interrupt（新方案） |
|-------------------|------------------------------|
| 手动维护 FIFO 队列 | 框架自动管理中断/恢复 |
| 前端轮询检查队列状态 | 后端推送 interrupt 事件 |
| 需要 task_id 关联 | `Command(resume)` 自动关联子图 |
| 并发控制复杂 | 框架天然支持并行中断 |

### 6.4 状态流转

每格卡片状态：
- `waiting` — 等待用户输入
- `submitting` — 已提交，等待子图恢复执行
- `completed` — 子图执行完毕，显示结果

用户回答能覆盖多个面的理想情况（"跑了半小时，报告明天交"）作为 **M 后期增强**：MVP 阶段各问各的。

---

## 7. 落地改动清单（点对点）

按项目 CLAUDE.md 的分层约定（prompts/services/routers + 前端 pages）：

| 层 | 文件 | 动作 | 工作量 |
|----|------|------|--------|
| state | 新建 `backend/services/coordinator/state.py` | 定义 `CoordinatorState` TypedDict + 各子图状态 | 小 |
| graph | 新建 `backend/services/coordinator/graph.py` | 主图定义（StateGraph + 条件路由 + 编译） | 中 |
| router | 新建 `backend/services/coordinator/router.py` | 路由节点：意图识别 + 动态生成子 Agent 指令 | 中 |
| agents | 新建 `backend/services/coordinator/agents/` | 各域子图：`action_agent.py` / `task_agent.py` / `habit_agent.py` / `query_agent.py` | 大 |
| prompts | 新建 `backend/prompts/coordinate.py` | 主 Agent 系统提示词 + 各子 Agent 指令模板 | 中 |
| routers | 新建 `backend/routers/coordinator.py` | `POST /api/coordinator/chat` + `POST /api/coordinator/resume` | 中 |
| routers | `backend/main.py` | 注册新路由 | 小 |
| frontend | 新建 `frontend/js/pages/coordinator.js` | 对话面板 + interrupt 事件处理 + 反问卡片渲染 | 中 |
| frontend | `frontend/css/pages.css` | 新增 `.coord__*` 样式，风格对齐 `.expr__*` | 小 |
| deps | `backend/pyproject.toml` | 新增 `langgraph` 依赖 | 小 |
| tests | `backend/tests/` | 新增协调服务 + 子图单元测试 | 中 |

**核心工作量集中在两块**：`agents/`（各域子图封装）和 `router.py`（主 Agent 路由 + 指令动态生成）。

---

## 8. 里程碑规划

| 阶段 | 内容 | 验收 |
|------|------|------|
| **M1** | LangGraph 环境搭建 + 主图骨架 + 行动/统计查询 2 个子图 | 「两个子图并行 interrupt 反问」跑通 |
| **M2** | interrupt 事件前端处理 + 反问卡片组件 | 多意图输入并行派发 + 前端双框渲染 |
| **M3** | 补任务/习惯/技能树子图 | 5 个执行域子图全通 |
| **M4** | 写操作确认流 + 免确认模式开关 | 写库前确认卡片 + 开关生效 |
| **M5** | 主 Agent 上下文管理（LangGraph checkpoint + 摘要压缩） | 长对话跨任务关联正确 |
| **M6** | 语音化操作（复用 agent.js ASR）+ 测试 + 整合 + 文档更新 | pytest 通过 |

---

## 9. 待定项（已确认）

1. **主 Agent 上下文管理** —— 采用 LangGraph 内置 SQLite checkpoint，MVP 阶段先不加摘要压缩，够用再优化。
2. **跨任务延续的精确判定** —— "这一句是上一单延续还是新一单"的具体 Prompt 策略，M5 随主 Agent 上下文一起定。
3. **主 Agent 是否流式** —— 纯路由判断可非流式（快省），最终长回复由命中的子图负责流式。

---

## 10. 技术决策记录

| 决策项 | 结论 | 理由 |
|--------|------|------|
| **主图上下文存储** | LangGraph 内置 SQLite checkpoint | 开箱即用，MVP 够用，后续可迁移到 PostgreSQL |
| **子图并行上限** | 无限制（框架自动调度） | LangGraph 默认 cap 16，项目最多 5 个域，足够 |
| **LLM 模型选择** | 复用项目现有 AI_API_KEY 配置 | 保持一致，不引入新依赖 |
| **子图复用方式** | 预编译子图，运行时传不同指令 | 性能更好，避免重复构建图 |
| **前端 interrupt 传输** | SSE 推送中断事件 | 与项目现有 SSE 风格一致 |
| **手写 tool-call 处理** | 保留现有 3 个 AI 服务不动，新功能用 LangGraph | 渐进式迁移，降低风险 |

---

## 10. 面试讲解对照表

| 面试官可能问 | 怎何答 |
|--------------|--------|
| 做过什么 AI 相关 | "基于 LangGraph 的多智能体协调系统，主图路由 + 5 个子图并行，跨 8 个数据域" |
| 为什么用 LangGraph | "手写 tool-call 循环和反问队列太重，LangGraph 的 `create_react_agent` + `interrupt/resume` 天然解决，代码量减少 40%" |
| 多智能体怎么分工 | "主图路由 + 动态写子图指令，子图无状态可并行，通过 `interrupt` 与用户交互" |
| 并发反问用户怎么操作 | "LangGraph 原生 `interrupt` 机制，每个子图独立中断/恢复，前端按 agent_id 渲染反问卡片" |
| 跨任务上下文怎么处理 | "边界判断上移主图，主图动态提炼指令传给子图，子图无状态，通过 checkpoint 持久化主图上下文" |
| AI 会不会乱写库 | "AI 只决定调哪个工具传什么参数，写库统一走业务层，含经验结算和写前确认（interrupt 确认）" |
| 如何演示 | "语音说『记一笔创作 + 加个明天交报告的任务』→ 双子图并行 interrupt 反问补齐 → 自动写库 + 等级变化回显" |

---

## 附录 A：主 Agent `route_to` 工具 Schema（草稿）

```json
[
  {
    "type": "function",
    "function": {
      "name": "route_to",
      "description": "将用户输入路由到对应域的次 Agent 处理。可同时调用多个次 Agent 处理多意图输入。",
      "parameters": {
        "type": "object",
        "properties": {
          "domains": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "domain": {
                  "type": "string",
                  "enum": ["action", "habit", "task", "query", "skill_tree", "expression", "chat"]
                },
                "reason": {"type": "string", "description": "为何路由至此域"},
                "instruction": {
                  "type": "string",
                  "description": "根据对话历史动态编写的该次 Agent 定制指令（含维度、可能缺的参数、用户表述习惯等）"
                }
              },
              "required": ["domain", "instruction"]
            }
          }
        },
        "required": ["domains"]
      }
    }
  }
]
```

---

## 附录 B：各域子图工具集（草稿）

> 仅列核心工具，LangGraph 子图使用 `@tool` 装饰器定义，实现时精简到对应域。

```json
[
  {
    "type": "function",
    "function": {
      "name": "record_action",
      "description": "记录一条用户行动。将识别到的维度、子类型、时长、备注提交入库并结算经验。",
      "parameters": {
        "type": "object",
        "properties": {
          "action": {
            "type": "object",
            "properties": {
              "category_id": {"type": "string", "description": "维度ID: health/study/relation/work/create/finance/hobby/soul"},
              "sub_type": {"type": "string"},
              "duration": {"type": "integer", "description": "时长分钟，固定值类型传0"},
              "note": {"type": "string"},
              "dimension_exp": {"type": "number", "description": "按计分规则计算的维度经验值"},
              "sleep_start": {"type": "string", "description": "睡眠模式入睡 HH:MM"},
              "sleep_end": {"type": "string", "description": "睡眠模式起床 HH:MM"}
            },
            "required": ["category_id", "note", "dimension_exp"]
          },
          "confirm": {"type": "boolean", "description": "用户是否已确认。默认 false。"}
        },
        "required": ["action", "confirm"]
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "set_habit_checkin",
      "description": "对某个习惯打卡或补打。参数含习惯名、日期、状态(done/skipped)。",
      "parameters": {
        "type": "object",
        "properties": {
          "habit_name": {"type": "string"},
          "date": {"type": "string", "description": "YYYY-MM-DD，默认今天"},
          "status": {"type": "string", "enum": ["done", "skipped"]}
        },
        "required": ["habit_name", "status"]
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "query_global_stats",
      "description": "查询用户整体数据：8维进度、净成绩、近期动态、热力图。只读，不改数据。",
      "parameters": {
        "type": "object",
        "properties": {
          "period": {"type": "string", "enum": ["today", "week", "month", "all"], "description": "统计范围"}
        }
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "ask_user",
      "description": "向用户发送一条消息并进入队列展示。用于询问缺失参数、确认写操作或解释结果。",
      "parameters": {
        "type": "object",
        "properties": {"content": {"type": "string", "description": "消息内容"}},
        "required": ["content"]
      }
    }
  }
]
```

> 附录 B 仅列核心 4 个工具；`create_task` / `update_task_status` / `query_skill_tree` 实现时按对应域补齐。LangGraph 子图通过 `interrupt` 实现反问，无需单独的 `ask_user` 工具。

---

*文档结束。v3 方案基于 LangGraph 多智能体编排，复用项目现有业务数据层，核心工作量集中在 `coordinator/agents/`（各域子图封装）+ `coordinator/router.py`（主图路由 + 指令动态生成）。*
