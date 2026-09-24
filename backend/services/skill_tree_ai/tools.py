"""
Self Grow — 技能树 AI 编辑工具

所有工具操作后端内存中的树状态（state["tree"]）。
工具返回 dict，包含：
- success: bool
- message: str
- diff: 可选，变更记录
"""

import json
import uuid
import logging
from typing import Annotated

from langchain_core.tools import tool
from langgraph.prebuilt import InjectedState


log = logging.getLogger(__name__)

# ───────────────────────────────────────────────────────────────
# 工具内部辅助函数
# ───────────────────────────────────────────────────────────────


def _uid() -> str:
    return "node_" + uuid.uuid4().hex[:12]


def _get_tree(state: dict) -> dict:
    return state.get("tree", {})


def _get_nodes(state: dict) -> list:
    return _get_tree(state).get("nodes", [])


def _get_connections(state: dict) -> list:
    return _get_tree(state).get("connections", [])


def _find_node(state: dict, node_id: str):
    return next((n for n in _get_nodes(state) if n.get("id") == node_id), None)


def _as_list(value, field: str = "") -> list:
    """把可能是「JSON 字符串」的列表参数规整成 list

    ⚠️ 千万别写 `list(value or [])` —— 字符串会被**按字符拆开**：
        list('[\"Root\"]')  →  ['[', '"', 'R', 'o', 'o', 't', '"', ']']
    症状是节点上凭空多出一堆单字符标签，而且**完全不报错**（实测于 2026-09-24）。
    """
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        try:
            parsed = json.loads(text)
        except (ValueError, TypeError):
            return [text]                    # 普通字符串 → 当成单个标签
        if isinstance(parsed, list):
            return parsed
        return [parsed] if parsed is not None else []
    return [value] if isinstance(value, (dict, int, float)) else []


def _validate_name(name: str) -> tuple[bool, str]:
    if not name or not name.strip():
        return False, "节点名称不能为空"
    return True, ""


def _validate_priority(priority: str) -> tuple[bool, str]:
    if priority not in {"none", "high", "medium", "low"}:
        return False, f"优先级必须是 none/high/medium/low 之一，收到: {priority}"
    return True, ""


def _validate_progress(progress: int) -> tuple[bool, str]:
    if not isinstance(progress, int) or progress < 0 or progress > 100:
        return False, f"progress 必须是 0-100 的整数，收到: {progress}"
    return True, ""


def _has_valid_coords(node: dict) -> bool:
    """节点是否带了有效坐标（LLM 经常省略 x/y，全 0 视为未指定）"""
    try:
        return not (float(node.get("x", 0) or 0) == 0 and float(node.get("y", 0) or 0) == 0)
    except (TypeError, ValueError):
        return False


def _auto_layout(nodes: list, connections: list,
                 start_x: int = 80, start_y: int = 80,
                 gap_x: int = 200, gap_y: int = 110) -> None:
    """按父子层级自动排布节点坐标。

    LLM 生成整棵树时经常省略 x/y（默认 0），如果不处理，所有节点会全部
    叠在 (0,0) 上。这里用 BFS 计算层级：根节点一列、子节点依次向右展开，
    同层节点垂直排列。
    """
    if not nodes:
        return

    by_id = {n.get("id"): n for n in nodes}
    child_ids = {c.get("to") for c in (connections or [])}
    roots = [n for n in nodes if n.get("id") not in child_ids] or [nodes[0]]

    visited = set()
    level_count = {}
    queue = [(r.get("id"), 0) for r in roots]

    while queue:
        nid, level = queue.pop(0)
        if nid in visited:
            continue
        visited.add(nid)

        idx = level_count.get(level, 0)
        level_count[level] = idx + 1

        node = by_id.get(nid)
        if node is not None:
            node["x"] = start_x + level * gap_x
            node["y"] = start_y + idx * gap_y

        for c in (connections or []):
            if c.get("from") == nid and c.get("to") not in visited:
                queue.append((c.get("to"), level + 1))

    # 兜底：没有任何连线关系时按顺序垂直排列，避免重叠
    for i, n in enumerate(nodes):
        if n.get("id") not in visited:
            n["x"] = start_x
            n["y"] = start_y + i * gap_y


def _ensure_unique_name(nodes: list, name: str, original_name: str = None) -> str:
    """如果名称重复，自动追加序号。"""
    existing_names = {n.get("name") for n in nodes if n.get("name") != original_name}
    if name not in existing_names:
        return name
    base = name
    counter = 2
    while f"{base} {counter}" in existing_names:
        counter += 1
    return f"{base} {counter}"


# ───────────────────────────────────────────────────────────────
# 工具定义
# ───────────────────────────────────────────────────────────────


@tool

def create_node(
    name: str,
    icon: str = "📚",
    color: str = "#2a2a4a",
    description: str = "",
    tags: list | None = None,
    priority: str = "none",
    parent_id: str | None = "",
    x: int = 0,
    y: int = 0,
    state: Annotated[dict, InjectedState()] = None,
) -> dict:
    """创建一个新节点。如果提供了 parent_id，会自动建立连线。

    Args:
        name: 节点名称（必填）
        icon: 图标 emoji，如 📚 💡 🔧 🎯 🌟
        color: 背景颜色 hex，如 #2a2a4a
        description: 节点描述
        tags: 标签列表
        priority: 优先级，只能 none / high / medium / low
        parent_id: 父节点 ID（可选），提供时自动与父节点连线
        x: X 坐标（像素），可省略 —— 全部省略时会自动按层级排布
        y: Y 坐标（像素），可省略
    """
    tree = _get_tree(state)
    nodes = tree.setdefault("nodes", [])

    ok, err = _validate_name(name)
    if not ok:
        return {"success": False, "message": err}

    ok, err = _validate_priority(priority)
    if not ok:
        return {"success": False, "message": err}

    parent = None
    if parent_id:
        parent = _find_node(state, parent_id)
        if not parent:
            return {"success": False, "message": f"未找到父节点 {parent_id}"}

    # 未指定坐标时，相对父节点排布（否则会落在 (0,0) 与其他节点重叠）
    if x == 0 and y == 0:
        if parent:
            siblings = sum(1 for c in _get_connections(state) if c["from"] == parent_id)
            x = int(parent.get("x", 0) or 0) + 200
            y = int(parent.get("y", 0) or 0) + siblings * 110
        elif nodes:
            x = 80
            y = max(int(n.get("y", 0) or 0) for n in nodes) + 110

    final_name = _ensure_unique_name(nodes, name.strip())

    node = {
        "id": _uid(),
        "name": final_name,
        "x": x,
        "y": y,
        "size": 70,
        "shape": "round",
        "icon": icon or "📚",
        "color": color or "#2a2a4a",
        "borderColor": "#444466",
        "description": description or "",
        "tags": _as_list(tags, "tags"),
        "priority": priority or "none",
        "progress": 0,
    }
    nodes.append(node)

    connections = tree.setdefault("connections", [])
    if parent:
        connections.append({
            "id": _uid(),
            "from": parent_id,
            "to": node["id"],
            "color": "#666680",
            "dashed": False,
            "showArrow": True,
        })

    return {
        "success": True,
        "message": f"已创建节点「{final_name}」",
        "diff": {
            "op": "create",
            "node_id": node["id"],
            "parent_id": parent_id or None,
            "data": node,
        },
    }


@tool
def create_nodes_batch(
    nodes: list[dict],
    connections: list[dict] | None = None,
    parent_id: str | None = "",
    state: Annotated[dict, InjectedState()] = None,
) -> dict:
    """批量创建节点并建立连线。用于一次性生成整棵子树。

    Args:
        nodes: 节点列表（**真正的数组**，不是 JSON 字符串），
               每个元素可含 name/icon/color/description/tags/priority/x/y。
               坐标可省略，会按父子层级自动排布。
               元素里的 children 字段可直接写子节点名称列表
               （这些名称若没在 nodes 里声明，会自动补建出节点）。
        connections: 连线列表（**真正的数组**），元素为 {from_name, to_name}
                     或 {from_id, to_id}；用名称时需能在 nodes 里找到。
        parent_id: 父节点 ID（可选）。提供时，批量节点中未作为任何连线目标的
                   「根节点」会自动连接到该父节点。
    """
    tree = _get_tree(state)
    existing_nodes = tree.setdefault("nodes", [])
    existing_connections = tree.setdefault("connections", [])

    if not nodes:
        return {"success": False, "message": "nodes 不能为空"}

    # 校验名称
    for i, n in enumerate(nodes):
        ok, err = _validate_name(n.get("name", ""))
        if not ok:
            return {"success": False, "message": f"第 {i+1} 个节点: {err}"}

    # `children` 里出现、但 nodes 里没有的名称 → **自动补一个节点**
    #
    # ⚠️ 别只把它们当连线目标：连线解析时 `name_map` 找不到就 `continue`
    #    **静默跳过**，于是「父节点 + children(子1,子2)」只建出父节点一个，
    #    而返回消息里数字也变小了 —— 模型和用户都看不出哪儿少了
    #    （2026-09-24 实测，与 docstring 承诺的"与 connections 二选一"不符）。
    declared = {n.get("name", "").strip() for n in nodes}
    extra_nodes = []
    for n in nodes:
        for raw_child in _as_list(n.get("children"), "children"):
            cname = str(raw_child).strip()
            if cname and cname not in declared:
                declared.add(cname)
                extra_nodes.append({"name": cname})
    if extra_nodes:
        nodes = list(nodes) + extra_nodes
        log.info("children 里有 %d 个未声明的子节点名，已自动创建：%s",
                 len(extra_nodes), [e["name"] for e in extra_nodes])

    parent = None
    if parent_id:
        parent = _find_node(state, parent_id)
        if not parent:
            return {"success": False, "message": f"未找到父节点 {parent_id}"}

    # 创建节点，建立 name -> node 映射
    name_map = {}
    created = []
    for n in nodes:
        final_name = _ensure_unique_name(existing_nodes, n.get("name", "").strip())
        node = {
            "id": _uid(),
            "name": final_name,
            "x": n.get("x", 0),
            "y": n.get("y", 0),
            "size": n.get("size", 70),
            "shape": n.get("shape", "round"),
            "icon": n.get("icon", "📚"),
            "color": n.get("color", "#2a2a4a"),
            "borderColor": n.get("borderColor", "#444466"),
            "description": n.get("description", ""),
            "tags": _as_list(n.get("tags"), "tags"),
            "priority": n.get("priority", "none"),
            "progress": n.get("progress", 0),
        }
        existing_nodes.append(node)
        name_map[final_name] = node
        name_map[n.get("name", "").strip()] = node  # 同时保留原始名称映射
        created.append(node)

    # 处理 children 字段
    # ⚠️ 用 `_as_list` 而不是直接遍历：模型可能把 children 传成 JSON 字符串
    #    （'["A","B"]'），直接 `for child_name in children` 会**按字符**建节点。
    conns = _as_list(connections, "connections")
    for n in nodes:
        children = _as_list(n.get("children"), "children")
        if children:
            for child_name in children:
                conns.append({"from_name": n.get("name", "").strip(), "to_name": child_name})

    # 提供 parent_id 时，把批量节点中的「根」（未作为任何连线目标）连接到父节点
    if parent:
        child_names = {c.get("to_name") or c.get("to_id") for c in conns}
        for n in nodes:
            if n.get("name", "").strip() not in child_names:
                conns.append({
                    "from_id": parent_id,
                    "to_name": n.get("name", "").strip(),
                })

    # 建立连线（from/to 均可按名称或 ID 指定，支持混合）
    conn_created = []
    for c in conns:
        from_node = None
        to_node = None
        if c.get("from_name"):
            from_node = name_map.get(c["from_name"])
        elif c.get("from_id"):
            from_node = _find_node(state, c["from_id"])
        if c.get("to_name"):
            to_node = name_map.get(c["to_name"])
        elif c.get("to_id"):
            to_node = _find_node(state, c["to_id"])

        if not from_node or not to_node:
            continue

        existing = any(
            conn["from"] == from_node["id"] and conn["to"] == to_node["id"]
            for conn in existing_connections
        )
        if existing:
            continue

        conn = {
            "id": _uid(),
            "from": from_node["id"],
            "to": to_node["id"],
            "color": c.get("color", "#666680"),
            "dashed": c.get("dashed", False),
            "showArrow": True,
        }
        existing_connections.append(conn)
        conn_created.append(conn)

    # LLM 省略坐标时自动布局，否则新节点会全部叠在 (0,0)
    if created and not any(_has_valid_coords(n) for n in created):
        if parent:
            _auto_layout(created, conn_created,
                         start_x=int(parent.get("x", 0) or 0) + 200,
                         start_y=int(parent.get("y", 0) or 0))
        else:
            _auto_layout(created, conn_created)

    return {
        "success": True,
        "message": f"已批量创建 {len(created)} 个节点和 {len(conn_created)} 条连线",
        "diff": {
            "op": "replace",
            "data": {
                "nodes": created,
                "connections": conn_created,
            },
        },
    }


@tool
def update_node(
    node_id: str,
    changes: dict,
    state: Annotated[dict, InjectedState()] = None,
) -> dict:
    """修改一个已有节点的属性。只传需要修改的字段。

    Args:
        node_id: 节点 ID
        changes: 要修改的字段，可包含 icon/color/description/priority/progress/tags/name。
                 priority 只能 none / high / medium / low；
                 progress 是 0-100 的整数；tags 是字符串数组；
                 改 name 时不要和其他节点重名（重复会自动加后缀）。
    """
    node = _find_node(state, node_id)
    if not node:
        return {"success": False, "message": f"未找到节点 {node_id}"}

    allowed = {"icon", "color", "description", "priority", "progress", "tags", "name"}
    actual_changes = {}

    for key, value in changes.items():
        if key not in allowed:
            continue
        if key == "priority":
            ok, err = _validate_priority(value)
            if not ok:
                return {"success": False, "message": err}
        if key == "progress":
            ok, err = _validate_progress(value)
            if not ok:
                return {"success": False, "message": err}
        if key == "name":
            ok, err = _validate_name(value)
            if not ok:
                return {"success": False, "message": err}
            value = _ensure_unique_name(
                _get_nodes(state), value.strip(), original_name=node.get("name")
            )
        if key == "tags":
            value = _as_list(value, "tags")

        actual_changes[key] = value

    if not actual_changes:
        return {"success": False, "message": "没有有效的变更字段"}

    node.update(actual_changes)

    return {
        "success": True,
        "message": f"已更新节点「{node.get('name')}」",
        "diff": {
            "op": "update",
            "node_id": node_id,
            "changes": actual_changes,
        },
    }


@tool
def delete_node(
    node_id: str,
    confirm: bool = False,
    state: Annotated[dict, InjectedState()] = None,
) -> dict:
    """删除指定节点及其相关连线。如果节点有子节点或删除影响较大，默认需要二次确认。

    Args:
        node_id: 要删除的节点 ID
        confirm: 是否已确认（危险操作需要用户确认）
    """
    tree = _get_tree(state)
    nodes = _get_nodes(state)
    node = _find_node(state, node_id)
    if not node:
        return {"success": False, "message": f"未找到节点 {node_id}"}

    connections = _get_connections(state)
    child_count = sum(1 for c in connections if c["from"] == node_id)

    # 影响较大时需要确认
    if not confirm and child_count > 0:
        return {
            "success": False,
            "needs_confirmation": True,
            "message": f"节点「{node.get('name')}」有 {child_count} 个子节点，删除将同时移除所有后代节点，确认吗？",
        }

    # 删除相关连线
    tree["connections"] = [c for c in connections if c["from"] != node_id and c["to"] != node_id]
    # 删除节点（同时级联删除子节点）
    deleted_ids = {node_id}
    # BFS 收集所有后代
    queue = [node_id]
    while queue:
        current = queue.pop(0)
        children = [c["to"] for c in connections if c["from"] == current]
        for child in children:
            if child not in deleted_ids:
                deleted_ids.add(child)
                queue.append(child)

    tree["nodes"] = [n for n in nodes if n["id"] not in deleted_ids]

    return {
        "success": True,
        "message": f"已删除节点「{node.get('name')}」及 {len(deleted_ids) - 1} 个后代节点",
        "diff": {
            "op": "delete",
            "node_id": node_id,
            "deleted_ids": list(deleted_ids),
        },
    }


@tool
def add_connection(
    from_id: str,
    to_id: str,
    state: Annotated[dict, InjectedState()] = None,
) -> dict:
    """在两个节点之间建立连线（父子关系）。"""
    from_node = _find_node(state, from_id)
    to_node = _find_node(state, to_id)
    if not from_node:
        return {"success": False, "message": f"未找到源节点 {from_id}"}
    if not to_node:
        return {"success": False, "message": f"未找到目标节点 {to_id}"}

    connections = _get_tree(state).setdefault("connections", [])
    exists = any(c["from"] == from_id and c["to"] == to_id for c in connections)
    if exists:
        return {"success": False, "message": "连线已存在"}

    conn = {
        "id": _uid(),
        "from": from_id,
        "to": to_id,
        "color": "#666680",
        "dashed": False,
        "showArrow": True,
    }
    connections.append(conn)

    return {
        "success": True,
        "message": f"已建立连线：{from_node.get('name')} → {to_node.get('name')}",
        "diff": {
            "op": "connect",
            "from_id": from_id,
            "to_id": to_id,
            "data": conn,
        },
    }


@tool
def delete_connection(
    from_id: str,
    to_id: str,
    state: Annotated[dict, InjectedState()] = None,
) -> dict:
    """删除两个节点之间的连线。"""
    tree = _get_tree(state)
    connections = _get_connections(state)
    original_len = len(connections)
    tree["connections"] = [c for c in connections if not (c["from"] == from_id and c["to"] == to_id)]

    if len(tree["connections"]) == original_len:
        return {"success": False, "message": "未找到指定连线"}

    from_node = _find_node(state, from_id)
    to_node = _find_node(state, to_id)
    return {
        "success": True,
        "message": f"已删除连线：{from_node.get('name') if from_node else from_id} → {to_node.get('name') if to_node else to_id}",
        "diff": {
            "op": "disconnect",
            "from_id": from_id,
            "to_id": to_id,
        },
    }


@tool
def   move_node(
    node_id: str,
    x: int,
    y: int,
    state: Annotated[dict, InjectedState()] = None,
) -> dict:
    """移动节点到指定坐标位置。"""
    node = _find_node(state, node_id)
    if not node:
        return {"success": False, "message": f"未找到节点 {node_id}"}

    node["x"] = x
    node["y"] = y

    return {
        "success": True,
        "message": f"已移动节点「{node.get('name')}」到 ({x}, {y})",
        "diff": {
            "op": "move",
            "node_id": node_id,
            "x": x,
            "y": y,
        },
    }


@tool
def send_reply(
    reply: str,
    state: Annotated[dict, InjectedState()] = None,
) -> dict:
    """向用户发送一条文本消息。用于解释你的操作、回答用户问题或询问更多信息。

    Args:
        reply: 要展示给用户的文本消息
    """
    return {
        "success": True,
        "message": "消息已记录",
        "reply": reply,
    }


# 工具列表（供 graph 绑定）
SKILL_TREE_AI_TOOLS = [
    create_node,
    create_nodes_batch,
    update_node,
    delete_node,
    add_connection,
    delete_connection,
    move_node,
    send_reply,
]
