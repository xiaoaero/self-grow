"""
AI 分析：提示词 + 模型来源 的回归测试

两件事都是 2026-09-24 用户提的：

① **摘要里全是废话** —— 用户反馈："我搜索的就是 ai、agent、llm，让它不要说那种
   GitHub 近期出现大量的 agent 那种废话了"。
   根因不是模型笨：材料**本来就是按 AI/Agent/LLM 检索来的**，
   模型从"一堆 agent 项目"里归纳出"agent 很火"是必然的 ——
   那是**检索条件本身**，零信息量。提示词必须从源头堵住。

② 生成时用的模型配置 —— `get_llm()` 漏传 user_id 会静默退化成 user_id=1 的配置
   （项目统一约定，见 services/llm.py）。本模块以前就漏了。
"""

import inspect
import io
import os

from services.aiconsult_analysis_service import SUMMARY_SYSTEM, TRANSLATE_SYSTEM

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(BASE, "..")


def _src(rel):
    return io.open(os.path.join(ROOT, rel), encoding="utf-8").read()


# ================================================================
# ① 摘要提示词：不许再说「AI 很热 / Agent 扎堆」
# ================================================================

class TestSummaryPrompt:
    """提示词要「全面但精炼」—— 该说的说清，废话一句不留"""

    def test_states_the_material_is_already_ai_filtered(self):
        """必须让模型知道：这批材料本身就是 AI/Agent/LLM 检索结果

        不知道这一点，它必然把检索条件当成发现写进摘要。
        """
        p = SUMMARY_SYSTEM
        assert "检索" in p, "没说明材料的来源（模型不知道它就只能复述主题）"
        assert "Agent" in p and "LLM" in p, "没点明具体是哪几个主题"

    def test_bans_the_tautology_with_examples(self):
        """禁止项要给**具体例句** —— 抽象规则（"不要空话"）对模型没用"""
        p = SUMMARY_SYSTEM
        assert "废话" in p or "禁止" in p, "没写禁止项"
        # 这三句是用户点名的那类
        for phrase in ("扎堆", "升温", "值得关注"):
            assert phrase in p, f"禁止清单里缺少例句「{phrase}」"

    def test_demands_material_specific_facts(self):
        """正向要求：说只有这批材料里才有的具体信息"""
        p = SUMMARY_SYSTEM
        assert "只有这批材料里才有" in p, "没要求写「材料里才有的」具体信息"
        assert "refs" in p, "丢了 refs（要点要有出处）"

    def test_trend_is_not_a_recap(self):
        """trend 只写真正新的东西，不写综述/常识"""
        p = SUMMARY_SYSTEM
        assert "真正新" in p
        assert "综述" in p

    def test_prompt_stays_short(self):
        """提示词本身也要精炼 —— 超过 20 行说明又开始堆砌了"""
        assert len(SUMMARY_SYSTEM.splitlines()) <= 20, "提示词又变长了"


def test_translate_prompt_unchanged_intent():
    """翻译/打分那块的职责没被带偏（它只负责翻译和打分）"""
    assert "intro_zh" in TRANSLATE_SYSTEM and "score" in TRANSLATE_SYSTEM


def test_translate_task_is_not_token_capped():
    """翻译/打分任务**不能**限制输出 token

    它一次要吐「N 个仓库简介 + 数十条资讯的中文标题/摘要/打分」，
    JSON 体积远大于摘要任务。撞上限 → 输出被截断 → JSON 没闭合 → 解析失败 →
    `return [], []` → **仓库中文简介和资讯热度榜整块消失**，
    而日志里只有一句「✅ AI 分析已生成」。
    2026-09-24 实测：`aiconsult_repo_intro` 0 行、`news_hot` 无记录，
    用户看到的是"资讯热度榜一直空着"，查不到任何原因。
    """
    from services import aiconsult_analysis_service as m
    assert m.TRANSLATE_MAX_TOKENS is None, (
        "翻译/打分任务又被限制了 token —— 输出会被截断，资讯热度榜会变成空白"
    )


def test_json_parse_failure_is_logged():
    """解析失败必须留下痕迹 —— 否则「榜空着」永远查不到原因"""
    src = _src(os.path.join("services", "aiconsult_analysis_service.py"))
    assert "不是合法 JSON" in src, "模型输出解析失败时没有日志"


# ================================================================
# ② user_id 必须一路传到 get_llm()
# ================================================================

class TestUserIdThreading:

    def test_signatures_accept_user_id(self):
        from services import aiconsult_analysis_service as m

        for fn in (m._call_llm_json, m._task_summary, m._task_translate,
                   m._generate, m._run_and_store, m.ensure_analysis):
            params = inspect.signature(fn).parameters
            assert "user_id" in params, f"{fn.__name__} 的签名里没有 user_id"

    def test_router_passes_current_user(self):
        src = _src(os.path.join("routers", "aiconsult.py"))
        assert 'ensure_analysis(user["id"])' in src, "路由没把当前用户传下去"

    def test_llm_call_site_passes_user_id(self):
        """静态护栏：本模块所有 `get_llm(` 调用都必须带 user_id=

        漏传**不报错**（内部 `user_id or 1` 静默兜底），
        表现是"我在用户中心换了模型，AI 分析却还在用旧的"。
        """
        src = _src(os.path.join("services", "aiconsult_analysis_service.py"))
        assert "user_id=user_id" in src, "get_llm() 漏传 user_id"


def test_every_get_llm_call_project_wide_passes_user_id():
    """全项目扫一遍：任何 `get_llm(...)` 调用都必须带 user_id=

    ⚠️ 这是**项目级硬约定**（见 services/llm.py 与 MEMORY.md）。
    漏传的症状是"切了模型不生效"，而且完全静默 —— 只能靠静态断言兜住。

    判定方式：从每个 `get_llm(` 往后取 200 个字符（够覆盖多行调用），
    里面必须出现 `user_id=`。
    """
    import re

    problems = []
    for sub in ("services", "routers"):
        d = os.path.join(ROOT, sub)
        for dirpath, _dirs, files in os.walk(d):
            if ".pixi" in dirpath or "__pycache__" in dirpath:
                continue
            for name in files:
                if not name.endswith(".py"):
                    continue
                path = os.path.join(dirpath, name)
                text = io.open(path, encoding="utf-8").read()
                for m in re.finditer(r"get_llm\s*\(", text):
                    # 跳过 `def get_llm(` 定义本身
                    prefix = text[max(0, m.start() - 5):m.start()]
                    if prefix.endswith("def "):
                        continue
                    # 跳过注释里提到的 `get_llm()`（说明文字不是调用，
                    # 如 services/llm.py 缓存那段注释 —— 不跳会误报）
                    line_start = text.rfind("\n", 0, m.start()) + 1
                    if text[line_start:m.start()].lstrip().startswith("#"):
                        continue
                    window = text[m.start():m.start() + 200]
                    if "user_id=" not in window:
                        lineno = text[:m.start()].count("\n") + 1
                        problems.append(
                            f"  {os.path.relpath(path, ROOT)}:{lineno}"
                        )
    assert not problems, (
        "以下 get_llm() 调用没传 user_id —— 会静默退化成 user_id=1 的模型配置：\n"
        + "\n".join(problems)
    )
