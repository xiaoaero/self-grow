"""
Self Grow — 建表语句的方言转换（SQLite DDL → MySQL DDL）

**为什么不让两边各写一份建表语句**：
    `db/init.py` 有 22 张表 + 8 个索引。写两份的话，以后改表结构要改两处，
    漏掉一处就是静默不一致 —— 这个项目里已经踩过好几次同类的坑
    （`CATEGORY_MAP` 抄 `CATEGORIES`、`DEFAULT_DIMENSIONS` 写死 150…）。
    所以这里保持**单一 DDL 源 + 转换**。

**转换规则（只有这几条，都是 SQLite/MySQL 的硬性语法差异）**：

| # | SQLite | MySQL | 为什么 |
|---|---|---|---|
| 1 | `INTEGER PRIMARY KEY AUTOINCREMENT` | `INT NOT NULL AUTO_INCREMENT PRIMARY KEY` | 语法不同。**用 INT 不用 BIGINT**：外键两侧类型必须完全一致，而子表的 `user_id INTEGER` 在 MySQL 里是 `INT` |
| 2 | `DEFAULT (datetime('now','localtime'))` | `DEFAULT (CURRENT_TIMESTAMP)` | 函数名不同（连接层已 `SET time_zone='+08:00'`，所以 CURRENT_TIMESTAMP 就是本地时间） |
| 3 | `DEFAULT (date('now'))` | `DEFAULT (CURRENT_DATE)` | 同上 |
| 4 | `col TEXT ... DEFAULT x` | `col VARCHAR(n) ... DEFAULT x` | ⚠️ **MySQL 的 TEXT/BLOB 不能有默认值**（36 处）。时间戳给 32，其余给 255 |
| 5 | `CREATE INDEX IF NOT EXISTS x` | `CREATE INDEX x` | MySQL 不支持索引的 IF NOT EXISTS（已存在时由连接层吞掉 1061 错误，等价于幂等） |
| 6 | `REAL` | `DOUBLE` | MySQL 的 REAL 是 DOUBLE 的别名，写清楚避免歧义 |

**不做转换的**：
  · 字符集 / 引擎 —— 依赖容器启动参数（`--character-set-server=utf8mb4`）
    与连接参数（`charset="utf8mb4"`）。建完后会实际查 information_schema 验证。
  · `FOREIGN KEY ... REFERENCES ...` —— 两边语法一致，且 init.py 里父表先建。
"""

import re

# ── 规则 1：自增主键 ──
# 注意用 INT 而不是 BIGINT：外键两侧类型必须完全一致，
# 子表的 `user_id INTEGER` 在 MySQL 里是 INT，主键若是 BIGINT 会报
# errno 3780（Referencing column and referenced column are incompatible）
_RE_AUTOINC = re.compile(
    r"INTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT",
    re.IGNORECASE,
)

# ── 规则 2/3：时间函数默认值 ──
_RE_DT_DEFAULT = re.compile(
    r"DEFAULT\s*\(\s*datetime\s*\(\s*'now'\s*,\s*'localtime'\s*\)\s*\)",
    re.IGNORECASE,
)
_RE_DATE_DEFAULT = re.compile(
    r"DEFAULT\s*\(\s*date\s*\(\s*'now'\s*\)\s*\)",
    re.IGNORECASE,
)

# ── 规则 4：TEXT 列若带「会与 MySQL 冲突」的约束 → VARCHAR ──
#
# MySQL 的两条硬限制：
#   (a) TEXT/BLOB 不能有 DEFAULT           → errno 1101
#   (b) TEXT/BLOB 不能当键（PK/UNIQUE/INDEX）→ errno 1170
# 所以只要 TEXT 列后面跟着 DEFAULT / UNIQUE / PRIMARY，就必须转 VARCHAR。
#
# ⚠️ 这里漏一个就会在建表时炸 —— 已经踩过两次（`desc` 的 DEFAULT、`tree_id` 的列级 UNIQUE）。
#    所以除了看列定义行，下面还有 _promote_key_columns() 扫表级键定义兜底。
_RE_TEXT_WITH_CONSTRAINT = re.compile(
    r"(?m)^([ \t]*)([`\"]?)(\w+)\2[ \t]+TEXT"
    r"(?=[ \t][^\n]*(?:DEFAULT|\bUNIQUE\b|\bPRIMARY\b))"
    r"([^\n]*)$",
    re.IGNORECASE,
)

# 兜底用：任意列定义行（不带约束判断），配合 _promote_key_columns 使用
_RE_ANY_TEXT_COLUMN = re.compile(
    r"(?m)^([ \t]*)([`\"]?)(\w+)\2[ \t]+TEXT([^\n]*)$",
    re.IGNORECASE,
)

# ── 规则 5：索引的 IF NOT EXISTS ──
_RE_INDEX_INE = re.compile(
    r"(CREATE\s+(?:UNIQUE\s+)?INDEX)\s+IF\s+NOT\s+EXISTS\s+",
    re.IGNORECASE,
)

# ── 规则 6：REAL → DOUBLE ──
_RE_REAL = re.compile(r"\bREAL\b", re.IGNORECASE)

# ── 规则 7：MySQL 保留字列名要加反引号 ──
#
# 用 `SELECT word FROM information_schema.keywords WHERE reserved = 1`（262 个）
# 跟项目里 101 个列名对了一遍，**只有两个冲突**：
#   · `desc`        （rewards / reward_drafts 两张表；MySQL 保留字）
#   · `year_month`  （user_monthly_stats；8.0 里是保留字）
#
# 为什么不干脆把列改名（`desc` → `description`）：
#   改名会牵连前后端约 20 处（SQL、Python 参数、API 字段 `reward.desc`、
#   前端 `rewards.js`），迁移期做这种横跨三层的重命名风险太大。
#   加反引号是零语义变更的做法。**等迁移稳了再考虑改名。**
_RESERVED_WORDS = ("desc", "year_month")

# ORDER BY 里的 DESC 是**关键字**，绝不能加反引号（加了就语法错误）。
# 项目里有 16 处 `ORDER BY xxx DESC`，所以必须先把它保护起来。
_ORDER_DESC_PLACEHOLDER = "\x00__ORDER_DESC__\x00"


def quote_reserved(sql: str) -> str:
    """给作为标识符的 MySQL 保留字加反引号

    做法：先按**行**把 `ORDER BY` 之后的 `DESC` 换成占位符（那是关键字），
    给剩下的加反引号，最后还原占位符。

    为什么按行判断就够：项目里的 `ORDER BY ... DESC` 都是单行写法。
    （已核实没有 16 处以外的 DESC 关键字用法。）
    """
    lines = []
    for line in sql.split("\n"):
        up = line.upper()
        idx = up.find("ORDER BY")
        if idx >= 0:
            head, tail = line[:idx], line[idx:]
            tail = re.sub(r"(?<![`\w])DESC(?![`\w])",
                          _ORDER_DESC_PLACEHOLDER, tail, flags=re.IGNORECASE)
            line = head + tail
        lines.append(line)
    sql = "\n".join(lines)

    for word in _RESERVED_WORDS:
        # 前后不能是反引号或单词字符，避免重复加引号 / 改到长词的一部分
        sql = re.sub(rf"(?<![`\w]){word}(?![`\w])", f"`{word}`", sql,
                     flags=re.IGNORECASE)

    return sql.replace(_ORDER_DESC_PLACEHOLDER, "DESC")


# ── 规则 8：DML 里的 SQLite 专有语法 ──
#
# `INSERT OR IGNORE INTO` 是 SQLite 的写法；MySQL 是 `INSERT IGNORE INTO`。
# ⚠️ 这个**没法靠改源码统一**：SQLite 不接受 `INSERT IGNORE`，
#    两边写法就是不同，只能转换。
#    语义一致：遇到唯一键冲突时静默跳过（不报错）。
#
# 已核实项目里只有这 2 处（都在 db/init.py 的维度 seed），
# 没有 OR REPLACE / OR ABORT / OR FAIL 等其它变体。
# （`INSERT OR REPLACE` 若要转 MySQL 得改写成 ON DUPLICATE KEY UPDATE，
#   两者语义有差别，所以不在这里自动转 —— 将来真要用请人工确认。）
_RE_INSERT_OR_IGNORE = re.compile(
    r"\bINSERT\s+OR\s+IGNORE\s+INTO\b",
    re.IGNORECASE,
)

# SQLite 的 upsert → MySQL 的 upsert
#
#   SQLite:  INSERT ... ON CONFLICT(user_id, date) DO UPDATE SET x = excluded.x
#   MySQL:   INSERT ... ON DUPLICATE KEY UPDATE x = VALUES(x)
#
# 两处语法差异都要改：冲突子句本身，以及 `excluded.` 这个 SQLite 专有的行别名。
# 项目里有 7 处（habits / users / rewards / routines / skill_tree / init / main）。
#
# ⚠️ 语义上有一点点差别：SQLite 只在**指定的那组列**冲突时才 upsert，
#    MySQL 是任意唯一键冲突都触发。项目里这些表都只有一组相关的唯一约束，
#    所以行为一致 —— 将来若给这些表加第二组 UNIQUE，要重新确认这里。
_RE_ON_CONFLICT = re.compile(
    r"ON\s+CONFLICT\s*\([^)]*\)\s+DO\s+UPDATE\s+SET",
    re.IGNORECASE,
)
_RE_EXCLUDED_ROW = re.compile(r"\bexcluded\.(\w+)", re.IGNORECASE)


def dml_to_mysql(sql: str) -> str:
    """DML（增删改查）里的 SQLite 专有写法 → MySQL

    这个要作用在**所有** SQL 上，不只是建表语句。

    已核实项目里只有这两类：
      · `INSERT OR IGNORE INTO`（2 处，db/init.py 的维度 seed）
      · `ON CONFLICT ... DO UPDATE SET` + `excluded.col`（7 处 upsert）
    没有 `DO NOTHING`、没有 `||` 字符串连接符。
    """
    sql = _RE_INSERT_OR_IGNORE.sub("INSERT IGNORE INTO", sql)
    sql = _RE_ON_CONFLICT.sub("ON DUPLICATE KEY UPDATE", sql)
    sql = _RE_EXCLUDED_ROW.sub(r"VALUES(\1)", sql)
    return sql


# 已经是 MySQL 方言的标记（用于幂等判断）
#
# ⚠️ 只能放**SQLite 语法里绝不会出现**的特征。
#    一开始我把 `VARCHAR(` 也放进来了，结果所有含 VARCHAR 的建表语句
#    （源码里为了兼容 MySQL 索引/主键，已经把 start_time / dimension_key
#    等列声明成 VARCHAR）都被判定成"已转换"而跳过，自增主键没被换掉，
#    建表直接报 1064。**SQLite 也接受 VARCHAR 语法**，所以它不能当标记。
_MYSQL_MARKERS = ("AUTO_INCREMENT", "ENGINE=")


def is_ddl(sql: str) -> bool:
    """这条 SQL 是不是建表/建索引语句"""
    head = sql.lstrip()[:24].upper()
    return head.startswith(("CREATE TABLE", "CREATE INDEX", "CREATE UNIQUE INDEX"))


def _text_with_default_to_varchar(m: re.Match) -> str:
    indent, quote, col, rest = m.group(1), m.group(2), m.group(3), m.group(4)
    upper = rest.upper()
    if "CURRENT_TIMESTAMP" in upper or "CURRENT_DATE" in upper:
        width = 32          # 'YYYY-MM-DD HH:MM:SS' 是 19 字符，留点余量
    else:
        width = 255         # 状态 / 类型 / 名称这类短文本
    return f"{indent}{quote}{col}{quote} VARCHAR({width}){rest}"


def _promote_key_columns(sql: str) -> str:
    """表级键定义里引用的 TEXT 列 → VARCHAR(255)

    兜底用：`PRIMARY KEY (a, b)` / `UNIQUE (a, b)` 里的列如果声明成 TEXT，
    MySQL 会报 1170。列级约束由 _RE_TEXT_WITH_CONSTRAINT 处理，这里管表级的。
    """
    keys = set()
    for grp in re.findall(
        r"(?:PRIMARY\s+KEY|UNIQUE|FOREIGN\s+KEY|KEY)\s*\(([^)]*)\)", sql, re.IGNORECASE
    ):
        for c in grp.split(","):
            keys.add(c.strip().strip("`\" ").split("(")[0].strip())
    if not keys:
        return sql

    def fix(m: re.Match) -> str:
        indent, quote, col, rest = m.group(1), m.group(2), m.group(3), m.group(4)
        if col not in keys or "VARCHAR" in rest.upper():
            return m.group(0)
        return f"{indent}{quote}{col}{quote} VARCHAR(255){rest}"

    return _RE_ANY_TEXT_COLUMN.sub(fix, sql)


def to_mysql_ddl(sql: str) -> str:
    """把 SQLite 建表语句翻成 MySQL 方言

    幂等：已经是 MySQL 方言（含 AUTO_INCREMENT / VARCHAR( / ENGINE=）的原样返回。
    """
    if any(mk in sql for mk in _MYSQL_MARKERS):
        return sql

    s = _RE_AUTOINC.sub("INT NOT NULL AUTO_INCREMENT PRIMARY KEY", sql)

    # ⚠️ 顺序重要：先把时间默认值换成 CURRENT_TIMESTAMP/CURRENT_DATE，
    #    规则 4 才能据此判断该给 VARCHAR(32) 还是 VARCHAR(255)
    s = _RE_DT_DEFAULT.sub("DEFAULT (CURRENT_TIMESTAMP)", s)
    s = _RE_DATE_DEFAULT.sub("DEFAULT (CURRENT_DATE)", s)

    s = _RE_TEXT_WITH_CONSTRAINT.sub(_text_with_default_to_varchar, s)
    s = _promote_key_columns(s)
    s = _RE_INDEX_INE.sub(r"\1 ", s)
    s = _RE_REAL.sub("DOUBLE", s)
    return s
