"""
Self Grow — 协调 Agent 反问（interrupt）交互的回归测试

覆盖三类真实踩到的问题：

1. **连点提交 → 子图重复执行**
   /resume 是「读 state → await 子图 → 写 state」，两次并发请求会在 await 点交错，
   两个都读到「该域还没完成」，于是子图跑两次。写库型工具会重复写入
   （连点发送按钮 = 创建两个任务 / 打卡两次）。
   → 现在由服务端会话锁返回 409 兜住（前端防抖只是缓解，挡不住重试/多标签页/脚本）

2. **跳过一个反问 → 这条记录的总结永远不会生成**
   跳过的域永远进不了 completed_domains，`pending_domains ⊆ completed` 恒不成立
   → `final_reply` 永远是空。
   → 现在 `/resume` 支持 `skip=True`：不重跑子图，只把该域标记为已完成

3. **两个反问依次回答** → 第二个回答完必须产出总结（这是正常路径，不能回归）

所有 LLM 调用都在模块层打桩，不联网、不写库。
"""

import asyncio
import json

import httpx
import pytest

from helpers import get_auth_headers


# ================================================================
# 打桩：一个能按角色分派、并统计子 Agent 执行次数的假 LLM
# ================================================================

class FakeLLM:
    """协调Agent → 路由；子 Agent → 首次反问、回答后给结论；总结 → 逐字流"""

    def __init__(self, domains=("habit", "task")):
        self.domains = list(domains)
        self.sub_runs = 0          # 子 Agent 被真正执行了几次

    def bind_tools(self, tools, **kw):
        return self

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
        from langchain_core.messages import AIMessage, ToolMessage

        text = self._flatten(msgs)
        if "协调Agent" in text:
            return AIMessage(content=json.dumps({
                "domains": [{"domain": d, "reason": "测试", "instruction": f"{d} 任务"}
                            for d in self.domains]
            }, ensure_ascii=False))

        self.sub_runs += 1
        # 已经出现过 ToolMessage → 说明反问过了，这次给结论
        if any(isinstance(m, ToolMessage) for m in msgs):
            return AIMessage(content="已按要求处理完成。")
        return AIMessage(
            content="",
            tool_calls=[{
                "name": "ask_user",
                "args": {"question": "请确认一下具体信息？", "options": ["甲", "乙"]},
                "id": "call_ask_1",
            }],
        )

    async def astream(self, msgs):
        from langchain_core.messages import AIMessageChunk

        for piece in ["两个域", "都完成了", "。"]:
            yield AIMessageChunk(content=piece)


@pytest.fixture
def fake_llm(monkeypatch):
    """把三层 LLM 入口都换掉（router / synthesize 是模块级绑定，agents 是函数内 import）"""
    from services import llm as llm_mod
    import services.coordinator.router_node as rn
    import services.coordinator.synthesize_node as sn

    fake = FakeLLM()
    monkeypatch.setattr(llm_mod, "get_llm", lambda *a, **k: fake)
    monkeypatch.setattr(rn, "get_llm", lambda *a, **k: fake)
    monkeypatch.setattr(sn, "get_llm", lambda *a, **k: fake)
    return fake


@pytest.fixture(autouse=True)
def clean_session_locks():
    """会话锁是模块级全局 —— 每个用例前后都清一遍，避免相互影响"""
    import routers.coordinator as coord

    coord._inflight.clear()
    yield
    coord._inflight.clear()


# ================================================================
# 工具
# ================================================================

def parse_sse(raw: str) -> list:
    out = []
    for block in raw.split("\n\n"):
        block = block.strip()
        if not block or block.startswith(":"):
            continue
        for line in block.splitlines():
            if line.startswith("data: "):
                out.append(json.loads(line[6:]))
    return out


def done_of(raw: str) -> dict:
    dones = [e for e in parse_sse(raw) if e.get("type") == "done"]
    assert dones, f"没有 done 事件：{raw[:300]}"
    return dones[-1]


def start_conversation(client, headers, message="打卡并建个任务") -> dict:
    """发一条消息，返回 done（里面有 thread_id 与 interrupts）"""
    resp = client.post("/api/coordinator/chat", json={"message": message}, headers=headers)
    assert resp.status_code == 200
    return done_of(resp.text)


# ================================================================
# 一、正常路径：两个反问依次回答 → 第二个回答完出总结
# ================================================================

class TestSequentialAnswers:

    def test_two_interrupts_then_summary(self, fake_llm):
        from main import app
        from fastapi.testclient import TestClient

        headers = get_auth_headers("admin")
        with TestClient(app) as client:
            first = start_conversation(client, headers)

            assert len(first["interrupts"]) == 2, "两个域应各反问一次"
            assert first["reply"] == "", "还有域没完成时不应给最终回复"

            subs = [(i["domain"], i["sub_thread_id"]) for i in first["interrupts"]]

            r1 = client.post("/api/coordinator/resume", headers=headers, json={
                "thread_id": first["thread_id"],
                "sub_thread_id": subs[0][1],
                "answer": "答案一",
            })
            d1 = done_of(r1.text)
            assert d1["reply"] == "", "只完成一个域时不应总结"
            assert d1["completed_domains"] == [subs[0][0]]
            assert len(d1["interrupts"]) == 0, "这个域没有新反问"
            # 另一个域的反问仍在（前端靠这个决定还显示几张卡片）
            assert len(d1.get("pending_domains") or []) == 2

            r2 = client.post("/api/coordinator/resume", headers=headers, json={
                "thread_id": first["thread_id"],
                "sub_thread_id": subs[1][1],
                "answer": "答案二",
            })
            d2 = done_of(r2.text)
            assert d2["reply"], "两个域都完成后必须产出总结"
            assert "都完成了" in d2["reply"]

    def test_interrupt_payload_shape(self, fake_llm):
        """反问事件必须带齐前端渲染需要的字段（id / domain / sub_thread_id / options）"""
        from main import app
        from fastapi.testclient import TestClient

        with TestClient(app) as client:
            first = start_conversation(client, get_auth_headers("admin"))

        for it in first["interrupts"]:
            for field in ("id", "domain", "sub_thread_id", "question",
                          "options", "domain_label"):
                assert field in it, f"interrupt 缺字段 {field}：{it}"
            assert it["sub_thread_id"].endswith(":" + it["domain"]), \
                "sub_thread_id 必须能以 ':' 切出 domain（resume 靠它定位子图）"


# ================================================================
# 二、跳过：skip=True 必须让编排能继续走到总结
# ================================================================

class TestSkipInterrupt:

    def test_skip_marks_domain_completed_and_summary_still_generated(self, fake_llm):
        """核心回归：跳过的域必须算"已完成"，否则这条记录的总结永远为空

        （改造前前端 `skipInterrupt` 只是不调接口，域永久卡在未完成）
        """
        from main import app
        from fastapi.testclient import TestClient

        headers = get_auth_headers("admin")
        with TestClient(app) as client:
            first = start_conversation(client, headers)
            subs = [(i["domain"], i["sub_thread_id"]) for i in first["interrupts"]]
            runs_before = fake_llm.sub_runs

            # 跳过第一个
            rs = client.post("/api/coordinator/resume", headers=headers, json={
                "thread_id": first["thread_id"],
                "sub_thread_id": subs[0][1],
                "skip": True,
            })
            ds = done_of(rs.text)

            assert ds["completed_domains"] == [subs[0][0]], \
                f"跳过的域必须进 completed_domains：{ds['completed_domains']}"
            assert len(ds["interrupts"]) == 0, "跳过后该域的反问要被移除"
            assert fake_llm.sub_runs == runs_before, \
                "跳过不应重新执行子图（省一次 LLM 调用，也避免误写库）"

            # 再回答另一个 → 必须出总结
            r2 = client.post("/api/coordinator/resume", headers=headers, json={
                "thread_id": first["thread_id"],
                "sub_thread_id": subs[1][1],
                "answer": "答案二",
            })
            d2 = done_of(r2.text)
            assert d2["reply"], "跳过一个域后，另一个完成时必须能总结（否则总结永远为空）"

    def test_skip_is_idempotent(self, fake_llm):
        """重复跳过同一域 → 第二次走幂等分支，不重复执行也不报错"""
        from main import app
        from fastapi.testclient import TestClient

        headers = get_auth_headers("admin")
        with TestClient(app) as client:
            first = start_conversation(client, headers)
            sub = first["interrupts"][0]["sub_thread_id"]
            body = {"thread_id": first["thread_id"], "sub_thread_id": sub, "skip": True}

            d1 = done_of(client.post("/api/coordinator/resume", headers=headers, json=body).text)
            d2 = done_of(client.post("/api/coordinator/resume", headers=headers, json=body).text)

        assert d1["completed_domains"] == d2["completed_domains"], \
            "重复跳过不应改变已完成集合"


# ================================================================
# 三、并发 / 连点：会话锁必须挡住，且子图只执行一次
# ================================================================

def run_concurrent_resumes(app, headers, thread_id, targets):
    """用 ASGITransport 真正并发地打 /resume（TestClient 是同步的，发不出并发）"""
    async def go():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
            async def one(sub_thread_id, answer):
                r = await c.post("/api/coordinator/resume",
                                 headers=headers,
                                 json={"thread_id": thread_id,
                                       "sub_thread_id": sub_thread_id,
                                       "answer": answer})
                return r.status_code, r.text

            return await asyncio.gather(*[one(sub, ans) for sub, ans in targets])

    return asyncio.run(go())


class TestConcurrentResume:

    def test_double_submit_same_interrupt_is_rejected(self, fake_llm):
        """连点发送：第二次必须被 409 挡住 → 子图只执行一次（不重复写库）"""
        from main import app
        from fastapi.testclient import TestClient

        headers = get_auth_headers("admin")
        # 单域场景：这个域就是最后一个待完成域，第二次请求会走到"总结"那一步 ——
        # 正是改造前真正会重复执行 + 重复总结的路径
        import services.coordinator.router_node as rn
        single = FakeLLM(domains=("habit",))
        rn.get_llm = lambda *a, **k: single

        with TestClient(app) as client:
            first = start_conversation(client, headers, message="打卡")
            assert len(first["interrupts"]) == 1
            sub = first["interrupts"][0]["sub_thread_id"]

            # ⚠️ 子 Agent 的 get_llm 是函数内 import（services.llm.get_llm），
            # 所以它的执行次数记在 fake_llm 上，不是 single（single 只被 router 用）
            runs_before = fake_llm.sub_runs
            results = run_concurrent_resumes(app, headers, first["thread_id"],
                                             [(sub, "连点A"), (sub, "连点B")])
            runs_delta = fake_llm.sub_runs - runs_before

            statuses = sorted(code for code, _ in results)
            assert statuses == [200, 409], \
                f"应一个成功一个 409，实际 {statuses} → 连点会让子图重复执行"

            rejected = [body for code, body in results if code == 409]
            assert "处理中" in rejected[0], "409 的提示要能看懂"

        assert runs_delta == 1, \
            f"子 Agent 只应执行 1 次（否则写库型工具会重复写入），实际 {runs_delta}"

    def test_two_different_interrupts_are_serialized(self, fake_llm):
        """两个不同域同时提交 → 一个成功、一个 409

        这是**有意的**：服务端宁可拒绝也不并发改写共享 state。
        前端据此把「一次只能提交一张卡片」做成显式约束（禁用其它卡片 + 提示），
        而不是像改造前那样**静默吞掉**第二次提交（用户点了没反应）。
        """
        from main import app
        from fastapi.testclient import TestClient

        headers = get_auth_headers("admin")
        with TestClient(app) as client:
            first = start_conversation(client, headers)
            subs = [i["sub_thread_id"] for i in first["interrupts"]]

            results = run_concurrent_resumes(
                app, headers, first["thread_id"],
                [(subs[0], "甲"), (subs[1], "乙")],
            )

        statuses = sorted(code for code, _ in results)
        assert statuses == [200, 409], f"应一个成功一个 409，实际 {statuses}"

    def test_lock_released_after_success(self, fake_llm):
        """锁是用后即释的：前一个请求结束后，后续请求必须能正常提交（不能把会话锁死）"""
        from main import app
        from fastapi.testclient import TestClient

        headers = get_auth_headers("admin")
        with TestClient(app) as client:
            first = start_conversation(client, headers)
            subs = [(i["domain"], i["sub_thread_id"]) for i in first["interrupts"]]

            for i, (dom, sub) in enumerate(subs, 1):
                r = client.post("/api/coordinator/resume", headers=headers, json={
                    "thread_id": first["thread_id"],
                    "sub_thread_id": sub,
                    "answer": f"答案{i}",
                })
                assert r.status_code == 200, \
                    f"第 {i} 次提交被拒（锁没释放？）：{r.status_code} {r.text[:200]}"
                done_of(r.text)

    def test_lock_not_leaked_when_runner_fails(self, fake_llm, monkeypatch):
        """业务中途抛异常 → 锁必须在 runner 的 finally 里释放，不能把会话永久锁死"""
        from main import app
        from fastapi.testclient import TestClient
        import routers.coordinator as coord

        headers = get_auth_headers("admin")
        with TestClient(app) as client:
            first = start_conversation(client, headers)
            sub = first["interrupts"][0]["sub_thread_id"]

            async def boom(*a, **k):
                raise RuntimeError("模拟子图崩溃")

            monkeypatch.setattr(coord, "resume_subgraph", boom)
            r = client.post("/api/coordinator/resume", headers=headers, json={
                "thread_id": first["thread_id"], "sub_thread_id": sub, "answer": "x",
            })
            # 流已经开始，所以状态码仍是 200，但 body 里是 error 事件
            assert "error" in r.text
            assert first["thread_id"] not in coord._inflight, \
                "异常路径没释放会话锁 → 这个会话以后再也提交不了"


# ================================================================
# 四、鉴权
# ================================================================

class TestResumeAuth:

    def test_resume_requires_auth(self):
        from main import app
        from fastapi.testclient import TestClient

        with TestClient(app) as client:
            r = client.post("/api/coordinator/resume", json={
                "thread_id": "x", "sub_thread_id": "a:habit", "answer": "1",
            })
            assert r.status_code == 401

    def test_resume_unknown_thread_404(self):
        from main import app
        from fastapi.testclient import TestClient

        with TestClient(app) as client:
            r = client.post("/api/coordinator/resume",
                            headers=get_auth_headers("admin"),
                            json={"thread_id": "no-such", "sub_thread_id": "a:habit",
                                  "answer": "1"})
            assert r.status_code == 404
