"""
Self Grow — 任务历史 CRUD

由定时归档任务将 tasks 表中的完成/过期任务移入此表永久保存。
"""

from db.connection import get_conn


def get_task_history(user_id: int, page: int = 1, page_size: int = 20,
                     status: str = None, source_type: str = None) -> dict:
    """分页查询任务历史，按 archived_at DESC 排序"""
    conn = get_conn()
    where_clauses = ["user_id = ?"]
    where_params = [user_id]

    if status and status != "all":
        where_clauses.append("status = ?")
        where_params.append(status)
    if source_type and source_type != "all":
        where_clauses.append("source_type = ?")
        where_params.append(source_type)

    where_sql = " AND ".join(where_clauses)

    count_row = conn.execute(
        f"SELECT COUNT(*) as cnt FROM task_history WHERE {where_sql}",
        where_params,
    ).fetchone()
    total = count_row["cnt"]

    offset = (page - 1) * page_size
    rows = conn.execute(
        f"SELECT * FROM task_history WHERE {where_sql} ORDER BY archived_at DESC, id DESC LIMIT ? OFFSET ?",
        where_params + [page_size, offset],
    ).fetchall()
    conn.close()

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "records": [dict(r) for r in rows],
    }


def archive_tasks_to_history(conn, user_id: int, source_types: list, date_start: str, date_end: str) -> int:
    """
    将指定日期范围内、指定 source_type 的任务复制到 task_history 并删除。
    需在调用方的事务/连接中执行，不自动 commit/close。
    返回归档数量。
    """
    placeholders = ",".join("?" for _ in source_types)
    params = [user_id] + source_types + [date_start, date_end]

    # 先查出要归档的任务
    rows = conn.execute(
        f"""SELECT id, title, category, priority, exp, intro, status, source_type, completed_at, created_at
            FROM tasks
            WHERE user_id = ? AND source_type IN ({placeholders})
            AND date(created_at) >= ? AND date(created_at) <= ?
            AND status IN ('todo', 'doing', 'done', 'completed', 'expired')""",
        params,
    ).fetchall()

    if not rows:
        return 0

    # 批量插入 task_history
    for r in rows:
        conn.execute(
            """INSERT INTO task_history
               (user_id, task_id, title, category, priority, exp, intro, status, source_type, completed_at, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (user_id, r["id"], r["title"], r["category"], r["priority"],
             r["exp"], r["intro"], r["status"], r["source_type"],
             r["completed_at"], r["created_at"]),
        )

    # 从 tasks 表删除已归档的任务
    conn.execute(
        f"""DELETE FROM tasks
            WHERE user_id = ? AND source_type IN ({placeholders})
            AND date(created_at) >= ? AND date(created_at) <= ?""",
        params,
    )

    return len(rows)


def clear_task_history(user_id: int) -> int:
    """清空用户的任务历史"""
    conn = get_conn()
    cursor = conn.execute(
        "DELETE FROM task_history WHERE user_id = ?",
        (user_id,),
    )
    deleted = cursor.rowcount
    conn.commit()
    conn.close()
    return deleted
