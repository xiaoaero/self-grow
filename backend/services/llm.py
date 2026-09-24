"""
Self Grow — 统一 LLM 工厂

所有 AI 功能统一从这里获取 ChatOpenAI 实例（替代原先 coordinator/llm.py 与
ai_client.py 各自维护一份缓存的两套重复实现）。

模型来源：model_configs 表（用户配置）优先，.env 兜底。
实例按 (temperature, max_tokens, timeout, model, base_url, api_key) 缓存，
配置或参数变化 → key 变化 → 自动重建实例（无需重启）。
"""

import logging
from collections import OrderedDict

from langchain_openai import ChatOpenAI

from config import AI_BASE_URL, AI_API_KEY, AI_MODEL
from db.model_configs import get_active_config

log = logging.getLogger(__name__)

# 默认超时（秒）。纯文本长生成场景（call_ai_text）会显式传更大的 timeout。
DEFAULT_TIMEOUT = 120.0

# 缓存实例：{cache_key: ChatOpenAI} —— 用 OrderedDict 做 LRU
#
# ⚠️ 必须有容量上限。原来是个普通 dict，只增不减：
#    key 里含 (temperature, max_tokens, timeout, model, base_url, api_key)，
#    虽然单用户切模型也就几十个，但「改一次配置多一个常驻实例」这件事
#    没有任何东西拦着 —— 每个实例都带自己的 httpx 连接池。
#    加上限是廉价的保险。
_MAX_LLM_CACHE = 32
_llm_cache: "OrderedDict[tuple, ChatOpenAI]" = OrderedDict()


def get_llm(
    temperature: float = 0.3,
    max_tokens: int | None = 9192,
    timeout: float = DEFAULT_TIMEOUT,
    user_id: int = None,
) -> ChatOpenAI:
    """获取（缓存的）LLM 实例。

    动态读取 model_configs 表里当前启用的 LLM 配置（无则回退 .env），
    用 (temperature, max_tokens, timeout, model, base_url, api_key) 做缓存 key，
    切换启用模型或参数变化后 key 变化 → 自动重建实例，无需重启。

    Args:
        temperature: 温度参数（默认 0.3）
        max_tokens: 最大输出 token。默认 9192（给协调器等长输出场景留足空间）；
                    **传 None = 不限制** —— 这时不往请求里带这个字段，交给服务商的默认上限
                   （`ChatOpenAI` 把 max_tokens 放在 `exclude_if_none` 里，None 不会发出去，
                    换成 0 或 -1 反而会被部分服务商当成"输出 0 个 token"）
        timeout: 请求超时（秒，默认 120）
        user_id: 用户 ID（用于读取 model_configs 表里该用户启用的配置，默认 1）
    """
    cfg = get_active_config(user_id or 1, "llm")
    model = (cfg or {}).get("model") or AI_MODEL
    api_key = (cfg or {}).get("api_key") or AI_API_KEY
    base_url = (cfg or {}).get("base_url") or AI_BASE_URL

    cache_key = (temperature, max_tokens, timeout, model, base_url, api_key)

    # 命中即刷新热度（LRU 的「最近使用」）
    cached = _llm_cache.get(cache_key)
    if cached is not None:
        _llm_cache.move_to_end(cache_key)
        return cached

    llm = ChatOpenAI(
        model=model,
        api_key=api_key,
        base_url=base_url,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=timeout,
        max_retries=0,
    )
    _llm_cache[cache_key] = llm
    log.info(
        f"创建 LLM 实例: model={model}, temperature={temperature}, "
        f"max_tokens={max_tokens}, timeout={timeout}"
    )

    # 超出容量 → 淘汰最久未用的
    #
    # ⚠️ 只从缓存字典里移除，**不要**顺手调 `aclose()`：
    #    `get_llm()` 是同步函数，而 `ChatOpenAI.aclose()` 是 async ——
    #    在同步上下文里调它得引 event loop，会给调用方凭空加一堆约束。
    #    被淘汰的实例如果正被某个请求持有，它仍有引用、不会消失；
    #    用完之后引用归零，GC 会连它的连接池一起收掉。让 GC 处理就好。
    while len(_llm_cache) > _MAX_LLM_CACHE:
        evicted_key, _ = _llm_cache.popitem(last=False)
        log.info(
            "LLM 实例缓存已达上限 %d，淘汰最久未用：model=%s temperature=%s",
            _MAX_LLM_CACHE, evicted_key[3], evicted_key[0],
        )

    return llm


def get_effective_model(user_id: int = None) -> str:
    """返回该用户**当前实际生效**的模型名（供日志使用）

    ⚠️ 记日志时不要用 `config.AI_MODEL` —— 那只是 .env 里的兜底值。
    用户在「用户中心 → 模型信息」切换模型后它不会变，于是日志里会一直
    显示旧模型名，排查「回复质量突然变了」时会被直接带偏。
    （`services/ai_client.py` 原来打的就是那个常量，属于静默误导。）
    """
    cfg = get_active_config(user_id or 1, "llm")
    return (cfg or {}).get("model") or AI_MODEL or "(未配置)"
