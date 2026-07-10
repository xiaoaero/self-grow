"""
Self Grow — 用户 CRUD

包含 users 表和 user_stats_daily 表的增删改查。
"""

from db.connection import get_conn
from db.dimensions import get_total_exp_from_dimensions


def get_user(user_id: int):
    """获取用户信息"""
    conn = get_conn()
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    if row:
        return dict(row)
    return None


def get_user_by_name(name: str):
    """按名称查找用户"""
    conn = get_conn()
    row = conn.execute("SELECT * FROM users WHERE name = ?", (name,)).fetchone()
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


def get_user_stats(user_id: int, date: str) -> dict:
    """获取某日统计，无记录则返回默认零值"""
    conn = get_conn()
    row = conn.execute(
        "SELECT focus_minutes, tasks_done, habits_checked, exp_earned FROM user_stats_daily WHERE user_id = ? AND date = ?",
        (user_id, date),
    ).fetchone()
    conn.close()
    if row:
        return dict(row)
    return {"focus_minutes": 0, "tasks_done": 0, "habits_checked": 0, "exp_earned": 0}


def upsert_user_stats(user_id: int, date: str, focus_minutes: int = 0, tasks_done: int = 0,
                      habits_checked: int = 0, exp_earned: int = 0):
    """插入或更新某日统计"""
    conn = get_conn()
    conn.execute("""
        INSERT INTO user_stats_daily (user_id, date, focus_minutes, tasks_done, habits_checked, exp_earned)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id, date) DO UPDATE SET
            focus_minutes = excluded.focus_minutes,
            tasks_done = excluded.tasks_done,
            habits_checked = excluded.habits_checked,
            exp_earned = excluded.exp_earned
    """, (user_id, date, focus_minutes, tasks_done, habits_checked, exp_earned))
    conn.commit()
    conn.close()


def update_user_exp(user_id: int, level: int, exp: int, total_exp: int = None):
    """更新用户等级/经验值（total_exp 为 None 时从维度表实时 SUM）"""
    if total_exp is None:
        total_exp = get_total_exp_from_dimensions(user_id)
    conn = get_conn()
    conn.execute(
        "UPDATE users SET level = ?, exp = ?, total_exp = ? WHERE id = ?",
        (level, exp, total_exp, user_id),
    )
    conn.commit()
    conn.close()