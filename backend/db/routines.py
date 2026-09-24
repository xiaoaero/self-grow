"""
Self Grow — 规律作息持久化
"""

from db.connection import get_conn


def get_routine_streak(user_id: int) -> dict:
    """获取用户规律作息状态，返回 { streak, has_protection, last_date }"""
    conn = get_conn()
    row = conn.execute(
        """SELECT streak, has_protection, last_date FROM routine_streak WHERE user_id = %s""",
        (user_id,),
    ).fetchone()
    conn.close()
    if row:
        return {
            "streak": row["streak"],
            "has_protection": bool(row["has_protection"]),
            "last_date": row["last_date"],
        }
    return {"streak": 0, "has_protection": False, "last_date": None}


def upsert_routine_streak(user_id: int, streak: int, has_protection: bool, last_date: str):
    """插入或更新规律作息状态"""
    conn = get_conn()
    conn.execute(
        """INSERT INTO routine_streak (user_id, streak, has_protection, last_date)
           VALUES (%s, %s, %s, %s)
           ON DUPLICATE KEY UPDATE
               streak = VALUES(streak),
               has_protection = VALUES(has_protection),
               last_date = VALUES(last_date)
        """,
        (user_id, streak, int(has_protection), last_date),
    )
    conn.commit()
    conn.close()
