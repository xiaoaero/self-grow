# SQLite → MySQL 迁移方案

> ✅ **2026-09-19 已完成**。实际结果与本文档的差异、以及 10 个"跑起来才炸"的坑，
> 记录在 `.workbuddy/memory/2026-09-19.md`。本文档保留为方案设计与决策依据。
>
> 一句话状态：**双后端可用** —— `SELF_GROW_DB_BACKEND=sqlite|mysql` 切换，
> SQLite 150 passed、MySQL 141 passed + 9 skipped（skip 的是检查 SQLite 元数据的用例），
> 数据 1304 行迁移后一致性核对全通过。

> 2026-09-19 制定。基于对现有代码的**实测侦察**（不是估），所有数字可复算。

## 零、你本地容器的现状（实测）

```
容器     mysql8-local（mysql:8.0）
状态     running，已映射 0.0.0.0:3306
数据卷   mysql_local_data → /var/lib/mysql
字符集   --character-set-server=utf8mb4 --collation-server=utf8mb4_unicode_ci   ✅ 已设对
库名     MYSQL_DATABASE=ai_project
时区     ❌ 既没有 TZ 环境变量，也没有 --default-time-zone
```

**唯一的问题就是时区**：容器跑在 UTC，所以 `NOW()` / `CURRENT_TIMESTAMP`
返回的是 UTC 时间，会比本地时间**早 8 小时**。
本项目全项目统一「本地时间」，这个不一致会重演当年那个
「刚记录完却显示 8 小时前」「凌晨 0~8 点的记录落到前一天」的坑
（详见 `docs/时间口径统一方案.md`）。

### 修法：不用重建容器，在连接层设就行

**首选：在 PyMySQL 建连时设时区**，让每个连接的 `NOW()` 都返回北京时间：

```python
_pool = PooledDB(
    creator=pymysql, ...,
    init_command="SET time_zone = '+08:00'",   # ← 关键一行
)
```

这样做的三个好处：

1. **不用重建容器**（省事，也不动你的 `ai_project` 库）
2. **与容器时区解耦** —— 以后换任何镜像/服务器都不会再踩这个坑
3. 配合「时间都由 Python 侧 `now_str()` 显式写入」的既有约定，**双保险**

**备选**（如果想让容器本身也统一）：重建容器加 `-e TZ=Asia/Shanghai --default-time-zone=+08:00`，
数据卷 `mysql_local_data` 会保留。但如上所述，**连接层设置就够了，不建议为此折腾**。

### 库名建议

现在容器里建的是 `ai_project`（看起来是别的项目的库）。
**建议为本项目单独建一个 `self_grow` 库**，别混用 —— 迁移期的反复重建、
清表操作会更放心：

```sql
CREATE DATABASE self_grow DEFAULT CHARSET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

---

## 一、改动面实测

先看真实规模，这决定了方案选型。

| 项目 | 数量 | 是否要改 |
|---|---|---|
| `get_conn()` 调用点 | **151** 处（20 个文件） | ❌ **不改**（用连接池代理） |
| `conn.close()` | 205 处 | ❌ **不改**（代理的 close = 归还连接） |
| `conn.commit()` | 104 处 | ❌ **不改**（代理透传） |
| `?` 占位符 | **~150** 处 | ✅ 要改（见 §4.2） |
| `AUTOINCREMENT` | 19 处（建表） | ✅ 建表重写 |
| **`TEXT NOT NULL DEFAULT`** | **36 处（建表）** | ✅ **头号坑**，必须逐列改（见 §5） |
| `TEXT` 列总数 | 119 处（建表） | 部分要改成 `VARCHAR(n)` |
| `FOREIGN KEY` | **18 处（建表）** | ⚠️ 影响迁移顺序（见 §6） |
| 建表默认值 `datetime('now','localtime')` | 16 处 | ✅ 建表重写 |
| 建表默认值 `date('now')` | 1 处 | ✅ 建表重写 |
| **SQL 查询里的** `datetime('now','localtime')` | **仅 5 处** | ✅ 改成 Python 传值 |
| `PRAGMA` | 9 处 | ✅ 删除 |
| `INSERT OR IGNORE` | 2 处 | ✅ 改 `INSERT IGNORE` |
| `sqlite3.Row` 类型注解 | 1 处（`db/expressions.py:375`） | ✅ 改 `DictCursor` |
| `.lastrowid` | 12 处 | ❌ **不改**（PyMySQL 的 cursor 同样支持） |
| SQL 层面的 `strftime()` | **0 处** | — 全是 Python 的 `datetime.strftime` |
| SQL 里字面 `%` | **0 处** | — 不用转义成 `%%` |
| `RETURNING` | 0 处 | — |
| **数据库层总规模** | `db/` **3,734 行**，22 张表 + 8 索引 | |

**结论**：真正要手改的是 **~150 处占位符 + 22 张表 DDL（含 36 处 TEXT 默认值）+ 5 处时间函数**。
`db/` 层之外的 151 个调用点**可以一行不动** —— 这是方案设计的核心目标。

---

## 二、总体策略：双后端 + 分阶段

**用环境变量保留 SQLite 通路**，不要一次切死：

```bash
SELF_GROW_DB_BACKEND=sqlite   # 默认，行为完全不变
SELF_GROW_DB_BACKEND=mysql    # 新通路
```

这样做的三个好处：

1. **可随时回退** —— 迁移期的任何一步出问题，改个环境变量就回到原状
2. **可对照验证** —— 同一份数据两边跑，对比结果是否一致（比"看起来正常"可靠得多）
3. **测试可以双跑** —— CI 里两个后端都跑一遍 150 个用例

---

## 三、分阶段实施

### 阶段 0：准备（30 分钟）

```bash
docker run -d --name sg-mysql \
  -e MYSQL_ROOT_PASSWORD=root \
  -e MYSQL_DATABASE=self_grow \
  -e MYSQL_USER=self_grow -e MYSQL_PASSWORD=self_grow \
  -e TZ=Asia/Shanghai \
  -p 3306:3306 mysql:8 \
  --character-set-server=utf8mb4 \
  --collation-server=utf8mb4_unicode_ci \
  --default-time-zone=+08:00
```

⚠️ **`TZ` 和 `--default-time-zone` 必须设**。本项目全项目统一用本地时间（naive local），
MySQL 默认用 UTC，不设就会重演当年那个"刚记录完却显示 8 小时前"的坑。
（详见 `docs/时间口径统一方案.md`）

### 阶段 1：连接层（半天）

新增 `db/backend.py`：按 `SELF_GROW_DB_BACKEND` 分派，SQLite / MySQL 各返一个统一接口。

MySQL 侧的关键是**用连接池 + 代理对象**，让既有的 `get_conn()` / `close()` 模式一行不改：

```python
from dbutils.pooled_db import PooledDB
import pymysql

_pool = PooledDB(
    creator=pymysql, maxconnections=12, blocking=True,
    host=..., user=..., password=..., database=...,
    charset="utf8mb4", cursorclass=pymysql.cursors.DictCursor,
    autocommit=False,
)

class Conn:
    """代理：保持 sqlite3.Connection 的那套用法"""
    def __init__(self, raw, pool):
        self._raw, self._pool = raw, pool

    def cursor(self):
        return self._raw.cursor()          # DictCursor → row["col"] 仍可用

    def execute(self, sql, params=()):
        cur = self._raw.cursor()
        cur.execute(_adapt(sql), params)
        return cur

    def executemany(self, sql, seq):
        cur = self._raw.cursor(); cur.executemany(_adapt(sql), seq); return cur

    def commit(self): self._raw.commit()
    def rollback(self): self._raw.rollback()
    def close(self): self._pool.close()     # ← 归还，不是真关

    # 顺手补上上下文管理器（现在项目里没有，205 处手动 close 是隐患）
    def __enter__(self): return self
    def __exit__(self, exc_type, *a):
        self._raw.rollback() if exc_type else self._raw.commit()
        self.close()
```

**连接池大小要 ≥ 并发线程数**：协调 Agent 会用 `asyncio.gather` 并行跑多个子 Agent，
每个工具调用都 `asyncio.to_thread` + `get_conn()`。池太小 → 线程等连接 →
比 SQLite 的 `busy_timeout` 更容易卡死。默认给 12 是留了余量。

### 阶段 2：SQL 方言（1 天，主要工作量）

见 §4。

### 阶段 3：建表 DDL 重写（半天）

`db/init.py` 的 22 张表重写成 MySQL 方言，见 §5。

### 阶段 4：数据迁移（半天）

写 `tools/migrate_sqlite_to_mysql.py`，见 §6。

### 阶段 5：验证（1 天）

见 §7。

**总计约 3~4 个工作日**；若只求"本地跑通"（阶段 0-3 + 手工灌数据），**1~1.5 天**。

---

## 四、SQL 方言处理（主要工作量）

### 4.1 时间函数（只有 5 处查询，好办）

SQL 查询里用 `datetime('now','localtime')` 的**只有 5 处**：

| 文件 | 用途 |
|---|---|
| `db/model_configs.py:64` | UPDATE 时写 `updated_at` |
| `db/rewards.py:122` | INSERT 时写时间 |
| `db/rewards.py:128` | UPDATE 时写 `updated_at` |
| `db/skill_tree.py:82` | 同上 |
| `db/skill_tree.py:115` | 同上 |

**建议改成 Python 侧传值**（`db/connection.py` 已有 `now_str()` 就是干这个的）：

```python
# 改前
"... updated_at = datetime('now','localtime') WHERE id = ?"
# 改后（推荐）
f"... updated_at = %s WHERE id = %s", (now_str(), row_id)
```

**为什么不直接用 MySQL 的 `NOW()`**：`NOW()` 走 MySQL 服务器时区，
多了一层「容器时区设对了吗」的隐式依赖。用 `now_str()` 是**应用层算好的本地时间**，
与项目其它部分（`date.today()`、APScheduler cron、`user_stats_daily.date`）天然一致。

### 4.2 占位符（~150 处）—— 两条路

**方案 A：连接层翻译（改动最小）**

在 `_adapt(sql)` 里把 `?` 换成 `%s`：

```python
def _adapt(sql: str) -> str:
    return sql.replace("?", "%s") if "?" in sql else sql
```

- ✅ **150 处 SQL 零改动**，回退成本低
- ✅ 已核实安全：SQL 里**没有字面 `?`**，也**没有字面 `%`**（不用写 `%%`）
- ⚠️ 缺点：隐式魔法，代码里混着 `?` 和 `%s` 会让人困惑

**方案 B：老实改成 `%s`（推荐）**

脚本批量替换 SQL 字符串里的 `?` → `%s`，再人工核对一遍。

- ✅ 代码干净，符合 MySQL 生态惯例，没有隐藏行为
- ✅ 一次性投入，之后不会再有人问"为什么这里写 `?` 也能跑"
- ⚠️ 150 处要核对，容易漏；但可以用「改完后跑全量测试」兜住

**建议**：**先 A 跑通（1 小时就能让整条链路活起来），验证无误后再做 B 收口。**
两者不冲突，A 是过渡手段。

### 4.3 其余零星

| 现状 | 改法 |
|---|---|
| `INSERT OR IGNORE INTO x` (2 处) | `INSERT IGNORE INTO x` |
| `PRAGMA journal_mode=WAL` 等 9 处 | **直接删除**（InnoDB 不需要，连接池设置代替） |
| `import sqlite3` + `sqlite3.Row` 注解 | 改 `DictCursor`，注解改 `dict` 或 `Any` |
| `sqlite_master`（在测试里） | MySQL 对应 `information_schema.tables` |

---

## 五、建表 DDL 重写要点

### ⚠️ 头号坑：MySQL 的 `TEXT` 不能有默认值（**36 处**，必须逐列改）

实测 `db/init.py` 里有 **36 处**这种写法：

```sql
role       TEXT NOT NULL DEFAULT 'user'                        -- SQLite 合法
icon       TEXT NOT NULL DEFAULT ''
priority   TEXT NOT NULL DEFAULT 'mid'
joined     TEXT NOT NULL DEFAULT (date('now'))
created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))  -- 16 处
```

**全部在 MySQL 里直接报错**：
`ERROR 1101 (42000): BLOB, TEXT, GEOMETRY or JSON column 'xxx' can't have a default value`

**逐列改法**：

| 列的类型 | 改法 |
|---|---|
| 短文本（`role` / `icon` / `status` / `priority` / `category_id` / 时间戳） | `VARCHAR(n) NOT NULL DEFAULT ''`（n 按实际长度：时间 32、状态 32、名称 128） |
| 长文本（`note` / `intro` / `desc` / JSON 串 / AI 回复） | `TEXT NULL`（**去掉 NOT NULL 和 DEFAULT**，由代码侧保证） |

**这个坑的危险在于"跑起来才发现"** —— 建表是 `init_db()` 里逐条 `execute()`，
第一条炸了就中断，剩下的表都不会建，然后你会看到一堆"表不存在"的错。
**建议先用脚本扫一遍 36 处，一次改到位。**

### 其它类型映射

| SQLite | MySQL | 说明 |
|---|---|---|
| `INTEGER PRIMARY KEY AUTOINCREMENT` | `BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY` | 19 处 |
| `INTEGER` | `INT` 或 `BIGINT` | id 类建议 BIGINT |
| `TEXT`（时间戳） | `VARCHAR(32)` 或 `DATETIME` | **建议保持字符串**（见下） |
| `REAL` / `NUMERIC` | `DECIMAL(10,2)` | |
| 布尔（0/1） | `TINYINT(1)` | |
| `DEFAULT (datetime('now','localtime'))` | 去掉默认值，或 `DEFAULT CURRENT_TIMESTAMP` | 16 处 |

**关于时间列**：项目现在把时间存成 **TEXT 字符串**（`'2026-09-19 14:30:00'`）。
迁移时**建议保持字符串不动** —— 改成 `DATETIME` 会牵动所有比较、分组、
以及前端拿到的格式，收益（类型安全）远小于风险。**这是有意保留的取舍。**

### 表选项

```sql
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

22 张表都要加。字符集必须 `utf8mb4`（项目里有 emoji：`🏃 🎁 📊`）。

---

## 六、数据迁移脚本

`tools/migrate_sqlite_to_mysql.py`：

1. 读 SQLite 的 `data.db`（用户本地那份有 **test Lv188、246+ 行动记录**的真实数据）
2. 按 `sqlite_master` 取全部表名
3. **逐表迁移，显式列出字段名**（不要靠列顺序，SQLite 和 MySQL 的建表顺序可能不同）
4. `id` 显式插入（`AUTO_INCREMENT` 列允许显式赋值）
5. 迁完 **重置每张表的 `AUTO_INCREMENT`** 到 `max(id)+1`，否则新数据会撞主键
6. 逐表比对行数 + 关键聚合值（`SUM(exp_earned)`、`COUNT(*)`）

⚠️ **有 18 处外键**（实测），所以：

1. 迁移时**按依赖顺序**（先父表后子表）：`users` → `user_dimensions` / `habits` / `tasks` / ...
   → `habit_checkins` / `action_logs` ...
2. 或者更省事：迁移会话里先 `SET FOREIGN_KEY_CHECKS=0`，迁完再 `=1`，
   最后用 `SELECT ... LEFT JOIN` 抽查几条孤儿记录
3. **SQLite 侧的外键默认不生效**（除非 `PRAGMA foreign_keys=ON`），
   所以老库里可能**本来就存在孤儿数据** —— 迁移前先查一遍，
   否则 MySQL 会拒绝插入，你会以为是脚本写错了

---

## 七、验证清单

| # | 验证项 | 方法 |
|---|---|---|
| 1 | 150 个 pytest 在 MySQL 上全绿 | 测试库 `self_grow_test`，conftest 里切后端 |
| 2 | 数据一致性 | 逐表行数 + `SUM(exp_earned)` / `SUM(total_exp)` 等聚合值对比 |
| 3 | **时间口径** | 跑 `tests/test_time_consistency.py`（10 个用例专测这个）+ 手工查一条刚插入的记录 |
| 4 | 维度不变式 | 跑 `tests/test_dimension_invariant.py`（6 个用例） |
| 5 | 并发写 | 协调 Agent 双域请求并发提交（反问场景），确认无死锁、无重复写入 |
| 6 | 连接池不泄漏 | 压一下 `/api/coordinator/chat`，看 MySQL 的 `Threads_connected` 是否稳定 |
| 7 | SSE 长任务 | 89 秒那条链路（习惯图标）在 MySQL 下仍能跑完 |
| 8 | 字符集 | 写一条带 emoji 的记录（习惯图标 🏃），确认不是 `????` |

---

## 八、必须知道的坑（汇总）

1. **`TEXT` 不能有默认值** —— 22 张表逐列检查，最容易在运行时才炸
2. **时区** —— MySQL 容器必须设 `TZ=Asia/Shanghai` + `--default-time-zone=+08:00`，
   否则重演"刚记录完显示 8 小时前"
3. **连接池要 ≥ 并发线程数** —— 协调 Agent 并行跑子 Agent，池小了会卡死（比 SQLite 更糟）
4. **`conn.close()` 有 205 处但 `get_conn()` 只有 143 处** —— 说明有分支重复 close。
   代理对象里 `close()` 必须**幂等**（重复归还不能把连接搞坏）
5. **`autocommit` 语义不同** —— SQLite 的 `conn.commit()` 是显式事务结束；
   PyMySQL 默认 `autocommit=False`，行为接近，但**要确认 104 处 commit 都覆盖到了**
6. **`lastrowid` 只在 INSERT 后有效** —— 现在 12 处用法要确认没在别处读

---

## 九、回退方案

任何阶段出问题：`SELF_GROW_DB_BACKEND=sqlite` → 立刻回到原状。
**这是整个方案能做的前提** —— 不要先删 SQLite 通路。
