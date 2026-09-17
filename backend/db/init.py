"""
Self Grow — 数据库初始化

建表（15 张表）+ 插入默认用户和默认奖励。
"""

import datetime

from config import log
from db.connection import get_conn
from db.dimensions import get_total_exp_from_dimensions
from models.constants import DIMENSION_KEYS, DEFAULT_DIMENSIONS
from models.level import exp_for_level, level_from_total_exp, total_exp_for_level

# 维度等级上限（与 db/dimensions.py::upsert_dimension 的 `level < 140` 保持一致）
MAX_DIM_LEVEL = 140


# ================================================================
# 空库时的初始账号与初始进度
#
# 数据来源：**本地开发库 backend/data.db 里 test / admin 的真实状态，原样搬过来**。
# 这样新部署一份空库，看到的就是本地那套真实进度，而不是演示用的占位数字。
#
# ⚠️ 三个字段必须**配套**，这是踩过坑的：
#    · level      当前等级
#    · xp         当前等级内的进度（不是累计！）
#    · xp_to_next 从 level 升到 level+1 所需经验
#    不变式： 0 <= xp < xp_to_next  且  xp_to_next == exp_for_level(level)
#
#    违反不变式的后果（真实踩过）：以前这里写死 level=1 / xp_to_next=150，
#    却把 total_exp//8 当成 xp 塞进去，于是库里出现「Lv1 却有 5625 经验、
#    还差 150 就升级」这种自相矛盾的行；前端 min(xp/xp_to_next,1) 渲染成 100%，
#    看着像进度满了，其实是脏数据，一直要到该维度被记录一次才会自愈。
#
# 累计经验 = total_exp_for_level(level) + xp（db/dimensions.py::get_total_exp_from_dimensions）
# ================================================================

# (name, role, level, exp=本级进度, total_exp, streak, joined)
# 注：users.total_exp 是**遗留字段**，真值一律以 8 维反推为准（见上面公式），
#     这里填的就是反推之和，避免两处对不上。
#
# ⚠️ 三条恒等式（`tests/test_dimension_invariant.py` 会逐条断言）：
#     ① total_exp == total_exp_for_level(level) + exp
#     ② total_exp == 该用户名下 8 维的 Σ(total_exp_for_level(lv) + xp)
#     ③ 每维 0 <= xp < xp_to_next 且 xp_to_next == exp_for_level(lv)
#   2026-09-17 复核时 ① 在 test 上差 30（exp 填的是 145356，应为 145386），已修正。
DEFAULT_DEMO_USERS = [
    ("test", "user", 188, 145386, 12230686, 21, "2026-01-15"),
    ("admin", "admin", 99, 46923, 1795043, 7, "2026-06-01"),
]

# name -> [(dimension_key, level, xp, xp_to_next), ...]
DEFAULT_DEMO_DIMENSIONS = {
    "test": [
        ("health", 98, 51311.5, 52644),
        ("study", 99, 4565.0, 53729),
        ("relation", 91, 40666.0, 45362),
        ("work", 105, 8231.0, 60472),
        ("create", 91, 40666.0, 45362),
        ("finance", 83, 19295.0, 37707),
        ("hobby", 87, 37551.0, 41445),
        ("soul", 95, 27655.0, 49456),
    ],
    "admin": [
        ("health", 52, 2324.0, 14770),
        ("study", 52, 2381.0, 14770),
        ("relation", 48, 4631.0, 12589),
        ("work", 55, 7403.0, 16522),
        ("create", 48, 4711.0, 12589),
        ("finance", 43, 8925.0, 10113),
        ("hobby", 46, 2572.0, 11565),
        ("soul", 50, 4460.0, 13657),
    ],
}


def default_dimensions_for(name: str):
    """取该用户名的初始 8 维数据；没有专门配置就退回全 0 的默认值"""
    return DEFAULT_DEMO_DIMENSIONS.get(name, DEFAULT_DIMENSIONS)


def init_default_dimensions(user_id: int, conn=None, dimensions=None):
    """为指定用户插入 8 维数据（如果还不存在）

    dimensions 不传时用全 0 的 DEFAULT_DIMENSIONS；传了就按传入的（带真实进度）。
    """
    rows = dimensions if dimensions is not None else DEFAULT_DIMENSIONS
    if conn:
        for key, lv, xp, xpn in rows:
            conn.execute(
                """INSERT OR IGNORE INTO user_dimensions (user_id, dimension_key, level, xp, xp_to_next)
                   VALUES (?, ?, ?, ?, ?)""",
                (user_id, key, lv, xp, xpn),
            )
    else:
        conn2 = get_conn()
        for key, lv, xp, xpn in rows:
            conn2.execute(
                """INSERT OR IGNORE INTO user_dimensions (user_id, dimension_key, level, xp, xp_to_next)
                   VALUES (?, ?, ?, ?, ?)""",
                (user_id, key, lv, xp, xpn),
            )
        conn2.commit()
        conn2.close()


def init_db():
    """初始化数据库：建表 + 插入默认用户（如果不存在）"""
    conn = get_conn()
    cursor = conn.cursor()

    # 用户表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user',
            level INTEGER NOT NULL DEFAULT 1,
            exp INTEGER NOT NULL DEFAULT 0,
            total_exp INTEGER NOT NULL DEFAULT 0,
            streak INTEGER NOT NULL DEFAULT 0,
            joined TEXT NOT NULL DEFAULT (date('now'))
        )
    """)

    # 每日统计表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_stats_daily (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            focus_minutes INTEGER NOT NULL DEFAULT 0,
            tasks_done INTEGER NOT NULL DEFAULT 0,
            habits_checked INTEGER NOT NULL DEFAULT 0,
            exp_earned INTEGER NOT NULL DEFAULT 0,
            UNIQUE(user_id, date),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    # 习惯定义表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS habits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            icon TEXT NOT NULL DEFAULT '',
            intro TEXT DEFAULT '',
            category TEXT NOT NULL,
            weekly_target INTEGER NOT NULL DEFAULT 7,
            xp_reward INTEGER NOT NULL DEFAULT 15,
            active INTEGER NOT NULL DEFAULT 1,
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    # 每日打卡记录表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS habit_checkins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            habit_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            status TEXT NOT NULL,
            UNIQUE(habit_id, date),
            FOREIGN KEY (habit_id) REFERENCES habits(id)
        )
    """)

    # 行动记录表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS action_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            category_id TEXT NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            duration INTEGER NOT NULL,
            note TEXT DEFAULT '',
            exp_earned INTEGER NOT NULL,
            sub_type TEXT DEFAULT '',
            sleep_start TEXT DEFAULT '',
            sleep_end TEXT DEFAULT '',
            created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_action_logs_user_date
        ON action_logs(user_id, start_time)
    """)

    # 规律作息连续天数表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS routine_streak (
            user_id INTEGER NOT NULL PRIMARY KEY,
            streak INTEGER NOT NULL DEFAULT 0,
            has_protection INTEGER NOT NULL DEFAULT 0,
            last_date TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    # 用户维度经验表（八维属性）
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_dimensions (
            user_id INTEGER NOT NULL,
            dimension_key TEXT NOT NULL,
            level INTEGER NOT NULL DEFAULT 1,
            xp REAL NOT NULL DEFAULT 0,
            xp_to_next INTEGER NOT NULL DEFAULT 150,
            PRIMARY KEY (user_id, dimension_key),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    # 目标表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS goals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            intro TEXT DEFAULT '',
            category TEXT NOT NULL,
            progress INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'active',
            deadline TEXT,
            reward_exp INTEGER NOT NULL DEFAULT 0,
            claimed INTEGER NOT NULL DEFAULT 0,
            category_image TEXT DEFAULT '',
            created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    # 目标里程碑表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS goal_milestones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            goal_id INTEGER NOT NULL,
            done INTEGER NOT NULL DEFAULT 0,
            note TEXT DEFAULT '',
            sort_order INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (goal_id) REFERENCES goals(id) ON DELETE CASCADE
        )
    """)

    # 任务表（含历史）
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            category TEXT NOT NULL,
            priority TEXT NOT NULL DEFAULT 'mid',
            exp INTEGER NOT NULL DEFAULT 50,
            intro TEXT DEFAULT '',
            status TEXT NOT NULL DEFAULT 'todo',
            created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
            deadline TEXT,
            completed_at TEXT,
            claimed INTEGER NOT NULL DEFAULT 0,
            source_type TEXT DEFAULT 'today',
            source_template_id INTEGER,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_tasks_user_status
        ON tasks(user_id, status)
    """)
    # 创建索引：按 source_type 快速查询
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_tasks_user_source
        ON tasks(user_id, source_type, created_at)
    """)

    # ================================================================
    # 任务历史表（定时归档）
    # ================================================================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS task_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            task_id INTEGER,
            title TEXT NOT NULL,
            category TEXT NOT NULL,
            priority TEXT NOT NULL DEFAULT 'mid',
            exp INTEGER NOT NULL DEFAULT 50,
            intro TEXT DEFAULT '',
            status TEXT NOT NULL,
            source_type TEXT NOT NULL,
            completed_at TEXT,
            created_at TEXT NOT NULL,
            archived_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_task_history_user
        ON task_history(user_id, archived_at)
    """)

    # 定时任务模板表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS scheduled_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            type TEXT NOT NULL,
            title TEXT NOT NULL,
            intro TEXT DEFAULT '',
            category TEXT NOT NULL,
            priority TEXT NOT NULL DEFAULT 'mid',
            exp INTEGER NOT NULL DEFAULT 50,
            weekdays TEXT,
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    # 奖励商城表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS rewards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            desc TEXT DEFAULT '',
            icon TEXT NOT NULL DEFAULT '🎁',
            category TEXT DEFAULT '',
            image TEXT DEFAULT '',
            unlock_conditions TEXT NOT NULL DEFAULT '[]',
            claim_conditions TEXT NOT NULL DEFAULT '[]',
            unlocked INTEGER NOT NULL DEFAULT 0,
            claimed INTEGER NOT NULL DEFAULT 0,
            claimed_at TEXT,
            manual_confirmed TEXT NOT NULL DEFAULT '[]',
            created_at_exp INTEGER DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    # 奖励草稿表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reward_drafts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL UNIQUE,
            title TEXT DEFAULT '',
            desc TEXT DEFAULT '',
            icon TEXT DEFAULT '🎁',
            category TEXT DEFAULT '',
            image TEXT DEFAULT '',
            unlock_conditions TEXT NOT NULL DEFAULT '[]',
            claim_conditions TEXT NOT NULL DEFAULT '[]',
            updated_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    # 月度统计表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_monthly_stats (
            user_id INTEGER NOT NULL,
            year_month TEXT NOT NULL,
            habit_count INTEGER NOT NULL DEFAULT 0,
            habit_xp INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (user_id, year_month),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    # 模型配置表（LLM / ASR）
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS model_configs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            type TEXT NOT NULL,
            name TEXT NOT NULL,
            model TEXT NOT NULL,
            base_url TEXT NOT NULL DEFAULT '',
            api_key TEXT NOT NULL DEFAULT '',
            is_active INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    # 插入默认用户（含真实初始进度，见文件上方 DEFAULT_DEMO_USERS 的说明）
    existing = cursor.execute("SELECT id FROM users").fetchall()
    if not existing:
        cursor.executemany(
            "INSERT INTO users (name, role, level, exp, total_exp, streak, joined) VALUES (?, ?, ?, ?, ?, ?, ?)",
            DEFAULT_DEMO_USERS,
        )

        # 为默认用户初始化 8 维数据（带真实进度，与本地开发库保持一致）
        for u in cursor.execute("SELECT id, name FROM users").fetchall():
            init_default_dimensions(
                u["id"], conn=conn, dimensions=default_dimensions_for(u["name"])
            )

        # 注意：不再为默认用户插入默认奖励，奖励商城从空开始
        # 用户可自行创建自定义奖励，互相隔离

    # 为没有模型配置的用户插入默认配置（从 .env 读取，幂等）
    from config import AI_MODEL, AI_BASE_URL, AI_API_KEY, DASHSCOPE_API_KEY
    for u in cursor.execute("SELECT id FROM users").fetchall():
        uid = u["id"]
        has_cfg = cursor.execute(
            "SELECT COUNT(*) AS cnt FROM model_configs WHERE user_id = ?", (uid,)
        ).fetchone()["cnt"]
        if has_cfg == 0:
            cursor.execute(
                "INSERT INTO model_configs (user_id, type, name, model, base_url, api_key, is_active) "
                "VALUES (?, 'llm', '默认模型', ?, ?, ?, 1)",
                (uid, AI_MODEL, AI_BASE_URL, AI_API_KEY),
            )
            cursor.execute(
                "INSERT INTO model_configs (user_id, type, name, model, base_url, api_key, is_active) "
                "VALUES (?, 'asr', '默认语音模型', 'paraformer-realtime-v2', ?, ?, 1)",
                (uid, "wss://dashscope.aliyuncs.com/api-ws/v1/inference", DASHSCOPE_API_KEY),
            )

    conn.commit()
    conn.close()

    # 数据迁移：检测现有用户的 total_exp 是否已经分配到维度
    migrate_total_exp_to_dimensions()

    # 自愈：把历史上写坏（违反 xp < xp_to_next）的维度行一次性修回来
    fixed_rows = normalize_dimension_rows()
    if fixed_rows:
        log.warning(f"⚠️ 修正了 {fixed_rows} 条不自洽的维度数据（历史遗留）")

    # 迁移：action_logs 增加 sub_type / sleep_start / sleep_end（幂等）
    # migrate_total_exp_to_dimensions() 可能关闭了 conn，需要重新获取
    conn = get_conn()
    for col, col_type in [
        ("sub_type", "TEXT DEFAULT ''"),
        ("sleep_start", "TEXT DEFAULT ''"),
        ("sleep_end", "TEXT DEFAULT ''"),
    ]:
        try:
            conn.execute(f"ALTER TABLE action_logs ADD COLUMN {col} {col_type}")
        except Exception:
            pass  # 列已存在，跳过
    conn.commit()
    conn.close()

    # 创建技能树相关表
    init_skill_trees_tables()

    # 创建表达训练相关表
    init_expression_tables()

    # 迁移：user_dimensions.xp 从 INTEGER → REAL（幂等）
    conn2 = get_conn()
    try:
        info = conn2.execute("PRAGMA table_info(user_dimensions)").fetchall()
        xp_col = [c for c in info if c["name"] == "xp"]
        if xp_col and xp_col[0]["type"].upper() == "INTEGER":
            conn2.execute("ALTER TABLE user_dimensions ADD COLUMN xp_real REAL NOT NULL DEFAULT 0")
            conn2.execute("UPDATE user_dimensions SET xp_real = xp")
            conn2.execute("ALTER TABLE user_dimensions DROP COLUMN xp")
            conn2.execute("ALTER TABLE user_dimensions RENAME COLUMN xp_real TO xp")
            conn2.commit()
    except Exception:
        pass  # 列已迁移或 SQLite 版本不支持 DROP COLUMN
    conn2.close()

    # 迁移：rewards 增加 unlocked_at_snapshot 字段（幂等）
    conn3 = get_conn()
    try:
        conn3.execute(
            "ALTER TABLE rewards ADD COLUMN unlocked_at_snapshot TEXT NOT NULL DEFAULT '{}'"
        )
        conn3.commit()
    except Exception:
        pass  # 列已存在
    conn3.close()

    # 登录鉴权：users 补字段 + 新建 refresh_tokens / api_keys（幂等）
    init_auth_tables()
    migrate_users_auth_columns()


def init_auth_tables():
    """创建登录鉴权相关表（refresh_tokens / api_keys）"""
    conn = get_conn()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS refresh_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            token_hash TEXT NOT NULL,
            user_agent TEXT DEFAULT '',
            expires_at TEXT NOT NULL,
            revoked INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_refresh_user
        ON refresh_tokens(user_id)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_refresh_hash
        ON refresh_tokens(token_hash)
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS api_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            key_hash TEXT NOT NULL,
            last_used_at TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
            revoked INTEGER NOT NULL DEFAULT 0
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_apikey_hash
        ON api_keys(key_hash)
    """)

    conn.commit()
    conn.close()


def migrate_users_auth_columns():
    """users 表补 password_hash / token_version / last_login（幂等）"""
    conn = get_conn()
    for col, col_type in [
        ("password_hash", "TEXT"),
        ("token_version", "INTEGER NOT NULL DEFAULT 1"),
        ("last_login", "TEXT"),
    ]:
        try:
            conn.execute(f"ALTER TABLE users ADD COLUMN {col} {col_type}")
        except Exception:
            pass  # 列已存在
    conn.commit()
    conn.close()


def split_total_exp(total_exp: float):
    """把某维度的「累计经验」拆成 (等级, 本级进度, 升级所需)

    这是**唯一**能保证不变式 `0 <= 本级进度 < 升级所需` 与
    `升级所需 == exp_for_level(等级)` 同时成立的地方。
    任何直接写 user_dimensions 的代码都应该走它，别自己拼三个数字。
    """
    level = min(level_from_total_exp(total_exp), MAX_DIM_LEVEL)
    current = total_exp - total_exp_for_level(level)
    return level, current, exp_for_level(level)


def normalize_dimension_rows() -> int:
    """自愈：修正违反不变式的维度行，返回修正条数（幂等，每次启动跑）

    判据：`xp_to_next != exp_for_level(level)` 或 `xp >= xp_to_next`。

    历史背景：migrate_total_exp_to_dimensions() 曾经写死 `level=1 / xp_to_next=150`，
    在库里留下「Lv1 却有 5625 经验、还差 150 就升级」这种自相矛盾的行 ——
    前端会把进度渲染成 100%，看着像满级。这些行原本只在「该维度被记录一次」时
    才靠进位循环自愈；这里启动时一次性全修掉。
    """
    conn = get_conn()
    rows = conn.execute(
        "SELECT user_id, dimension_key, level, xp, xp_to_next FROM user_dimensions"
    ).fetchall()

    fixed = 0
    for r in rows:
        level, xp = r["level"], r["xp"]
        if level >= MAX_DIM_LEVEL:
            continue                        # 已到维度上限，不再参与升级
        need = exp_for_level(level)
        if need > 0 and xp < need and r["xp_to_next"] == need:
            continue                        # 本来就是对的
        new_level, new_cur, new_need = split_total_exp(total_exp_for_level(level) + xp)
        conn.execute(
            "UPDATE user_dimensions SET level = ?, xp = ?, xp_to_next = ? "
            "WHERE user_id = ? AND dimension_key = ?",
            (new_level, new_cur, new_need, r["user_id"], r["dimension_key"]),
        )
        fixed += 1

    conn.commit()
    conn.close()
    return fixed


def migrate_total_exp_to_dimensions():
    """将 users.total_exp 平均分配到 8 维（仅在维度 SUM 为 0 时执行一次）

    ⚠️ 拆分一律走 split_total_exp()，不要自己拼 level/xp/xp_to_next 三个数字 ——
    曾经写死 level=1 / xp_to_next=150，留下的脏行见 normalize_dimension_rows() 的说明。
    """
    conn = get_conn()
    users = conn.execute("SELECT id, total_exp FROM users").fetchall()
    for u in users:
        row = conn.execute(
            "SELECT COALESCE(SUM(xp), 0) as total FROM user_dimensions WHERE user_id = ?",
            (u["id"],),
        ).fetchone()
        if row and row["total"] > 0:
            continue
        total = u["total_exp"]
        per_dim = total // len(DIMENSION_KEYS)
        remainder = total % len(DIMENSION_KEYS)
        for i, key in enumerate(DIMENSION_KEYS):
            dim_total = per_dim + (1 if i < remainder else 0)
            if dim_total <= 0:
                continue
            lv, cur, need = split_total_exp(dim_total)
            conn.execute(
                """INSERT INTO user_dimensions (user_id, dimension_key, level, xp, xp_to_next)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(user_id, dimension_key) DO UPDATE
                       SET level = excluded.level,
                           xp = excluded.xp,
                           xp_to_next = excluded.xp_to_next""",
                (u["id"], key, lv, cur, need),
            )
        new_total = total
        new_level = level_from_total_exp(new_total)
        new_current = new_total - total_exp_for_level(new_level)
        conn.execute(
            "UPDATE users SET level = ?, exp = ?, total_exp = ? WHERE id = ?",
            (new_level, new_current, new_total, u["id"]),
        )
    conn.commit()
    conn.close()


def init_skill_trees_tables():
    """创建技能树相关表"""
    from db.connection import get_conn
    conn = get_conn()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS skill_trees (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            tree_id TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL DEFAULT '未命名技能树',
            description TEXT DEFAULT '',
            data TEXT NOT NULL DEFAULT '{}',
            published_data TEXT,
            image TEXT DEFAULT '',
            remark TEXT DEFAULT '',
            node_count INTEGER NOT NULL DEFAULT 0,
            completed_count INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
            published_at TEXT,
            update_history TEXT NOT NULL DEFAULT '[]',
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_skills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL UNIQUE,
            skill_ids TEXT NOT NULL DEFAULT '[]',
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    conn.commit()
    conn.close()

    # 创建表达训练相关表
    init_expression_tables()


def init_expression_tables():
    """创建表达训练相关表"""
    from db.connection import get_conn
    conn = get_conn()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS expression_questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question TEXT NOT NULL,
            question_type TEXT NOT NULL,
            hints TEXT,
            source TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now','localtime'))
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS expression_answers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL DEFAULT 'test',
            question_id INTEGER NOT NULL,
            attempt INTEGER DEFAULT 1,
            answer TEXT,
            filler_words TEXT,
            score_total REAL,
            score_fluency REAL,
            score_logic REAL,
            score_content REAL,
            score_language REAL,
            strengths TEXT,
            improvements TEXT,
            suggestion TEXT,
            status TEXT DEFAULT 'answered',
            created_at TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (question_id) REFERENCES expression_questions(id)
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_exp_answers_user
        ON expression_answers(user_id, question_id)
    """)

    conn.commit()
    conn.close()