"""
Self Grow — 维度经验 CRUD

八维属性（健康/学习/关系/工作/创作/财务/爱好/魅力）的经验管理。
"""

from db.connection import get_conn
from models.level import exp_for_level, total_exp_for_level


def get_user_dimensions(user_id: int) -> list:
    """获取用户 8 维数据"""
    conn = get_conn()
    rows = conn.execute(
        """SELECT * FROM user_dimensions WHERE user_id = %s""",
        (user_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def upsert_dimension(user_id: int, dimension_key: str, xp_add: float = 0, conn=None):
    """增量更新维度 XP（小数精度保留），检查是否需要升级。传入 conn 由调用方负责 commit。"""
    own_conn = conn is None
    if own_conn:
        from db.connection import get_conn as _get_conn
        conn = _get_conn()

    row = conn.execute(
        """SELECT level, xp, xp_to_next FROM user_dimensions WHERE user_id = %s AND dimension_key = %s""",
        (user_id, dimension_key),
    ).fetchone()

    if not row:
        conn.execute(
            """INSERT INTO user_dimensions (user_id, dimension_key, level, xp, xp_to_next) VALUES (%s, %s, 1, 0, 150)""",
            (user_id, dimension_key),
        )
        row = conn.execute(
            """SELECT level, xp, xp_to_next FROM user_dimensions WHERE user_id = %s AND dimension_key = %s""",
            (user_id, dimension_key),
        ).fetchone()

    level = row["level"]
    xp = row["xp"] + xp_add
    xp_to_next = row["xp_to_next"]

    while xp >= xp_to_next and level < 140:
        xp -= xp_to_next
        level += 1
        xp_to_next = exp_for_level(level)

    conn.execute(
        """UPDATE user_dimensions SET level = %s, xp = %s, xp_to_next = %s WHERE user_id = %s AND dimension_key = %s""",
        (level, xp, xp_to_next, user_id, dimension_key),
    )

    if own_conn:
        conn.commit()
        conn.close()
    return {"level": level, "xp": xp, "xp_to_next": xp_to_next}


def get_total_exp_from_dimensions(user_id: int, conn=None) -> int:
    """从 8 维表 SUM 出全局总经验（level 累计经验 + 剩余经验，返回整数）

    ⚠️ 支持传入 conn（传了由调用方负责关闭）。
    调用方若正处在一个**尚未提交**的事务里，必须把 conn 传进来 —— 否则本函数
    会另开一条连接，**读不到同事务里刚 upsert 的维度经验**，算出的总经验与
    等级会永远滞后一条记录。`services/exp_service.py` 正是踩了这个：
    它上一句刚 `upsert_dimension(..., conn=conn)`，下一句就来这里查。
    """
    own_conn = conn is None
    if own_conn:
        conn = get_conn()

    rows = conn.execute(
        """SELECT level, xp FROM user_dimensions WHERE user_id = %s""",
        (user_id,),
    ).fetchall()

    if own_conn:
        conn.close()

    total = 0.0
    for r in rows:
        total += total_exp_for_level(r["level"]) + r["xp"]
    return round(total)