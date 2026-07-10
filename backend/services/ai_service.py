"""
Self Grow — AI 代理服务

封装 AI 聊天功能，包括工具定义、系统提示词、HTTP 调用逻辑。
"""

import json
import logging
import httpx
from fastapi import HTTPException

from config import AI_BASE_URL, AI_API_KEY, AI_MODEL

log = logging.getLogger(__name__)


# ================================================================
# 工具定义 (Tool Use)
# ================================================================

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_tree_state",
            "description": "获取当前知识树的完整状态（节点列表、连线列表）。当你需要了解当前树的结构时调用此工具。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_node",
            "description": "创建一个新节点。如果提供了 parent_name，会自动建立连线。",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "节点名称"},
                    "icon": {"type": "string", "description": "图标 emoji，如 📚 💡 🔧 🎯 🌟 🔗 ⚡ 🏆"},
                    "color": {"type": "string", "description": "背景颜色 hex，如 #2a2a4a"},
                    "description": {"type": "string", "description": "节点描述"},
                    "tags": {"type": "array", "items": {"type": "string"}, "description": "标签列表"},
                    "priority": {"type": "string", "enum": ["none", "high", "medium", "low"], "description": "优先级"},
                    "parent_name": {"type": "string", "description": "父节点名称（可选）"},
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_node",
            "description": "修改一个已有节点的属性。只传需要修改的字段。",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "要修改的节点名称"},
                    "changes": {
                        "type": "object",
                        "description": "要修改的字段和值",
                        "properties": {
                            "icon": {"type": "string"},
                            "color": {"type": "string"},
                            "description": {"type": "string"},
                            "priority": {"type": "string", "enum": ["none", "high", "medium", "low"]},
                            "progress": {"type": "integer", "minimum": 0, "maximum": 100},
                            "tags": {"type": "array", "items": {"type": "string"}},
                        },
                    },
                },
                "required": ["name", "changes"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_node",
            "description": "删除指定节点及其所有相关连线。",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "要删除的节点名称"},
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_connection",
            "description": "在两个节点之间建立连线（父子关系）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "from": {"type": "string", "description": "父节点名称"},
                    "to": {"type": "string", "description": "子节点名称"},
                },
                "required": ["from", "to"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_connection",
            "description": "删除两个节点之间的连线。",
            "parameters": {
                "type": "object",
                "properties": {
                    "from": {"type": "string", "description": "父节点名称"},
                    "to": {"type": "string", "description": "子节点名称"},
                },
                "required": ["from", "to"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "move_node",
            "description": "移动节点到指定坐标位置。",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "要移动的节点名称"},
                    "x": {"type": "integer", "description": "X 坐标（像素）"},
                    "y": {"type": "integer", "description": "Y 坐标（像素）"},
                },
                "required": ["name", "x", "y"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "replace_tree",
            "description": "用新的节点列表替换整个知识树。会清空所有已有节点和连线。",
            "parameters": {
                "type": "object",
                "properties": {
                    "nodes": {
                        "type": "array",
                        "description": "节点列表",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "icon": {"type": "string"},
                                "color": {"type": "string"},
                                "description": {"type": "string"},
                                "tags": {"type": "array", "items": {"type": "string"}},
                                "priority": {"type": "string"},
                                "children": {"type": "array", "items": {"type": "string"}, "description": "子节点名称列表"},
                            },
                        },
                    },
                },
                "required": ["nodes"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_message",
            "description": "向用户发送一条文本消息。用于解释你的操作、回答用户问题或询问更多信息。",
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "消息内容"},
                },
                "required": ["content"],
            },
        },
    },
]

SYSTEM_PROMPT = """你是一个AI知识树编辑助手。你可以通过调用工具来操作知识树。

可用的工具：
- replace_tree: 用新节点列表替换整棵树（用于首次生成知识树）
- get_tree_state: 查看当前树的结构
- create_node: 创建新节点（可指定父节点自动连线）
- update_node: 修改节点属性
- delete_node: 删除节点
- add_connection: 建立父子连线
- delete_connection: 删除连线
- move_node: 移动节点位置
- send_message: 向用户发送消息

操作规则：
1. 当用户要求生成知识树且当前树为空时，直接使用 replace_tree，不要先调 get_tree_state
2. 修改已有树时，优先使用 create_node/update_node/delete_node 等工具
3. 每次操作后，用 send_message 告诉用户你做了什么
4. 节点 icon 使用 emoji
5. 颜色使用 hex 格式（如 #4a4a6a）
6. 优先级：high/medium/low/none
7. 知识树层级深度建议 3-4 层，每层子节点不超过 6 个"""


async def call_ai(messages: list, tree_state: dict = None):
    """调用 AI API，返回 ChatResponse 所需的数据"""
    if not AI_API_KEY:
        raise HTTPException(status_code=500, detail="AI_API_KEY 未配置")

    # 构造 messages
    msgs = [{"role": "system", "content": SYSTEM_PROMPT}]

    if tree_state:
        tree_info = json.dumps(tree_state, ensure_ascii=False, indent=2)
        msgs.append({
            "role": "system",
            "content": f"当前知识树状态：\n{tree_info}",
        })

    msgs.extend(messages)

    # 调用 AI API
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            payload = {
                "model": AI_MODEL,
                "messages": msgs,
                "tools": TOOLS,
                "tool_choice": "auto",
                "temperature": 0.7,
                "max_tokens": 8192,
            }
            log.info(f"→ 请求 AI: {AI_MODEL}")
            resp = await client.post(
                f"{AI_BASE_URL}/chat/completions",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {AI_API_KEY}",
                },
                json=payload,
            )

            if resp.status_code != 200:
                err_text = resp.text[:500]
                log.error(f"← AI 错误 {resp.status_code}: {err_text}")
                raise HTTPException(
                    status_code=502,
                    detail=f"AI API 错误 {resp.status_code}: {err_text}",
                )

            data = resp.json()
            choice = data["choices"][0]
            msg = choice["message"]

            # 如果有工具调用，返回给前端
            if "tool_calls" in msg and msg["tool_calls"]:
                tool_calls = []
                for tc in msg["tool_calls"]:
                    try:
                        args = json.loads(tc["function"]["arguments"])
                    except json.JSONDecodeError:
                        args = {"_raw": tc["function"]["arguments"]}
                    tool_calls.append({
                        "id": tc["id"],
                        "name": tc["function"]["name"],
                        "arguments": args,
                    })
                log.info(f"← AI 调用 {len(tool_calls)} 个工具: {[t['name'] for t in tool_calls]}")
                return {"tool_calls": tool_calls}

            # 纯文本回复
            content = msg.get("content", "")
            log.info(f"← AI 回复: {content[:60]}...")
            return {"content": content}

    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="AI API 请求超时")
    except Exception as e:
        log.exception("AI 请求异常")
        raise HTTPException(status_code=500, detail=str(e))