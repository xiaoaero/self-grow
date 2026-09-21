"""
SQL 方言静态检查（不连数据库，两个后端下都跑）

它拦的是**运行时方言转换层处理不了**的那些 MySQL 限制 ——
`db/dialect.py` 会自动改自增主键、TEXT 默认值、`ON CONFLICT`、保留字等，
但下面这些它是**不能自动改**的（自动改要么危险、要么得凭空造名字），
只能在源码层面要求写对：

  ① 派生表必须有别名
     MySQL:  errno 1248 «Every derived table must have its own alias»
     SQLite: 不要求
     → `FROM (SELECT ...)` 后面必须跟 `AS x`。

  ② 不要用 `INSERT OR REPLACE`
     SQLite 专有；MySQL 对应的 `REPLACE INTO` **语义不同**
     （它是 DELETE + INSERT，会触发外键级联、重置自增），
     不能机械转换，所以要求人工确认后再写。

背景（这条 lint 的由来）
------------------------
2026-09-20 SQLite → MySQL 迁移收尾时，`/api/expression/stats` 在 MySQL 下 500，
根因就是 ① —— 而且**测试全绿**：当时 150 个用例里没有一个打表达训练 API，
SQLite 又不报错。这类"只在另一个后端炸"的问题，静态检查比用例更划算。
"""

import io
import os
import re
import tokenize

import pytest

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SKIP_DIRS = {".pixi", "__pycache__", "tests"}


def strip_py_comments(src: str) -> str:
    """去掉 Python 注释，**保留字符串与行号**

    为什么必须做：`db/dialect.py` 里就有解释「不要用 `INSERT OR REPLACE`」
    的注释 —— 不剥注释的话，讲规则的文档反而会被规则判为违规。
    （实测第一次跑就误报了这一处。）

    用 `tokenize` 而不是按 `#` 切分：SQL 里完全可能出现 `#`，
    正则切会把字符串切断。tokenize 只丢 COMMENT token，STRING 原样保留；
    又因为 token 位置没变，行号仍然准确。
    """
    try:
        toks = [t for t in tokenize.generate_tokens(io.StringIO(src).readline)
                if t.type != tokenize.COMMENT]
        return tokenize.untokenize(toks)
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return src                      # 解析不了就按原样扫（宁可漏也不错杀）


# `)` 后面出现这些词时**不是**别名，是外层 SQL 关键字
NOT_ALIAS = {
    "SELECT", "WHERE", "GROUP", "ORDER", "LIMIT", "UNION", "ON", "JOIN",
    "HAVING", "SET", "VALUES", "INTO", "FROM", "AND", "OR", "LEFT", "RIGHT",
    "INNER", "OUTER", "CROSS", "AS", "USING",
}

# 别名后面不能再跟标识符字符。
# ⚠️ 不能用 `(?=$|[,\s)])` —— 三引号 SQL 里别名后面紧跟 `"""`，那样会漏判。
_ALIAS_RE = re.compile(r"\s*(?:AS\s+)?`?([A-Za-z_]\w*)`?(?![A-Za-z0-9_])")


def _py_files():
    for dirpath, dirnames, filenames in os.walk(BACKEND_DIR):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            if fn.endswith(".py"):
                p = os.path.join(dirpath, fn)
                yield os.path.relpath(p, BACKEND_DIR).replace(os.sep, "/"), p


def find_derived_tables_without_alias(src: str):
    """返回 [(行号, SQL 片段)]：所有没写别名的派生表"""
    out = []
    for m in re.finditer(r"\b(?:FROM|JOIN)\s*\(", src, re.IGNORECASE):
        # 只关心真正的子查询：括号后（跳过任意空白，含换行 + 深缩进）是 SELECT，
        # 或者是 f-string 拼接的 `{base_sql}`。
        # ⚠️ 探测切片不能太短 —— 换行 + 16 空格就能吃掉十几个字符，
        #    切 12 个再 lstrip 会得到空串，于是真正的 bug 被静默跳过。
        head = src[m.end():m.end() + 200]
        if not (re.match(r"\s*SELECT\b", head, re.IGNORECASE)
                or re.match(r"\s*\{", head)):
            continue

        # 手动配对括号
        i, depth = m.end() - 1, 0
        while i < len(src):
            if src[i] == "(":
                depth += 1
            elif src[i] == ")":
                depth -= 1
                if depth == 0:
                    break
            i += 1

        am = _ALIAS_RE.match(src[i + 1:i + 80])
        if am and am.group(1).upper() not in NOT_ALIAS:
            continue

        out.append((src[:m.start()].count("\n") + 1,
                    re.sub(r"\s+", " ", src[m.start():i + 1])[:150]))
    return out


# ================================================================
# 规则 ①：派生表必须有别名
# ================================================================

def test_no_derived_table_without_alias():
    """MySQL 强制派生表带别名，SQLite 不强制 —— 要求源码里一律写全

    这条是真实踩坑后加的：`/api/expression/stats` 在 MySQL 下 500，
    SQLite 下却一直好好的。
    """
    problems = []
    for rel, path in _py_files():
        src = strip_py_comments(
            io.open(path, encoding="utf-8", errors="ignore").read())
        for line, snippet in find_derived_tables_without_alias(src):
            problems.append(f"  {rel}:{line}\n      {snippet}")

    assert not problems, (
        "以下派生表没有别名 —— MySQL 会报 1248（Every derived table must have "
        "its own alias）：\n" + "\n".join(problems)
    )


def test_lint_rule1_is_actually_sensitive():
    """自检：确认上面的规则**不是永远返回空**（假的绿灯比红灯更危险）

    用一个已知坏例 + 一个已知好例验证。如果没有这条，规则写错了也看不出来。
    """
    bad = 'conn.execute("""SELECT AVG(x) FROM (\n    SELECT x FROM t LIMIT 3\n)""")'
    good = 'conn.execute("""SELECT AVG(x) FROM (\n    SELECT x FROM t LIMIT 3\n) AS recent""")'
    dynamic_bad = 'sql = f"SELECT COUNT(*) FROM ({base_sql} {having})"'

    assert find_derived_tables_without_alias(bad), "坏例没被检出 —— 规则失效了"
    assert not find_derived_tables_without_alias(good), "好例被误报 —— 规则太严"
    assert find_derived_tables_without_alias(dynamic_bad), "动态拼接的坏例没被检出"


# ================================================================
# 规则 ②：不要用 INSERT OR REPLACE
# ================================================================

def test_no_insert_or_replace():
    """`INSERT OR REPLACE` 不能机械转成 MySQL

    MySQL 的 `REPLACE INTO` 是「先 DELETE 再 INSERT」：会触发外键级联删除、
    也会把没写到的列重置为默认值。与 SQLite 的 `INSERT OR REPLACE` 在
    「部分列更新」场景下行为不同，所以不放进 `db/dialect.py` 自动转换 ——
    真要 upsert 请用 `ON CONFLICT ... DO UPDATE` 或 `ON DUPLICATE KEY UPDATE`。
    """
    hits = []
    for rel, path in _py_files():
        src = strip_py_comments(
            io.open(path, encoding="utf-8", errors="ignore").read())
        for m in re.finditer(r"INSERT\s+OR\s+REPLACE", src, re.IGNORECASE):
            hits.append(f"  {rel}:{src[:m.start()].count(chr(10)) + 1}")

    assert not hits, (
        "发现 INSERT OR REPLACE —— 它没有 MySQL 等价物，请改用 upsert：\n"
        + "\n".join(hits)
    )


def test_lint_rule2_is_actually_sensitive():
    assert re.search(r"INSERT\s+OR\s+REPLACE", "INSERT OR REPLACE INTO t VALUES (1)")
    assert not re.search(r"INSERT\s+OR\s+REPLACE", "INSERT INTO t VALUES (1)")


def test_comment_stripping_keeps_code_and_line_numbers():
    """剥注释后：注释内容消失、代码与字符串保留、行号不变

    这条是给上面两个规则兜底的 —— 一旦剥注释把字符串也吃掉，
    规则会变成永远通过（假绿灯），那比误报更危险。
    """
    src = (
        "# 说明：不要用 INSERT OR REPLACE\n"
        "SQL = 'INSERT INTO t VALUES (1)'   # 行尾注释\n"
    )
    out = strip_py_comments(src)
    assert "INSERT OR REPLACE" not in out, "注释没被剥掉"
    assert "INSERT INTO t VALUES (1)" in out, "字符串被误伤"
    assert out.count("\n") == src.count("\n"), "行数变了，行号会错位"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
