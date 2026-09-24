"""
Self Grow — 用户 CRUD

包含 users 表和 user_stats_daily 表的增删改查。
"""

from db.connection import get_conn
from db.dimensions import get_total_exp_from_dimensions


def get_user(user_id: int):
    """获取用户信息"""
    conn = get_conn()
    row = conn.execute("""SELECT * FROM users WHERE id = %s""", (user_id,)).fetchone()
    conn.close()
    if row:
        return dict(row)
    return None


def get_user_by_name(name: str):
    """按名称查找用户"""
    conn = get_conn()
    row = conn.execute("""SELECT * FROM users WHERE name = %s""", (name,)).fetchone()
    conn.close()
    if row:
        return dict(row)
    return None


def get_all_users():
    """获取所有用户列表"""
    conn = get_conn()
    rows = conn.execute("SELECT id, name, role FROM users").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_user_stats(user_id: int, date: str, conn=None) -> dict:
    """获取某日统计，无记录则返回默认零值

    ⚠️ 支持传入 conn（传了由调用方负责关闭）。
    调用方若在**尚未提交**的事务里做过 upsert_user_stats，必须传 conn，
    否则另开连接读不到刚写的数据 —— `services/exp_service.py` 的
    「今日统计累加」就是这样读到旧值、把新值覆盖回旧值的。
    """
    own_conn = conn is None
    if own_conn:
        conn = get_conn()

    row = conn.execute(
        """SELECT focus_minutes, tasks_done, habits_checked, exp_earned FROM user_stats_daily WHERE user_id = %s AND date = %s""",
        (user_id, date),
    ).fetchone()

    if own_conn:
        conn.close()

    if row:
        return dict(row)
    return {"focus_minutes": 0, "tasks_done": 0, "habits_checked": 0, "exp_earned": 0}


def upsert_user_stats(user_id: int, date: str, focus_minutes: int = 0, tasks_done: int = 0,
                      habits_checked: int = 0, exp_earned: int = 0, conn=None):
    """插入或更新某日统计。传入 conn 由调用方负责 commit。"""
    own_conn = conn is None
    if own_conn:
        from db.connection import get_conn as _get_conn
        conn = _get_conn()
    conn.execute(
        """INSERT INTO user_stats_daily (user_id, date, focus_minutes, tasks_done, habits_checked, exp_earned)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            focus_minutes = VALUES(focus_minutes),
            tasks_done = VALUES(tasks_done),
            habits_checked = VALUES(habits_checked),
            exp_earned = VALUES(exp_earned)
        """,
        (user_id, date, focus_minutes, tasks_done, habits_checked, exp_earned),
    )
    if own_conn:
        conn.commit()
        conn.close()


def update_user_exp(user_id: int, level: int, exp: int, total_exp: int = None, conn=None):
    """更新用户等级/经验值。传入 conn 由调用方负责 commit。"""
    own_conn = conn is None
    if own_conn:
        from db.connection import get_conn as _get_conn
        conn = _get_conn()
    if total_exp is None:
        # 若无外部 conn，此处会创建自己的连接，不算跨 conn，可接受
        total_exp = get_total_exp_from_dimensions(user_id)
    conn.execute(
        """UPDATE users SET level = %s, exp = %s, total_exp = %s WHERE id = %s""",
        (level, exp, total_exp, user_id),
    )
    if own_conn:
        conn.commit()
        conn.close()