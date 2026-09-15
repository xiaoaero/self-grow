"""
Self Grow — SQLite 数据库连接管理
"""

import datetime

from config import DB_PATH
import sqlite3


def now_str() -> str:
    """本地时间的 SQL 文本形式，用于**显式**写入 created_at / updated_at

    全项目时间口径统一为**本地时间（naive local）**，详见 docs/时间口径统一方案.md。

    为什么必须显式写、不能依赖建表默认值：
        SQLite 的 `datetime('now')` 永远是 **UTC**，而本项目其他部分
        （`date.today()`、APScheduler 的 cron 小时数、`user_stats_daily.date`）
        用的都是**本地时间**。两种口径相减会恒定差 8 小时（UTC+8），
        表现为「刚记录完却显示 8 小时前」「凌晨 0~8 点的记录落到前一天」。

        SQLite **不支持** `ALTER TABLE ... ALTER COLUMN`，所以已经建好的库
        （本机开发库、服务器上的库）里列的默认值改不掉 —— 只能靠插入时显式赋值。
        建表语句里的默认值也一并改成 localtime，那是给新库兜底的。
    """
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


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