"""
Self Grow — 统一 AI 调用客户端

封装 LangChain 的 ChatOpenAI 调用，供所有纯文本生成类 AI 功能使用。
技能树 AI（需要 Tool Use）保留独立调用方式。
"""

import logging
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

from config import AI_BASE_URL, AI_API_KEY, AI_MODEL

log = logging.getLogger(__name__)


async def call_ai_text(
    system_prompt: str,
    user_message: str,
    temperature: float = 0.7,
    max_tokens: int = 2048,
) -> str:
    """
    调用 AI 模型，返回纯文本回复。

    Args:
        system_prompt: 系统提示词
        user_message: 用户消息内容
        temperature: 温度参数（默认 0.7）
        max_tokens: 最大输出 token 数（默认 2048）

    Returns:
        AI 返回的文本内容

    Raises:
        RuntimeError: 当 AI_API_KEY 未配置或 API 调用失败时
    """
    if not AI_API_KEY:
        raise RuntimeError("AI_API_KEY 未配置")

    llm = ChatOpenAI(
        model=AI_MODEL,
        api_key=AI_API_KEY,
        base_url=AI_BASE_URL,
        temperature=temperature,
        max_tokens=max_tokens,
    )

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