"""
Self Grow — 定时批处理函数

被 APScheduler 定时任务调用，包含每日/每周的任务刷新、习惯结算、统计快照。
"""

from db.connection import get_conn
from db.users import get_user, get_user_stats, upsert_user_stats
from db.habits import get_habits, get_checkins_in_range
from db.dimensions import upsert_dimension, get_total_exp_from_dimensions
from db.scheduled_tasks import get_scheduled_tasks_by_type
from db.task_history import archive_tasks_to_history
from models.level import level_from_total_exp, total_exp_for_level
import datetime


def archive_daily_tasks(user_id: int):
    """
    每日 03:00 执行：将昨天 source_type IN ('today','daily') 的任务归档到 task_history 并删除。
    已完成的任务保留 completed 状态，未完成的标记为 expired。
    """
    yesterday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()

    conn = get_conn()
    # 将昨天未完成的 today/daily 任务标记为 expired
    conn.execute(
        """UPDATE tasks SET status = 'expired'
           WHERE user_id = ? AND source_type IN ('today', 'daily')
           AND date(created_at) = ?
           AND status IN ('todo', 'doing')""",
        (user_id, yesterday),
    )
    # 归档到 task_history 并删除
    count = archive_tasks_to_history(conn, user_id, ['today', 'daily'], yesterday, yesterday)
    conn.commit()
    conn.close()
    return count


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


def archive_weekly_tasks(user_id: int):
    """
    每周一 03:00 执行：将上周 source_type='weekly' 的任务归档到 task_history 并删除。
    """
    today = datetime.date.today()
    # 上周一 ~ 上周日
    last_monday = today - datetime.timedelta(days=today.weekday() + 7)
    last_sunday = last_monday + datetime.timedelta(days=6)

    conn = get_conn()
    # 将上周未完成的 weekly 任务标记为 expired
    conn.execute(
        """UPDATE tasks SET status = 'expired'
           WHERE user_id = ? AND source_type = 'weekly'
           AND date(created_at) >= ? AND date(created_at) <= ?
           AND status IN ('todo', 'doing')""",
        (user_id, last_monday.isoformat(), last_sunday.isoformat()),
    )
    # 归档到 task_history 并删除
    count = archive_tasks_to_history(
        conn, user_id, ['weekly'],
        last_monday.isoformat(), last_sunday.isoformat(),
    )
    conn.commit()
    conn.close()
    return count


def refresh_weekly_tasks(user_id: int):
    """从 weekly 模板创建本周任务（周一凌晨 03:05 执行）"""
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


def settle_habit_exp_for_user(user_id: int) -> tuple:
    """统计昨日已完成的习惯，发放 EXP，返回 (打卡次数, 总经验)"""
    yesterday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    habits = get_habits(user_id)
    total_xp = 0
    total_count = 0
    for h in habits:
        if not h["active"]:
            continue
        checkins = get_checkins_in_range(h["id"], yesterday, yesterday)
        if checkins and checkins[0]["status"] == "done":
            xp = h["xp_reward"]
            total_xp += xp
            total_count += 1
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
    return (total_count, total_xp)


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


def catch_up_missed_archives(user_id: int):
    """
    启动时检查：如果凌晨3点的归档任务未执行（如电脑关机），则补执行。
    - 昨天的 today/daily 任务 → 归档
    - 上周的 weekly 任务 → 归档
    """
    from config import log

    today = datetime.date.today()
    yesterday = (today - datetime.timedelta(days=1)).isoformat()
    conn = get_conn()

    # 1. 检查昨天是否有未归档的 today/daily 任务
    yesterday_tasks = conn.execute(
        """SELECT COUNT(*) as cnt FROM tasks
           WHERE user_id = ? AND source_type IN ('today', 'daily')
           AND date(created_at) = ?""",
        (user_id, yesterday),
    ).fetchone()

    if yesterday_tasks and yesterday_tasks["cnt"] > 0:
        # 将未完成的标记为 expired
        conn.execute(
            """UPDATE tasks SET status = 'expired'
               WHERE user_id = ? AND source_type IN ('today', 'daily')
               AND date(created_at) = ?
               AND status IN ('todo', 'doing')""",
            (user_id, yesterday),
        )
        conn.commit()
        # 归档
        count = archive_tasks_to_history(conn, user_id, ['today', 'daily'], yesterday, yesterday)
        conn.commit()
        if count > 0:
            log.info(f"  🔧 补归档：用户 {user_id} 昨日 {count} 条日任务")

    # 2. 检查上周是否有未归档的 weekly 任务
    last_monday = today - datetime.timedelta(days=today.weekday() + 7)
    last_sunday = last_monday + datetime.timedelta(days=6)

    weekly_tasks = conn.execute(
        """SELECT COUNT(*) as cnt FROM tasks
           WHERE user_id = ? AND source_type = 'weekly'
           AND date(created_at) >= ? AND date(created_at) <= ?""",
        (user_id, last_monday.isoformat(), last_sunday.isoformat()),
    ).fetchone()

    if weekly_tasks and weekly_tasks["cnt"] > 0:
        # 将未完成的标记为 expired
        conn.execute(
            """UPDATE tasks SET status = 'expired'
               WHERE user_id = ? AND source_type = 'weekly'
               AND date(created_at) >= ? AND date(created_at) <= ?
               AND status IN ('todo', 'doing')""",
            (user_id, last_monday.isoformat(), last_sunday.isoformat()),
        )
        conn.commit()
        # 归档
        count = archive_tasks_to_history(
            conn, user_id, ['weekly'],
            last_monday.isoformat(), last_sunday.isoformat(),
        )
        conn.commit()
        if count > 0:
            log.info(f"  🔧 补归档：用户 {user_id} 上周 {count} 条周任务")

    conn.close()
