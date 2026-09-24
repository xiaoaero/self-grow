"""
Self Grow — 技能树 AI 工具测试

覆盖 services/skill_tree_ai/tools.py 的核心行为：
- 危险操作的确认守卫（delete_node）
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
    update_node,
)


@pytest.fixture
def state():
    return {"tree": {"name": "测试树", "nodes": [], "connections": []}}


# ─────────────────────────────────────────────────────────────
# 确认守卫
# ─────────────────────────────────────────────────────────────

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
    create_nodes_batch.invoke({
        "nodes": [
            {"name": "根", "children": ["子A", "子B"]},
            {"name": "子A", "children": ["孙1"]},
            {"name": "子B"},
            {"name": "孙1"},
        ],
        "state": state,
    })
    nodes = state["tree"]["nodes"]
    coords = [(n["x"], n["y"]) for n in nodes]

    # 不能有点停留在原点，也不能有重叠
    assert all(not (x == 0 and y == 0) for x, y in coords)
    assert len(set(coords)) == len(coords)


def test_explicit_coords_are_preserved(state):
    create_nodes_batch.invoke({
        "nodes": [{"name": "A", "x": 500, "y": 300}, {"name": "B", "x": 700, "y": 400}],
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
    create_nodes_batch.invoke({"nodes": [{"name": "目标"}], "state": state})
    node_id = state["tree"]["nodes"][0]["id"]
    create_node.invoke({"name": "另一个", "x": 900, "y": 900, "state": state})
    other_id = state["tree"]["nodes"][1]["id"]

    r = update_node.invoke({"node_id": other_id, "changes": {"name": "目标"}, "state": state})
    assert r["success"] is True
    names = [n["name"] for n in state["tree"]["nodes"]]
    assert names.count("目标") == 1
    assert "目标 2" in names


# ─────────────────────────────────────────────────────────────
# 模型配置来源
# ─────────────────────────────────────────────────────────────

def test_agent_node_passes_state_to_llm_factory():
    """agent_node 必须把 **state** 传给 llm_factory

    ⚠️ 曾经写成 `llm_factory()`（无参）→ 工厂拿不到 user_id →
    `get_llm()` 内部是 `get_active_config(user_id or 1, "llm")` →
    **恒定读 user_id=1 的模型配置**。

    而技能树 AI 只有 admin 能用，于是 admin 在
    「用户中心 → 模型信息」里选的模型对它**不生效** ——
    实际跑的是 user_id=1 那个普通用户配的模型，而且**不报错、日志也看不出来**。
    实测：admin 配的是 qwen3.7-plus，技能树实际在用 qwen3.7-flash。
    """
    import asyncio

    from langchain_core.messages import AIMessage

    from services.skill_tree_ai.node import make_agent_node

    received = []

    class FakeLLM:
        def bind_tools(self, tools):
            return self

        async def ainvoke(self, messages):
            return AIMessage(content="好的")

    def factory(state):
        received.append(state)
        return FakeLLM()

    node = make_agent_node(tools=[], llm_factory=factory)
    asyncio.run(node({
        "user_id": 42,
        "tree": {"nodes": [], "connections": []},
        "messages": [],
        "selected_node_ids": [],
    }))

    assert received, "llm_factory 没有被调用"
    assert received[0].get("user_id") == 42, (
        f"state 没传到工厂（收到 {received[0].get('user_id')!r}）—— "
        "这会让模型配置被读成 user_id=1 的"
    )


def test_graph_llm_factory_passes_user_id():
    """graph.py 里那处 get_llm 调用必须带 `user_id=`

    用 AST 检查而不是字符串匹配 —— 字符串匹配会被注释里的反例骗过去。
    """
    import ast
    import io
    import os

    path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "services", "skill_tree_ai", "graph.py",
    )
    tree = ast.parse(io.open(path, encoding="utf-8").read())

    calls = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Name) and n.func.id == "get_llm"
    ]
    assert calls, "graph.py 里找不到 get_llm 调用（测试需要同步更新）"

    for c in calls:
        assert "user_id" in {k.arg for k in c.keywords}, (
            f"graph.py:{c.lineno} 的 get_llm() 没传 user_id —— "
            "会恒定读 user_id=1 的模型配置"
        )


# ─────────────────────────────────────────────────────────────
# 工具集合本身
# ─────────────────────────────────────────────────────────────

def test_replace_tree_tool_is_removed():
    """整树替换工具已按需求删除

    它会「清空并替换整棵树」，是这套工具里破坏性最强的一个，
    而且能力已被 create_nodes_batch 覆盖（树为空时效果一样；
    树非空时要重建，提示词里要求先删根节点再批量建）。

    ⚠️ 如果哪天要加回来，请先想清楚：一个能一次清空整棵树的工具，
    在「AI 自主决定调哪个工具」的场景下风险有多大。
    """
    from services.skill_tree_ai.tools import SKILL_TREE_AI_TOOLS

    names = [t.name for t in SKILL_TREE_AI_TOOLS]
    assert "replace_tree" not in names
    assert names == [
        "create_node", "create_nodes_batch", "update_node", "delete_node",
        "add_connection", "delete_connection", "move_node", "send_reply",
    ], f"工具集合变了：{names}"


def test_prompt_does_not_mention_replace_tree():
    """提示词里也不能再提 replace_tree

    工具删了但提示词还写着，模型会去调一个不存在的工具 ——
    表现为「AI 说它要生成整棵树，然后什么都没发生」。
    """
    from services.skill_tree_ai.prompts import SKILL_TREE_AI_SYSTEM_PROMPT

    assert "replace_tree" not in SKILL_TREE_AI_SYSTEM_PROMPT


# ─────────────────────────────────────────────────────────────
# 会话与树的绑定（切树后不能操作旧树）
# ─────────────────────────────────────────────────────────────

class _FakeSnapshot:
    def __init__(self, values):
        self.values = values


class _FakeGraph:
    def __init__(self, values):
        self._values = values

    async def aget_state(self, config):
        return _FakeSnapshot(self._values)


def test_resume_rejects_thread_from_another_tree():
    """跨树恢复会话必须被拒绝

    ⚠️ checkpointer 是**按 thread_id** 恢复 state 的，而状态里带着创建时的 tree_id。
    不校验的话：用 A 树的 tree_id 通过归属校验、再拿 B 树的 thread_id 恢复会话，
    就会操作 B 树 —— 「打开某棵树却动了另一棵」。

    前端 switchToTree / 新建树 / 删除树 都会 resetSession()，
    但那只是 UX；后端不能依赖前端（切树入口多、能直接打 API）。
    """
    import asyncio

    from services.skill_tree_ai.graph import _ensure_thread_belongs_to_tree

    graph = _FakeGraph({"tree_id": "tree-A"})

    # 会话属于 tree-A，却用它请求 tree-B → 拒绝
    try:
        asyncio.run(_ensure_thread_belongs_to_tree(graph, "t1", "tree-B"))
        raise AssertionError("跨树恢复应该被拒绝")
    except ValueError as e:
        # 文案里必须带「会话」—— 前端 ai-bridge.js 靠 /404|会话|thread/i
        # 决定是否自动重置会话并提示用户
        assert "会话" in str(e), f"文案缺少「会话」二字，前端不会自动重置：{e}"

    # 同一棵树 → 放行
    asyncio.run(_ensure_thread_belongs_to_tree(graph, "t1", "tree-A"))

    # 新会话（没有 thread_id）→ 放行
    asyncio.run(_ensure_thread_belongs_to_tree(graph, None, "tree-B"))

    # 老会话的 state 里没有 tree_id（历史数据 / 状态未初始化）→ 放行，避免误杀
    asyncio.run(_ensure_thread_belongs_to_tree(_FakeGraph({}), "t1", "tree-B"))


# ================================================================
# 参数容错：模型把数组传成 JSON 字符串（2026-09-24）
# ================================================================

class TestJsonStringArgs:
    """模型经常把 list/dict 参数序列化成字符串传过来

    实测（2026-09-24 用户报「半天就生成了一个」）：一次对话里连续 5 次工具调用全部
    因参数校验失败而回滚 ——

        create_nodes_batch(connections='[{"from_name": "后端", "to_name": "项目实战"}]')
        → 1 validation error ... Input should be a valid list [input_type=str]
        create_node(tags='["Root"]') → 同上

    工具**永远执行不了**，模型换个写法继续重试 → 一轮烧掉 93 秒、10 个节点只建出 1 个。
    修法在 `services/tool_args.py::coerce_json_args`（调用点两处：技能树 node.py、
    协调 Agent base.py），以及 `tools.py::_as_list`（嵌套在数组里的字符串）。
    """

    def _state(self):
        return {"tree": {"nodes": [], "connections": []}}

    def test_connections_as_json_string(self):
        from services.skill_tree_ai.tools import create_nodes_batch
        from services.tool_args import coerce_json_args

        state = self._state()
        raw = {
            "nodes": [{"name": "后端入门指南"}, {"name": "项目实战"}],
            "connections": '[{"from_name": "后端入门指南", "to_name": "项目实战"}]',
        }
        # 前置：不解析就必然抛校验错误（否则这个用例是假的）
        try:
            create_nodes_batch.invoke({**raw, "state": self._state()})
            raise AssertionError("未容错时本该抛参数校验错误")
        except Exception:      # noqa: BLE001 — pydantic ValidationError
            pass

        safe = coerce_json_args(create_nodes_batch, raw)
        assert isinstance(safe["connections"], list), "connections 没被解析成 list"
        result = create_nodes_batch.invoke({**safe, "state": state})
        assert result["success"] is True, result.get("message")
        assert len(state["tree"]["nodes"]) == 2
        assert len(state["tree"]["connections"]) == 1

    def test_tags_as_json_string(self):
        from services.skill_tree_ai.tools import create_node
        from services.tool_args import coerce_json_args

        state = self._state()
        result = create_node.invoke({
            **coerce_json_args(create_node, {"name": "根", "tags": '["Root"]'}),
            "state": state,
        })
        assert result["success"] is True
        # ⚠️ 关键：不能变成 ['[', '"', 'R', 'o', 'o', 't', '"', ']']
        assert state["tree"]["nodes"][0]["tags"] == ["Root"]

    def test_nested_tags_in_batch_nodes(self):
        """数组**里面**的字符串同样要规整（coerce 只看顶层字段，管不到嵌套）"""
        from services.skill_tree_ai.tools import create_nodes_batch

        state = self._state()
        create_nodes_batch.invoke({
            "nodes": [{"name": "A", "tags": '["Root"]'}],
            "state": state,
        })
        assert state["tree"]["nodes"][0]["tags"] == ["Root"]

    def test_children_as_json_string(self):
        """children 传字符串时不能**按字符**建节点"""
        from services.skill_tree_ai.tools import create_nodes_batch

        state = self._state()
        create_nodes_batch.invoke({
            "nodes": [{"name": "父", "children": '["子1", "子2"]'}],
            "state": state,
        })
        names = sorted(n["name"] for n in state["tree"]["nodes"])
        # ⚠️ 拆错的话会变成 ['[', '"', '子', '1', ...] 这种按字符铺开的垃圾节点
        assert names == sorted(["父", "子1", "子2"]), names
        # 连线也要建起来（原来 children 里的名称在 nodes 里找不到就**静默跳过**）
        names_by_id = {n["id"]: n["name"] for n in state["tree"]["nodes"]}
        edges = {(names_by_id[c["from"]], names_by_id[c["to"]]) for c in state["tree"]["connections"]}
        assert ("父", "子1") in edges and ("父", "子2") in edges, edges

    def test_update_node_tags_as_json_string(self):
        from services.skill_tree_ai.tools import create_node, update_node

        state = self._state()
        create_node.invoke({"name": "A", "state": state})
        node_id = state["tree"]["nodes"][0]["id"]
        update_node.invoke({"node_id": node_id, "changes": {"tags": '["A", "B"]'}, "state": state})
        assert state["tree"]["nodes"][0]["tags"] == ["A", "B"]

    def test_coerce_leaves_normal_values_alone(self):
        """不该动的别动：普通字符串 / 已经是 list / 解析不了的字符串"""
        from services.skill_tree_ai.tools import create_node
        from services.tool_args import coerce_json_args

        raw = {"name": "普通名字", "tags": ["已经是列表"], "description": "[不是JSON"}
        safe = coerce_json_args(create_node, raw)
        assert safe["name"] == "普通名字"
        assert safe["tags"] == ["已经是列表"]
        assert safe["description"] == "[不是JSON"

    def test_coerce_is_applied_in_both_tool_loops(self):
        """静态护栏：两处工具执行点都必须过 `coerce_json_args`

        这个 bug 的症状是"工具静默不执行 + 模型反复重试"，
        很容易在重构工具循环时把这一行弄丢（丢了也能跑，只是又回到烧 90 秒的状态）。
        """
        import io
        import os

        base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "services")
        for rel in ("skill_tree_ai/node.py", "coordinator/agents/base.py"):
            src = io.open(os.path.join(base, rel), encoding="utf-8").read()
            assert "coerce_json_args(" in src, f"{rel} 的工具执行路径漏了参数容错"
            assert "tool_fn.invoke" in src


# ================================================================
# 提示词：必须区分「咨询」和「执行」（2026-09-24）
# ================================================================

class TestPromptIsMinimal:
    """提示词只留「什么时候调工具」这一层，细节交给工具自己的描述

    2026-09-24 用户要求：**规则别写那么细** —— 「涉及调整树就调工具（工具里有描述），
    不涉及就直接回答」就够了。于是提示词从 ~75 行压到 ~19 行，
    原来写在提示词里的参数细节（优先级枚举、进度范围、坐标可省略…）全部下沉到工具 docstring。

    这组用例钉住两件事：① 意图分界仍然在（否则「推荐下就建树」会复发）
    ② 提示词**没有**再把工具清单/参数细节抄回来（那正是用户要去掉的复杂度）。
    """

    def _prompt(self):
        from services.skill_tree_ai.prompts import SKILL_TREE_AI_SYSTEM_PROMPT
        return SKILL_TREE_AI_SYSTEM_PROMPT

    # ---- ① 意图分界必须在 ----

    def test_has_both_sides_of_intent(self):
        p = self._prompt()
        assert "涉及调整树" in p and "不涉及调整树" in p, "缺少「要不要调工具」的分界"
        assert "不要动树" in p, "没写清咨询时不许动树"
        for word in ("推荐", "建议"):
            assert word in p, f"咨询侧缺少常见措辞「{word}」"

    def test_asks_before_writing_on_consult(self):
        p = self._prompt()
        assert ("要我建出来吗" in p) or ("建成节点吗" in p), "缺少结尾的确认问句"
        assert "拿不准" in p, "没写「拿不准先问再做」"

    def test_consult_example_marked_as_no_tool(self):
        p = self._prompt()
        idx = p.find("推荐下 Python")
        assert idx != -1, "缺少咨询类的例子"
        assert "不调工具" in p[idx:idx + 80], "咨询示例没标注「不调工具」"

    def test_execute_example_points_to_batch_tool(self):
        """反向：明确的执行意图仍要直接调工具（不能被拦成"先问"）"""
        p = self._prompt()
        idx = p.find("帮我生成前端学习路线")
        assert idx != -1 and "create_nodes_batch" in p[idx:idx + 60]

    def test_prompt_stays_small(self):
        """提示词就该短 —— 超过 40 行说明又把细节抄回来了"""
        assert len(self._prompt().splitlines()) <= 40, "提示词又变长了，考虑把细节下沉到工具描述"

    # ---- ② 细节要在工具自己的描述里（提示词不再重复）----

    def test_no_duplicated_tool_inventory(self):
        p = self._prompt()
        assert "## 可用工具" not in p, "提示词里又抄了一份工具清单（工具自身描述才是唯一来源）"
        assert "- create_node:" not in p and "- update_node:" not in p

    def test_tool_docstrings_carry_the_details(self):
        """原来写在提示词里的参数约束，必须在**工具描述**里能找到"""
        from services.skill_tree_ai import tools

        node_doc = tools.create_node.description
        assert "none / high / medium / low" in node_doc, "create_node 没写优先级枚举"
        assert "自动" in node_doc, "create_node 没写坐标可省略"

        batch_doc = tools.create_nodes_batch.description
        assert "自动" in batch_doc, "create_nodes_batch 没写坐标自动排布"
        assert "children" in batch_doc, "create_nodes_batch 没写 children 用法"

        upd_doc = tools.update_node.description
        assert "0-100" in upd_doc, "update_node 没写 progress 范围"
        assert "none / high / medium / low" in upd_doc, "update_node 没写优先级枚举"


# ================================================================
# 生成要求（2026-09-24 用户明确提的三条）
# ================================================================

class TestGenerationRequirements:
    """生成整棵树时的硬要求：别写"路线"当根节点、别一条直线"""

    def _prompt(self):
        from services.skill_tree_ai.prompts import SKILL_TREE_AI_SYSTEM_PROMPT
        return SKILL_TREE_AI_SYSTEM_PROMPT

    def test_root_is_not_a_title(self):
        p = self._prompt()
        assert "第一个节点" in p, "没写「第一个节点直接是知识点」"
        assert "学习路线" in p and "不要写成" in p, "没禁掉把根节点写成「XX 学习路线」"

    def test_structure_must_branch(self):
        p = self._prompt()
        assert "不要是一条直线" in p, "没禁掉单线结构"
        assert "3~5 条分支" in p or "3-5 条分支" in p, "没给分支数量下限"
        assert "3~4 层" in p or "3-4 层" in p, "没给层数区间"

    def test_unlimited_tokens_for_skill_tree(self):
        """技能树 AI 必须**不限制输出 token**（一次生成整棵树，很容易撞上限）

        用文本断言 graph.py 的工厂：`max_tokens=None` 一旦被"顺手"改回具体数字，
        表现就是"树生成一半就停"，很难联想到根因。
        """
        import io
        import os

        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                            "services", "skill_tree_ai", "graph.py")
        src = io.open(path, encoding="utf-8").read()
        assert "max_tokens=None" in src, "技能树 AI 又被限了 token"
        assert "timeout=300" in src, "长输出容易超过默认 120s 超时，应放宽"


# ================================================================
# 上下文窗口：只带最近 5 个「来回」（2026-09-24 用户要求）
# ================================================================

def _fake_round(i):
    """造一个来回：Human + AIMessage(tool_calls) + ToolMessage + AIMessage"""
    from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

    return [
        HumanMessage(content=f"第{i}轮的问题"),
        AIMessage(content="", tool_calls=[{
            "id": f"call{i}", "name": "create_node", "args": {"name": f"n{i}"},
        }]),
        ToolMessage(content="ok", tool_call_id=f"call{i}"),
        AIMessage(content=f"第{i}轮的回答"),
    ]


class TestContextWindow:
    """上下文按**轮**裁剪，不是按条数

    一轮 ReAct 里会有：1 条 AI(tool_calls) + N 条 ToolMessage + 1 条 AI。
    按条数切很容易切在 tool_calls 和它的 ToolMessage 之间 → 孤儿 ToolMessage
    → LLM API 400。所以切点必须落在 HumanMessage 上。
    """

    def _truncate(self):
        from services.skill_tree_ai.node import _truncate_messages
        return _truncate_messages

    def test_keeps_only_last_five_rounds(self):
        from langchain_core.messages import HumanMessage

        msgs = [m for i in range(1, 8) for m in _fake_round(i)]   # 7 轮
        out = self._truncate()(msgs)
        humans = [m.content for m in out if isinstance(m, HumanMessage)]
        assert humans == [f"第{i}轮的问题" for i in (3, 4, 5, 6, 7)], humans

    def test_cut_point_is_a_human_message(self):
        """切口必须是 HumanMessage —— 否则会出现孤儿 ToolMessage"""
        from langchain_core.messages import HumanMessage, ToolMessage

        msgs = [m for i in range(1, 8) for m in _fake_round(i)]
        out = self._truncate()(msgs)
        assert isinstance(out[0], HumanMessage), f"切口是 {type(out[0]).__name__}"
        # 也不能以 ToolMessage 收尾的中间态：每条 ToolMessage 前面必有带 tool_calls 的 AI
        for idx, m in enumerate(out):
            if isinstance(m, ToolMessage):
                assert idx > 0 and getattr(out[idx - 1], "tool_calls", None), \
                    f"第 {idx} 条是孤儿 ToolMessage"

    def test_short_history_is_untouched(self):
        msgs = [m for i in range(1, 4) for m in _fake_round(i)]   # 3 轮 < 5
        assert self._truncate()(msgs) == msgs

    def test_exactly_five_rounds_is_untouched(self):
        msgs = [m for i in range(1, 6) for m in _fake_round(i)]
        assert self._truncate()(msgs) == msgs

    def test_empty(self):
        assert self._truncate()([]) == []
        assert self._truncate()(None) == []
