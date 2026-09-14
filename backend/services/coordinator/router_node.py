"""
Self Grow — 主图路由节点（LLM意图识别）

全部使用LLM语义判断路由，取消正则+关键词路由。
"""

import json
import logging
import re
from services.llm import get_llm
from services.coordinator.state import CoordinatorState, SubgraphTask
from prompts.coordinator import COORDINATOR_ROUTER_SYSTEM_PROMPT, ROUTING_DECISION_SCHEMA

log = logging.getLogger(__name__)

# 预编译正则：匹配 JSON 对象，用于从 LLM 输出中提取
_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


def _parse_routing_json(content: str) -> dict | None:
    """从 LLM 输出中健壮地提取 JSON 路由决策

    LLM 有时在 JSON 前后附加解释文本，或用 markdown 代码块包裹。
    依次尝试：直接解析 → 提取 ```json 块 → 正则匹配最外层 {}。
    """
    # 1. 去除 markdown 代码块
    cleaned = content.strip()
    if cleaned.startswith("```"):
        # 去掉首行（```json 或 ```）
        first_nl = cleaned.find("\n")
        cleaned = cleaned[first_nl + 1:] if first_nl != -1 else cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    cleaned = cleaned.strip()

    # 2. 直接尝试解析
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # 3. 正则提取最外层 JSON 对象
    m = _JSON_OBJECT_RE.search(cleaned)
    if m:
        try:
            return json.loads(m.group())
        except json.JSONDecodeError:
            pass

    return None


async def router_node(state: CoordinatorState) -> dict:
    """LLM意图识别 + 动态生成子Agent定制指令

    分析用户输入和对话历史，决定需要调度哪些功能域。
    """
    user_message = state["user_message"]
    records = state.get("records", [])

    # 构建主 agent 上下文（近 5 条记录的「用户说的话 + 主 agent 总结」）
    history_text = ""
    if records:
        history_lines = []
        for r in records:
            history_lines.append(f"用户：{r.get('user_message', '')}")
            history_lines.append(f"助手总结：{r.get('summary', '')}")
        history_text = "\n".join(history_lines)

    # 构建提示词
    prompt = f"""用户消息：{user_message}

"""
    if history_text:
        prompt += f"""此前记录（近 {len(records)} 条，用于判断本次是否延续之前未完成的任务）：
{history_text}

"""
    prompt += """请分析用户意图，决定需要调度哪些功能域。返回JSON格式的路由决策。"""

    # 调用LLM
    llm = get_llm(temperature=0.1, user_id=state.get("user_id"))
    try:
        response = await llm.ainvoke([
            {"role": "system", "content": COORDINATOR_ROUTER_SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ])

        content = response.content.strip()
        routing_decision = _parse_routing_json(content)

        if not routing_decision:
            log.warning(f"无法从 LLM 输出解析路由 JSON：{content[:200]}")
            return {"pending_tasks": []}

        # 转换为SubgraphTask列表
        pending_tasks = []
        for item in routing_decision.get("domains", []):
            domain = item.get("domain", "")
            if not domain:
                continue
            pending_tasks.append(SubgraphTask(
                domain=domain,
                reason=item.get("reason", ""),
                instruction=item.get("instruction", ""),
            ))

        log.info(f"路由决策：{[t['domain'] for t in pending_tasks]}")
        return {"pending_tasks": pending_tasks}

    except Exception as e:
        log.error(f"路由节点执行失败：{e}")
        return {"pending_tasks": []}
