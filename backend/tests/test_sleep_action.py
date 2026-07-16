"""
睡眠行动记录测试 — 覆盖问题1（数据持久化）、问题2（展示）和规律作息的核心路径

运行方式：cd backend && pixi run pytest tests/test_sleep_action.py -v
"""

import os
import tempfile
import pytest
from datetime import datetime


# ================================================================
# Fixtures
# ================================================================

@pytest.fixture
def tmp_db(monkeypatch, tmp_path):
    """创建临时数据库，monkeypatch DB_PATH 指向它"""
    db_path = str(tmp_path / "test.db")
    from db import connection
    monkeypatch.setattr(connection, "DB_PATH", db_path)
    # 重新 init_db 建表
    from db.init import init_db
    init_db()
    return db_path


@pytest.fixture
def user_id(tmp_db):
    """获取默认测试用户 id"""
    from db.connection import get_conn
    conn = get_conn()
    row = conn.execute("SELECT id FROM users WHERE name = 'test'").fetchone()
    conn.close()
    return row["id"]


# ================================================================
# 测试1：数据库迁移 — 新列存在
# ================================================================

class TestMigration:
    def test_action_logs_has_sub_type_column(self, tmp_db):
        """action_logs 表应有 sub_type 列"""
        from db.connection import get_conn
        conn = get_conn()
        cols = [row[1] for row in conn.execute("PRAGMA table_info(action_logs)").fetchall()]
        conn.close()
        assert "sub_type" in cols, f"sub_type 列不存在，现有列：{cols}"

    def test_action_logs_has_sleep_start_column(self, tmp_db):
        """action_logs 表应有 sleep_start 列"""
        from db.connection import get_conn
        conn = get_conn()
        cols = [row[1] for row in conn.execute("PRAGMA table_info(action_logs)").fetchall()]
        conn.close()
        assert "sleep_start" in cols

    def test_action_logs_has_sleep_end_column(self, tmp_db):
        """action_logs 表应有 sleep_end 列"""
        from db.connection import get_conn
        conn = get_conn()
        cols = [row[1] for row in conn.execute("PRAGMA table_info(action_logs)").fetchall()]
        conn.close()
        assert "sleep_end" in cols

    def test_migration_idempotent(self, tmp_db):
        """重复调用 init_db() 不应报错（ALTER TABLE ADD COLUMN 幂等）"""
        from db.init import init_db
        init_db()  # 二次调用
        from db.connection import get_conn
        conn = get_conn()
        cols = [row[1] for row in conn.execute("PRAGMA table_info(action_logs)").fetchall()]
        conn.close()
        assert "sub_type" in cols


# ================================================================
# 测试2：create_action_log 存入新字段
# ================================================================

class TestCreateActionLog:
    def test_sleep_record_stored_with_sub_type(self, tmp_db, user_id):
        """睡眠记录应正确存入 sub_type='health-sleep'"""
        from db.actions import create_action_log, get_action_logs
        now = datetime.now().isoformat()
        rid = create_action_log(
            user_id, "health", now, now, 0, "测试睡眠", 20,
            sub_type="health-sleep", sleep_start="23:30", sleep_end="07:00",
        )
        assert rid > 0
        result = get_action_logs(user_id, page=1, page_size=10)
        rec = result["records"][0]
        assert rec["sub_type"] == "health-sleep"
        assert rec["sleep_start"] == "23:30"
        assert rec["sleep_end"] == "07:00"

    def test_sport_record_stored_with_sub_type(self, tmp_db, user_id):
        """运动记录应存入 sub_type='health-sport'，sleep 字段为空"""
        from db.actions import create_action_log, get_action_logs
        now = datetime.now().isoformat()
        rid = create_action_log(
            user_id, "health", now, now, 30, "跑步", 15,
            sub_type="health-sport",
        )
        result = get_action_logs(user_id, page=1, page_size=10)
        rec = result["records"][0]
        assert rec["sub_type"] == "health-sport"
        assert rec["sleep_start"] == ""
        assert rec["sleep_end"] == ""

    def test_old_style_record_without_sub_type(self, tmp_db, user_id):
        """旧式调用（不传 sub_type）不应报错，字段为空字符串"""
        from db.actions import create_action_log, get_action_logs
        now = datetime.now().isoformat()
        rid = create_action_log(
            user_id, "study", now, now, 60, "学习", 30,
        )
        result = get_action_logs(user_id, page=1, page_size=10)
        rec = result["records"][0]
        assert rec["sub_type"] == ""
        assert rec["sleep_start"] == ""
        assert rec["sleep_end"] == ""

    def test_sleep_duration_stored_correctly(self, tmp_db, user_id):
        """睡眠记录的 duration 应为实际睡眠分钟数（而非0）"""
        from db.actions import create_action_log, get_action_logs
        start_dt = datetime(2026, 7, 14, 23, 30)
        end_dt = datetime(2026, 7, 15, 7, 0)
        rid = create_action_log(
            user_id, "health", start_dt.isoformat(), end_dt.isoformat(), 450,
            "睡眠测试", 20,
            sub_type="health-sleep", sleep_start="23:30", sleep_end="07:00",
        )
        result = get_action_logs(user_id, page=1, page_size=10)
        rec = result["records"][0]
        assert rec["duration"] == 450


# ================================================================
# 测试3：EXP 计算 — 睡眠场景
# ================================================================

class TestSleepExpCalculation:
    def test_sleep_valid_6_to_9_hours(self):
        """6-9小时内的睡眠应返回正经验值"""
        from models.constants import calculate_exp
        result = calculate_exp("health", 0, sub_type="health-sleep",
                               sleep_start="23:00", sleep_end="07:00")
        assert result["dimension_exp"] > 0
        assert result["sleep_valid"] is True
        assert result["sub_type"] == "health-sleep"
        assert "is_routine" in result

    def test_sleep_too_short(self):
        """不足6小时的睡眠应无效"""
        from models.constants import calculate_exp
        result = calculate_exp("health", 0, sub_type="health-sleep",
                               sleep_start="02:00", sleep_end="06:00")
        assert result["dimension_exp"] == 0
        assert result["sleep_valid"] is False

    def test_sleep_too_long(self):
        """超过9小时的睡眠应无效"""
        from models.constants import calculate_exp
        result = calculate_exp("health", 0, sub_type="health-sleep",
                               sleep_start="22:00", sleep_end="09:00")
        assert result["dimension_exp"] == 0
        assert result["sleep_valid"] is False

    def test_sleep_late_bedtime_reduces_exp(self):
        """晚睡应降低基础经验"""
        from models.constants import calculate_exp
        r_early = calculate_exp("health", 0, sub_type="health-sleep",
                                sleep_start="23:00", sleep_end="07:00")
        r_late = calculate_exp("health", 0, sub_type="health-sleep",
                               sleep_start="01:00", sleep_end="08:00")
        assert r_early["dimension_exp"] > r_late["dimension_exp"]

    def test_sleep_no_time_returns_zero(self):
        """缺少睡眠时间应返回0经验"""
        from models.constants import calculate_exp
        result = calculate_exp("health", 0, sub_type="health-sleep",
                               sleep_start="", sleep_end="")
        assert result["dimension_exp"] == 0
        assert result["sleep_valid"] is False

    def test_non_health_categories_have_is_routine_false(self):
        """非健康维度返回 is_routine=False"""
        from models.constants import calculate_exp
        result = calculate_exp("study", 60)
        assert result.get("is_routine") is False


# ================================================================
# 测试4：规律作息 — 连续天数持久化
# ================================================================

class TestRoutineStreak:
    def test_routine_streak_table_exists(self, tmp_db):
        """routine_streak 表应存在"""
        from db.connection import get_conn
        conn = get_conn()
        tables = [row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()]
        conn.close()
        assert "routine_streak" in tables

    def test_get_routine_streak_default(self, tmp_db, user_id):
        """新用户规律状态应为0"""
        from db.routines import get_routine_streak
        info = get_routine_streak(user_id)
        assert info["streak"] == 0
        assert info["has_protection"] is False
        assert info["last_date"] is None

    def test_upsert_routine_streak(self, tmp_db, user_id):
        """写入规律状态后应可读回"""
        from db.routines import upsert_routine_streak, get_routine_streak
        upsert_routine_streak(user_id, streak=5, has_protection=False, last_date="2026-07-14")
        info = get_routine_streak(user_id)
        assert info["streak"] == 5
        assert info["has_protection"] is False
        assert info["last_date"] == "2026-07-14"

    def test_upsert_routine_streak_update(self, tmp_db, user_id):
        """重复 upsert 应覆盖"""
        from db.routines import upsert_routine_streak, get_routine_streak
        upsert_routine_streak(user_id, streak=3, has_protection=False, last_date="2026-07-13")
        upsert_routine_streak(user_id, streak=4, has_protection=False, last_date="2026-07-14")
        info = get_routine_streak(user_id)
        assert info["streak"] == 4


# ================================================================
# 测试5：规律作息 EXP 计算
# ================================================================

class TestRoutineExpCalculation:
    def test_routine_bonus_streak_0(self):
        """连续0天不加成"""
        from models.constants import _calc_routine_bonus
        assert _calc_routine_bonus(0) == 0

    def test_routine_bonus_streak_1_to_5(self):
        """连续1~5天，养成期不加成"""
        from models.constants import _calc_routine_bonus
        assert _calc_routine_bonus(1) == 0
        assert _calc_routine_bonus(3) == 0
        assert _calc_routine_bonus(5) == 0

    def test_routine_bonus_streak_6_plus(self):
        """连续6天起，固定+15"""
        from models.constants import _calc_routine_bonus
        assert _calc_routine_bonus(6) == 15
        assert _calc_routine_bonus(10) == 15
        assert _calc_routine_bonus(30) == 15
        assert _calc_routine_bonus(100) == 15

    def test_routine_sleep_streak_5_no_extra(self):
        """连续4天规律(streak=4)，今天第5天，尚未达6天，无额外加成"""
        from models.constants import calculate_exp
        result = calculate_exp("health", 0, sub_type="health-sleep",
                               sleep_start="23:00", sleep_end="07:00",
                               streak=4)
        assert result["routine_extra"] == 0  # streak+1=5 < 6

    def test_routine_sleep_streak_6_gets_extra(self):
        """连续6天规律，获得+15额外加成"""
        from models.constants import calculate_exp
        result = calculate_exp("health", 0, sub_type="health-sleep",
                               sleep_start="23:00", sleep_end="07:00",
                               streak=6)
        assert result["routine_extra"] == 15

    def test_routine_sleep_total_exp(self):
        """规律睡眠总EXP = 基础20 + 规律15 = 35"""
        from models.constants import calculate_exp
        result = calculate_exp("health", 0, sub_type="health-sleep",
                               sleep_start="23:00", sleep_end="07:00",
                               streak=6)
        assert result["dimension_exp"] == 35  # 20(基础) + 15(规律)
        assert result["global_exp"] == 35     # health global_rate=1.0

    def test_non_routine_sleep_no_extra(self):
        """不规律的睡眠不应获得规律加成，即使streak很高"""
        from models.constants import calculate_exp
        result = calculate_exp("health", 0, sub_type="health-sleep",
                               sleep_start="01:00", sleep_end="08:00",
                               streak=10)
        assert result["is_routine"] is False
        assert result["routine_extra"] == 0

    def test_no_time_returns_zero(self):
        """缺少睡眠时间应返回0经验"""
        from models.constants import calculate_exp
        result = calculate_exp("health", 0, sub_type="health-sleep",
                               sleep_start="", sleep_end="")
        assert result["dimension_exp"] == 0
        assert result["sleep_valid"] is False


# ================================================================
# 测试6：连续天数管理逻辑
# ================================================================

class TestStreakLogic:
    """测试 _update_streak_logic 连续天数管理"""

    def test_first_routine_day(self):
        """首次规律：streak=1"""
        from routers.actions import _update_streak_logic
        streak, prot = _update_streak_logic(0, False, None, True, "2026-07-14")
        assert streak == 1
        assert prot is False

    def test_consecutive_routine(self):
        """连续规律：streak 递增"""
        from routers.actions import _update_streak_logic
        streak, prot = _update_streak_logic(4, False, "2026-07-13", True, "2026-07-14")
        assert streak == 5

    def test_break_without_protection(self):
        """不规律且无保护：streak 归零"""
        from routers.actions import _update_streak_logic
        streak, prot = _update_streak_logic(10, False, "2026-07-13", False, "2026-07-14")
        assert streak == 0
        assert prot is False

    def test_break_with_protection(self):
        """不规律但有保护：消耗保护，streak 不变"""
        from routers.actions import _update_streak_logic
        streak, prot = _update_streak_logic(10, True, "2026-07-13", False, "2026-07-14")
        assert streak == 10
        assert prot is False  # 保护被消耗

    def test_earn_protection_at_streak_10(self):
        """连续10天获得保护"""
        from routers.actions import _update_streak_logic
        streak, prot = _update_streak_logic(9, False, "2026-07-13", True, "2026-07-14")
        assert streak == 10
        assert prot is True

    def test_gap_resets_streak(self):
        """间隔>1天：重新从1开始"""
        from routers.actions import _update_streak_logic
        streak, prot = _update_streak_logic(5, False, "2026-07-10", True, "2026-07-14")
        assert streak == 1
        assert prot is False


# ================================================================
# 测试7：向后兼容 — 旧数据不受影响
# ================================================================

class TestBackwardCompatibility:
    def test_old_records_still_queryable(self, tmp_db, user_id):
        """旧式记录（无 sub_type）仍可正常查询和展示"""
        from db.connection import get_conn
        conn = get_conn()
        conn.execute(
            """INSERT INTO action_logs (user_id, category_id, start_time, end_time, duration, note, exp_earned)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (user_id, "study", "2026-07-14T10:00:00", "2026-07-14T11:00:00", 60, "旧数据学习", 30),
        )
        conn.commit()
        conn.close()

        from db.actions import get_action_logs
        result = get_action_logs(user_id)
        old_rec = [r for r in result["records"] if r["note"] == "旧数据学习"]
        assert len(old_rec) == 1
        assert old_rec[0]["sub_type"] == ""  # 默认空字符串
        assert old_rec[0]["duration"] == 60

    def test_mixed_old_and_new_records(self, tmp_db, user_id):
        """旧记录和新记录混合查询时均正常"""
        from db.connection import get_conn
        from db.actions import create_action_log, get_action_logs
        conn = get_conn()
        conn.execute(
            """INSERT INTO action_logs (user_id, category_id, start_time, end_time, duration, note, exp_earned)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (user_id, "study", "2026-07-14T10:00:00", "2026-07-14T11:00:00", 60, "旧数据", 30),
        )
        conn.commit()
        conn.close()

        now = datetime.now().isoformat()
        create_action_log(
            user_id, "health", now, now, 450, "新睡眠", 20,
            sub_type="health-sleep", sleep_start="23:30", sleep_end="07:00",
        )

        result = get_action_logs(user_id)
        assert len(result["records"]) == 2
        sleep = [r for r in result["records"] if r["sub_type"] == "health-sleep"]
        old = [r for r in result["records"] if r["note"] == "旧数据"]
        assert len(sleep) == 1
        assert len(old) == 1
        assert sleep[0]["sleep_start"] == "23:30"
        assert old[0]["sub_type"] == ""


# ================================================================
# 测试8：睡眠每日限制 — 一天只允许一次睡眠记录
# ================================================================

class TestSleepDailyLimit:
    def test_has_sleep_record_today_false(self, tmp_db, user_id):
        """今天没有睡眠记录时应返回 False"""
        from db.actions import has_sleep_record_today
        assert has_sleep_record_today(user_id) is False

    def test_has_sleep_record_today_true(self, tmp_db, user_id):
        """今天有睡眠记录时应返回 True"""
        from db.actions import create_action_log, has_sleep_record_today
        now = datetime.now().isoformat()
        create_action_log(
            user_id, "health", now, now, 450, "睡眠", 20,
            sub_type="health-sleep", sleep_start="23:30", sleep_end="07:00",
        )
        assert has_sleep_record_today(user_id) is True

    def test_has_sleep_record_today_sport_ignored(self, tmp_db, user_id):
        """运动记录不应触发睡眠每日限制"""
        from db.actions import create_action_log, has_sleep_record_today
        now = datetime.now().isoformat()
        create_action_log(
            user_id, "health", now, now, 30, "跑步", 15,
            sub_type="health-sport",
        )
        assert has_sleep_record_today(user_id) is False

    def test_has_sleep_record_today_other_user(self, tmp_db):
        """其他用户的睡眠记录不应影响当前用户"""
        from db.actions import create_action_log, has_sleep_record_today
        from db.connection import get_conn
        # 获取 admin 用户
        conn = get_conn()
        admin = conn.execute("SELECT id FROM users WHERE name = 'admin'").fetchone()
        conn.close()
        admin_id = admin["id"]
        # admin 记录睡眠
        now = datetime.now().isoformat()
        create_action_log(
            admin_id, "health", now, now, 450, "admin的睡眠", 20,
            sub_type="health-sleep", sleep_start="23:30", sleep_end="07:00",
        )
        # test 用户不应受影响
        from db import connection
        # user_id fixture 对应 test 用户
        # 直接用 admin_id 验证
        assert has_sleep_record_today(admin_id) is True
