"""
Self Grow — 技能树 AI 编辑图

编译 LangGraph StateGraph，提供：
- build_skill_tree_chat_graph(): 构建图
- run_skill_tree_chat(): 一次性运行
- resume_skill_tree_chat(): 恢复对话（用于用户确认/回答）
"""

import json
import logging
import uuid

from langchain_core.messages import HumanMessage
from langgraph.graph import StateGraph, END

from services.coordinator.checkpointer import get_checkpointer
from services.llm import get_llm
from services.skill_tree_ai.state import SkillTreeChatState
from services.skill_tree_ai.node import make_agent_node
from services.skill_tree_ai.tools import SKILL_TREE_AI_TOOLS

log = logging.getLogger(__name__)


def build_skill_tree_chat_graph():
    """构建并编译技能树 AI 编辑图。"""
    graph = StateGraph(SkillTreeChatState)

    agent_node = make_agent_node(
        tools=SKILL_TREE_AI_TOOLS,
        # ⚠️ 工厂必须接收 state，否则拿不到 user_id ——
        #    `get_llm()` 内部是 `get_active_config(user_id or 1, "llm")`，
        #    不传就**恒定读 user_id=1 的模型配置**。
        #    而技能树 AI 只有 admin 能用，于是 admin 在
        #    「用户中心 → 模型信息」里选的模型对它**不生效**，
        #    实际跑的是 user_id=1（那个普通用户）配的模型 —— 静默用错模型。
        #
        #    传的必须是**整个 state**而不是 user_id：工厂在图**编译时**创建，
        #    那时还没有任何请求上下文，拿不到具体用户。
        # ⚠️ 技能树是「一次生成一整棵树」的场景：一次 create_nodes_batch 可能有
        #    几十个节点、每个还带描述，输出很容易撞上默认的 9192 token 上限，
        #    表现是**树只生成了一半就停**。所以这里显式不限制（max_tokens=None，
        #    不往请求里带该字段，用服务商的默认上限），并把超时放宽到 5 分钟 ——
        #    长输出的耗时本来就可能超过默认的 120s。
        llm_factory=lambda state: get_llm(
            temperature=0.3, max_tokens=None, timeout=300,
            user_id=state.get("user_id"),
        ),
    )

    graph.add_node("agent", agent_node)
    graph.set_entry_point("agent")
    graph.add_edge("agent", END)

    return graph.compile(checkpointer=get_checkpointer())


# 全局单例：避免每次请求重新编译
_skill_tree_chat_graph = None


def get_skill_tree_chat_graph():
    """获取编译后的图单例。"""
    global _skill_tree_chat_graph
    if _skill_tree_chat_graph is None:
        _skill_tree_chat_graph = build_skill_tree_chat_graph()
    return _skill_tree_chat_graph


async def _ensure_thread_belongs_to_tree(graph, thread_id: str, tree_id: str) -> None:
    """校验一个已有会话确实属于这棵树

    ⚠️ 为什么必须有：checkpointer 是**按 thread_id** 恢复 state 的，
    而 state 里带着创建时的 `tree_id`。不校验的话，用 A 树的 `{tree_id}`
    通过归属校验、再拿 B 树的 `thread_id` 恢复会话，就会**操作 B 树**。

    前端 `switchToTree` / 新建树 / 删除树 都会 `resetSession()`（丢弃 thread_id），
    但那只是 UX —— **后端不能依赖前端**：
      1. 切换树的入口有好几个，漏一处就串树
      2. 多个管理员之间能互相操作对方的会话（thread_id 并不是秘密）
      3. 直接打 API 完全绕得过去

    ⚠️ 抛 `ValueError` 的文案里必须带「会话」二字 ——
    前端 `ai-bridge.js` 用 `/404|会话|thread/i` 匹配来决定是否自动重置会话。
    """
    if not thread_id:
        return                                   # 新会话，无需校验
    snapshot = await graph.aget_state({"configurable": {"thread_id": thread_id}})
    prev = (snapshot.values if snapshot else None) or {}
    prev_tree_id = prev.get("tree_id")
    if prev_tree_id and prev_tree_id != tree_id:
        log.warning(
            "会话与树不匹配：thread=%s 属于 tree=%s，但请求的是 tree=%s",
            thread_id, prev_tree_id, tree_id,
        )
        raise ValueError("AI 会话与当前技能树不匹配，已重置会话，请重新提问")


async def run_skill_tree_chat(
    tree: dict,
    user_message: str,
    user_id: int,
    tree_id: str,
    selected_node_ids: list[str] | None = None,
    thread_id: str = None,
) -> dict:
    """启动一次新的 AI 编辑对话（或续接已有会话）。"""
    graph = get_skill_tree_chat_graph()
    # 续接已有会话时先校验它属于这棵树（见 _ensure_thread_belongs_to_tree）
    await _ensure_thread_belongs_to_tree(graph, thread_id, tree_id)
    # 每次新会话生成独立 thread_id（编入 user_id，避免跨用户会话串号）；
    # 同一会话由前端回传 thread_id 续接
    thread_id = thread_id or f"stc_{user_id}_{uuid.uuid4().hex[:12]}"
    config = {"configurable": {"thread_id": thread_id}}

    initial_state = {
        "user_id": user_id,
        "tree_id": tree_id,
        "tree": tree,
        "selected_node_ids": list(selected_node_ids or []),
        "messages": [HumanMessage(content=user_message)],
        "diffs": [],
        "executed_tools": [],
        "reply": None,
        "pending_confirmation": None,
        "ask_rounds": 0,
    }

    result = await graph.ainvoke(initial_state, config=config)
    return _format_result(result, thread_id)


async def resume_skill_tree_chat(
    thread_id: str,
    user_message: str,
    confirm: bool = False,
    tree: dict = None,
    tree_id: str = None,
) -> dict:
    """恢复对话：用户回答反问或确认操作。

    Args:
        tree: 前端当前的树状态（可选）。传入时会覆盖 checkpoint 里的旧树，
              否则 AI 会基于旧快照继续编辑，把用户期间的手动改动覆盖掉。
        tree_id: 当前打开的树 ID。**必传** —— 用来校验这个会话确实属于这棵树，
                 防止「切到别的树之后点确认，结果改了原来那棵树」。
    """
    graph = get_skill_tree_chat_graph()
    config = {"configurable": {"thread_id": thread_id}}

    # ⚠️ 校验会话归属（见 _ensure_thread_belongs_to_tree）
    #    放在最前面：确认类操作会真的改树，绝不能校验前就动手
    if tree_id:
        await _ensure_thread_belongs_to_tree(graph, thread_id, tree_id)

    # 如果有待确认的操作，先注入确认状态
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
    else:
        content = user_message

    # tree 是普通字段（非 operator.add），放进 input 即整体覆盖
    invoke_input = {"messages": [HumanMessage(content=content)]}
    if tree is not None:
        invoke_input["tree"] = tree

    result = await graph.ainvoke(invoke_input, config=config)
    return _format_result(result, thread_id)


def _format_result(result: dict, thread_id: str) -> dict:
    """格式化图为前端可用的响应。"""
    reply = result.get("reply")
    if not reply:
        # 兜底：工具执行成功但没有 send_reply 时，用工具结果拼一个摘要
        msgs = [t.get("message", "") for t in (result.get("executed_tools") or []) if t.get("message")]
        reply = "\n".join(msgs) if msgs else "操作已完成。"
    return {
        "thread_id": thread_id,
        "reply": reply,
        "diffs": result.get("diffs", []),
        "executed_tools": result.get("executed_tools", []),
        "pending_confirmation": result.get("pending_confirmation"),
        "tree": result.get("tree", {}),
    }
