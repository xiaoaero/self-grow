"""
Self Grow — AI 代理服务

封装 AI 聊天功能，包括工具定义、系统提示词、HTTP 调用逻辑。
提示词和工具定义从 prompts/ 模块导入，便于统一管理。
"""

import json
import logging
import httpx
from fastapi import HTTPException

from config import AI_BASE_URL, AI_API_KEY, AI_MODEL
from prompts import SKILL_TREE_SYSTEM_PROMPT, SKILL_TREE_TOOLS

log = logging.getLogger(__name__)


async def call_ai(messages: list, tree_state: dict = None):
    """调用 AI API，返回 ChatResponse 所需的数据"""
    if not AI_API_KEY:
        raise HTTPException(status_code=500, detail="AI_API_KEY 未配置")

    # 构造 messages
    msgs = [{"role": "system", "content": SKILL_TREE_SYSTEM_PROMPT}]

    if tree_state:
        tree_info = json.dumps(tree_state, ensure_ascii=False, indent=2)
        msgs.append({
            "role": "system",
            "content": f"当前知识树状态：\n{tree_info}",
        })

    msgs.extend(messages)

    # 调用 AI API
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            payload = {
                "model": AI_MODEL,
                "messages": msgs,
                "tools": SKILL_TREE_TOOLS,
                "tool_choice": "auto",
                "temperature": 0.7,
                "max_tokens": 8192,
            }
            log.info(f"→ 请求 AI: {AI_MODEL}")
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
                raise HTTPException(
                    status_code=502,
                    detail=f"AI API 错误 {resp.status_code}: {err_text}",
                )

            data = resp.json()
            choice = data["choices"][0]
            msg = choice["message"]

            # 如果有工具调用，返回给前端
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
                log.info(f"← AI 调用 {len(tool_calls)} 个工具: {[t['name'] for t in tool_calls]}")
                return {"tool_calls": tool_calls}

            # 纯文本回复
            content = msg.get("content", "")
            log.info(f"← AI 回复: {content[:60]}...")
            return {"content": content}

    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="AI API 请求超时")
    except Exception as e:
        log.exception("AI 请求异常")
        raise HTTPException(status_code=500, detail=str(e))