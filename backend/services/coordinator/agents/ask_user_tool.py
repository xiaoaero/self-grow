"""
Self Grow — ask_user 反问工具 + 域标签常量

子 agent 通过调用 ask_user 工具向用户反问缺失信息（而非用 LangGraph interrupt()）。
工具返回 needs_user=True 标记，由 base.py 的 ReAct 循环捕获并作为子图结果返回；
用户回答后，dispatch/resume 层把回答作为新的 HumanMessage 追加回该子图的
checkpoint 历史，子 agent 继续执行 —— 全程不重新经过主 agent 分发。

这是「三段式」中的第二阶段（子 agent 反问与执行）内部循环。
"""

from langchain_core.tools import tool

DOMAIN_LABELS = {
    "action": "🏃 行动记录",
    "query": "📊 统计查询",
    "goal": "🎯 目标管理",
    "task": "📋 任务管理",
    "habit": "✅ 习惯管理",
    "reward": "🎁 奖励管理",
}


@tool
def ask_user(question: str, options: list = None, domain: str = "", domain_label: str = "") -> dict:
    """向用户反问，请求补充缺失的信息或确认某个写操作。

    当你的任务缺少必要参数（如时长、标题、截止日期、维度、习惯名等），
    或需要用户确认某个写库操作时，调用此工具。调用后本轮执行暂停，
    等待用户回答后再继续。

    Args:
        question: 要问用户的问题（简洁、具体、一次只问一件事）
        options: 可选选项列表（如 ["30分钟", "1小时"]），无则传空列表 []
        domain: 所属功能域（action/query/goal/task/habit/reward）
        domain_label: 前端展示的域标签（带 emoji，如 "🏃 行动记录"）
    """
    return {
        "needs_user": True,
        "question": question,
        "options": options or [],
        "domain": domain,
        "domain_label": domain_label,
    }
