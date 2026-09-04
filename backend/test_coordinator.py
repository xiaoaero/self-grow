"""
统一协调 Agent 后端测试脚本

用法：
cd backend
pixi run python test_coordinator.py
"""

import asyncio
import httpx
import json
import sys

BASE = "http://localhost:3001"


def _test_health():
    """测试健康检查"""
    print("=" * 50)
    print("1. 测试服务器健康检查...")
    try:
        r = httpx.get(f"{BASE}/api/health", timeout=5)
        print(f"   [OK] 状态码: {r.status_code}")
        return True
    except Exception as e:
        print(f"   [FAIL] 服务器未启动: {e}")
        print("   请先运行: cd backend && pixi run start")
        return False


def _test_chat(message, label=""):
    """测试 /api/coordinator/chat"""
    print(f"\n{'=' * 50}")
    print(f"测试: {label or message[:40]}")
    print(f"输入: {message}")
    print("-" * 30)

    try:
        r = httpx.post(
            f"{BASE}/api/coordinator/chat?user_id=1",
            json={"user_id": 1, "message": message},
            timeout=60,
        )
        data = r.json()

        print(f"状态码: {r.status_code}")

        if r.status_code != 200:
            print(f"[ERROR] 错误: {data}")
            return

        print(f"thread_id: {data.get('thread_id', 'N/A')[:16]}...")
        print(f"路由决策: {[t['domain'] for t in data.get('pending_tasks', [])]}")

        if data.get("interrupts"):
            for interrupt in data["interrupts"]:
                print(f"🤔 反问: {interrupt.get('question', '')}")

        if data.get("results"):
            for result in data["results"]:
                msg = result.get("message", "")
                tool = result.get("tool_name", "")
                if msg:
                    print(f"   结果: {msg[:100]}")
                if tool:
                    print(f"   工具: {tool} → {json.dumps(result.get('tool_result', {}), ensure_ascii=False)[:80]}")

        reply = data.get("reply", "")
        if reply:
            print(f"[REPLY] AI回复: {reply[:200]}")

        return data

    except httpx.ConnectError:
        print("[INFO] 服务器未启动，请先运行: cd backend && pixi run start")
        return None
    except Exception as e:
        print(f"[ERROR] 请求失败: {e}")
        return None


def main():
    # 1. 健康检查
    if not _test_health():
        sys.exit(1)

    # 2. 测试路由识别 + 行动记录
    _test_chat("我下午跑了30分钟步", "行动记录")

    # 3. 测试统计查询
    _test_chat("我现在的等级是多少", "统计查询")

    # 4. 测试创建目标（可能反问）
    data = _test_chat("帮我创建一个学习英语的目标", "创建目标（可能反问）")

    # 5. 如果有反问，测试恢复
    if data and data.get("interrupts"):
        interrupt = data["interrupts"][0]
        thread_id = data.get("thread_id")
        sub_thread_id = interrupt.get("sub_thread_id", "")
        if thread_id and sub_thread_id:
            print(f"\n{'=' * 50}")
            print(f"测试: 回答反问（恢复子图 {sub_thread_id[-20:]}）")
            print(f"回答: 6月30日前，先背完四级词汇")
            r = httpx.post(
                f"{BASE}/api/coordinator/resume?user_id=1",
                json={
                    "thread_id": thread_id,
                    "sub_thread_id": sub_thread_id,
                    "answer": "6月30日前，先背完四级词汇",
                },
                timeout=60,
            )
            data2 = r.json()
            print(f"💬 AI回复: {data2.get('reply', '')[:200]}")
            if data2.get("interrupts"):
                for it in data2["interrupts"]:
                    print(f"🤔 仍需反问: {it.get('question', '')}")
            print(f"   已完成域: {data2.get('completed_domains', [])}")

    # 6. 测试模糊意图
    _test_chat("我最近状态怎么样", "模糊意图")

    # 7. 测试多域并行
    _test_chat("完成任务跑步并记录我跑了30分钟", "多域并行")

    # 8. 测试习惯打卡
    _test_chat("今天读了30分钟书，帮我打卡", "习惯打卡")

    # 9. 测试奖励查询
    _test_chat("看看我有什么奖励", "奖励查询")

    print("\n" + "=" * 50)
    print("测试完成！")


if __name__ == "__main__":
    main()
