"""
Self Grow — 技能树 AI 工具测试

覆盖 services/skill_tree_ai/tools.py 的核心行为：
- 危险操作的确认守卫（replace_tree / delete_node）
- 级联删除
- 名称唯一化
- LLM 省略坐标时的自动布局（否则所有节点会叠在 (0,0)）
"""

import sys
import os
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.skill_tree_ai.tools import (  # noqa: E402
    create_node,
    create_nodes_batch,
    delete_node,
    replace_tree,
    update_node,
)


@pytest.fixture
def state():
    return {"tree": {"name": "测试树", "nodes": [], "connections": []}}


# ─────────────────────────────────────────────────────────────
# 确认守卫
# ─────────────────────────────────────────────────────────────

def test_replace_tree_requires_confirm(state):
    r = replace_tree.invoke({"nodes": [{"name": "A"}], "state": state})
    assert r["success"] is False
    assert r.get("needs_confirmation") is True
    assert state["tree"]["nodes"] == []          # 未确认不能动树


def test_replace_tree_applies_after_confirm(state):
    r = replace_tree.invoke({"nodes": [{"name": "A"}, {"name": "B"}], "confirm": True, "state": state})
    assert r["success"] is True
    assert len(state["tree"]["nodes"]) == 2
    assert state["tree"]["name"] == "A"


def test_delete_node_with_children_requires_confirm(state):
    create_nodes_batch.invoke({"nodes": [{"name": "父"}, {"name": "子"}], "state": state})
    parent_id = state["tree"]["nodes"][0]["id"]
    child_id = state["tree"]["nodes"][1]["id"]
    from services.skill_tree_ai.tools import add_connection
    add_connection.invoke({"from_id": parent_id, "to_id": child_id, "state": state})

    r = delete_node.invoke({"node_id": parent_id, "confirm": False, "state": state})
    assert r.get("needs_confirmation") is True
    assert len(state["tree"]["nodes"]) == 2      # 未确认不删除

    # 确认后级联删除
    r2 = delete_node.invoke({"node_id": parent_id, "confirm": True, "state": state})
    assert r2["success"] is True
    assert state["tree"]["nodes"] == []


# ─────────────────────────────────────────────────────────────
# 自动布局（LLM 省略坐标时）
# ─────────────────────────────────────────────────────────────

def test_auto_layout_when_coords_missing(state):
    replace_tree.invoke({
        "nodes": [
            {"name": "根", "children": ["子A", "子B"]},
            {"name": "子A", "children": ["孙1"]},
            {"name": "子B"},
            {"name": "孙1"},
        ],
        "confirm": True,
        "state": state,
    })
    nodes = state["tree"]["nodes"]
    coords = [(n["x"], n["y"]) for n in nodes]

    # 不能有点停留在原点，也不能有重叠
    assert all(not (x == 0 and y == 0) for x, y in coords)
    assert len(set(coords)) == len(coords)


def test_explicit_coords_are_preserved(state):
    replace_tree.invoke({
        "nodes": [{"name": "A", "x": 500, "y": 300}, {"name": "B", "x": 700, "y": 400}],
        "confirm": True,
        "state": state,
    })
    nodes = {n["name"]: n for n in state["tree"]["nodes"]}
    assert nodes["A"]["x"] == 500 and nodes["A"]["y"] == 300
    assert nodes["B"]["x"] == 700 and nodes["B"]["y"] == 400


def test_create_node_places_relative_to_parent(state):
    create_node.invoke({"name": "父", "x": 100, "y": 100, "state": state})
    parent_id = state["tree"]["nodes"][0]["id"]
    # 不给坐标 → 应排在父节点右侧，而不是 (0,0)
    create_node.invoke({"name": "子", "parent_id": parent_id, "state": state})
    child = state["tree"]["nodes"][1]
    assert not (child["x"] == 0 and child["y"] == 0)
    assert child["x"] > 100


# ─────────────────────────────────────────────────────────────
# 批量创建与名称唯一化
# ─────────────────────────────────────────────────────────────

def test_batch_attaches_to_parent(state):
    create_node.invoke({"name": "父", "x": 0, "y": 0, "state": state})
    parent_id = state["tree"]["nodes"][0]["id"]
    r = create_nodes_batch.invoke(
        {"nodes": [{"name": "子1"}, {"name": "子2"}], "parent_id": parent_id, "state": state}
    )
    assert r["success"] is True
    conns = state["tree"]["connections"]
    assert len(conns) == 2
    assert all(c["from"] == parent_id for c in conns)


def test_batch_auto_layout_relative_to_parent(state):
    create_node.invoke({"name": "父", "x": 100, "y": 100, "state": state})
    parent_id = state["tree"]["nodes"][0]["id"]
    create_nodes_batch.invoke(
        {"nodes": [{"name": "子1"}, {"name": "子2"}], "parent_id": parent_id, "state": state}
    )
    children = state["tree"]["nodes"][1:]
    assert all(n["x"] >= 300 for n in children)          # 父 x=100 + 200
    assert children[0]["y"] != children[1]["y"]          # 同层错开


def test_update_node_renames_with_unique_suffix(state):
    replace_tree.invoke({"nodes": [{"name": "目标"}], "confirm": True, "state": state})
    node_id = state["tree"]["nodes"][0]["id"]
    create_node.invoke({"name": "另一个", "x": 900, "y": 900, "state": state})
    other_id = state["tree"]["nodes"][1]["id"]

    r = update_node.invoke({"node_id": other_id, "changes": {"name": "目标"}, "state": state})
    assert r["success"] is True
    names = [n["name"] for n in state["tree"]["nodes"]]
    assert names.count("目标") == 1
    assert "目标 2" in names
