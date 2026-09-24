"""
Self Grow — 经验值服务

封装"加经验→更新维度→重算等级→更新今日统计"的完整流程。
消除 server.py 中该模式重复5次的问题。
"""

from db.dimensions import upsert_dimension, get_total_exp_from_dimensions
from db.users import get_user_stats, upsert_user_stats, update_user_exp
from db.connection import get_conn
from db.actions import create_action_log
from models.level import exp_for_level, total_exp_for_level, level_from_total_exp
from models.constants import get_rank_info, get_category, calculate_exp
from datetime import datetime, timedelta


def award_exp_and_recalc(user_id: int, category: str, exp_amount: float,
                         extra_focus_minutes: int = 0, extra_tasks_done: int = 0,
                         extra_habits_checked: int = 0, is_global_exp: bool = False,
                         conn=None) -> dict:
    """
    核心 EXP 奖励函数：
    1. 更新对应维度经验（维度经验原始值）
    2. 从 8 维 SUM 总经验，重算等级
    3. 更新用户表
    4. 更新今日统计
    5. 返回 exp_result + today_stats

    参数:
        category: 维度ID
        exp_amount: 经验值
        is_global_exp: True 表示 exp_amount 已是全局经验值，False 表示维度经验值需要折算
        conn: 可选外部数据库连接。传入时本函数不 commit/close，由调用方控制事务。

    返回:
        {
            "exp_earned": int,
            "exp_result": { level, exp, expToNext, totalExp, isMaxLevel, rank, rankTier, leveledUp, oldLevel, global_exp_earned },
            "today_stats": { focusMinutes, tasksDone, habitsChecked, expEarned }
        }
    """
    own_conn = conn is None
    if own_conn:
        conn = get_conn()

    try:
        user = conn.execute("""SELECT level FROM users WHERE id = %s""", (user_id,)).fetchone()
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

        # 1. 更新维度经验（保留小数精度）
        if category and dimension_exp > 0:
            upsert_dimension(user_id, category, dimension_exp, conn=conn)

        # 2. 从维度表实时 SUM 总经验，重算等级
        # ⚠️ 必须带 conn：上一句刚在这个事务里 upsert 了维度经验，
        #    另开连接读不到未提交的数据 → 算出来的总经验永远滞后一条记录
        new_total = get_total_exp_from_dimensions(user_id, conn=conn)
        new_level = level_from_total_exp(new_total)
        new_current = max(0, new_total - total_exp_for_level(new_level))

        # 3. 更新用户表
        update_user_exp(user_id, new_level, new_current, total_exp=new_total, conn=conn)

        # 4. 更新今日统计
        today = datetime.now().strftime('%Y-%m-%d')
        # 同样必须带 conn：下面 upsert_user_stats 要基于这一份读数做累加，
        # 读到旧值的话会把本次增量覆盖掉（今日统计少算）
        today_row = get_user_stats(user_id, today, conn=conn)
        upsert_user_stats(
            user_id, today,
            focus_minutes=today_row["focus_minutes"] + extra_focus_minutes,
            tasks_done=today_row["tasks_done"] + extra_tasks_done,
            habits_checked=today_row["habits_checked"] + extra_habits_checked,
            exp_earned=today_row["exp_earned"] + int(global_exp),
            conn=conn,
        )

        if own_conn:
            conn.commit()
    except Exception:
        if own_conn:
            conn.rollback()
        raise
    finally:
        if own_conn:
            conn.close()

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


def create_action_and_award_exp(
    user_id: int,
    category: str,
    duration: int,
    start_time: str,
    detail: str = "",
    end_time: str = None,
    exp: float = None,
    sub_type: str = None,
    sleep_start: str = None,
    sleep_end: str = None,
    request_id: str = "",
    extra_focus_minutes: int = None,
    extra_tasks_done: int = 0,
    extra_habits_checked: int = 0,
    is_global_exp: bool = False,
) -> dict:
    """
    原子事务：创建行动记录 + 计算并奖励经验值。

    保留原路由层 "create_action_log + award_exp_and_recalc" 的全部参数能力，
    所有 DB 操作使用单一连接，原子提交。

    参数:
        user_id: 用户ID
        category: 维度ID
        duration: 时长（分钟）
        start_time: 开始时间 ISO 字符串（duration > 0 时必须提供）
        detail: 行动内容描述（对应 action_logs.note）
        end_time: 结束时间 ISO 字符串，为空则根据 start_time + duration 计算
        exp: 经验值（维度经验），为空则根据 category/duration/sub_type 自动计算
        sub_type: 子类型（如 health-sport, health-sleep 等）
        sleep_start/sleep_end: 睡眠开始/结束时间（HH:MM）
        request_id: 幂等请求ID
        extra_focus_minutes: 额外专注分钟数，为空则默认使用 duration（睡眠除外）
        extra_tasks_done: 额外完成任务数
        extra_habits_checked: 额外打卡习惯数
        is_global_exp: True 表示 exp 已是全局经验

    幂等:
        相同 request_id + user_id + start_time 会返回已有记录，不重复奖励。

    返回:
        {
            "success": True,
            "action_id": int,
            "exp_earned": int,
            "exp_result": { ... },
            "today_stats": { ... },
            "message": str,
        }
    """
    if duration > 0 and not start_time:
        raise ValueError("duration > 0 时必须提供 start_time")

    # 计算结束时间
    if end_time is None:
        if duration > 0:
            end_dt = datetime.fromisoformat(start_time) + timedelta(minutes=duration)
            end_time = end_dt.isoformat()
        else:
            end_time = start_time

    # 计算经验
    if exp is None:
        exp_result = calculate_exp(
            category_id=category,
            duration=duration,
            sub_type=sub_type,
            sleep_start=sleep_start,
            sleep_end=sleep_end,
        )
        dimension_exp = exp_result.get("dimension_exp", 0)
        sub_type = exp_result.get("sub_type", sub_type)
    else:
        dimension_exp = exp

    # 默认专注时长 = duration（睡眠除外）
    if extra_focus_minutes is None:
        extra_focus_minutes = duration if sub_type != "health-sleep" else 0

    conn = get_conn()
    try:
        # 1. 创建行动记录（幂等检查在 create_action_log 内部）
        action_id = create_action_log(
            user_id=user_id,
            category_id=category,
            start_time=start_time,
            end_time=end_time,
            duration=duration,
            note=detail,
            exp_earned=0,  # 先占位 0，奖励后回写，避免幂等检查把新记录误判为"已奖励"
            sub_type=sub_type or "",
            sleep_start=sleep_start or "",
            sleep_end=sleep_end or "",
            request_id=request_id,
            conn=conn,
        )

        # 2. 幂等检查：该记录是否已经奖励过经验
        existing = conn.execute(
            """SELECT exp_earned FROM action_logs WHERE id = %s""",
            (action_id,),
        ).fetchone()
        if existing and existing["exp_earned"] and existing["exp_earned"] > 0:
            conn.commit()
            return {
                "success": True,
                "action_id": action_id,
                "exp_earned": 0,
                "exp_result": None,
                "today_stats": None,
                "message": "该行动已记录过，不重复奖励经验值",
            }

        # 3. 奖励经验（复用 award_exp_and_recalc，使用同一连接，不单独提交）
        service_result = award_exp_and_recalc(
            user_id=user_id,
            category=category,
            exp_amount=dimension_exp,
            extra_focus_minutes=extra_focus_minutes,
            extra_tasks_done=extra_tasks_done,
            extra_habits_checked=extra_habits_checked,
            is_global_exp=is_global_exp,
            conn=conn,
        )

        # 4. 回写行动记录的最终经验值（第 1 步先占位 0，这里再更新为真实值）
        conn.execute(
            """UPDATE action_logs SET exp_earned = %s WHERE id = %s""",
            (dimension_exp, action_id),
        )

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return {
        "success": True,
        "action_id": action_id,
        "exp_earned": service_result["exp_earned"],
        "exp_result": service_result["exp_result"],
        "today_stats": service_result["today_stats"],
        "message": f"已记录{detail}（{duration}分钟），{category}维度 +{dimension_exp} EXP",
    }