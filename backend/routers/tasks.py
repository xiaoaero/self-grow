"""
Self Grow — 任务 API 路由
"""

from fastapi import APIRouter, HTTPException, Depends

from db.tasks import get_task, get_today_tasks, get_week_tasks, get_tasks_paginated, create_task, update_task, delete_task, claim_task_reward
from db.task_history import get_task_history
from schemas.api import CreateTaskRequest, UpdateTaskRequest, PatchTaskStatusRequest
from routers.deps import get_current_user

router = APIRouter()


@router.get("/api/tasks")
async def list_today_tasks(user=Depends(get_current_user)):
    """获取今日任务（todo/doing/done 三栏）"""
    return get_today_tasks(user["id"])


@router.get("/api/tasks/week")
async def list_week_tasks(user=Depends(get_current_user)):
    """获取本周任务（todo/doing/done 三栏，周一至周日）"""
    return get_week_tasks(user["id"])


@router.get("/api/tasks/all")
async def list_all_tasks(
    user=Depends(get_current_user),
    page: int = 1,
    page_size: int = 20,
    status: str = None,
    category: str = None,
    sort: str = "newest",
):
    """分页获取所有任务（含历史）"""
    return get_tasks_paginated(
        user["id"], page=page, page_size=page_size,
        status=status, category=category, sort=sort,
    )


@router.post("/api/tasks")
async def create_new_task(req: CreateTaskRequest, user=Depends(get_current_user)):
    """创建任务"""
    new_id = create_task(
        user["id"], req.title, req.category, req.priority,
        req.exp, req.intro, req.status, req.source_type, req.source_template_id,
    )
    # 使用 get_task 替代直接 sqlite3.connect('data.db')
    task = get_task(new_id)
    return task if task else {"id": new_id}


@router.put("/api/tasks/{task_id}")
async def update_existing_task(task_id: int, req: UpdateTaskRequest):
    """更新任务"""
    update_task(task_id, **{k: v for k, v in req.dict().items() if v is not None})
    return {"updated": True}


@router.patch("/api/tasks/{task_id}/status")
async def patch_task_status(task_id: int, req: PatchTaskStatusRequest):
    """修改任务状态"""
    kwargs = {"status": req.status}
    if req.completed_at:
        kwargs["completed_at"] = req.completed_at
    update_task(task_id, **kwargs)
    return {"status": req.status}


@router.post("/api/tasks/{task_id}/claim")
async def claim_task(task_id: int, user=Depends(get_current_user)):
    """领取任务 EXP 奖励"""
    result = claim_task_reward(task_id)
    if not result:
        raise HTTPException(status_code=400, detail="任务不存在或已领取")

    exp_earned = result["exp_earned"]

    # 使用 get_task 替代 get_tasks_paginated + 裸 SQL 的脆弱查询
    task = get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    # 使用服务层统一处理 EXP 奖励
    from services.exp_service import award_exp_and_recalc
    service_result = award_exp_and_recalc(
        user["id"], task["category"], exp_earned,
        extra_tasks_done=1,
    )

    return {
        "claimed": True,
        "exp_earned": exp_earned,
        "exp_result": service_result["exp_result"],
        "today_stats": service_result["today_stats"],
    }


@router.delete("/api/tasks/{task_id}")
async def delete_existing_task(task_id: int):
    """删除任务"""
    delete_task(task_id)
    return {"deleted": True}


@router.get("/api/tasks/history")
async def list_task_history(
    user=Depends(get_current_user),
    user_id: int = None,
    page: int = 1,
    page_size: int = 20,
    status: str = "all",
    source_type: str = "all",
    category: str = "all",
    sort: str = "newest",
):
    """分页获取任务历史（已归档的日任务/周任务）"""
    # 校验 user_id 与 token 中的用户一致
    if user_id is not None and user_id != user["id"]:
        raise HTTPException(status_code=403, detail="无权访问其他用户数据")
    return get_task_history(
        user["id"], page=page, page_size=page_size,
        status=status, source_type=source_type,
        category=category, sort=sort,
    )
