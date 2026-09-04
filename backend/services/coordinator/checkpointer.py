"""
Self Grow — Coordinator Agent 全局 Checkpointer

所有主图和子图共用一个 MemorySaver 实例，通过不同 thread_id 隔离。
子图 thread_id 格式：{main_thread_id}:{domain}
"""

from langgraph.checkpoint.memory import MemorySaver

_checkpointer = MemorySaver()


def get_checkpointer() -> MemorySaver:
    """获取全局 checkpointer 单例"""
    return _checkpointer
