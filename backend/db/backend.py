"""
Self Grow — 数据库后端（MySQL）

项目原先直连 `sqlite3`（151 处 `get_conn()` 散在 20 个文件里），2026-09-19 迁到 MySQL，
2026-09-23 彻底移除 SQLite —— 现在**只有 MySQL 一条通路**。

这一层做三件事：
  1. **连接池**（DBUtils / PyMySQL），用 `_pool_lock` 保证并发首次取连接时只建一个池
  2. **代理**（`MysqlConn` / `MysqlCursor`）补上 `sqlite3.connect()` 才有的
     `conn.execute()` 便利方法与 `row["col"]` 取值方式 —— 业务代码因此一行没改
  3. **慢查询埋点**：所有 SQL 都汇聚到 `_run()`，超阈值打 WARNING

⚠️ 这里**没有**方言转换层了。原 `db/dialect.py`（? → %s、AUTOINCREMENT → AUTO_INCREMENT、
`INSERT OR IGNORE`、`ON CONFLICT`、TEXT 键与默认值、保留字反引号、时间函数）已随 SQLite
一并删除 —— 那些转换结果已全部**固化进源码**，源码里现在写的就是 MySQL 原生 SQL。
`tests/test_sql_dialect_lint.py` 会拦住任何回退写法。

⚠️ `_INIT_COMMAND` 里的 `SET time_zone = '+08:00'` 不能删 ——
建表默认值用的 `now()` 走的就是这个连接时区，删了会让容器（UTC）里写 UTC，
与项目其他地方（`date.today()`、cron 小时数）用的本地时间恒定差 8 小时。
"""

import logging
import os
import threading
import time

from config import (
    MYSQL_HOST, MYSQL_PORT, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DATABASE,
    MYSQL_POOL_SIZE, MYSQL_TIME_ZONE,
)
log = logging.getLogger(__name__)

# 慢查询阈值（毫秒）。超了打 WARNING，带上耗时与 SQL 摘要。
#
# 为什么必须有这个：本项目踩过一次「接口不报错也不返回、整站挂死，
# 而且完全没有错误日志」—— 根因是 MySQL 的 lock_wait_timeout 默认一年
# 加上 DBUtils 连接池无限等待。当时**没有任何日志能指向 DB**，
# 只能靠读代码猜。有了慢查询日志，同类问题下次必然能定位。
#
# 阈值可以调：正常业务 SQL 都是毫秒级，500ms 已经很不正常；
# 但测试环境跑 DROP+CREATE 22 张表，可以设大一点免噪。
_SLOW_QUERY_MS = float(os.getenv("SELF_GROW_SLOW_QUERY_MS", "500") or 500)


# ================================================================
# 连接池
# ================================================================

_pool = None

# 保护 `_pool` 的创建过程。
#
# ⚠️ 没有这把锁时 `_get_pool()` 的 `if _pool is None` 是**典型的 check-then-act
# 竞态**：服务刚起来、一批请求同时首次查库时，每个线程都会看到 `_pool is None`
# 而各自创建一个完整连接池 —— 只有最后赋值的那个能存活，前面创建的池连同里面
# 已建立的连接一起被丢弃（那些连接要等 GC 才关，期间一直占着 MySQL 的连接数）。
#
# 实测症状：16 个线程并发首次取连接时，「MySQL 连接池就绪」这行日志
# **被打印了 16 次** —— 一看日志条数就知道池建重了。
# 除了浪费连接，每次请求命中不同池也会让缓存与 `mincached` 形同虚设。
_pool_lock = threading.Lock()


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
    """懒加载连接池（首次用时才建，避免 import 阶段就要求 MySQL 可达）

    ⚠️ 必须双重检查 + 加锁，不能只写 `if _pool is None: ...`。
    原因见 `_pool_lock` 处的说明：并发首次取连接时每个线程都会各建一个池。
    `_pool` 的读写不需要每次都抢锁 —— 快路径（已建好）直接返回，
    只有首次创建才进临界区，之后零开销。
    """
    global _pool
    if _pool is not None:          # 快路径：绝大多数调用走这里
        return _pool

    with _pool_lock:
        if _pool is not None:      # 双重检查：等锁期间可能已被别的线程建好
            return _pool

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
            cursorclass=pymysql.cursors.DictCursor,   # row["col"] 取列（与原来的 sqlite3.Row 写法一致）
            autocommit=False,                 # 显式 commit（原本就是主动调 commit 的写法）
            init_command=_INIT_COMMAND,
        )
        # 这行日志正常只应出现**一次**。看到多条 = 池被重复创建。
        log.info(
            f"MySQL 连接池就绪：{MYSQL_USER}@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DATABASE} "
            f"（max={MYSQL_POOL_SIZE}, tz={MYSQL_TIME_ZONE}）"
        )
        return _pool


def _sql_summary(sql: str, limit: int = 120) -> str:
    """把 SQL 压成一行短摘要（日志里不打全文，避免刷屏 + 泄漏参数）"""
    flat = " ".join(str(sql).split())
    return flat if len(flat) <= limit else flat[:limit] + "…"


def _run(raw_cur, sql, params):
    """在原生 cursor 上执行，并处理 MySQL 特有的两个差异

    1. 直接执行（SQL 已是 MySQL 原生写法，没有方言转换层了）
    2. 吞掉"对象已存在"（1050 表 / 1061 索引）—— 让 init_db 可以重复执行

    顺带统计耗时，超过 `_SLOW_QUERY_MS` 打一条 WARNING。
    （所有 MySQL 侧的 SQL 都汇聚到这里：`conn.execute()` 与
    `conn.cursor().execute()` 都经 `_run`，所以埋一处就够。）

    MySQL 才是生产默认后端，也正是历史上出过静默卡死的那个。
    """
    import pymysql
    started = time.perf_counter()
    try:
        try:
            raw_cur.execute(sql, params)
        except pymysql.err.OperationalError as e:
            code = e.args[0] if e.args else None
            # 只对 DDL 吞「已存在」（1050 表 / 1061 索引）—— DML 撞主键是真实错误，不能吞。
            # `is_ddl` 原来在 db/dialect.py 里，方言层已随 SQLite 一并删除，这里内联。
            if not (code in _ALREADY_EXISTS_CODES and _is_ddl(sql)):
                raise
    finally:
        elapsed_ms = (time.perf_counter() - started) * 1000
        if elapsed_ms >= _SLOW_QUERY_MS:
            log.warning(
                "慢查询 %.0fms（阈值 %.0fms）: %s",
                elapsed_ms, _SLOW_QUERY_MS, _sql_summary(sql),
            )
    return raw_cur


class MysqlCursor:
    """cursor 代理

    ⚠️ 这个类是**必要的**，不是多余的包装：
    项目里有 36 处是 `cursor = conn.cursor()` 再 `cursor.execute(...)`
    （典型是 `db/init.py` 的建表循环）。如果只包装 `conn.execute()`，
    这类写法也走 `conn.cursor()` 而不是 `conn.execute()`，
    所以 cursor 代理必须存在，不能只包 Connection。

    其余方法与属性（fetchone / fetchall / lastrowid / rowcount / description…）
    全部透传到底层 DictCursor。
    """

    __slots__ = ("_raw",)

    def __init__(self, raw):
        self._raw = raw

    def execute(self, sql, params=None):
        _run(self._raw, sql, params)
        return self          # 与 PyMySQL 一致：execute 返回 cursor 自身，支持链式

    def executemany(self, sql, seq_of_params):
        self._raw.executemany(sql, seq_of_params)
        return self

    def __getattr__(self, name):
        return getattr(self._raw, name)

    def __iter__(self):
        return iter(self._raw)


class MysqlConn:
    """连接代理，只补两个差异（原来的 sqlite3.Connection 才有）：

    1. `execute()` / `executemany()` —— 便利方法，项目里有 190+ 处在用；
       PyMySQL 只有 cursor 才有 → 这里补上，返回 cursor
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

    # ── 便利方法（与原来的 Connection 接口一致）──
    def cursor(self):
        return MysqlCursor(self._raw.cursor())

    def execute(self, sql, params=None):
        return MysqlCursor(_run(self._raw.cursor(), sql, params))

    def executemany(self, sql, seq_of_params):
        cur = self._raw.cursor()
        cur.executemany(sql, seq_of_params)
        return MysqlCursor(cur)

    def commit(self):
        self._raw.commit()

    def rollback(self):
        self._raw.rollback()

    def close(self):
        """归还连接到池（幂等）

        ⚠️⚠️ 必须是 `self._raw.close()`（归还**这一个**连接），
        **不是** `self._pool.close()`（那是关闭**整个池**）。

        这里原来写的是 `self._pool.close()`，是一个**完全静默的真 bug**
        （已实测：一次 close 之后池的 idle 缓存从 1 变 0）：

          · `self._pool` 是 `PooledDB` 池对象（在 `get_conn()` 里传进来的），
            `self._raw` 才是 `PooledDedicatedDBConnection` 单个连接
          · 于是**每次 `conn.close()` 都在清空整个池**，池里所有空闲连接都被
            真关掉。下一个请求只能重新建连 —— TCP 握手 + MySQL 认证 +
            `init_command` 里的 `SET time_zone / lock_wait_timeout`。
            连接池等于白建，高并发下更是互相清空对方的缓存。
          · 要命的是它**不报错、功能看起来一切正常，只是慢**，
            所以能一直潜伏。

        `close_pool()` 里那个 `_pool.close()` 才是对的写法
        （那是进程退出 / 测试收尾，确实要关掉整个池）。
        """
        if self._closed:
            return
        self._closed = True
        try:
            self._raw.close()
        except Exception:
            # 归还失败不能往上抛 —— 调用点都写在 finally 里，
            # 抛出去会把真正的业务异常盖掉
            log.exception("归还 MySQL 连接失败（已忽略）")

    def __del__(self):
        """GC 兜底归还连接

        为什么必须有：全项目有 126 处是这么写的 ——

            conn = get_conn()
            rows = conn.execute(...).fetchall()
            conn.close()

        `close()` **不在 `finally` 里**，所以中途任何一句抛出异常
        （SQL 报错、`json.loads` 撞上脏数据、`commit()` 锁等待超时）
        都会跳过它，连接不归还。

        为什么这件事的后果比"少一个连接"严重：池是
        `PooledDB(blocking=True)`，**池满时无限等待（没有超时）** ——
        每泄漏一个，可用连接就永久少一个，最终表现为
        「接口不报错也不返回、整站静默卡死」，而且日志里什么都看不到。
        项目已经踩过一次同类事故（当时是池配小了）。

        有了这个兜底，最坏情况也只是**延迟**归还，不会永久丢。
        但这只是安全网，不替代正确的 try/finally 写法。
        """
        try:
            self.close()
        except Exception:
            # 解释器关闭阶段既不能抛异常也不能打日志（模块可能已经拆了）
            pass

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
    """获取数据库连接（MySQL，走连接池）"""
    pool = _get_pool()
    return MysqlConn(pool.connection(), pool)


def close_pool():
    """关闭连接池（测试收尾 / 进程退出用）

    ⚠️ 也要拿同一把锁：它会把 `_pool` 置回 None，若与 `_get_pool()` 的
    创建过程并发，可能出现「刚建好就被关掉」或「关了一个已经换掉的池」。
    """
    global _pool
    with _pool_lock:
        if _pool is not None:
            try:
                _pool.close()
            except Exception:
                log.exception("关闭连接池失败（已忽略）")
            _pool = None


def backend_name() -> str:
    """当前后端名

    项目已只支持 MySQL（2026-09-23 移除 SQLite 通路），
    保留这个函数是因为测试里还有少量 "按后端分支" 的写法 —
    它们现在恒为同一个分支，可逐步清理，但不必为了删一个函数去动几十处调用。
    """
    return "mysql"
