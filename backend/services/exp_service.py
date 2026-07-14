"""
Self Grow — 经验值服务

封装"加经验→更新维度→重算等级→更新今日统计"的完整流程。
消除 server.py 中该模式重复5次的问题。
"""

from db.dimensions import upsert_dimension, get_total_exp_from_dimensions
from db.users import get_user, get_user_stats, upsert_user_stats, update_user_exp
from models.level import exp_for_level, total_exp_for_level, level_from_total_exp
from models.constants import get_rank_info, get_category
from datetime import datetime


def award_exp_and_recalc(user_id: int, category: str, exp_amount: float,
                         extra_focus_minutes: int = 0, extra_tasks_done: int = 0,
                         extra_habits_checked: int = 0, is_global_exp: bool = False) -> dict:
    """
    核心 EXP 奖励函数：
    1. 更新对应维度经验（维度经验原始值）
    2. 从 8 维 SUM 总经验，重算等级
    3. 更新用户表
    4. 更新今日统计
    5. 返回 exp_result + today_stats

    参数:
        category: 维度ID
        exp_amount: 经验值（维度经验值）
        is_global_exp: True 表示 exp_amount 已是全局经验值（tasks/habits等用），False 表示维度经验值需要折算

    返回:
        {
            "exp_earned": float,
            "exp_result": { level, exp, expToNext, totalExp, isMaxLevel, rank, rankTier, leveledUp, oldLevel, global_exp_earned },
            "today_stats": { focusMinutes, tasksDone, habitsChecked, expEarned }
        }
    """
    user = get_user(user_id)
    old_level = user["level"] if user else 1

    # 计算全局经验值
    if is_global_exp:
        global_exp = exp_amount
        dimension_exp = exp_amount
    else:
        cat = get_category(category)
        global_rate = cat["global_rate"] if cat else 1.0
        global_exp = round(exp_amount * global_rate)
        dimension_exp = exp_amount

    # 1. 更新维度经验（始终使用维度经验原始值）
    if category and dimension_exp > 0:
        # 维度经验可能为小数，但 upsert_dimension 用整数
        upsert_dimension(user_id, category, round(dimension_exp))

    # 2. 从维度表实时 SUM 总经验，重算等级
    new_total = get_total_exp_from_dimensions(user_id)
    new_level = level_from_total_exp(new_total)
    new_current = max(0, new_total - total_exp_for_level(new_level))

    # 3. 更新用户表
    update_user_exp(user_id, new_level, new_current)

    # 4. 更新今日统计（使用全局经验值）
    today = datetime.now().strftime('%Y-%m-%d')
    today_row = get_user_stats(user_id, today)
    upsert_user_stats(
        user_id, today,
        focus_minutes=today_row["focus_minutes"] + extra_focus_minutes,
        tasks_done=today_row["tasks_done"] + extra_tasks_done,
        habits_checked=today_row["habits_checked"] + extra_habits_checked,
        exp_earned=today_row["exp_earned"] + int(global_exp),
    )

    # 5. 获取更新后的统计
    updated_today = get_user_stats(user_id, today)
    rank_info = get_rank_info(new_level)

    exp_result = {
        "level": new_level,
        "exp": new_current,
        "expToNext": exp_for_level(new_level),
        "totalExp": new_total,
        "isMaxLevel": new_level >= 200,
        "rank": rank_info["name"],
        "rankTier": rank_info["tier"],
        "leveledUp": new_level > old_level,
        "oldLevel": old_level,
        "global_exp_earned": int(global_exp),
    }

    today_stats = {
        "focusMinutes": updated_today["focus_minutes"],
        "tasksDone": updated_today["tasks_done"],
        "habitsChecked": updated_today["habits_checked"],
        "expEarned": updated_today["exp_earned"],
    }

    return {
        "exp_earned": int(global_exp),
        "exp_result": exp_result,
        "today_stats": today_stats,
    }