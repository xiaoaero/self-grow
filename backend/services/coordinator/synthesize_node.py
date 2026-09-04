"""
Self Grow — 主图结果整合节点

整合各子图执行结果，使用 LLM 生成自然语言回复。
"""

import logging
from services.coordinator.state import CoordinatorState
from services.coordinator.llm import get_llm

log = logging.getLogger(__name__)

_SYNTHESIZE_SYSTEM_PROMPT = """你是「Self Grow 个人成长系统」的结果整合Agent。

你的职责是将各子Agent的执行结果整合为一段自然、友好的用户回复。

## 规则
1. 用简洁的中文回复，语气亲切
2. 将多个操作结果合并为一段连贯的回复，不要逐条罗列
3. 如果有反问（interrupt），优先呈现反问内容，附带已执行的结果
4. 如果没有执行结果，根据用户意图生成合适的引导性回复
5. 不要编造未执行的操作
6. 鼓励用户，给予正向反馈

## 回复长度
- 单个操作：1-2 句话
- 多个操作：3-5 句话，适当分段
- 反问：简洁清晰地提出问题"""


async def synthesize_node(state: CoordinatorState) -> dict:
    """整合各子图执行结果，使用 LLM 生成自然语言回复"""
    results = state.get("results", [])
    interrupts = state.get("interrupts", [])
    pending_tasks = state.get("pending_tasks", [])
    user_message = state.get("user_message", "")

    # 构建给 LLM 的上下文
    context_parts = [f"用户原始消息：{user_message}"]

    if interrupts:
        interrupt_texts = []
        for interrupt in interrupts:
            q = interrupt.get("question", "请补充信息")
            opts = interrupt.get("options", [])
            if opts:
                opts_text = " / ".join(str(o) for o in opts)
                interrupt_texts.append(f"反问：{q}（选项：{opts_text}）")
            else:
                interrupt_texts.append(f"反问：{q}")
        context_parts.append("反问事件：\n" + "\n".join(interrupt_texts))

    if results:
        result_texts = []
        for r in results:
            msg = r.get("message", "")
            tool_name = r.get("tool_name", "")
            tool_result = r.get("tool_result", {})
            if msg:
                result_texts.append(f"[{r.get('domain', '?')}] {msg}")
            elif tool_name:
                result_texts.append(f"[{r.get('domain', '?')}] 工具 {tool_name} 执行完成")
        if result_texts:
            context_parts.append("各子Agent执行结果：\n" + "\n".join(result_texts))

    if not results and not interrupts:
        if pending_tasks:
            context_parts.append("（有路由任务但无执行结果，可能子Agent遇到了问题）")
        else:
            context_parts.append("（未识别到具体任务）")

    prompt = "\n\n".join(context_parts)

    # 调用 LLM 生成回复
    try:
        llm = get_llm(temperature=0.3, user_id=state.get("user_id"))
        response = await llm.ainvoke([
            {"role": "system", "content": _SYNTHESIZE_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ])
        final_reply = response.content.strip()
    except Exception as e:
        log.error(f"LLM 整合回复失败，降级为规则拼接：{e}")
        # 降级：简单拼接
        parts = []
        if interrupts:
            for i in interrupts:
                parts.append(f"🤔 {i.get('question', '请补充信息')}")
        if results:
            for r in results:
                msg = r.get("message", "")
                if msg:
                    parts.append(f"✅ {msg}")
        if not parts:
            parts.append("抱歉，我没有理解你的意思。请告诉我你想做什么？")
        final_reply = "\n".join(parts)

    log.info(f"生成回复：{final_reply[:100]}...")
    return {"final_reply": final_reply}
