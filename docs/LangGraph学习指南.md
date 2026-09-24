# LangGraph 学习指南

> **读者画像**：你已经会用 LangChain 的基础（ChatOpenAI、消息类型、@tool、简单的 chain），本文从这个基础出发，把 LangGraph 系统讲一遍。
> **结合项目**：凡是本项目（Self Grow）用到的知识点，都会标注【本项目结合】并贴真实代码；踩过的坑标注【本项目踩坑】。
> **覆盖范围**：按 LangGraph 官方知识体系覆盖 80% 以上的常用知识点，从 State/Node/Edge 到 Checkpointer、interrupt、Send、多智能体、流式、Store、Platform，再到 LangChain 的进阶内容。
> 核实时间：2026-09-23。项目代码引用自 `backend/services/coordinator/`、`backend/services/skill_tree_ai/`。

---

## 目录

- [第一部分：为什么会有 LangGraph](#第一部分为什么会有-langgraph)
- [第二部分：四大基石——State / Node / Edge / Compile](#第二部分四大基石state--node--edge--compile)
- [第三部分：Checkpointer——会话持久化](#第三部分checkpointer会话持久化)
- [第四部分：工具调用——Agent 的手脚](#第四部分工具调用agent-的手脚)
- [第五部分：人机协同（Human-in-the-loop）](#第五部分人机协同human-in-the-loop)
- [第六部分：多智能体架构](#第六部分多智能体架构)
- [第七部分：流式输出](#第七部分流式输出)
- [第八部分：循环防护与图设计](#第八部分循环防护与图设计)
- [第九部分：长期记忆 Store](#第九部分长期记忆store)
- [第十部分：部署与生态](#第十部分部署与生态)
- [第十一部分：LangChain 进阶](#第十一部分langchain-进阶)
- [第十二部分：知识地图自检](#第十二部分知识地图自检)
- [附录 A：本项目 LangGraph 文件地图](#附录-a本项目-langgraph-文件地图)
- [附录 B：面试高频问答](#附录-b面试高频问答)

---

# 第一部分：为什么会有 LangGraph

## 1.1 链是"管道"，Agent 是"循环"

用 LangChain 写最基础的功能时，代码长这样：

```python
chain = prompt | llm | output_parser
result = chain.invoke({"question": "你好"})
```

这就是 **LCEL（LangChain Expression Language）** 的链：数据从左流到右，**走一遍就结束**。像水管，进什么出什么。

但 Agent 不是这样的。Agent 的本质是：

```
用户提问 → LLM 思考 → 要不要调工具？
                          ├── 要 → 调用工具 → 拿到结果 → 回到"LLM 思考"（再来一轮）
                          └── 不要 → 输出答案 → 结束
```

**这里面有一个循环**：LLM 可能调用工具、看结果、再调用工具、再看结果……循环多少轮事先不知道，由 LLM 自己决定。水管模型表达不了"回到上游"，这就是为什么需要一个能表达**循环和分支**的结构——**图（Graph）**。

LangGraph 的名字就是这么来的：**用图来编排 LLM 应用**。节点（Node）是干活的步骤，边（Edge）是步骤之间的跳转关系，边可以回头，所以能表达循环。

## 1.2 旧 AgentExecutor 为什么被淘汰

LangChain 早期有一个 `AgentExecutor`（`initialize_agent` / `create_tool_calling_agent` 那一套），它把上面的循环帮你写死了。快速上手很爽，但很快你会撞墙：

| 撞墙点 | 说明 |
|--------|------|
| **循环逻辑改不了** | 想"工具失败重试 3 次再放弃"？AgentExecutor 内部写死了，你只能在外面 hack |
| **中间状态看不见** | 想知道"现在跑到第几轮、调用了哪些工具"？很难拿 |
| **做不了人机协同** | 想在关键操作前暂停、问用户一句"确定吗"？没有官方机制 |
| **多 Agent 组合难** | 想让 Agent A 干完活交给 Agent B？要靠 prompt 骗 |
| **没法持久化中断** | 程序重启，对话状态全丢 |

于是 LangChain 团队做了 LangGraph：**把循环、分支、状态、持久化这些底层能力全部交还给你，你用图自己搭**。代价是要多写一点代码，换来完全的控制力。

官方目前的迁移方向也很明确：**旧的 AgentExecutor / Memory 体系已被标记弃用，新项目一律用 LangGraph**。所以现在学 LangGraph 不是"学个新框架"，而是"学 LangChain 官方钦定的下一代写法"。

## 1.3 一分钟最小示例

先看一个最简单的 LangGraph 程序，感受一下形态：

```python
from typing import TypedDict
from langgraph.graph import StateGraph, START, END

# 1. 定义状态：一张所有节点共享的"黑板"
class State(TypedDict):
    text: str

# 2. 定义节点：普通函数，接收状态、返回"要更新的部分"
def step_a(state: State) -> dict:
    return {"text": state["text"] + " → A处理过"}

def step_b(state: State) -> dict:
    return {"text": state["text"] + " → B处理过"}

# 3. 搭图
graph = StateGraph(State)
graph.add_node("a", step_a)
graph.add_node("b", step_b)
graph.add_edge(START, "a")     # 入口 → a
graph.add_edge("a", "b")       # a → b
graph.add_edge("b", END)       # b → 结束

# 4. 编译并运行
app = graph.compile()
print(app.invoke({"text": "初始"})["text"])
# 输出: 初始 → A处理过 → B处理过
```

四步：**定义状态 → 定义节点 → 连边 → 编译运行**。这就是 LangGraph 的全部骨架，后面所有高级功能都是往这四步里加料。

## 1.4 版本与安装

```bash
pip install langgraph                    # 核心（会自动带上 langchain-core）
pip install langgraph-checkpoint-sqlite  # SQLite 持久化（可选）
pip install langgraph-checkpoint-postgres # Postgres 持久化（可选）
```

版本历史需要知道两段：

- **0.x 时代**（2024）：API 频繁变动，很多老教程里的写法（`Memory`、`interrupt_before` 老用法）已过时。
- **1.0 时代**（2025-10 起正式发布）：API 稳定，主推 `interrupt()` / `Command` / `stream_mode="custom"` / `Store` 这套新写法。本文以 1.x 的心智模型为主，同时兼顾 1.0 前的常见写法（因为大量教程和存量代码还是老写法）。

【本项目结合】项目 `pixi.toml` 中直接依赖 `langgraph`（连带 `langchain-core`、`langchain-openai`），两个 AI 模块（`services/coordinator/`、`services/skill_tree_ai/`）都基于它构建。

---

# 第二部分：四大基石——State / Node / Edge / Compile

## 2.1 State：图的"共享黑板"

**State 是整张图共享的、唯一的数据载体。** 所有节点读它、写它；LangGraph 负责在节点之间传递它。

三种定义方式：

```python
# 方式一：TypedDict（最常用，轻量）
from typing import TypedDict
class State(TypedDict):
    messages: list
    user_id: int

# 方式二：Pydantic（自带校验）
from pydantic import BaseModel
class State(BaseModel):
    messages: list = []
    user_id: int

# 方式三：dataclass
import dataclasses
@dataclasses.dataclass
class State:
    messages: list
    user_id: int
```

一个重要细节：`TypedDict(total=False)` 表示**所有键都是可选的**——节点返回时不强制每个字段都给值。项目里就这么用：

```python
# 【本项目结合】技能树 AI 的状态（services/skill_tree_ai/state.py 节选）
class SkillTreeChatState(TypedDict):
    user_id: int
    tree_id: str
    tree: dict                          # 当前内存中的树（AI 操作的目标）
    selected_node_ids: list[str]        # 当前选中的节点
    messages: Annotated[list, operator.add]   # 对话历史（自动累积！）
    diffs: list[NodeDiff]               # 变更记录（每次整体替换）
    executed_tools: list[dict]          # 工具日志（每次整体替换）
    reply: str | None                   # 最终回复
    pending_confirmation: PendingConfirmation | None  # 待确认操作
    ask_rounds: int                     # 反问轮数
```

## 2.2 Reducer：状态怎么合并（最容易踩坑的地方）

**默认规则：节点返回什么，对应字段就被整体覆盖。**

```python
def node(state):
    return {"counter": 10}   # state["counter"] 直接变成 10，不管原来是几
```

但有些字段你不想要"覆盖"，想要"追加"——最典型的就是 `messages`：每个节点产生的新消息应该**追加**到历史里，而不是把历史清了。这时用 `Annotated` 给字段挂一个 **Reducer（合并函数）**：

```python
import operator
from typing import Annotated

class State(TypedDict):
    # operator.add 就是 "a + b"：对列表来说就是列表拼接
    messages: Annotated[list, operator.add]
    # 没挂 reducer 的字段 = 默认覆盖
    final_answer: str
```

这样节点返回 `{"messages": [新消息]}` 时，LangGraph 会自动做 `旧消息列表 + [新消息]`。

常用 reducer 还有：

```python
# add_messages：官方提供的消息专用 reducer
# 它比 operator.add 更聪明：会按 message id 去重合并（同 id 更新而不是追加）
from langgraph.graph.message import add_messages
class State(TypedDict):
    messages: Annotated[list, add_messages]

# 自定义 reducer：比如"取最大值"
def keep_max(a: int, b: int) -> int:
    return max(a, b)
class State(TypedDict):
    best_score: Annotated[int, keep_max]
```

**【本项目踩坑】这就是本项目主流程退出 StateGraph 的直接原因。** `services/coordinator/graph.py` 的注释写得很清楚：

> 本模块只做编排，不再使用 LangGraph StateGraph（主流程是线性三段，无分支/循环，LangGraph 的 operator.add 状态合并反而会引入跨轮累积问题）。

具体场景：协调 Agent 的会话是**多轮**的（用户说一句 → 反问 → 用户答 → 总结）。如果主图状态用 `operator.add` 挂在 `results` / `interrupts` 这类字段上，那么**第二轮** ainvoke 时，上一轮的结果会被累积进新一轮，前端就会收到重复的旧结果。项目的解法是**双轨制**：

- **子图内部**（单轮内）：`messages` 用 `Annotated[list, operator.add]`，享受自动累积（对话历史正是需要累积的）。
- **主流程**（跨轮编排）：不用 StateGraph，用普通 Python dict + 显式函数调用（`run_coordinator` 三段式），状态合并逻辑完全自己控制。

同一份代码里，`state.py` 还有第二个刻意的反例——`diffs` 和 `executed_tools` **故意不挂** reducer：

```python
# AI 对树的所有变更（返回给前端一次性应用）
# 注意：普通字段而非 operator.add —— 每次调用整体替换，
# 否则旧 diff 会在 checkpointer 中跨轮累积并被重复返回给前端
diffs: list[NodeDiff]
```

这两处注释是理解 reducer 的最好教材：**"要不要累积"不是框架替你决定的，而是你按字段的业务语义决定的。** 这是 LangGraph 面试里最值得讲的一个点。

## 2.3 Node：干活的函数

节点就是一个函数：**接收完整 state，返回"要更新的部分"**（不用返回全量）。

```python
def my_node(state: State) -> dict:
    # 读状态、干活（调 LLM、查数据库……）
    return {"final_answer": "干完了"}   # 只返回要更新的键
```

三条规则：

1. **可以 async**：`async def my_node(state)` 完全支持，且推荐（LLM 调用天然是 IO 密集）。
2. **返回部分更新**：只写你要改的键，没写的键保持不变。
3. **返回值立即过 reducer**：挂了 `operator.add` 的字段是"追加"，普通字段是"覆盖"（见 2.2）。

节点除了函数，还可以是：**另一个编译好的图（子图）**、一个 **Runnable**（LangChain 的可调用对象）。子图作为节点详见第六部分。

**【本项目结合】** 项目里最核心的节点是 `make_agent_node` 工厂产出的 `agent_node`——它内部包了一整个 ReAct 循环（LLM ↔ 工具多轮交互），对外只是一个"节点"。这是很重要的设计思想：**节点的粒度由你定，一个节点内部可以是一个很复杂的世界**。图的边只负责粗粒度流转，细粒度循环在节点内部自己写。

```python
# 【本项目结合】services/coordinator/agents/base.py（节选）
def make_agent_node(tools, domain, domain_label, system_prompt):
    async def agent_node(state):          # ← 这就是"节点"
        llm = get_llm(temperature=0.3, user_id=state.get("user_id", 0))
        # ... 内部是一个 for 循环跑 ReAct（详见第四部分）...
        return {"messages": new_messages, "result": tool_result}
    return agent_node
```

## 2.4 Edge：普通边、条件边、START / END

**普通边**——写死的跳转：

```python
graph.add_edge("a", "b")        # a 完成后必定去 b
graph.add_edge(START, "a")      # 入口：图启动后第一个去 a
graph.add_edge("b", END)        # b 之后图结束
# 等价写法：graph.set_entry_point("a")
```

`START` 和 `END` 是两个特殊常量（`from langgraph.graph import START, END`），分别代表图的起点和终点。

**条件边**——由函数决定去哪：

```python
def should_continue(state: State) -> str:
    if state["needs_tool"]:
        return "tools"       # 返回"节点名"
    return END               # 也可以直接返回 END 结束

graph.add_conditional_edges("agent", should_continue)   # agent 完成后问 should_continue
```

条件函数的返回值可以是：**单个节点名**、**节点名列表**（并行去多个节点）、`END`，或者一个 `{"节点名": 更新值}` 的映射（老版本写法）。如果返回的名字不存在的节点，运行时报错——所以常见做法是配合路由表。

条件边 + 循环边（`tools → agent` 的回头边）就是手写 ReAct 的标准结构：

```python
graph.add_edge(START, "agent")
graph.add_conditional_edges("agent", should_continue)   # agent → tools 或 agent → END
graph.add_edge("tools", "agent")                        # tools 干完 → 回 agent（循环！）
```

**【本项目结合】** 项目两个子图都是"单节点直通图"——`agent → END`，没有任何条件边。因为循环被放进了节点**内部**（ReAct 在 `agent_node` 里 for 循环完成），图层面不需要再表达循环。两种写法（图层面循环 vs 节点内循环）都是合法的，项目选择了后者，理由在第四部分详细分析。

```python
# 【本项目结合】services/coordinator/agents/base.py::build_subgraph
graph = StateGraph(state_class)
graph.add_node("agent", make_agent_node(tools, domain, domain_label, system_prompt))
graph.set_entry_point("agent")     # START → agent
graph.add_edge("agent", END)       # agent → END（一次性跑完）
return graph.compile(checkpointer=get_checkpointer())
```

## 2.5 compile() 与调用方式

`compile()` 把"图纸"（StateGraph 对象）变成"可运行的机器"：

```python
app = graph.compile(
    checkpointer=...,          # 持久化器（第三部分）
    interrupt_before=["tools"], # 在进入 tools 节点前暂停（第五部分）
    interrupt_after=[...],      # 在节点之后暂停
    store=...,                  # 长期记忆仓库（第九部分）
)
```

编译产物有四种调用方式：

| 方法 | 说明 |
|------|------|
| `app.invoke(input, config)` | 同步一次性执行，返回最终 state |
| `app.ainvoke(input, config)` | 异步一次性执行（**项目用的就是它**） |
| `app.stream(input, config, stream_mode=...)` | 流式执行，逐步吐出中间状态（第七部分） |
| `app.batch([input1, input2])` | 批量执行 |

## 2.6 config：thread_id、recursion_limit

调用时的 `config` 参数是新手最容易忽略、但极其重要的东西：

```python
config = {
    "configurable": {
        "thread_id": "user123:session456",   # 会话标识（checkpointer 按它隔离）
    },
    "recursion_limit": 50,   # 循环上限（默认 25，详见第八部分）
    "tags": ["production"],  # 标签（给 LangSmith 追踪用）
    "metadata": {...},       # 任意元数据
}
result = await app.ainvoke({"messages": [...]}, config=config)
```

**【本项目结合】** 项目里 thread_id 的用法分两处，命名规则不同：

```python
# 协调 Agent 的子图：主会话 ID 拼上域名，天然隔离
sub_thread_id = f"{main_thread_id}:{domain}"      # 如 "abc123:action"
config = {"configurable": {"thread_id": sub_thread_id}}

# 技能树 AI：独立会话 ID 编入 user_id，避免跨用户串号
thread_id = thread_id or f"stc_{user_id}_{uuid.uuid4().hex[:12]}"
```

---

# 第三部分：Checkpointer——会话持久化

## 3.1 为什么需要它

LLM 是无状态的：每次调用只认识你这次传给它的消息。所谓"多轮对话"，全靠你把历史消息每次都重新传一遍。**那么历史消息存在哪？** 这就是 checkpointer 的职责：

> **Checkpointer = 在每个节点执行完后，把当前 state 快照存下来的组件。**

有了它，你获得三个能力：

1. **对话记忆**：下次 ainvoke 时，LangGraph 自动从快照恢复历史，新消息自动接在后面。
2. **断点恢复**：程序中断后重启，从上次快照继续（配合 interrupt）。
3. **时间旅行**：查看/回滚到任意一步的历史快照。

## 3.2 三种实现

```python
# ① MemorySaver（1.0 后也叫 InMemorySaver）：存内存，重启全丢，开发调试用
from langgraph.checkpoint.memory import MemorySaver
checkpointer = MemorySaver()

# ② SqliteSaver：存本地 SQLite 文件，单机轻量持久化
# pip install langgraph-checkpoint-sqlite
from langgraph.checkpoint.sqlite import SqliteSaver
with SqliteSaver.from_conn_string("checkpoints.db") as cp:
    app = graph.compile(checkpointer=cp)

# ③ PostgresSaver：生产级，多实例共享
# pip install langgraph-checkpoint-postgres
from langgraph.checkpoint.postgres import PostgresSaver
```

**【本项目结合】** 项目用的是 ①，且做成了**全局单例**（`services/coordinator/checkpointer.py`，全部代码就这么几行）：

```python
from langgraph.checkpoint.memory import MemorySaver

_checkpointer = MemorySaver()

def get_checkpointer() -> MemorySaver:
    """获取全局 checkpointer 单例"""
    return _checkpointer
```

为什么全局单例？因为**主图和 6 个子图共用一个 checkpointer，靠 thread_id 隔离**。如果每个图各建一个，对话历史就"各记各的"，反问后接不回上下文。这本质上是单例模式（详见 `docs/设计模式学习指南.md` §2.1）。

**【本项目踩坑】必须知道的取舍**：`MemorySaver` **不是持久化**——服务重启，所有会话历史清零。这是项目的已知限制（已记入文档"已知限制"）：重启后用户如果继续旧会话，子图会当成全新会话处理。生产上要扛重启，就该换 SqliteSaver/PostgresSaver——接入成本很低，因为 checkpointer 是编译时注入的，业务代码一行不用改。这是 checkpointer 抽象设计的好处：**存储实现与图逻辑完全解耦**。

## 3.3 thread_id：会话隔离的全部秘密

checkpointer 按 `thread_id` 分仓：**相同 thread_id = 同一个会话（共享历史），不同 thread_id = 完全隔离**。

```python
# 同一个 thread_id 连续 invoke：第二次会自动带上第一次的消息历史
config = {"configurable": {"thread_id": "session-001"}}
await app.ainvoke({"messages": [HumanMessage("我叫小明")]}, config)
result = await app.ainvoke({"messages": [HumanMessage("我叫什么？")]}, config)
# result 里 LLM 能答出"小明"——因为历史被 checkpointer 拼回来了
```

**【本项目结合】** 这是项目里最精妙的一处设计。协调 Agent 有 6 个域子图（action/query/goal/task/habit/reward），全部挂在**同一个** MemorySaver 上，thread_id 规则：

```
{main_thread_id}:{domain}
例如 "会话abc:action"、"会话abc:goal"
```

效果：**主会话 abc 里，每个域有自己独立的对话线**。用户回答了 action 域的反问，只污染 action 这一条线，不会串到 goal 域。这是多智能体共享 checkpointer 的标准姿势。

## 3.4 读取状态：get_state / get_state_history

```python
# 查看当前快照
snapshot = await app.aget_state(config)
snapshot.values          # 当前完整 state 字典
snapshot.next            # 下一步要执行的节点（元组）；() 空表示图跑完了
snapshot.tasks           # 正在执行/待执行的任务信息（含 interrupt 详情）

# 查看历史快照列表（时间旅行的基础）
history = app.get_state_history(config)
for snap in history:
    print(snap.config, snap.values)
```

**【本项目结合】** 技能树 AI 的 resume 流程在恢复前先读快照，检查有没有"待确认操作"：

```python
# services/skill_tree_ai/graph.py::resume_skill_tree_chat（节选）
state = await graph.aget_state(config)
pending = state.values.get("pending_confirmation") if state else None

if pending and confirm:
    # 把「操作 + 原始参数」一起回灌：不带上参数，LLM 重新调用时可能
    # 生成与用户确认内容不一致的参数（确认的是删 A，结果删了 B）
    args_text = json.dumps(pending.get("args") or {}, ensure_ascii=False)
    content = (
        f"[系统] 用户已确认执行「{pending['tool']}」，原始参数：{args_text}。"
        f"请原样使用这些参数并附加 confirm=True 重新调用该工具。\n{user_message}"
    )
```

注意这个真实 bug 注释：**确认操作必须回灌原始参数**，否则 LLM 重新生成参数时可能跟用户确认过的内容不一致（用户确认删 A，LLM 重新算参数删了 B）。这是人机协同里非常隐蔽的正确性问题。

## 3.5 update_state 与时间旅行

```python
# 从外部直接改某个 thread 的状态（会记为一次"外部节点"的写入）
await app.aupdate_state(config, {"ask_rounds": 0}, as_node="agent")

# 时间旅行：拿历史快照的 config 重新 invoke，从那个点"分叉"重跑
old_snapshot = list(app.get_state_history(config))[-1]   # 最早的快照
await app.ainvoke(None, old_snapshot.config)              # 从那里重新执行
```

`update_state` 很实用：比如你在 resume 前想重置某个计数器、或者修正被 LLM 写坏的字段。时间旅行主要用于调试和"重试从某一步开始"。项目暂未用到这两者（用不到就不加，是对的）。

---

# 第四部分：工具调用——Agent 的手脚

## 4.1 @tool 与工具 schema

LangChain 的 `@tool` 装饰器把普通函数变成"LLM 认识的工具"：

```python
from langchain_core.tools import tool

@tool
def record_action(category: str, detail: str, duration: int) -> dict:
    """记录用户的行动并计算经验值。

    Args:
        category: 维度ID（health/study/work...）
        detail: 行动描述
        duration: 时长（分钟）
    """
    return create_action_and_award_exp(...)
```

三个要点：

1. **类型注解必须写**：LLM 是按 schema 调用的，`category: str` 告诉它该传字符串。
2. **docstring 就是工具说明书**：LLM 靠它判断"什么时候该调这个工具、参数怎么填"。写得好 = 工具用得准。
3. **枚举约束用 `Literal`**：

**【本项目结合】** 项目的 MCP 工具用 `Literal` 枚举把非法值挡在 LLM 门外：

```python
from typing import Literal
CategoryId = Literal["health", "study", "relation", "work", "create", "finance", "hobby", "soul"]

@mcp.tool()
def record_action(category: CategoryId, ...):
    ...
# LLM 传 "health" 之外的值 → schema 校验直接拦截，不会进业务代码
```

## 4.2 bind_tools：把工具"绑"给 LLM

`bind_tools` 不执行任何工具，只是把工具 schema 塞进请求：

```python
llm_with_tools = llm.bind_tools([record_action, ask_user])
response = await llm_with_tools.ainvoke(messages)

response.tool_calls
# [{'name': 'record_action', 'args': {...}, 'id': 'call_abc123'}, ...]
# 空列表 = LLM 认为不需要工具，直接给了文字回复
```

关键认知：**"调用工具"的永远是你，不是 LLM**。LLM 只是在回复里说"我想调 record_action，参数是这些"（`tool_calls` 字段），真正执行 `record_action(...)` 的是你的代码。理解了这一点，手写 ReAct 循环就毫无神秘感了。

**【本项目结合】** 项目有个动态 bind_tools 的小技巧——**反问超限时移除 ask_user 工具，逼 LLM 降级**：

```python
# services/coordinator/agents/base.py（节选）
if ask_rounds >= MAX_ASK_ROUNDS:
    active_tools = list(tools)          # 只剩业务工具，没有 ask_user
else:
    active_tools = all_tools            # 业务工具 + ask_user
llm_with_tools = llm.bind_tools(active_tools)
```

工具列表不是编译时写死的，**每次执行节点时按状态动态决定**。LLM 看不到 ask_user，自然不会再反问，只能用已有信息干活——这是一种很优雅的"软降级"。

## 4.3 ToolMessage 与 tool_call_id 配对

LLM 每次想调工具，会产生一条带 `tool_calls` 的 AIMessage；你执行完工具，必须**逐条**回一条 ToolMessage，并用 `tool_call_id` 对上号：

```python
new_messages = [response]                     # AIMessage（含 tool_calls）
for tc in response.tool_calls:
    result = tools_by_name[tc["name"]].invoke(tc["args"])
    new_messages.append(ToolMessage(
        content=json.dumps(result, ensure_ascii=False),
        tool_call_id=tc["id"],                # ← 必须配对
    ))
full = full + new_messages                     # 拼回上下文，下一轮 LLM 就能"看到"工具结果
```

如果配对断裂（AIMessage 说要调 3 个工具，你只回了 2 条 ToolMessage），下一轮请求会被 LLM API **直接拒绝（HTTP 400）**。

**【本项目踩坑】孤儿 ToolMessage。** 项目对消息历史做窗口截断时踩过这个坑：如果截断的刀口正好切在"AIMessage(tool_calls) 和它的 ToolMessage"之间，历史里就会出现一条"前面没有对应 AIMessage 的 ToolMessage"——孤儿。下一轮请求直接 400。修复代码（`services/skill_tree_ai/node.py`）：

```python
def _truncate_messages(messages: list, max_recent: int = 10) -> list:
    """截断消息历史，保留首条 + 最近若干条。

    截断边界必须落在「完整对话轮」上：若切在 AIMessage(tool_calls) 与其
    ToolMessage 之间，会产生孤儿 ToolMessage，导致 LLM API 返回 400。
    因此起始位置向后推进，直到不是 ToolMessage 为止。
    """
    if len(messages) <= max_recent + 1:
        return list(messages)
    start = len(messages) - max_recent
    while start < len(messages) and isinstance(messages[start], ToolMessage):
        start += 1          # ← 刀口落在 ToolMessage 上就往后挪，直到切在"轮"边界
    return [messages[0]] + messages[start:]
```

这个坑非常常见（所有做消息截断的项目都会遇到），面试讲出来含金量很高。

## 4.4 三种实现 ReAct 的方式

**方式一：官方 prebuilt——create_react_agent（最快）**

```python
from langgraph.prebuilt import create_react_agent
agent = create_react_agent(model, tools, prompt="你是一个助手")
result = await agent.ainvoke({"messages": [HumanMessage("...")]})
```

一行搞定，内部是标准的 "agent ↔ tools" 循环图。适合快速原型。

**方式二：ToolNode + tools_condition（半自动）**

```python
from langgraph.prebuilt import ToolNode, tools_condition

graph.add_node("agent", call_model)
graph.add_node("tools", ToolNode(tools))               # 官方工具执行节点
graph.add_conditional_edges("agent", tools_condition)  # 官方路由：有 tool_calls 去 tools，否则 END
graph.add_edge("tools", "agent")                       # 循环回到 agent
```

图结构自己搭，工具执行器用官方的。ToolNode 自带错误处理（工具抛异常会转成错误消息回给 LLM 而不是炸掉整个图）。

**方式三：手写循环（完全控制）**

在**一个节点内部**写 `for` 循环，自己解析 `tool_calls`、自己执行、自己拼 ToolMessage。

**【本项目结合】两个 AI 模块都不约而同选了方式三**（`coordinator/agents/base.py` 和 `skill_tree_ai/node.py` 各有一个手写循环）。为什么放弃官方封装？看项目需要的定制点就明白了：

| 定制需求 | create_react_agent 能做吗 | 手写循环 |
|---|---|---|
| ask_user 反问后**立即结束子图**并返回结构化 result | 做不到（它的循环语义是"工具结果回给 LLM 继续"） | ✅ 直接 return |
| 工具执行成功即结束（不看 LLM 后续） | 做不到 | ✅ `if tool_result.get("success"): return` |
| 每轮给 SSE 推"正在执行 xxx"阶段事件 | 要 hack | ✅ 循环里随便插 |
| 反问超限动态移除工具 | 做不到 | ✅ 每轮重新 bind_tools |
| 业务工具失败重试上限（MAX_ITERS） | 只能靠 recursion_limit | ✅ for 循环天然控制 |

**结论性经验**：prebuilt 适合"标准 ReAct"；一旦你的 Agent 需要**非标准退出条件**（反问即停、成功即停）或**过程可视化**，手写循环反而是更简单的选择。这也是"框架给你便利，也给你边界"的典型例子。

## 4.5 InjectedState / InjectedToolArg：隐藏参数

有时工具需要访问图的 state（比如 user_id），但你**不想让 LLM 填这个参数**（它填了反而是安全隐患）。两个专用注解：

```python
from langchain_core.tools import InjectedToolArg
from langgraph.prebuilt import InjectedState

@tool
def my_tool(query: str, state: Annotated[dict, InjectedState()]) -> dict:
    """这个工具的 schema 里不会出现 state —— LLM 看不到它"""
    user_id = state["user_id"]
    ...
```

**【本项目结合】** 技能树 AI 的工具就是这么注入整棵树状态的：

```python
# services/skill_tree_ai/node.py（执行处）
# 手动注入 state（InjectedState 已把 state 从工具 schema 中排除）
result = tool_fn.invoke({**args, "state": state})
```

技能树 AI 的 9 个工具全部按"节点 ID"操作（而不是按内容猜），工具需要拿到 `state["tree"]` 才能干活——由循环统一注入，LLM 的 schema 里只有"节点 ID、操作类型"这些它该填的。

## 4.6 并行工具调用与错误处理

一次 AIMessage 的 `tool_calls` 可能是**多条**（LLM 决定同时调多个工具），你的循环要逐条处理、逐条回 ToolMessage（项目就是这么做的：`for tc in response.tool_calls`）。

错误处理的两种策略：

```python
# 策略一：异常转成"失败结果消息"回给 LLM，让它自己决定重试还是放弃（项目做法）
try:
    tool_result = await asyncio.to_thread(tool_fn.invoke, args)
except Exception as e:
    tool_result = {"success": False, "message": f"工具执行异常：{e}"}
new_messages.append(ToolMessage(content=json.dumps(tool_result), tool_call_id=tc["id"]))
```

```python
# 策略二：ToolNode 的内置处理
ToolNode(tools, handle_tool_errors=True)   # 异常自动转错误消息
```

**项目做法里有个细节值得学**：工具是同步的（内部是同步 DB 调用），直接在 async 节点里跑会**卡死整个事件循环**（全站无响应）。所以统一丢线程池：

```python
tool_result = await asyncio.to_thread(tool_fn.invoke, args)
```

这在 FastAPI + LangGraph 组合里是必答题级的知识点。

---

# 第五部分：人机协同（Human-in-the-loop）

很多真实业务不允许 Agent"一路莽到底"：写数据库、删数据、花钱的操作，需要**中途暂停，等人类点头**。LangGraph 对此有一等公民的支持。

## 5.1 官方方案：interrupt() 与 interrupt_before/after

**老写法：编译期声明（粒度 = 节点）**

```python
app = graph.compile(checkpointer=cp, interrupt_before=["tools"])
# 每次要进入 tools 节点前，图暂停，ainvoke 返回当前状态
# 你检查后用 Command 恢复：
from langgraph.types import Command
result = await app.ainvoke(Command(resume=None), config)   # 放行
```

**新写法（1.0 主推）：interrupt() 函数（粒度 = 代码行）**

```python
from langgraph.types import interrupt, Command

def human_approval_node(state):
    answer = interrupt({"question": "确认执行删除吗？", "data": state["draft"]})
    # ↑ 图在这里暂停，answer 在恢复前是 None
    # ↓ 恢复时（resume 传值），从这里"原地复活"，answer 拿到用户给的值
    if answer == "yes":
        return do_delete(state)
    return {"reply": "已取消"}
```

恢复：

```python
result = await app.ainvoke(Command(resume="yes"), config)
```

`interrupt()` 的实现机制值得知道：它靠**抛出一个特殊异常**让图停止，checkpointer 记住暂停位置；resume 时从头重放节点，到 interrupt 行时不再抛异常、改为返回你 resume 的值。**副作用是：interrupt 之前的代码会重新执行一遍**——所以 interrupt 前不要放不可重复的操作（比如已经写了库的代码）。

## 5.2 Command：恢复 / 跳转 / 改状态三合一

```python
from langgraph.types import Command

Command(resume=value)            # 恢复 interrupt，把 value 交给它
Command(goto="node_b")           # 节点返回它 = 直接跳到 node_b（替代条件边）
Command(update={"key": value})   # 跳转的同时更新状态
Command(goto="node_b", update={"x": 1}, graph=Command.PARENT)  # 子图里控制父图跳转
```

`Command(goto=...)` 是 1.0 的新范式：**跳转逻辑从"边上的函数"移到了"节点内部"**，节点可以拿着刚算出来的结果决定去哪，比条件边更直观（条件边只能看 state，看不到节点局部变量）。

## 5.3 两条技术路线对比（本项目的选择）

**路线 A：interrupt 挂起式**（官方原生）

```
执行 → interrupt 暂停（图挂起，等待 resume）→ 用户回答 → Command(resume=...) → 原地继续
```

**路线 B：消息回灌式**（项目实际采用）

```
执行 → 调 ask_user 工具 → 子图【正常结束】，result 里带 needs_user=True
     → 编排层把问题透传给前端
     → 用户回答 → 编排层把回答作为 HumanMessage 追加，重新 ainvoke 同一个 thread
     → checkpointer 自动拼回全部历史，子图接着跑
```

**【本项目结合】** 协调 Agent 明确选了路线 B，`ask_user_tool.py` 的注释直接写了对比理由：

```python
# 相比 LangGraph interrupt() 方案的优势：
# - 反问问题作为普通消息持久化在 checkpoint，resume 时不丢失、不重问
# - 无挂起状态，「跳过/放弃」零成本
# - 单一状态源（checkpointer），不依赖额外线程存储
```

展开讲三点：

1. **interrupt 的暂停点是"节点重放"语义**，跨进程/重启场景下挂起状态依赖 checkpointer 的持久化可靠性；而路线 B 里反问是**普通消息**，天然躺在 checkpoint 历史里，永不丢。
2. **"跳过"零成本**：用户不想答了，前端传 `skip: true`，编排层补一句"用户跳过了该问题"，子图自己决定降级。如果用 interrupt，跳过也得构造一次 resume。
3. **子图结束 = 图层面无状态**：反问时子图已经 `agent → END` 跑完了，编排层（`_thread_store`）只需要记"哪些域还没完成"，简单得多。

注意一个精髓：**路线 B 之所以能工作，靠的正是第三部分讲的 thread_id 机制**——`resume_subgraph` 用同一个 `sub_thread_id` 再 ainvoke 一次，checkpointer 把"instruction + 反问"的历史拼回来，新 HumanMessage 接在后面，LLM 就在完整上下文里继续。**"多轮对话"不是 LangGraph 的新功能，而是 checkpointer 的自然推论。**

```python
# 【本项目结合】services/coordinator/graph.py::resume_subgraph（核心就这几行）
async def resume_subgraph(domain, sub_thread_id, answer):
    agent = SUBGRAPH_BUILDERS.get(domain)()
    config = {"configurable": {"thread_id": sub_thread_id}}   # ← 同一条会话线
    agent_result = await agent.ainvoke(
        {"messages": [HumanMessage(content=answer)]},          # ← 回答作为新消息
        config=config,
    )
    return _parse_agent_outcome(agent_result, domain, sub_thread_id)
```

**面试怎么答**：被问"为什么不用 interrupt()"，就答：我的反问发生在**子 Agent 层**，且业务要求"跳过/放弃"是一等操作；把反问做成普通工具调用 + 消息回灌，比挂起式更符合"单一状态源"原则，也避免了 interrupt 的节点重放副作用。这说明你不是不知道 interrupt，而是**评估后做的工程取舍**——这比"我用了最新 API"高一个段位。

## 5.4 技能树的确认卡片：另一种人机协同形态

技能树 AI 的"危险操作确认"（删除节点、批量替换）走的是**状态标记式**：

```python
# 工具返回 needs_confirmation → 节点把操作+参数写进 state，正常结束
return {
    "messages": new_messages,
    "reply": "请确认此操作",
    "pending_confirmation": {"tool": name, "args": args, ...},  # ← 挂起在状态里
}
# resume 时：aget_state 读出 pending_confirmation，
# 确认则回灌原始参数（见 3.4），拒绝则告诉 LLM 取消
```

对比协调 Agent 的 ask_user：一个把"要问的事"放在 `result`（瞬时返回值），一个放在 `state.pending_confirmation`（持久化在 checkpoint）——因为技能树的确认可能隔很久才回来（用户去页面上看了半天树才点确认），必须落进快照才可靠。**同一套"反问"需求，两种落点，取决于"问题要存活多久"。**

---

# 第六部分：多智能体架构

## 6.1 四种常见拓扑

当你需要多个 Agent 协作时，业界沉淀了四种典型结构：

| 拓扑 | 结构 | 适用 | 一句话 |
|------|------|------|--------|
| **单 Agent + 多工具** | 一个 ReAct 循环挂 N 个工具 | 工具少、域单一 | 一个人带一柜子工具 |
| **Supervisor（主管）** | 一个主管 Agent 决定派活给哪个工人，工人干完汇报 | 域多、需要路由 | 项目经理带团队 |
| **层级（Hierarchical）** | Supervisor 套 Supervisor，树状 | 规模大 | 部门总监 → 组长 → 员工 |
| **Swarm / Handoff** | Agent 之间直接互相"移交"控制权，无中心 | 对话式流转 | 接力赛 |

## 6.2 Supervisor 模式（最常用，理解本项目的基础）

```python
# 伪代码：Supervisor 的核心是一个路由节点
def supervisor(state):
    decision = llm.invoke("用户想说：{msg}。该交给哪个工人？[researcher/writer/ FINISH]")
    if decision == "FINISH":
        return Command(goto=END)
    return Command(goto=decision)      # 派活

graph.add_node("supervisor", supervisor)
graph.add_node("researcher", researcher_subgraph)   # 子图作为节点！
graph.add_node("writer", writer_subgraph)
# 每个工人干完 → 回 supervisor
```

官方还有高层封装库 `langgraph-supervisor` / `langgraph-swarm`，几行代码搭出标准结构；但**建议先手写一遍 Supervisor 再用封装**，否则出问题完全没有排障能力。

## 6.3 子图作为节点

编译好的图可以直接 `add_node` 进另一张图：

```python
parent.add_node("worker", worker_app)     # worker_app 是 compile() 的产物
```

三种状态对接方式：

1. **共享 state schema**：子图与父图用同一个（或兼容的）TypedDict，状态直通。
2. **状态映射**：两边 schema 不同，你包一个函数节点，进出各翻译一次。
3. **独立 checkpointer**：子图 compile 时挂自己的 checkpointer 和自己的 thread_id 规则。

**【本项目结合】** 项目走的是**第三种的变体**——子图不是"add_node 进父图"，而是被**编排函数直接 ainvoke**：

```python
# 父流程（graph.py）里没有 add_node，而是：
agent = builder()                                  # 编译好的子图
agent_result = await agent.ainvoke({...}, config)  # 直接调用
```

且父子共用一个 MemorySaver、用 `{main}:{domain}` 命名规则隔离。效果等价于"子图作为节点"，但**父层保留了对并发、错误隔离、事件推送的完全控制**（`asyncio.gather` 并行 6 个子图，一个失败不影响其他）。

## 6.4 Send API：动态并行（map-reduce）

条件边只能返回"已存在的节点名"，**发多少个分支在搭图时就定了**。如果分支数要运行时才知道（比如"把用户的 3 个诉求分给 3 个不同的子 Agent"，数量每次不同），就用 **Send**：

```python
from langgraph.types import Send

def dispatch(state) -> list[Send]:          # 条件函数返回 Send 列表
    return [Send(f"worker_{t['domain']}", {"task": t}) for t in state["tasks"]]
    # 运行时生成 N 份输入，N 个 worker 副本并行执行（map）
# 所有 worker 汇合到 reduce 节点（reducer 用 operator.add 汇总）
graph.add_conditional_edges("dispatcher", dispatch, ["workers_merge"])
```

**【本项目结合】** 项目实现同样语义用的是 **`asyncio.gather`**：

```python
coros = [_run_one_subgraph_reported(task, user_id, main_thread_id)
         for task in pending_tasks]
outcomes = await asyncio.gather(*coros, return_exceptions=True)
```

对比：Send 是**图层面**的动态并行（LangGraph 管理，checkpoint 每个分支一份，可视化里能看到 fan-out）；asyncio.gather 是**代码层面**的并行（自己管理，灵活、可以带 return_exceptions 做错误隔离、可以在每个分支前后插 SSE 事件推送）。项目选后者的理由：分支内需要精细的阶段事件（domain_start / domain_done / domain_ask），且父流程本来就没用 StateGraph。**两种都是正解，知道取舍就赢了。**

## 6.5 本项目架构全图

把前几部分拼起来，协调 Agent 的完整架构：

```
用户消息（自然语言）
   │
   ▼
┌─────────────────────────────────────────────────────┐
│ 阶段一 router_node（LLM 路由）                        │
│   "用户想记录行动 + 查询统计" → pending_tasks =        │
│   [{domain: action, instruction: ...},               │
│    {domain: query,  instruction: ...}]               │
└─────────────────────────────────────────────────────┘
   │  asyncio.gather 并行
   ├──────────────┬──────────────┐
   ▼              ▼              ▼
┌────────┐   ┌────────┐    ┌────────┐     每个是独立的单节点 StateGraph
│action  │   │query   │    │...     │     - 手写 ReAct 循环（节点内部）
│子图    │   │子图     │    │        │     - checkpointer: 全局 MemorySaver
│        │   │        │    │        │     - thread: {main}:{domain}
│ 缺信息?│   │ 完成 ✓ │    │        │     - 工具: 业务工具 + ask_user
│ ask_user│   └───┬────┘    │        │
└───┬────┘        │         └────────┘
    │ needs_user=True
    ▼
┌─────────────────────────────────────────────────────┐
│ 有未完成的域 → final_reply 置空，把反问透传给前端        │
│ 用户回答 → resume_subgraph（同 thread 追加消息再跑）    │
└─────────────────────────────────────────────────────┘
   │ 全部域完成
   ▼
┌─────────────────────────────────────────────────────┐
│ 阶段三 synthesize_node：汇总所有域的 result → 最终回复  │
└─────────────────────────────────────────────────────┘
```

**它是 Supervisor 的变体**：router_node 是"主管决策"，dispatch 是"派活"，子图是"工人"，synthesize 是"验收汇报"。区别于教科书 Supervisor 的三点：主管只决策一次（不做 FINISH 循环）、并行靠 gather 而非 Send、反问直达工人不回主管（resume 不重新路由）。**【本项目结合】** 这套"三段式"是理解本项目所有 AI 代码的地图，面试讲架构就从这张图开始。

---

# 第七部分：流式输出

## 7.1 stream() 与五种 stream_mode

```python
for chunk in app.stream(input, config, stream_mode="values"):
    ...
# 异步版
async for chunk in app.astream(input, config, stream_mode="updates"):
    ...
```

五种模式对比：

| stream_mode | 吐什么 | 典型用途 |
|-------------|--------|---------|
| `"values"` | 每个超级步后的**完整 state** | 调试、看状态演化 |
| `"updates"` | 每个节点的**增量更新**（`{节点名: 返回值}`） | 前端展示"步骤进度" |
| `"messages"` | LLM 的**消息块**（AIMessageChunk, metadata） | 逐 token 打字机效果 |
| `"custom"` | 你在节点里 `writer` 主动推的**自定义事件** | 推业务事件（"正在执行工具 X"） |
| `"debug"` | 一切内部事件（含任务、状态 diff） | 深度调试 |

可以叠加：`stream_mode=["updates", "messages"]`，每个 chunk 会带 `(namespace, mode, data)` 元组。

## 7.2 subgraphs=True

默认 stream 只吐**顶层图**的事件；加 `subgraphs=True` 可以收到子图的（namespace 前缀区分来源）：

```python
async for ns, mode, chunk in app.astream(input, config, stream_mode="updates", subgraphs=True):
    print(ns, chunk)     # ns 是类似 ('worker:abc',) 的命名空间路径
```

## 7.3 custom 模式与 get_stream_writer（1.0 写法）

节点里主动往外推事件：

```python
from langgraph.config import get_stream_writer

def my_node(state):
    writer = get_stream_writer()
    writer({"type": "tool_start", "name": "search"})   # 推自定义事件
    ...
```

外面用 `stream_mode="custom"` 接收。这是 1.0 的官方姿势（旧写法是往 state 塞特殊字段 + 自定义 stream handler，已不推荐）。

## 7.4 本项目的流式方案：自建 SSE 层（对比官方流式）

**【本项目结合】** 项目**没有直接用** LangGraph 的 stream API，而是自建了一套 SSE 发射层（`services/sse.py`），核心是 **ContextVar 绑定的发射器**：

```python
# 节点内部直接调用（services/sse.py 提供）
await emit_stage("domain_start", f"{label}：开始处理", domain=domain)   # 阶段事件
await emit_token("正在整理回复…")                                     # 逐 token
```

为什么不用官方流式？项目的设计考量：

1. **事件协议要跨三个阶段统一**：路由阶段（routing）、子图并行阶段（domain_start/tool/domain_done）、总结阶段（逐 token）——官方 `messages` 模式只覆盖"LLM 生成"，业务阶段事件还得靠 custom 模式，两套拼接不如一套自定义协议干净。
2. **前端契约**：SSE 只有四种事件（stage/token/error/done），前端 `sse.js` 一个 `streamSSE()` 通吃全部 AI 端点（协调 Agent、技能树 AI、表达训练——后两者根本不是 LangGraph，也能用同一协议）。
3. **非流式时零开销**：`emit_stage` 在未启用流式时是**空操作**，同一个函数 `run_coordinator_stream` 在非流式场景下行为与 `run_coordinator` 完全一致——官方 stream API 做不到这种"可关闭"。
4. **为什么 SSE 而不是 WebSocket**：单向推送场景，SSE 更轻；且 EventSource 不能自定义请求头（带不了 JWT），所以前端用 `fetch + getReader()` 自己解析（README 有详细说明）。

**经验结论**：LangGraph 的 stream 适合"把图内部过程透出去"；当你的产品需要**统一的多来源事件协议**（LangGraph 的、非 LangGraph 的、纯业务的），自建一层发射器更可控。两者也可以混用：图内用官方 stream 收集，出口再转译成自己的协议。

另一个易错点也值得记：**阶段事件必须在主协程里发，不能丢进 `asyncio.to_thread` 的线程里**——ContextVar 在线程池里的语义不保证（base.py 注释里明确写了）。这是 Python 并发 + 上下文变量的深水区知识。

---

# 第八部分：循环防护与图设计

## 8.1 recursion_limit

图里有循环（agent → tools → agent → ...）就有失控风险：LLM 犯傻反复调同一个工具，无限烧钱。LangGraph 的保险丝是 `recursion_limit`：

```python
config = {"configurable": {...}, "recursion_limit": 25}   # 默认值就是 25
# 计数单位是"超级步"（super-step，一个节点执行一次算一步），不是 LLM 调用次数
# 超限抛出：langgraph.errors.GraphRecursionError
```

注意：**节点内部自己写的 for 循环不计入 recursion_limit**！它只数"图的边走了多少步"。所以手写 ReAct 循环（项目做法）必须自己加轮数上限。

## 8.2 项目的"防循环三闸"

**【本项目结合】** `coordinator/agents/base.py` 顶部三个常量构成三道防线：

```python
MAX_ITERS = 8          # ① 节点内 ReAct 循环上限（业务工具失败重试的轮数）
MAX_ASK_ROUNDS = 3     # ② 一条记录内反问次数上限
MAX_HISTORY = 1 + MAX_ASK_ROUNDS * 3   # ③ 消息窗口 = 首条 instruction + 3 轮×每轮约 3 条 = 10
```

三闸各自的防御目标：

- **① MAX_ITERS 防"工具死循环"**：LLM 反复调一个总失败的工具 → for 循环 8 次后强制返回"处理轮次超限"。
- **② MAX_ASK_ROUNDS 防"反问死循环"**：LLLM 每轮都缺信息、无限反问 → 满 3 轮后**移除 ask_user 工具**（4.2 节讲过），逼它用已有信息降级执行。
- **③ MAX_HISTORY 防"上下文爆炸"**：消息历史读取时窗口截断（保首条 instruction + 最近 9 条），防 token 无限增长。

```python
# ③ 的实现：保留首条 instruction + 最近 MAX_HISTORY-1 条
messages = list(state.get("messages", []))
if len(messages) > MAX_HISTORY:
    messages = messages[:1] + messages[-(MAX_HISTORY - 1):]
```

（技能树侧的截断还要额外处理孤儿 ToolMessage 边界，见 4.3。）

**经验总结成一句**：**LLM 是不可靠的循环条件判断者，所有循环必须有确定性上限**。三闸分别覆盖"工具重试、反问轮数、上下文长度"三个维度，缺一不可——这是手写 Agent 循环（而非依赖框架默认值）换来的完整控制力。

## 8.3 常见图设计模式

| 模式 | 结构 | 例子 |
|------|------|------|
| **线性链** | A → B → C，无循环 | 简单流水线（ETL、翻译） |
| **ReAct 循环** | agent ↔ tools，条件退出 | 工具型 Agent（项目节点内部） |
| **路由分发** | router → 多分支 → 汇聚 | Supervisor、意图分类 |
| **反思循环** | 生成 → 评估 → 不合格回到生成 | 自我修正的写作/代码 Agent |
| **Map-Reduce** | dispatcher → N 并行 worker → merger | 批量处理（Send API） |

设计建议（从项目实践提炼）：

1. **能不用图层面循环就不用**——项目主流程是线性三段，直接用函数编排；图层面的循环留给真正需要 checkpoint 每一步的场景。
2. **粗粒度的边、细粒度的循环**——把 ReAct 塞进一个节点内部，图保持简单，可读性和调试性都更好。
3. **每个分支都要想"失败了去哪"**——项目的 `_run_one_subgraph` 把每个子图的异常捕获成一条 error result，而不是让一个域失败炸掉整次请求（`asyncio.gather(return_exceptions=True)`）。

---

# 第九部分：长期记忆 Store

## 9.1 Checkpointer vs Store：两种"记忆"

这是 LangGraph 里最容易混淆的一对概念：

| | Checkpointer | Store |
|---|---|---|
| 存什么 | 图的执行状态（消息、中间结果） | 任意的键值数据（用户画像、偏好、事实） |
| 隔离单位 | thread（会话） | namespace（任意命名空间，常按用户） |
| 生命周期 | 一段会话 | **跨会话、跨 thread 永久** |
| 类比 | 聊天记录 | 用户档案 |

典型场景：用户三周前说过"我对花生过敏"。今天新开会话问"推荐个菜"——checkpointer 帮不上（新 thread 是空的），得靠 Store 把这条事实跨会话记住。

## 9.2 用法

```python
from langgraph.store.memory import InMemoryStore      # 生产用 PostgresStore
store = InMemoryStore()

# 写：namespace 是层级元组，按用户隔离
store.put(("users", "user_1", "facts"), "fact_001", {"text": "对花生过敏"})

# 搜（语义检索，需要配置 embeddings 才能模糊搜；否则只是按 namespace 列出）
items = store.search(("users", "user_1", "facts"), query="饮食禁忌")

# 接入图：compile 时传 store，节点/工具里通过 get_store() 拿到
app = graph.compile(checkpointer=cp, store=store)
```

节点和工具里都能访问 store；官方的"记忆 Agent"模板就是把"提取记忆 → 写入 store"做成工具让 LLM 自己调用。

## 9.3 项目的现状与差距

**【本项目结合】** 项目目前**没有用 Store**，跨会话上下文是两个土办法：

- **近 5 条记录**（`graph.py` 的 `finalize_record` + `MAX_RECORDS=5`）：每次三阶段走完，把 {用户说的话, 总结} 压进 `state["records"]`，FIFO 保留 5 条，下次作为上下文传给 router。**它的生命周期挂在编排层的内存 dict（`_thread_store`，TTL 30 分钟）上——重启即失**，且只在"同一主会话"内有效。
- **维度/习惯数据本身在数据库里**：查询类子 Agent 需要的"长期信息"（用户等级、打卡记录）直接查业务库，这是正确的做法——业务数据本来就该在库里，不用塞进 Agent 记忆。

如果要升级：把 `records` 挪进 Store（namespace 按 `("users", user_id, "chat_summary")`），就能做到跨会话、跨重启的长期上下文。这是项目 AI 部分最清晰的一个下一步演进方向。

---

# 第十部分：部署与生态

## 10.1 LangGraph Platform / Server

自己 `uvicorn` 跑 `graph.compile()` 的产物，你得到的是一个"进程"；而 LangGraph Platform 提供的是一整套**生产运行时**：

- **Threads API**：会话状态管理外包给 Server（你不用自己持有 MemorySaver）
- **Runs + 任务队列**：异步任务、双文本处理（double-texting：用户在上一条还没跑完时又发一条，平台有现成策略）
- **Cron 定时运行**：定时跑图
- **持久化伸缩**：Postgres checkpointer 开箱即用
- **Stream 中间件**：SSE/WebSocket 出口都给你做好

形态有 LangGraph Cloud（托管）和 Self-hosted（自建，`langgraph-cli`）。**取舍**：平台省运维但绑它的运行时；自托管（项目现在的做法：FastAPI + 自建 SSE + Docker）自由但要自己处理并发、持久化、流式——项目都自己处理了（这就是为什么有了 `services/sse.py`、会话锁、`_thread_store` 这些自研件）。

## 10.2 LangGraph Studio 与 dev server

```bash
pip install langgraph-cli
langgraph dev      # 本地起开发服务器 + 自动打开 Studio
```

Studio 是官方可视化调试器：画图般查看图结构、逐节点看状态流转、测试 thread 的时间旅行。**学习阶段强烈建议玩一下**——把本文第二、三部分的例子丢进去，"超级步"这个抽象会立刻具象化。

## 10.3 LangSmith（可观测性）

```bash
export LANGSMITH_TRACING=true
export LANGSMITH_API_KEY=lsv2_...
```

开了之后，每次图执行（每个节点的输入输出、每次 LLM 调用的完整请求、每个工具调用）都会上报到 LangSmith 的看板，可以按 trace 排查"为什么 LLM 在这轮做了这个决策"。免费额度够个人项目用。项目目前用的是**本地日志 + request_id 贯穿**（`docs/日志系统方案.md`），够用但粒度不如 LangSmith。

## 10.4 prebuilt 组件一览

`langgraph.prebuilt` 里值得知道的东西：`create_react_agent`（完整 Agent）、`ToolNode`（工具执行节点）、`tools_condition`（标准路由函数）、`InjectedState`（状态注入）。还有社区层的 `langgraph-supervisor` / `langgraph-swarm`（多智能体高层封装）。原则：**先懂手写，再用封装**。

---

# 第十一部分：LangChain 进阶

你已会 LangChain 基础，这一部分把"值得往上补"的进阶件过一遍，并给出新旧迁移地图。

## 11.1 LCEL 与 Runnable 体系

`chain = prompt | llm | parser` 这个竖线的本质：每个组件都是 **Runnable**（统一了 `invoke / batch / stream / ainvoke / astream` 五个方法的最小协议），`|` 是 `pipe` 的语法糖。常用件：

```python
from langchain_core.runnables import RunnableLambda, RunnablePassthrough, RunnableParallel

# RunnableLambda：把普通函数变成 Runnable，才能进管道
parse = RunnableLambda(lambda x: x["question"])

# RunnableParallel：一分多路再自动汇合
retrieval = RunnableParallel(
    context=retriever,                        # 查知识库
    question=RunnablePassthrough(),           # 原样透传（占位符技巧）
)

# .assign()：在不动原 dict 的基础上追加键
chain = retrieval.assign(answer=llm_chain)

# batch 并行
results = chain.batch([{"question": "q1"}, {"question": "q2"}])
```

**什么时候用 LCEL，什么时候用 LangGraph？** 经验法则：**无循环、无分支的确定性流水线用 LCEL（更短）；有循环/分支/状态持久化用 LangGraph**。你的毕设 RAG 系统（预处理→嵌入→检索→重排→生成）就是典型的 LCEL 链；Self Grow 的多智能体就是典型的 LangGraph。

## 11.2 消息类型体系（工程细节）

```python
from langchain_core.messages import (
    SystemMessage,      # 系统设定
    HumanMessage,       # 用户输入
    AIMessage,          # 模型回复（可含 .tool_calls）
    ToolMessage,        # 工具结果（必须带 tool_call_id 配对）
    AIMessageChunk,     # 流式分片（可拼接：chunk1 + chunk2）
)
```

进阶点：

- **多模态**：`HumanMessage(content=[{"type": "text", "text": "..."}, {"type": "image_url", "image_url": {"url": "..."}}])`——content 传列表就是多模态格式。
- **AIMessageChunk 可加**：流式场景把 chunks 累加起来还原完整消息（`ai_client.py` 的流式接口就在处理 chunk 的类型差异：`isinstance(chunk, ChatGenerationChunk)`）。
- **消息是"不可变值"**：不要原地修改历史消息（checkpointer 存的是快照），要改就构造新列表。

## 11.3 结构化输出

```python
from pydantic import BaseModel, Field

class Route(BaseModel):
    domain: str = Field(description="action/query/goal/task/habit/reward 之一")
    instruction: str = Field(description="给子 Agent 的具体指令")

router_llm = llm.with_structured_output(Route)   # 强制 JSON Schema
result = router_llm.invoke("用户想记录今天的运动")   # 返回 Route 对象，domain="action"
```

比"在 prompt 里求 LLM 输出 JSON 再手工解析"可靠一个数量级（底层是模型的 function calling / json_schema 模式）。**【本项目结合】** 项目的 router_node 走的也是"LLM 输出结构化路由决策"的路子（自己实现的解析），用 `with_structured_output` 可以更省心。做 RAG 时（你的毕设）对"意图分类 → 检索策略选择"同样适用。

## 11.4 RAG 组件族（呼应你的毕设）

LangChain 里 RAG 的标准件（你毕设里大概率在用，这里给个"全家福"坐标）：

```python
# 文档加载 → 切分 → 嵌入 → 向量库 → 检索器 → 拼 prompt → 生成
from langchain_community.document_loaders import ...       # PDF/Word/CSV loader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import Chroma

splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
chunks = splitter.split_documents(docs)
vs = Chroma.from_documents(chunks, OpenAIEmbeddings())
retriever = vs.as_retriever(search_kwargs={"k": 5})

rag_chain = (
    {"context": retriever | format_docs, "question": RunnablePassthrough()}
    | prompt | llm
)
```

与 LangGraph 的结合点：**RAG 也能图化**——"检索 → 相关性自检（不相关就改写 query 重检索）→ 生成"就是典型的反思循环图。这是你毕设（混合检索 + 重排）之后可以讲的高级演进方向。

## 11.5 新旧迁移地图（避坑老教程）

| 旧（已弃用/弃用中） | 新 |
|---|---|
| `initialize_agent` / `AgentExecutor` | LangGraph（create_react_agent 或手写） |
| `ConversationBufferMemory` 系列 | LangGraph **Checkpointer** |
| `create_tool_calling_agent` | 同上 |
| `LLMChain` / `ConversationChain` | LCEL 管道 |
| `CallbackHandler` 手搓追踪 | LangSmith |

看到教程用 Memory / AgentExecutor，心里要翻译成对应新概念。

## 11.6 ChatOpenAI 的工程参数（项目踩过坑的）

```python
ChatOpenAI(
    model="qwen3",
    temperature=0.3,
    max_tokens=4096,        # 推理模型的 max_tokens 含思考部分，给太小正文会被截断
    timeout=300,            # 显式超时！httpx 默认 5s，慢网关下会静默重试放大延迟
    max_retries=0,          # 生成类任务重试收益低（重试=再等一轮），项目统一关闭
)
```

**【本项目踩坑】** `services/ai_client.py` 的注释记录了完整教训：不设 `request_timeout` 时 httpx 默认 5 秒，网关慢的时候底层静默重试，用户感知就是"等了 N 倍时间"。**超时和重试永远是成对显式配置的**，默认值是坑。

## 11.7 多模型热切换（项目实现）

**【本项目结合】** 项目支持运行时切换模型（用户中心改配置即时生效），实现是"带失效键的实例缓存"：

```python
# services/llm.py（节选）
_llm_cache: dict[tuple, ChatOpenAI] = {}

def get_llm(temperature=0.3, user_id=None) -> ChatOpenAI:
    cfg = get_active_config(user_id or 1, "llm")        # 读数据库里启用的模型配置
    cache_key = (temperature, model, base_url, api_key)  # 参数变 = key 变
    if cache_key not in _llm_cache:
        _llm_cache[cache_key] = ChatOpenAI(...)          # 自动重建
    return _llm_cache[cache_key]
```

所有 AI 模块（协调 Agent、技能树、表达训练）都通过 `get_llm()` 取实例——一处缓存、处处生效。这是"LCEL/LangGraph 都不管、但工程上必须有人管"的典型问题。

---

# 第十二部分：知识地图自检

下面这张表 = LangGraph 的知识全景。**右边打勾的是本项目用到的**——建议对照自检：左边概念能讲清楚吗？右边项目能定位到代码吗？

| # | 知识点 | 本项目对应 |
|---|--------|-----------|
| 1 | StateGraph / State / TypedDict | `SkillTreeChatState`、各子图 State |
| 2 | Reducer（operator.add / add_messages / 自定义） | ✅ messages 累积 + diffs 刻意不累积 |
| 3 | Annotated 挂 reducer | ✅ `state.py` |
| 4 | 节点（函数 / Runnable / 子图） | ✅ make_agent_node |
| 5 | 普通边 / 条件边 / START / END | 子图是直通图（无条件边——刻意的） |
| 6 | compile（checkpointer/store/interrupt 参数） | ✅ compile(checkpointer=...) |
| 7 | invoke / ainvoke / stream / batch | ✅ ainvoke 为主 |
| 8 | config：thread_id / recursion_limit / tags | ✅ thread_id 体系 |
| 9 | MemorySaver / SqliteSaver / PostgresSaver | ✅ MemorySaver 全局单例（知其局限） |
| 10 | thread_id 会话隔离 | ✅ `{main}:{domain}` 双层命名 |
| 11 | get_state / aget_state / StateSnapshot | ✅ resume 前读 pending_confirmation |
| 12 | get_state_history / 时间旅行 | 未用（知道即可） |
| 13 | update_state | 未用 |
| 14 | @tool / docstring schema / Literal 枚举 | ✅（MCP 工具重度使用） |
| 15 | bind_tools / tool_calls | ✅ 含动态移除工具降级 |
| 16 | ToolMessage / tool_call_id 配对 | ✅ 踩过孤儿 ToolMessage 的坑 |
| 17 | create_react_agent / ToolNode / tools_condition | 知道但刻意不用（要定制退出条件） |
| 18 | InjectedState / InjectedToolArg | ✅ 技能树工具注入 state |
| 19 | interrupt() / interrupt_before / NodeInterrupt | 知道，评估后未用（见 §5.3） |
| 20 | Command（resume/goto/update） | 知道 |
| 21 | 人机协同两种路线（挂起 vs 回灌） | ✅ 自建 ask_user + 消息回灌 |
| 22 | Supervisor / 层级 / Swarm 拓扑 | ✅ Supervisor 变体（三段式） |
| 23 | 子图作为节点 | ✅ 变体：编排层直接 ainvoke 子图 |
| 24 | Send API（动态并行） | 用 asyncio.gather 实现同语义 |
| 25 | stream_mode 五种 | 自建 SSE 层（知其原因） |
| 26 | subgraphs=True | 知道 |
| 27 | get_stream_writer（custom 事件） | 知道，用 ContextVar emitter 替代 |
| 28 | recursion_limit / GraphRecursionError | ✅ 三闸防护（节点内循环另设上限） |
| 29 | Store（跨会话长期记忆） | 未用（演进方向明确） |
| 30 | LangGraph Platform / Server / Studio / LangSmith | 自部署路线（知取舍） |
| 31 | LCEL / Runnable / Parallel / batch | 知道边界：无循环用 LCEL |
| 32 | with_structured_output | router 自实现解析 |
| 33 | RAG 组件族 | （毕设主场） |
| 34 | 新旧迁移（AgentExecutor→LG 等） | 全部按新范式写 |

覆盖度自查方法：把没打 ✅ 的行挑出来，能对着本文相应章节讲 3 分钟，就算过关。

---

# 附录 A：本项目 LangGraph 文件地图

```
backend/services/
├── coordinator/                    # 统一协调 Agent（Supervisor 变体）
│   ├── graph.py                    # ★ 三段式主编排（不用 StateGraph，原因见 §2.2）
│   ├── router_node.py              # 阶段一：LLM 路由决策
│   ├── synthesize_node.py          # 阶段三：汇总生成最终回复（支持逐 token）
│   ├── checkpointer.py             # 全局 MemorySaver 单例（§3.2）
│   ├── llm.py → (统一到 services/llm.py)  # 动态 LLM 实例缓存（§11.7）
│   └── agents/
│       ├── __init__.py             # SUBGRAPH_BUILDERS 域→工厂注册表
│       ├── base.py                 # ★ make_agent_node + build_subgraph（§4.4 §8.2）
│       ├── ask_user_tool.py        # ask_user 反问工具（§5.3）
│       └── action_agent.py 等 6 个  # 各域的 create_xxx_agent 工厂
│
├── skill_tree_ai/                  # 技能树 AI 编辑（单 Agent 图）
│   ├── graph.py                    # ★ 图编译 + run/resume + aget_state 读确认（§3.4）
│   ├── node.py                     # ★ ReAct 循环 + 消息截断防孤儿（§4.3）
│   ├── state.py                    # ★ SkillTreeChatState（reucer 正反例 §2.2）
│   ├── tools.py                    # 9 个工具 + InjectedState + 危险操作守卫
│   └── prompts.py                  # 系统提示词 + 树状态动态注入
│
├── sse.py                          # 自建流式层（ContextVar emitter，§7.4）
└── llm.py                          # 多模型热切换缓存（§11.7）
```

# 附录 B：面试高频问答

**Q1：LangGraph 和 LangChain 什么关系？**
LangChain 管的是"单步"的组件（模型、工具、prompt）；LangGraph 管"多步"的编排（状态、循环、持久化）。官方已把 Agent/Memory 的未来押在 LangGraph 上，旧 AgentExecutor 弃用。

**Q2：reducer 是什么？为什么重要？**
节点返回的状态怎么合并进当前状态。默认覆盖；`Annotated[list, operator.add]` 改为追加。重要性：多轮会话里"该累积的字段"（消息历史）和"该覆盖的字段"（单次结果）必须区分，否则跨轮重复累积——本项目主流程退出 StateGraph 的直接原因（能讲出具体场景，秒杀背概念的候选人）。

**Q3：checkpointer 的 thread_id 怎么设计？**
按"会话线"隔离。项目两层：主会话一层、每个域子图一层（`{main}:{domain}`），保证域间互不污染、域内跨轮连续。

**Q4：怎么实现"Agent 中途问用户"？**
两条路：官方 `interrupt()` 挂起 + `Command(resume=...)`；或"反问工具 + 子图正常结束 + 回答作为新消息回灌重跑"。项目选后者，理由：问题作为普通消息天然持久化、跳过零成本、单一状态源。

**Q5：消息历史变长怎么办？**
窗口截断，且截断边界必须对齐"完整对话轮"（不能切断 AIMessage(tool_calls) 和 ToolMessage 的配对，否则 400）。保留首条（系统级 instruction）+ 最近 N 条。

**Q6：怎么防止 Agent 死循环？**
三层：图层面 recursion_limit（默认 25）；节点内 for 循环上限；语义层面反问轮数上限 + 超限动态移除工具逼降级。核心思想：LLM 不可靠，循环条件必须有确定性上限。

**Q7：多 Agent 并行你怎么做的？**
编排层 `asyncio.gather` 并行 ainvoke 各域子图，`return_exceptions=True` 错误隔离，每个分支前后推 SSE 阶段事件。对比 Send API：图层面 fan-out 由框架管理（可視化友好），代码层面并行更灵活（可插自定义事件、错误策略）。

**Q8：MemorySaver 能上生产吗？**
不能持久化（重启丢）。但它是接口兼容的，换 SqliteSaver/PostgresSaver 业务代码零改动。项目当前用 MemorySaver 是已知取舍（单实例部署、重启后新开会话可接受），记在"已知限制"里。

**Q9：流式输出怎么做的？**
没直接用 LangGraph stream，自建 SSE 层：ContextVar 绑定发射器，节点里 emit_stage/emit_token，非流式时是空操作。理由：需要跨三个阶段统一事件协议，且同一协议要服务非 LangGraph 的 AI 端点。

**Q10：如果要加"长期记忆"，你怎么改？**
引入 Store（namespace 按 user_id），把现在挂在内存编排层的 records（近 5 条、TTL 30min、重启丢）迁进去；业务数据（等级/打卡）继续走数据库，不进 Agent 记忆。

---

> **结语**：LangGraph 的学习曲线不在 API（一天就能上手），而在**状态设计的判断力**——哪个字段累积、哪个覆盖；循环放图上还是节点里；用 interrupt 还是消息回灌；用官方流式还是自建事件层。这些判断，本文每一处【本项目结合】都是真实做过的决定。把第十二部分的表格过一遍，能对答如流，你就不只是"用过 LangGraph"，而是"设计过 LangGraph 系统"。
