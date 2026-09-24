"""
Self Grow — 定时任务模板 CRUD
"""

from db.connection import get_conn
import json


def get_scheduled_tasks(user_id: int) -> list:
    """获取用户所有模板"""
    conn = get_conn()
    rows = conn.execute(
        """SELECT * FROM scheduled_tasks WHERE user_id = %s ORDER BY type ASC, created_at DESC""",
        (user_id,),
    ).fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        if d["weekdays"]:
            try:
                d["weekdays"] = json.loads(d["weekdays"])
            except (json.JSONDecodeError, TypeError):
                d["weekdays"] = []
        else:
            d["weekdays"] = []
        result.append(d)
    return result


def get_scheduled_task(task_id: int) -> dict:
    """获取单个定时任务模板（返回完整行，含 user_id —— 路由层要做归属校验用）

    原来没有这个函数，PUT/DELETE 直接按 id 改删，于是任何人（甚至未登录）
    都能改掉别人的模板。这里补上单条查询，让路由能先校验归属。
    """
    conn = get_conn()
    row = conn.execute("""SELECT * FROM scheduled_tasks WHERE id = %s""", (task_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_scheduled_tasks_by_type(user_id: int, task_type: str) -> list:
    """按类型获取定时任务模板"""
    conn = get_conn()
    rows = conn.execute(
        """SELECT * FROM scheduled_tasks WHERE user_id = %s AND type = %s ORDER BY id ASC""",
        (user_id, task_type),
    ).fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        if d["weekdays"]:
            try:
                d["weekdays"] = json.loads(d["weekdays"])
            except (json.JSONDecodeError, TypeError):
                d["weekdays"] = []
        else:
            d["weekdays"] = []
        result.append(d)
    return result


def create_scheduled_task(user_id: int, type_: str, title: str, category: str,
                          priority: str = "mid", exp: int = 50, intro: str = "",
                          weekdays: list = None) -> int:
    """创建模板，返回 id"""
    weekdays_json = json.dumps(weekdays or [], ensure_ascii=False)
    conn = get_conn()
    cursor = conn.execute(
        """INSERT INTO scheduled_tasks (user_id, type, title, intro, category, priority, exp, weekdays)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
        (user_id, type_, title, intro, category, priority, exp, weekdays_json),
    )
    new_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return new_id


def update_scheduled_task(task_id: int, **kwargs) -> bool:
    """更新模板字段"""
    allowed = ["type", "title", "intro", "category", "priority", "exp", "weekdays", "active"]
    fields = []
    values = []
    for k, v in kwargs.items():
        if k in allowed and v is not None:
            if k == "weekdays":
                v = json.dumps(v, ensure_ascii=False)
            fields.append(f"{k} = %s")
            values.append(v)
    if not fields:
        return False
    values.append(task_id)
    conn = get_conn()
    conn.execute(f"UPDATE scheduled_tasks SET {', '.join(fields)} WHERE id = %s", values)
    conn.commit()
    conn.close()
    return True


def delete_scheduled_task(task_id: int) -> bool:
    """删除模板"""
    conn = get_conn()
    conn.execute("""DELETE FROM scheduled_tasks WHERE id = %s""", (task_id,))
    conn.commit()
    conn.close()
    return True