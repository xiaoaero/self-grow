"""
Self Grow — 技能树 AI 编辑 Agent 提示词

⚠️ **找提示词时的两个坑**（2026-09-24 用户问「它的提示词在哪，为什么我没找到」）：

  1. 技能树的提示词在**这里**（`services/skill_tree_ai/prompts.py`），
     **不在** 根目录的 `backend/prompts/` 里 —— 那个目录装的是**另外几个** Agent 的：
     `action_parse.py`（行动解析）/ `coordinator.py`（协调 Agent）/
     `expression.py`（表达训练）/ `habit_icon.py`（习惯图标）。
     两处并存是历史原因，都合法，只是找的时候要先想清楚是哪个 Agent。
  2. 它是 **Python 字符串常量**（`SKILL_TREE_AI_SYSTEM_PROMPT`），不是 .md/.txt 文件，
     所以按文件名找提示词是找不到的；前端里也**没有**（提示词不下发到浏览器）。

本文件两块内容：

| 名字 | 作用 | 什么时候变 |
|---|---|---|
| `SKILL_TREE_AI_SYSTEM_PROMPT` | 静态规则（工具清单 / 操作规则 / 坐标约定 / 输出示例） | 手写维护 |
| `build_tree_state_prompt()` | **动态**注入当前树状态（节点表、连线、选中项） | 每次 agent 节点执行时重建 |

两者在 `services/skill_tree_ai/node.py` 里拼成一个 SystemMessage 列表发给模型
（见该文件 `full_messages = [...]`）。

改提示词要注意：**规则和「输出示例」要一起改** —— 示例对模型的引导力比规则强，
只改规则常常改不动行为（踩过：示例全是"生成/加子节点"，模型就把"推荐下"也当成生成）。
改完**必须重启后端**才生效。

想看模型实际收到什么：`SELF_GROW_LOG_LEVEL=DEBUG` 后重启，
`node.py` 会把两条 SystemMessage 原文打进日志。
"""

SKILL_TREE_AI_SYSTEM_PROMPT = """你是一个知识树编辑助手，通过调用工具来修改知识树。

## 两条规则

1. **涉及调整树 → 调用工具**：生成 / 加节点 / 修改 / 删除 / 连线 / 移动，
   调对应工具完成。参数说明看**工具自身的描述**（不再在这里重复），
   批量生成用 create_nodes_batch。
2. **不涉及调整树 → 直接回答**：用户在问问题、要建议、让你推荐或评价，
   没有明确让你改 —— 用文字回答，**不要动树**。
   如果建议值得落成节点，结尾问一句「要我建出来吗？」，**等用户同意再调工具**。
3. 拿不准要不要改时，先问再做。

改完树之后，用 send_reply 用一两句说明做了什么。

## 生成整棵树时（用户要求里的硬条件）

- **第一个节点直接是第一个知识点**，不要写成「XX 学习路线 / XX 入门指南」这种标题
  —— 树名是树名，节点是节点。
- 结构**不要是一条直线、也不要只有一个分叉**：至少 3~5 条分支、整体 3~4 层；
  同层节点数不必相等，重要的分支可以更深。
- 节点名称具体到能执行（「变量与作用域」），不要空泛（「基础知识」）。

## 例子

"帮我生成前端学习路线" → 调 create_nodes_batch
"推荐下 Python 该学什么" → 不调工具，直接回答 + 结尾问「要我建出来吗？」
"""


def build_tree_state_prompt(tree: dict, selected_node_ids: list[str]) -> str:
    """构建发送给 LLM 的当前树状态提示。"""
    nodes = tree.get("nodes", [])
    connections = tree.get("connections", [])

    lines = ["当前知识树状态："]
    lines.append(f"树名：{tree.get('name', '未命名知识树')}")
    lines.append(f"节点数：{len(nodes)}，连线数：{len(connections)}")

    if selected_node_ids:
        selected = [n for n in nodes if n.get("id") in selected_node_ids]
        lines.append(f"当前选中节点：{', '.join(n.get('name', '') for n in selected)}")

    if nodes:
        # 「操作用 id」这句放这里而不是系统提示词里 —— 贴着数据说，模型更容易照做
        lines.append("\n节点列表（id | name | progress；操作节点时用 id）：")
        for n in nodes:
            lines.append(f"- {n.get('id')} | {n.get('name')} | progress={n.get('progress', 0)}")

    if connections:
        lines.append("\n连线列表（from → to）：")
        node_map = {n.get("id"): n.get("name", "") for n in nodes}
        for c in connections:
            from_name = node_map.get(c.get("from"), c.get("from"))
            to_name = node_map.get(c.get("to"), c.get("to"))
            lines.append(f"- {from_name} → {to_name}")

    return "\n".join(lines)
