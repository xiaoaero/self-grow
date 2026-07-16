"""
Self Grow — 行动记录 API 路由
"""

from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime, timedelta

from db.actions import create_action_log, get_action_logs, get_today_action_stats, get_activity_feed, has_sleep_record_today, has_finance_review_this_half
from db.routines import get_routine_streak, upsert_routine_streak
from db.users import get_user_stats
from models.constants import get_category, calculate_exp, _calc_routine_bonus
from schemas.api import CreateActionRequest, AIChatActionRequest, AISubmitActionsRequest
from routers.deps import get_current_user
from services.ai_action_service import call_action_ai

router = APIRouter()


# ================================================================
# 连续天数管理辅助函数
# ================================================================

def _update_streak_logic(current_streak: int, has_protection: bool,
                         last_date: str, is_routine: bool,
                         today_str: str) -> tuple:
    """
    根据今天是否规律，计算新的连续天数和保护状态。
    返回 (new_streak, new_has_protection)
    """
    if not is_routine:
        if has_protection:
            # 消耗保护：不加经验但保留连续天数
            return current_streak, False
        else:
            # 无保护：重置连续天数
            return 0, False

    # 今天符合规律，计算连续性
    if last_date:
        try:
            last = datetime.strptime(last_date, "%Y-%m-%d").date()
            today = datetime.strptime(today_str, "%Y-%m-%d").date()
            days_diff = (today - last).days
        except ValueError:
            days_diff = 999

        if days_diff == 1:
            new_streak = current_streak + 1
        elif days_diff > 1:
            new_streak = 1  # 不连续，重新计数
        else:
            new_streak = current_streak  # 同一天，不重复计数
    else:
        new_streak = 1

    # 连续>=10天且没有保护机会时，获得保护
    new_protection = has_protection
    if new_streak >= 10 and not new_protection:
        new_protection = True

    return new_streak, new_protection


@router.post("/api/actions")
async def create_action(req: CreateActionRequest, user=Depends(get_current_user)):
    """提交行动记录 — 按新规则计算 EXP、更新等级和今日统计"""
    user_id = user["id"]

    # 校验分类
    cat = get_category(req.category_id)
    if not cat:
        raise HTTPException(status_code=400, detail=f"无效分类: {req.category_id}")

    # 计算 end_time
    try:
        start_dt = datetime.fromisoformat(req.start_time)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="无效的 start_time 格式，需要 ISO 8601")

    # 读取规律作息连续天数（仅健康-睡眠需要）
    routine_info = get_routine_streak(user_id)
    current_streak = routine_info["streak"]

    # 使用新规则计算经验
    from models.constants import calculate_exp as calc_exp_new
    today_str = datetime.now().strftime('%Y-%m-%d')
    exp_result = calc_exp_new(
        req.category_id, req.duration,
        sub_type=req.sub_type or None,
        sleep_start=req.sleep_start or None,
        sleep_end=req.sleep_end or None,
        today=today_str,
        streak=current_streak,
    )

    dimension_exp = exp_result["dimension_exp"]
    global_exp = exp_result["global_exp"]
    sub_type = exp_result["sub_type"]

    # 睡眠每日限制：一天只允许记录一次睡眠
    if sub_type == "health-sleep" and has_sleep_record_today(user_id):
        raise HTTPException(status_code=400, detail="今日已记录睡眠，每天只能记录一次")

    # 财务复盘半月限制：每个半月只允许记录一次
    if sub_type == "finance-review" and has_finance_review_this_half(user_id):
        raise HTTPException(status_code=400, detail="当前半月已记录复盘，每个半月只能记录一次")

    # 计算 end_time
    if req.duration > 0:
        end_dt = start_dt + timedelta(minutes=req.duration)
    else:
        end_dt = start_dt
    end_time = end_dt.isoformat()

    # 插入行动记录（保存维度经验值 + sub_type/sleep_start/sleep_end）
    new_id = create_action_log(
        user_id, req.category_id, req.start_time, end_time,
        req.duration, req.note or "", round(dimension_exp),
        sub_type=sub_type, sleep_start=req.sleep_start or "",
        sleep_end=req.sleep_end or "",
    )

    # 睡眠记录：更新规律作息连续天数
    if sub_type == "health-sleep":
        is_routine = exp_result.get("is_routine", False)
        new_streak, new_protection = _update_streak_logic(
            current_streak, routine_info["has_protection"],
            routine_info["last_date"], is_routine, today_str,
        )
        upsert_routine_streak(user_id, new_streak, new_protection, today_str)

    # 使用服务层统一处理 EXP 奖励（传入维度经验，由服务层折算全局经验）
    from services.exp_service import award_exp_and_recalc
    # 睡眠时长不计入"今日专注"——睡觉不是专注
    focus_minutes = req.duration if (req.duration > 0 and sub_type != "health-sleep") else 0
    service_result = award_exp_and_recalc(
        user_id, req.category_id, dimension_exp,
        extra_focus_minutes=focus_minutes,
        extra_tasks_done=0,  # 行动记录不算完成任务
        is_global_exp=False,  # 传入的是维度经验，需要内置折算
    )

    return {
        "id": new_id,
        "category_id": req.category_id,
        "category_name": cat["name"],
        "start_time": req.start_time,
        "end_time": end_time,
        "duration": req.duration,
        "note": req.note or "",
        "exp_earned": int(global_exp),
        "dimension_exp": dimension_exp,
        "sub_type": sub_type,
        "sleep_valid": exp_result.get("sleep_valid", False),
        "routine_extra": exp_result.get("routine_extra", 0),
        "is_routine": exp_result.get("is_routine", False),
        "exp_result": service_result["exp_result"],
        "today_stats": service_result["today_stats"],
    }


@router.get("/api/actions")
async def list_actions(
    user=Depends(get_current_user),
    page: int = 1,
    page_size: int = 20,
    category: str = None,
    sort: str = "newest",
    search: str = None,
    date_from: str = None,
    date_to: str = None,
):
    """分页查询行动历史"""
    user_id = user["id"]
    return get_action_logs(
        user_id, page=page, page_size=page_size,
        category=category, sort=sort, search=search,
        date_from=date_from, date_to=date_to,
    )


@router.get("/api/actions/today-stats")
async def today_action_stats(user=Depends(get_current_user)):
    """今日行动统计（分类分布 + 最近行动）"""
    user_id = user["id"]
    today = datetime.now().strftime('%Y-%m-%d')
    today_row = get_user_stats(user_id, today)
    action_stats = get_today_action_stats(user_id)

    return {
        "today_stats": {
            "focusMinutes": today_row["focus_minutes"],
            "tasksDone": today_row["tasks_done"],
            "habitsChecked": today_row["habits_checked"],
            "expEarned": today_row["exp_earned"],
        },
        "category_dist": action_stats["category_dist"],
        "recent_actions": action_stats["recent_actions"],
    }


@router.get("/api/actions/routine-status")
async def routine_status(user=Depends(get_current_user)):
    """获取当前用户的作息规律状态"""
    user_id = user["id"]
    info = get_routine_streak(user_id)
    # 计算如果明天也规律，能获得的额外经验
    next_bonus = _calc_routine_bonus(info["streak"] + 1)
    return {
        "streak": info["streak"],
        "has_protection": info["has_protection"],
        "last_date": info["last_date"] or "",
        "next_bonus": next_bonus,
    }


@router.get("/api/actions/finance-review-status")
async def finance_review_status(user=Depends(get_current_user)):
    """获取当前半月是否已记录财务复盘"""
    user_id = user["id"]
    has_review = has_finance_review_this_half(user_id)
    return {"has_review_this_half": has_review}


@router.get("/api/activities/feed")
async def activity_feed(user=Depends(get_current_user)):
    """动态播报列表"""
    user_id = user["id"]
    activities = get_activity_feed(user_id)
    return {"activities": activities}


# ================================================================
# AI 行动解析对话
# ================================================================


@router.post("/api/actions/ai-chat")
async def ai_chat_action(req: AIChatActionRequest):
    """AI 行动解析对话：支持多轮交互，AI 可反问用户"""
    result = await call_action_ai(req.messages)
    if "tool_calls" in result:
        return {"tool_calls": result["tool_calls"]}
    return {"content": result.get("content", "")}


@router.post("/api/actions/ai-submit")
async def ai_submit_actions(req: AISubmitActionsRequest, user=Depends(get_current_user)):
    """
    批量提交 AI 解析后的行动记录。
    后端用 calculate_exp() 二次校验 EXP，确保与手动记录一致。
    """
    user_id = user["id"]
    from datetime import timedelta
    from services.exp_service import award_exp_and_recalc

    results = []
    total_global_exp = 0
    last_service_result = None

    # 读取规律作息状态
    routine_info = get_routine_streak(user_id)
    current_streak = routine_info["streak"]

    for action in req.actions:
        cat = get_category(action.category_id)
        if not cat:
            continue

        now = datetime.now()
        start_time = now.isoformat()
        today_str = now.strftime('%Y-%m-%d')

        # 后端二次计算经验（确保与手动记录一致）
        exp_result = calculate_exp(
            action.category_id, action.duration,
            sub_type=action.sub_type or None,
            sleep_start=action.sleep_start or None,
            sleep_end=action.sleep_end or None,
            today=today_str,
            streak=current_streak,
        )

        dimension_exp = exp_result["dimension_exp"]
        global_exp = exp_result["global_exp"]
        sub_type = exp_result["sub_type"]
        total_global_exp += global_exp

        # 睡眠每日限制
        if sub_type == "health-sleep" and has_sleep_record_today(user_id):
            continue  # 跳过重复的睡眠记录

        # 财务复盘半月限制
        if sub_type == "finance-review" and has_finance_review_this_half(user_id):
            continue  # 跳过重复的半月复盘

        # 计算 end_time
        end_dt = now
        if action.duration > 0:
            end_dt = now + timedelta(minutes=action.duration)
        end_time = end_dt.isoformat()

        # 插入记录
        new_id = create_action_log(
            user_id, action.category_id, start_time, end_time,
            action.duration, action.note or "", round(dimension_exp),
            sub_type=sub_type, sleep_start=action.sleep_start or "",
            sleep_end=action.sleep_end or "",
        )

        # 睡眠记录：更新规律作息连续天数
        if sub_type == "health-sleep":
            is_routine = exp_result.get("is_routine", False)
            new_streak, new_protection = _update_streak_logic(
                current_streak, routine_info["has_protection"],
                routine_info["last_date"], is_routine, today_str,
            )
            upsert_routine_streak(user_id, new_streak, new_protection, today_str)
            # 更新当前 streak 供后续 action 使用
            current_streak = new_streak
            routine_info = {"streak": new_streak, "has_protection": new_protection, "last_date": today_str}

        # 更新经验
        # 睡眠时长不计入"今日专注"——睡觉不是专注
        ai_focus_min = action.duration if (action.duration > 0 and sub_type != "health-sleep") else 0
        last_service_result = award_exp_and_recalc(
            user_id, action.category_id, dimension_exp,
            extra_focus_minutes=ai_focus_min,
            extra_tasks_done=0,  # 行动记录不算完成任务
            is_global_exp=False,
        )

        results.append({
            "id": new_id,
            "category_id": action.category_id,
            "category_name": cat["name"],
            "note": action.note,
            "duration": action.duration,
            "sub_type": sub_type,
            "exp_earned": int(global_exp),
            "dimension_exp": dimension_exp,
        })

    # 取最后一个的 today_stats 和 exp_result（已累加所有记录）
    merged_stats = last_service_result["today_stats"] if last_service_result else {}
    merged_exp = last_service_result["exp_result"] if last_service_result else {}

    return {
        "records": results,
        "total_global_exp": total_global_exp,
        "today_stats": merged_stats,
        "exp_result": merged_exp,
    }
