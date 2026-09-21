"""
Self Grow — 数据库连接管理（对外门面）

真正的后端实现在 `db/backend.py`：它按 `SELF_GROW_DB_BACKEND` 分派到
SQLite（默认，原行为）或 MySQL（连接池 + 占位符适配 + 时区补偿）。

这里只做两件事：
  · 保留 `get_conn` 这个名字 —— 全项目 151 处 `from db.connection import get_conn` 依赖它
  · 保留 `now_str()` —— 全项目时间口径的落地点

⚠️ 新增代码请用 `now_str()` 显式写时间，不要依赖建表默认值：
   SQLite 的 `datetime('now')` 是 UTC；MySQL 的 `NOW()` 走服务器时区
   （本地容器跑 UTC，已在连接层用 `SET time_zone='+08:00'` 补偿）。
   两种后端行为一致的前提是**时间由应用层算**。
   详见 docs/时间口径统一方案.md。
"""

import datetime

# re-export：让 `from db.connection import get_conn` 这一既有写法继续有效
#
# `DB_PATH` 也要导出 —— 既有测试靠
# `monkeypatch.setattr(db.connection, "DB_PATH", ...)` 切到临时库，
# 而 `db/backend.py` 会**动态**回来读这个属性（见 _current_sqlite_path）。
from db.backend import get_conn, backend_name, close_pool, DB_PATH  # noqa: F401

__all__ = ["get_conn", "now_str", "backend_name", "close_pool", "DB_PATH"]


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

        改用 MySQL 后这个约束依然成立（MySQL 容器默认 UTC）：
        连接层会 `SET time_zone='+08:00'`，但显式赋值仍是最可靠的做法。
    """
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
