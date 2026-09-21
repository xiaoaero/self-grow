"""
Self Grow — 测试辅助

为什么需要这个
--------------
既有测试用 `monkeypatch.setattr(db.connection, "DB_PATH", tmp_path/"test.db")`
来做**每个测试一个干净库**的隔离。这在 SQLite 下有效（换文件就行），
但 MySQL 下没有"文件"可换，monkeypatch 完全没有效果 ——
测试会直接写真实库，既污染数据、又因为状态残留而失败。

所以这里提供一个 MySQL 侧的等价物：**清空测试库的所有表再重新播种**，
效果与"换一个全新的库文件"一致。

⚠️ 安全闸：只允许在**库名含 test** 的库上执行，防止误清真实库。
"""

import logging

log = logging.getLogger(__name__)


def is_mysql_backend() -> bool:
    from db.backend import backend_name
    return backend_name() == "mysql"


def reset_test_database() -> bool:
    """清空测试库并重新 init_db()

    Returns:
        True —— 执行了重置（MySQL 后端）
        False —— 当前是 SQLite 后端，调用方应走原来的 monkeypatch 路径
    """
    if not is_mysql_backend():
        return False

    import config
    dbname = config.MYSQL_DATABASE
    if "test" not in dbname.lower():
        raise RuntimeError(
            f"拒绝重置库 `{dbname}` —— 库名里必须含 'test'。"
            "这是防止误清真实数据的保护。"
        )

    from db.connection import get_conn

    conn = get_conn()
    try:
        conn.execute("SET FOREIGN_KEY_CHECKS=0")
        rows = conn.execute("""
            SELECT table_name AS t FROM information_schema.tables
            WHERE table_schema = DATABASE()
        """).fetchall()

        # ⚠️ 用 `DROP TABLE` 而不是 `TRUNCATE`：
        #   尝试过 TRUNCATE（想着更快 + 顺带归零 AUTO_INCREMENT），
        #   但实测**会卡死** —— InnoDB 的 TRUNCATE 要拿元数据锁并重建表空间，
        #   而连接池里其它连接的状态让它一直等（`lock_wait_timeout` 默认是极长的）。
        #   失败表现是 pytest 停在半路、没有任何报错输出。
        #   DROP 版本慢（22 张表的字典操作）但**稳定**，`test_sleep_action.py`
        #   （38 个用例 × 22 张表）在 MySQL 下约 45 秒、SQLite 下几秒。
        #   ⇒ MySQL 全量测试请**分批跑**（见 README「数据库（双后端）」）。
        for r in rows:
            conn.execute(f"DROP TABLE IF EXISTS `{r['t']}`")

        conn.execute("SET FOREIGN_KEY_CHECKS=1")
        conn.commit()
    finally:
        conn.close()

    # DROP 之后表全没了 → init_db() 重新建表 + 重新播种
    # demo 用户 / 维度 / 模型配置，等价于「换一个全新的库文件」。
    from db.init import init_db
    init_db()
    return True
