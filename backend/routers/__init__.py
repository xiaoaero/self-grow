"""
Self Grow — 路由注册

汇总所有路由模块，统一导出给 main.py 使用。
"""

from .health import router as health_router
from .users import router as users_router
from .habits import router as habits_router
from .actions import router as actions_router
from .goals import router as goals_router
from .tasks import router as tasks_router
from .scheduled_tasks import router as scheduled_tasks_router
from .stats import router as stats_router
from .rewards import router as rewards_router
from .ai import router as ai_router
from .skill_tree import router as skill_tree_router
from .expression import router as expression_router