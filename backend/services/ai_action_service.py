"""
Self Grow — AI 行动解析服务

通过对话式交互，让 AI 了解用户行动并精确计算经验值。
复用现有 httpx 调用模式，使用 action_parse 的 system prompt 和工具定义。
"""

import json
import logging
import httpx
from fastapi import HTTPException

from config import AI_BASE_URL, AI_API_KEY, AI_MODEL
from prompts.action_parse import ACTION_PARSE_SYSTEM_PROMPT, ACTION_PARSE_TOOLS

log = logging.getLogger(__name__)


async def call_action_ai(messages: list) -> dict:
    """
    调用 AI 行动解析代理。

    Args:
        messages: 对话历史列表，每项为 {"role": "user"|"assistant", "content": str}

    Returns:
        {"content": str} 或 {"tool_calls": [...]}

    Raises:
        HTTPException: 当 AI_API_KEY 未配置或 API 调用失败时
    """
    if not AI_API_KEY:
        raise HTTPException(status_code=500, detail="AI_API_KEY 未配置")

    # 构造消息列表：system prompt + 对话历史
    msgs = [{"role": "system", "content": ACTION_PARSE_SYSTEM_PROMPT}]
    msgs.extend(messages)

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            payload = {
                "model": AI_MODEL,
                "messages": msgs,
                "tools": ACTION_PARSE_TOOLS,
                "tool_choice": "auto",
                "temperature": 0.7,
                "max_tokens": 8192,
            }
            log.info(f"→ AI 行动解析请求: {AI_MODEL}, 消息数={len(messages)}")
            resp = await client.post(
                f"{AI_BASE_URL}/chat/completions",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {AI_API_KEY}",
                },
                json=payload,
            )

            if resp.status_code != 200:
                err_text = resp.text[:500]
                log.error(f"← AI 错误 {resp.status_code}: {err_text}")
                raise HTTPException(status_code=502, detail="AI API 返回错误")

            data = resp.json()
            choice = data["choices"][0]
            msg = choice["message"]

            # 检查是否有工具调用
            if "tool_calls" in msg and msg["tool_calls"]:
                tool_calls = []
                for tc in msg["tool_calls"]:
                    try:
                        args = json.loads(tc["function"]["arguments"])
                    except json.JSONDecodeError:
                        args = {"_raw": tc["function"]["arguments"]}
                    tool_calls.append({
                        "id": tc["id"],
                        "name": tc["function"]["name"],
                        "arguments": args,
                    })
                log.info(f"← AI 调用工具: {[t['name'] for t in tool_calls]}")
                return {"tool_calls": tool_calls}

            # 纯文本回复
            content = msg.get("content", "")
            log.info(f"← AI 回复: {content[:60]}...")
            return {"content": content}

    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="AI API 请求超时")
    except HTTPException:
        raise
    except Exception as e:
        log.exception("AI 请求异常")
        raise HTTPException(status_code=500, detail=f"AI 请求异常: {str(e)}")