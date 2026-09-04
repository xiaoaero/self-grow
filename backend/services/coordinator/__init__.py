"""
Self Grow — 统一协调 Agent（Coordinator Agent）

三段式多智能体编排：
  1. 主 agent 路由（router）→ 2. 子 agent 并行反问/执行 → 3. 主 agent 总结

用户自然语言输入 → 主 agent 判断启动哪些次 agent → 并行派发 → 次 agent
缺信息时通过 ask_user 反问 → 用户回答直接接回该次 agent 上下文 → 循环 →
所有次 agent 完成后由主 agent 总结回复。
"""

from .graph import run_coordinator, resume_subgraph
from .state import CoordinatorState

__all__ = ["run_coordinator", "resume_subgraph", "CoordinatorState"]
