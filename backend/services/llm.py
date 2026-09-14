"""
Self Grow — 统一 LLM 工厂

所有 AI 功能统一从这里获取 ChatOpenAI 实例（替代原先 coordinator/llm.py 与
ai_client.py 各自维护一份缓存的两套重复实现）。

模型来源：model_configs 表（用户配置）优先，.env 兜底。
实例按 (temperature, max_tokens, timeout, model, base_url, api_key) 缓存，
配置或参数变化 → key 变化 → 自动重建实例（无需重启）。
"""

import logging

from langchain_openai import ChatOpenAI

from config import AI_BASE_URL, AI_API_KEY, AI_MODEL
from db.model_configs import get_active_config

log = logging.getLogger(__name__)

# 默认超时（秒）。纯文本长生成场景（call_ai_text）会显式传更大的 timeout。
DEFAULT_TIMEOUT = 120.0

# 缓存实例：{cache_key: ChatOpenAI}
_llm_cache: dict[tuple, ChatOpenAI] = {}


def get_llm(
    temperature: float = 0.3,
    max_tokens: int = 9192,
    timeout: float = DEFAULT_TIMEOUT,
    user_id: int = None,
) -> ChatOpenAI:
    """获取（缓存的）LLM 实例。

    动态读取 model_configs 表里当前启用的 LLM 配置（无则回退 .env），
    用 (temperature, max_tokens, timeout, model, base_url, api_key) 做缓存 key，
    切换启用模型或参数变化后 key 变化 → 自动重建实例，无需重启。

    Args:
        temperature: 温度参数（默认 0.3）
        max_tokens: 最大输出 token（默认 9192，给协调器等长输出场景留足空间）
        timeout: 请求超时（秒，默认 120）
        user_id: 用户 ID（用于读取 model_configs 表里该用户启用的配置，默认 1）
    """
    cfg = get_active_config(user_id or 1, "llm")
    model = (cfg or {}).get("model") or AI_MODEL
    api_key = (cfg or {}).get("api_key") or AI_API_KEY
    base_url = (cfg or {}).get("base_url") or AI_BASE_URL

    cache_key = (temperature, max_tokens, timeout, model, base_url, api_key)
    if cache_key not in _llm_cache:
        _llm_cache[cache_key] = ChatOpenAI(
            model=model,
            api_key=api_key,
            base_url=base_url,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
            max_retries=0,
        )
        log.info(
            f"创建 LLM 实例: model={model}, temperature={temperature}, "
            f"max_tokens={max_tokens}, timeout={timeout}"
        )
    return _llm_cache[cache_key]
