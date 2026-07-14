"""
Self Grow — AI 提示词模块

集中存放所有 AI 功能的系统提示词和工具定义。
新增 AI 功能只需在此目录下新建 .py 文件，然后在 __init__.py 中导出。
"""

from .skill_tree import SKILL_TREE_SYSTEM_PROMPT, SKILL_TREE_TOOLS
from .habit_analysis import HABIT_ANALYSIS_SYSTEM_PROMPT
from .habit_icon import HABIT_ICON_SYSTEM_PROMPT
from .action_parse import ACTION_PARSE_SYSTEM_PROMPT, ACTION_PARSE_TOOLS

__all__ = [
    "SKILL_TREE_SYSTEM_PROMPT",
    "SKILL_TREE_TOOLS",
    "HABIT_ANALYSIS_SYSTEM_PROMPT",
    "HABIT_ICON_SYSTEM_PROMPT",
    "ACTION_PARSE_SYSTEM_PROMPT",
    "ACTION_PARSE_TOOLS",
]