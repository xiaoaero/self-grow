"""
Self Grow — 2026-09-23 代码审查所修问题的回归测试

覆盖三类「修完很容易被改回去」的修复：

1. **评分不可用时不落库、不编造分数**（原来是失败就写一份默认 70 分）
2. **WebSocket 鉴权**（原来信任 `?user_id=` 且默认 1，等于可冒用他人身份与 ASR 密钥）
3. **资源归属校验**（`ensure_owner` / `_ensure_answer_owner`）

这些都是纯逻辑，不需要起服务，跑得很快。
"""

import pytest
from fastapi import HTTPException

from services.expression_service import (
    EvaluationUnavailable,
    _parse_evaluation_result,
    _validate_evaluation,
)


# ================================================================
# 一、评分：拿不到真分就说「暂不可用」，绝不编分
# ================================================================

class TestNoFakeScore:

    def test_missing_scores_raise_instead_of_defaulting(self):
        """缺分数维度 → 抛异常（原来每个维度都会兜底成 70 分）"""
        with pytest.raises(EvaluationUnavailable) as exc:
            _validate_evaluation({"scores": {"total": 85}})
        assert "不完整" in str(exc.value)

    def test_non_numeric_score_raise(self):
        """分数是字符串 → 同样算不合法"""
        with pytest.raises(EvaluationUnavailable):
            _validate_evaluation({
                "scores": {"total": "85", "fluency": 80, "logic": 80,
                           "content": 80, "language": 80},
            })

    def test_complete_scores_pass_and_are_clamped(self):
        """完整分数正常通过，且做 0~100 截断"""
        result = _validate_evaluation({
            "scores": {"total": 120, "fluency": -5, "logic": 80,
                       "content": 80, "language": 80},
        })
        assert result["scores"] == {
            "total": 100, "fluency": 0, "logic": 80, "content": 80, "language": 80,
        }

    def test_text_fields_still_have_fallback(self):
        """文字部分（优点/改进/建议）保留兜底 —— 它们不构成误导性的量化结论"""
        result = _validate_evaluation({
            "scores": {"total": 80, "fluency": 80, "logic": 80,
                       "content": 80, "language": 80},
        })
        assert result["strengths"] and result["improvements"] and result["suggestion"]

    @pytest.mark.parametrize("raw", [
        "这不是 JSON",
        "```json\n{坏掉的 json}\n```",
        "",
    ])
    def test_unparsable_output_raises(self, raw):
        """LLM 返回非 JSON → 抛异常，而不是返回一份编造的分数

        ⚠️ 这条是本次修复的**第二条**假分路径：原来只在
        `_parse_evaluation_result` 里也调了 `_fallback_evaluation()`，
        于是「模型答非所问」会被静默变成「70 分」并落库。
        """
        with pytest.raises(EvaluationUnavailable):
            _parse_evaluation_result(raw)

    def test_valid_json_block_is_parsed(self):
        good = (
            "```json\n"
            '{"scores": {"total": 88, "fluency": 90, "logic": 85, '
            '"content": 88, "language": 86}, "strengths": ["清晰"], '
            '"improvements": ["再具体些"], "suggestion": "多用连接词"}\n'
            "```"
        )
        result = _parse_evaluation_result(good)
        assert result["scores"]["total"] == 88
        assert result["strengths"] == ["清晰"]


# ================================================================
# 二、WebSocket 鉴权
# ================================================================

class _FakeWS:
    """只提供 query_params 的假 WebSocket"""

    def __init__(self, params=None):
        self.query_params = params or {}


class TestWebSocketAuth:

    def test_no_token_is_rejected(self):
        from routers.deps import authenticate_websocket
        assert authenticate_websocket(_FakeWS({})) is None

    def test_invalid_token_is_rejected(self):
        from routers.deps import authenticate_websocket
        assert authenticate_websocket(_FakeWS({"token": "not-a-real-jwt"})) is None

    def test_user_id_param_alone_is_not_enough(self):
        """旧写法 `?user_id=1` 必须失效 —— 否则等于客户端自己声明身份"""
        from routers.deps import authenticate_websocket
        assert authenticate_websocket(_FakeWS({"user_id": "1"})) is None


# ================================================================
# 三、资源归属校验
# ================================================================

class TestEnsureOwner:

    def test_same_owner_passes(self):
        from routers.deps import ensure_owner
        ensure_owner({"user_id": 7}, {"id": 7})      # 不抛异常即通过

    def test_other_owner_is_403(self):
        from routers.deps import ensure_owner
        with pytest.raises(HTTPException) as exc:
            ensure_owner({"user_id": 7}, {"id": 8})
        assert exc.value.status_code == 403

    def test_missing_user_id_is_not_blocked(self):
        """查不到 user_id 时放行而不是误杀（属实现疏漏，不该把正常用户挡掉）"""
        from routers.deps import ensure_owner
        ensure_owner({}, {"id": 8})

    def test_answer_owner_compares_username_not_id(self):
        """表达训练的作答记录：user_id 字段存的是**用户名**

        ⚠️ 所以它不能复用 ensure_owner（那比的是 int 型 id）——
        这里用真实数据形态钉死这个约定。
        """
        from routers.expression import _ensure_answer_owner

        _ensure_answer_owner({"user_id": "test"}, {"id": 2, "name": "test"})
        with pytest.raises(HTTPException) as exc:
            _ensure_answer_owner({"user_id": "admin"}, {"id": 2, "name": "test"})
        assert exc.value.status_code == 403
