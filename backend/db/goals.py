"""
Self Grow — 目标 CRUD
"""

from db.connection import get_conn


def get_goals(user_id: int) -> list:
    """获取用户所有目标（含里程碑）"""
    conn = get_conn()
    goal_rows = conn.execute(
        """SELECT * FROM goals WHERE user_id = %s ORDER BY created_at DESC""",
        (user_id,),
    ).fetchall()
    conn.close()

    result = []
    for g in goal_rows:
        goal = dict(g)
        goal["milestones"] = get_goal_milestones(goal["id"])
        result.append(goal)
    return result


def get_goal(goal_id: int) -> dict:
    """获取单个目标（含里程碑）"""
    conn = get_conn()
    row = conn.execute("""SELECT * FROM goals WHERE id = %s""", (goal_id,)).fetchone()
    conn.close()
    if not row:
        return None
    goal = dict(row)
    goal["milestones"] = get_goal_milestones(goal_id)
    return goal


def get_goal_milestones(goal_id: int) -> list:
    """获取目标的里程碑列表"""
    conn = get_conn()
    rows = conn.execute(
        """SELECT * FROM goal_milestones WHERE goal_id = %s ORDER BY sort_order ASC""",
        (goal_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def create_goal(user_id: int, title: str, intro: str, category: str,
                deadline: str, reward_exp: int, category_image: str,
                milestones: list) -> int:
    """创建目标及里程碑，返回目标 id"""
    conn = get_conn()
    cursor = conn.execute(
        """INSERT INTO goals (user_id, title, intro, category, deadline, reward_exp, category_image)
           VALUES (%s, %s, %s, %s, %s, %s, %s)""",
        (user_id, title, intro, category, deadline, reward_exp, category_image or ''),
    )
    goal_id = cursor.lastrowid

    done_count = sum(1 for m in milestones if m.get("done"))
    total_count = len(milestones)
    progress = round(done_count / total_count * 100) if total_count > 0 else 0
    conn.execute("""UPDATE goals SET progress = %s WHERE id = %s""", (progress, goal_id))

    for i, m in enumerate(milestones):
        conn.execute(
            """INSERT INTO goal_milestones (goal_id, done, note, sort_order) VALUES (%s, %s, %s, %s)""",
            (goal_id, 1 if m.get("done") else 0, m.get("note", ""), i),
        )

    conn.commit()
    conn.close()
    return goal_id


def update_goal(goal_id: int, title: str = None, intro: str = None,
                category: str = None, deadline: str = None,
                reward_exp: int = None, category_image: str = None,
                milestones: list = None) -> bool:
    """更新目标及里程碑，返回是否成功"""
    conn = get_conn()
    fields = []
    values = []
    for k, v in [('title', title), ('intro', intro), ('category', category),
                 ('deadline', deadline), ('reward_exp', reward_exp),
                 ('category_image', category_image)]:
        if v is not None:
            fields.append(f"{k} = %s")
            values.append(v)

    if milestones is not None:
        done_count = sum(1 for m in milestones if m.get("done"))
        total_count = len(milestones)
        progress = round(done_count / total_count * 100) if total_count > 0 else 0
        fields.append("progress = %s")
        values.append(progress)

    if fields:
        values.append(goal_id)
        conn.execute(f"UPDATE goals SET {', '.join(fields)} WHERE id = %s", values)

    if milestones is not None:
        conn.execute("""DELETE FROM goal_milestones WHERE goal_id = %s""", (goal_id,))
        for i, m in enumerate(milestones):
            conn.execute(
                """INSERT INTO goal_milestones (goal_id, done, note, sort_order) VALUES (%s, %s, %s, %s)""",
                (goal_id, 1 if m.get("done") else 0, m.get("note", ""), i),
            )

    conn.commit()
    conn.close()
    return True


def delete_goal(goal_id: int) -> bool:
    """删除目标（级联删除里程碑由 ON DELETE CASCADE 处理）"""
    conn = get_conn()
    conn.execute("""DELETE FROM goal_milestones WHERE goal_id = %s""", (goal_id,))
    conn.execute("""DELETE FROM goals WHERE id = %s""", (goal_id,))
    conn.commit()
    conn.close()
    return True


def claim_goal_reward(goal_id: int) -> dict:
    """领取目标奖励，返回 exp_earned"""
    conn = get_conn()
    row = conn.execute(
        """SELECT reward_exp, claimed FROM goals WHERE id = %s""",
        (goal_id,),
    ).fetchone()
    if not row or row["claimed"]:
        conn.close()
        return None
    exp_earned = row["reward_exp"]
    conn.execute("""UPDATE goals SET claimed = 1 WHERE id = %s""", (goal_id,))
    conn.commit()
    conn.close()
    return {"exp_earned": exp_earned}