"""
Self Grow — 技能树 AI 编辑 Agent 状态定义

用于 LangGraph StateGraph，保存一次 AI 编辑会话的完整上下文。
"""

from typing import Annotated, TypedDict
import operator


class NodeDiff(TypedDict, total=False):
    """单次树变更记录"""
    op: str                    # create / update / delete / connect / disconnect / move / replace
    node_id: str | None        # 涉及节点 ID
    parent_id: str | None      # 创建子节点时的父节点
    data: dict | None          # 创建/更新时的节点数据
    changes: dict | None       # update 时的变更字段
    from_id: str | None        # connect/disconnect
    to_id: str | None          # connect/disconnect
    x: int | None              # move
    y: int | None              # move
    message: str | None        # 操作结果说明


class PendingConfirmation(TypedDict, total=False):
    """待用户确认的操作"""
    tool: str
    args: dict
    message: str
    confirmed: bool


class SkillTreeChatState(TypedDict):
    """技能树 AI 编辑会话状态"""
    # 用户与上下文
    user_id: int
    tree_id: str

    # 当前内存中的树（AI 操作的目标）
    tree: dict

    # 当前选中的节点 ID 列表（供 AI 参考）
    selected_node_ids: list[str]

    # 对话历史（checkpointer 自动累积）
    messages: Annotated[list, operator.add]

    # AI 对树的所有变更（返回给前端一次性应用）
    # 注意：普通字段而非 operator.add —— 每次调用整体替换，
    # 否则旧 diff 会在 checkpointer 中跨轮累积并被重复返回给前端
    diffs: list[NodeDiff]

    # 已执行的工具日志（同上，每次调用替换）
    executed_tools: list[dict]

    # 自然语言回复（最终返回给用户）
    reply: str | None

    # 待确认的危险操作
    pending_confirmation: PendingConfirmation | None

    # 反问/确认轮数（防无限循环）
    ask_rounds: int
