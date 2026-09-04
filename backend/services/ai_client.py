"""
Self Grow — 统一 AI 调用客户端

封装 LangChain 的 ChatOpenAI 调用，供所有纯文本生成类 AI 功能使用。
技能树 AI（需要 Tool Use）保留独立调用方式。

优化点（2026-08-01）：
- 显式 request_timeout：避免 httpx 默认 5s 超时在网关慢时静默重试，放大延迟
- LLM 实例模块级缓存：复用连接池，省去每次调用的 DNS/TLS 握手
- 流式生成接口：供习惯分析等长文本场景打字机式输出
"""

import logging

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.outputs import ChatGenerationChunk

from config import AI_BASE_URL, AI_API_KEY, AI_MODEL
from db.model_configs import get_active_config

log = logging.getLogger(__name__)

# 显式请求超时（秒）。推理模型长文本生成可达数分钟，避免 httpx 默认 5s 触发重试。
REQUEST_TIMEOUT = 300
# 生成类任务超时重试收益低、还放大延迟，统一关闭
MAX_RETRIES = 0
# 输出上限：推理模型（qwen3.x-max 等）的 max_tokens 含思考部分，
# 若设置过小正文会被截断/为空，故给足空间（1024 正文 ≈ 约 700 token）
DEFAULT_MAX_TOKENS = 4096

# 模块级单例：复用 TCP/TLS 连接，避免每次调用重建
_llm_instance: ChatOpenAI | None = None
_llm_cache_key: tuple | None = None


def _get_llm(temperature: float = 0.7, max_tokens: int = DEFAULT_MAX_TOKENS,
             user_id: int = None) -> ChatOpenAI:
    """获取（缓存的）LLM 实例。模型配置或参数变化时重建实例。

    动态读取当前启用的 LLM 配置（model_configs 表），切换启用模型后
    cache_key 变化 → 重建实例，实现「切换模型即时生效」。
    """
    global _llm_instance, _llm_cache_key
    cfg = get_active_config(user_id or 1, "llm")
    model = (cfg or {}).get("model") or AI_MODEL
    api_key = (cfg or {}).get("api_key") or AI_API_KEY
    base_url = (cfg or {}).get("base_url") or AI_BASE_URL

    cache_key = (temperature, max_tokens, model, base_url, api_key)
    if _llm_instance is None or _llm_cache_key != cache_key:
        _llm_instance = ChatOpenAI(
            model=model,
            api_key=api_key,
            base_url=base_url,
            temperature=temperature,
            max_tokens=max_tokens,
            request_timeout=REQUEST_TIMEOUT,
            max_retries=MAX_RETRIES,
        )
        _llm_cache_key = cache_key
    return _llm_instance


async def call_ai_text(
    system_prompt: str,
    user_message: str,
    temperature: float = 0.7,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    user_id: int = None,
) -> str:
    """
    调用 AI 模型，返回纯文本回复。

    Args:
        system_prompt: 系统提示词
        user_message: 用户消息内容
        temperature: 温度参数（默认 0.7）
        max_tokens: 最大输出 token 数（默认 1024）
        user_id: 用户ID（用于读取其启用的模型配置，默认 1）

    Returns:
        AI 返回的文本内容

    Raises:
        RuntimeError: 当 AI_API_KEY 未配置或 API 调用失败时
    """
    cfg = get_active_config(user_id or 1, "llm")
    effective_key = (cfg or {}).get("api_key") or AI_API_KEY
    if not effective_key:
        raise RuntimeError("AI_API_KEY 未配置")

    llm = _get_llm(temperature=temperature, max_tokens=max_tokens, user_id=user_id)

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_message),
    ]

    log.info(f"→ AI 请求: {AI_MODEL}, system_prompt={system_prompt[:40]}...")
    try:
        response = await llm.ainvoke(messages)
        content = response.content.strip()
        log.info(f"← AI 回复: {len(content)} 字符")
        return content
    except Exception as e:
        log.exception("AI 调用失败")
        raise RuntimeError(f"AI 调用失败: {str(e)}") from e


async def call_ai_text_stream(
    system_prompt: str,
    user_message: str,
    temperature: float = 0.7,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    user_id: int = None,
):
    """
    调用 AI 模型，流式产出文本增量（异步生成器）。

    逐段产出字符串，供 SSE 等场景即时转发，缓解长文本"等待数分钟"的体验问题。
    仅使用模型的流式接口，不进行重试（生成中断后重试无意义）。

    Args:
        system_prompt: 系统提示词
        user_message: 用户消息内容
        temperature: 温度参数（默认 0.7）
        max_tokens: 最大输出 token 数（默认 1024）
        user_id: 用户ID（用于读取其启用的模型配置，默认 1）

    Yields:
        str: 文本增量块

    Raises:
        RuntimeError: 当 AI_API_KEY 未配置时
    """
    cfg = get_active_config(user_id or 1, "llm")
    effective_key = (cfg or {}).get("api_key") or AI_API_KEY
    if not effective_key:
        raise RuntimeError("AI_API_KEY 未配置")

    llm = _get_llm(temperature=temperature, max_tokens=max_tokens, user_id=user_id)

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_message),
    ]

    log.info(f"→ AI 流式请求: {AI_MODEL}, system_prompt={system_prompt[:40]}...")
    try:
        async for chunk in llm.astream(messages):
            if isinstance(chunk, ChatGenerationChunk):
                text = chunk.text
            else:
                text = getattr(chunk, "content", "") or ""
            if text:
                yield text
        log.info(f"← AI 流式回复完成: {AI_MODEL}")
    except Exception as e:
        log.exception("AI 流式调用失败")
        raise RuntimeError(f"AI 流式调用失败: {str(e)}") from e
