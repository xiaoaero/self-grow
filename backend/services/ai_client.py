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

import hashlib
import logging
import time

from langchain_core.messages import HumanMessage, SystemMessage

from config import AI_API_KEY
from db.model_configs import get_active_config
from services.llm import get_effective_model, get_llm

log = logging.getLogger(__name__)

# 显式请求超时（秒）。推理模型长文本生成可达数分钟，避免 httpx 默认 5s 触发重试。
REQUEST_TIMEOUT = 300
# 输出上限：推理模型（qwen3.x-max 等）的 max_tokens 含思考部分，
# 若设置过小正文会被截断/为空，故给足空间（1024 正文 ≈ 约 700 token）
DEFAULT_MAX_TOKENS = 4096


def _digest(text: str) -> str:
    """给 prompt 生成一个短摘要（长度 + 前 8 位 hash）

    为什么不直接记 prompt 内容：本项目的 system_prompt / 用户输入里有
    用户的私人目标与情绪倾诉，INFO 级别不该落盘。要排查「是不是 prompt
    拼错了」时，比对 hash 是否变化就够了。
    """
    return f"{len(text)}字符/{hashlib.sha256(text.encode('utf-8')).hexdigest()[:8]}"


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
        max_tokens: 最大输出 token 数（默认 4096，见 DEFAULT_MAX_TOKENS）
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

    # ⚠️ 必须取「实际生效」的模型名。config.AI_MODEL 只是 .env 兜底值，
    # 用户在「用户中心 → 模型信息」切换模型后它不会变 —— 用常量记日志
    # 会让人以为还在用旧模型，排查时被直接带偏。
    model = get_effective_model(user_id)

    llm = get_llm(temperature=temperature, max_tokens=max_tokens, timeout=REQUEST_TIMEOUT, user_id=user_id)

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_message),
    ]

    log.info(
        "→ AI 请求: model=%s prompt=%s+%s",
        model, _digest(system_prompt), _digest(user_message),
    )
    # prompt 正文只在 DEBUG 出现，且仍然只给摘要不落原文
    log.debug("AI system_prompt=%r user_message=%r", system_prompt[:200], user_message[:200])

    started = time.perf_counter()
    try:
        response = await llm.ainvoke(messages)
        content = response.content.strip()
        elapsed = time.perf_counter() - started

        # token 用量：LangChain 的 AIMessage 统一暴露在 usage_metadata 上。
        # 取不到就记 "-"，**不要伪造数字** —— 假数据比没数据更害人。
        usage = getattr(response, "usage_metadata", None) or {}
        log.info(
            "← AI 回复: %d 字符 | %.1fs | in=%s out=%s",
            len(content), elapsed,
            usage.get("input_tokens", "-"), usage.get("output_tokens", "-"),
        )
        return content
    except Exception as e:
        log.exception(
            "AI 调用失败（model=%s，已耗时 %.1fs）", model, time.perf_counter() - started
        )
        raise RuntimeError(f"AI 调用失败: {str(e)}") from e

