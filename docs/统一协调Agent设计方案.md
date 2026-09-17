# 统一协调 Agent（Coordinator Agent）设计与实现

> 项目：Self Grow 个人成长系统
> 文档状态：**已落地实现**（v4）。本文同时保留历史设计决策，供对照。
> 最后核实：2026-09-04，逐项对照 `backend/services/coordinator/` 与 `frontend/js/chat.js`

---

## 0. 设计稿 vs 实际实现 · 差异速查

原始设计方案写于实现之前，落地时有多处偏离。**以本表右列为准。**

| 设计项 | v3 设计稿 | **v4 实际实现** | 偏离原因 |
|---|---|---|---|
| 主流程编排 | LangGraph StateGraph | **三段式线性编排**（普通 async 函数） | 主流程无分支/循环，`operator.add` 会跨轮累积消息 |
| 子图编排 | `create_react_agent` | **StateGraph 单节点 + 自研 ReAct 循环** | 需要窗口截断与反问降级，`create_react_agent` 管不了 |
| 反问机制 | `interrupt()` + `Command(resume)` | **`ask_user` 工具 + `needs_user` 标志 + resume 追加消息** | 见 §3.2，三条理由 |
| 意图路由 | 正则 + 关键词，LLM 兜底 | **全部 LLM 语义判断** | 关键词维护成本高，LLM 足够快 |
| 领域构成 | action / habit / task / query / skill_tree / expression | **action / query / goal / task / habit / reward** | 技能树、表达训练未纳入协调层 |
| 会话持久化 | SQLite checkpoint | **`MemorySaver`（内存）** | 见 §7 技术债 |
| 主图上下文 | LangGraph checkpoint | **近 5 条记录 FIFO（内存 dict，TTL 30 分钟）** | 够用且可控 |
| 前端传输 | SSE 推送中断事件 | **POST + `fetch` 读 SSE 流**（反问仍用 interruptQueue 队列） | ✅ 2026-09-16 已改为真流式，见 §6.2 |
| 写操作确认 | interrupt 确认卡片 | **未实现** | 当前直接写库 |
| 依赖声明 | `pyproject.toml` | **`pixi.toml`** | 项目实际用 pixi 管理 |
| 前端文件 | `frontend/js/pages/coordinator.js` | **`frontend/js/chat.js`（472 行）** | 命名调整 |

---

## 1. 背景与目标

### 1.1 现状痛点

系统原本是「多表单孤岛」：行动记录、习惯打卡、任务、技能树、表达训练各有独立入口，用户想完成一件事必须先**找到正确的页面 → 找对表单 → 逐项填写**。

### 1.2 解决方案

装一个**统一协调 Agent**：用户用自然语言输入，主 Agent 理解意图并调度，对应领域的子 Agent 完成操作。

```
打开行动页 → 选维度"健康" → 选子类型"运动" → 填时长"30" → 填备注 → 提交     ← 原来
输入："我下午跑了半小时步" → 自动写库 + 返回 "+15 EXP，健康维度"              ← 现在
```

### 1.3 面试叙事版本（已按实现校准）

> **我做了一个基于 Tool-Use 的多智能体协调系统：主 Agent 用 LLM 做语义路由，为命中的每个领域动态生成定制指令；6 个领域子 Agent 并行执行，各自通过 checkpointer 维护独立会话，缺参数时通过工具级反问接回原上下文继续。**

四层递进的技术亮点：

1. **编排分层**：主流程是线性的，就不用状态图；子 Agent 内部有循环，才用 LangGraph 状态图。按形状选工具，而不是一律上框架。
2. **反问机制的取舍**：主动放弃框架原生的 `interrupt()`，选择"反问即正常结束 + 消息追加恢复"，换来单一状态源和零成本放弃。
3. **防失控设计**：ReAct 循环上限、反问轮次上限（超限自动移除反问工具降级）、消息窗口截断，三道闸。
4. **产品 sense**：理解"用户不填表单，用户说话"。

---

## 2. 核心架构（v4 实际实现）

### 2.1 三段式主流程

`services/coordinator/graph.py` 的 `run_coordinator()` 是**普通 async 函数**，不是 StateGraph：

```
用户输入
  ▼
阶段一  router_node        LLM 语义路由 → pending_tasks（含每域定制指令）
  ▼
阶段二  dispatch_subgraphs  asyncio.gather 并行派发各子图
  ▼
阶段三  synthesize_node     （仅当全部域完成）整合所有结果生成一句回复
```

**为什么主流程不用 StateGraph？**

主流程是线性的三段，没有分支、没有循环。`StateGraph` 默认的 `operator.add` 状态合并语义会把每次节点的返回值**追加**累积，多轮对话下 `messages` 会无限膨胀。用普通 async 函数编排，状态完全可控。

**LangGraph 用在哪？** 子 Agent 内部的 ReAct 循环 + 会话持久化——那里确实有循环和状态需求。见 §4。

### 2.2 六域子图

`services/coordinator/agents/` 下 6 个域，由 `SUBGRAPH_BUILDERS` 统一注册：

| 域 | 文件 | 职责 |
|---|---|---|
| `action` | `action_agent.py` | 行动记录与经验结算 |
| `query` | `query_agent.py` | 只读统计查询 |
| `goal` | `goal_agent.py` | 目标与里程碑 |
| `task` | `task_agent.py` | 任务增删改与领取奖励 |
| `habit` | `habit_agent.py` | 习惯创建与打卡 |
| `reward` | `reward_agent.py` | 奖励商城与兑换 |

> 技能树（`services/skill_tree_ai/`）和表达训练（`services/expression_service.py`）**未纳入协调层**，仍走各自的独立链路。

### 2.3 thread_id 设计

- 主会话：`thread_id`（UUID，前端 sessionStorage 持久化）
- 子图会话：`{main_thread_id}:{domain}`

主会话与每个子域各有独立 checkpoint，多域并行时消息互不污染。路由层用 `sub_thread_id.split(":")[-1]` 反解域名。

---

## 3. 关键设计

### 3.1 路由：全部交给 LLM

`router_node.py` 的 docstring 第一句就写明「**全部使用 LLM 语义判断路由，取消正则+关键词路由**」。

- 温度 `temperature=0.1`，追求稳定
- 输入 = 用户消息 + 近 5 条历史记录（用户消息 + 主 agent 总结），用于判断"是延续还是新任务"
- 输出 = 结构化路由决策（域名 + 理由 + **为该域动态生成的定制指令**）

**JSON 解析三级降级**（LLM 经常夹带解释文本）：

```python
1. 去掉 markdown 代码块围栏          # ```json ... ```
2. json.loads(cleaned)              # 直接解析
3. 正则提取最外层 { ... } 再解析      # _JSON_OBJECT_RE
全部失败 → 返回空 pending_tasks（不派发，不报错）
```

**动态定制指令是核心**：主 Agent 不只是说"交给行动域"，而是根据整个对话历史，为子图写一份包含维度、可能缺的参数、用户表述习惯的专用指令。所以子图不需要读全部历史。

### 3.2 反问：为什么不用 `interrupt()`

**这是本项目最值得讲的一个决策。**

LangGraph 原生支持 human-in-the-loop，按理说子图缺参数时直接 `interrupt()` 最省事。实现时主动放弃，改成了：

```
LLM 调用 ask_user 工具
  ▼
子图把问题写成 ToolMessage 持久化进 checkpoint
  ▼
返回 result.needs_user = True，子图【正常结束】，不挂起
  ▼
前端渲染反问卡片（push 进 interruptQueue）
  ▼
用户回答 → POST /api/coordinator/resume { sub_thread_id, answer }
  ▼
resume_subgraph 把回答作为 HumanMessage 追加到【该子图的 checkpoint】
  ▼
重新 ainvoke —— LLM 在完整上下文（instruction + 反问 + 回答）中继续
```

**三条理由**（见 `agents/base.py` 模块 docstring）：

| 维度 | `interrupt()` 方案 | 本项目的 ask_user 方案 |
|---|---|---|
| 状态源 | 挂起状态 + 额外线程存储 | checkpointer 单一状态源 |
| 放弃成本 | 需处理各种 resume 分支 | 无需处理，零成本 |
| 问题留存 | 需自行管理 | 作为普通消息持久化，resume 时不丢、不重问 |

**`interrupt()` 适合什么场景？** 人工审批那种强阻塞的 human-in-the-loop 流程。本项目是"补个参数"，用户随时可能放弃，挂起反而是负担。

### 3.3 防失控：三道闸

`agents/base.py` 顶部三个常量，是这套系统敢放 LLM 自己跑的前提：

| 闸门 | 常量 | 值 | 行为 |
|---|---|---|---|
| ReAct 循环上限 | `MAX_ITERS` | 8 | 工具失败重试不超过 8 轮 |
| 反问轮次上限 | `MAX_ASK_ROUNDS` | 3 | 超过 3 轮**把 `ask_user` 从 `bind_tools` 里移除**，逼 LLM 用已有信息执行或直接放弃 |
| 消息窗口 | `MAX_HISTORY` | 10 | 保留首条 instruction + 最近 9 条，`1 + MAX_ASK_ROUNDS * 3` |

反问超限降级还留了保险分支：万一 LLM 仍然调用了已被移除的 `ask_user`，工具返回"信息不足，本次放弃"的失败结果，而不是真的再问一轮。

### 3.4 主 Agent 上下文

`finalize_record()` 维护近 5 条记录的 FIFO：

- **压入时机**：仅当三阶段全部走完（`final_reply` 非空）。有 pending 反问时 `final_reply` 为空 → 不压入
- **存储内容**：`{用户说的话, 主 agent 总结}`——不是原始对话，是压缩后的摘要

设计意图：主 Agent 只需要知道"最近做过什么"来判断本次是否延续，不需要背完整历史。

---

## 4. 技术选型与演进

### 4.1 LangGraph 用在哪、没用在哪

| 位置 | 是否用 LangGraph | 理由 |
|---|---|---|
| 主流程编排 | ❌ | 线性三段，用普通 async 函数更可控 |
| 子图 ReAct 循环 | ✅ | 有循环、需要状态合并 |
| 会话持久化 | ✅ `checkpointer` | 按 `sub_thread_id` 隔离各子域会话 |
| 反问机制 | ❌ | 见 §3.2 |

**子图结构**（`build_subgraph`）：单节点 StateGraph + 全局 `MemorySaver`，入口即出口。

```python
graph = StateGraph(state_class)
graph.add_node("agent", make_agent_node(tools, domain, domain_label, system_prompt))
graph.set_entry_point("agent")
graph.add_edge("agent", END)
return graph.compile(checkpointer=get_checkpointer())
```

**为什么不用 `create_react_agent`？** 需要在循环内做两件框架管不了的事：消息窗口截断、反问轮次超限后动态摘除工具。自研循环约 120 行，换来完全的控制权。

### 4.2 工具参数约束

工具层做了三层防护，防止 LLM 乱传参：

1. **类型约束**：`@tool` 装饰器 + 类型注解自动生成 JSON Schema；`user_id` 由 `agent_node` 统一注入（`args["user_id"] = state.get("user_id")`），不让模型自己填
2. **异常兜底**：工具执行包 try/catch，异常转成 `{"success": false, "message": ...}` 回灌给 LLM，让它自己重试或换参数，而不是整条链路崩掉
3. **并行隔离**：各子图用 `asyncio.gather(..., return_exceptions=True)` 派发，单域失败不影响其他域，失败结果以 `{error: true}` 参与最终汇总

### 4.3 依赖

`backend/pixi.toml`：

```toml
langgraph = ">=0.2.0"
langchain-openai = ">=1.3.5,<2"
langchain-core = ">=0.3.0"
```

---

## 5. 落地文件清单（实际）

| 层 | 文件 | 内容 |
|---|---|---|
| 编排 | `services/coordinator/graph.py` | 三段式主编排 `run_coordinator` / `resume_subgraph` |
| 路由 | `services/coordinator/router_node.py` | LLM 语义路由 + JSON 三级降级解析 |
| 汇总 | `services/coordinator/synthesize_node.py` | 多域结果整合 |
| 状态 | `services/coordinator/state.py` | `CoordinatorState` / `SubgraphTask` |
| 持久化 | `services/coordinator/checkpointer.py` | 全局 `MemorySaver` 单例 |
| LLM | `services/coordinator/llm.py` | 多模型热切换（四元组缓存 key） |
| 子图基座 | `services/coordinator/agents/base.py` | ReAct 循环 + 反问 + 防失控三闸 |
| 子图 | `services/coordinator/agents/{action,query,goal,task,habit,reward}_agent.py` | 6 个域 |
| 提示词 | `backend/prompts/coordinator.py` | 路由系统提示词 + 各域子图提示词 |
| 接口 | `routers/coordinator.py` | 4 个端点，见 §6 |
| 前端 | `frontend/js/chat.js` | 对话面板 + interruptQueue + 反问卡片 |

---

## 6. 接口与前端交互

### 6.1 四个端点

| 方法 | 路径 | 用途 | 用户校验 |
|---|---|---|---|
| POST | `/api/coordinator/chat` | 发送消息：路由 → 并行派发 →（全部完成时）总结 | `get_current_user` |
| POST | `/api/coordinator/resume` | 回答反问：接回指定子图继续，**不重新路由** | `get_current_user` + 归属校验 |
| ~~GET~~ | ~~`/api/coordinator/stream/{thread_id}`~~ | **已删除**（占位且无鉴权；`/chat` 本身已流式） | — |
| ~~GET~~ | ~~`/api/coordinator/status/{thread_id}`~~ | **已删除**（2026-09-17，零调用方；要看编排过程直接看 `/chat` 的 SSE 流） | — |

> ✅ **2026-09-16**：`/chat` 与 `/resume` 已改为 **SSE 流式** —— 推阶段事件
> （routing / 每个子 Agent 的起止 / 工具执行）+ 协调 Agent 的总结**逐 token** 输出。
> `done` 事件里携带的字段与改造前完全一致，前端只改了「怎么读」没改「怎么处理」。

> ⚠️ **注意：`get_current_user` 不是真正的身份认证。** 它的实现（`routers/deps.py`）只是校验 URL 上的 `user_id` 参数是否存在于 users 表：

```python
async def get_current_user(user_id: int = Query(...)):
    user = get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    return user
```

> `user_id` 来自 query 字符串，客户端可任意指定。`resume` / `status` 里的 `state["user_id"] != user["id"] → 403` 归属校验，同样因为 `user_id` 可被伪造而**形同虚设**——攻击者只需传正确的 `user_id` 即可通过。**这是整个项目最严重的安全缺口**，改进方向是 JWT/session 鉴权。

**`resume` 的幂等保护**：若该域已完成且无待处理反问，直接返回当前状态，不重复执行。

**`resume` 的会话锁（2026-09-16 新增）**：同一 `thread_id` 同时只允许一个写请求，
冲突返回 **409**。

- 起因：`/resume` 是「读 state → await 子图 → 写 state」，两次并发请求会在 await 点
  交错，双方都读到「该域还没完成」→ **子图被重复执行**。实测（单域场景连点两次发送）
  `results` 变成 2 条、子图跑了两次。写库型工具会重复写入（连点发送 = 创建两个任务）
- 为什么必须在服务端做：前端防抖只能挡「手滑连点」，挡不住重试、多标签页、脚本调用
- 占用时机：**返回流式响应之前**（否则拿不到干净的 409 状态码）；
  释放在 runner 的 `finally` 里（`StreamingResponse` 是「返回即开始」，
  在端点里释放等于业务还没跑就把锁丢了）。客户端中途断开也会走 `finally`，不会锁死会话
- 配套：前端把多个回答**排队串行提交**（见 §6.2），所以正常操作不会撞到 409

**`resume` 的 `skip` 语义（2026-09-16 新增）**：`skip: true` 表示用户跳过这个提问 ——
**不重新执行子图**，直接把这个域标记为已完成。

- 必须显式告诉后端：跳过的域如果永远完不成，`pending_domains ⊆ completed_domains`
  恒不成立 → **这条记录的总结永远不会生成**（改造前前端只删本地卡片，就是这个结果）
- 不重跑子图也有实际好处：用户没给信息，再问一遍也问不出来，省一次 LLM 调用，
  也避免子 Agent 拿不到信息硬猜着去写库

### 6.2 前端（`frontend/js/chat.js`）

- **走 SSE 流式**（2026-09-16 改造）：`fetch` + `resp.body.getReader()` 读事件流
  —— 阶段事件渲染成进度列表，`token` 事件逐字追加，`done` 里的 `reply` 覆盖已渲染文本
  （服务端中途出错会降级成规则拼接，所以 done 才是权威值）
- ⚠️ **不能用原生 `EventSource`**：它不能自定义请求头，而身份是 `js/auth.js`
  包装 `fetch` 注入的 `Authorization: Bearer`，用 EventSource 必然 401
- `thread_id` 存 `sessionStorage`（key：`self_grow_coordinator_thread_id`）——刷新不丢，关闭浏览器才丢
- 恢复时携带 `sub_thread_id`，精确指定恢复哪个子图

**反问卡片的提交逻辑（2026-09-16 重写）**

一次消息可能路由到多个域，**两个反问一同到达是常态**。改造前用单个 `isLoading`
全局开关挡住第二次提交，结果是：

| 问题 | 后果 |
|---|---|
| `if (this.isLoading) return` | 用户在 B 卡片里提交 → **静默无反应**（不报错、不提示），只能反复点 |
| 绕过前端直接并发 | 后端子图重复执行 → 写库型工具重复写入 |
| `_refreshInterruptArea()` 里 `innerHTML = ''` | 提交 A 会把 **B 卡片里已输入的内容清空** |
| `skipInterrupt` 只删本地卡片 | 后端不知道该域已放弃 → 总结永远为空 |

现在的做法：

1. **串行队列**：`resumeInterrupt` / `skipInterrupt` 只把任务推入 `_answerJobs`，
   由 `_drainAnswers()` 单飞循环逐个发 —— 天然不会并发撞 409
2. **状态即防抖**：`_interruptStatus[id]` 在第一次点击时**同步**置为 `queued`，
   后续点击（连点、Enter 连按）在入口检查处被忽略。比定时器防抖可靠 ——
   定时器窗口之外仍可能漏
3. **草稿保留**：重渲染前先 `_captureInterruptDrafts()`，输入框实时写回草稿 map，
   重建后回填。提交 A 不会再清掉 B 里打的字
4. **排队/提交中有明确反馈**：卡片降透明度 + 状态行「排队中…／正在提交…」+
   按钮禁用（改造前是毫无反馈）
5. **失败可重试**：请求失败时卡片**留在原地**、状态清除、输入内容还回去
   （`delete this._interruptStatus[id]` —— 不能赋 `'idle'`，卡片判断用的是
   `busy = !!status`，任何真值都会被当成忙）
6. **进场动画**：卡片首次出现时淡入 + 轻微上移，两张错开 70ms；
   用 `_interruptAnimated` 记标记，重渲染不重播

配套测试：`frontend/tests/interrupt-submit.test.mjs`（Node + 极简假 DOM，
不开浏览器、零依赖，7 组场景）。**这个测试当场抓到了上面第 5 点的 `'idle'` 真值 bug。**

### 6.3 编排状态存储

`routers/coordinator.py` 用进程内 dict：

```python
_THREAD_TTL_SECONDS = 30 * 60   # 30 分钟
_thread_store: dict[str, dict] = {}
```

写入时打过期时间戳，读取时判过期并删除，**活跃访问自动续期**。

> ⚠️ 这是内存存储，进程重启即失、多实例不共享。见 §7。

---

## 7. 已知限制与技术债

按优先级排列，面试时主动说出来比被问出来好：

| # | 问题 | 影响 | 改进方向 |
|---|---|---|---|
| 1 | 编排状态 `_thread_store` 在进程内存 | 重启丢失、多实例不共享 | 迁 Redis，或落库 |
| 2 | checkpointer 用 `MemorySaver` | 重启后所有子图会话历史丢失 | 换 `AsyncSqliteSaver` / `PostgresSaver` |
| 3 | ~~子图工具同步调用~~ **✅ 已修复**（2026-09-08） | 原 `tool_fn.invoke(args)` 在 async 节点里阻塞事件循环，`gather` 的"并行"实际串行 | 已改为 `await asyncio.to_thread(tool_fn.invoke, args)` 丢线程池 |
| 4 | ~~SSE 端点未实装且无鉴权~~ **✅ 已修复**（2026-09-16） | 原 `GET /stream/{thread_id}` 只发一条 `done` 且**没挂鉴权**（知道 thread_id 就能查） | 已删除；`/chat` 与 `/resume` 改为真流式并带鉴权 |
| 5 | 写操作确认流未实现 | AI 直接写库，无二次确认 | 写库前用 `ask_user` 发起确认（机制已具备，加提示词即可） |
| 6 | 领域覆盖不全 | 技能树、表达训练未纳入协调层 | 各加一个子图 |
| 7 | **无真正身份认证** | `get_current_user` 只校验 user_id 存在，可被伪造；越权读取/篡改他人数据 | 引入 JWT/session 鉴权（见 §6.1） |

---

## 8. 面试讲解对照表（已按实现校准）

| 面试官可能问 | 怎么答 |
|---|---|
| 做过什么 AI 相关 | "基于 LangGraph 的多智能体协调系统，主流程三段式编排，6 个领域子 Agent 并行" |
| 为什么主流程不用 StateGraph | "主流程是线性的三段，没有分支和循环。StateGraph 的 operator.add 会跨轮累积，多轮对话下消息会膨胀。只有子 Agent 内部的循环才用状态图" |
| 反问为什么不用 interrupt | "interrupt 适合强阻塞的人工审批。我这个是补参数，用户随时会放弃。改成反问即结束 + 消息追加恢复，换来单一状态源、零成本放弃、问题不丢不重问" |
| 怎么防 LLM 失控 | "三道闸：循环上限 8 轮、反问上限 3 轮（超限摘掉反问工具逼它降级）、消息窗口截断到 10 条" |
| 多智能体怎么分工 | "主 Agent 做语义路由，并为每个命中的域动态生成定制指令；子图只吃这份指令，不需要读全量历史" |
| 多域并行怎么做 | "asyncio.gather 派发，单个域失败用 return_exceptions 兜住，失败结果照常参与最终汇总" |
| thread_id 怎么设计 | "主会话 UUID，子图会话是 {主ID}:{域名}，各自独立 checkpoint，并行时消息不串味" |
| AI 会不会乱写库 | "只决定调哪个工具传什么参数，写库统一走业务层；user_id 由工具层注入不让模型填；工具异常转成失败结果回灌给模型自愈" |
| 有什么不足 | "编排状态和 checkpointer 都在内存，重启即失；子图工具是同步调用，并行实际会串行；写操作还没做二次确认" |

---

## 附录 A：历史设计稿（v3，部分已废弃）

以下内容为早期设计，**仅供对照，实现请以正文为准**：

- ❌ 主流程用 StateGraph —— 已改为三段式线性编排
- ❌ 用 `interrupt()` + `Command(resume)` 实现反问 —— 已改为 ask_user 工具方案
- ❌ 路由用正则 + 关键词 —— 已改为全 LLM 语义判断
- ❌ 领域含 skill_tree / expression —— 实际为 goal / reward
- ❌ 依赖写在 `pyproject.toml` —— 实际在 `pixi.toml`
- ❌ 前端用 SSE 推送中断事件 —— ~~实际为 POST 同步~~ ✅ 2026-09-16 起为 POST + SSE 流；
  中断仍走前端 `interruptQueue` 队列（这是有意的：反问卡片需要支持「跳过/放弃」，
  用队列比用挂起状态灵活）
- ⏸ 写操作确认流 —— 未实现

原始工具 Schema 草稿（`route_to` / `record_action` / `set_habit_checkin` / `query_global_stats` / `ask_user`）已被 `@tool` 装饰器自动生成的 Schema 取代，不再单独维护。

---

*文档结束。当前实现位于 `backend/services/coordinator/`，核心是 `graph.py`（三段式编排）+ `agents/base.py`（子图基座与防失控三闸）。*
