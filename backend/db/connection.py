"""
Self Grow — 数据库连接管理（对外门面）

真正的实现在 `db/backend.py`：MySQL 连接池 + 一层很薄的代理，
让业务代码里 151 处 `get_conn()` / `conn.execute(...)` 的写法完全不用改
（代理补上了 `sqlite3.Connection` 才有的 `execute()` 便利方法）。

这里只做两件事：
  · 保留 `get_conn` 这个名字 —— 全项目都 `from db.connection import get_conn`
  · 保留 `now_str()` —— 全项目时间口径的落地点

⚠️ 新增代码请用 `now_str()` **显式**写时间，不要依赖建表默认值。
   表默认值是 `now()`，它走连接时区（连接层设了 `SET time_zone='+08:00'`），
   确实是本地时间 —— 但这条等价关系**完全依赖连接层那一行**。
   详见 docs/时间口径统一方案.md。
"""

import datetime

# re-export：让 `from db.connection import get_conn` 这一既有写法继续有效
from db.backend import get_conn, backend_name, close_pool  # noqa: F401

__all__ = ["get_conn", "now_str", "backend_name", "close_pool", "placeholders"]


def placeholders(n: int) -> str:
    """生成 n 个占位符，`IN (...)` 用：n=3 → `'%s,%s,%s'`

    ⚠️ **必须从这里取，别手写**。手写出来的几乎肯定是 SQLite 时代的 `"?"`，
    而它是**运行到那一行才炸**的（2026-09-24 实测）：

        ph = ",".join("?" * len(repos))            # ← 看起来毫无问题
        conn.execute(f"... WHERE repo IN ({ph})", repos)
        → pymysql: not all arguments converted during string formatting

    为什么静态护栏**扫不到**它：`?` 是一个**运行时拼出来的变量**，
    源码里的字符串常量只是 `"?"`（不含 SQL 关键字 → 被准入判断放掉），
    而真正带 SQL 关键字的那一句里只有 `{ph}`。
    ⇒ 所以光有护栏不够，还得有**唯一入口**：只有一处会写占位符。

    真实事故：`services/aiconsult_analysis_service.py::get_repo_intros` ——
    「AI 分析」每次打开都 500（后台任务报错），而且**只在有上榜仓库时才触发**。
    """
    if n <= 0:
        return ""
    return ",".join(["%s"] * n)


def now_str() -> str:
    """本地时间的 SQL 文本形式，用于**显式**写入 created_at / updated_at

    全项目时间口径统一为**本地时间（naive local）**，
    详见 docs/时间口径统一方案.md。

    为什么必须显式写、不能只依赖建表默认值：
        建表默认值是 `now()`，走连接时区（连接层设了 `SET time_zone='+08:00'`）→
        确实是本地时间。但这条等价关系**完全依赖连接层那一行 `init_command`**：
        一旦它被删掉，容器（默认 UTC）里 `now()` 会写 UTC，
        而项目其他地方（`date.today()`、APScheduler 的 cron 小时数、
        `user_stats_daily.date`）用的都是本地时间 → 恒定差 8 小时，
        表现为「刚记录完却显示 8 小时前」「凌晨 0~8 点的记录落到前一天」。

        ⚠️ 所以 `db/backend.py` 的 `_INIT_COMMAND` 里那个
           `SET time_zone = '+08:00'` **不能删**。
    """
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
