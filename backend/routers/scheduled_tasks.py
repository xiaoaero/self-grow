"""
Self Grow — 定时任务模板 API 路由
"""

from fastapi import APIRouter, Depends

from db.scheduled_tasks import get_scheduled_tasks, create_scheduled_task, update_scheduled_task, delete_scheduled_task
from schemas.api import CreateScheduledTaskRequest, UpdateScheduledTaskRequest
from routers.deps import get_current_user

router = APIRouter()


@router.get("/api/scheduled-tasks")
def list_scheduled_tasks(user=Depends(get_current_user)):
    """获取定时任务模板列表"""
    templates = get_scheduled_tasks(user["id"])
    daily = [t for t in templates if t["type"] == "daily"]
    weekly = [t for t in templates if t["type"] == "weekly"]
    return {"daily": daily, "weekly": weekly}


@router.post("/api/scheduled-tasks")
def create_new_scheduled_task(req: CreateScheduledTaskRequest, user=Depends(get_current_user)):
    """创建定时任务模板"""
    new_id = create_scheduled_task(
        user["id"], req.type, req.title, req.category,
        req.priority, req.exp, req.intro, req.weekdays,
    )
    return {"id": new_id}


@router.put("/api/scheduled-tasks/{task_id}")
def update_scheduled_task_route(task_id: int, req: UpdateScheduledTaskRequest):
    """更新定时任务模板"""
    update_scheduled_task(task_id, **{k: v for k, v in req.dict().items() if v is not None})
    return {"updated": True}


@router.delete("/api/scheduled-tasks/{task_id}")
def delete_scheduled_task_route(task_id: int):
    """删除定时任务模板"""
    delete_scheduled_task(task_id)
    return {"deleted": True}