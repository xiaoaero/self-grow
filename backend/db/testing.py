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


def reset_test_database() -> bool:
    """清空测试库并重新 init_db()

    项目已只支持 MySQL（2026-09-23 移除 SQLite 通路），
    这里不再有「SQLite 分支返回 False、调用方退回 monkeypatch 切文件」那条路 ——
    **MySQL 没有"文件"可换**，只能清空所有表再重建。

    Returns:
        True —— 总是执行重置（保留返回值是为了不动调用方的 `if reset_test_database():` 写法）
    """
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
        #   DROP 版本慢（28 张表的字典操作）但**稳定**，`test_sleep_action.py`
        #   （38 个用例 × 28 张表）约 45 秒。
        #   ⇒ 全量测试约 2.5 分钟，需要时**分批跑**（见 README「数据库（MySQL，唯一后端）」）。
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

    # 通知测试辅助：库是新的，之前设过的测试账号密码已随清库一起消失。
    # 不通知的话 `ensure_test_accounts()` 会因为缓存而跳过设置，
    # 后续所有需要登录的测试都会 401（实测：test_sleep_action 之后
    # test_streaming 的 11 个用例全挂在这里）。
    try:
        import sys
        helper_mod = sys.modules.get("helpers") or sys.modules.get("tests.helpers")
        if helper_mod is not None and hasattr(helper_mod, "invalidate_test_accounts"):
            helper_mod.invalidate_test_accounts()
    except Exception:      # noqa: BLE001 — 测试辅助的事不该影响重置本身
        pass

    return True
