"""
Self Grow — SQLite 数据库连接管理
"""

from config import DB_PATH
import sqlite3


def get_conn():
    """获取数据库连接（row_factory = sqlite3.Row）"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn