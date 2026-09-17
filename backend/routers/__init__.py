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
from .auth import router as auth_router
from .skill_tree import router as skill_tree_router
from .skill_tree_ai import router as skill_tree_ai_router
from .expression import router as expression_router
from .coordinator import router as coordinator_router
from .model_configs import router as model_configs_router

# 注：routers/ai.py（旧 /api/chat 技能树 AI 代理）曾于 2026-09-03 下线、
# 2026-09-17 全代码审查时**文件本体已删除**。下线原因：无用户鉴权
# （全后端唯一裸奔的 AI 端点，任何人可直接消耗 API 配额），
# 且功能已被 skill_tree_ai_router 的 LangGraph 版本完全替代。
# 需要回看旧实现：`git log --all -- backend/routers/ai.py`。