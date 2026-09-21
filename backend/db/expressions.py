"""
Self Grow — 表达训练数据库 CRUD

管理 expression_questions（题目表）和 expression_answers（回答表）的增删改查。
"""

import json

from db.connection import get_conn


# ================================================================
# 题目 CRUD
# ================================================================

def create_question(question: str, question_type: str, hints: str = None, source: str = "") -> int:
    """创建一条新题目，返回题目 ID"""
    conn = get_conn()
    try:
        cursor = conn.execute(
            """INSERT INTO expression_questions (question, question_type, hints, source)
               VALUES (?, ?, ?, ?)""",
            (question, question_type, hints or None, source),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def get_question(question_id: int) -> dict:
    """获取单条题目"""
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM expression_questions WHERE id = ?", (question_id,)
        ).fetchone()
        return _row_to_dict(row) if row else None
    finally:
        conn.close()


def get_existing_questions(types: list = None, limit: int = 50) -> list:
    """获取已有题目（用于 LLM 查重），返回题目文本列表"""
    conn = get_conn()
    try:
        if types:
            placeholders = ",".join("?" for _ in types)
            rows = conn.execute(
                f"SELECT question, question_type FROM expression_questions WHERE question_type IN ({placeholders}) ORDER BY created_at DESC LIMIT ?",
                (*types, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT question, question_type FROM expression_questions ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [{"question": r["question"], "question_type": r["question_type"]} for r in rows]
    finally:
        conn.close()


def update_question_hints(question_id: int, hints: str):
    """更新题目的提示内容"""
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE expression_questions SET hints = ? WHERE id = ?",
            (hints, question_id),
        )
        conn.commit()
    finally:
        conn.close()


# ================================================================
# 回答 CRUD
# ================================================================

def create_answer(user_id: str, question_id: int, attempt: int = 1) -> int:
    """创建一条新回答记录，返回 answer ID"""
    conn = get_conn()
    try:
        cursor = conn.execute(
            """INSERT INTO expression_answers (user_id, question_id, attempt, status)
               VALUES (?, ?, ?, 'answered')""",
            (user_id, question_id, attempt),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def update_answer_text(answer_id: int, answer: str, filler_words: dict = None):
    """更新回答文本和填充词统计"""
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE expression_answers SET answer = ?, filler_words = ? WHERE id = ?",
            (answer, json.dumps(filler_words, ensure_ascii=False) if filler_words else None, answer_id),
        )
        conn.commit()
    finally:
        conn.close()


def update_answer_evaluation(answer_id: int, scores: dict, strengths: list, improvements: list, suggestion: str):
    """更新 AI 评分和建议"""
    conn = get_conn()
    try:
        conn.execute(
            """UPDATE expression_answers SET
               score_total = ?, score_fluency = ?, score_logic = ?,
               score_content = ?, score_language = ?,
               strengths = ?, improvements = ?, suggestion = ?,
               status = 'evaluated'
               WHERE id = ?""",
            (
                scores.get("total"), scores.get("fluency"), scores.get("logic"),
                scores.get("content"), scores.get("language"),
                json.dumps(strengths, ensure_ascii=False) if strengths else None,
                json.dumps(improvements, ensure_ascii=False) if improvements else None,
                suggestion,
                answer_id,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def get_answer(answer_id: int) -> dict:
    """获取单条回答详情（含题目信息）"""
    conn = get_conn()
    try:
        row = conn.execute(
            """SELECT a.*, q.question, q.question_type, q.hints, q.source
               FROM expression_answers a
               JOIN expression_questions q ON a.question_id = q.id
               WHERE a.id = ?""",
            (answer_id,),
        ).fetchone()
        return _row_to_dict(row) if row else None
    finally:
        conn.close()


def get_answers_by_question(question_id: int, user_id: str = None) -> list:
    """获取某题目的所有回答"""
    conn = get_conn()
    try:
        if user_id:
            rows = conn.execute(
                """SELECT * FROM expression_answers
                   WHERE question_id = ? AND user_id = ?
                   ORDER BY attempt ASC""",
                (question_id, user_id),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM expression_answers WHERE question_id = ? ORDER BY attempt ASC",
                (question_id,),
            ).fetchall()
        return [_row_to_dict(r) for r in rows]
    finally:
        conn.close()


def get_user_history(user_id: str, limit: int = 20) -> list:
    """获取用户最近回答记录（按时间倒序），每条含题目预览"""
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT a.id, a.answer, a.score_total, a.status, a.attempt, a.created_at,
                      q.id as question_id, q.question, q.question_type
               FROM expression_answers a
               JOIN expression_questions q ON a.question_id = q.id
               WHERE a.user_id = ?
               ORDER BY a.created_at DESC
               LIMIT ?""",
            (user_id, limit),
        ).fetchall()
        return [_row_to_dict(r) for r in rows]
    finally:
        conn.close()


def get_user_stats(user_id: str) -> dict:
    """获取用户总训练统计数据"""
    conn = get_conn()
    try:
        # 累计回答总数
        total = conn.execute(
            "SELECT COUNT(*) as cnt FROM expression_answers WHERE user_id = ?",
            (user_id,),
        ).fetchone()["cnt"]

        # 累计训练天数
        days = conn.execute(
            "SELECT COUNT(DISTINCT DATE(created_at)) as cnt FROM expression_answers WHERE user_id = ?",
            (user_id,),
        ).fetchone()["cnt"]

        # 各题型分布
        types = conn.execute(
            """SELECT q.question_type, COUNT(*) as cnt
               FROM expression_answers a
               JOIN expression_questions q ON a.question_id = q.id
               WHERE a.user_id = ?
               GROUP BY q.question_type""",
            (user_id,),
        ).fetchall()
        type_summary = {r["question_type"]: r["cnt"] for r in types}

        # 平均分（近5次）
        #
        # ⚠️ 子查询必须带别名 `AS recent` —— **MySQL 强制要求**
        #    （errno 1248 «Every derived table must have its own alias»），
        #    SQLite 不要求，所以本地用 SQLite 开发时这个问题不会暴露。
        avg_row = conn.execute(
            """SELECT AVG(score_total) as avg_score FROM (
                SELECT score_total FROM expression_answers
                WHERE user_id = ? AND score_total IS NOT NULL
                ORDER BY created_at DESC LIMIT 5
            ) AS recent""",
            (user_id,),
        ).fetchone()
        avg_score = round(avg_row["avg_score"], 1) if avg_row and avg_row["avg_score"] else None

        return {
            "total_answered": total,
            "total_days": days,
            "type_summary": type_summary,
            "avg_score": avg_score,
        }
    finally:
        conn.close()


def get_max_attempt(question_id: int, user_id: str) -> int:
    """获取某题目用户的最大 attempt 次数"""
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT MAX(attempt) as max_attempt FROM expression_answers WHERE question_id = ? AND user_id = ?",
            (question_id, user_id),
        ).fetchone()
        return row["max_attempt"] if row and row["max_attempt"] else 0
    finally:
        conn.close()


def get_question_history_list(
    user_id: str,
    question_type: str = None,
    time_start: str = None,
    time_end: str = None,
    answer_count: str = None,
    page: int = 1,
    page_size: int = 10,
) -> dict:
    """
    获取按题目分组的分页历史列表（用户回答过的题目列表）。
    支持题型、时间范围、回答次数筛选。
    返回 { total, page, page_size, items: [{ question_id, question, question_type, last_answer_time, answer_count, ... }] }
    """
    conn = get_conn()
    try:
        params = [user_id]
        where_clauses = ["a.user_id = ?"]

        # 题型筛选
        if question_type:
            where_clauses.append("q.question_type = ?")
            params.append(question_type)

        # 时间范围筛选（基于 last_answer_time）
        if time_start:
            where_clauses.append("MAX(a.created_at) >= ?")
            params.append(time_start)
        if time_end:
            where_clauses.append("MAX(a.created_at) <= ?")
            params.append(time_end + " 23:59:59")

        where_sql = " AND ".join(where_clauses)

        # 按题目分组查询——先查出所有符合条件的题目及其回答统计
        base_sql = f"""
            SELECT q.id as question_id, q.question, q.question_type,
                   MAX(a.created_at) as last_answer_time,
                   COUNT(a.id) as answer_count
            FROM expression_answers a
            JOIN expression_questions q ON a.question_id = q.id
            WHERE {where_sql}
            GROUP BY q.id
        """

        # 回答次数筛选（在分组后过滤）
        if answer_count:
            if answer_count == "gt3":
                having_sql = "HAVING answer_count > 3"
            else:
                having_sql = f"HAVING answer_count = {int(answer_count)}"
        else:
            having_sql = ""

        # 查询总数
        # ⚠️ `AS cnt_sub` 不能省 —— MySQL 要求派生表必须有别名（errno 1248），
        #    SQLite 不要求。见本文件 get_user_stats() 里的同款注释。
        count_sql = f"SELECT COUNT(*) as cnt FROM ({base_sql} {having_sql}) AS cnt_sub"
        total = conn.execute(count_sql, params).fetchone()["cnt"]

        # 查询分页数据
        offset = (page - 1) * page_size
        data_sql = f"""
            {base_sql} {having_sql}
            ORDER BY last_answer_time DESC
            LIMIT ? OFFSET ?
        """
        rows = conn.execute(data_sql, params + [page_size, offset]).fetchall()

        items = []
        for r in rows:
            items.append({
                "question_id": r["question_id"],
                "question": r["question"],
                "question_type": r["question_type"],
                "last_answer_time": r["last_answer_time"],
                "answer_count": r["answer_count"],
            })

        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "items": items,
        }
    finally:
        conn.close()


def get_recent_answers(question_id: int, user_id: str = None, limit: int = 5) -> list:
    """
    获取某题目最近的 N 条回答记录（按时间倒序）。
    用于展开区域展示。
    """
    conn = get_conn()
    try:
        if user_id:
            rows = conn.execute(
                """SELECT a.id, a.attempt, a.answer, a.score_total, a.status, a.created_at,
                          a.score_fluency, a.score_logic, a.score_content, a.score_language,
                          a.strengths, a.improvements, a.suggestion
                   FROM expression_answers a
                   WHERE a.question_id = ? AND a.user_id = ?
                   ORDER BY a.created_at DESC
                   LIMIT ?""",
                (question_id, user_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT a.id, a.attempt, a.answer, a.score_total, a.status, a.created_at,
                          a.score_fluency, a.score_logic, a.score_content, a.score_language,
                          a.strengths, a.improvements, a.suggestion
                   FROM expression_answers a
                   WHERE a.question_id = ?
                   ORDER BY a.created_at DESC
                   LIMIT ?""",
                (question_id, limit),
            ).fetchall()
        return [_row_to_dict(r) for r in rows]
    finally:
        conn.close()


# ================================================================
# 辅助函数
# ================================================================

def _row_to_dict(row) -> dict:
    """行对象 → 普通 dict

    两个后端的行对象都支持 `dict()`：
      · SQLite：`sqlite3.Row`（由 row_factory 设置）
      · MySQL ：PyMySQL 的 `DictCursor` 本来就返回 `dict`（`dict(dict)` 是浅拷贝）

    所以这里不写死 `sqlite3.Row` 注解 —— 写了会让人以为只有 SQLite 能用。
    """
    return dict(row) if row else None