"""
Self Grow — 目标 API 路由
"""

from fastapi import APIRouter, HTTPException, Depends

from db.goals import get_goals, get_goal, create_goal, update_goal, delete_goal, claim_goal_reward
from schemas.api import CreateGoalRequest, UpdateGoalRequest
from routers.deps import get_current_user

router = APIRouter()


@router.get("/api/goals")
def list_goals(user=Depends(get_current_user)):
    """获取目标列表"""
    goals = get_goals(user["id"])
    return {"goals": goals}


@router.post("/api/goals")
def create_new_goal(req: CreateGoalRequest, user=Depends(get_current_user)):
    """创建目标"""
    new_id = create_goal(
        user["id"], req.title, req.intro, req.category,
        req.deadline, req.reward_exp, req.category_image,
        [m.dict() for m in req.milestones],
    )
    goal = get_goal(new_id)
    return goal


@router.put("/api/goals/{goal_id}")
def update_existing_goal(goal_id: int, req: UpdateGoalRequest):
    """更新目标"""
    goal = get_goal(goal_id)
    if not goal:
        raise HTTPException(status_code=404, detail="目标不存在")

    update_goal(
        goal_id,
        title=req.title,
        intro=req.intro,
        category=req.category,
        deadline=req.deadline,
        reward_exp=req.reward_exp,
        category_image=req.category_image,
        milestones=[m.dict() for m in req.milestones] if req.milestones is not None else None,
    )
    return get_goal(goal_id)


@router.delete("/api/goals/{goal_id}")
def delete_existing_goal(goal_id: int):
    """删除目标"""
    goal = get_goal(goal_id)
    if not goal:
        raise HTTPException(status_code=404, detail="目标不存在")
    delete_goal(goal_id)
    return {"deleted": True}


@router.post("/api/goals/{goal_id}/claim")
def claim_goal(goal_id: int):
    """领取目标 EXP 奖励"""
    goal = get_goal(goal_id)
    if not goal:
        raise HTTPException(status_code=404, detail="目标不存在")
    if goal["claimed"]:
        raise HTTPException(status_code=400, detail="目标已领取过奖励")
    if goal["progress"] < 100:
        raise HTTPException(status_code=400, detail="目标尚未完成")

    result = claim_goal_reward(goal_id)
    if not result:
        raise HTTPException(status_code=400, detail="无法领取奖励")

    exp_earned = result["exp_earned"]

    # 使用服务层统一处理 EXP 奖励
    from services.exp_service import award_exp_and_recalc
    service_result = award_exp_and_recalc(goal["user_id"], goal["category"], exp_earned)

    return {
        "claimed": True,
        "exp_earned": exp_earned,
        "exp_result": service_result["exp_result"],
        "today_stats": service_result["today_stats"],
    }