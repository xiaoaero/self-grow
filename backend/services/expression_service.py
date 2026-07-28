"""
Self Grow — 表达训练业务逻辑层

处理出题和评分核心逻辑，调用 AI 客户端。
"""

import json
import logging
import re

from config import AI_BASE_URL, AI_API_KEY, AI_MODEL
from prompts.expression import (
    EXPRESSION_QUESTION_SYSTEM_PROMPT,
    EXPRESSION_EVALUATE_SYSTEM_PROMPT,
    EXPRESSION_QUESTION_TOOLS,
    EXPRESSION_HINTS_SYSTEM_PROMPT,
)
from db.expressions import (
    get_existing_questions,
    create_question,
    get_question,
    create_answer,
    update_answer_text,
    update_answer_evaluation,
    get_max_attempt,
)

log = logging.getLogger(__name__)

# 题型映射
QUESTION_TYPES = {
    "hot_opinion": {"name": "热门事件观点", "desc": "针对社会热点事件发表观点"},
    "emotional": {"name": "情感表达", "desc": "表达情感、感受和内心想法"},
    "life_reflection": {"name": "生活感悟", "desc": "对生活经历和观察的思考和感悟"},
    "career": {"name": "职场沟通", "desc": "职场场景下的表达和沟通"},
}


async def generate_question(types: list[str]) -> dict:
    """
    生成题目 + 3 条思考提示。

    调用 LLM（Tool Use 模式），先查历史题目防重复，再生成新题。
    当前热搜搜索工具预留，暂不实现。
    """
    if not AI_API_KEY:
        return _fallback_question(types)

    # 查询已有题目（用于查重）
    existing = get_existing_questions(types=types if types else None, limit=30)
    existing_text = "\n".join(
        f"- [{e['question_type']}] {e['question']}" for e in existing
    ) if existing else "（暂无历史题目）"

    type_names = ", ".join(QUESTION_TYPES.get(t, {}).get("name", t) for t in types) if types else "全部类型"

    user_message = f"""用户选择的题型：{type_names}

已有题目列表（请确保新题不与以下重复）：
{existing_text}

请生成一道符合所选题型、不重复的题目，并附上 3 条思考提示。"""

    # 调用 LLM
    try:
        result = await _call_llm_with_tools(
            system_prompt=EXPRESSION_QUESTION_SYSTEM_PROMPT,
            user_message=user_message,
            tools=EXPRESSION_QUESTION_TOOLS,
        )
        # 从 result 中解析出 question 和 hints
        question_data = _parse_question_result(result)
        if not question_data:
            return _fallback_question(types)

        # 保存到数据库
        qid = create_question(
            question=question_data["question"],
            question_type=types[0] if types else "hot_opinion",
            hints=json.dumps(question_data["hints"], ensure_ascii=False),
            source=question_data.get("source", ""),
        )

        return {
            "id": qid,
            "question": question_data["question"],
            "question_type": types[0] if types else "hot_opinion",
            "hints": question_data["hints"],
        }
    except Exception as e:
        log.exception(f"出题失败: {e}")
        return _fallback_question(types)


async def evaluate_answer(question_id: int, answer_id: int, answer_text: str, filler_words: dict = None) -> dict:
    """
    对用户的回答进行 AI 评分，并保存到数据库。
    """
    # 获取题目信息
    question = get_question(question_id)
    if not question:
        raise ValueError(f"题目不存在: {question_id}")

    filler_info = ""
    if filler_words:
        items = sorted(filler_words.items(), key=lambda x: -x[1])
        filler_info = "\n填充词统计：" + "，".join(f"「{k}」出现 {v} 次" for k, v in items if v > 0)

    user_message = f"""题目：{question['question']}

用户回答：{answer_text}{filler_info}

请对用户的表达进行评分，给出优点和改进建议。"""

    try:
        result = await _call_llm_direct(
            system_prompt=EXPRESSION_EVALUATE_SYSTEM_PROMPT,
            user_message=user_message,
            temperature=0.5,
        )
        evaluation = _parse_evaluation_result(result)
    except Exception as e:
        log.exception(f"评分失败: {e}")
        evaluation = _fallback_evaluation()

    # 保存到数据库
    update_answer_text(answer_id, answer_text, filler_words)
    update_answer_evaluation(
        answer_id,
        scores=evaluation["scores"],
        strengths=evaluation["strengths"],
        improvements=evaluation["improvements"],
        suggestion=evaluation["suggestion"],
    )

    return evaluation


async def generate_hints(question_id: int, question: str, question_type: str) -> list:
    """
    异步生成提示（表达方向 + 例子），不阻塞答题流程。
    调用 LLM 纯文本模式，解析 JSON 返回。
    """
    if not AI_API_KEY:
        return _fallback_hints()

    user_message = f"""题目（{question_type}）：{question}

请为这道表达训练题目生成 3 条思考提示，每条包含表达方向和具体例子。"""

    try:
        result = await _call_llm_direct(
            system_prompt=EXPRESSION_HINTS_SYSTEM_PROMPT,
            user_message=user_message,
            temperature=0.7,
        )
        hints = _parse_hints_result(result)
    except Exception as e:
        log.exception(f"生成提示失败: {e}")
        hints = _fallback_hints()

    # 保存到数据库
    if hints:
        from db.expressions import update_question_hints
        update_question_hints(question_id, json.dumps(hints, ensure_ascii=False))

    return hints


async def _call_llm_with_tools(system_prompt: str, user_message: str, tools: list) -> dict:
    """调用 LLM（支持 Tool Use 模式）"""
    import httpx

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

    max_rounds = 5  # 防止无限循环
    current_round = 0

    async with httpx.AsyncClient(timeout=60.0) as client:
        while current_round < max_rounds:
            current_round += 1
            payload = {
                "model": AI_MODEL,
                "messages": messages,
                "tools": tools,
                "tool_choice": "auto",
                "temperature": 0.8,
                "max_tokens": 4096,
            }

            log.info(f"→ 出题 AI 请求 ({current_round})")
            resp = await client.post(
                f"{AI_BASE_URL}/chat/completions",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {AI_API_KEY}",
                },
                json=payload,
            )

            if resp.status_code != 200:
                log.error(f"← AI 错误 {resp.status_code}: {resp.text[:300]}")
                raise RuntimeError(f"AI API 错误 {resp.status_code}")

            data = resp.json()
            msg = data["choices"][0]["message"]

            # 处理工具调用：保存完整的 assistant 消息（含 tool_calls）
            if "tool_calls" in msg and msg["tool_calls"]:
                assistant_msg = {
                    "role": "assistant",
                    "content": msg.get("content") or "",
                    "tool_calls": [
                        {
                            "id": tc["id"],
                            "type": "function",
                            "function": {
                                "name": tc["function"]["name"],
                                "arguments": tc["function"]["arguments"],
                            },
                        }
                        for tc in msg["tool_calls"]
                    ],
                }
                messages.append(assistant_msg)

                for tc in msg["tool_calls"]:
                    name = tc["function"]["name"]
                    try:
                        args = json.loads(tc["function"]["arguments"])
                    except json.JSONDecodeError:
                        args = {}

                    if name == "query_history_questions":
                        # 查询历史题目
                        q_types = args.get("types", [])
                        limit = args.get("limit", 20)
                        existing = get_existing_questions(types=q_types if q_types else None, limit=limit)
                        result_text = json.dumps(existing, ensure_ascii=False)
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc["id"],
                            "content": result_text,
                        })
                    elif name == "search_hot_events":
                        # 预留：联网搜索，暂不可用
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc["id"],
                            "content": "【该工具暂不可用】联网搜索功能尚未接入，请基于已有知识生成题目。",
                        })
                    else:
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc["id"],
                            "content": "未知工具",
                        })
            else:
                # 没有工具调用，返回最终结果
                return {"content": msg.get("content") or ""}

    return {"content": ""}


async def _call_llm_direct(system_prompt: str, user_message: str, temperature: float = 0.5) -> str:
    """调用 LLM（纯文本模式，无工具调用）"""
    import httpx

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

    async with httpx.AsyncClient(timeout=60.0) as client:
        payload = {
            "model": AI_MODEL,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": 4096,
        }

        log.info("→ 评分 AI 请求")
        resp = await client.post(
            f"{AI_BASE_URL}/chat/completions",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {AI_API_KEY}",
            },
            json=payload,
        )

        if resp.status_code != 200:
            log.error(f"← AI 错误 {resp.status_code}: {resp.text[:300]}")
            raise RuntimeError(f"AI API 错误 {resp.status_code}")

        data = resp.json()
        return data["choices"][0]["message"]["content"]


def _parse_question_result(result: dict) -> dict:
    """从 LLM 返回内容中解析题目和提示"""
    content = result.get("content", "")

    # 提取 JSON 块（如果 LLM 直接返回 JSON）
    json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', content, re.DOTALL)
    if json_match:
        try:
            data = json.loads(json_match.group(1))
            if "question" in data:
                return data
        except json.JSONDecodeError:
            pass

    # 尝试全文 JSON 解析
    try:
        data = json.loads(content)
        if "question" in data:
            return data
    except json.JSONDecodeError:
        pass

    # 按行解析：题目 + 提示1/2/3
    lines = content.strip().split("\n")
    question = ""
    hints = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        # 匹配题目行
        q_match = re.match(r'^题目[：:]\s*(.*)', stripped)
        if q_match:
            question = q_match.group(1).strip()
            continue

        # 匹配提示行：提示1/提示2/提示3 或 提示一/提示二/提示三
        hint_match = re.match(r'^提示[1-3一二三][.、．:：\s]*(.*)', stripped)
        if hint_match:
            hint_text = hint_match.group(1).strip()
            # 尝试按 —— 或 — 或 : 分割标题和内容
            parts = re.split(r'[—－:：]', hint_text, maxsplit=1)
            if len(parts) >= 2 and len(parts[0]) < 20:
                title = parts[0].strip()
                hint_content = parts[1].strip()
            else:
                title = f"思考方向 {len(hints) + 1}"
                hint_content = hint_text
            hints.append({"title": title, "content": hint_content})
            continue

        # 匹配数字序号提示：1. 2. 3.
        num_match = re.match(r'^(\d+)[.、．]\s*(.*)', stripped)
        if num_match:
            hint_text = num_match.group(2).strip()
            parts = re.split(r'[—－:：]', hint_text, maxsplit=1)
            if len(parts) >= 2 and len(parts[0]) < 20:
                title = parts[0].strip()
                hint_content = parts[1].strip()
            else:
                title = f"思考方向 {int(num_match.group(1))}"
                hint_content = hint_text
            hints.append({"title": title, "content": hint_content})

    # 如果还没找到题目，尝试其他策略
    if not question:
        # 找双引号/书名号包裹的长句子
        for line in lines:
            q_matches = re.findall(r'[""「]([^""」]{10,})[""」]', line)
            if q_matches:
                question = q_matches[0]
                break

    # 找有问号的句子
    if not question:
        for line in lines:
            if '？' in line or '?' in line:
                question = line.strip()
                break

    # 取第一个非空行（去掉对话式开头）
    if not question:
        for line in lines:
            stripped = line.strip()
            if stripped and not any(
                stripped.startswith(p) for p in ['好的', '好的，', '好的!', '好的！', '```', '#', '根据', '基于']
            ):
                question = stripped
                break

    if not question:
        question = "请谈谈你对某个社会热点的看法"

    if not hints:
        hints = [
            {"title": "多角度思考", "content": "尝试从不同立场和角度分析这个问题"},
            {"title": "结合实际", "content": "结合你自身的经历或见闻来佐证观点"},
            {"title": "辩证总结", "content": "最后给出你的综合判断或结论"},
        ]

    return {
        "question": question,
        "hints": hints,
        "source": "",
    }


def _parse_evaluation_result(content: str) -> dict:
    """从 LLM 返回内容中解析评分结果"""
    # 提取 JSON 块
    json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', content, re.DOTALL)
    if json_match:
        try:
            data = json.loads(json_match.group(1))
            return _validate_evaluation(data)
        except json.JSONDecodeError:
            pass

    # 尝试全文解析
    try:
        data = json.loads(content)
        return _validate_evaluation(data)
    except json.JSONDecodeError:
        pass

    return _fallback_evaluation()


def _validate_evaluation(data: dict) -> dict:
    """校验并补全评分数据"""
    scores = data.get("scores", {})
    return {
        "scores": {
            "total": max(0, min(100, scores.get("total", 70))),
            "fluency": max(0, min(100, scores.get("fluency", 70))),
            "logic": max(0, min(100, scores.get("logic", 70))),
            "content": max(0, min(100, scores.get("content", 70))),
            "language": max(0, min(100, scores.get("language", 70))),
        },
        "strengths": data.get("strengths", ["表达清晰，能够完整回答问题"]),
        "improvements": data.get("improvements", ["可以尝试增加更多具体例子来支撑观点"]),
        "suggestion": data.get("suggestion", "建议多练习结构化表达，使用「首先、其次、最后」等连接词让逻辑更清晰。"),
    }


def _fallback_question(types: list = None) -> dict:
    """降级出题：当 AI 不可用时使用预设题目"""
    fallback_questions = {
        "hot_opinion": "你认为人工智能技术发展对普通人的日常生活带来了哪些积极和消极的影响？请结合具体例子说明。",
        "emotional": "回想一个让你感到特别温暖或感动的时刻，请描述当时的情景和你的感受。",
        "life_reflection": "如果让你给 10 年前的自己一个建议，你会说什么？为什么？",
        "career": "在团队合作中，当你和同事意见不一致时，你通常会如何处理？请分享一个具体经历。",
    }

    q_type = types[0] if types else "hot_opinion"
    question = fallback_questions.get(q_type, fallback_questions["hot_opinion"])

    qid = create_question(
        question=question,
        question_type=q_type,
        hints=json.dumps([
            {"title": "多角度思考", "content": "尝试从不同立场和角度分析这个问题"},
            {"title": "结合实际", "content": "结合你自身的经历或见闻来佐证观点"},
            {"title": "辩证总结", "content": "最后给出你的综合判断或结论"},
        ], ensure_ascii=False),
    )

    return {
        "id": qid,
        "question": question,
        "question_type": q_type,
        "hints": [
            {"title": "多角度思考", "content": "尝试从不同立场和角度分析这个问题"},
            {"title": "结合实际", "content": "结合你自身的经历或见闻来佐证观点"},
            {"title": "辩证总结", "content": "最后给出你的综合判断或结论"},
        ],
    }


def _fallback_evaluation() -> dict:
    """降级评分：当 AI 不可用时返回默认评分"""
    return {
        "scores": {"total": 70, "fluency": 70, "logic": 70, "content": 70, "language": 70},
        "strengths": ["表达清晰，能够完整回答问题"],
        "improvements": ["可以尝试增加更多具体例子来支撑观点"],
        "suggestion": '建议多练习结构化表达，使用「首先、其次、最后」等连接词让逻辑更清晰。',
    }


def _fallback_hints() -> list:
    """降级提示：当 AI 不可用时返回默认提示"""
    return [
        {
            "title": "提示一",
            "direction": "尝试从不同立场和角度分析这个问题",
            "examples": ["想想看，不同身份的人（如当事人、旁观者、管理者）会怎么看这个问题？", "你可以结合你自身的经历或见闻来佐证观点"],
        },
        {
            "title": "提示二",
            "direction": "结合具体案例来支撑你的观点",
            "examples": ["回忆一下你最近看到或听到的相关新闻或故事", "如果是你亲身经历过的场景，可以描述当时的感受"],
        },
        {
            "title": "提示三",
            "direction": "尝试给出你的综合判断，而不仅仅是罗列观点",
            "examples": ["在分析完各方面后，你最终支持哪个立场？为什么？", "如果让你给出一个具体的建议或行动方案，会是什么？"],
        },
    ]


def _parse_hints_result(content: str) -> list:
    """从 LLM 返回内容中解析提示结果"""
    # 提取 JSON 块
    json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', content, re.DOTALL)
    if json_match:
        try:
            data = json.loads(json_match.group(1))
            return _validate_hints(data)
        except json.JSONDecodeError:
            pass

    # 尝试全文 JSON 解析
    try:
        data = json.loads(content)
        return _validate_hints(data)
    except json.JSONDecodeError:
        pass

    return _fallback_hints()


def _validate_hints(data: dict) -> list:
    """校验并补全提示数据"""
    raw_hints = data.get("hints", [])
    if not raw_hints or len(raw_hints) < 3:
        return _fallback_hints()

    result = []
    for i, h in enumerate(raw_hints):
        title = h.get("title", "") or f"提示{'一二三'[i] if i < 3 else i + 1}"

        # 兼容两种格式：新格式 direction + examples，旧格式 content
        direction = h.get("direction", "") or h.get("content", "")
        examples = h.get("examples", [])

        # 如果内容是旧格式，尝试从 content 中提取例子
        if not examples and h.get("content"):
            # 检查 content 是否包含"比如"、"例如"等引导词
            content = h.get("content", "")
            parts = re.split(r'[比如例如]', content, maxsplit=1)
            if len(parts) >= 2:
                direction = parts[0].strip()
                examples = [p.strip() for p in re.split(r'[；;]', parts[1]) if p.strip()]
                # 补上"比如"前缀
                examples = [f"比如{ex}" if not ex.startswith('比如') else ex for ex in examples]
            else:
                direction = content

        if not examples:
            examples = ["可以结合你的经历来思考这个角度"]

        result.append({
            "title": title,
            "direction": direction,
            "examples": examples,
        })
    return result