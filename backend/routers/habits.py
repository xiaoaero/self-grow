"""
Self Grow — 习惯 API 路由

包含习惯 CRUD、打卡切换、统计卡片、AI 智能洞察、上周数据。
"""

from fastapi import APIRouter, HTTPException, Depends
from datetime import date as date_func, timedelta

from db.connection import get_conn
from db.habits import get_habits, get_habit, create_habit, update_habit, delete_habits
from db.habits import get_checkins_in_range, get_all_checkins_in_range, upsert_checkin, delete_checkin, calculate_streak
from db.users import get_user
from schemas.api import CreateHabitRequest, UpdateHabitRequest, DeleteHabitsRequest, HabitAIInsightRequest, HabitAIIconRequest
from routers.deps import get_current_user
from services.ai_habit_service import call_ai_for_habits, call_ai_for_icon

router = APIRouter()


@router.get("/api/habits")
async def list_habits(user=Depends(get_current_user)):
    """获取用户所有习惯 + 本周打卡数据"""
    user_id = user["id"]
    habits = get_habits(user_id)

    today = date_func.today()
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)
    start_str = monday.isoformat()
    end_str = sunday.isoformat()

    checkins = get_all_checkins_in_range(user_id, start_str, end_str)
    checkin_map = {}
    for c in checkins:
        cid = c["habit_id"]
        if cid not in checkin_map:
            checkin_map[cid] = {}
        checkin_map[cid][c["date"]] = c["status"]

    weekday = today.weekday()
    today_idx = (weekday + 1) % 7
    today_str = today.isoformat()

    result = []
    for h in habits:
        week_done = [0] * 7
        week_skipped = [0] * 7
        h_checkins = checkin_map.get(h["id"], {})

        for i in range(7):
            d = (monday + timedelta(days=i)).isoformat()
            status = h_checkins.get(d)
            if status == "done":
                idx = (i + 1) % 7
                week_done[idx] = 1
            elif status == "skipped":
                idx = (i + 1) % 7
                week_skipped[idx] = 1

        today_checkin = h_checkins.get(today_str)
        today_done = today_checkin == "done"
        today_skipped = today_checkin == "skipped"
        streak = calculate_streak(h["id"])

        result.append({
            "id": h["id"],
            "name": h["name"],
            "icon": h["icon"],
            "intro": h["intro"],
            "category": h["category"],
            "streak": streak,
            "weekDone": week_done,
            "weekSkipped": week_skipped,
            "todayDone": today_done,
            "todaySkipped": today_skipped,
            "weeklyTarget": h["weekly_target"],
            "xpReward": h["xp_reward"],
            "active": bool(h["active"]),
        })

    return result


@router.post("/api/habits")
async def create_new_habit(req: CreateHabitRequest, user=Depends(get_current_user)):
    """创建新习惯"""
    user_id = user["id"]
    new_id = create_habit(
        user_id, req.name, req.icon, req.intro, req.category,
        req.weekly_target, req.xp_reward,
    )

    habit = get_habit(new_id)
    if not habit:
        raise HTTPException(status_code=500, detail="创建失败")

    today = date_func.today()
    today_str = today.isoformat()

    return {
        "id": habit["id"],
        "name": habit["name"],
        "icon": habit["icon"],
        "intro": habit["intro"],
        "category": habit["category"],
        "streak": 0,
        "weekDone": [0, 0, 0, 0, 0, 0, 0],
        "weekSkipped": [0, 0, 0, 0, 0, 0, 0],
        "todayDone": False,
        "todaySkipped": False,
        "weeklyTarget": habit["weekly_target"],
        "xpReward": habit["xp_reward"],
        "active": True,
    }


@router.put("/api/habits/{habit_id}")
async def update_existing_habit(habit_id: int, req: UpdateHabitRequest):
    """更新习惯"""
    habit = get_habit(habit_id)
    if not habit:
        raise HTTPException(status_code=404, detail="习惯不存在")

    update_habit(
        habit_id,
        name=req.name,
        icon=req.icon,
        intro=req.intro,
        category=req.category,
        weekly_target=req.weekly_target,
        xp_reward=req.xp_reward,
        active=req.active,
    )

    updated = get_habit(habit_id)
    return updated


@router.delete("/api/habits")
async def delete_habits_batch(req: DeleteHabitsRequest, user=Depends(get_current_user)):
    """批量删除习惯"""
    delete_habits(req.ids)
    return {"deleted": len(req.ids)}


@router.post("/api/habits/{habit_id}/toggle")
async def toggle_habit_checkin(habit_id: int):
    """打卡三态切换：done → skipped → pending → done"""
    habit = get_habit(habit_id)
    if not habit:
        raise HTTPException(status_code=404, detail="习惯不存在")

    today = date_func.today()
    today_str = today.isoformat()

    checkins = get_checkins_in_range(habit_id, today_str, today_str)
    current_status = checkins[0]["status"] if checkins else None

    if current_status == "done":
        upsert_checkin(habit_id, today_str, "skipped")
        new_status = "skipped"
    elif current_status == "skipped":
        delete_checkin(habit_id, today_str)
        new_status = "pending"
    else:
        upsert_checkin(habit_id, today_str, "done")
        new_status = "done"

    streak = calculate_streak(habit_id)
    return {"status": new_status, "streak": streak}


@router.get("/api/habits/stats")
async def habit_stats(user=Depends(get_current_user)):
    """统计卡片数据：今日完成/最长连续/本周完成率/本月估算/活跃数 + 上周对比"""
    user_id = user["id"]
    habits = get_habits(user_id)
    active_habits = [h for h in habits if h["active"]]
    total_active = len(active_habits)

    today = date_func.today()
    today_str = today.isoformat()
    weekday = today.weekday()
    monday = today - timedelta(days=weekday)
    sunday = monday + timedelta(days=6)
    last_monday = monday - timedelta(days=7)
    last_sunday = monday - timedelta(days=1)

    this_week_checkins = get_all_checkins_in_range(user_id, monday.isoformat(), sunday.isoformat())
    last_week_checkins = get_all_checkins_in_range(user_id, last_monday.isoformat(), last_sunday.isoformat())

    def aggregate_week(checkins_list, start, end):
        result = {}
        for c in checkins_list:
            cid = c["habit_id"]
            if cid not in result:
                result[cid] = {}
            result[cid][c["date"]] = c["status"]
        return result

    this_map = aggregate_week(this_week_checkins, monday, sunday)
    last_map = aggregate_week(last_week_checkins, last_monday, last_sunday)

    # 今日完成
    done_today = 0
    for h in active_habits:
        c = this_map.get(h["id"], {}).get(today_str)
        if c == "done":
            done_today += 1

    # 最长连续
    best_streak = 0
    best_name = ""
    for h in active_habits:
        s = calculate_streak(h["id"])
        if s > best_streak:
            best_streak = s
            best_name = h["name"]

    # 本周完成率（按 weekly_target 加权）
    this_week_done = 0
    this_week_total = 0
    days_passed = min(7, (today - monday).days + 1)
    for h in active_habits:
        target = h["weekly_target"] or 7
        h_checkins = this_map.get(h["id"], {})
        # 分母：过去天数中最多不超过 weekly_target 次机会
        contrib = min(target, days_passed)
        this_week_total += contrib
        # 分子：截止到今天的实际完成次数
        for i in range(7):
            d = (monday + timedelta(days=i))
            if d <= today and h_checkins.get(d.isoformat()) == "done":
                this_week_done += 1
            if this_week_done > this_week_total:
                break

    week_rate = round(this_week_done / this_week_total * 100) if this_week_total > 0 else 0

    # 上周完成率
    last_week_done = 0
    last_week_total = len(active_habits) * 7
    for h in active_habits:
        h_checkins = last_map.get(h["id"], {})
        for i in range(7):
            d = (last_monday + timedelta(days=i))
            if h_checkins.get(d.isoformat()) == "done":
                last_week_done += 1

    last_week_rate = round(last_week_done / last_week_total * 100) if last_week_total > 0 else 0
    rate_diff = week_rate - last_week_rate

    # 昨日对比
    yesterday = today - timedelta(days=1)
    yesterday_str = yesterday.isoformat()
    yesterday_done = 0
    for h in active_habits:
        c = this_map.get(h["id"], {}).get(yesterday_str)
        if c == "done":
            yesterday_done += 1
    diff_today = done_today - yesterday_done

    # 本月实际打卡统计（从 user_monthly_stats 读取）
    year_month = today.strftime("%Y-%m")
    conn = get_conn()
    row = conn.execute(
        "SELECT habit_count, habit_xp FROM user_monthly_stats WHERE user_id = ? AND year_month = ?",
        (user_id, year_month),
    ).fetchone()
    conn.close()
    monthly_total = row["habit_count"] if row else 0
    monthly_xp = row["habit_xp"] if row else 0

    inactive_count = len(habits) - total_active

    return {
        "doneToday": done_today,
        "totalActive": total_active,
        "diffToday": diff_today,
        "bestStreak": best_streak,
        "bestStreakName": best_name,
        "weekRate": week_rate,
        "rateDiff": rate_diff,
        "monthlyTotal": monthly_total,
        "monthlyXP": monthly_xp,
        "inactiveCount": inactive_count,
    }


@router.get("/api/habits/insights")
async def habit_insights(user=Depends(get_current_user)):
    """简单版习惯洞察（降级方案），AI 洞察请使用 POST /api/habits/ai-insights"""
    user_id = user["id"]
    habits = get_habits(user_id)
    active_habits = [h for h in habits if h["active"]]

    today = date_func.today()
    today_str = today.isoformat()
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)
    checkins = get_all_checkins_in_range(user_id, monday.isoformat(), sunday.isoformat())
    checkin_map = {}
    for c in checkins:
        cid = c["habit_id"]
        if cid not in checkin_map:
            checkin_map[cid] = {}
        if c["status"] == "done":
            checkin_map[cid][c["date"]] = 1

    insights = []

    # 今日剩余
    pending = 0
    first_pending = None
    for h in active_habits:
        if today_str not in checkin_map.get(h["id"], {}):
            pending += 1
            if first_pending is None:
                first_pending = h["name"]
    if pending > 0:
        insights.append({
            "text": f"⏳ 今日还有 {pending} 个习惯待完成，先开始 {first_pending or ''} 吧"
        })

    # 最长连续
    best_streak = 0
    best_habit = None
    for h in active_habits:
        s = calculate_streak(h["id"])
        if s > best_streak:
            best_streak = s
            best_habit = h
    if best_habit and best_streak >= 7:
        insights.append({
            "text": f"🔥 {best_habit['name']} 已连续打卡 {best_streak} 天，继续保持！"
        })

    return {"insights": insights}


@router.post("/api/habits/ai-insights")
async def habit_ai_insights(req: HabitAIInsightRequest, user=Depends(get_current_user)):
    """AI 分析习惯数据，返回个性化分析报告"""
    user_id = user["id"]

    # 验证日期范围
    try:
        d_from = date_func.fromisoformat(req.date_from)
        d_to = date_func.fromisoformat(req.date_to)
    except ValueError:
        raise HTTPException(status_code=400, detail="日期格式无效，请使用 YYYY-MM-DD")

    days = (d_to - d_from).days
    if days < 2:
        raise HTTPException(status_code=400, detail="时间范围至少需要3天")
    if days > 30:
        raise HTTPException(status_code=400, detail="时间范围最多30天")
    if d_to > date_func.today():
        raise HTTPException(status_code=400, detail="结束日期不能超过今天")

    report = await call_ai_for_habits(user_id, req.date_from, req.date_to)
    return {"report": report}


@router.post("/api/habits/ai-icon")
async def habit_ai_icon(req: HabitAIIconRequest, user=Depends(get_current_user)):
    """AI 根据习惯信息生成 SVG 图标"""
    if not req.name.strip():
        raise HTTPException(status_code=400, detail="习惯名称不能为空")
    svg = await call_ai_for_icon(req.name, req.intro, req.category)
    return {"svg": svg}


@router.get("/api/habits/last-week")
async def last_week_habits(user=Depends(get_current_user)):
    """上周打卡数据"""
    user_id = user["id"]
    habits = get_habits(user_id)
    today = date_func.today()
    monday = today - timedelta(days=today.weekday())
    last_monday = monday - timedelta(days=7)
    last_sunday = monday - timedelta(days=1)

    checkins = get_all_checkins_in_range(user_id, last_monday.isoformat(), last_sunday.isoformat())
    checkin_map = {}
    for c in checkins:
        cid = c["habit_id"]
        if cid not in checkin_map:
            checkin_map[cid] = {}
        checkin_map[cid][c["date"]] = c["status"]

    result = []
    for h in habits:
        week_done = [0] * 7
        week_skipped = [0] * 7
        h_checkins = checkin_map.get(h["id"], {})
        for i in range(7):
            d = (last_monday + timedelta(days=i)).isoformat()
            status = h_checkins.get(d)
            idx = (i + 1) % 7
            if status == "done":
                week_done[idx] = 1
            elif status == "skipped":
                week_skipped[idx] = 1

        result.append({
            "id": h["id"],
            "weekDone": week_done,
            "weekSkipped": week_skipped,
        })

    return result