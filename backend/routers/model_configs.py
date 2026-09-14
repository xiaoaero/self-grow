"""
Self Grow — 模型配置 API

用户可管理多个 AI 模型配置（LLM / ASR），支持增删改 + 切换启用。
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from routers.deps import get_current_user
from db.model_configs import (
    get_configs, get_config, create_config, update_config,
    delete_config, set_active,
)

router = APIRouter(prefix="/api/model-configs", tags=["model-configs"])


def _mask_key(key: str) -> str:
    """脱敏密钥：保留前 3 后 4，中间打码"""
    if not key:
        return ""
    if len(key) <= 8:
        return "****"
    return key[:3] + "****" + key[-4:]


def _to_public(cfg: dict) -> dict:
    """返回给前端的配置（api_key 脱敏）"""
    d = dict(cfg)
    d["api_key"] = _mask_key(d.get("api_key", ""))
    return d


class ModelConfigCreate(BaseModel):
    type: str
    name: str
    model: str
    base_url: str = ""
    api_key: str = ""


class ModelConfigUpdate(BaseModel):
    name: str = None
    model: str = None
    base_url: str = None
    api_key: str = None


@router.get("")
def list_configs(type: Optional[str] = None, user=Depends(get_current_user)):
    """获取模型配置列表（可按 type 过滤）"""
    cfgs = get_configs(user["id"], type=type)
    return [_to_public(c) for c in cfgs]


@router.post("")
def add_config(req: ModelConfigCreate, user=Depends(get_current_user)):
    """新增模型配置"""
    if req.type not in ("llm", "asr"):
        raise HTTPException(status_code=400, detail="type 必须是 llm 或 asr")
    cfg_id = create_config(user["id"], req.type, req.name, req.model, req.base_url, req.api_key)
    return {"success": True, "id": cfg_id}


@router.put("/{config_id}")
def edit_config(config_id: int, req: ModelConfigUpdate, user=Depends(get_current_user)):
    """编辑模型配置"""
    cfg = get_config(config_id)
    if not cfg or cfg["user_id"] != user["id"]:
        raise HTTPException(status_code=404, detail="配置不存在")
    updates = {}
    if req.name is not None: updates["name"] = req.name
    if req.model is not None: updates["model"] = req.model
    if req.base_url is not None: updates["base_url"] = req.base_url
    if req.api_key is not None: updates["api_key"] = req.api_key
    update_config(config_id, **updates)
    return {"success": True}


@router.delete("/{config_id}")
def remove_config(config_id: int, user=Depends(get_current_user)):
    """删除模型配置"""
    cfg = get_config(config_id)
    if not cfg or cfg["user_id"] != user["id"]:
        raise HTTPException(status_code=404, detail="配置不存在")
    delete_config(config_id)
    return {"success": True}


@router.post("/{config_id}/activate")
def activate_config(config_id: int, user=Depends(get_current_user)):
    """切换启用（同类型下互斥，只能有一个启用）"""
    cfg = get_config(config_id)
    if not cfg or cfg["user_id"] != user["id"]:
        raise HTTPException(status_code=404, detail="配置不存在")
    set_active(user["id"], cfg["type"], config_id)
    return {"success": True}


class ModelConfigTest(BaseModel):
    type: str
    model: str
    base_url: str = ""
    api_key: str = ""


@router.post("/test")
async def test_connection(req: ModelConfigTest, user=Depends(get_current_user)):
    """测试模型配置连通性（LLM 发 ping，ASR 做配置校验）"""
    if not req.api_key:
        return {"success": False, "message": "API Key 为空"}
    if req.type == "llm":
        return await _test_llm(req)
    elif req.type == "asr":
        return {"success": True, "message": "ASR 配置有效（语音识别将在使用时建立连接）"}
    return {"success": False, "message": "type 必须是 llm 或 asr"}


async def _test_llm(req: ModelConfigTest) -> dict:
    """用 ChatOpenAI 发一个极短 ping，验证 model/base_url/api_key 是否可用"""
    from langchain_openai import ChatOpenAI
    try:
        llm = ChatOpenAI(
            model=req.model,
            api_key=req.api_key,
            base_url=req.base_url or None,
            max_tokens=1,
            timeout=30,
            max_retries=0,
        )
        await llm.ainvoke("ping")
        return {"success": True, "message": "连接成功"}
    except Exception as e:
        return {"success": False, "message": str(e)[:200]}
