"""
Self Grow — 数据库后端（SQLite / MySQL 双通路）

为什么要有这一层
----------------
项目原来直接 `sqlite3.connect()`（151 处 `get_conn()` 调用散在 20 个文件里）。
迁 MySQL 时如果去改每个调用点，改动面和出错概率都不可控。所以这里**在连接层做适配**，
对外仍然暴露 `get_conn()`，返回一个**代理对象**，让下面这套既有用法一行不改：

    conn = get_conn()
    try:
        cur = conn.execute("INSERT ... VALUES (?, ?)", (a, b))   # 返回 cursor
        new_id = cur.lastrowid
        rows = conn.execute("SELECT ... WHERE x = ?", (x,)).fetchall()
        conn.commit()
    finally:
        conn.close()

两条通路：
  SELF_GROW_DB_BACKEND=sqlite（默认）→ 原来的 data.db，行为完全不变
  SELF_GROW_DB_BACKEND=mysql        → MySQL（连接池 + 时区补偿）

保留 sqlite 通路是**有意为之**：迁移期任何一步出问题，改个环境变量就能整体回退。
详见 docs/SQLite迁移MySQL方案.md。
"""

import logging

from config import (
    DB_BACKEND, DB_PATH,
    MYSQL_HOST, MYSQL_PORT, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DATABASE,
    MYSQL_POOL_SIZE, MYSQL_TIME_ZONE,
)
from db import dialect as _dialect

log = logging.getLogger(__name__)


# ================================================================
# SQLite 后端（原样保留，含 WAL / busy_timeout 那几个 PRAGMA）
# ================================================================

def _current_sqlite_path() -> str:
    """取当前 SQLite 库路径（**动态**读，不能直接用模块常量）

    为什么绕这一下：既有测试用
        `monkeypatch.setattr(db.connection, "DB_PATH", str(tmp_path / "test.db"))`
    来切换到临时库（`tests/test_time_consistency.py` 与 `tests/test_sleep_action.py`）。
    如果这里直接用 import 时绑定的 `DB_PATH` 常量，monkeypatch 就失效 ——
    28 个时间口径用例会全部 ERROR（`db.connection has no attribute 'DB_PATH'`）。
    所以优先从 `db.connection` 读；那里对 DB_PATH 做了 re-export。
    """
    try:
        from db import connection as _c          # 延迟导入，避免与 connection 循环
        return getattr(_c, "DB_PATH", DB_PATH)
    except Exception:
        return DB_PATH


def _new_sqlite_conn():
    import sqlite3
    conn = sqlite3.connect(_current_sqlite_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


# ================================================================
# MySQL 后端
# ================================================================

_pool = None


def _prepare(sql: str) -> str:
    """把 SQLite 风格的 SQL 调整成 MySQL 能执行的形态

    两件事：
    1. **MySQL 保留字列名加反引号**（`desc` / `year_month`）—— DML 也要，
       所以放在最前面独立做
    2. **建表/建索引语句**走方言转换（`db/dialect.py`）——
       自增主键、时间函数默认值、TEXT 带默认值、索引的 IF NOT EXISTS…
    3. 把 `?` 占位符翻成 PyMySQL 的 `%s`

    为什么占位符在这里翻、而不是把 150 处 SQL 全改成 `%s`：
    改 SQL 会让 **SQLite 通路也需要反向转换**（否则老后端挂掉），
    等于两条路都要维护一份转换逻辑。放在这里，SQLite 侧一个字不用动，
    SQL 文本也保持项目原有的写法。

    安全性：已核实 SQL 里没有字面 `?`、也没有字面 `%`
    （参数值里的 `%` 不需要转义，PyMySQL 只处理 SQL 模板本身）。
    """
    # ⚠️ 顺序很重要：**先做方言转换、再加反引号**。
    #    反过来的话，`desc` 会先变成 `` `desc` ``，而 to_mysql_ddl 里
    #    「列定义行」的正则用 `\w+` 取列名、匹配不到反引号，
    #    于是 `desc TEXT DEFAULT ''` 没被转成 VARCHAR —— 
    #    MySQL 直接报 1101（TEXT can't have a default value）。**这个坑踩过。**
    sql = _dialect.dml_to_mysql(sql)          # INSERT OR IGNORE 等（所有 SQL）
    if _dialect.is_ddl(sql):
        sql = _dialect.to_mysql_ddl(sql)
    sql = _dialect.quote_reserved(sql)
    return sql.replace("?", "%s") if "?" in sql else sql


# MySQL 的"对象已存在"错误码。
# SQLite 有 `CREATE TABLE/INDEX IF NOT EXISTS`，MySQL 只有表支持；
# 这两个错误码吞掉后，语义就与 IF NOT EXISTS 等价（幂等建表）。
_ALREADY_EXISTS_CODES = (1050, 1061)   # 1050 表已存在 / 1061 索引已存在


# 每个新连接都执行一次的会话设置（拼成**一条** SET，减少一次往返）
#
# 三件事，缺一不可：
#
# 1. `time_zone` —— 容器/服务器常跑 UTC，而本项目全量依赖「本地时间」。
#    在连接层设而不是改容器，好处是与部署环境**解耦**。
#
# 2. `lock_wait_timeout` + `innodb_lock_wait_timeout` —— **这两个是防死锁保命的**。
#    MySQL 的默认值极其激进：`lock_wait_timeout` 是 **31536000 秒（一年）**。
#    也就是说，只要有一个连接持有表的元数据锁 / 行锁不放，其它连接就会
#    **无限期等下去** —— 表现为接口不报错也不返回、整个 worker 挂死。
#    配合 DBUtils 的 `blocking=True`（池满时同样是无限等待，也没有超时），
#    一旦触发就是「网站彻底不动且没有任何错误日志」，极难排查。
#    实测踩过：MySQL 后端跑测试时卡在半路、没有任何报错输出。
#    设成 30 秒后，这类情况会抛出明确的 1205/3024 错误，而不是静默挂死。
#    （30 秒对正常业务是绰绰有余的；真的等 30 秒说明已经出问题了，
#      这时候「快速失败」比「一直装作还在处理」有价值得多。）
_INIT_COMMAND = (
    f"SET time_zone = '{MYSQL_TIME_ZONE}', "
    "lock_wait_timeout = 30, "
    "innodb_lock_wait_timeout = 30"
)


def _get_pool():
    """懒加载连接池（首次用时才建，避免 import 阶段就要求 MySQL 可达）"""
    global _pool
    if _pool is None:
        import pymysql
        from dbutils.pooled_db import PooledDB

        _pool = PooledDB(
            creator=pymysql,
            maxconnections=MYSQL_POOL_SIZE,   # ⚠️ 必须 ≥ 并发线程数，见 config.py 注释
            mincached=2,
            blocking=True,                    # 池满时等待而不是抛错
            ping=1,                           # 取连接时探活，避免拿到被服务端断掉的连接
            host=MYSQL_HOST,
            port=MYSQL_PORT,
            user=MYSQL_USER,
            password=MYSQL_PASSWORD,
            database=MYSQL_DATABASE,
            charset="utf8mb4",                # 项目里有 emoji（🏃 🎁 📊）
            cursorclass=pymysql.cursors.DictCursor,   # row["col"] 与 sqlite3.Row 用法一致
            autocommit=False,                 # 与 sqlite3 语义对齐：显式 commit
            init_command=_INIT_COMMAND,
        )
        log.info(
            f"MySQL 连接池就绪：{MYSQL_USER}@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DATABASE} "
            f"（max={MYSQL_POOL_SIZE}, tz={MYSQL_TIME_ZONE}）"
        )
    return _pool


def _run(raw_cur, sql, params):
    """在原生 cursor 上执行，并处理 MySQL 特有的两个差异

    1. 走 `_prepare`（DDL 方言转换 + 占位符翻译）
    2. 吞掉"对象已存在"（1050 表 / 1061 索引）—— 等价于 SQLite 的
       `IF NOT EXISTS`，让 init_db 可以重复执行
    """
    import pymysql
    try:
        raw_cur.execute(_prepare(sql), params or ())
    except pymysql.err.OperationalError as e:
        code = e.args[0] if e.args else None
        if not (code in _ALREADY_EXISTS_CODES and _dialect.is_ddl(sql)):
            raise
    return raw_cur


class MysqlCursor:
    """cursor 代理

    ⚠️ 这个类是**必要的**，不是多余的包装：
    项目里有 36 处是 `cursor = conn.cursor()` 再 `cursor.execute(...)`
    （典型是 `db/init.py` 的建表循环）。如果只包装 `conn.execute()`，
    这些路径不会过 `_prepare` —— 建表语句不会走方言转换，
    会在 `INTEGER PRIMARY KEY AUTOINCREMENT` 上报 1064。**这个坑踩过。**

    其余方法与属性（fetchone / fetchall / lastrowid / rowcount / description…）
    全部透传到底层 DictCursor。
    """

    __slots__ = ("_raw",)

    def __init__(self, raw):
        self._raw = raw

    def execute(self, sql, params=()):
        _run(self._raw, sql, params)
        return self          # 与 PyMySQL 一致：execute 返回 cursor 自身，支持链式

    def executemany(self, sql, seq_of_params):
        self._raw.executemany(_prepare(sql), seq_of_params)
        return self

    def __getattr__(self, name):
        return getattr(self._raw, name)

    def __iter__(self):
        return iter(self._raw)


class MysqlConn:
    """sqlite3.Connection 的代理，只补两个差异：

    1. `execute()` / `executemany()` —— sqlite3 的 Connection 有这两个便利方法
       （196 处代码在用），PyMySQL 只有 cursor 才有 → 这里补上，返回 cursor
    2. 占位符 `?` → `%s` 的翻译

    其余（cursor / commit / rollback / close）原样透传。
    `close()` 是**归还连接到池**，不是真关 —— 并且做了幂等保护
    （项目里有分支重复 close 的写法，见方案文档 §8.4）。
    """

    __slots__ = ("_raw", "_pool", "_closed")

    def __init__(self, raw, pool):
        self._raw = raw
        self._pool = pool
        self._closed = False

    # ── 与 sqlite3.Connection 一致 ──
    def cursor(self):
        return MysqlCursor(self._raw.cursor())

    def execute(self, sql, params=()):
        return MysqlCursor(_run(self._raw.cursor(), sql, params))

    def executemany(self, sql, seq_of_params):
        cur = self._raw.cursor()
        cur.executemany(_prepare(sql), seq_of_params)
        return MysqlCursor(cur)

    def commit(self):
        self._raw.commit()

    def rollback(self):
        self._raw.rollback()

    def close(self):
        """归还连接到池（幂等）"""
        if self._closed:
            return
        self._closed = True
        try:
            self._pool.close()
        except Exception:
            # 归还失败不能往上抛 —— 调用点都写在 finally 里，
            # 抛出去会把真正的业务异常盖掉
            log.exception("归还 MySQL 连接失败（已忽略）")

    # ── 顺手补上上下文管理器（原来全项目都是手动 close，205 处）──
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            self._raw.rollback() if exc_type else self._raw.commit()
        finally:
            self.close()
        return False

    @property
    def raw(self):
        """少数需要拿到底层连接的场合"""
        return self._raw


# ================================================================
# 对外统一入口
# ================================================================

def get_conn():
    """获取数据库连接（用法与原来的 sqlite3 版本完全一致）"""
    if DB_BACKEND == "mysql":
        pool = _get_pool()
        return MysqlConn(pool.connection(), pool)
    return _new_sqlite_conn()


def close_pool():
    """关闭连接池（测试收尾 / 进程退出用）"""
    global _pool
    if _pool is not None:
        try:
            _pool.close()
        except Exception:
            log.exception("关闭连接池失败（已忽略）")
        _pool = None


def backend_name() -> str:
    return DB_BACKEND
