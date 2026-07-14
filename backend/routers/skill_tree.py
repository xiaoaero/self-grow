"""
Self Grow — 技能树 API 路由

提供技能树的 CRUD 操作，替代前端 localStorage 存储。
"""

from fastapi import APIRouter, HTTPException, Depends, Query, Body

from db.skill_tree import (
    get_skill_trees, get_skill_tree_by_tree_id, create_skill_tree,
    save_skill_tree_draft, publish_skill_tree, get_published_skill_tree,
    save_learner_progress, delete_skill_tree,
    get_user_skill_ids, save_user_skill_ids,
)
from routers.deps import get_current_user

router = APIRouter()


@router.get("/api/skill-trees")
async def list_skill_trees(user=Depends(get_current_user)):
    """获取用户所有技能树（索引列表）"""
    trees = get_skill_trees(user["id"])
    return {"trees": trees}


@router.post("/api/skill-trees")
async def create_new_skill_tree(
    tree_id: str = Body(...),
    name: str = Body(...),
    description: str = Body(""),
    user=Depends(get_current_user),
):
    """创建新技能树"""
    try:
        new_id = create_skill_tree(user["id"], tree_id, name, description)
        return {"id": new_id, "tree_id": tree_id, "success": True}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"创建失败: {str(e)}")


@router.get("/api/skill-trees/{tree_id}")
async def get_skill_tree(tree_id: str, user=Depends(get_current_user)):
    """获取单个技能树草稿数据"""
    tree = get_skill_tree_by_tree_id(tree_id, user["id"])
    if not tree:
        raise HTTPException(status_code=404, detail="技能树不存在")
    return tree


@router.put("/api/skill-trees/{tree_id}")
async def update_skill_tree(
    tree_id: str,
    name: str = Body(...),
    description: str = Body(""),
    data: dict = Body(...),
    node_count: int = Body(0),
    completed_count: int = Body(0),
    image: str = Body(""),
    remark: str = Body(""),
    user=Depends(get_current_user),
):
    """保存技能树草稿"""
    save_skill_tree_draft(
        tree_id, user["id"], name, description,
        data, node_count, completed_count, image, remark,
    )
    return {"success": True}


@router.put("/api/skill-trees/{tree_id}/publish")
async def publish_skill_tree_endpoint(
    tree_id: str,
    published_data: dict = Body(...),
    node_count: int = Body(0),
    completed_count: int = Body(0),
    user=Depends(get_current_user),
):
    """发布/更新技能树"""
    publish_skill_tree(tree_id, user["id"], published_data, node_count, completed_count)
    return {"success": True}


@router.get("/api/skill-trees/{tree_id}/published")
async def get_published_tree(tree_id: str):
    """获取已发布的技能树（含学习进度，无需登录）"""
    tree = get_published_skill_tree(tree_id)
    if not tree:
        raise HTTPException(status_code=404, detail="该技能树未发布或不存在")
    return tree


@router.put("/api/skill-trees/{tree_id}/learner")
async def update_learner_progress(
    tree_id: str,
    learner: dict = Body(...),
    user=Depends(get_current_user),
):
    """保存学习进度"""
    save_learner_progress(tree_id, user["id"], learner)
    return {"success": True}


@router.delete("/api/skill-trees/{tree_id}")
async def delete_skill_tree_endpoint(tree_id: str, user=Depends(get_current_user)):
    """删除技能树"""
    delete_skill_tree(tree_id, user["id"])
    return {"success": True}


@router.get("/api/skill-trees/user-skills/list")
async def list_user_skills(user=Depends(get_current_user)):
    """获取用户已添加的技能 ID 列表"""
    skill_ids = get_user_skill_ids(user["id"])
    return {"skill_ids": skill_ids}


@router.put("/api/skill-trees/user-skills/list")
async def save_user_skills(
    skill_ids: list = Body(..., embed=True),
    user=Depends(get_current_user),
):
    """保存用户已添加的技能 ID 列表"""
    save_user_skill_ids(user["id"], skill_ids)
    return {"success": True}