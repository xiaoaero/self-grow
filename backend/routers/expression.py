"""
Self Grow — 表达训练 API 路由
"""

import asyncio
import json
import logging

from fastapi import APIRouter, HTTPException, Depends, Query, WebSocket, WebSocketDisconnect
from datetime import datetime

from db.expressions import (
    get_question,
    get_answer,
    get_answers_by_question,
    get_user_history,
    get_user_stats,
    create_answer,
    create_question,
    update_answer_text,
    get_max_attempt,
    get_question_history_list,
    get_recent_answers,
)
from services.expression_service import generate_question, evaluate_answer, generate_hints, beautify_question
from services.asr_service import ASRConnection
from routers.deps import get_current_user
from services.sse import (
    stream_events, sse_response, immediate_response, use_emitter, emit_stage,
)

log = logging.getLogger(__name__)

router = APIRouter()


# ================================================================
# 表达训练的 AI 端点都是**流式（SSE）**的
#
# 这几个端点的产出是 **JSON**（题目+提示 / 四维评分+建议），所以**不做逐 token 推送**
# —— 把残缺 JSON 逐字喂给前端，等于逼前端做增量 JSON 解析，是负优化。
# 推的是**阶段事件**（正在连接模型 / 正在查询历史题目 / 正在解析…）：
#   1. 出题、评分都是单次 LLM 调用，30~60s，比协调 Agent 更容易让用户以为"卡住了"
#   2. `stream_events` 的心跳会把中间代理的空闲计时器顶掉，防止长请求被掐断
#
# `done` 事件里的字段与改造前的 JSON 返回**逐字相同**，前端读流拿 done 即可。
# ================================================================


@router.post("/api/expression/generate")
async def api_generate_question(
    req: dict,
    user=Depends(get_current_user),
):
    """生成表达训练题目 + 3 条思考提示（流式）。支持自定义题目（不走 AI）"""
    # 自定义题目：直接保存到数据库，不调用 AI —— 无需流式，发个 done 即可
    custom_question = req.get("custom_question", "").strip()
    if custom_question:
        question_type = req.get("custom_type", "custom")
        qid = create_question(
            question=custom_question,
            question_type=question_type,
            hints=None,
            source="custom",
        )
        return await immediate_response({
            "id": qid,
            "question": custom_question,
            "question_type": question_type,
            "hints": [],
        })

    types = req.get("types", ["hot_opinion", "emotional", "life_reflection", "career"])
    if not types:
        types = ["hot_opinion", "emotional", "life_reflection", "career"]

    async def runner(emit):
        with use_emitter(emit):
            await emit_stage("generate", "正在构思题目…")
            result = await generate_question(types, user_id=user["id"])
        await emit({"type": "done", **(result or {})})

    return sse_response(stream_events(runner))


@router.post("/api/expression/answer")
def api_create_answer(
    req: dict,
    user=Depends(get_current_user),
):
    """创建一条新的回答记录（用户点击「开始回答」时调用）"""
    question_id = req.get("question_id")
    if not question_id:
        raise HTTPException(status_code=400, detail="缺少 question_id")

    # 验证题目存在
    question = get_question(question_id)
    if not question:
        raise HTTPException(status_code=404, detail="题目不存在")

    # 计算 attempt
    max_attempt = get_max_attempt(question_id, user["name"])
    attempt = max_attempt + 1

    answer_id = create_answer(user["name"], question_id, attempt)
    return {"answer_id": answer_id, "attempt": attempt}


@router.post("/api/expression/generate-hints")
async def api_generate_hints(
    req: dict,
    user=Depends(get_current_user),
):
    """异步生成提示（表达方向 + 例子），不阻塞答题。流式（阶段事件）。

    校验放在流外：这样 400/404 仍是正常的 HTTP 状态码，
    不会变成"200 + 一个 error 事件"（前端就没法用状态码区分错误类型了）。
    """
    question_id = req.get("question_id")
    if not question_id:
        raise HTTPException(status_code=400, detail="缺少 question_id")

    question = get_question(question_id)
    if not question:
        raise HTTPException(status_code=404, detail="题目不存在")

    # 先检查是否已有 hints 缓存（必须是新格式：包含 direction 和 examples）
    hints = _parse_json_field(question.get("hints"))
    if hints and len(hints) >= 3 and hints[0].get("direction"):
        return await immediate_response({"hints": hints})

    async def runner(emit):
        with use_emitter(emit):
            await emit_stage("hints", "正在生成思考提示…")
            result = await generate_hints(
                question_id=question_id,
                question=question["question"],
                question_type=question["question_type"],
                user_id=user["id"],
            )
        await emit({"type": "done", "hints": result})

    return sse_response(stream_events(runner))


@router.post("/api/expression/answer/{answer_id}/text")
def api_update_answer_text(
    answer_id: int,
    data: dict,
    user=Depends(get_current_user),
):
    """更新回答文本（用户点击「完成回答」时调用）"""
    answer = get_answer(answer_id)
    if not answer:
        raise HTTPException(status_code=404, detail="回答记录不存在")

    update_answer_text(
        answer_id,
        answer=data.get("answer", ""),
        filler_words=data.get("filler_words"),
    )
    return {"status": "ok"}


@router.post("/api/expression/evaluate/{answer_id}")
async def api_evaluate_answer(
    answer_id: int,
    user=Depends(get_current_user),
):
    """AI 评分 + 建议（用户点击「AI 分析」时调用）。流式（阶段事件）"""
    answer = get_answer(answer_id)
    if not answer:
        raise HTTPException(status_code=404, detail="回答记录不存在")

    if not answer.get("answer"):
        raise HTTPException(status_code=400, detail="回答内容为空，请先完成回答")

    # 如果已经评估过，直接返回缓存结果
    if answer.get("status") == "evaluated" and answer.get("score_total") is not None:
        return await immediate_response({
            "scores": {
                "total": answer["score_total"],
                "fluency": answer["score_fluency"],
                "logic": answer["score_logic"],
                "content": answer["score_content"],
                "language": answer["score_language"],
            },
            "strengths": _parse_json_field(answer.get("strengths")),
            "improvements": _parse_json_field(answer.get("improvements")),
            "suggestion": answer.get("suggestion", ""),
        })

    # 填充词统计
    filler_words = _parse_json_field(answer.get("filler_words")) or {}

    async def runner(emit):
        with use_emitter(emit):
            await emit_stage("evaluate", "正在分析你的回答…")
            result = await evaluate_answer(
                question_id=answer["question_id"],
                answer_id=answer_id,
                answer_text=answer["answer"],
                filler_words=filler_words,
                user_id=user["id"],
            )
        await emit({"type": "done", **(result or {})})

    return sse_response(stream_events(runner))


@router.get("/api/expression/stats")
def api_expression_stats(user=Depends(get_current_user)):
    """获取用户总训练统计数据"""
    return get_user_stats(user["name"])


@router.get("/api/expression/history")
def api_expression_history(
    limit: int = Query(default=20, le=100),
    user=Depends(get_current_user),
):
    """获取用户最近回答记录（按时间倒序）"""
    records = get_user_history(user["name"], limit=limit)

    result = []
    for r in records:
        result.append({
            "id": r["id"],
            "question_id": r["question_id"],
            "question": r["question"],
            "question_type": r["question_type"],
            "answer_preview": (r["answer"] or "")[:100] + ("..." if r["answer"] and len(r["answer"]) > 100 else ""),
            "answer_full": r["answer"],
            "score_total": r["score_total"],
            "status": r["status"],
            "attempt": r["attempt"],
            "created_at": r["created_at"],
        })

    return {"records": result}


@router.get("/api/expression/history/questions")
def api_expression_history_questions(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=50),
    question_type: str = Query(default=None, description="题型筛选"),
    time_start: str = Query(default=None, description="开始日期 YYYY-MM-DD"),
    time_end: str = Query(default=None, description="结束日期 YYYY-MM-DD"),
    answer_count: str = Query(default=None, description="回答次数: 1,2,3,gt3"),
    user=Depends(get_current_user),
):
    """获取按题目分组的分页历史列表（含筛选）"""
    result = get_question_history_list(
        user_id=user["name"],
        question_type=question_type,
        time_start=time_start,
        time_end=time_end,
        answer_count=answer_count,
        page=page,
        page_size=page_size,
    )
    return result


@router.get("/api/expression/history/questions/{question_id}/answers")
def api_expression_question_answers(
    question_id: int,
    limit: int = Query(default=5, ge=1, le=20),
    user=Depends(get_current_user),
):
    """获取某题目的最近回答记录"""
    answers = get_recent_answers(question_id, user_id=user["name"], limit=limit)

    # 重新排序为升序（按 attempt）
    answers.sort(key=lambda a: a["attempt"])

    result = []
    for a in answers:
        result.append({
            "id": a["id"],
            "attempt": a["attempt"],
            "answer": a.get("answer", ""),
            "score_total": a.get("score_total"),
            "status": a.get("status", ""),
            "created_at": a["created_at"],
            "scores": {
                "fluency": a.get("score_fluency"),
                "logic": a.get("score_logic"),
                "content": a.get("score_content"),
                "language": a.get("score_language"),
            } if a.get("score_total") is not None else None,
            "strengths": _parse_json_field(a.get("strengths")),
            "improvements": _parse_json_field(a.get("improvements")),
            "suggestion": a.get("suggestion", ""),
        })

    return {"answers": result}


@router.get("/api/expression/question/{question_id}")
def api_get_question_detail(question_id: int, user=Depends(get_current_user)):
    """获取题目详情 + 该题下所有回答"""
    question = get_question(question_id)
    if not question:
        raise HTTPException(status_code=404, detail="题目不存在")

    answers = get_answers_by_question(question_id, user_id=user["name"])

    # 解析 hints
    hints = _parse_json_field(question.get("hints"))

    return {
        "id": question["id"],
        "question": question["question"],
        "question_type": question["question_type"],
        "hints": hints if hints else [],
        "source": question.get("source", ""),
        "created_at": question["created_at"],
        "answers": [_format_answer(a) for a in answers],
    }


@router.get("/api/expression/answer/{answer_id}")
def api_get_answer_detail(answer_id: int, user=Depends(get_current_user)):
    """获取单条回答详情"""
    answer = get_answer(answer_id)
    if not answer:
        raise HTTPException(status_code=404, detail="回答记录不存在")

    return _format_answer(answer)


@router.post("/api/expression/beautify")
async def api_beautify_question(
    req: dict,
    user=Depends(get_current_user),
):
    """AI 美化自定义问题"""
    text = (req.get("text") or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="输入内容不能为空")
    beautified = await beautify_question(text, user_id=user["id"])
    return {"beautified": beautified, "original": text}


# ================================================================
# 辅助函数
# ================================================================

def _format_answer(a: dict) -> dict:
    """格式化回答数据"""
    hints = _parse_json_field(a.get("hints"))
    return {
        "id": a["id"],
        "question_id": a["question_id"],
        "question": a.get("question", ""),
        "question_type": a.get("question_type", ""),
        "hints": hints if hints else [],
        "attempt": a["attempt"],
        "answer": a.get("answer", ""),
        "filler_words": _parse_json_field(a.get("filler_words")),
        "score_total": a.get("score_total"),
        "scores": {
            "fluency": a.get("score_fluency"),
            "logic": a.get("score_logic"),
            "content": a.get("score_content"),
            "language": a.get("score_language"),
        } if a.get("score_total") is not None else None,
        "strengths": _parse_json_field(a.get("strengths")),
        "improvements": _parse_json_field(a.get("improvements")),
        "suggestion": a.get("suggestion", ""),
        "status": a["status"],
        "created_at": a["created_at"],
    }


def _parse_json_field(value):
    """安全解析 JSON 字段"""
    if not value:
        return None
    if isinstance(value, (list, dict)):
        return value
    try:
        import json
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return value


# ================================================================
# WebSocket: 实时语音识别
# ================================================================


@router.websocket("/ws/asr")
async def websocket_asr(websocket: WebSocket):
    """
    实时语音识别 WebSocket 端点。

    浏览器 → PCM 音频分片 → 本端点 → DashScope paraformer-realtime-v2
    DashScope 识别结果 → 本端点 → JSON 文本 → 浏览器

    浏览器发送：binary PCM 数据（16kHz, 16-bit, mono）
    浏览器接收：{"type":"transcript","text":"...","is_end":true}
               {"type":"error","message":"..."}
    """
    await websocket.accept()
    log.info("WebSocket /ws/asr 连接已建立")

    # 从 query param 读取 user_id（如 /ws/asr?user_id=1），默认 1
    user_id_str = websocket.query_params.get("user_id")
    user_id = int(user_id_str) if user_id_str and user_id_str.isdigit() else 1

    asr = None
    receive_task = None
    send_task = None

    try:
        # 创建 ASR 连接（读取该用户启用的 ASR 模型配置）
        asr = ASRConnection(model="paraformer-realtime-v2", sample_rate=16000, user_id=user_id)
        asr.start()

        async def receive_audio():
            """接收浏览器音频分片，转发到 ASR"""
            try:
                while True:
                    data = await websocket.receive_bytes()
                    if asr and asr.is_running:
                        asr.send_audio(data)
            except WebSocketDisconnect:
                log.info("WebSocket 客户端断开连接")
            except Exception as e:
                log.warning(f"接收音频异常: {e}")

        async def send_results():
            """轮询 ASR 识别结果，推送到浏览器"""
            try:
                while True:
                    # 检查状态变化
                    state = asr.get_state() if asr else None
                    if state:
                        s_type = state.get("type")
                        if s_type == "error":
                            await websocket.send_json({
                                "type": "error",
                                "message": state.get("message", "ASR 识别错误"),
                            })
                            break
                        elif s_type == "close" or s_type == "complete":
                            break

                    # 检查识别结果
                    result = asr.get_result() if asr else None
                    if result:
                        await websocket.send_json({
                            "type": "transcript",
                            "text": result.get("text", ""),
                            "is_end": result.get("is_end", False),
                        })

                    await asyncio.sleep(0.05)  # 50ms 轮询间隔
            except asyncio.CancelledError:
                pass
            except Exception as e:
                log.warning(f"发送结果异常: {e}")

        # 并发运行收发任务
        receive_task = asyncio.create_task(receive_audio())
        send_task = asyncio.create_task(send_results())

        # 等待任意一个任务完成（客户端断开 或 ASR 出错）
        done, pending = await asyncio.wait(
            [receive_task, send_task],
            return_when=asyncio.FIRST_COMPLETED,
        )

        # 取消未完成的任务
        for task in pending:
            task.cancel()

    except WebSocketDisconnect:
        log.info("WebSocket /ws/asr 客户端断开连接")
    except Exception as e:
        log.error(f"WebSocket /ws/asr 异常: {e}")
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass
    finally:
        # 确保 ASR 被停止
        if asr:
            try:
                asr.stop()
            except Exception as e:
                log.warning(f"ASR stop 异常: {e}")
        log.info("WebSocket /ws/asr 连接已关闭")