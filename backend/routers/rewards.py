"""
Self Grow — 奖励商城 API 路由
"""

import os
import time

from fastapi import APIRouter, HTTPException, Depends, UploadFile, File

from db.rewards import get_reward, create_reward, update_reward, delete_reward, claim_reward, manual_confirm_condition, evaluate_all_rewards, evaluate_reward, save_reward_draft, get_reward_draft, delete_reward_draft
from schemas.api import CreateRewardRequest, UpdateRewardRequest, ManualConfirmRequest
from routers.deps import get_current_user
from config import UPLOAD_DIR

router = APIRouter()


@router.get("/api/rewards")
def list_rewards(user=Depends(get_current_user)):
    """获取所有奖励（自动评估解锁状态）"""
    rewards = evaluate_all_rewards(user["id"])
    return {"rewards": rewards}


@router.post("/api/rewards")
def create_new_reward(req: CreateRewardRequest, user=Depends(get_current_user)):
    """创建新奖励"""
    new_id = create_reward(
        user["id"], req.title, req.desc, req.icon,
        req.category, req.image,
        req.unlock_conditions, req.claim_conditions,
    )
    reward = get_reward(new_id)
    return reward


@router.put("/api/rewards/{reward_id}")
def update_existing_reward(reward_id: int, req: UpdateRewardRequest, user=Depends(get_current_user)):
    """更新奖励"""
    reward = get_reward(reward_id)
    if not reward:
        raise HTTPException(status_code=404, detail="奖励不存在")
    if reward["user_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="无权修改他人奖励")

    kwargs = {k: v for k, v in req.dict(exclude_unset=True).items() if v is not None}
    update_reward(reward_id, **kwargs)
    return get_reward(reward_id)


@router.delete("/api/rewards/{reward_id}")
def delete_existing_reward(reward_id: int, user=Depends(get_current_user)):
    """删除奖励"""
    reward = get_reward(reward_id)
    if not reward:
        raise HTTPException(status_code=404, detail="奖励不存在")
    if reward["user_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="无权删除他人奖励")
    delete_reward(reward_id)
    return {"deleted": True}


@router.post("/api/rewards/{reward_id}/claim")
def claim_reward_endpoint(reward_id: int, user=Depends(get_current_user)):
    """领取奖励（后端校验条件）"""
    reward = get_reward(reward_id)
    if not reward:
        raise HTTPException(status_code=404, detail="奖励不存在")
    if reward.get("claimed"):
        raise HTTPException(status_code=400, detail="奖励已领取过")
    if not reward.get("unlocked"):
        raise HTTPException(status_code=400, detail="奖励尚未解锁")

    evaluated = evaluate_reward(user["id"], reward)
    if not evaluated.get("unlocked"):
        raise HTTPException(status_code=400, detail="解锁条件未满足")

    result = claim_reward(reward_id, user["id"])
    if not result:
        raise HTTPException(status_code=400, detail="领取条件未满足或已领取")

    return result


@router.post("/api/rewards/{reward_id}/manual-confirm")
def manual_confirm_reward_condition(reward_id: int, req: ManualConfirmRequest, user=Depends(get_current_user)):
    """手动确认某个条件"""
    reward = get_reward(reward_id)
    if not reward:
        raise HTTPException(status_code=404, detail="奖励不存在")
    if reward["user_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="无权操作他人奖励")

    manual_confirm_condition(reward_id, req.condition_text)
    return {"confirmed": True}


@router.post("/api/rewards/reevaluate")
def reevaluate_all_rewards(user=Depends(get_current_user)):
    """重新评估所有奖励的解锁状态"""
    rewards = evaluate_all_rewards(user["id"])
    return {"rewards": rewards}


@router.post("/api/rewards/{reward_id}/image")
async def upload_reward_image(reward_id: int, file: UploadFile = File(...)):
    """上传奖励图片"""
    reward = get_reward(reward_id)
    if not reward:
        raise HTTPException(status_code=404, detail="奖励不存在")

    upload_dir = os.path.join(UPLOAD_DIR, "rewards")
    os.makedirs(upload_dir, exist_ok=True)

    ext = os.path.splitext(file.filename)[1] or ".jpg"
    filename = f"reward_{reward_id}_{int(time.time())}{ext}"
    filepath = os.path.join(upload_dir, filename)
    content = await file.read()
    with open(filepath, "wb") as f:
        f.write(content)

    url = f"/uploads/rewards/{filename}"
    update_reward(reward_id, image=url)
    return {"url": url}


# ================================================================
# 奖励草稿 API
# ================================================================

@router.get("/api/rewards/draft")
def get_draft(user=Depends(get_current_user)):
    """获取草稿"""
    draft = get_reward_draft(user["id"])
    return {"draft": draft}


@router.post("/api/rewards/draft")
def save_draft(req: CreateRewardRequest, user=Depends(get_current_user)):
    """保存草稿"""
    save_reward_draft(user["id"], req.dict())
    return {"saved": True}


@router.delete("/api/rewards/draft")
def delete_draft(user=Depends(get_current_user)):
    """删除草稿"""
    delete_reward_draft(user["id"])
    return {"deleted": True}