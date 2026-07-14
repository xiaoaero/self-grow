"""
Self Grow — 奖励商城 CRUD + 条件评估引擎

包含奖励的增删改查、解锁/领取条件的结构化评估。
"""

from db.connection import get_conn
from db.habits import get_habits, calculate_streak
from db.goals import get_goal
from db.dimensions import get_total_exp_from_dimensions
import json
import datetime


# ================================================================
# 奖励 CRUD
# ================================================================

def get_rewards(user_id: int) -> list:
    """获取用户所有奖励"""
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM rewards WHERE user_id = ? ORDER BY created_at ASC",
        (user_id,),
    ).fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        d["unlock_conditions"] = json.loads(d.get("unlock_conditions", "[]"))
        d["claim_conditions"] = json.loads(d.get("claim_conditions", "[]"))
        d["manual_confirmed"] = json.loads(d.get("manual_confirmed", "[]"))
        result.append(d)
    return result


def get_reward(reward_id: int):
    """获取单个奖励"""
    conn = get_conn()
    row = conn.execute("SELECT * FROM rewards WHERE id = ?", (reward_id,)).fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    d["unlock_conditions"] = json.loads(d.get("unlock_conditions", "[]"))
    d["claim_conditions"] = json.loads(d.get("claim_conditions", "[]"))
    d["manual_confirmed"] = json.loads(d.get("manual_confirmed", "[]"))
    return d


def create_reward(user_id: int, title: str, desc: str = "", icon: str = "🎁",
                   category: str = "", image: str = "",
                   unlock_conditions: list = None, claim_conditions: list = None) -> int:
    """创建奖励，返回 id"""
    unlock_json = json.dumps(unlock_conditions or [], ensure_ascii=False)
    claim_json = json.dumps(claim_conditions or [], ensure_ascii=False)

    conn = get_conn()
    user = conn.execute("SELECT total_exp FROM users WHERE id = ?", (user_id,)).fetchone()
    created_at_exp = user["total_exp"] if user else 0

    cursor = conn.execute(
        """INSERT INTO rewards (user_id, title, desc, icon, category, image,
           unlock_conditions, claim_conditions, manual_confirmed, created_at_exp)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, '[]', ?)""",
        (user_id, title, desc, icon, category, image,
         unlock_json, claim_json, created_at_exp),
    )
    new_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return new_id


def update_reward(reward_id: int, **kwargs) -> bool:
    """更新奖励字段"""
    allowed = ["title", "desc", "icon", "category", "image",
               "unlock_conditions", "claim_conditions", "unlocked",
               "claimed", "claimed_at", "manual_confirmed"]
    fields = []
    values = []
    for k, v in kwargs.items():
        if k in allowed and v is not None:
            if k in ("unlock_conditions", "claim_conditions", "manual_confirmed"):
                v = json.dumps(v, ensure_ascii=False)
            fields.append(f"{k} = ?")
            values.append(v)
    if not fields:
        return False
    values.append(reward_id)
    conn = get_conn()
    conn.execute(f"UPDATE rewards SET {', '.join(fields)} WHERE id = ?", values)
    conn.commit()
    conn.close()
    return True


def delete_reward(reward_id: int) -> bool:
    """删除奖励"""
    conn = get_conn()
    conn.execute("DELETE FROM rewards WHERE id = ?", (reward_id,))
    conn.commit()
    conn.close()
    return True


# ================================================================
# 奖励草稿 CRUD
# ================================================================

def save_reward_draft(user_id: int, data: dict) -> bool:
    """保存/覆盖奖励草稿"""
    unlock_json = json.dumps(data.get("unlock_conditions", []), ensure_ascii=False)
    claim_json = json.dumps(data.get("claim_conditions", []), ensure_ascii=False)
    conn = get_conn()
    conn.execute(
        """INSERT INTO reward_drafts (user_id, title, desc, icon, category, image,
           unlock_conditions, claim_conditions, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
           ON CONFLICT(user_id) DO UPDATE SET
           title=excluded.title, desc=excluded.desc, icon=excluded.icon,
           category=excluded.category, image=excluded.image,
           unlock_conditions=excluded.unlock_conditions,
           claim_conditions=excluded.claim_conditions,
           updated_at=datetime('now')""",
        (user_id, data.get("title", ""), data.get("desc", ""), data.get("icon", "🎁"),
         data.get("category", ""), data.get("image", ""), unlock_json, claim_json),
    )
    conn.commit()
    conn.close()
    return True


def get_reward_draft(user_id: int) -> dict | None:
    """获取用户草稿"""
    conn = get_conn()
    row = conn.execute("SELECT * FROM reward_drafts WHERE user_id = ?", (user_id,)).fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    d["unlock_conditions"] = json.loads(d.get("unlock_conditions", "[]"))
    d["claim_conditions"] = json.loads(d.get("claim_conditions", "[]"))
    return d


def delete_reward_draft(user_id: int) -> bool:
    """删除草稿"""
    conn = get_conn()
    conn.execute("DELETE FROM reward_drafts WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()
    return True


def claim_reward(reward_id: int, user_id: int) -> dict:
    """领取奖励（后端校验条件），返回 exp_earned 或 None"""
    conn = get_conn()
    row = conn.execute("SELECT * FROM rewards WHERE id = ? AND user_id = ?",
                       (reward_id, user_id)).fetchone()
    if not row or row["claimed"]:
        conn.close()
        return None

    reward = dict(row)
    reward["unlock_conditions"] = json.loads(reward.get("unlock_conditions", "[]"))
    reward["claim_conditions"] = json.loads(reward.get("claim_conditions", "[]"))
    reward["manual_confirmed"] = json.loads(reward.get("manual_confirmed", "[]"))

    for cond in reward["claim_conditions"]:
        if not evaluate_condition(user_id, cond, reward):
            conn.close()
            return None

    today = datetime.date.today().isoformat()
    conn.execute(
        "UPDATE rewards SET claimed = 1, claimed_at = ? WHERE id = ?",
        (today, reward_id),
    )
    conn.commit()
    conn.close()

    return {"claimed": True, "claimed_at": today}


def manual_confirm_condition(reward_id: int, condition_text: str) -> bool:
    """手动确认某个条件"""
    conn = get_conn()
    row = conn.execute("SELECT manual_confirmed FROM rewards WHERE id = ?",
                       (reward_id,)).fetchone()
    if not row:
        conn.close()
        return False
    confirmed = json.loads(row["manual_confirmed"])
    if condition_text not in confirmed:
        confirmed.append(condition_text)
    conn.execute("UPDATE rewards SET manual_confirmed = ? WHERE id = ?",
                 (json.dumps(confirmed, ensure_ascii=False), reward_id))
    conn.commit()
    conn.close()
    return True


# ================================================================
# 条件评估引擎
# ================================================================

def calculate_week_completion_rate(user_id: int) -> int:
    """计算本周习惯完成率（百分比）"""
    today = datetime.date.today()
    monday = today - datetime.timedelta(days=today.weekday())
    sunday = monday + datetime.timedelta(days=6)

    habits = get_habits(user_id)
    active_habits = [h for h in habits if h["active"]]
    if not active_habits:
        return 0

    from db.habits import get_all_checkins_in_range
    checkins = get_all_checkins_in_range(user_id, monday.isoformat(), sunday.isoformat())
    checkin_map = {}
    for c in checkins:
        cid = c["habit_id"]
        if cid not in checkin_map:
            checkin_map[cid] = {}
        checkin_map[cid][c["date"]] = c["status"]

    done_total = 0
    total = 0
    for h in active_habits:
        h_checkins = checkin_map.get(h["id"], {})
        for i in range(7):
            d = (monday + datetime.timedelta(days=i))
            if d <= today:
                total += 1
                if h_checkins.get(d.isoformat()) == "done":
                    done_total += 1

    return round(done_total / total * 100) if total > 0 else 0


def evaluate_condition(user_id: int, condition: dict, reward: dict = None) -> bool:
    """评估单个结构化条件是否满足"""
    ctype = condition.get("type")
    threshold = condition.get("threshold", 0)
    target_id = condition.get("targetId")

    if ctype == "level":
        conn = get_conn()
        row = conn.execute("SELECT level FROM users WHERE id = ?", (user_id,)).fetchone()
        conn.close()
        return row and row["level"] >= threshold

    elif ctype == "dim_level":
        conn = get_conn()
        row = conn.execute(
            "SELECT level FROM user_dimensions WHERE user_id = ? AND dimension_key = ?",
            (user_id, target_id),
        ).fetchone()
        conn.close()
        return row and row["level"] >= threshold

    elif ctype == "exp_since_create":
        total = get_total_exp_from_dimensions(user_id)
        if not reward:
            return False
        base_exp = reward.get("created_at_exp", 0)
        return (total - base_exp) >= threshold

    elif ctype == "habit_streak":
        if not target_id:
            return False
        streak = calculate_streak(int(target_id))
        return streak >= threshold

    elif ctype == "habit_streak_any":
        habits = get_habits(user_id)
        max_streak = 0
        for h in habits:
            if h["active"]:
                s = calculate_streak(h["id"])
                if s > max_streak:
                    max_streak = s
        return max_streak >= threshold

    elif ctype == "milestone":
        if not target_id:
            return False
        goal = get_goal(int(target_id))
        if not goal:
            return False
        done = sum(1 for m in goal.get("milestones", []) if m.get("done"))
        return done >= threshold

    elif ctype == "tasks_done":
        conn = get_conn()
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM tasks WHERE user_id = ? AND claimed = 1",
            (user_id,),
        ).fetchone()
        conn.close()
        return row["cnt"] >= threshold

    elif ctype == "goals_done":
        conn = get_conn()
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM goals WHERE user_id = ? AND progress = 100 AND claimed = 1",
            (user_id,),
        ).fetchone()
        conn.close()
        return row["cnt"] >= threshold

    elif ctype == "week_rate":
        rate = calculate_week_completion_rate(user_id)
        return rate >= threshold

    elif ctype == "manual":
        if not reward:
            return False
        manual_list = reward.get("manual_confirmed", [])
        cond_label = condition.get("_label", "")
        return cond_label in manual_list

    return False


def evaluate_reward(user_id: int, reward: dict) -> dict:
    """评估单个奖励的解锁状态，返回更新后的 reward dict"""
    if reward.get("claimed"):
        return reward

    if not reward.get("unlocked"):
        all_unlock_met = all(
            evaluate_condition(user_id, c, reward)
            for c in reward.get("unlock_conditions", [])
        )
        if all_unlock_met and reward.get("unlock_conditions"):
            reward["unlocked"] = True
            update_reward(reward["id"], unlocked=1)

    return reward


def evaluate_all_rewards(user_id: int) -> list:
    """评估所有奖励的解锁状态，返回更新后的列表"""
    rewards = get_rewards(user_id)
    evaluated = []
    for r in rewards:
        evaluated.append(evaluate_reward(user_id, r))
    return evaluated