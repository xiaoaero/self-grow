"""
Self Grow — 定时批处理函数

被 APScheduler 定时任务调用，包含每日/每周的任务刷新、习惯结算、统计快照。
"""

from db.connection import get_conn
from db.users import get_user, get_user_stats, upsert_user_stats
from db.habits import get_habits, get_checkins_in_range
from db.dimensions import upsert_dimension, get_total_exp_from_dimensions
from db.scheduled_tasks import get_scheduled_tasks_by_type
from models.level import level_from_total_exp, total_exp_for_level
import datetime


def archive_incomplete_tasks(user_id: int):
    """将昨日未完成的 todo/doing 任务标记为 expired"""
    conn = get_conn()
    yesterday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    conn.execute(
        """UPDATE tasks SET status = 'expired'
           WHERE user_id = ? AND status IN ('todo', 'doing')
           AND date(created_at) <= ?""",
        (user_id, yesterday),
    )
    conn.commit()
    conn.close()


def refresh_daily_tasks(user_id: int):
    """从 daily 模板创建今日任务"""
    templates = get_scheduled_tasks_by_type(user_id, "daily")
    today_weekday = datetime.date.today().isoweekday()  # 1=Mon, 7=Sun
    conn = get_conn()
    for t in templates:
        if not t["active"]:
            continue
        weekdays = t.get("weekdays", [])
        if weekdays and today_weekday not in weekdays:
            continue
        conn.execute(
            """INSERT INTO tasks (user_id, title, category, priority, exp, intro, status, source_type, source_template_id)
               VALUES (?, ?, ?, ?, ?, ?, 'todo', 'daily', ?)""",
            (user_id, t["title"], t["category"], t["priority"],
             t["exp"], t["intro"], t["id"]),
        )
    conn.commit()
    conn.close()


def refresh_weekly_tasks(user_id: int):
    """从 weekly 模板创建本周任务"""
    templates = get_scheduled_tasks_by_type(user_id, "weekly")
    conn = get_conn()
    for t in templates:
        if not t["active"]:
            continue
        conn.execute(
            """INSERT INTO tasks (user_id, title, category, priority, exp, intro, status, source_type, source_template_id)
               VALUES (?, ?, ?, ?, ?, ?, 'todo', 'weekly', ?)""",
            (user_id, t["title"], t["category"], t["priority"],
             t["exp"], t["intro"], t["id"]),
        )
    conn.commit()
    conn.close()


def settle_habit_exp_for_user(user_id: int) -> int:
    """统计昨日已完成的习惯，发放 EXP，返回发放的总 EXP"""
    yesterday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    habits = get_habits(user_id)
    total_xp = 0
    for h in habits:
        if not h["active"]:
            continue
        checkins = get_checkins_in_range(h["id"], yesterday, yesterday)
        if checkins and checkins[0]["status"] == "done":
            xp = h["xp_reward"]
            total_xp += xp
            upsert_dimension(user_id, h["category"], xp)
    if total_xp > 0:
        new_total = get_total_exp_from_dimensions(user_id)
        new_level = level_from_total_exp(new_total)
        user = get_user(user_id)
        new_current = new_total - total_exp_for_level(new_level)
        from db.users import update_user_exp
        update_user_exp(user_id, new_level, new_current)
        today = datetime.date.today().isoformat()
        today_row = get_user_stats(user_id, today)
        upsert_user_stats(
            user_id, today,
            focus_minutes=today_row["focus_minutes"],
            tasks_done=today_row["tasks_done"],
            habits_checked=today_row["habits_checked"],
            exp_earned=today_row["exp_earned"] + total_xp,
        )
    return total_xp


def snapshot_daily_stats(user_id: int):
    """确保前一天的统计数据在数据库中有记录（兜底）"""
    yesterday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    row = get_user_stats(user_id, yesterday)
    upsert_user_stats(
        user_id, yesterday,
        focus_minutes=row["focus_minutes"],
        tasks_done=row["tasks_done"],
        habits_checked=row["habits_checked"],
        exp_earned=row["exp_earned"],
    )