"""
Self Grow — 行动记录 CRUD
"""

from db.connection import get_conn
from models.constants import get_category
import datetime as _dt


def has_finance_review_this_half(user_id: int) -> bool:
    """检查用户当前半月是否已有财务复盘记录（sub_type='finance-review'）
    上半月：1~15日，下半月：16~月末
    注意：16 号归入下半月（half_start = 当月16日），15 号归入上半月（half_end = 当月15日）
    """
    today = _dt.date.today()
    if today.day <= 15:
        half_start = _dt.date(today.year, today.month, 1)
        half_end = _dt.date(today.year, today.month, 15)
    else:
        half_start = _dt.date(today.year, today.month, 16)
        # 下半月结束日：下个月1号 - 1天
        if today.month == 12:
            half_end = _dt.date(today.year + 1, 1, 1) - _dt.timedelta(days=1)
        else:
            half_end = _dt.date(today.year, today.month + 1, 1) - _dt.timedelta(days=1)

    conn = get_conn()
    row = conn.execute(
        """SELECT COUNT(*) as cnt FROM action_logs
           WHERE user_id = ? AND sub_type = 'finance-review'
           AND start_time >= ? AND start_time <= ?""",
        (user_id, f"{half_start.isoformat()}T00:00:00", f"{half_end.isoformat()}T23:59:59"),
    ).fetchone()
    conn.close()
    return row["cnt"] > 0


def has_sleep_record_today(user_id: int) -> bool:
    """检查用户今天是否已有睡眠记录（sub_type='health-sleep'）"""
    today = _dt.date.today().isoformat()
    today_start = f"{today}T00:00:00"
    today_end = f"{today}T23:59:59"
    conn = get_conn()
    row = conn.execute(
        """SELECT COUNT(*) as cnt FROM action_logs
           WHERE user_id = ? AND sub_type = 'health-sleep'
           AND start_time >= ? AND start_time <= ?""",
        (user_id, today_start, today_end),
    ).fetchone()
    conn.close()
    return row["cnt"] > 0


def create_action_log(user_id: int, category_id: str, start_time: str,
                      end_time: str, duration: int, note: str = "",
                      exp_earned: int = 0, sub_type: str = "",
                      sleep_start: str = "", sleep_end: str = "",
                      request_id: str = "", conn=None) -> int:
    """插入行动记录，返回新记录的 id

    重复 request_id 在同用户+同 start_time 下视为幂等，返回已有记录 ID。
    传入 conn 时由调用方负责 commit/close。
    """
    own_conn = conn is None
    if own_conn:
        from db.connection import get_conn as _get_conn
        conn = _get_conn()

    # 幂等：同用户、同起始时间、同 request_id
    if request_id:
        existing = conn.execute(
            """SELECT id FROM action_logs
               WHERE user_id = ? AND start_time = ? AND note = ?
               LIMIT 1""",
            (user_id, start_time, f"[req:{request_id}] {note}" if note else f"[req:{request_id}]"),
        ).fetchone()
        if existing:
            return int(existing["id"])

    note_value = f"[req:{request_id}] {note}" if request_id else note
    cursor = conn.execute(
        """INSERT INTO action_logs
           (user_id, category_id, start_time, end_time, duration, note, exp_earned, sub_type, sleep_start, sleep_end)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (user_id, category_id, start_time, end_time, duration, note_value, exp_earned,
         sub_type, sleep_start, sleep_end),
    )
    new_id = int(cursor.lastrowid)

    if own_conn:
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
        where_clauses.append("(al.note LIKE ? OR al.category_id LIKE ? OR al.sub_type LIKE ?)")
        where_params.append(f"%{search}%")
        where_params.append(f"%{search}%")
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


def get_action_logs_for_export(user_id: int, category: str = None,
                                date_from: str = None, date_to: str = None) -> list:
    """
    导出用查询：无分页限制，按时间升序返回所有匹配记录。
    返回列表，每条含 category_name / category_color 映射。
    """
    conn = get_conn()

    where_clauses = ["al.user_id = ?"]
    where_params = [user_id]

    if category and category != "all":
        where_clauses.append("al.category_id = ?")
        where_params.append(category)

    if date_from:
        where_clauses.append("al.start_time >= ?")
        where_params.append(f"{date_from}T00:00:00")

    if date_to:
        where_clauses.append("al.start_time <= ?")
        where_params.append(f"{date_to}T23:59:59")

    where_sql = " AND ".join(where_clauses)

    rows = conn.execute(
        f"""SELECT al.* FROM action_logs al
            WHERE {where_sql}
            ORDER BY al.start_time ASC, al.id ASC""",
        where_params,
    ).fetchall()
    conn.close()

    records = []
    for r in rows:
        d = dict(r)
        cat = get_category(d["category_id"])
        d["category_name"] = cat["name"] if cat else d["category_id"]
        d["category_color"] = cat["color"] if cat else "#888"
        records.append(d)

    return records


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
           ORDER BY al.start_time DESC, al.id DESC
           LIMIT ?""",
        (user_id, limit),
    ).fetchall()
    conn.close()

    activities = []
    for r in rows:
        d = dict(r)
        cat = get_category(d["category_id"])
        d["category_name"] = cat["name"] if cat else d["category_id"]
        # 睡眠记录生成友好的描述
        if d.get("sub_type") == "health-sleep" and d.get("sleep_start") and d.get("sleep_end"):
            note_preview = f"😴 睡眠 {d['sleep_start']}→{d['sleep_end']}"
            if d.get("note"):
                note_preview += f" · {d['note'][:30]}"
        elif d["note"]:
            note_preview = d["note"][:50]
        else:
            # 固定时长子类型（duration=0），显示友好的子类型标签
            sub_type_labels = {
                "work-daily": "日常工作",
                "work-overtime-weekday": "工作日加班",
                "work-overtime-weekend": "休息日加班",
                "relation-offline": "线下见面",
                "create-publish": "发布作品",
                "finance-review": "半月复盘",
            }
            sub_type = d.get("sub_type", "")
            if sub_type in sub_type_labels:
                note_preview = sub_type_labels[sub_type]
            else:
                note_preview = f"{cat['name'] if cat else ''} {d['duration']}分钟"
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