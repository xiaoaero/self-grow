"""
Self Grow — AI 分析（懒触发 + 每天最多一次 + 结果全局共享）

产出三样，都在「AI 分析」视图里展示：
  1. 每日情报摘要（中文）：3~5 条要点 + 1 条趋势判断
  2. 本周新鲜榜 Top5 的**中文简介**（按仓库名缓存，只给新上榜的生成）
  3. 资讯热度榜：在**同一批 LLM 结果里**给国内/国际资讯打分，取前 5，转中文 + 标出处

⚠️ 触发方式**不是定时任务**：
   任何用户打开「AI 分析」→ 前端调 GET /api/aiconsult/analysis →
   后端发现"今天还没生成过"就**丢一个后台任务**去跑，先返回 {"status":"generating"}；
   生成完写库，之后**所有用户**都读同一份（每天最多一次）。

LLM 调用：**两个任务并发**（prompt / 输入都不同），用 asyncio.gather 一起跑：
   A. 总结类 → 每日情报摘要
   B. 翻译/打分类 → 仓库中文简介 + 资讯打分转中文
两路都失败时留空，页面不展示对应块（不阻塞其他内容）。
"""

import asyncio
import json
import re
from datetime import datetime

from langchain_core.messages import SystemMessage, HumanMessage

from config import log
from db.connection import get_conn, now_str, placeholders
from services.llm import get_llm
from services.aiconsult_service import (
    get_items, get_board, save_board, build_weekly_board,
    list_board_periods, NEWS_HOT_KEEP, _dstr, _today, _week_monday,
)

ANALYSIS_MAX_TOKENS = 4096          # 摘要任务：输出短，够用
# 翻译/打分类任务**不限制输出**：它一次要吐 N 个仓库简介 + 数十条资讯的中文标题、
# 摘要和打分，JSON 很大 —— 撞上限 → 输出被截断 → JSON 没闭合 → 解析失败 →
# 仓库简介和资讯热度榜**整块静默消失**（2026-09-24 实测）。
TRANSLATE_MAX_TOKENS = None
NEWS_INPUT_MAX = 24          # 喂给 LLM 的资讯条数上限（省 token）
DESC_TRUNC = 100             # 每条只截摘要前 100 字


# ================================================================
# 存储：当日产出（同时是「今天生成过没」的哨兵）
# ================================================================

def read_analysis(day):
    conn = get_conn()
    try:
        row = conn.execute(
            """SELECT payload, updated_at FROM aiconsult_analysis WHERE day=%s""", (day,)).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    try:
        data = json.loads(row["payload"])
    except Exception:
        return None
    data["updated_at"] = row["updated_at"]
    return data


def write_analysis(day, payload):
    ts = now_str()
    blob = json.dumps(payload, ensure_ascii=False)
    conn = get_conn()
    try:
        row = conn.execute("""SELECT id FROM aiconsult_analysis WHERE day=%s""", (day,)).fetchone()
        if row:
            conn.execute("""UPDATE aiconsult_analysis SET payload=%s, updated_at=%s WHERE id=%s""",
                         (blob, ts, row["id"]))
        else:
            conn.execute(
                """INSERT INTO aiconsult_analysis (day, payload, created_at, updated_at) VALUES (%s,%s,%s,%s)""",
                (day, blob, ts, ts))
        conn.commit()
    finally:
        conn.close()


# ================================================================
# 仓库中文简介缓存
# ================================================================

def get_repo_intros(repos):
    """批量读 {repo: intro_zh}"""
    repos = [r for r in (repos or []) if r]
    if not repos:
        return {}
    ph = placeholders(len(repos))
    conn = get_conn()
    try:
        rows = conn.execute(
            f"SELECT repo, intro_zh FROM aiconsult_repo_intro WHERE repo IN ({ph})", repos
        ).fetchall()
    finally:
        conn.close()
    return {r["repo"]: (r["intro_zh"] or "") for r in rows}


def save_repo_intros(pairs):
    """pairs: [(repo, intro_zh), ...]"""
    if not pairs:
        return
    ts = now_str()
    conn = get_conn()
    try:
        for repo, intro in pairs:
            row = conn.execute("""SELECT id FROM aiconsult_repo_intro WHERE repo=%s""", (repo,)).fetchone()
            if row:
                conn.execute("""UPDATE aiconsult_repo_intro SET intro_zh=%s, updated_at=%s WHERE id=%s""",
                             (intro, ts, row["id"]))
            else:
                conn.execute(
                    """INSERT INTO aiconsult_repo_intro (repo, intro_zh, updated_at) VALUES (%s,%s,%s)""",
                    (repo, intro, ts))
        conn.commit()
    finally:
        conn.close()


# ================================================================
# LLM 调用
# ================================================================

def _extract_json(text):
    """从模型输出里抠 JSON（容忍 ```json 包裹与前后废话）"""
    if not text:
        return None
    s = text.strip()
    m = re.search(r"```(?:json)?\s*(.+?)\s*```", s, re.DOTALL)
    if m:
        s = m.group(1).strip()
    for i, ch in enumerate(s):
        if ch in "{[":
            close = "}" if ch == "{" else "]"
            j = s.rfind(close)
            if j > i:
                try:
                    return json.loads(s[i:j + 1])
                except Exception:
                    pass
            break
    try:
        return json.loads(s)
    except Exception:
        return None


async def _call_llm_json(system, user, user_id=None, max_tokens=ANALYSIS_MAX_TOKENS, tag=""):
    # ⚠️ 必须显式传 user_id：`get_llm()` 内部是 `user_id or 1`，漏传会**静默用错人的模型配置**
    #    （项目统一约定，见 services/llm.py 的说明）
    llm = get_llm(temperature=0.3, max_tokens=max_tokens, user_id=user_id)
    resp = await llm.ainvoke([SystemMessage(content=system), HumanMessage(content=user)])
    text = resp.content or ""

    data = _extract_json(text)
    if data is None:
        # ⚠️ 这里以前**直接返回 None、什么都不记**，于是「翻译/打分那一半」整块消失
        #    而日志里只有一句 ✅ 生成成功 —— 用户看到的是"资讯热度榜一直空着"，
        #    查不到任何原因（2026-09-24）。
        #    最常见的成因是**输出被 max_tokens 截断**（JSON 没闭合，解析必然失败）。
        log.error(
            "❌ AI 分析·%s：模型输出不是合法 JSON（%d 字，%s）。前 300 字：%s",
            tag or "LLM", len(text),
            "疑似被 max_tokens 截断" if text and not text.rstrip().endswith(("}", "]")) else "格式不符",
            text[:300].replace("\n", "\\n"),
        )
    return data


# ================================================================
# 任务 A：每日情报摘要
# ================================================================

SUMMARY_SYSTEM = (
    "你是 AI 行业分析师，基于给出的 GitHub 趋势项目与 AI 资讯写「每日情报摘要」。\n"
    '只输出 JSON：{"points":[{"text":"一句话要点","refs":[编号]}],"trend":"一句话趋势判断"}\n'
    "\n"
    "⚠️ 这批材料本身就是按 AI / Agent / LLM 检索来的，所以下面是废话，禁止出现：\n"
    "· 「AI 很热 / Agent 项目扎堆出现 / LLM 持续升温」—— 那是检索条件，不是发现；\n"
    "· 「值得关注 / 前景广阔 / 意义重大」这类没有信息量的评价；\n"
    "· 只复述标题、不给判断。\n"
    "\n"
    "要求：\n"
    "- points 3~5 条，每条说**只有这批材料里才有**的具体信息：谁做了什么、开源/发布了什么、\n"
    "  做法或数据上和别家有什么不同。refs 填依据的条目编号（可多个，没有就空数组）。\n"
    "- trend 只写这批里**真正新的**东西（新方向、反常信号、对比），不写综述、不写常识。\n"
    "- 全部简体中文。\n"
)


def _fmt_items(gh_weekly, gh_daily, dom, intl):
    """把当日内容拼成带编号的文本，返回 (文本, 编号→url 映射)"""
    lines, ref_map = [], {}
    idx = 0

    def add(tag, items, limit):
        nonlocal idx
        for it in (items or [])[:limit]:
            idx += 1
            title = (it.get("title") or "").strip()
            desc = (it.get("summary") or "").strip()[:DESC_TRUNC]
            lines.append(f"[{idx}] ({tag}) {title} — {desc}")
            ref_map[idx] = it.get("url") or ""

    add("GitHub 本周", gh_weekly, 8)
    add("GitHub 今日", gh_daily, 8)
    add("国内资讯", dom, NEWS_INPUT_MAX)
    add("国际资讯", intl, NEWS_INPUT_MAX)
    return "\n".join(lines), ref_map


async def _task_summary(gh_weekly, gh_daily, dom, intl, user_id=None):
    text, ref_map = _fmt_items(gh_weekly, gh_daily, dom, intl)
    if not text.strip():
        return None
    data = await _call_llm_json(SUMMARY_SYSTEM, f"今日材料如下：\n{text}",
                                user_id=user_id, tag="摘要")
    if not isinstance(data, dict):
        return None
    points = []
    for p in (data.get("points") or [])[:5]:
        if not isinstance(p, dict):
            continue
        txt = (p.get("text") or "").strip()
        if not txt:
            continue
        refs = p.get("refs") if isinstance(p.get("refs"), list) else []
        points.append({
            "text": txt,
            "sources": [{"ref": r, "url": ref_map.get(r, "")}
                        for r in refs if isinstance(r, int) and ref_map.get(r)],
        })
    trend = (data.get("trend") or "").strip()
    if not points and not trend:
        return None
    return {"points": points, "trend": trend}


# ================================================================
# 任务 B：仓库中文简介（只给未缓存的）+ 资讯打分转中文
# ================================================================

TRANSLATE_SYSTEM = (
    "你是中文科技编辑。请完成两件事，**只输出 JSON**，不要多余文字，格式：\n"
    '{"repos":[{"i":编号,"intro_zh":"中文简介"}],'
    '"news":[{"i":编号,"score":0,"title_zh":"中文标题","summary_zh":"中文摘要"}]}\n'
    "要求：\n"
    "- repos：把每个仓库的英文简介概括成**一句到两句简体中文**（说清它是做什么的）；\n"
    "- news：给每条资讯打 0~100 的**热度/重要度分**，并把标题、摘要译成简体中文；\n"
    "- score 综合行业影响力与新鲜度，不要都给高分；\n"
    "- 编号必须与输入一一对应，不要编造没给的编号。"
)


async def _task_translate(top_repos, dom, intl, user_id=None):
    """返回 (repo_intros:list[(repo,intro)], news_scored:list[dict])"""
    repo_lines, repo_of = [], {}
    for i, it in enumerate(top_repos, 1):
        repo_lines.append(f"[{i}] {it.get('repo')} — {(it.get('summary') or '')[:DESC_TRUNC]}")
        repo_of[i] = it.get("repo")

    news_lines, news_of = [], {}
    i = 0
    for tag, items in (("国内", dom), ("国际", intl)):
        for it in (items or [])[:NEWS_INPUT_MAX]:
            i += 1
            news_lines.append(
                f"[{i}] ({tag}) {(it.get('title') or '').strip()} — {(it.get('summary') or '')[:DESC_TRUNC]}")
            news_of[i] = it

    if not repo_lines and not news_lines:
        return [], []

    user = "【仓库（只需 repo 部分）】\n" + ("\n".join(repo_lines) or "（无）")
    user += "\n\n【资讯（只需 news 部分）】\n" + ("\n".join(news_lines) or "（无）")
    # ⚠️ 这个任务一次要输出「N 个仓库简介 + 20 条资讯的中文标题/摘要/打分」，
    #    JSON 体积远大于摘要任务 —— 用默认上限会被截断，截断后 JSON 没闭合、
    #    解析必然失败，于是**仓库简介和资讯榜整块消失**（2026-09-24 实测：
    #    `aiconsult_repo_intro` 0 行、`news_hot` 无记录，而日志只有一句"生成成功"）。
    #    ⇒ 这里不限制输出，交给服务商的默认上限。
    data = await _call_llm_json(TRANSLATE_SYSTEM, user, user_id=user_id,
                                max_tokens=TRANSLATE_MAX_TOKENS, tag="翻译/打分")
    if not isinstance(data, dict):
        return [], []

    intros = []
    for r in (data.get("repos") or []):
        if not isinstance(r, dict):
            continue
        repo = repo_of.get(r.get("i"))
        intro = (r.get("intro_zh") or "").strip()
        if repo and intro:
            intros.append((repo, intro))

    scored = []
    for n in (data.get("news") or []):
        if not isinstance(n, dict):
            continue
        src = news_of.get(n.get("i"))
        if not src:
            continue
        try:
            score = int(n.get("score") or 0)
        except Exception:
            score = 0
        url = src.get("url") or ""
        host = ""
        try:
            from urllib.parse import urlparse
            host = urlparse(url).netloc.replace("www.", "")
        except Exception:
            host = ""
        scored.append({
            "title": (n.get("title_zh") or src.get("title") or "").strip(),
            "summary": (n.get("summary_zh") or "").strip(),
            "url": url, "source": host, "score": max(0, min(100, score)),
        })
    scored.sort(key=lambda x: -x["score"])
    return intros, scored


# ================================================================
# 生成 + 懒触发
# ================================================================

_state = {"running": False, "last_error": None}


async def _generate(day, user_id=None):
    gh_weekly = get_items("github_weekly")
    gh_daily = get_items("github_daily")
    dom = get_items("domestic")
    intl = get_items("international")

    # 本周榜（没有就先算一遍），只把**没缓存过中文简介**的交给 LLM
    monday = _dstr(_week_monday())
    board = get_board("weekly", monday)
    if not board or not (board.get("items") or []):
        build_weekly_board(monday)
        board = get_board("weekly", monday)
    top = (board or {}).get("items") or []
    cached = get_repo_intros([it.get("repo") for it in top])
    need = [it for it in top if it.get("repo") and not cached.get(it["repo"])]

    sum_task = _task_summary(gh_weekly, gh_daily, dom, intl, user_id)
    tra_task = _task_translate(need, dom, intl, user_id)
    sum_res, tra_res = await asyncio.gather(sum_task, tra_task, return_exceptions=True)

    briefing = sum_res if isinstance(sum_res, dict) else None
    if isinstance(sum_res, Exception):
        log.error(f"❌ AI 分析·摘要失败：{sum_res}")
    if isinstance(tra_res, Exception):
        log.error(f"❌ AI 分析·翻译/打分失败：{tra_res}")
        tra_res = ([], [])
    intros, scored = tra_res if isinstance(tra_res, tuple) else ([], [])

    # ⚠️ 「两个都是空」以前没有任何提示 —— 表现是仓库简介和资讯热度榜**永远空白**，
    #    而日志只有一句 ✅ 生成成功。多半是上面那条解析失败（输出被截断）导致的，
    #    具体原因看 `_call_llm_json` 打的那条 ERROR。
    if not intros and not scored:
        log.warning("⚠️ AI 分析·翻译/打分返回空（仓库简介 + 资讯榜都不会有内容）"
                    "—— 常见原因是 LLM 输出被截断或不是合法 JSON，详见上面的 ERROR")

    if intros:
        save_repo_intros(intros)

    news_items = scored[:NEWS_HOT_KEEP]
    if news_items:                      # 打分失败（空）时不落库，避免把已有内容清掉
        save_board("news_hot", day, news_items)

    return {
        "day": day,
        "briefing": briefing,
        "news_hot_count": len(news_items),
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


# 后台任务的强引用。
#
# ⚠️ 必须用模块级变量持有它：`asyncio.create_task()` 的返回值如果没人引用，
#    事件循环只保留**弱引用**，任务可能在执行途中被 GC 回收 —— 那时连
#    `finally` 都不会跑，`_state["running"]` 就永久停在 True，
#    当天的 AI 分析再也不会生成，**而且不报任何错**（静默卡死，最难查）。
_pending_task = None


async def _run_and_store(day, user_id=None):
    try:
        result = await _generate(day, user_id)
        await asyncio.to_thread(write_analysis, day, result)
        log.info(f"✅ AI 分析已生成（{day}）")
    except Exception as e:
        _state["last_error"] = str(e)
        log.error(f"❌ AI 分析生成失败：{e}")
    finally:
        _state["running"] = False


async def ensure_analysis(user_id=None):
    """懒触发入口：有今天的产出就直接返回；没有且没在跑 → 起后台任务并返回 generating。

    user_id 是**触发者**的 id，只用来决定用谁的模型配置（见 get_llm 的约定）；
    产出本身是全局共享的（每天一份，所有用户读同一份）。
    """
    global _pending_task

    day = _dstr(_today())
    cached = await asyncio.to_thread(read_analysis, day)
    if cached:
        return {"status": "ready", "day": day, **cached}

    if not _state["running"]:
        _state["running"] = True
        _state["last_error"] = None
        # 必须把 task 存到模块级变量里（原因见 _pending_task 定义处）
        _pending_task = asyncio.create_task(_run_and_store(day, user_id))
        log.info(f"⏳ 触发 AI 分析后台生成（{day}）")
    return {"status": "generating", "day": day, "error": _state["last_error"]}


def reset_analysis(day=None):
    """删掉某天的产出（用于"重新生成"）"""
    day = day or _dstr(_today())
    conn = get_conn()
    try:
        conn.execute("""DELETE FROM aiconsult_analysis WHERE day=%s""", (day,))
        conn.commit()
    finally:
        conn.close()


# ================================================================
# 组装给前端的完整响应
# ================================================================

def _enrich_weekly(board):
    """给本周榜条目补上缓存里的中文简介"""
    items = (board or {}).get("items") or []
    intros = get_repo_intros([it.get("repo") for it in items])
    for it in items:
        it["intro_zh"] = intros.get(it.get("repo"), "")
    return board


def get_board_payload(kind, period=None):
    """单个榜单（供切换器用）：返回 period + 榜单内容 + 可选期列表。"""
    if kind == "weekly":
        p = period or _dstr(_week_monday())
        return {"kind": kind, "period": p,
                "board": _enrich_weekly(get_board("weekly", p)),
                "periods": list_board_periods("weekly")}
    if kind in ("daily", "news_hot"):
        p = period or _dstr(_today())
        return {"kind": kind, "period": p,
                "board": get_board(kind, p),
                "periods": list_board_periods(kind)}
    return None


def build_analysis_payload(analysis):
    """把当日产出 + 三个榜默认期拼成一个响应体"""
    day = analysis.get("day") or _dstr(_today())
    monday = _dstr(_week_monday())

    boards = {
        "weekly": {"default": monday, "periods": list_board_periods("weekly")},
        "daily": {"default": day, "periods": list_board_periods("daily")},
        "news_hot": {"default": day, "periods": list_board_periods("news_hot")},
    }
    data = {
        "weekly": _enrich_weekly(get_board("weekly", monday)),
        "daily": get_board("daily", day),
        "news_hot": get_board("news_hot", day),
    }
    return {
        "status": "ready",
        "day": day,
        "briefing": analysis.get("briefing"),
        "updated_at": analysis.get("updated_at"),
        "boards": boards,
        "data": data,
    }
