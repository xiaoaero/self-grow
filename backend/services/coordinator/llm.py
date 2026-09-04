"""
Self Grow — Coordinator Agent 统一 LLM 实例

复用项目现有 ChatOpenAI 模式，为 coordinator 主图和各子图提供统一 LLM 接口。

支持「模型动态切换」：每次获取实例时从 model_configs 表读取当前启用的 LLM 配置
（无配置或配置无效则回退 .env），切换启用模型后缓存 key 变化 → 自动重建实例。
"""

import logging
from langchain_openai import ChatOpenAI
from config import AI_BASE_URL, AI_API_KEY, AI_MODEL
from db.model_configs import get_active_config

log = logging.getLogger(__name__)

# 超时与重试
REQUEST_TIMEOUT = 120
MAX_RETRIES = 0

# 缓存实例：{cache_key: ChatOpenAI}
# cache_key 含 model/base_url/api_key，切换模型后 key 变化 → 重建实例
_llm_cache: dict[tuple, ChatOpenAI] = {}


def get_llm(temperature: float = 0.3, user_id: int = None) -> ChatOpenAI:
    """获取缓存的 LLM 实例。

    动态读取当前启用的模型配置（user_id 对应 model_configs 表，默认 1），
    切换启用模型后自动重建实例。
    """
    cfg = get_active_config(user_id or 1, "llm")
    model = (cfg or {}).get("model") or AI_MODEL
    api_key = (cfg or {}).get("api_key") or AI_API_KEY
    base_url = (cfg or {}).get("base_url") or AI_BASE_URL

    cache_key = (temperature, model, base_url, api_key)
    if cache_key not in _llm_cache:
        _llm_cache[cache_key] = ChatOpenAI(
            model=model,
            api_key=api_key,
            base_url=base_url,
            temperature=temperature,
            max_tokens=9192,
            timeout=REQUEST_TIMEOUT,
            max_retries=MAX_RETRIES,
        )
        log.info(f"创建 LLM 实例: model={model}, temperature={temperature}")
    return _llm_cache[cache_key]
