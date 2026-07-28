"""
Self Grow — SQLite 数据库连接管理
"""

from config import DB_PATH
import sqlite3


def get_conn():
    """获取数据库连接（row_factory = sqlite3.Row）

    PRAGMA 优化说明：
    - journal_mode=WAL：写不阻塞读，读写并发能力大幅提升（SQLite 并发写入的核心优化）
    - busy_timeout=5000：写锁冲突时等待 5 秒而非立即报错，减少高频写入时的 database is locked 错误
    - synchronous=NORMAL：WAL 模式下足够安全，写入性能提升约 2 倍
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn