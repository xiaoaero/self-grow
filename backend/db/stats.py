"""
Self Grow — 统计查询

包含仪表盘和成长记录页面的各种统计查询函数。
"""

from db.connection import get_conn
from db.dimensions import get_total_exp_from_dimensions, get_user_dimensions
from models.constants import CATEGORY_MAP
from models.level import total_exp_for_level
import datetime


def get_recent_activities(user_id: int, limit: int = 10) -> list:
    """从 action_logs 生成仪表盘动态播报"""
    conn = get_conn()
    rows = conn.execute(
        """SELECT al.* FROM action_logs al
           WHERE al.user_id = %s
           ORDER BY al.created_at DESC, al.id DESC
           LIMIT %s""",
        (user_id, limit),
    ).fetchall()
    conn.close()

    activities = []
    now = datetime.datetime.now()
    for r in rows:
        d = dict(r)
        from models.constants import get_category
        cat = get_category(d["category_id"])
        cat_name = cat["name"] if cat else d["category_id"]

        created_str = d.get("created_at") or d.get("start_time", "")
        try:
            created_dt = datetime.datetime.fromisoformat(created_str)
            # 历史数据里可能有带时区偏移的串（旧版前端发的是 toISOString()），
            # 统一折算成本地 naive 再比较，否则 aware 与 naive 相减会直接抛异常
            if created_dt.tzinfo is not None:
                created_dt = created_dt.astimezone().replace(tzinfo=None)
        except (ValueError, TypeError):
            created_dt = now
        # 两边都是本地时间（created_at 由 db/connection.now_str() 写入本地时间）。
        # 修正前 created_at 来自 SQLite 的 datetime('now')（UTC），与本地时间相减
        # 恒定差 8 小时 → 刚记录完也显示"8小时前"
        delta = now - created_dt
        if delta.total_seconds() < 60:
            time_str = "刚刚"
        elif delta.total_seconds() < 3600:
            time_str = f"{int(delta.total_seconds() // 60)}分钟前"
        elif delta.total_seconds() < 7200:
            time_str = "1小时前"
        elif delta.total_seconds() < 86400:
            time_str = f"{int(delta.total_seconds() // 3600)}小时前"
        elif delta.total_seconds() < 172800:
            time_str = "昨天"
        else:
            time_str = f"{int(delta.days)}天前"

        note = d.get("note", "") or ""
        target = note[:20] if note else f"{cat_name} {d['duration']}分钟"

        activities.append({
            "time": time_str,
            "action": "记录了",
            "target": target,
            "category": d["category_id"],
            "exp": d["exp_earned"],
        })

    return activities


def get_yearly_activity(user_id: int, year: int = None) -> list:
    """获取某年每日 EXP 聚合（用于热力图）"""
    if year is None:
        year = datetime.date.today().year

    conn = get_conn()
    rows = conn.execute(
        """SELECT date, exp_earned FROM user_stats_daily
           WHERE user_id = %s AND date >= %s AND date <= %s
           ORDER BY date ASC""",
        (user_id, f"{year}-01-01", f"{year}-12-31"),
    ).fetchall()
    conn.close()

    exp_map = {r["date"]: r["exp_earned"] for r in rows}

    result = []
    start = datetime.date(year, 1, 1)
    end = datetime.date(year, 12, 31)
    current = start
    while current <= end:
        date_str = current.isoformat()
        result.append({"date": date_str, "exp": exp_map.get(date_str, 0)})
        current += datetime.timedelta(days=1)

    return result


def get_daily_exp_trend(user_id: int, days: int = 30) -> list:
    """获取最近 N 天每日 EXP 趋势"""
    end = datetime.date.today()
    start = end - datetime.timedelta(days=days - 1)

    conn = get_conn()
    rows = conn.execute(
        """SELECT date, exp_earned FROM user_stats_daily
           WHERE user_id = %s AND date >= %s AND date <= %s
           ORDER BY date ASC""",
        (user_id, start.isoformat(), end.isoformat()),
    ).fetchall()
    conn.close()

    exp_map = {r["date"]: r["exp_earned"] for r in rows}

    result = []
    current = start
    while current <= end:
        date_str = current.isoformat()
        result.append({"date": date_str, "exp": exp_map.get(date_str, 0)})
        current += datetime.timedelta(days=1)

    return result


def get_profile_stats(user_id: int) -> dict:
    """聚合计算 6 项统计数字 + 8 维进度"""
    conn = get_conn()

    user = conn.execute("""SELECT * FROM users WHERE id = %s""", (user_id,)).fetchone()
    if not user:
        conn.close()
        return None

    user = dict(user)

    joined = datetime.date.fromisoformat(user["joined"])
    effort_days = (datetime.date.today() - joined).days

    checkin_row = conn.execute(
        """SELECT COUNT(*) as cnt FROM habit_checkins hc
           JOIN habits h ON hc.habit_id = h.id
           WHERE h.user_id = %s AND hc.status = 'done'""",
        (user_id,),
    ).fetchone()

    tasks_row = conn.execute(
        """SELECT COUNT(*) as cnt FROM tasks WHERE user_id = %s AND claimed = 1""",
        (user_id,),
    ).fetchone()

    goals_row = conn.execute(
        """SELECT COUNT(*) as cnt FROM goals WHERE user_id = %s AND progress = 100 AND claimed = 1""",
        (user_id,),
    ).fetchone()

    rewards_row = conn.execute(
        """SELECT COUNT(*) as cnt FROM rewards WHERE user_id = %s AND unlocked = 1""",
        (user_id,),
    ).fetchone()
    rewards_unlocked = rewards_row["cnt"] if rewards_row else 0

    conn.close()

    dimensions = get_user_dimensions(user_id)
    dim_list = []
    for d in dimensions:
        info = CATEGORY_MAP.get(d["dimension_key"], (d["dimension_key"], "#888"))
        dim_list.append({
            "name": info[0],
            "key": d["dimension_key"],
            "level": d["level"],
            "xp": d["xp"],
            "totalXp": total_exp_for_level(d["level"]) + d["xp"],
            "xpToNext": d["xp_to_next"],
            "color": info[1],
        })

    return {
        "effortDays": effort_days,
        "totalXP": get_total_exp_from_dimensions(user_id),
        "habitCheckins": checkin_row["cnt"] if checkin_row else 0,
        "tasksCompleted": tasks_row["cnt"] if tasks_row else 0,
        "goalsAchieved": goals_row["cnt"] if goals_row else 0,
        "rewardsUnlocked": rewards_unlocked,
        "dimensions": dim_list,
    }