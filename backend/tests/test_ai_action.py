"""
Self Grow — AI 行动解析功能测试

测试后端 ai-chat 和 ai-submit 端点。
使用 pytest + httpx.AsyncClient。
"""

import os
import sys
import json
import pytest
from unittest.mock import patch

# 确保 backend 目录在 Python 路径中
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient
from main import app

# ================================================================
# 测试数据
# ================================================================

TEST_USER_ID = 1  # test 用户，由 init_db() 创建

# JWT 改造后所有端点都需凭证
def _auth():
    from helpers import get_auth_headers
    return get_auth_headers('user')


# ================================================================
# 辅助函数
# ================================================================

def _client():
    """创建测试客户端，附带默认 user_id 查询参数"""
    with TestClient(app) as c:
        yield c


# ================================================================
# Mock 数据
# ================================================================

MOCK_AI_TEXT_RESPONSE = {"content": "我了解到你今天下午花了2小时学习React。请问这是属于哪个维度呢？是学习、工作还是其他方面？"}
MOCK_AI_TOOLCALL_RESPONSE = {
    "tool_calls": [
        {
            "id": "call_1",
            "name": "submit_actions",
            "arguments": {
                "summary": "已识别到以下记录，请确认",
                "actions": [
                    {
                        "category_id": "study",
                        "duration": 120,
                        "note": "学习React，完成了状态管理章节",
                        "dimension_exp": 60,
                    }
                ],
            },
        }
    ]
}


@pytest.fixture(autouse=True)
def mock_ai_service():
    """自动 mock AI 服务，避免真实 API 调用"""
    with patch("routers.actions.call_action_ai") as mock:
        mock.return_value = MOCK_AI_TEXT_RESPONSE
        yield mock


# ================================================================
# TC-01: POST /api/actions/ai-chat — 正常消息
# ================================================================

def test_ai_chat_normal(mock_ai_service):
    """TC-01: 发送正常消息，AI 返回回复"""
    with TestClient(app) as client:
        payload = {
            "messages": [
                {"role": "user", "content": "今天下午学习了2小时React"}
            ]
        }
        resp = client.post(f"/api/actions/ai-chat?user_id={TEST_USER_ID}", json=payload, headers=_auth())
        assert resp.status_code == 200
        data = resp.json()
        assert "content" in data
        assert len(data["content"]) > 0
        mock_ai_service.assert_called_once()


# ================================================================
# TC-02: POST /api/actions/ai-chat — 空消息
# ================================================================

def test_ai_chat_empty_messages(mock_ai_service):
    """TC-02: 发送空消息列表，AI 应返回引导消息"""
    with TestClient(app) as client:
        payload = {"messages": []}
        resp = client.post(f"/api/actions/ai-chat?user_id={TEST_USER_ID}", json=payload, headers=_auth())
        assert resp.status_code == 200
        data = resp.json()
        assert "content" in data


# ================================================================
# TC-03: POST /api/actions/ai-chat — 多轮对话
# ================================================================

def test_ai_chat_multi_turn(mock_ai_service):
    """TC-03: 模拟多轮对话，先模糊再补充"""
    with TestClient(app) as client:
        # 第1轮：模糊描述
        messages = [{"role": "user", "content": "今天好累"}]
        resp1 = client.post(f"/api/actions/ai-chat?user_id={TEST_USER_ID}", json={"messages": messages}, headers=_auth())
        assert resp1.status_code == 200
        data1 = resp1.json()
        assert "content" in data1

        # 改变 mock 返回值模拟第2轮 AI 提交行动
        mock_ai_service.return_value = MOCK_AI_TOOLCALL_RESPONSE

        # 第2轮：补充细节
        messages.append({"role": "assistant", "content": data1["content"]})
        messages.append({"role": "user", "content": "下午学了2小时React，晚上跑了30分钟步"})
        resp2 = client.post(f"/api/actions/ai-chat?user_id={TEST_USER_ID}", json={"messages": messages}, headers=_auth())
        assert resp2.status_code == 200
        data2 = resp2.json()
        # 第2轮应该返回 tool_calls
        assert "tool_calls" in data2
        assert mock_ai_service.call_count == 2


# ================================================================
# TC-04: POST /api/actions/ai-submit — 单条行动
# ================================================================

def test_ai_submit_single():
    """TC-04: 提交单条学习行动记录"""
    with TestClient(app) as client:
        payload = {
            "actions": [
                {
                    "category_id": "study",
                    "duration": 120,
                    "note": "学习React，完成了状态管理章节",
                    "dimension_exp": 60,
                }
            ]
        }
        resp = client.post(f"/api/actions/ai-submit?user_id={TEST_USER_ID}", json=payload, headers=_auth())
        assert resp.status_code == 200
        data = resp.json()
        assert "records" in data
        assert len(data["records"]) == 1
        record = data["records"][0]
        assert record["category_id"] == "study"
        assert record["category_name"] == "学习"
        # EXP 应该被后端二次校验为 floor(120/20)*10 = 60
        assert record["exp_earned"] == 60
        assert "today_stats" in data
        assert "exp_result" in data


# ================================================================
# TC-05: POST /api/actions/ai-submit — 多条行动（多维度）
# ================================================================

def test_ai_submit_multi():
    """TC-05: 批量提交多条行动记录（学习+健康运动）"""
    with TestClient(app) as client:
        payload = {
            "actions": [
                {
                    "category_id": "study",
                    "duration": 120,
                    "note": "学习React",
                    "dimension_exp": 60,
                },
                {
                    "category_id": "health",
                    "sub_type": "health-sport",
                    "duration": 30,
                    "note": "跑步30分钟",
                    "dimension_exp": 7.5,
                },
            ]
        }
        resp = client.post(f"/api/actions/ai-submit?user_id={TEST_USER_ID}", json=payload, headers=_auth())
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["records"]) == 2
        # 验证两条记录的维度不同
        cat_ids = [r["category_id"] for r in data["records"]]
        assert "study" in cat_ids
        assert "health" in cat_ids


# ================================================================
# TC-06: POST /api/actions/ai-submit — 空列表
# ================================================================

def test_ai_submit_empty():
    """TC-06: 提交空列表"""
    with TestClient(app) as client:
        payload = {"actions": []}
        resp = client.post(f"/api/actions/ai-submit?user_id={TEST_USER_ID}", json=payload, headers=_auth())
        assert resp.status_code == 200
        data = resp.json()
        assert data["records"] == []


# ================================================================
# TC-07: POST /api/actions/ai-submit — 无效 category_id
# ================================================================

def test_ai_submit_invalid_category():
    """TC-07: 提交无效的维度 ID，该条应被跳过"""
    with TestClient(app) as client:
        payload = {
            "actions": [
                {
                    "category_id": "invalid_cat",
                    "note": "test",
                    "dimension_exp": 10,
                }
            ]
        }
        resp = client.post(f"/api/actions/ai-submit?user_id={TEST_USER_ID}", json=payload, headers=_auth())
        assert resp.status_code == 200
        data = resp.json()
        # 无效维度被跳过，records 为空
        assert len(data["records"]) == 0


# ================================================================
# TC-08: POST /api/actions/ai-submit — 后端 EXP 二次校验
# ================================================================

def test_ai_submit_exp_override():
    """TC-08: AI 提交的 EXP 与后端计算不一致时，以后端为准"""
    with TestClient(app) as client:
        payload = {
            "actions": [
                {
                    "category_id": "study",
                    "duration": 65,
                    "note": "学习65分钟",
                    "dimension_exp": 999,  # AI 故意算错
                }
            ]
        }
        resp = client.post(f"/api/actions/ai-submit?user_id={TEST_USER_ID}", json=payload, headers=_auth())
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["records"]) == 1
        # 后端二次计算：floor(65/20)*10 = 30
        assert data["records"][0]["exp_earned"] == 30


# ================================================================
# EXP 计算正确性测试（直接测 calculate_exp）
# ================================================================

def test_exp_study():
    """TC-E1: 学习 EXP 计算"""
    from models.constants import calculate_exp

    cases = [
        (20, 10),   # floor(20/20)*10 = 10
        (19, 0),    # floor(19/20)*10 = 0
        (40, 20),   # floor(40/20)*10 = 20
        (99, 40),   # floor(99/20)*10 = 40
        (65, 30),   # floor(65/20)*10 = 30
        (120, 60),  # floor(120/20)*10 = 60
        (0, 0),     # 边界
    ]
    for duration, expected in cases:
        result = calculate_exp("study", duration)
        assert result["dimension_exp"] == expected, \
            f"study duration={duration}: expected {expected}, got {result['dimension_exp']}"
        # global_rate = 1.0
        assert result["global_exp"] == expected


def test_exp_health_sport():
    """TC-E2: 健康-运动 EXP 计算"""
    from models.constants import calculate_exp

    cases = [
        (60, 15),    # floor(60/15)*3.75 = 15
        (30, 7.5),   # floor(30/15)*3.75 = 7.5
        (14, 0),     # 不足15分钟
        (90, 22.5),  # floor(90/15)*3.75 = 22.5
    ]
    for duration, expected in cases:
        result = calculate_exp("health", duration, sub_type="health-sport")
        assert abs(result["dimension_exp"] - expected) < 0.01, \
            f"health-sport duration={duration}: expected {expected}, got {result['dimension_exp']}"


def test_exp_health_sleep():
    """TC-E3: 健康-睡眠 EXP 计算"""
    from models.constants import calculate_exp

    # 23:00→07:00，时长8h，23:00前睡
    result = calculate_exp("health", 0, sub_type="health-sleep",
                           sleep_start="23:00", sleep_end="07:00")
    assert result["sleep_valid"] is True
    assert result["dimension_exp"] >= 20  # 基础20EXP

    # 23:08→07:00，延后8分钟，基础18 + 无规律加成（默认streak=0） = 18
    result = calculate_exp("health", 0, sub_type="health-sleep",
                           sleep_start="23:08", sleep_end="07:00")
    assert result["sleep_valid"] is True
    assert abs(result["dimension_exp"] - 18) < 0.01  # (20 - 8/4) + 0 = 18

    # 00:20→07:00，延后80分钟，基础0 + 睡觉时间00:20超出规律范围(23:00~00:00)，无规律加成
    result = calculate_exp("health", 0, sub_type="health-sleep",
                           sleep_start="00:20", sleep_end="07:00")
    assert result["sleep_valid"] is True
    assert result["dimension_exp"] == 0  # 0 + 0 = 0

    # 01:00→11:00，时长10h>9h，无效
    result = calculate_exp("health", 0, sub_type="health-sleep",
                           sleep_start="01:00", sleep_end="11:00")
    assert result["sleep_valid"] is False


def test_exp_relation_offline():
    """TC-E4: 关系-线下 EXP"""
    from models.constants import calculate_exp

    result = calculate_exp("relation", 0, sub_type="relation-offline")
    assert result["dimension_exp"] == 80


def test_exp_relation_online():
    """TC-E5: 关系-线上 EXP"""
    from models.constants import calculate_exp

    cases = [
        (60, 40),   # floor(60/30)*20 = 40
        (30, 20),   # floor(30/30)*20 = 20
        (29, 0),    # 不足30分钟
        (90, 60),   # floor(90/30)*20 = 60
    ]
    for duration, expected in cases:
        result = calculate_exp("relation", duration, sub_type="relation-online")
        assert result["dimension_exp"] == expected, \
            f"relation-online duration={duration}: expected {expected}, got {result['dimension_exp']}"


def test_exp_work():
    """TC-E6: 工作 EXP"""
    from models.constants import calculate_exp

    assert calculate_exp("work", 0, sub_type="work-daily")["dimension_exp"] == 10
    assert calculate_exp("work", 0, sub_type="work-overtime-weekday")["dimension_exp"] == 20
    assert calculate_exp("work", 0, sub_type="work-overtime-weekend")["dimension_exp"] == 30


def test_exp_create():
    """TC-E7: 创作 EXP"""
    from models.constants import calculate_exp

    # 产出 60分钟
    result = calculate_exp("create", 60, sub_type="create-output")
    assert result["dimension_exp"] == 120  # 60*2

    # 素材 60分钟
    result = calculate_exp("create", 60, sub_type="create-material")
    assert result["dimension_exp"] == 40  # floor(60/30)*20

    # 发布
    result = calculate_exp("create", 0, sub_type="create-publish")
    assert result["dimension_exp"] == 160


def test_exp_finance():
    """TC-E8: 财务 EXP"""
    from models.constants import calculate_exp

    # 学习梳理 60分钟
    result = calculate_exp("finance", 60, sub_type="finance-study")
    assert abs(result["dimension_exp"] - 80) < 0.01  # 60*4/3

    # 半月复盘
    result = calculate_exp("finance", 0, sub_type="finance-review")
    assert result["dimension_exp"] == 50


def test_exp_hobby():
    """TC-E9: 爱好 EXP"""
    from models.constants import calculate_exp

    result = calculate_exp("hobby", 60)
    assert abs(result["dimension_exp"] - 40) < 0.01  # 60*2/3


def test_exp_soul():
    """TC-E10: 魅力 EXP"""
    from models.constants import calculate_exp

    result = calculate_exp("soul", 60)
    assert abs(result["dimension_exp"] - 50) < 0.01  # 60*5/6


# ================================================================
# 模型验证测试
# ================================================================

def test_pydantic_models():
    """验证 Pydantic 模型序列化/反序列化"""
    from schemas.api import AIChatActionRequest, AISubmitActionItem, AISubmitActionsRequest

    # AIChatActionRequest
    req = AIChatActionRequest(messages=[{"role": "user", "content": "test"}])
    assert len(req.messages) == 1

    # AISubmitActionItem
    item = AISubmitActionItem(
        category_id="study",
        duration=120,
        note="test",
        dimension_exp=60,
    )
    assert item.category_id == "study"
    assert item.duration == 120
    assert item.sub_type == ""  # 默认值

    # AISubmitActionsRequest
    req = AISubmitActionsRequest(actions=[item])
    assert len(req.actions) == 1
    assert req.actions[0].category_id == "study"


# ================================================================
# 健康检查（确保应用启动正常）
# ================================================================

def test_health():
    """验证应用健康检查端点"""
    with TestClient(app) as client:
        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"