"""
Self Grow — AI 咨询板块（GitHub 趋势 + 国内/国际 AI 资讯）

设计：
- GitHub：每天多个时间点，每个时间点分 ai / agent / llm 三段错峰搜索，
  结果先落暂存表 aiconsult_raw，整轮结束后交错合并（ai→agent→llm→ai…）
  去重取前 15 条落 aiconsult_items。
    · 每周：滚动 7 天 + sort=stars（star 最高）
    · 每日：滚动 24 小时内新建 + 默认排序（GitHub best-match）
- 资讯：Bocha（国内）/ Tavily（国际），只看最近 48 小时，每天两次抓取，直接落 aiconsult_items。
- 全部由 APScheduler 定时触发（见 main.py），前端只读 aiconsult_items 表，
  接口不实时打外部 API，因此无配额/鉴权风险。

失败容错：单次 HTTP 请求失败后隔 1 分钟 + 随机几秒重试，最多 3 次。
Key 缺失时跳过该源并打日志，库里保留旧数据。
"""

import json
import time
import random
import logging
import threading
from datetime import datetime, timedelta

import requests

from config import GITHUB_TOKEN, BOCHA_API_KEY, TAVILY_API_KEY
from db.connection import get_conn, now_str

# 用本模块自己的 logger。原来借的是 `config` 的 ——
# 抓取进度/失败日志在文件里全显示成配置模块，排查时会被误导。
log = logging.getLogger(__name__)

CATEGORIES = ("github_weekly", "github_daily", "domestic", "international")
GITHUB_SEGMENTS = ("ai", "agent", "llm")
GITHUB_TOP_KEEP = 16        # 定时任务：ai/agent/llm 三段交错合并去重后保留的条数
MANUAL_GITHUB_KEEP = 16     # 手动刷新：只搜 "ai" 一次直接取的条数
NEWS_WINDOW_HOURS = 48      # 国内/国际资讯只看最近 48 小时
REQUEST_TIMEOUT = 20
MAX_ATTEMPTS = 3
# 重试退避：指数增长（第 1 次失败等 ~2s，第 2 次 ~4s）+ 随机抖动。
#
# ⚠️ 原来是「固定 60 秒 + 随机 0~30 秒」。那个值有两个问题：
#   1. 对**不该重试**的错误也白等 —— 4xx（Key 无效、仓库不存在、参数写错）
#      重试多少次结果都一样，却每次都要占住调度线程一分半钟
#   2. APScheduler 的工作线程池只有 4 个，一个抓取任务最坏能占 4.5 分钟
#      （3 次 × 90s），后面排队的定时抓取全被推迟
# 现在：4xx 立刻失败；只有网络错误 / 5xx / 限流才重试。
# 服务端明确要求等待（`Retry-After` / `X-RateLimit-Reset`）时以它为准。
RETRY_BASE_SEC = 2
RETRY_MAX_SEC = 60   # 单次等待上限，避免服务端要求的超长等待拖垮调度线程

# GitHub 搜索关键词（三段）
GITHUB_QUERIES = {"ai": "ai", "agent": "agent", "llm": "llm"}
# 资讯搜索词（可按需调整）
DOMESTIC_QUERY = "AI 大模型 人工智能 最新动态 发布"
INTERNATIONAL_QUERY = "AI LLM agent latest news breakthrough"

# ⚠️ 不能用模块级共享的 Session：`requests.Session` **官方不保证线程安全**
# （连接池与 cookie 在两个线程同时发请求时可能互相串）。
# 本项目里定时抓取跑在 APScheduler 的工作线程、手动刷新跑在请求线程，
# 确实会并发。改成每线程一个。
_thread_local = threading.local()


def _get_session() -> requests.Session:
    """取当前线程的 requests.Session（没有则创建）"""
    s = getattr(_thread_local, "session", None)
    if s is None:
        s = requests.Session()
        s.headers.update({"User-Agent": "SelfGrow-AIConsult/1.0"})
        _thread_local.session = s
    return s


def _parse_retry_after(resp):
    """从响应里读服务端建议的等待秒数，没有则返回 None

    两种来源都认：
      · `Retry-After: 120`（标准头，秒数）
      · `X-RateLimit-Reset: <unix 时间戳>`（GitHub 用这个）
    """
    ra = resp.headers.get("Retry-After")
    if ra and str(ra).strip().isdigit():
        return float(ra)
    reset = resp.headers.get("X-RateLimit-Reset")
    if reset and str(reset).strip().isdigit():
        delta = float(reset) - time.time()
        # sanity check：只认「未来 1 天内」的合理值。
        # 第三方头不可信是常态 —— 实测一个荒谬的时间戳会算出
        # 980 亿秒的等待（虽然最终仍会被 RETRY_MAX_SEC 封顶到 60s，
        # 但日志里出现这种数字很容易让人以为程序算错了）。
        if 0 < delta <= 86400:
            return delta
    return None


def _classify_error(e):
    """判断一个异常是否值得重试 → (是否重试, 服务端建议的等待秒数)

    ⚠️ 这个区分是本次改动的核心。原来 `except Exception` 一律重试，
    等于把「Key 写错了」和「网络抖了一下」当成同一类事情。

      · 无 response 的 requests 异常（超时 / 连不上 / DNS）→ 重试 ✅
      · HTTP 5xx（服务端临时故障）                          → 重试 ✅
      · HTTP 429，或 403 且 GitHub 的配额已耗尽             → 重试 ✅（限流）
      · 其余 4xx（401 鉴权失败 / 404 不存在 / 422 参数错）  → **不重试** ❌
        重试 N 次结果完全一样，纯粹浪费一个调度线程
    """
    resp = getattr(e, "response", None)

    if resp is not None:
        code = resp.status_code
        # GitHub 的限流用的是 403 + X-RateLimit-Remaining: 0（不是标准的 429）
        rate_limited = code == 429 or (
            code == 403 and resp.headers.get("X-RateLimit-Remaining") == "0"
        )
        if rate_limited:
            return True, _parse_retry_after(resp)
        if 500 <= code < 600:
            return True, None
        return False, None

    # 没有 response → 网络层错误（超时 / 连接被拒 / DNS），值得重试
    if isinstance(e, requests.RequestException):
        return True, None

    # 其它异常（本地代码 bug、JSON 解析失败）→ 重试也不会变好
    return False, None


def _request_with_retry(fn):
    """执行 fn()；只对**值得重试**的失败重试（见 `_classify_error`）。

    退避是指数的且有上限。服务端明确要求等待时（限流场景）以它为准，
    但仍受 `RETRY_MAX_SEC` 封顶 —— 宁可稍后重试，也不要让一个定时任务
    把调度线程占住好几分钟。
    """
    last_err = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001 — 分类逻辑在 _classify_error 里
            last_err = e
            retryable, suggested = _classify_error(e)

            if not retryable:
                # 这条日志很重要：以前 4xx 会被重试 3 次才报「最终失败」，
                # 日志里看不出是「重试也没用」还是「重试次数不够」
                log.error(
                    f"❌ AI咨询请求失败且不可重试（{type(e).__name__}）：{e}"
                )
                raise

            if attempt >= MAX_ATTEMPTS:
                break

            if suggested is not None:
                wait = min(float(suggested), RETRY_MAX_SEC)
            else:
                wait = min(RETRY_BASE_SEC * (2 ** (attempt - 1)), RETRY_MAX_SEC)
            wait += random.uniform(0, 2)   # 抖动，避免多线程同时重试

            log.warning(
                f"⚠️ AI咨询请求第 {attempt} 次失败（可重试）：{e}；{wait:.0f}s 后重试"
            )
            time.sleep(wait)

    log.error(f"❌ AI咨询请求最终失败（已重试 {MAX_ATTEMPTS} 次）：{last_err}")
    raise last_err


def _news_date_range():
    """资讯的 48 小时窗口 → (start, end)，均为本地日期 YYYY-MM-DD。

    Bocha / Tavily 的时间过滤都只到「日期」粒度，给不出精确到小时的滚动窗口，
    所以用「今天 - 2 天 .. 今天」近似「最近 48 小时」。
    """
    now = datetime.now()
    start = (now - timedelta(hours=NEWS_WINDOW_HOURS)).strftime("%Y-%m-%d")
    return start, now.strftime("%Y-%m-%d")


# ================================================================
# 外部 API 调用
# ================================================================

def _github_headers():
    return {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _github_search(keyword, since, weekly, per_page=10):
    """单次 GitHub 搜索，返回 item 列表。Key 缺失直接返回 []。

    per_page：定时任务的「一段」固定取 10（三段共 30，再交错合并）；
              手动刷新传 16（一次到位）。GitHub 上限 100。
    """
    if not GITHUB_TOKEN:
        log.warning("⚠️ GITHUB_TOKEN 未配置，跳过 GitHub 抓取")
        return []
    params = {"q": f"{keyword} created:>={since}", "per_page": per_page}
    if weekly:
        params["sort"] = "stars"
        params["order"] = "desc"
    # 每日不传 sort → GitHub 默认 best-match

    def _do():
        resp = _get_session().get(
            "https://api.github.com/search/repositories",
            headers=_github_headers(), params=params, timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        return [
            {
                "title": repo.get("full_name", ""),
                "url": repo.get("html_url", ""),
                "summary": repo.get("description") or "",
                "stars": repo.get("stargazers_count", 0) or 0,
                "meta": json.dumps(
                    {"language": repo.get("language"),
                     "owner": (repo.get("owner") or {}).get("login")},
                    ensure_ascii=False,
                ),
            }
            for repo in resp.json().get("items", [])
        ]

    return _request_with_retry(_do)


def _bocha_search(query):
    """Bocha 国内网页搜索。Key 缺失返回 []。"""
    if not BOCHA_API_KEY:
        log.warning("⚠️ BOCHA_API_KEY 未配置，跳过国内资讯抓取")
        return []

    start, end = _news_date_range()   # 最近 48 小时
    def _do():
        resp = _get_session().post(
            "https://api.bochaai.com/v1/web-search",
            headers={"Authorization": f"Bearer {BOCHA_API_KEY}", "Content-Type": "application/json"},
            # Bocha 没有「两天」选项，用日期范围 YYYY-MM-DD..YYYY-MM-DD 表达 48 小时
            json={"query": query, "freshness": f"{start}..{end}", "summary": True, "count": 10},
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        pages = (resp.json().get("data") or {}).get("webPages") or {}
        return [
            {
                "title": w.get("name") or w.get("title") or "",
                "url": w.get("url") or "",
                "summary": w.get("snippet") or "",
                "stars": None,
                "meta": json.dumps({"date": w.get("dateLastCrawled")}, ensure_ascii=False),
            }
            for w in (pages.get("value") or [])
        ]

    return _request_with_retry(_do)


def _tavily_search(query):
    """Tavily 国际网页搜索（用 requests 直连，避免额外依赖）。Key 缺失返回 []。"""
    if not TAVILY_API_KEY:
        log.warning("⚠️ TAVILY_API_KEY 未配置，跳过国际资讯抓取")
        return []

    start, end = _news_date_range()   # 最近 48 小时
    def _do():
        resp = _get_session().post(
            "https://api.tavily.com/search",
            headers={"Authorization": f"Bearer {TAVILY_API_KEY}", "Content-Type": "application/json"},
            json={
                "query": query,
                "search_depth": "advanced",
                "max_results": 10,
                # Tavily 的 start_date/end_date 为 YYYY-MM-DD，用来卡 48 小时
                "start_date": start,
                "end_date": end,
            },
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        return [
            {
                "title": r.get("title") or "",
                "url": r.get("url") or "",
                "summary": r.get("content") or "",
                "stars": None,
                "meta": json.dumps({}, ensure_ascii=False),
            }
            for r in (resp.json().get("results") or [])
        ]

    return _request_with_retry(_do)


# ================================================================
# 数据库读写
# ================================================================

def save_raw(category, query, round_key, items):
    conn = get_conn()
    try:
        conn.execute(
            """INSERT INTO aiconsult_raw (category, query, round_key, payload, created_at) VALUES (%s,%s,%s,%s,%s)""",
            (category, query, round_key, json.dumps(items, ensure_ascii=False), now_str()),
        )
        conn.commit()
    finally:
        conn.close()


def get_raw(round_key, category):
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT query, payload FROM aiconsult_raw WHERE round_key=%s AND category=%s ORDER BY id""",
            (round_key, category),
        ).fetchall()
    finally:
        conn.close()
    out = {}
    for r in rows:
        try:
            out[r["query"]] = json.loads(r["payload"])
        except Exception:
            continue
    return out


def clear_raw(round_key, category):
    conn = get_conn()
    try:
        conn.execute(
            """DELETE FROM aiconsult_raw WHERE round_key=%s AND category=%s""",
            (round_key, category),
        )
        conn.commit()
    finally:
        conn.close()


def save_items(category, items, batch_time):
    conn = get_conn()
    try:
        conn.execute("""DELETE FROM aiconsult_items WHERE category=%s""", (category,))
        for it in items:
            conn.execute(
                """INSERT INTO aiconsult_items (category, title, url, summary, stars, meta, batch_time, created_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                (category, it.get("title", ""), it.get("url", ""),
                 it.get("summary", ""), it.get("stars"), it.get("meta", ""),
                 batch_time, now_str()),
            )
        conn.commit()
    finally:
        conn.close()


def get_items(category, limit=15):
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT title, url, summary, stars, meta, batch_time FROM aiconsult_items WHERE category=%s ORDER BY id""",
            (category,),
        ).fetchall()
    finally:
        conn.close()
    result = []
    for r in rows:
        meta = {}
        try:
            meta = json.loads(r["meta"]) if r["meta"] else {}
        except Exception:
            pass
        result.append({
            "title": r["title"], "url": r["url"], "summary": r["summary"],
            "stars": r["stars"], "meta": meta, "batch_time": r["batch_time"],
        })
    return result[:limit]


# ================================================================
# 抓取流程：GitHub 三段错峰 + 合并
# ================================================================

def _since_str(weekly):
    """GitHub `created:` 过滤的起始时刻（显式带 +08:00 偏移）。

    - 每日：**滚动 24 小时**（now - 24h）—— 不是「本地今天 0 点」
    - 每周：滚动 7 天（now - 7d）
    ⚠️ 必须显式带 +08:00：不带时区 GitHub 会按 **UTC** 解析，和本地差 8 小时。
    （中国无夏令时，固定 +08:00 安全。）
    """
    now = datetime.now()
    start = now - timedelta(days=7) if weekly else now - timedelta(hours=24)
    return start.strftime("%Y-%m-%dT%H:%M:%S+08:00")


def stage_github_segment(category, query, round_key):
    """抓取一段 GitHub 搜索结果并暂存；单段失败仅告警，不阻断整轮。"""
    weekly = category == "github_weekly"
    since = _since_str(weekly)
    keyword = GITHUB_QUERIES[query]
    try:
        items = _github_search(keyword, since, weekly)
        save_raw(category, query, round_key, items)
        log.info(f"✅ GitHub 暂存 [{category}/{query}] {len(items)} 条（轮 {round_key}）")
    except Exception as e:
        log.error(f"❌ GitHub 暂存失败 [{category}/{query}]：{e}")


def merge_github_round(category, round_key, keep=GITHUB_TOP_KEEP):
    """读取本轮三段暂存，交错合并（ai→agent→llm）去重取前 keep 条落库。"""
    raw = get_raw(round_key, category)
    if not raw:
        log.warning(f"⚠️ 无暂存数据，跳过合并 [{category}] 轮 {round_key}")
        clear_raw(round_key, category)
        return
    max_len = max((len(v) for v in raw.values()), default=0)
    interleaved = []
    for i in range(max_len):
        for q in GITHUB_SEGMENTS:
            seg = raw.get(q)
            if seg and i < len(seg):
                interleaved.append(seg[i])
    seen, out = set(), []
    for it in interleaved:
        u = it.get("url")
        if u and u in seen:
            continue
        if u:
            seen.add(u)
        out.append(it)
        if len(out) >= keep:
            break
    # ⚠️ 合并结果为空时绝不能落库：save_items 是「先 DELETE 再 INSERT」，
    #    传空列表会把上一轮的好数据整个清掉。保留旧数据更符合预期。
    if not out:
        log.warning(
            f"⚠️ 本轮合并结果为空，保留旧数据 [{category}] 轮 {round_key}"
            "（多半是 GITHUB_TOKEN 缺失，或三段都没返回）"
        )
        clear_raw(round_key, category)
        return
    batch = now_str()
    save_items(category, out, batch)
    clear_raw(round_key, category)
    log.info(f"✅ GitHub 合并落库 [{category}] {len(out)} 条（轮 {round_key}）")
    post_process_github(category)   # 派生：每周→本周新鲜榜；每日→日快照 + 本日新鲜榜


# ================================================================
# 抓取流程：资讯（直接落库）
# ================================================================

def fetch_domestic_news():
    try:
        items = _bocha_search(DOMESTIC_QUERY)
        # Key 缺失 / 搜索无结果都会返回 []，此时必须跳过 save_items，
        # 否则「先 DELETE 再 INSERT」会把上一轮数据清空（与文件头承诺矛盾）。
        if not items:
            log.warning("⚠️ 国内 AI 资讯本轮无数据（Key 缺失或搜索为空），保留旧数据")
            return
        save_items("domestic", items, now_str())
        log.info(f"✅ 国内 AI 资讯抓取 {len(items)} 条")
    except Exception as e:
        log.error(f"❌ 国内 AI 资讯抓取失败：{e}")


def fetch_international_news():
    try:
        items = _tavily_search(INTERNATIONAL_QUERY)
        if not items:
            log.warning("⚠️ 国际 AI 资讯本轮无数据（Key 缺失或搜索为空），保留旧数据")
            return
        save_items("international", items, now_str())
        log.info(f"✅ 国际 AI 资讯抓取 {len(items)} 条")
    except Exception as e:
        log.error(f"❌ 国际 AI 资讯抓取失败：{e}")


# ================================================================
# 手动触发（供 /api/aiconsult/refresh 使用）
# ================================================================

def run_github_round_now(category):
    """**手动刷新专用**：GitHub 只搜 "ai"、取前 16 条（单次请求，快）。

    ⚠️ 定时任务**不走这里** —— 它们走 stage_github_segment（ai/agent/llm 三段错峰，每段 10）
    + merge_github_round（交错合并去重取前 16）。所以「只搜 ai」只影响手动刷新。
    每周/每日逻辑相同：仅时间窗与排序不同（每周=近7天按 star，每日=当天 best-match）。
    """
    weekly = category == "github_weekly"
    since = _since_str(weekly)
    try:
        items = _github_search(GITHUB_QUERIES["ai"], since, weekly, per_page=MANUAL_GITHUB_KEEP)
    except Exception as e:
        log.error(f"❌ 手动刷新 [{category}] 失败：{e}")
        return
    if not items:
        log.warning(f"⚠️ 手动刷新 [{category}] 无数据（Token 缺失或搜索为空），保留旧数据")
        return
    save_items(category, items, now_str())
    log.info(f"✅ 手动刷新落库 [{category}] {len(items)} 条（只搜 ai 前 {MANUAL_GITHUB_KEEP}）")
    post_process_github(category)   # 手动刷新同样派生榜单/快照


def run_all_now():
    run_github_round_now("github_weekly")
    run_github_round_now("github_daily")
    fetch_domestic_news()
    fetch_international_news()


# ================================================================
# AI 分析 · 数据侧（快照 / 榜单）—— 纯数据，**不调 LLM**
# ================================================================

WEEKLY_BOARD_KEEP = 5      # 本周新鲜榜取前 5
DAILY_BOARD_MAX = 10       # 本日新鲜榜最多 10 条
SNAP_KEEP_DAYS = 2         # 日快照 / 日榜 / 资讯榜只保留「今天 + 昨天」
NEWS_HOT_KEEP = 5          # 资讯热度榜取前 5


def _today():
    return datetime.now().date()


def _dstr(d):
    return d.strftime("%Y-%m-%d")


def _week_monday(d=None):
    d = d or _today()
    return d - timedelta(days=d.weekday())


# ── 快照 ────────────────────────────────────────────────────────

def save_gh_snapshot(kind, snap_date, repos):
    """repos: [{'repo': 'owner/name', 'stars': int}, ...]"""
    repos = [r for r in (repos or []) if r.get("repo")]
    if not repos:
        return 0
    ts = now_str()
    conn = get_conn()
    try:
        for r in repos:
            conn.execute(
                """INSERT INTO aiconsult_gh_snap (kind, snap_date, snap_at, repo, stars, created_at) VALUES (%s,%s,%s,%s,%s,%s)""",
                (kind, snap_date, ts, r["repo"], int(r.get("stars") or 0), ts),
            )
        conn.commit()
    finally:
        conn.close()
    return len(repos)


def get_snapshots(kind, snap_date):
    """按写入顺序（= 时间顺序）返回 [(repo, stars)]"""
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT repo, stars FROM aiconsult_gh_snap WHERE kind=%s AND snap_date=%s ORDER BY id""",
            (kind, snap_date),
        ).fetchall()
    finally:
        conn.close()
    return [(r["repo"], r["stars"]) for r in rows]


# 原来这里有个 `list_snap_dates(kind, limit=60)`（列出某类快照里出现过的日期），
# 全项目零调用方，已于 2026-09-23 的代码审查删除。
# 它的用途是「让前端选一个历史日期」，但那个功能没做；若将来要做，
# 去 git 历史里找这次提交之前的版本即可恢复。


def get_prev_weekly_snapshot(before_date):
    """早于 before_date 的**最近一份周基线** → (日期, {repo: stars})"""
    conn = get_conn()
    try:
        row = conn.execute(
            """SELECT snap_date FROM aiconsult_gh_snap WHERE kind='weekly' AND snap_date<%s ORDER BY snap_date DESC LIMIT 1""", (before_date,)).fetchone()
        if not row:
            return None, {}
        d = row["snap_date"]
        rows = conn.execute(
            """SELECT repo, stars FROM aiconsult_gh_snap WHERE kind='weekly' AND snap_date=%s""",
            (d,)).fetchall()
    finally:
        conn.close()
    return d, {r["repo"]: r["stars"] for r in rows}


# ── 榜单读写 ────────────────────────────────────────────────────

def save_board(kind, period_key, items):
    payload = json.dumps(items or [], ensure_ascii=False)
    conn = get_conn()
    try:
        row = conn.execute(
            """SELECT id FROM aiconsult_board WHERE kind=%s AND period_key=%s""", (kind, period_key)
        ).fetchone()
        if row:
            conn.execute("""UPDATE aiconsult_board SET payload=%s, created_at=%s WHERE id=%s""",
                         (payload, now_str(), row["id"]))
        else:
            conn.execute(
                """INSERT INTO aiconsult_board (kind, period_key, payload, created_at) VALUES (%s,%s,%s,%s)""",
                (kind, period_key, payload, now_str()),
            )
        conn.commit()
    finally:
        conn.close()


def get_board(kind, period_key):
    conn = get_conn()
    try:
        row = conn.execute(
            """SELECT payload, created_at FROM aiconsult_board WHERE kind=%s AND period_key=%s""",
            (kind, period_key)).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    try:
        items = json.loads(row["payload"])
    except Exception:
        items = []
    return {"period": period_key, "items": items, "created_at": row["created_at"]}


def list_board_periods(kind, limit=60):
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT period_key FROM aiconsult_board WHERE kind=%s ORDER BY period_key DESC LIMIT %s""",
            (kind, limit)).fetchall()
    finally:
        conn.close()
    return [r["period_key"] for r in rows]


# ── 快照记录任务 ────────────────────────────────────────────────

def _items_to_repos(category):
    out = []
    for it in get_items(category):
        repo = (it.get("title") or "").strip()
        if repo:
            out.append({"repo": repo, "stars": it.get("stars") or 0})
    return out


def record_weekly_baseline():
    """每周日 15:05：把当轮「GitHub 每周」结果记为周基线，供下周比对。"""
    repos = _items_to_repos("github_weekly")
    if not repos:
        log.warning("⚠️ 无 GitHub 每周数据，跳过周基线快照")
        return
    day = _dstr(_today())
    n = save_gh_snapshot("weekly", day, repos)
    log.info(f"✅ 周基线快照已记：{day}，{n} 个仓库")


def record_daily_snapshot():
    """每次每日抓取后：存一份当日快照，并即时重算「本日新鲜榜」。"""
    repos = _items_to_repos("github_daily")
    if not repos:
        log.warning("⚠️ 无 GitHub 每日数据，跳过快照")
        return
    day = _dstr(_today())
    n = save_gh_snapshot("daily", day, repos)
    build_daily_board()
    log.info(f"✅ 日快照已记：{day}，{n} 个仓库")


# ── 榜单计算 ────────────────────────────────────────────────────

def build_weekly_board(monday_key=None):
    """本周新鲜榜：当前每周结果 vs 上周末基线（**缺基线的按 0 算**），取涨幅前 5。

    monday_key：这一周的周一（YYYY-MM-DD）；不传则取「本周周一」。
    """
    monday_key = monday_key or _dstr(_week_monday())
    base_date, base = get_prev_weekly_snapshot(monday_key)
    items = []
    for it in get_items("github_weekly"):
        repo = (it.get("title") or "").strip()
        if not repo:
            continue
        cur = it.get("stars") or 0
        b = base.get(repo, 0)          # 基线里没有 → 按 0
        items.append({
            "repo": repo, "url": it.get("url") or "",
            "stars": cur, "base": b, "delta": cur - b,
            "summary": it.get("summary") or "", "meta": it.get("meta") or {},
        })
    items.sort(key=lambda x: -x["delta"])
    top = items[:WEEKLY_BOARD_KEEP]
    save_board("weekly", monday_key, top)
    log.info(f"✅ 本周新鲜榜 {monday_key}：{len(top)} 名（基线 {base_date or '无→按0'}）")
    return top


def build_daily_board(day=None):
    """本日新鲜榜：每条 = 当前星数 − **它今天最早出现的快照**的星数；取增加 > 0 的前 10。

    不足 10 条 → 用昨天榜的条目顶着（保留其原日期）。
    """
    day = day or _dstr(_today())
    first, last = {}, {}
    for repo, stars in get_snapshots("daily", day):
        if repo not in first:
            first[repo] = stars
        last[repo] = stars

    risers = []
    for repo, cur in last.items():
        delta = cur - first.get(repo, cur)
        if delta > 0:
            risers.append({"repo": repo, "stars": cur, "delta": delta, "date": day})
    risers.sort(key=lambda x: -x["delta"])
    risers = risers[:DAILY_BOARD_MAX]

    if len(risers) < DAILY_BOARD_MAX:                     # 不够 → 拿昨天的顶
        prev = get_board("daily", _dstr(_today() - timedelta(days=1)))
        have = {r["repo"] for r in risers}
        for it in ((prev or {}).get("items") or []):
            if len(risers) >= DAILY_BOARD_MAX:
                break
            if it.get("repo") in have:
                continue
            risers.append(it)
            have.add(it["repo"])

    save_board("daily", day, risers)
    log.info(f"✅ 本日新鲜榜 {day}：{len(risers)} 条")
    return risers


def post_process_github(category):
    """GitHub 各轮落库后派生榜单/快照（定时与手动刷新都走这里）。"""
    try:
        if category == "github_weekly":
            build_weekly_board()
        elif category == "github_daily":
            record_daily_snapshot()
    except Exception as e:
        log.error(f"❌ 派生榜单失败 [{category}]：{e}")


def cleanup_expired():
    """清理过期数据：日快照 / 日榜 / 资讯榜只留「今天 + 昨天」；周基线、周榜长期保留。"""
    keep_from = _dstr(_today() - timedelta(days=SNAP_KEEP_DAYS - 1))
    conn = get_conn()
    try:
        n1 = conn.execute("""DELETE FROM aiconsult_gh_snap WHERE kind='daily' AND snap_date<%s""",
                          (keep_from,)).rowcount
        n2 = conn.execute("""DELETE FROM aiconsult_board WHERE kind IN ('daily','news_hot') AND period_key<%s""", (keep_from,)).rowcount
        conn.commit()
    finally:
        conn.close()
    log.info(f"🧹 清理过期数据：日快照 -{n1} 行、日榜/资讯榜 -{n2} 行（保留 {keep_from} 起）")


# ================================================================
# 读取（供路由层）
# ================================================================

def get_all():
    return {
        "github_weekly": get_items("github_weekly"),
        "github_daily": get_items("github_daily"),
        "domestic": get_items("domestic"),
        "international": get_items("international"),
        "configured": {
            "github": bool(GITHUB_TOKEN),
            "domestic": bool(BOCHA_API_KEY),
            "international": bool(TAVILY_API_KEY),
        },
    }
