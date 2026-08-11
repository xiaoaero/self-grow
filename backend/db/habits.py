"""
Self Grow — 习惯 CRUD + 打卡记录
"""

import re
from xml.etree import ElementTree

from db.connection import get_conn
import datetime


def sanitize_icon(icon):
    """icon 写入前的合法性兜底。

    - 空 / emoji / 普通文本：原样放行
    - 以 <svg 开头：必须是白名单内的合法 SVG，否则置空
    （AI 图标走 /api/habits/ai-icon 时已在服务层校验，这里防御直接调 API 的写入）
    """
    if not icon:
        return ''
    if str(icon).strip().lower().startswith('<svg'):
        return icon if validate_svg(icon) else ''
    return icon


def validate_svg(svg: str) -> bool:
    """SVG 白名单校验（独立实现，避免与 services 层循环依赖）。

    与 services/ai_habit_service.py 中的校验规则保持一致。
    """
    if not svg or not str(svg).strip():
        return False
    try:
        root = ElementTree.fromstring(svg)
    except ElementTree.ParseError:
        return False
    local = root.tag.split("}", 1)[1] if "}" in root.tag else root.tag
    if local.lower() != "svg":
        return False
    allowed = {"svg", "g", "path", "rect", "circle", "ellipse", "line",
               "polyline", "polygon"}
    for el in root.iter():
        tag = el.tag.lower()
        if "}" in tag:
            tag = tag.split("}", 1)[1]
        if tag not in allowed:
            return False
        for attr in el.attrib:
            al = attr.lower()
            if al.startswith("on") or al in ("href", "xlink:href"):
                return False
    return True


# ================================================================
# 习惯 CRUD
# ================================================================

def get_habits(user_id: int) -> list:
    """获取用户的所有习惯"""
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM habits WHERE user_id = ? ORDER BY sort_order ASC, id ASC",
        (user_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_habit(habit_id: int):
    """获取单个习惯"""
    conn = get_conn()
    row = conn.execute("SELECT * FROM habits WHERE id = ?", (habit_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def create_habit(user_id: int, name: str, icon: str, intro: str, category: str,
                 weekly_target: int = 7, xp_reward: int = 15) -> int:
    """创建习惯，返回新习惯的 id"""
    conn = get_conn()
    cursor = conn.execute(
        """INSERT INTO habits (user_id, name, icon, intro, category, weekly_target, xp_reward)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (user_id, name, sanitize_icon(icon), intro, category, weekly_target, xp_reward),
    )
    new_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return new_id


def update_habit(habit_id: int, name: str = None, icon: str = None, intro: str = None,
                 category: str = None, weekly_target: int = None, xp_reward: int = None,
                 active: int = None):
    """更新习惯，只传需要改的字段"""
    fields = []
    values = []
    for k, v in [('name', name), ('icon', icon), ('intro', intro),
                 ('category', category), ('weekly_target', weekly_target),
                 ('xp_reward', xp_reward), ('active', active)]:
        if v is not None:
            if k == 'icon':
                v = sanitize_icon(v)
            fields.append(f"{k} = ?")
            values.append(v)
    if not fields:
        return
    values.append(habit_id)
    conn = get_conn()
    conn.execute(f"UPDATE habits SET {', '.join(fields)} WHERE id = ?", values)
    conn.commit()
    conn.close()


def delete_habits(ids: list):
    """批量删除习惯及其打卡记录"""
    if not ids:
        return
    placeholders = ",".join("?" for _ in ids)
    conn = get_conn()
    conn.execute(f"DELETE FROM habit_checkins WHERE habit_id IN ({placeholders})", ids)
    conn.execute(f"DELETE FROM habits WHERE id IN ({placeholders})", ids)
    conn.commit()
    conn.close()


# ================================================================
# 打卡记录
# ================================================================

def get_checkins_in_range(habit_id: int, start_date: str, end_date: str) -> list:
    """获取某个习惯在日期范围内的打卡记录"""
    conn = get_conn()
    rows = conn.execute(
        "SELECT date, status FROM habit_checkins WHERE habit_id = ? AND date >= ? AND date <= ? ORDER BY date",
        (habit_id, start_date, end_date),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_checkins_in_range(user_id: int, start_date: str, end_date: str) -> list:
    """获取用户所有习惯在日期范围内的打卡记录"""
    conn = get_conn()
    rows = conn.execute(
        """SELECT hc.habit_id, hc.date, hc.status
           FROM habit_checkins hc
           JOIN habits h ON hc.habit_id = h.id
           WHERE h.user_id = ? AND hc.date >= ? AND hc.date <= ?
           ORDER BY hc.habit_id, hc.date""",
        (user_id, start_date, end_date),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def upsert_checkin(habit_id: int, date: str, status: str):
    """插入或更新一条打卡记录"""
    conn = get_conn()
    conn.execute(
        """INSERT INTO habit_checkins (habit_id, date, status)
           VALUES (?, ?, ?)
           ON CONFLICT(habit_id, date) DO UPDATE SET status = excluded.status""",
        (habit_id, date, status),
    )
    conn.commit()
    conn.close()


def delete_checkin(habit_id: int, date: str):
    """删除某天的打卡记录"""
    conn = get_conn()
    conn.execute(
        "DELETE FROM habit_checkins WHERE habit_id = ? AND date = ?",
        (habit_id, date),
    )
    conn.commit()
    conn.close()


def calculate_streak(habit_id: int, until_date: str = None) -> int:
    """计算某个习惯的连续打卡天数（从 until_date 往前数）"""
    if until_date is None:
        until_date = datetime.date.today().isoformat()

    conn = get_conn()
    rows = conn.execute(
        "SELECT date, status FROM habit_checkins WHERE habit_id = ? AND date <= ? ORDER BY date DESC",
        (habit_id, until_date),
    ).fetchall()
    conn.close()

    streak = 0
    current = datetime.date.fromisoformat(until_date)
    for row in rows:
        row_date = datetime.date.fromisoformat(row["date"])
        if row_date > current:
            continue
        if streak > 0 and (current - row_date).days > 1:
            break
        if row["status"] == "done":
            streak += 1
            current = row_date
        elif row["status"] == "skipped":
            current = row_date
        else:
            break
    return streak