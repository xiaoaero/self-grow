"""
Self Grow — 维度经验 CRUD

八维属性（健康/学习/关系/工作/创作/财务/爱好/心灵）的经验管理。
"""

from db.connection import get_conn
from models.level import exp_for_level, total_exp_for_level


def get_user_dimensions(user_id: int) -> list:
    """获取用户 8 维数据"""
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM user_dimensions WHERE user_id = ?",
        (user_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def upsert_dimension(user_id: int, dimension_key: str, xp_add: int = 0):
    """增量更新维度 XP，检查是否需要升级"""
    conn = get_conn()

    row = conn.execute(
        "SELECT level, xp, xp_to_next FROM user_dimensions WHERE user_id = ? AND dimension_key = ?",
        (user_id, dimension_key),
    ).fetchone()

    if not row:
        conn.execute(
            "INSERT INTO user_dimensions (user_id, dimension_key, level, xp, xp_to_next) VALUES (?, ?, 1, 0, 150)",
            (user_id, dimension_key),
        )
        row = conn.execute(
            "SELECT level, xp, xp_to_next FROM user_dimensions WHERE user_id = ? AND dimension_key = ?",
            (user_id, dimension_key),
        ).fetchone()

    level = row["level"]
    xp = row["xp"] + xp_add
    xp_to_next = row["xp_to_next"]

    # 检查是否升级（复用等级公式，维度上限 120 级）
    while xp >= xp_to_next and level < 120:
        xp -= xp_to_next
        level += 1
        xp_to_next = exp_for_level(level)

    conn.execute(
        "UPDATE user_dimensions SET level = ?, xp = ?, xp_to_next = ? WHERE user_id = ? AND dimension_key = ?",
        (level, xp, xp_to_next, user_id, dimension_key),
    )
    conn.commit()
    conn.close()
    return {"level": level, "xp": xp, "xp_to_next": xp_to_next}


def recalc_dimensions_from_actions(user_id: int):
    """从 action_logs 按 category_id 聚合重算所有维度"""
    conn = get_conn()
    rows = conn.execute(
        "SELECT category_id, SUM(exp_earned) as total_xp FROM action_logs WHERE user_id = ? GROUP BY category_id",
        (user_id,),
    ).fetchall()
    conn.close()

    for r in rows:
        upsert_dimension(user_id, r["category_id"], r["total_xp"])

    # 确保所有 8 维都有数据（没 action 的维度保持 0）
    from db.init import init_default_dimensions
    init_default_dimensions(user_id)


def get_total_exp_from_dimensions(user_id: int) -> int:
    """从 8 维表 SUM 出全局总经验（level 累计经验 + 剩余经验）"""
    conn = get_conn()
    rows = conn.execute(
        "SELECT level, xp FROM user_dimensions WHERE user_id = ?",
        (user_id,),
    ).fetchall()
    conn.close()
    total = 0
    for r in rows:
        total += total_exp_for_level(r["level"]) + r["xp"]
    return total