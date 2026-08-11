# 统一协调 Agent（Coordinator Agent）设计方案

> 项目：Self Grow 个人成长系统
> 文档状态：设计方案（含落地指引）
> 关联文档：[前端浏览器缓存与存储详解](./前端浏览器缓存与存储详解.md) · [数据库知识深入学习指南](./数据库知识深入学习指南.md)

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

### 1.2 候选 A 定义

给整个系统装一个 **统一协调 Agent**：用户用自然语言在侧边栏输入，Agent 先理解意图，再**自动调对应模块的工具**完成操作，并返回结果。

例如，同样是记一笔行动，原来是：

```
打开行动页 → 选维度"健康" → 选子类型"运动" → 填时长"30" → 填备注 → 提交
```

现在是：

```
输入："我下午跑了半小时步"
→ Agent 识别 [记录行动] → 自动调 record_action 工具 → 返回"+15 EXP，健康维度"
```

### 1.3 面试叙事版本

> **我构建了一个基于 Tool-Use 的统一智能体网关，让用户用自然语言操作整个系统的 8+ 个数据域，AI 负责意图识别与跨域工具调度。**

四层递进的技术亮点：
1. **Tool-Use 工程**：手动实现 OpenAI 式多工具轮询协议，非简单调 API。
2. **跨域调度架构**：从 3 个单域 Agent 抽象出统一协调网关，把重复代码升级为通用能力。
3. **工程权衡**：关键词轻量分类做意图预判 + 模糊指令交给 AI，省 token 且保灵活。
4. **产品 sense**：理解"用户不填表单，用户说话"。

---

## 2. 项目现状盘点（可复用资产）

这是候选 A 最大的优势——**不需要从零搭基础设施**。项目中已有 3 套成熟的 Tool-Use 引擎在运行：

| 引擎 | 文件 | 现状 | 借鉴点 |
|------|------|------|--------|
| 技能树 AI | `backend/services/ai_service.py` + `backend/prompts/skill_tree.py` | 9 个工具，`tool_choice:auto` 多工具轮询 | 最完整的多工具循环 |
| 行动解析 AI | `backend/services/ai_action_service.py` + `backend/prompts/action_parse.py` | 对话提取行动 + `submit_actions` 批量提交 | 意图解析 + 精确计分规则提示词 |
| 表达训练 AI | `backend/services/expression_service.py` 的 `_call_llm_with_tools` | 分轮执行工具（查重 + 生成），170-266 行 | 轮询循环 + 容错 + JSON 解析骨架 |

### 2.1 核心技术循环（现成可泛化）

`expression_service.py:171-266` 的循环是候选 A 的核心骨架：

```
构造 messages（system + user）
  ↓
调 /chat/completions，tools + tool_choice:auto
  ↓
有 tool_calls？
  ├─ 是：保存 assistant 消息 → 逐个执行工具 → 回填 tool 结果 → 回到"调API"
  └─ 否：返回纯文本，结束
（max_rounds 上限防止死循环）
```

候选 A = 把这段 `_call_llm_with_tools` 从「只处理表达训练一个域的 2 个工具」泛化为「处理全系统多域的协调工具」。

### 2.2 技术选型：不引入 LangChain 的 Agent 工具链

**结论：候选 A 沿用项目现有的裸 httpx 模式，不上 LangChain Agent。**

项目当前两套 AI 通道：
- **裸 httpx**（`ai_service` / `ai_action_service` / `expression_service`）：所有 Tool-Use 场景。
- **LangChain**（`ai_client.py` 的 `call_ai_text_stream`）：纯文本 / 流式生成（如习惯分析长文打字机）。

理由：
1. **一致性** — 项目 Tool-Use 统一风格是裸 httpx，候选 A 保持同风格，代码整体可读。
2. **低风险** — 复用 `_call_llm_with_tools` ≈ 复制 + 泛化，不学新语法，出问题熟悉自己的代码。
3. **面试叙事更强** — 讲「自己实现 OpenAI 式 Tool-Use 协议的多工具编排」，比「用 LangChain 的 agent_executor」更能证明深度。

**LangChain 在系统中的定位保持不变**：纯文本/流式生成继续用 `call_ai_text_stream`，Tool-Use 走裸 httpx。

---

## 3. 核心设计

### 3.1 架构图

```
┌─────────────────────────────────────────────────────────────┐
│  前端 coordinator.js（对话框）                                 │
│  └─ 输入自然语言 → POST /api/coordinator/chat                 │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│  后端 Router: backend/routers/coordinate.py                   │
│  1. 轻量意图分词前缀（关键词 → 定域）                            │
│  2. 命中简单域 → 直接调业务层，不调 AI                          │
│  3. 模糊/复杂 → 走协调服务                                    │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│  协调服务: backend/services/coordinate_service.py             │
│  └─ 泛化版 _call_llm_with_tools（裸 httpx Tool-Use 循环）       │
│      ├─ prompts/coordinate.py  定义 COORDINATE_TOOLS + 提示词  │
│      ├─ coordinate_executor()  按工具名分发到各模块 handler     │
│      └─ 回填工具结果 → 继续轮询 → 纯文本结束                     │
└──────────────────────────┬──────────────────────────────────┘
                           │ 复用现有业务函数（方案①）
┌──────────────────────────▼──────────────────────────────────┐
│  业务数据层（不变，唯一写库通道）                                 │
│  db/actions.py · db/habits.py · db/tasks.py                  │
│  db/skill_tree.py · services/exp_service.py（经验结算）        │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 工具集定义（COORDINATE_TOOLS）

**核心决策：AI 不做业务逻辑，AI 只决定"调哪个工具、传什么参数"。真正的写库/算经验仍走现有业务函数。**

工具示意（具体 JSON Schema 见附录 A）：

| 工具 | 作用域 | 复用函数 |
|------|--------|---------|
| `record_action` | 记行动 | `db/actions.create_action_log` + `services/exp_service.award_exp_and_recalc` |
| `set_habit_checkin` | 习惯打卡 | `db/habits`（打卡/补卡） |
| `create_task` | 新增任务 | `db/tasks.create_task` |
| `update_task_status` | 改任务状态 | `db/tasks`（todo/doing/done） |
| `query_global_stats` | 统计查询（只读） | `db/stats.get_profile_stats` / `get_yearly_activity` / `get_recent_activities` |
| `query_skill_tree` | 技能树查改 | `db/skill_tree`（读/建节点/连线） |
| `list_available_tools` | 让 AI 自查能力 | 静态返回 |
| `ask_user` | 信息不足时反问 | 前端展示回执 |

> ⚠️ **权限边界**：`record_action` 等写操作默认需要用户确认（见 3.4），查询类只读工具可免确认。

### 3.3 意图分类层（薄薄一层）

在调 AI 之前，做一次轻量意图判断（正则 + 关键词，非重活）：

```
输入 → 快速分类
  ├─ 行动记录域：  含 记/跑了/睡了/运动/工作/创作/复盘    → 直接进行动解析（可复用 ai_action）
  ├─ 习惯域：      含 打卡/习惯/坚持/每天                 → 习惯处理
  ├─ 任务域：      含 任务/待办/今天做/安排              → 任务处理
  ├─ 统计查询域：  含 怎么/怎么样/报告/统计/进度          → 只读查询，不写库
  ├─ 技能树域：    含 技能树/节点/技能                   → 技能树
  └─ URL 全不中：   → 走泛化 Tool-Use，让 AI 自己决定
```

**价值**：
- 简单指令（"跑了30分钟"适合已成熟的 `ai_action`）直接走轻路径，不重复造轮子。
- 省 token：能关键词定域的不惊动大模型。
- 保灵活：模糊语义交给泛化协调器。

### 3.4 写操作确认（安全设计）

写库操作（记行动/打卡/建任务/改技能树）默认**先确认后执行**：

```
Agent: 识别到「跑步 30 分钟 · 健康维度 +15 EXP」，是否提交？
用户: 确认 → 走业务层写库 → 回显经验/等级变化
```

实现：`ask_user` 工具回传确认，前端渲染确认卡片。可提供"免确认模式"开关（设置项）提升流畅度。

---

## 4. 落地改动清单（点对点）

按项目 CLAUDE.md 的分层约定（prompts/services/routers + 前端 pages），改动如下：

| 层 | 文件 | 动作 | 工作量 |
|----|------|------|--------|
| prompts | 新建 `backend/prompts/coordinate.py` | 定义 `COORDINATE_SYSTEM_PROMPT` + `COORDINATE_TOOLS`（附录 A 的 8 个工具 JSON Schema） | 中 |
| services | 新建 `backend/services/coordinate_service.py` | 泛化 `_call_llm_with_tools` 循环 + `coordinate_executor` 分发器，复用各 `db/*.py` | 大 |
| services | `ai_client.py` | 不动（长文回复用现有 `call_ai_text_stream`） | 无 |
| routers | 新建 `backend/routers/coordinate.py` | `POST /api/coordinator/chat`：意图分词 + 调用 service + 确认流 | 小 |
| routers | `backend/main.py` | 注册新路由 + 更新 136-153 行 import 与 include | 小 |
| routers | `ai.py` | 不动，新路由独立 | 无 |
| frontend | 新建 `frontend/js/pages/coordinator.js` | 对话面板，复用 `agent.js` 的消息渲染/滚动/流式展示模式 | 中 |
| frontend | `frontend/css/pages.css` | 新增 `.coord__*` 少量样式，风格对齐 `.expr__*` | 小 |
| backend | `backend/tests/` | 新增协调服务的单元测试 | 中 |

**核心工作量集中在两块**：`coordinate.py`（工具集 + 提示词）和 `coordinate_service.py`（执行器循环）。前端因复用 agent.js 模式最轻量。

---

## 5. 关键实现细节

### 5.1 coordinate_service.py 核心循环（泛化版）

基于 `expression_service._call_llm_with_tools` 改写，只改分发的部分：

```python
async def coordinate_executor(tool_name: str, args: dict, user_id: int) -> str:
    """按工具名分发到各业务模块，返回可回填给 AI 的结果字符串。"""
    try:
        if tool_name == "record_action":
            # 复用 action 解析产出的记录 + 精确经验结算
            log_id = create_action_log(user_id, **args["action"])
            result = award_exp_and_recalc(user_id, args["action"]["category_id"], args["action"]["dimension_exp"])
            return json.dumps({"ok": True, "action_id": log_id, **result["exp_result"]}, ensure_ascii=False)

        if tool_name == "set_habit_checkin":
            # 复用 habits 打卡，返回打卡成功后习惯状态
            ...

        if tool_name == "query_global_stats":
            stats = get_profile_stats(user_id)
            return json.dumps(stats, ensure_ascii=False)

        # ... 其余工具分发

    except Exception as e:
        log.exception(f"工具执行失败: {tool_name}")
        return json.dumps({"error": str(e)}, ensure_ascii=False)  # 把错误回填给 AI 让它兜底
```

### 5.2 与 ai_client 流式的配合

长回复（如统计报告）用 `call_ai_text_stream` 走 SSE 打字机；工具调度用 `coordinate_service` 的裸 httpx 循环。二者在 Router 层按是否含工具调用分流。

### 5.3 前端复用点

- `agent.js` 的对话式消息渲染（气泡、流式光标）可平移。
- `agent.js` 的 ASR 语音链路（麦克风 → AudioWorklet 降采样 → WebSocket）可直接接到协调入口，实现**语音化操作**（对 demo 冲击力提升明显）。

---

## 6. 里程碑规划

| 阶段 | 内容 | 验收 |
|------|------|------|
| **M1** | `coordinate.py` 工具集 + 提示词 | 8 个工具 Schema 定义齐全 |
| **M2** | `coordinate_service.py` 分发器，先接 2 个域（行动 + 统计查询） | 对话调和查询跑通 |
| **M3** | 补任务/习惯/技能树域工具 | 5 个写查询域全通 |
| **M4** | 意图分词 + 简单域短路 + 确认流 | 关键词指令不走 AI |
| **M5** | 前端 coordinator.js + 样式 + 语音入口 | 侧边栏统一对话可用 |
| **M6** | 测试 + 整合到 `main.py` + 文档更新 | pytest 通过 |

---

## 7. 面试讲解对照表

| 面试官可能问 | 怎么答 |
|--------------|--------|
| 做过什么 AI 相关 | "手写 OpenAI 式 Tool-Use 多工具编排，跨 8 个数据域调度" |
| 为什么不用 LangChain Agent | "项目 Tool-Use 三处都是裸 httpx，保持一致 + 自己控制协议细节，需长文才复用 LangChain 流式" |
| 意图识别怎么做 | "关键词分词做轻量预判短路 + 模糊指令交给大模型，省 token 且兜底" |
| AI 会不会乱写库 | "AI 只决定调哪个工具传什么参数，写库统一走业务层，含经验结算和写前确认" |
| 如何演示 | "语音说『记一笔创作』→ 自动写库 + 等级变化回显" |

---

## 附录 A：COORDINATE_TOOLS 工具 Schema（草稿）

> 完整实现时按此骨架展开，JSON 结构与现有 `SKILL_TREE_TOOLS` / `ACTION_PARSE_TOOLS` 一致（`{"type":"function","function":{...}}`）。

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
              "sub_type": {"type": "string", "description": "子类型ID，同 ACTION_PARSE_TOOLS 定义"},
              "duration": {"type": "integer", "description": "时长分钟，固定值类型传0"},
              "note": {"type": "string", "description": "具体做了什么"},
              "dimension_exp": {"type": "number", "description": "按计分规则计算的维度经验值"},
              "sleep_start": {"type": "string", "description": "睡眠模式入睡 HH:MM"},
              "sleep_end": {"type": "string", "description": "睡眠模式起床 HH:MM"}
            },
            "required": ["category_id", "note", "dimension_exp"]
          },
          "confirm": {"type": "boolean", "description": "用户是否已确认此写入。默认 false。"}
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
      "name": "query_skill_tree",
      "description": "查询或描述技能树结构。参数支持返回某棵树节点/连线，或查找某技能。",
      "parameters": {
        "type": "object",
        "properties": {
          "question": {"type": "string", "description": "对技能树的自然语言问题"}
        }
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "ask_user",
      "description": "向用户发送一条消息。用于询问更多信息、确认写操作或解释结果。",
      "parameters": {
        "type": "object",
        "properties": {"content": {"type": "string", "description": "消息内容"}},
        "required": ["content"]
      }
    }
  }
]
```

> 附录 A 仅列出 5 个核心工具的骨架；`create_task` / `update_task_status` / `list_available_tools` 结构与 `skill_tree.py` 中对应工具一致，实现时补齐。

---

*文档结束。本方案复用项目现有 Tool-Use 引擎与业务数据层，核心工作量集中在 `coordinate.py` + `coordinate_service.py` 两个文件。*
