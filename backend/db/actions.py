"""
Self Grow — 行动记录 CRUD
"""

from db.connection import get_conn
from models.constants import get_category
import datetime as _dt


def create_action_log(user_id: int, category_id: str, start_time: str,
                      end_time: str, duration: int, note: str = "",
                      exp_earned: int = 0) -> int:
    """插入行动记录，返回新记录的 id"""
    conn = get_conn()
    cursor = conn.execute(
        """INSERT INTO action_logs (user_id, category_id, start_time, end_time, duration, note, exp_earned)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (user_id, category_id, start_time, end_time, duration, note, exp_earned),
    )
    new_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return new_id


def get_action_logs(user_id: int, page: int = 1, page_size: int = 20,
                    category: str = None, sort: str = "newest",
                    search: str = None, date_from: str = None,
                    date_to: str = None) -> dict:
    """分页查询行动记录，返回 { total, page, page_size, total_duration, total_exp, records }"""
    conn = get_conn()

    where_clauses = ["al.user_id = ?"]
    where_params = [user_id]

    if category and category != "all":
        where_clauses.append("al.category_id = ?")
        where_params.append(category)

    if search:
        where_clauses.append("al.note LIKE ?")
        where_params.append(f"%{search}%")

    if date_from:
        where_clauses.append("al.start_time >= ?")
        where_params.append(f"{date_from}T00:00:00")

    if date_to:
        where_clauses.append("al.start_time <= ?")
        where_params.append(f"{date_to}T23:59:59")

    where_sql = " AND ".join(where_clauses)

    count_row = conn.execute(
        f"SELECT COUNT(*) as cnt, COALESCE(SUM(duration),0) as total_dur, COALESCE(SUM(exp_earned),0) as total_xp FROM action_logs al WHERE {where_sql}",
        where_params,
    ).fetchone()

    total = count_row["cnt"]
    total_duration = count_row["total_dur"]
    total_exp = count_row["total_xp"]

    order_map = {
        "newest": "start_time DESC, id DESC",
        "oldest": "start_time ASC, id ASC",
        "exp-desc": "exp_earned DESC, start_time DESC",
        "exp-asc": "exp_earned ASC, start_time DESC",
        "duration-desc": "duration DESC, start_time DESC",
        "duration-asc": "duration ASC, start_time DESC",
    }
    order_sql = order_map.get(sort, "start_time DESC, id DESC")

    offset = (page - 1) * page_size
    rows = conn.execute(
        f"""SELECT al.* FROM action_logs al
            WHERE {where_sql}
            ORDER BY {order_sql}
            LIMIT ? OFFSET ?""",
        where_params + [page_size, offset],
    ).fetchall()
    conn.close()

    records = []
    for r in rows:
        d = dict(r)
        cat = get_category(d["category_id"])
        d["category_name"] = cat["name"] if cat else d["category_id"]
        d["category_color"] = cat["color"] if cat else "#888"
        records.append(d)

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_duration": total_duration,
        "total_exp": total_exp,
        "records": records,
    }


def get_today_action_stats(user_id: int) -> dict:
    """获取今日行动统计（分类分布 + 最近行动 + 总数）"""
    today = _dt.date.today().isoformat()
    today_start = f"{today}T00:00:00"
    today_end = f"{today}T23:59:59"

    conn = get_conn()

    cat_rows = conn.execute(
        """SELECT category_id, COUNT(*) as count, COALESCE(SUM(duration),0) as duration, COALESCE(SUM(exp_earned),0) as exp
           FROM action_logs
           WHERE user_id = ? AND start_time >= ? AND start_time <= ?
           GROUP BY category_id
           ORDER BY duration DESC""",
        (user_id, today_start, today_end),
    ).fetchall()

    total_dur = 0
    total_exp = 0
    category_dist = []
    for r in cat_rows:
        d = dict(r)
        cat = get_category(d["category_id"])
        name = cat["name"] if cat else d["category_id"]
        total_dur += d["duration"]
        total_exp += d["exp"]
        category_dist.append({
            "category_id": d["category_id"],
            "name": name,
            "count": d["count"],
            "duration": d["duration"],
            "exp": d["exp"],
        })

    for cd in category_dist:
        cd["pct"] = round(cd["duration"] / total_dur * 100) if total_dur > 0 else 0

    recent = conn.execute(
        """SELECT al.* FROM action_logs al
           WHERE al.user_id = ?
           ORDER BY al.start_time DESC, al.id DESC
           LIMIT 8""",
        (user_id,),
    ).fetchall()
    conn.close()

    recent_actions = []
    for r in recent:
        d = dict(r)
        cat = get_category(d["category_id"])
        d["category_name"] = cat["name"] if cat else d["category_id"]
        recent_actions.append(d)

    return {
        "total_count": len(cat_rows),
        "total_duration": total_dur,
        "total_exp": total_exp,
        "category_dist": category_dist,
        "recent_actions": recent_actions,
    }


def get_activity_feed(user_id: int, limit: int = 20) -> list:
    """获取动态播报列表（按时间倒序，一条 action 生成一条播报）"""
    conn = get_conn()
    rows = conn.execute(
        """SELECT al.* FROM action_logs al
           WHERE al.user_id = ?
           ORDER BY al.created_at DESC, al.id DESC
           LIMIT ?""",
        (user_id, limit),
    ).fetchall()
    conn.close()

    activities = []
    for r in rows:
        d = dict(r)
        cat = get_category(d["category_id"])
        d["category_name"] = cat["name"] if cat else d["category_id"]
        note_preview = d["note"][:50] if d["note"] else f"{cat['name'] if cat else ''} {d['duration']}分钟"
        d["description"] = note_preview
        created = d["created_at"]
        if created:
            try:
                dt = _dt.datetime.fromisoformat(created)
                d["timestamp"] = dt.strftime("%Y/%m/%d %H:%M")
            except (ValueError, AttributeError):
                d["timestamp"] = created[:16]
        else:
            d["timestamp"] = ""
        activities.append(d)

    return activities