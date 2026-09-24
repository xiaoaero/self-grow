"""
Self Grow — 用户输入长度上限（集中定义）

为什么需要这个文件
==================
下面这些输入最终都会被拼进 prompt 送给 LLM，而**原先没有任何一处做长度限制**：

    协调 Agent 的用户消息 / 技能树 AI 的编辑指令 / 行动解析的对话历史 /
    表达训练的作答正文 / 语音识别的音频流

用户可以粘一整篇长文进来，后果是：
  · token 成本随输入长度线性上涨，没有天花板
  · 单次请求可能跑几分钟，一直占着 SSE 长连接与会话锁
  · 超出模型上下文窗口时由模型侧报错，用户看到的是一句莫名其妙的失败，
    而不是「你的输入太长了，请精简」

上限怎么定的
============
原则是「正常使用碰不到，但能挡住滥用」。本项目的实际用法是记录行动、
习惯、反思与表达训练 —— 几百字已经算长文本，所以几千字的上限对真实用户
相当于不存在，却能立刻挡住「粘贴一整本书」这种行为。

为什么不一律用 pydantic 的 max_length
====================================
能用模型字段的地方就用了（`Field(max_length=...)` 会返回 422，
并由 `main.py` 里那个 422 handler 记下字段级原因，排查方便）。
但项目里有几个端点的入参是裸 `dict`（`req: dict` / `data: dict`），
pydantic 管不到它们，只能在路由层显式检查 —— 这里提供共用常量与辅助函数。
"""

from fastapi import HTTPException

# ── 上限 ──
# 单条用户消息（协调 Agent / 技能树 AI / 行动解析）
MAX_USER_MESSAGE = 4000
# 行动解析：对话历史的条数与总字符数
# （历史上限是为了防「一直聊下去」，总字符上限是防「每条都很长」）
MAX_HISTORY_MESSAGES = 40
MAX_HISTORY_TOTAL_CHARS = 24000
# 表达训练：作答正文
MAX_ANSWER_TEXT = 8000
# 语音识别：单次会话累计音频上限（20MB）
# 按 16kHz / 16bit / 单声道 PCM 算，约合 10 分钟
MAX_ASR_AUDIO_BYTES = 20 * 1024 * 1024


def check_length(text, limit: int, what: str) -> str:
    """长度超限就抛 400（文案带上实际长度），否则原样返回字符串

    用于入参是裸 dict、pydantic 管不到的端点。

    文案里给出**实际字符数**是有意的：用户看到「8123 字符，上限 8000」
    就知道只超了一点、删两句话就行；只说「太长了」会让人完全不知道尺度。
    """
    if text is None:
        return ""
    text = str(text)
    if len(text) > limit:
        raise HTTPException(
            status_code=400,
            detail=f"{what}过长（{len(text)} 字符，上限 {limit}），请精简后再提交",
        )
    return text


def check_history(messages: list) -> list:
    """校验行动解析的对话历史（条数 + 总字符数），返回原列表

    两个维度都要看：只限条数挡不住「每条几万字」，
    只限总字符数又会让「几千条短消息」钻过去。
    """
    if not isinstance(messages, list):
        raise HTTPException(status_code=400, detail="messages 必须是数组")

    if len(messages) > MAX_HISTORY_MESSAGES:
        raise HTTPException(
            status_code=400,
            detail=f"对话历史过长（{len(messages)} 条，上限 {MAX_HISTORY_MESSAGES} 条）",
        )

    total = 0
    for m in messages:
        if isinstance(m, dict):
            total += len(str(m.get("content") or ""))
    if total > MAX_HISTORY_TOTAL_CHARS:
        raise HTTPException(
            status_code=400,
            detail=f"对话历史内容过长（{total} 字符，上限 {MAX_HISTORY_TOTAL_CHARS}），请开启新会话",
        )
    return messages
