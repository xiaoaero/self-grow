"""
SQL 方言静态检查（不连数据库）

职责在 2026-09-23 **反转**过一次，值得记一笔：

  之前 —— 项目同时支持 SQLite 与 MySQL，`db/dialect.py` 把 SQLite 写法自动转成
          MySQL。这个文件负责拦住**它转不了**的那几条（派生表别名、
          `INSERT OR REPLACE`），因为那些只能在源码层面写对。

  现在 —— SQLite 已被彻底移除（连接层、方言层、DDL、占位符全部原生化为 MySQL）。
          `db/dialect.py` 已删除，SQL 的自动转换**没有任何兜底了**。
          于是这个文件的职责变成：**拦住任何 SQLite 写法的回退**。

          ⚠️ 它现在是唯一的护栏。少了它，写回 `?` 或 `AUTOINCREMENT` 会一路过到
          真连上 MySQL 才报 1064 —— 而且往往落在测试没覆盖的那条路径上
          （历史上 `/api/expression/stats` 就是这么 500 的）。
"""

import ast
import io
import os
import re


SQL_KW = re.compile(r"\b(SELECT|INSERT|UPDATE|DELETE|CREATE|DROP|ALTER|REPLACE)\b", re.I)


def _py_files():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out = []
    for dp, dn, fn in os.walk(root):
        # 排除 archive/ —— 已归档的一次性脚本（如 SQLite 迁移工具）不参与 lint，
        # 它们本来就该保留 SQLite 写法（那是它们的工作对象）。
        dn[:] = [d for d in dn
                 if d not in {".pixi", "__pycache__", ".pytest_cache", "node_modules", "archive"}]
        for f in fn:
            if f.endswith(".py"):
                out.append(os.path.join(dp, f))
    return sorted(out)


def _docstrings(tree):
    """收集文件里所有 docstring 的**原文**

    为什么要单独挑出来：本文件要拦的是「SQL 里出现了 SQLite 写法」，
    而 `db/backend.py` 的模块 docstring 里**专门列举**了这些写法
    （"`? → %s`、`AUTOINCREMENT → AUTO_INCREMENT`、`INSERT OR IGNORE`…"）
    作为历史说明 —— 那是文档，不是代码，必须排除，否则护栏第一天就误报自己。
    """
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            d = ast.get_docstring(node, clean=False)
            if d:
                out.add(d)
    return out


def _string_literals(path):
    """返回 [(行号, 内容)] —— 源码里所有非 docstring 的字符串常量"""
    src = io.open(path, encoding="utf-8").read()
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return []
    docs = _docstrings(tree)
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.value in docs:
                continue
            out.append((node.lineno, node.value))
    return out


def _sql_text_units(path):
    """返回 [(行号, 文本)] —— 普通字符串常量 **+ 整条 f-string**

    ⚠️ 为什么要单独把 f-string 拎出来（2026-09-23 补，是真漏过一次的洞）：

    `_string_literals` 只取 `ast.Constant`；而 Python 3.12 起 f-string 是一棵
    `JoinedStr`，会被拆成若干个 `Constant` 片段。于是这句：

        f"UPDATE t SET {cols}, updated_at = datetime('now','localtime') WHERE id = %s"
           └─ 片段 1 里有 SQL 关键字 ─┘  └─ 违规在片段 2，但片段 2 没有关键字 ─┘

    准入判断 `if not SQL_KW.search(s): continue` 一挡 —— **违规整条溜过去**。

    真实后果：`db/model_configs.py` 里那句走了同一个模式，于是
    `PUT /api/model-configs/{id}` 直接 500（`pymysql.err.ProgrammingError 1064`，
    `near '('now','localtime')`）。它偏偏是 f-string 也不是巧合 ——
    动态 SET 子句基本只能用 f-string 拼，**洞正好开在所有动态 UPDATE 上**。

    这里用 `get_source_segment()` 取整条 f-string 的**原文**，
    关键字与违规就落在同一个字符串里，规则组 A 的全部规则自动生效。
    """
    src = io.open(path, encoding="utf-8").read()
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return []
    # 常量部分复用 `_string_literals()`（工具函数只有一份，别抄第二遍）
    out = list(_string_literals(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.JoinedStr):
            seg = ast.get_source_segment(src, node)
            if seg:
                out.append((node.lineno, seg))
    return out


# 原来这里有个 `_read(path)`（直接返回文件原文）。改用 `_masked_lines()` 之后
# 就没有调用方了，已于 2026-09-23 删除 —— 原因看下面 `_masked_lines` 的说明：
# 直接读原文会把 docstring 里**有意列举**的 SQLite 写法也当成违规。


def _masked_lines(path):
    """返回"清空注释与 docstring 之后"的源码，**行号保持不变**

    ⚠️ 这一步是必须的，不是可选优化：
    本文件自己和 `db/backend.py` 的文档里**专门列举**了那些 SQLite 写法
    （"`? → %s`、`AUTOINCREMENT → AUTO_INCREMENT`、`INSERT OR IGNORE`…"）
    作为历史说明 —— 不遮掉的话，护栏第一天就会把自己的说明书判成违规。

    行内注释只截掉 `#` 之后的部分（不能整行清空，那会把行内代码也丢掉）；
    docstring 才是整行清空。
    """
    import tokenize

    src = io.open(path, encoding="utf-8").read()
    lines = src.split("\n")
    try:
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type == tokenize.COMMENT:
                r, c = tok.start
                lines[r - 1] = lines[r - 1][:c]
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                b = node.body[0] if node.body else None
                if (isinstance(b, ast.Expr) and isinstance(b.value, ast.Constant)
                        and isinstance(b.value.value, str)):
                    for i in range(b.value.lineno - 1, min(b.value.end_lineno, len(lines))):
                        lines[i] = ""
    except Exception:
        pass
    return "\n".join(lines)


def _is_self(path):
    return os.path.relpath(path).replace("\\", "/").endswith("test_sql_dialect_lint.py")


def _has_cjk(s: str) -> bool:
    """是否含中日韩字符

    ⚠️ 存在的理由：`_sql_text_units()` 会把**整条 f-string** 拿来检查，
    而 f-string 里常常混着提示文案（`f"删除 {name} 失败，是否重试?"`）——
    这类字符串一旦含 `SELECT`/`DELETE` 之类的词就会被准入判断放行，
    再被 `?` 规则误报。SQL 语句里不会出现中文，用它当过滤器最省事也最准。
    """
    return bool(re.search(r"[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]", s))


# ================================================================
# 规则组 A：SQLite 残留（新增，2026-09-23）
# ================================================================
# 每条：(正则, 叫什么, 应该用什么)
SQLITE_RESIDUE_IN_SQL = [
    (r"\bAUTOINCREMENT\b", "AUTOINCREMENT", "AUTO_INCREMENT"),
    (r"INSERT\s+OR\s+IGNORE", "INSERT OR IGNORE", "INSERT IGNORE"),
    (r"INSERT\s+OR\s+REPLACE", "INSERT OR REPLACE", "ON DUPLICATE KEY UPDATE（语义不同，见规则 ②）"),
    (r"\bON\s+CONFLICT\b", "ON CONFLICT", "ON DUPLICATE KEY UPDATE"),
    (r"datetime\s*\(\s*'now'", "datetime('now')", "now() 或 utc_timestamp()"),
    (r"date\s*\(\s*'now'", "date('now')", "curdate()"),
    (r"CREATE\s+(?:UNIQUE\s+)?INDEX\s+IF\s+NOT\s+EXISTS",
     "CREATE INDEX IF NOT EXISTS", "mysql 不支持 IF NOT EXISTS（靠吞 1061 保证幂等）"),
    (r"\bPRAGMA\b", "PRAGMA", "information_schema"),
    (r"\bsqlite_master\b", "sqlite_master", "information_schema.tables"),
    (r"\bexcluded\.\w+", "excluded.col", "VALUES(col)"),
]

# 这些是 SQLite 专有的**拼接/DDL**写法，出现在 SQL 字符串里就一定是残留
SQL_LEVEL_ONLY = {"?"}


# ================================================================
# 规则组 B：MySQL 保留字列名必须加反引号（2026-09-23 新增）
# ================================================================

# 库里**确实是 MySQL 8.0 保留字**的列名。测法：把 information_schema 里的
# 全部列名（120 个）与 MySQL 保留字表比对，只有这 2 个撞上。
#
# 为什么必须有这条规则：这个反引号原来是 `db/dialect.py::quote_reserved()`
# **自动**加的（它还刻意保护 `ORDER BY ... DESC`，因为那里 DESC 是排序方向，
# 加反引号反而 1064）。方言层随 SQLite 一起删掉后**没有兜底了** ——
# 漏一个就是运行时 1064，且只有真的走到那条 SQL 才会炸，测试不一定覆盖得到。
#
# 维护：库结构变动时重新跑
#   SELECT DISTINCT column_name FROM information_schema.columns
#   WHERE table_schema = DATABASE()
# 再与 MySQL 保留字表比对即可。
RESERVED_COLUMN_NAMES = ("year_month", "desc")


def _strip_order_by(sql: str) -> str:
    """去掉 ORDER BY 子句

    ⚠️ 必须剥离：`ORDER BY created_at DESC` 里的 DESC 是**排序方向**，
    加反引号会变成 1064。不剥的话所有正常的倒序查询都会被误报。
    （原方言层的 `quote_reserved()` 里也有同款保护。）
    """
    return re.sub(r"ORDER\s+BY\b[\s\S]*?(?=\bLIMIT\b|$)", "", sql, flags=re.I)


def _unquoted_reserved_columns(sql: str) -> list:
    """返回 SQL 里裸用的保留字列名

    ⚠️ 用 `\\bdesc\\b`（区分大小写）而不是 re.I：
    靠**大小写**区分 `desc` 的两种身份 ——
      · 列名 → 源码里一律写小写 `desc`（`` `desc` ``）
      · 排序方向 → 一律写大写 `DESC`
    这是 SQL 社区惯例（关键字大写、标识符小写），本项目一直如此。
    加 re.I 的话 `ORDER BY x DESC` 会被误报（那正是要避免的方向）。
    """
    out = []
    for col in RESERVED_COLUMN_NAMES:
        if re.search(r"(?<!`)\b" + re.escape(col) + r"\b(?!`)", sql):
            out.append(col)
    return out


def test_reserved_column_names_are_backquoted():
    """MySQL 保留字列名必须加反引号

    实测踩到：`... FROM user_monthly_stats ORDER BY year_month DESC` → **1064**
    （`YEAR_MONTH` 和 `DESC` 都是 MySQL 8.0 保留字）。
    """
    problems = []
    for path in _py_files():
        if _is_self(path):
            continue
        for lineno, s in _sql_text_units(path):
            if not SQL_KW.search(s):
                continue
            rel = os.path.relpath(path)
            for col in _unquoted_reserved_columns(_strip_order_by(s)):
                problems.append(f"  {rel}:{lineno}  裸 {col}  → 应写成 `{col}`")
    assert not problems, (
        "以下 MySQL 保留字列名没加反引号 —— 会报 1064。"
        "db/dialect.py 已删除，不再自动加：\n" + "\n".join(sorted(set(problems))[:30])
    )


def test_lint_rule_reserved_columns_is_sensitive():
    """护栏自测：上面那条规则必须真的抓得到违规，且不误报正确写法

    ⚠️ 别删。写派生表检查时就是因为少了自测，
    括号计数起始深度写成 0，导致**连正确写法也被报错**（规则彻底失效还看不出来）。
    """
    # ① ORDER BY 子句要被剥离掉（DESC 是方向，不是列名）
    #    注意 LIMIT 会保留 —— 剥离用的是 lookahead（`(?=LIMIT|$)`），
    #    只吃掉 ORDER BY 那一段，不消费后面的关键字。
    assert _strip_order_by("SELECT a FROM t ORDER BY a DESC LIMIT 5") \
        == "SELECT a FROM t LIMIT 5"

    # ② 裸列名必须被抓住
    bad = "SELECT desc FROM rewards WHERE year_month = %s"
    hits = _unquoted_reserved_columns(_strip_order_by(bad))
    assert "desc" in hits and "year_month" in hits, f"灵敏度不足，只抓到 {hits}"

    # ③ 已加反引号的不能被误报
    good = "SELECT `desc` FROM rewards WHERE `year_month` = %s"
    hits_ok = _unquoted_reserved_columns(_strip_order_by(good))
    assert not hits_ok, f"正确写法被误报：{hits_ok}"

    # ④ 正常的倒序查询不能被误报（这条最容易写坏）
    order = "SELECT a FROM t ORDER BY created_at DESC, id DESC"
    assert not _unquoted_reserved_columns(_strip_order_by(order)), "倒序查询被误报"


def test_no_sqlite_residue_in_sql_strings():
    """SQL 字面量里不得出现任何 SQLite 写法

    方言层删除后没有兜底了：这些写法会原样发给 MySQL，
    报 1064 / 1064 / 1170 之类，而且**本地用 SQLite 跑测试也发现不了**
    （因为已经没有 SQLite 通路了，只会在连 MySQL 时炸）。
    """
    problems = []
    for path in _py_files():
        if _is_self(path):
            continue          # 本文件里有"反例样本"，见 _masked_lines 的说明
        for lineno, s in _sql_text_units(path):
            if not SQL_KW.search(s):
                continue
            rel = os.path.relpath(path)
            for pat, name, fix in SQLITE_RESIDUE_IN_SQL:
                if re.search(pat, s, re.I):
                    problems.append(f"  {rel}:{lineno}  {name}  → 应为 {fix}")
            # `?` 只在「看起来是 SQL」的字符串里检查 ——
            # 普通文案里的问号（"确定要删除吗?"）不该被误报。
            # 另：SQL 里不会出现中文，含中文的直接放过（f-string 会带上提示文案）
            if "?" in s and not _has_cjk(s):
                problems.append(f"  {rel}:{lineno}  ? 占位符  → 应为 %s")
    assert not problems, (
        f"发现 {len(problems)} 处 SQLite 残留 —— 项目已只支持 MySQL，"
        "db/dialect.py 已删除，没有自动转换兜底了：\n" + "\n".join(problems[:30])
    )


def test_no_sqlite_imports():
    """代码里不得再 import sqlite3

    允许在**注释与 docstring** 里提"（原来的 sqlite3.Connection 才有）"这类历史说明，
    但代码路径里不能真的依赖它。
    """
    problems = []
    for path in _py_files():
        rel = os.path.relpath(path)
        if _is_self(path):
            continue
        # 用 _masked_lines：注释与 docstring 里提到 sqlite3 是**有意的历史说明**
        # （"代理是为了补上 sqlite3.Connection 才有的 execute()"），不该判违规
        for i, ln in enumerate(_masked_lines(path).split("\n"), 1):
            if re.search(r"\bimport\s+sqlite3\b|\bsqlite3\.(Row|connect)\b", ln):
                problems.append(f"  {rel}:{i}  {ln.strip()[:80]}")
    assert not problems, (
        "代码里还有 sqlite3 依赖：\n" + "\n".join(problems)
    )


def test_no_placeholders_outside_sql_strings():
    """整个项目（非 docstring 字符串）里不该再有 SQL 的 `?` 占位符

    与上一条的区别：这条**不要求字符串含 SQL 关键字**，
    覆盖那些"只有一句 WHERE 片段"的短字符串。
    """
    problems = []
    for path in _py_files():
        rel = os.path.relpath(path)
        if rel.replace("\\", "/").endswith("test_sql_dialect_lint.py"):
            continue
        for lineno, s in _sql_text_units(path):
            if not SQL_KW.search(s):
                continue
            if _has_cjk(s):
                continue
            if re.search(r"[,\s(]\s*\?", s) or re.search(r"\?\s*[,)]", s) or s.strip() == "?":
                problems.append(f"  {rel}:{lineno}  {s.strip()[:70]!r}")
    assert not problems, "还有 ? 占位符：\n" + "\n".join(problems[:20])


def test_lint_sees_inside_fstrings(tmp_path):
    """护栏自测：**f-string 里的 SQL 也必须被检查**

    这是真漏过一次的洞，别删。成因见 `_sql_text_units()` 的 docstring：
    f-string 被 AST 拆成多个 `Constant` 片段，「有 SQL 关键字」与「有 SQLite 写法」
    落在不同片段 → 准入判断一挡，违规整条溜过去。

    真实后果就是本次这个 bug：`db/model_configs.py` 里
    `f"UPDATE model_configs SET {...}, updated_at = datetime('now','localtime') WHERE id = %s"`
    → `PUT /api/model-configs/{id}` 直接 500
    （`pymysql.err.ProgrammingError: (1064, ... near '('now','localtime') WHERE id = 3'`）。
    """
    bad = tmp_path / "bad.py"
    bad.write_text(
        'def f(cols, cid):\n'
        '    conn.execute(\n'
        "        f\"UPDATE t SET {', '.join(cols)}, updated_at = datetime('now','localtime') WHERE id = %s\",\n"
        '        (cid,),\n'
        '    )\n',
        encoding="utf-8",
    )
    hits = [(n, s) for n, s in _sql_text_units(str(bad))
            if SQL_KW.search(s) and re.search(r"datetime\s*\(\s*'now'", s, re.I)]
    assert hits, (
        "f-string 里的 datetime('now') 没被检查到 —— 这个洞曾经放过一次线上 500。"
        "检查 `_sql_text_units()` 是否还被改回了只看 ast.Constant。"
    )

    # 反向：含中文的 f-string 不该因为「出现了 SELECT 字样」被 `?` 规则误报
    ok = tmp_path / "ok.py"
    ok.write_text(
        'def g(msg):\n'
        '    raise ValueError(f"查询 SELECT 失败：{msg}，要重试?")\n',
        encoding="utf-8",
    )
    noise = [(n, s) for n, s in _sql_text_units(str(ok))
             if SQL_KW.search(s) and "?" in s and not _has_cjk(s)]
    assert not noise, f"含中文的提示文案被误报成 ? 占位符：{noise}"


def test_lint_rule_sqlite_residue_is_sensitive():
    """护栏自身要有效：喂给它一段 SQLite 写法必须能查出来"""
    for sample in ["INSERT OR IGNORE INTO t VALUES (?)",
                   "INSERT INTO t VALUES (?)",
                   "ON CONFLICT(a) DO UPDATE SET x = excluded.x",
                   "SELECT datetime('now')",
                   "CREATE INDEX IF NOT EXISTS i ON t(c)",
                   "SELECT * FROM sqlite_master"]:
        hit = (any(re.search(p, sample, re.I) for p, _, _ in SQLITE_RESIDUE_IN_SQL)
               or "?" in sample)
        assert hit, f"护栏漏掉了：{sample}"


# ================================================================
# 规则组 B：MySQL 自身的限制（保留原有两条，与 SQLite 无关）
# ================================================================
def strip_py_comments(src: str) -> str:
    """去掉 Python 的 `#` 注释与三引号字符串里的说明文本，保留行号

    ⚠️ 必须剥掉，否则本文件会把**解释这些规则的注释本身**判成违规
    （`db/backend.py` 与 `test_sql_dialect_lint.py` 里都有这种说明）。
    """
    try:
        import tokenize

        out = []
        lines = src.split("\n")
        got = set()
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type == tokenize.COMMENT:
                got.add(tok.start[0])
        for i, ln in enumerate(lines, 1):
            if i in got:
                out.append(ln[:ln.index("#")] if "#" in ln else ln)
            else:
                out.append(ln)
        return "\n".join(out)
    except Exception:
        return src


# `)` 后面出现这些词时**不是**别名，是外层 SQL 关键字
_NOT_ALIAS = {
    "WHERE", "ON", "GROUP", "ORDER", "LIMIT", "OFFSET", "HAVING", "UNION",
    "JOIN", "LEFT", "RIGHT", "INNER", "OUTER", "AND", "OR", "SET", "VALUES",
    "SELECT", "FROM", "INSERT", "UPDATE", "DELETE", "AS", "DO", "NOT", "IN",
}


def find_derived_tables_without_alias(src: str):
    """返回 [(行号, SQL 片段)]：所有没写别名的派生表"""
    stripped = strip_py_comments(src)
    out = []
    for m in re.finditer(r"FROM\s*\(\s*(SELECT\b)", stripped, re.I):
        start = m.start(1)
        # 找与之匹配的右括号。
        # ⚠️ 起始 depth 必须是 **1**，不能是 0 ——
        #    我们是从 `FROM (` 里那个 `SELECT` 之后开始扫的，此刻已经在那对括号**内部**了。
        #    写成 0 的话：第一个 `)` 会把 depth 减到 -1，而 `if depth == 0` 永远不成立，
        #    于是一路扫到文件末尾，`after` 取到完全无关的内容 →
        #    **连本来写了别名的派生表也被报成"没别名"**（第一版就是这样，护栏自己的
        #    "灵敏度测试"当场把它抓出来了 —— 这也说明那条自测用例值得留）。
        depth = 1
        i = m.end()
        while i < len(stripped):
            if stripped[i] == "(":
                depth += 1
            elif stripped[i] == ")":
                depth -= 1
                if depth == 0:
                    break
            i += 1
        after = stripped[i + 1:i + 40].strip()
        nxt = re.match(r"(?:AS\s+)?([A-Za-z_]\w*)", after, re.I)
        if not nxt or nxt.group(1).upper() in _NOT_ALIAS:
            lineno = stripped[:start].count("\n") + 1
            out.append((lineno, stripped[start:start + 60].replace("\n", " ")))
    return out


def test_no_derived_table_without_alias():
    """MySQL 强制派生表带别名（errno 1248），SQLite 不强制 —— 要求源码里一律写全

    历史：2026-09-20 迁移收尾时 `/api/expression/stats` 在 MySQL 下 500 就是这个 ——
    而且当时**测试全绿**（150 个用例里没有一个打那个接口，SQLite 又不报错）。
    """
    problems = []
    for path in _py_files():
        rel = os.path.relpath(path)
        if rel.replace("\\", "/").endswith("test_sql_dialect_lint.py"):
            continue
        for lineno, frag in find_derived_tables_without_alias(_masked_lines(path)):
            problems.append(f"  {rel}:{lineno}  {frag}")
    assert not problems, (
        "以下派生表没有别名 —— MySQL 会报 1248（Every derived table must have "
        "its own alias），SQLite 不报，所以本地开发发现不了：\n" + "\n".join(problems)
    )


# ================================================================
# 规则组 C：不许再手写 `?` 占位符生成器（2026-09-24）
# ================================================================

# 这些**子串**出现在代码里 = 有人在手搓 `IN (...)` 的占位符。
# 判子串而不是正则：可读性优先，也避免转义把人绕晕。
PLACEHOLDER_GEN_FRAGMENTS = (
    'join("?"', "join('?'",
    '"?" *', "'?' *",
    '"?" +', "'?' +",
    '"?" for', "'?' for",
)


def _docstring_lines(path):
    """返回属于 docstring 的行号集合（说明文字里的"反例"不算违规）"""
    src = io.open(path, encoding="utf-8").read()
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return set()
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = getattr(node, "body", None)
            if not body:
                continue
            first = body[0]
            if (isinstance(first, ast.Expr)
                    and isinstance(first.value, ast.Constant)
                    and isinstance(first.value.value, str)):
                out.update(range(first.lineno, (first.end_lineno or first.lineno) + 1))
    return out


def test_no_handmade_question_mark_placeholders():
    """不许手写 `"?" * n` / `("?" for _ in xs)` —— 统一用 `db.connection.placeholders(n)`

    ⚠️ 为什么必须单独一条规则（2026-09-24 真实事故）：

        ph = ",".join("?" * len(repos))          # 看着毫无问题
        conn.execute(f"... WHERE repo IN ({ph})", repos)
        → pymysql: not all arguments converted during string formatting

    表现是「AI 分析」每次打开都失败（后台任务报错，接口仍 200），
    而且**只在有上榜仓库时**才触发 —— 空库时测不出来。

    ⚠️ 更关键的是：**现有的字符串扫描根本抓不到它**。
    `?` 是**运行时拼出来的**：源码里的常量只是 `"?"`（不含 SQL 关键字 →
    被准入判断放掉），而带 SQL 关键字的那一句里只有 `{ph}`，
    连 f-string 取样（`_sql_text_units`）也救不了 —— 那里只有 `{ph}` 两个字符。

    ⇒ 动态占位符这类问题，靠"扫 SQL 文本"是无解的，
    只能靠**唯一入口** + 这条"不许手搓"的规则。
    """
    problems = []
    for path in _py_files():
        rel = os.path.relpath(path)
        if rel.replace("\\", "/").endswith("test_sql_dialect_lint.py"):
            continue                      # 本文件里这些是"反例"，见上面的常量
        skip = _docstring_lines(path)     # docstring 里的示例也不算
        src = io.open(path, encoding="utf-8").read()
        for lineno, line in enumerate(src.split("\n"), 1):
            if lineno in skip:
                continue
            code = line.split("#", 1)[0]
            for frag in PLACEHOLDER_GEN_FRAGMENTS:
                if frag in code:
                    problems.append(
                        f"  {rel}:{lineno}  {line.strip()[:70]}"
                        f"   → 改用 placeholders(n)"
                    )
                    break
    assert not problems, (
        "发现手搓的 `?` 占位符 —— MySQL 下会报 "
        "「not all arguments converted during string formatting」，"
        "而且是运行时才炸、静态扫 SQL 文本扫不到：\n" + "\n".join(problems)
    )


def test_placeholders_helper_is_the_only_source():
    """`db.connection.placeholders()` 必须存在且行为正确"""
    from db.connection import placeholders
    assert placeholders(3) == "%s,%s,%s"
    assert placeholders(1) == "%s"
    assert placeholders(0) == ""


def test_placeholder_rule_is_actually_sensitive(tmp_path):
    """自测：把违规写法放回去，这条规则必须能抓到"""
    bad = tmp_path / "bad.py"
    bad.write_text(
        'def f(repos):\n'
        '    ph = ",".join("?" * len(repos))\n'
        '    conn.execute(f"SELECT 1 WHERE repo IN ({ph})", repos)\n',
        encoding="utf-8",
    )
    hits = []
    for lineno, line in enumerate(bad.read_text(encoding="utf-8").split("\n"), 1):
        for frag in PLACEHOLDER_GEN_FRAGMENTS:
            if frag in line.split("#", 1)[0]:
                hits.append(lineno)
                break
    assert hits == [2], f"没抓到（或抓错了行）：{hits}"

    # 反向：docstring 里写同样的反例**不该**被判违规
    ok = tmp_path / "ok.py"
    ok.write_text(
        'def g(repos):\n'
        '    """示例：ph = ",".join("?" * len(repos))  ← 这是错的，别学"""\n'
        '    from db.connection import placeholders\n'
        '    return placeholders(len(repos))\n',
        encoding="utf-8",
    )
    skip = _docstring_lines(str(ok))
    bad_lines = [
        i for i, line in enumerate(ok.read_text(encoding="utf-8").split("\n"), 1)
        if i not in skip and any(f in line.split("#", 1)[0] for f in PLACEHOLDER_GEN_FRAGMENTS)
    ]
    assert not bad_lines, f"docstring 里的反例被误判：{bad_lines}"


def test_lint_rule1_is_actually_sensitive():
    bad = 'cursor.execute("SELECT AVG(x) FROM (SELECT x FROM t LIMIT 5)")'
    good = 'cursor.execute("SELECT AVG(x) FROM (SELECT x FROM t LIMIT 5) AS recent")'
    assert find_derived_tables_without_alias(bad), "没查出缺别名的派生表"
    assert not find_derived_tables_without_alias(good), "带别名的被误报了"


def test_no_insert_or_replace():
    """`INSERT OR REPLACE` 没有 MySQL 等价物，不能机械转换

    MySQL 的 `REPLACE INTO` 是 DELETE + INSERT —— 会触发外键级联、重置自增、
    也会把没写到的列重置为默认值，语义与 SQLite 的 `INSERT OR REPLACE` 不同。
    """
    problems = []
    for path in _py_files():
        rel = os.path.relpath(path)
        if rel.replace("\\", "/").endswith("test_sql_dialect_lint.py"):
            continue
        stripped = strip_py_comments(_masked_lines(path))
        for m in re.finditer(r"INSERT\s+OR\s+REPLACE", stripped, re.I):
            lineno = stripped[:m.start()].count("\n") + 1
            problems.append(f"  {rel}:{lineno}")
    assert not problems, (
        "发现 INSERT OR REPLACE —— 它没有 MySQL 等价物，请改用 upsert：\n"
        + "\n".join(problems)
    )


def test_lint_rule2_is_actually_sensitive():
    assert re.search(r"INSERT\s+OR\s+REPLACE", "INSERT OR REPLACE INTO t VALUES (1)")


def test_comment_stripping_keeps_code_and_line_numbers():
    src = "a = 1\n# 说明：不要用 INSERT OR REPLACE\nb = 2\n"
    out = strip_py_comments(src)
    assert "INSERT OR REPLACE" not in out, "注释没被剥掉"
    assert len(out.split("\n")) == len(src.split("\n")), "行号必须保持"
