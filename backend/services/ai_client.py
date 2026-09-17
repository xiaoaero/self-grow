"""
Self Grow — 统一 AI 调用客户端

封装 LangChain 的 ChatOpenAI 调用，供所有纯文本生成类 AI 功能使用。
技能树 AI（需要 Tool Use）保留独立调用方式。

优化点（2026-08-01）：
- 显式 request_timeout：避免 httpx 默认 5s 超时在网关慢时静默重试，放大延迟
- LLM 实例模块级缓存：复用连接池，省去每次调用的 DNS/TLS 握手

注：原来这里还有一个 `call_ai_text_stream()`（异步生成器，逐段 yield 文本），
已于 2026-09-17 删除 —— 全项目零调用。现在需要逐 token 流式的地方
（协调 Agent 的总结节点）直接用 `llm.astream()`，并且事件通过
`services/sse.py` 的 `emit_token` 往 SSE 流里推，不需要中间再包一层生成器。
"""

import logging

from langchain_core.messages import HumanMessage, SystemMessage

from config import AI_API_KEY, AI_MODEL
from db.model_configs import get_active_config
from services.llm import get_llm

log = logging.getLogger(__name__)

# 显式请求超时（秒）。推理模型长文本生成可达数分钟，避免 httpx 默认 5s 触发重试。
REQUEST_TIMEOUT = 300
# 输出上限：推理模型（qwen3.x-max 等）的 max_tokens 含思考部分，
# 若设置过小正文会被截断/为空，故给足空间（1024 正文 ≈ 约 700 token）
DEFAULT_MAX_TOKENS = 4096


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

    llm = get_llm(temperature=temperature, max_tokens=max_tokens, timeout=REQUEST_TIMEOUT, user_id=user_id)

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

