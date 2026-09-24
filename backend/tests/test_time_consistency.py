"""
时间口径一致性测试 — 回归「行动记录/行动历史」的时区 bug

背景（详见 docs/时间口径统一方案.md）：
    项目统一使用**本地时间**，但历史上存在三处 UTC 混用，导致：
      · action_logs.created_at 来自 `datetime('now')`（UTC）→ 「最近行动」恒显示"8小时前"
      · 前端用 toISOString() 发 UTC 壁钟，后端当本地时间解析 → 记录时间早 8 小时
      · db/batch.py 用 `date(created_at)`（UTC）归档 → 凌晨 0~8 点建的任务归到前一天

这些用例一律和「本机当前本地时间」比较，所以**在任何时区下跑都成立**。

运行方式：cd backend && pixi run pytest tests/test_time_consistency.py -v
"""

import datetime

import pytest


# ================================================================
# Fixtures（与 test_sleep_action.py 保持一致的做法）
# ================================================================

@pytest.fixture
def tmp_db(monkeypatch, tmp_path):
    """干净库：清空测试库所有表再重建

    ⚠️ 项目已只支持 MySQL（2026-09-23 移除 SQLite），这里不再有
    「monkeypatch DB_PATH 指向临时文件」那条路 —— MySQL 没有"文件"可换，
    只能清空重建。测试库名必须含 `test`（`db/testing.py` 的安全闸，**不要绕过**）。
    """
    from db.testing import reset_test_database
    reset_test_database()
    return "mysql"


@pytest.fixture
def user_id(tmp_db):
    from db.connection import get_conn
    conn = get_conn()
    row = conn.execute("SELECT id FROM users WHERE name = 'test'").fetchone()
    conn.close()
    return row["id"]


def _local_now():
    return datetime.datetime.now()


def _parse(text):
    return datetime.datetime.fromisoformat(text)


# ================================================================
# 1. db/connection.now_str()：写库用的时间戳必须是本地时间
# ================================================================

class TestNowStr:
    def test_now_str_is_local_time_not_utc(self):
        """now_str() 应等于本地时间（不是 UTC）"""
        from db.connection import now_str
        written = _parse(now_str())
        delta = abs((_local_now() - written).total_seconds())
        assert delta < 5, f"now_str() 与本地时间相差 {delta:.0f}s，疑似用了 UTC"

    def test_now_str_format_is_iso_seconds(self):
        """格式应为 YYYY-MM-DD HH:MM:SS（可直接给 fromisoformat 解析）"""
        from db.connection import now_str
        text = now_str()
        assert len(text) == 19
        assert text[4] == "-" and text[10] == " " and text[13] == ":"


# ================================================================
# 2. action_logs：写入显式本地时间
# ================================================================

class TestActionLogTimestamp:
    def test_created_at_is_local_not_utc(self, tmp_db, user_id):
        """落库的 created_at 应是本地时间（修复前是 UTC，差 8 小时）"""
        from db.actions import create_action_log
        from db.connection import get_conn

        now = _local_now().replace(microsecond=0)
        create_action_log(user_id, "create", now.strftime("%Y-%m-%dT%H:%M:%S"),
                          now.strftime("%Y-%m-%dT%H:%M:%S"), 30, "时间口径测试", 10)

        conn = get_conn()
        row = conn.execute(
            "SELECT created_at FROM action_logs ORDER BY id DESC LIMIT 1"
        ).fetchone()
        conn.close()

        delta = abs((now - _parse(row["created_at"])).total_seconds())
        assert delta < 5, f"created_at 与本地时间相差 {delta:.0f}s，疑似被写成了 UTC"

    def test_start_time_stored_verbatim(self, tmp_db, user_id):
        """后端应原样保存前端传来的本地时间串（不再被当成别的口径解读）"""
        from db.actions import create_action_log
        from db.connection import get_conn

        start = "2026-09-15T09:00:00"
        create_action_log(user_id, "create", start, "2026-09-15T10:00:00", 60, "原样保存", 10)

        conn = get_conn()
        row = conn.execute(
            "SELECT start_time, end_time FROM action_logs ORDER BY id DESC LIMIT 1"
        ).fetchone()
        conn.close()
        assert row["start_time"] == start
        assert row["end_time"] == "2026-09-15T10:00:00"


# ================================================================
# 3. 「最近行动」相对时间：刚记录完必须是「刚刚」
# ================================================================

class TestRecentActivityRelativeTime:
    def test_just_recorded_shows_just_now(self, tmp_db, user_id):
        """刚写入一条记录，相对时间应是「刚刚」（修复前恒为「8小时前」）"""
        from db.actions import create_action_log
        from db.stats import get_recent_activities

        now = _local_now().replace(microsecond=0)
        create_action_log(user_id, "create", now.strftime("%Y-%m-%dT%H:%M:%S"),
                          now.strftime("%Y-%m-%dT%H:%M:%S"), 30, "刚刚测试", 10)

        activities = get_recent_activities(user_id, limit=1)
        assert activities, "应能取到刚写入的动态"
        assert activities[0]["time"] == "刚刚", f"实际是 {activities[0]['time']!r}"

    def test_minutes_ago(self, tmp_db, user_id):
        """30 分钟前的记录应显示「30分钟前」，而不是被 8 小时偏移吃掉"""
        from db.actions import create_action_log
        from db.connection import get_conn
        from db.stats import get_recent_activities

        ts = (_local_now() - datetime.timedelta(minutes=30)).replace(microsecond=0)
        text = ts.strftime("%Y-%m-%dT%H:%M:%S")
        create_action_log(user_id, "create", text, text, 30, "半小时前", 10)

        # created_at 由代码写入本地时间，这里直接改成 30 分钟前以构造场景
        conn = get_conn()
        conn.execute("""UPDATE action_logs SET created_at = %s WHERE note = %s""",
                     (ts.strftime("%Y-%m-%d %H:%M:%S"), "半小时前"))
        conn.commit()
        conn.close()

        activities = get_recent_activities(user_id, limit=1)
        assert activities[0]["time"] == "30分钟前", f"实际是 {activities[0]['time']!r}"

    def test_tz_aware_created_at_does_not_crash(self, tmp_db, user_id):
        """历史数据里带时区偏移（旧版 toISOString 写入的）不能让比较抛 TypeError"""
        from db.actions import create_action_log
        from db.connection import get_conn
        from db.stats import get_recent_activities

        create_action_log(user_id, "create", "2026-09-15T09:00:00",
                          "2026-09-15T10:00:00", 30, "带偏移的历史数据", 10)

        conn = get_conn()
        conn.execute("""UPDATE action_logs SET created_at = %s WHERE note = %s""",
                     ("2026-09-15T01:00:00+00:00", "带偏移的历史数据"))
        conn.commit()
        conn.close()

        activities = get_recent_activities(user_id, limit=1)   # 不应抛异常
        assert len(activities) == 1
        assert activities[0]["time"]


# ================================================================
# 4. tasks.created_at：归档判断（db/batch.py 用 date(created_at)）
# ================================================================

class TestTaskTimestamp:
    def test_task_created_at_is_local_date(self, tmp_db, user_id):
        """新建任务的 date(created_at) 应等于本地「今天」（否则凌晨建的任务会被归到昨天）"""
        from db.connection import get_conn
        from db.tasks import create_task

        tid = create_task(user_id, "时间口径任务", "work")

        conn = get_conn()
        row = conn.execute(
            """SELECT created_at, date(created_at) AS d FROM tasks WHERE id = %s""", (tid,)
        ).fetchone()
        conn.close()

        today = datetime.date.today().isoformat()
        delta = abs((_local_now() - _parse(row["created_at"])).total_seconds())
        assert delta < 5, f"tasks.created_at 与本地时间相差 {delta:.0f}s"
        # ⚠️ SQLite 的 date() 返回**字符串**，MySQL 的 DATE() 返回 DATE 类型
        #    （PyMySQL 再转成 datetime.date）—— 两者值相同、类型不同，
        #    所以统一 str() 后再比。这是驱动的正常行为，不是数据问题。
        assert str(row["d"]) == today, f"date(created_at)={row['d']}，本地今天={today}"



def _columns(conn, table: str) -> list:
    """某张表的列名（按定义顺序）

    ⚠️ MySQL 没有 `PRAGMA table_info`（SQLite 专有）—— 换成查 information_schema。
    SQLite 移除后这些用例不再被 skip，所以实现必须跟着换，**断言语义不变**。
    """
    rows = conn.execute(
        "SELECT COLUMN_NAME FROM information_schema.columns "
        "WHERE table_schema = DATABASE() AND table_name = %s ORDER BY ORDINAL_POSITION",
        (table,),
    ).fetchall()
    return [r["COLUMN_NAME"] for r in rows]

# ================================================================
# 5. 建表默认值：新库必须是 localtime（老库改不掉，靠显式写入兜底）
# ================================================================

class TestTableDefaults:
    @pytest.mark.parametrize("table,column", [
        ("action_logs", "created_at"),
        ("tasks", "created_at"),
        ("habits", "created_at"),
    ])
    def test_new_db_default_is_localtime(self, tmp_db, table, column):
        """建表默认值必须走连接时区（`now()`），不能用 UTC

        ⚠️ 这条口径是踩过的：容器默认跑 UTC，如果默认值写成 `utc_timestamp()`，
        就会与项目其他地方（`date.today()`、APScheduler 的 cron 小时数、
        `user_stats_daily.date`）用的本地时间恒定差 8 小时，
        表现为「刚记录完却显示 8 小时前」「凌晨 0~8 点的记录落到前一天」。

        实现换了（原来读 `sqlite_master` 里的建表文本，现在读 information_schema），
        但断言语义不变：默认值里不能出现 UTC 函数。
        """
        from db.connection import get_conn
        conn = get_conn()
        row = conn.execute(
            "SELECT COLUMN_DEFAULT FROM information_schema.columns "
            "WHERE table_schema = DATABASE() AND table_name = %s AND column_name = %s",
            (table, column),
        ).fetchone()
        conn.close()
        assert row is not None, f"{table}.{column} 不存在"
        d = str(row["COLUMN_DEFAULT"] or "")
        assert d, f"{table}.{column} 没有默认值"
        assert "utc_timestamp" not in d.lower(), (
            f"{table}.{column} 的默认值是 UTC 口径：{d}（应为 now()）"
        )

    def test_no_utc_default_left_in_new_db(self, tmp_db):
        """新库里不应有任何 UTC 口径的默认值"""
        from db.connection import get_conn
        conn = get_conn()
        rows = conn.execute(
            "SELECT table_name, column_name, column_default FROM information_schema.columns "
            "WHERE table_schema = DATABASE() "
            "AND LOWER(COALESCE(column_default, '')) LIKE %s",
            ("%utc_timestamp%",),
        ).fetchall()
        conn.close()
        bad = [f"{r['table_name']}.{r['column_name']}" for r in rows]
        assert not bad, f"这些列的默认值仍是 UTC：{bad}"
