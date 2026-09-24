"""
Self Grow — 任务 CRUD
"""

from db.connection import get_conn
import datetime


def get_task(task_id: int):
    """获取单个任务（按 ID 直接查询）"""
    conn = get_conn()
    row = conn.execute("""SELECT * FROM tasks WHERE id = %s""", (task_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_tasks_paginated(user_id: int, page: int = 1, page_size: int = 20,
                        status: str = None, category: str = None,
                        sort: str = "newest") -> dict:
    """分页查询任务历史"""
    conn = get_conn()
    where_clauses = ["user_id = %s"]
    where_params = [user_id]

    if status and status != "all":
        where_clauses.append("status = %s")
        where_params.append(status)
    if category and category != "all":
        where_clauses.append("category = %s")
        where_params.append(category)

    where_sql = " AND ".join(where_clauses)

    count_row = conn.execute(
        f"SELECT COUNT(*) as cnt FROM tasks WHERE {where_sql}",
        where_params,
    ).fetchone()
    total = count_row["cnt"]

    order_map = {
        "newest": "created_at DESC, id DESC",
        "oldest": "created_at ASC, id ASC",
        "exp-high": "exp DESC, created_at DESC",
        "exp-low": "exp ASC, created_at DESC",
    }
    order_sql = order_map.get(sort, "created_at DESC, id DESC")

    offset = (page - 1) * page_size
    rows = conn.execute(
        f"SELECT * FROM tasks WHERE {where_sql} ORDER BY {order_sql} LIMIT %s OFFSET %s",
        where_params + [page_size, offset],
    ).fetchall()
    conn.close()

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "records": [dict(r) for r in rows],
    }


def get_today_tasks(user_id: int) -> dict:
    """获取今日任务（source_type='today' 或 'daily'，仅限今天创建）"""
    conn = get_conn()
    today_start = datetime.date.today().isoformat()
    rows = conn.execute(
        """SELECT * FROM tasks
           WHERE user_id = %s AND source_type IN ('today', 'daily')
           AND date(created_at) = %s
           AND status IN ('todo', 'doing', 'done')
           ORDER BY CASE status
               WHEN 'todo' THEN 1
               WHEN 'doing' THEN 2
               WHEN 'done' THEN 3
           END, created_at ASC""",
        (user_id, today_start),
    ).fetchall()
    conn.close()

    result = {"todo": [], "doing": [], "done": []}
    for r in rows:
        d = dict(r)
        result[d["status"]].append(d)
    return result


def get_week_tasks(user_id: int) -> dict:
    """获取本周任务（source_type='weekly'，周一至周日）"""
    today = datetime.date.today()
    monday = today - datetime.timedelta(days=today.weekday())  # 本周一
    sunday = monday + datetime.timedelta(days=6)                # 本周日
    week_start = monday.isoformat()
    week_end = sunday.isoformat()

    conn = get_conn()
    rows = conn.execute(
        """SELECT * FROM tasks
           WHERE user_id = %s AND source_type = 'weekly'
           AND date(created_at) >= %s AND date(created_at) <= %s
           AND status IN ('todo', 'doing', 'done')
           ORDER BY CASE status
               WHEN 'todo' THEN 1
               WHEN 'doing' THEN 2
               WHEN 'done' THEN 3
           END, created_at ASC""",
        (user_id, week_start, week_end),
    ).fetchall()
    conn.close()

    result = {"todo": [], "doing": [], "done": []}
    for r in rows:
        d = dict(r)
        result[d["status"]].append(d)
    return result


def create_task(user_id: int, title: str, category: str, priority: str = "mid",
                exp: int = 50, intro: str = "", status: str = "todo",
                source_type: str = "today", source_template_id: int = None) -> int:
    """创建任务，返回 id"""
    conn = get_conn()
    # created_at 显式写本地时间：db/batch.py 用 `date(created_at) = 昨天` 判断归档/过期，
    # 而表默认值 datetime('now') 是 UTC → 凌晨 0~8 点建的任务会被归到前一天
    from db.connection import now_str
    cursor = conn.execute(
        """INSERT INTO tasks (user_id, title, category, priority, exp, intro, status,
                              source_type, source_template_id, created_at)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
        (user_id, title, category, priority, exp, intro, status, source_type,
         source_template_id, now_str()),
    )
    new_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return new_id


def update_task(task_id: int, **kwargs) -> bool:
    """更新任务字段"""
    allowed = ["title", "category", "priority", "exp", "intro", "status",
               "deadline", "completed_at", "claimed", "source_type", "source_template_id"]
    fields = []
    values = []
    for k, v in kwargs.items():
        if k in allowed and v is not None:
            fields.append(f"{k} = %s")
            values.append(v)
    if not fields:
        return False
    values.append(task_id)
    conn = get_conn()
    conn.execute(f"UPDATE tasks SET {', '.join(fields)} WHERE id = %s", values)
    conn.commit()
    conn.close()
    return True


def delete_task(task_id: int) -> bool:
    """删除任务"""
    conn = get_conn()
    conn.execute("""DELETE FROM tasks WHERE id = %s""", (task_id,))
    conn.commit()
    conn.close()
    return True


def claim_task_reward(task_id: int) -> dict:
    """领取任务 EXP，返回 exp_earned"""
    conn = get_conn()
    row = conn.execute(
        """SELECT exp, claimed FROM tasks WHERE id = %s""",
        (task_id,),
    ).fetchone()
    if not row or row["claimed"]:
        conn.close()
        return None
    exp_earned = row["exp"]
    conn.execute("""UPDATE tasks SET claimed = 1 WHERE id = %s""", (task_id,))
    conn.commit()
    conn.close()
    return {"exp_earned": exp_earned}