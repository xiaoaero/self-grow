"""
Self Grow — 技能树 API 路由

提供技能树的 CRUD 操作，替代前端 localStorage 存储。
"""

from fastapi import APIRouter, HTTPException, Depends, Body

from db.skill_tree import (
    get_skill_trees, get_skill_tree_by_tree_id, create_skill_tree,
    save_skill_tree_draft, publish_skill_tree, get_published_skill_tree,
    save_learner_progress, delete_skill_tree,
    get_user_skill_ids, save_user_skill_ids,
)
from routers.deps import get_current_user, require_admin

router = APIRouter()


@router.get("/api/skill-trees")
def list_skill_trees(user=Depends(get_current_user)):
    """获取用户所有技能树（索引列表）"""
    trees = get_skill_trees(user["id"])
    return {"trees": trees}


@router.post("/api/skill-trees")
def create_new_skill_tree(
    tree_id: str = Body(...),
    name: str = Body(...),
    description: str = Body(""),
    user=Depends(require_admin),
):
    """创建新技能树（幂等）

    `create_skill_tree` 对同一个 tree_id 重复调用不报错（返回已有 id）；
    返回 0 表示这个 tree_id 已被**别人**占用 —— 此时必须报冲突，
    不能假装成功（否则用户会得到一棵自己永远访问不到的树）。
    """
    try:
        new_id = create_skill_tree(user["id"], tree_id, name, description)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"创建失败: {str(e)}")
    if not new_id:
        raise HTTPException(status_code=409, detail="该技能树 ID 已被占用，请换一个")
    return {"id": new_id, "tree_id": tree_id, "success": True}


@router.get("/api/skill-trees/{tree_id}")
def get_skill_tree(tree_id: str, user=Depends(get_current_user)):
    """获取单个技能树草稿数据"""
    tree = get_skill_tree_by_tree_id(tree_id, user["id"])
    if not tree:
        raise HTTPException(status_code=404, detail="技能树不存在")
    return tree


@router.put("/api/skill-trees/{tree_id}")
def update_skill_tree(
    tree_id: str,
    name: str = Body(...),
    description: str = Body(""),
    data: dict = Body(...),
    node_count: int = Body(0),
    completed_count: int = Body(0),
    image: str = Body(""),
    remark: str = Body(""),
    user=Depends(require_admin),
):
    """保存技能树草稿

    ⚠️ 必须**如实**返回结果：以前这个端点无论如何都 `{"success": True}`，
    而 DB 层也无论如何都 return True —— 于是「保存失败」在界面上和成功一模一样。
    现在 DB 层会告诉我们在不在写、有没有写进去（树不存在则顺手补建）。
    """
    ok = save_skill_tree_draft(
        tree_id, user["id"], name, description,
        data, node_count, completed_count, image, remark,
    )
    if not ok:
        # 只有一种情况会走到这：库里已有同 tree_id 但属于别的用户
        raise HTTPException(status_code=403, detail="这棵技能树不属于当前用户，无法保存")
    return {"success": True}


@router.put("/api/skill-trees/{tree_id}/publish")
def publish_skill_tree_endpoint(
    tree_id: str,
    published_data: dict = Body(...),
    node_count: int = Body(0),
    completed_count: int = Body(0),
    user=Depends(require_admin),
):
    """发布/更新技能树"""
    ok = publish_skill_tree(tree_id, user["id"], published_data, node_count, completed_count)
    if not ok:
        raise HTTPException(status_code=404, detail="技能树不存在，请先保存草稿")
    return {"success": True}


@router.get("/api/skill-trees/{tree_id}/published")
def get_published_tree(tree_id: str):
    """获取已发布的技能树（含学习进度，无需登录）"""
    tree = get_published_skill_tree(tree_id)
    if not tree:
        raise HTTPException(status_code=404, detail="该技能树未发布或不存在")
    return tree


@router.put("/api/skill-trees/{tree_id}/learner")
def update_learner_progress(
    tree_id: str,
    learner: dict = Body(...),
    user=Depends(get_current_user),
):
    """保存学习进度"""
    save_learner_progress(tree_id, user["id"], learner)
    return {"success": True}


@router.delete("/api/skill-trees/{tree_id}")
def delete_skill_tree_endpoint(tree_id: str, user=Depends(require_admin)):
    """删除技能树"""
    delete_skill_tree(tree_id, user["id"])
    return {"success": True}


@router.get("/api/skill-trees/user-skills/list")
def list_user_skills(user=Depends(get_current_user)):
    """获取用户已添加的技能 ID 列表"""
    skill_ids = get_user_skill_ids(user["id"])
    return {"skill_ids": skill_ids}


@router.put("/api/skill-trees/user-skills/list")
def save_user_skills(
    skill_ids: list = Body(..., embed=True),
    user=Depends(get_current_user),
):
    """保存用户已添加的技能 ID 列表"""
    save_user_skill_ids(user["id"], skill_ids)
    return {"success": True}