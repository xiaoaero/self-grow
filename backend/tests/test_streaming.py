"""
Self Grow — 流式（SSE）回归测试

覆盖两层：

1. **SSE 机制本身**（`services/sse.py`）—— 事件编码、响应头、心跳、发射器隔离、
   「没启用发射器时必须是空操作」这条不变式
2. **各流式端点的对外契约** —— 事件序列、`done` 字段、鉴权、错误处理

设计原则：
- **不联网**：所有 LLM 调用都在**路由层**打桩（`routers.xxx.生成函数`），
  这样既测到了 SSE 管道，又不会真的调模型、也不写数据库
- 断言用的是「事件类型序列 + 关键阶段存在」而不是逐字全文，
  免得提示词一改测试就碎
"""

import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from helpers import get_auth_headers


# ================================================================
# 工具：解析 SSE 原文
# ================================================================

def parse_sse(raw: str) -> list:
    """把 SSE 响应体解析成事件列表（心跳 → {'__comment': ...}）"""
    events = []
    for block in raw.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        if block.startswith(":"):
            events.append({"__comment": block[1:].strip()})
            continue
        for line in block.splitlines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
    return events


def types_of(events) -> list:
    return [e["type"] for e in events if "type" in e]


def stages_of(events) -> list:
    return [e["stage"] for e in events if e.get("type") == "stage"]


def tokens_of(events) -> str:
    return "".join(e["text"] for e in events if e.get("type") == "token")


def done_of(events) -> dict:
    dones = [e for e in events if e.get("type") == "done"]
    assert len(dones) == 1, f"done 事件应恰好 1 条，实际 {len(dones)}"
    return dones[0]


# ================================================================
# 一、SSE 机制
# ================================================================

class TestSSEPrimitives:

    def test_sse_encodes_json_without_ascii_escape(self):
        """中文不能被转义成 \\uXXXX —— 那样前端调试时完全看不懂"""
        from services.sse import sse

        line = sse({"type": "stage", "label": "正在理解你的意图…"})
        assert line.endswith("\n\n"), "SSE 事件必须以空行结束"
        assert line.startswith("data: ")
        assert "正在理解你的意图" in line
        assert "\\u" not in line

    def test_sse_comment_is_valid_heartbeat(self):
        from services.sse import sse_comment

        assert sse_comment() == ": ping\n\n"

    def test_response_headers_disable_proxy_buffering(self):
        """X-Accel-Buffering 是「Nginx 别缓冲这个响应」的关键 —— 漏了流式会被攒着一次性发"""
        from services.sse import SSE_HEADERS

        assert SSE_HEADERS["X-Accel-Buffering"] == "no"
        assert "no-cache" in SSE_HEADERS["Cache-Control"]

    # 说明：项目里没有装 pytest-asyncio，所以异步用例一律用 `asyncio.run(...)`
    # 包一层同步测试函数 —— 不额外引入插件依赖，跑法也和别的测试一致

    def test_emit_stage_is_noop_without_emitter(self):
        """核心不变式：没启用流式时，深层代码里的 emit_stage 必须完全静默"""
        from services.sse import emit_stage, emit_token, emit_event

        async def go():
            # 不应抛异常，也不应有任何副作用
            assert await emit_stage("routing", "x") is None
            assert await emit_token("已") is None
            assert await emit_event({"type": "done"}) is None

        asyncio.run(go())

    def test_emitter_is_scoped_and_restored(self):
        """use_emitter 必须是一个作用域：出 with 块后要回到「没有发射器」"""
        from services.sse import use_emitter, emit_stage

        async def go():
            got = []

            async def collect(payload):
                got.append(payload)

            with use_emitter(collect):
                await emit_stage("routing", "在范围内")
            assert len(got) == 1
            assert got[0]["stage"] == "routing"

            # 出了 with 块 → 又变回空操作
            await emit_stage("routing", "在范围外")
            assert len(got) == 1, "离开作用域后仍在推事件 → ContextVar 没被重置"

        asyncio.run(go())

    def test_emitter_isolated_between_concurrent_tasks(self):
        """并发请求之间不能串 —— asyncio 任务复制上下文，各自看到自己的发射器

        这条是整个设计成立的前提：协调 Agent 用 asyncio.gather 并发跑多个子 Agent，
        如果 ContextVar 不隔离，A 的界面会收到 B 的事件。
        """
        from services.sse import use_emitter, emit_stage

        async def worker(tag):
            bucket = []

            async def collect(payload):
                bucket.append(payload.get("label"))

            with use_emitter(collect):
                # 故意交错：让出控制权，制造并发的机会
                await asyncio.sleep(0.01)
                await emit_stage("t", f"{tag}-1")
                await asyncio.sleep(0.01)
                await emit_stage("t", f"{tag}-2")
            return bucket

        async def go():
            return await asyncio.gather(worker("A"), worker("B"))

        a, b = asyncio.run(go())
        assert a == ["A-1", "A-2"], f"A 收到了别的任务的事件：{a}"
        assert b == ["B-1", "B-2"], f"B 收到了别的任务的事件：{b}"

    def test_stream_events_emits_heartbeat_while_waiting(self):
        """等待期间必须发心跳 —— 否则长请求会被中间代理的空闲超时掐断"""
        from services.sse import stream_events

        async def go():
            async def runner(emit):
                await asyncio.sleep(0.12)      # 静默 120ms
                await emit({"type": "done", "reply": "ok"})

            return [c async for c in stream_events(runner, heartbeat=0.04)]

        chunks = asyncio.run(go())

        comments = [c for c in chunks if c.startswith(":")]
        assert comments, "静默期间没有发出任何心跳"
        assert chunks[-1].startswith("data: ")
        assert json.loads(chunks[-1][6:].strip())["reply"] == "ok"

    def test_stream_events_turns_exception_into_error_event(self):
        """流已经开始后出错 → 只能发 error 事件（HTTP 状态码早发出去了）"""
        from services.sse import stream_events

        async def go():
            async def runner(emit):
                await emit({"type": "token", "text": "前半段"})
                raise RuntimeError("模型中途挂了")

            return [c async for c in stream_events(runner, heartbeat=5)]

        chunks = asyncio.run(go())
        payloads = [json.loads(c[6:].strip()) for c in chunks if c.startswith("data: ")]

        assert payloads[0] == {"type": "token", "text": "前半段"}
        assert payloads[-1]["type"] == "error"
        assert "模型中途挂了" in payloads[-1]["message"]

    def test_keepalive_yields_ticks_then_result(self):
        from services.sse import keepalive

        async def go():
            async def slow():
                await asyncio.sleep(0.08)
                return "结果"

            return [kind async for kind, _ in keepalive(slow(), interval=0.03)]

        kinds = asyncio.run(go())
        assert kinds[-1] == "result"
        assert "tick" in kinds, "等待期间没有产出心跳"


# ================================================================
# 二、协调 Agent 流式端点
# ================================================================

class _FakeLLM:
    """按 system prompt 判定角色：协调Agent=路由 / 结果整合=逐字流 / 其他=子Agent"""

    def __init__(self, chunks=("你好", "，你的", "等级是", "Lv188", "。")):
        self.chunks = list(chunks)

    def bind_tools(self, tools, **kw):
        return self                        # 子 Agent 会 bind_tools，返回自己即可

    def bind(self, **kw):
        return self

    @staticmethod
    def _flatten(msgs):
        out = []
        for m in msgs:
            c = getattr(m, "content", None)
            if c is None and isinstance(m, dict):
                c = m.get("content")
            if isinstance(c, str):
                out.append(c)
        return "\n".join(out)

    async def ainvoke(self, msgs):
        from langchain_core.messages import AIMessage

        text = self._flatten(msgs)
        if "协调Agent" in text:
            return AIMessage(content=json.dumps({
                "domains": [{"domain": "query", "reason": "查统计",
                             "instruction": "查询用户等级"}]
            }, ensure_ascii=False))
        return AIMessage(content="你的等级是 Lv188。")

    async def astream(self, msgs):
        from langchain_core.messages import AIMessageChunk

        for piece in self.chunks:
            yield AIMessageChunk(content=piece)


@pytest.fixture
def fake_llm(monkeypatch):
    """把三层 LLM 入口都换成假的（router / synthesize 是模块级绑定，agents 是函数内 import）"""
    fake = _FakeLLM()
    import services.llm as llm_mod
    import services.coordinator.router_node as rn
    import services.coordinator.synthesize_node as sn

    monkeypatch.setattr(llm_mod, "get_llm", lambda *a, **k: fake)
    monkeypatch.setattr(rn, "get_llm", lambda *a, **k: fake)
    monkeypatch.setattr(sn, "get_llm", lambda *a, **k: fake)
    return fake


class TestCoordinatorStream:

    def test_requires_auth(self):
        """流式不等于免鉴权 —— 匿名必须 401"""
        from main import app

        with TestClient(app) as client:
            resp = client.post("/api/coordinator/chat", json={"message": "hi"})
            assert resp.status_code == 401

    def test_event_sequence_and_done_payload(self, fake_llm):
        from main import app

        with TestClient(app) as client:
            resp = client.post("/api/coordinator/chat",
                               json={"message": "我几级了"},
                               headers=get_auth_headers("admin"))

            assert resp.status_code == 200, resp.text[:400]
            assert "text/event-stream" in resp.headers["content-type"]
            assert resp.headers.get("x-accel-buffering") == "no"

            events = parse_sse(resp.text)

        # done 必须是最后一条，且唯一
        assert types_of(events)[-1] == "done"
        done = done_of(events)

        # 逐 token 真的生效了（不是一次性把整段塞进 done）
        assert types_of(events).count("token") == len(fake_llm.chunks)
        assert tokens_of(events) == "".join(fake_llm.chunks)

        # 阶段事件覆盖完整链路
        stages = stages_of(events)
        for need in ("routing", "routing_done", "domain_start", "domain_done", "synthesize"):
            assert need in stages, f"缺阶段 {need}：{stages}"

        # done 的字段与改造前的 JSON 返回一致（前端靠这个不改处理逻辑）
        for field in ("thread_id", "reply", "interrupts", "results",
                      "completed_domains", "pending_tasks", "records"):
            assert field in done, f"done 缺字段 {field}"
        assert done["reply"] == "".join(fake_llm.chunks)

    def test_synthesize_failure_falls_back_but_stream_survives(self, monkeypatch, fake_llm):
        """总结节点中途挂掉 → 已流出的半截文本保留，done.reply 降级为规则拼接

        这条是前端契约的依据：**done.reply 是权威值，前端要用它覆盖已渲染的文本**
        """
        from langchain_core.messages import AIMessageChunk
        from main import app

        class Exploding(_FakeLLM):
            async def astream(self, msgs):
                yield AIMessageChunk(content="前半段")
                raise RuntimeError("模拟模型中断")

        import services.coordinator.synthesize_node as sn
        monkeypatch.setattr(sn, "get_llm", lambda *a, **k: Exploding())

        with TestClient(app) as client:
            resp = client.post("/api/coordinator/chat",
                               json={"message": "我几级了"},
                               headers=get_auth_headers("admin"))
            assert resp.status_code == 200
            events = parse_sse(resp.text)

        assert tokens_of(events) == "前半段"
        done = done_of(events)
        assert "Lv188" in done["reply"], f"应降级为规则拼接：{done['reply']!r}"

    def test_resume_unknown_thread_returns_404(self):
        """resume 的校验在开流之前 → 仍然是正常的 404（而不是 200 + error 事件）"""
        from main import app

        with TestClient(app) as client:
            resp = client.post("/api/coordinator/resume",
                               json={"thread_id": "no-such-thread",
                                     "sub_thread_id": "x:query", "answer": "1"},
                               headers=get_auth_headers("admin"))
            assert resp.status_code == 404

    def test_placeholder_stream_endpoint_removed(self):
        """原来那个无鉴权的 GET /stream/{thread_id} 占位端点应已删除"""
        from main import app

        with TestClient(app) as client:
            resp = client.get("/api/coordinator/stream/anything",
                              headers=get_auth_headers("admin"))
            assert resp.status_code == 404


# ================================================================
# 三、技能树 AI 流式端点
# ================================================================

class TestSkillTreeStream:

    def test_chat_requires_admin(self):
        """技能树 AI 仅管理员可用：普通用户应 403，而不是进到流里"""
        from main import app

        with TestClient(app) as client:
            resp = client.post("/api/skill-trees/whatever/chat",
                               json={"tree": {"name": "t", "nodes": [], "connections": []},
                                     "message": "hi"},
                               headers=get_auth_headers("user"))
            assert resp.status_code == 403, resp.text[:300]

    def test_old_get_stream_endpoint_removed(self):
        from main import app

        with TestClient(app) as client:
            resp = client.get("/api/skill-trees/whatever/chat/stream?thread_id=x",
                              headers=get_auth_headers("admin"))
            assert resp.status_code == 404


# ================================================================
# 四、表达力 / 习惯图标 流式端点
# ================================================================

class TestExpressionStream:
    """在**路由层**打桩业务函数：既不联网也不写库，专测 SSE 管道"""

    def test_generate_stream_stage_then_done(self, monkeypatch):
        import routers.expression as expr_mod
        from main import app

        async def fake_generate(types, user_id=None):
            return {"id": 999, "question": "你怎么看远程办公？",
                    "question_type": "hot_opinion", "hints": []}

        monkeypatch.setattr(expr_mod, "generate_question", fake_generate)

        with TestClient(app) as client:
            resp = client.post("/api/expression/generate",
                               json={"types": ["hot_opinion"]},
                               headers=get_auth_headers("user"))
            assert resp.status_code == 200
            events = parse_sse(resp.text)

        assert "generate" in stages_of(events), "缺少出题的阶段提示"
        done = done_of(events)
        assert done["id"] == 999
        assert done["question"] == "你怎么看远程办公？"

    def test_generate_custom_question_skips_ai_but_still_streams(self, monkeypatch):
        """自定义题目不走 AI → 只发一个 done（仍然是 SSE，前端只有一条解析路径）"""
        import routers.expression as expr_mod
        from main import app

        monkeypatch.setattr(expr_mod, "create_question",
                            lambda **kw: 1001)

        with TestClient(app) as client:
            resp = client.post("/api/expression/generate",
                               json={"custom_question": "自定义题目"},
                               headers=get_auth_headers("user"))
            assert resp.status_code == 200
            events = parse_sse(resp.text)

        assert types_of(events) == ["done"], f"不应有阶段事件：{types_of(events)}"
        assert done_of(events)["question"] == "自定义题目"

    def test_hints_validation_errors_stay_http(self):
        """校验错误（缺 question_id）必须是 400，不能变成 200 + error 事件"""
        from main import app

        with TestClient(app) as client:
            resp = client.post("/api/expression/generate-hints",
                               json={},
                               headers=get_auth_headers("user"))
            assert resp.status_code == 400


class TestHabitIconStream:

    def test_icon_stream_stage_then_done(self, monkeypatch):
        import routers.habits as habits_mod
        from main import app

        async def fake_icon(name, intro, category, user_id=None):
            return '<svg viewBox="0 0 64 64"><circle cx="32" cy="32" r="20"/></svg>'

        monkeypatch.setattr(habits_mod, "call_ai_for_icon", fake_icon)

        with TestClient(app) as client:
            resp = client.post("/api/habits/ai-icon",
                               json={"name": "早睡", "intro": "", "category": "health"},
                               headers=get_auth_headers("user"))
            assert resp.status_code == 200
            assert resp.headers.get("x-accel-buffering") == "no"
            events = parse_sse(resp.text)

        assert "icon" in stages_of(events)
        done = done_of(events)
        assert "<svg" in done["svg"]

    def test_empty_name_is_400(self):
        """参数校验在开流之前，仍然是正常的状态码"""
        from main import app

        with TestClient(app) as client:
            resp = client.post("/api/habits/ai-icon",
                               json={"name": "   ", "intro": "", "category": "health"},
                               headers=get_auth_headers("user"))
            assert resp.status_code == 400
