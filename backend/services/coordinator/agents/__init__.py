"""
Self Grow — 各域子图

每个子图专注单一数据域，接受主图的定制指令，通过 ask_user 工具反问补齐参数，执行工具写库。
"""

from .action_agent import create_action_agent
from .query_agent import create_query_agent
from .goal_agent import create_goal_agent
from .task_agent import create_task_agent
from .habit_agent import create_habit_agent
from .reward_agent import create_reward_agent
from .ask_user_tool import DOMAIN_LABELS

# 域名 → 子图构建函数 映射
SUBGRAPH_BUILDERS = {
    "action": create_action_agent,
    "query": create_query_agent,
    "goal": create_goal_agent,
    "task": create_task_agent,
    "habit": create_habit_agent,
    "reward": create_reward_agent,
}

__all__ = [
    "SUBGRAPH_BUILDERS",
    "DOMAIN_LABELS",
    "create_action_agent",
    "create_query_agent",
    "create_goal_agent",
    "create_task_agent",
    "create_habit_agent",
    "create_reward_agent",
]
