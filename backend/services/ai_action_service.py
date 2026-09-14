"""
Self Grow — AI 行动解析服务

通过对话式交互，让 AI 了解用户行动并精确计算经验值。
使用 LangChain ChatOpenAI（统一 LLM 工厂 get_llm），替代原 httpx 直连 env 的写法。
模型来源：用户配置（model_configs 表）优先，env 兜底。
"""

import logging
from fastapi import HTTPException

from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from services.llm import get_llm
from prompts.action_parse import ACTION_PARSE_SYSTEM_PROMPT, ACTION_PARSE_TOOLS

log = logging.getLogger(__name__)


def _to_langchain_messages(messages: list) -> list:
    """把 [{"role": "user"|"assistant", "content": str}] 转成 LangChain 消息列表"""
    result = []
    for m in messages:
        role = m.get("role", "user")
        content = m.get("content", "")
        if role == "assistant":
            result.append(AIMessage(content=content))
        else:
            result.append(HumanMessage(content=content))
    return result


async def call_action_ai(messages: list, user_id: int = 1) -> dict:
    """
    调用 AI 行动解析代理。

    Args:
        messages: 对话历史列表，每项为 {"role": "user"|"assistant", "content": str}
        user_id: 用户 ID（用于读取 model_configs 表里该用户启用的模型配置）

    Returns:
        {"content": str} 或 {"tool_calls": [...]}

    Raises:
        HTTPException: 当 AI 调用失败时
    """
    llm = get_llm(temperature=0.7, user_id=user_id)
    # ACTION_PARSE_TOOLS 是 OpenAI function 格式，直接 bind 原样传给 API
    llm_with_tools = llm.bind(tools=ACTION_PARSE_TOOLS, tool_choice="auto")

    # 构造消息列表：system prompt + 对话历史
    msgs = [SystemMessage(content=ACTION_PARSE_SYSTEM_PROMPT)] + _to_langchain_messages(messages)

    try:
        log.info(f"→ AI 行动解析请求: 消息数={len(messages)}")
        resp = await llm_with_tools.ainvoke(msgs)

        # 检查是否有工具调用
        if resp.tool_calls:
            tool_calls = [
                {"id": tc["id"], "name": tc["name"], "arguments": tc["args"]}
                for tc in resp.tool_calls
            ]
            log.info(f"← AI 调用工具: {[t['name'] for t in tool_calls]}")
            return {"tool_calls": tool_calls}

        # 纯文本回复
        content = resp.content or ""
        log.info(f"← AI 回复: {content[:60]}...")
        return {"content": content}

    except HTTPException:
        raise
    except Exception as e:
        log.exception("AI 请求异常")
        raise HTTPException(status_code=500, detail=f"AI 请求异常: {str(e)}")
