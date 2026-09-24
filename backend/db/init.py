"""
Self Grow — 数据库初始化

建表（28 张表 + 20 个二级索引）+ 插入默认用户和默认奖励。
"""

import logging

from db.connection import get_conn
from db.dimensions import get_total_exp_from_dimensions
from models.constants import DIMENSION_KEYS, DEFAULT_DIMENSIONS
from models.level import exp_for_level, level_from_total_exp, total_exp_for_level

# 用本模块自己的 logger。原来借的是 `config` 的，日志里会显示成配置模块。
log = logging.getLogger(__name__)

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
                """INSERT IGNORE INTO user_dimensions (user_id, dimension_key, level, xp, xp_to_next)
                   VALUES (%s, %s, %s, %s, %s)""",
                (user_id, key, lv, xp, xpn),
            )
    else:
        conn2 = get_conn()
        for key, lv, xp, xpn in rows:
            conn2.execute(
                """INSERT IGNORE INTO user_dimensions (user_id, dimension_key, level, xp, xp_to_next)
                   VALUES (%s, %s, %s, %s, %s)""",
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
          `id` int NOT NULL AUTO_INCREMENT,
          `name` varchar(255) NOT NULL,
          `role` varchar(255) NOT NULL DEFAULT 'user',
          `level` int NOT NULL DEFAULT '1',
          `exp` int NOT NULL DEFAULT '0',
          `total_exp` int NOT NULL DEFAULT '0',
          `streak` int NOT NULL DEFAULT '0',
          `joined` varchar(32) NOT NULL DEFAULT (curdate()),
          `password_hash` varchar(128),
          `token_version` int NOT NULL DEFAULT '1',
          `last_login` text,
          PRIMARY KEY (`id`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)

    # 每日统计表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_stats_daily (
          `id` int NOT NULL AUTO_INCREMENT,
          `user_id` int NOT NULL,
          `date` varchar(32) NOT NULL,
          `focus_minutes` int NOT NULL DEFAULT '0',
          `tasks_done` int NOT NULL DEFAULT '0',
          `habits_checked` int NOT NULL DEFAULT '0',
          `exp_earned` int NOT NULL DEFAULT '0',
          PRIMARY KEY (`id`),
          UNIQUE KEY `user_id` (`user_id`,`date`),
          CONSTRAINT `user_stats_daily_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)

    # 习惯定义表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS habits (
          `id` int NOT NULL AUTO_INCREMENT,
          `user_id` int NOT NULL,
          `name` varchar(255) NOT NULL,
          `icon` varchar(255) NOT NULL DEFAULT '',
          `intro` varchar(255) DEFAULT '',
          `category` varchar(32) NOT NULL,
          `weekly_target` int NOT NULL DEFAULT '7',
          `xp_reward` int NOT NULL DEFAULT '15',
          `active` int NOT NULL DEFAULT '1',
          `sort_order` int NOT NULL DEFAULT '0',
          `created_at` varchar(32) NOT NULL DEFAULT (now()),
          PRIMARY KEY (`id`),
          KEY `user_id` (`user_id`),
          CONSTRAINT `habits_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)

    # 每日打卡记录表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS habit_checkins (
          `id` int NOT NULL AUTO_INCREMENT,
          `habit_id` int NOT NULL,
          `date` varchar(32) NOT NULL,
          `status` varchar(32) NOT NULL,
          PRIMARY KEY (`id`),
          UNIQUE KEY `habit_id` (`habit_id`,`date`),
          CONSTRAINT `habit_checkins_ibfk_1` FOREIGN KEY (`habit_id`) REFERENCES `habits` (`id`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)

    # 行动记录表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS action_logs (
          `id` int NOT NULL AUTO_INCREMENT,
          `user_id` int NOT NULL,
          `category_id` varchar(32) NOT NULL,
          `start_time` varchar(32) NOT NULL,
          `end_time` varchar(32) NOT NULL,
          `duration` int NOT NULL,
          `note` varchar(255) DEFAULT '',
          `exp_earned` int NOT NULL,
          `sub_type` varchar(255) DEFAULT '',
          `sleep_start` varchar(255) DEFAULT '',
          `sleep_end` varchar(255) DEFAULT '',
          `created_at` varchar(32) NOT NULL DEFAULT (now()),
          PRIMARY KEY (`id`),
          KEY `idx_action_logs_user_date` (`user_id`,`start_time`),
          CONSTRAINT `action_logs_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)

    # 规律作息连续天数表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS routine_streak (
          `user_id` int NOT NULL,
          `streak` int NOT NULL DEFAULT '0',
          `has_protection` int NOT NULL DEFAULT '0',
          `last_date` text,
          PRIMARY KEY (`user_id`),
          CONSTRAINT `routine_streak_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)

    # 用户维度经验表（八维属性）
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_dimensions (
          `user_id` int NOT NULL,
          `dimension_key` varchar(32) NOT NULL,
          `level` int NOT NULL DEFAULT '1',
          `xp` double NOT NULL DEFAULT '0',
          `xp_to_next` int NOT NULL DEFAULT '300',
          PRIMARY KEY (`user_id`,`dimension_key`),
          CONSTRAINT `user_dimensions_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)

    # 目标表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS goals (
          `id` int NOT NULL AUTO_INCREMENT,
          `user_id` int NOT NULL,
          `title` varchar(255) NOT NULL,
          `intro` varchar(255) DEFAULT '',
          `category` varchar(32) NOT NULL,
          `progress` int NOT NULL DEFAULT '0',
          `status` varchar(255) NOT NULL DEFAULT 'active',
          `deadline` text,
          `reward_exp` int NOT NULL DEFAULT '0',
          `claimed` int NOT NULL DEFAULT '0',
          `category_image` varchar(255) DEFAULT '',
          `created_at` varchar(32) NOT NULL DEFAULT (now()),
          PRIMARY KEY (`id`),
          KEY `user_id` (`user_id`),
          CONSTRAINT `goals_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)

    # 目标里程碑表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS goal_milestones (
          `id` int NOT NULL AUTO_INCREMENT,
          `goal_id` int NOT NULL,
          `done` int NOT NULL DEFAULT '0',
          `note` varchar(255) DEFAULT '',
          `sort_order` int NOT NULL DEFAULT '0',
          PRIMARY KEY (`id`),
          KEY `goal_id` (`goal_id`),
          CONSTRAINT `goal_milestones_ibfk_1` FOREIGN KEY (`goal_id`) REFERENCES `goals` (`id`) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)

    # 任务表（含历史）
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
          `id` int NOT NULL AUTO_INCREMENT,
          `user_id` int NOT NULL,
          `title` varchar(255) NOT NULL,
          `category` varchar(32) NOT NULL,
          `priority` varchar(255) NOT NULL DEFAULT 'mid',
          `exp` int NOT NULL DEFAULT '50',
          `intro` varchar(255) DEFAULT '',
          `status` varchar(255) NOT NULL DEFAULT 'todo',
          `created_at` varchar(32) NOT NULL DEFAULT (now()),
          `deadline` text,
          `completed_at` text,
          `claimed` int NOT NULL DEFAULT '0',
          `source_type` varchar(255) DEFAULT 'today',
          `source_template_id` int DEFAULT NULL,
          PRIMARY KEY (`id`),
          KEY `idx_tasks_user_status` (`user_id`,`status`),
          KEY `idx_tasks_user_source` (`user_id`,`source_type`,`created_at`),
          CONSTRAINT `tasks_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)
    # 创建索引：按 source_type 快速查询

    # ================================================================
    # 任务历史表（定时归档）
    # ================================================================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS task_history (
          `id` int NOT NULL AUTO_INCREMENT,
          `user_id` int NOT NULL,
          `task_id` int DEFAULT NULL,
          `title` varchar(255) NOT NULL,
          `category` varchar(32) NOT NULL,
          `priority` varchar(255) NOT NULL DEFAULT 'mid',
          `exp` int NOT NULL DEFAULT '50',
          `intro` varchar(255) DEFAULT '',
          `status` varchar(32) NOT NULL,
          `source_type` varchar(32) NOT NULL,
          `completed_at` text,
          `created_at` text NOT NULL,
          `archived_at` varchar(32) NOT NULL DEFAULT (now()),
          PRIMARY KEY (`id`),
          KEY `idx_task_history_user` (`user_id`,`archived_at`),
          CONSTRAINT `task_history_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)

    # 定时任务模板表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS scheduled_tasks (
          `id` int NOT NULL AUTO_INCREMENT,
          `user_id` int NOT NULL,
          `type` varchar(32) NOT NULL,
          `title` varchar(255) NOT NULL,
          `intro` varchar(255) DEFAULT '',
          `category` varchar(32) NOT NULL,
          `priority` varchar(255) NOT NULL DEFAULT 'mid',
          `exp` int NOT NULL DEFAULT '50',
          `weekdays` varchar(32),
          `active` int NOT NULL DEFAULT '1',
          `created_at` varchar(32) NOT NULL DEFAULT (now()),
          PRIMARY KEY (`id`),
          KEY `user_id` (`user_id`),
          CONSTRAINT `scheduled_tasks_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)

    # 奖励商城表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS rewards (
          `id` int NOT NULL AUTO_INCREMENT,
          `user_id` int NOT NULL,
          `title` varchar(255) NOT NULL,
          `desc` varchar(255) DEFAULT '',
          `icon` varchar(255) NOT NULL DEFAULT 0xF09F8E81,
          `category` varchar(255) DEFAULT '',
          `image` varchar(255) DEFAULT '',
          `unlock_conditions` text,
          `claim_conditions` text,
          `unlocked` int NOT NULL DEFAULT '0',
          `claimed` int NOT NULL DEFAULT '0',
          `claimed_at` text,
          `manual_confirmed` text,
          `unlocked_at_snapshot` text,
          `created_at_exp` int DEFAULT '0',
          `created_at` varchar(32) NOT NULL DEFAULT (now()),
          PRIMARY KEY (`id`),
          KEY `user_id` (`user_id`),
          CONSTRAINT `rewards_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)

    # 奖励草稿表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reward_drafts (
          `id` int NOT NULL AUTO_INCREMENT,
          `user_id` int NOT NULL,
          `title` varchar(255) DEFAULT '',
          `desc` varchar(255) DEFAULT '',
          `icon` varchar(255) DEFAULT 0xF09F8E81,
          `category` varchar(255) DEFAULT '',
          `image` varchar(255) DEFAULT '',
          `unlock_conditions` text,
          `claim_conditions` text,
          `updated_at` varchar(32) NOT NULL DEFAULT (now()),
          PRIMARY KEY (`id`),
          UNIQUE KEY `user_id` (`user_id`),
          CONSTRAINT `reward_drafts_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)

    # 月度统计表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_monthly_stats (
          `user_id` int NOT NULL,
          `year_month` varchar(16) NOT NULL,
          `habit_count` int NOT NULL DEFAULT '0',
          `habit_xp` int NOT NULL DEFAULT '0',
          PRIMARY KEY (`user_id`,`year_month`),
          CONSTRAINT `user_monthly_stats_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)

    # 模型配置表（LLM / ASR）
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS model_configs (
          `id` int NOT NULL AUTO_INCREMENT,
          `user_id` int NOT NULL,
          `type` varchar(32) NOT NULL,
          `name` varchar(255) NOT NULL,
          `model` varchar(128) NOT NULL,
          `base_url` varchar(255) NOT NULL DEFAULT '',
          `api_key` varchar(255) NOT NULL DEFAULT '',
          `is_active` int NOT NULL DEFAULT '0',
          `created_at` varchar(32) NOT NULL DEFAULT (now()),
          `updated_at` varchar(32) NOT NULL DEFAULT (now()),
          PRIMARY KEY (`id`),
          KEY `user_id` (`user_id`),
          CONSTRAINT `model_configs_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)

    # 插入默认用户（含真实初始进度，见文件上方 DEFAULT_DEMO_USERS 的说明）
    existing = cursor.execute("SELECT id FROM users").fetchall()
    if not existing:
        cursor.executemany(
            """INSERT INTO users (name, role, level, exp, total_exp, streak, joined)
               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
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
            """SELECT COUNT(*) AS cnt FROM model_configs WHERE user_id = %s""", (uid,)
        ).fetchone()["cnt"]
        if has_cfg == 0:
            cursor.execute(
                """INSERT INTO model_configs
                   (user_id, type, name, model, base_url, api_key, is_active)
                   VALUES (%s, 'llm', '默认模型', %s, %s, %s, 1)""",
                (uid, AI_MODEL, AI_BASE_URL, AI_API_KEY),
            )
            cursor.execute(
                """INSERT INTO model_configs
                   (user_id, type, name, model, base_url, api_key, is_active)
                   VALUES (%s, 'asr', '默认语音模型', 'paraformer-realtime-v2', %s, %s, 1)""",
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
    #
    # ⚠️ 类型必须是 VARCHAR 不能是 TEXT —— MySQL 的 TEXT 不能有默认值（errno 1101），
    #    写 `TEXT DEFAULT ''` 会**每次启动都失败**，而 `except` 把它吞掉，
    #    表面上完全看不出问题。这类"被 except 掩盖的失败"本文件里踩过不止一次。
    # migrate_total_exp_to_dimensions() 可能关闭了 conn，需要重新获取
    conn = get_conn()
    for col, col_type in [
        ("sub_type", "VARCHAR(32) DEFAULT ''"),
        ("sleep_start", "VARCHAR(16) DEFAULT ''"),
        ("sleep_end", "VARCHAR(16) DEFAULT ''"),
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

    # 创建 AI 咨询板块相关表
    init_aiconsult_tables()

    # 原来这里有一段「把 user_dimensions.xp 从 INTEGER 改成 REAL」的迁移，
    # 它靠 `PRAGMA table_info()` 读列类型 —— **PRAGMA 是 SQLite 专有语法**，
    # MySQL 下必然抛异常、再被 except 吞掉，等于一段永远不生效的死代码。
    # 建表语句里 xp 本来就是 double，不需要迁移，已随 SQLite 一起移除。

    # 迁移：rewards 增加 unlocked_at_snapshot 字段（幂等）
    #
    # ⚠️⚠️ 这里原来写的是 `TEXT NOT NULL DEFAULT '{}'` —— MySQL 的 TEXT 不支持默认值
    #     （errno 1101），于是**每次启动这条 ALTER 都失败、又被 except 吞掉**，
    #     结果这一列在 MySQL 库里**从来没有被创建过**
    #     （实测：`information_schema.columns` 里查不到）。
    #
    #     而 db/rewards.py 更新奖励快照时会调
    #     `update_reward(..., unlocked_at_snapshot=...)` → 那个 UPDATE 报
    #     1054 Unknown column → 500。读路径因为写了 `d.get(..., "{}")` 兜底，
    #     所以这个 bug 一直没暴露出来。
    #     ⇒ 改成 VARCHAR 之后这条迁移才真正生效，老库会被自动补上这一列。
    conn3 = get_conn()
    try:
        conn3.execute(
            "ALTER TABLE rewards ADD COLUMN unlocked_at_snapshot "
            "VARCHAR(255) NOT NULL DEFAULT '{}'"
        )
        conn3.commit()
    except Exception:
        pass  # 列已存在
    conn3.close()

    # 迁移：把「存 JSON 却写成 varchar(255)」的列统一加宽（幂等）
    # —— 老库不会因为 CREATE TABLE IF NOT EXISTS 而改变，必须显式 MODIFY
    migrate_json_column_widths()

    # 登录鉴权：users 补字段 + 新建 refresh_tokens / api_keys（幂等）
    init_auth_tables()
    migrate_users_auth_columns()


# 存 JSON 的列 → 目标类型
#
# ⚠️⚠️ 为什么必须显式迁移（2026-09-23 真实事故，用户表现为「AI 一直说技能树不存在」）：
#   SQLite 是**无类型**的，`varchar(255)` 形同虚设 —— 几 KB 的 JSON 照存不误。
#   迁移到 MySQL 之后它变成硬限制：真实的技能树 JSON 写进去直接
#       pymysql.err.DataError: (1406, "Data too long for column 'data' at row 1")
#   而**空对象存得进去**，所以任何"建一条空记录"的冒烟都测不出来。
#
#   更糟的是这条链上的失败**全是静默的**：
#     · `save_skill_tree_draft` 无条件 return True
#     · 前端 `saveSkillTreeDraft()` 不看返回值
#   ⇒ 用户以为存上了，服务器上其实一行都没有；AI 编辑按 tree_id 校验归属 → 404
#     「技能树不存在」。
#
# 判据不靠"记得改过"，靠 `information_schema` 读实际类型（幂等，可重复执行）。
JSON_COLUMN_TARGETS = (
    # (表, 列, 目标 DDL, 可接受的 DATA_TYPE 集合, 变长列的最小长度)
    ("skill_trees", "data", "LONGTEXT NOT NULL", {"longtext"}, None),
    ("skill_trees", "update_history", "TEXT", {"text", "mediumtext", "longtext"}, None),
    ("skill_trees", "description", "VARCHAR(1000) DEFAULT ''", {"varchar"}, 1000),
    ("skill_trees", "remark", "VARCHAR(1000) DEFAULT ''", {"varchar"}, 1000),
    ("user_skills", "skill_ids", "TEXT", {"text", "mediumtext", "longtext"}, None),
    ("rewards", "unlock_conditions", "TEXT", {"text", "mediumtext", "longtext"}, None),
    ("rewards", "claim_conditions", "TEXT", {"text", "mediumtext", "longtext"}, None),
    ("rewards", "manual_confirmed", "TEXT", {"text", "mediumtext", "longtext"}, None),
    ("rewards", "unlocked_at_snapshot", "TEXT", {"text", "mediumtext", "longtext"}, None),
    ("reward_drafts", "unlock_conditions", "TEXT", {"text", "mediumtext", "longtext"}, None),
    ("reward_drafts", "claim_conditions", "TEXT", {"text", "mediumtext", "longtext"}, None),
)


def migrate_json_column_widths():
    """把 JSON 列从 varchar(255) 加宽到 TEXT / LONGTEXT（幂等）

    ⚠️ 失败**不吞**：这里的 `except` 会 log.error。
    同文件里其它幂等迁移都是 `except Exception: pass`，那正是
    `rewards.unlocked_at_snapshot` 那次「列从来没被创建过却没人知道」的原因 ——
    「列已存在」（正常）和「这条 DDL 在 MySQL 下根本跑不通」（真 bug）被混为一谈。
    加宽类迁移尤其危险：悄悄失败 = 数据一写就 1406。
    """
    from db.connection import get_conn
    conn = get_conn()
    try:
        for table, col, target, ok_types, min_len in JSON_COLUMN_TARGETS:
            row = conn.execute(
                """SELECT DATA_TYPE AS dtype, CHARACTER_MAXIMUM_LENGTH AS maxlen
                   FROM information_schema.columns
                   WHERE table_schema = DATABASE() AND table_name = %s AND column_name = %s""",
                (table, col),
            ).fetchone()
            if not row:
                continue      # 表还没建（首次初始化由 CREATE TABLE 直接建成新类型）
            dtype = (row["dtype"] or "").lower()
            if dtype not in ok_types:
                pass                                  # 需要加宽
            elif min_len is not None and (row["maxlen"] or 0) < min_len:
                pass                                  # 变长但太短
            else:
                continue                              # 已经够宽，跳过

            try:
                conn.execute(f"ALTER TABLE `{table}` MODIFY COLUMN `{col}` {target}")
                conn.commit()
                log.info("JSON 列已加宽：%s.%s → %s（原 %s%s）", table, col, target, dtype,
                         f"({row['maxlen']})" if row["maxlen"] else "")
            except Exception as e:                     # noqa: BLE001 — 但要留下痕迹
                conn.rollback()
                log.error("JSON 列加宽失败：%s.%s → %s：%s（这条不修，写数据时会 1406）",
                          table, col, target, e)
    finally:
        conn.close()


def init_auth_tables():
    """创建登录鉴权相关表（refresh_tokens / api_keys）"""
    conn = get_conn()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS refresh_tokens (
          `id` int NOT NULL AUTO_INCREMENT,
          `user_id` int NOT NULL,
          `token_hash` varchar(128) NOT NULL,
          `user_agent` varchar(255) DEFAULT '',
          `expires_at` text NOT NULL,
          `revoked` int NOT NULL DEFAULT '0',
          `created_at` varchar(32) NOT NULL DEFAULT (now()),
          PRIMARY KEY (`id`),
          KEY `idx_refresh_user` (`user_id`),
          KEY `idx_refresh_hash` (`token_hash`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS api_keys (
          `id` int NOT NULL AUTO_INCREMENT,
          `user_id` int NOT NULL,
          `name` varchar(255) NOT NULL,
          `key_hash` varchar(128) NOT NULL,
          `last_used_at` text,
          `created_at` varchar(32) NOT NULL DEFAULT (now()),
          `revoked` int NOT NULL DEFAULT '0',
          PRIMARY KEY (`id`),
          KEY `idx_apikey_hash` (`key_hash`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
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
            """UPDATE user_dimensions SET level = %s, xp = %s, xp_to_next = %s WHERE user_id = %s AND dimension_key = %s""",
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
            """SELECT COALESCE(SUM(xp), 0) as total FROM user_dimensions WHERE user_id = %s""",
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
                   VALUES (%s, %s, %s, %s, %s)
                   ON DUPLICATE KEY UPDATE level = VALUES(level),
                           xp = VALUES(xp),
                           xp_to_next = VALUES(xp_to_next)""",
                (u["id"], key, lv, cur, need),
            )
        new_total = total
        new_level = level_from_total_exp(new_total)
        new_current = new_total - total_exp_for_level(new_level)
        conn.execute(
            """UPDATE users SET level = %s, exp = %s, total_exp = %s WHERE id = %s""",
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
          `id` int NOT NULL AUTO_INCREMENT,
          `user_id` int NOT NULL,
          `tree_id` varchar(255) NOT NULL,
          `name` varchar(255) NOT NULL DEFAULT '未命名技能树',
          `description` varchar(1000) DEFAULT '',
          `data` longtext NOT NULL,
          `published_data` text,
          `image` varchar(255) DEFAULT '',
          `remark` varchar(1000) DEFAULT '',
          `node_count` int NOT NULL DEFAULT '0',
          `completed_count` int NOT NULL DEFAULT '0',
          `created_at` varchar(32) NOT NULL DEFAULT (now()),
          `updated_at` varchar(32) NOT NULL DEFAULT (now()),
          `published_at` text,
          `update_history` text,
          PRIMARY KEY (`id`),
          UNIQUE KEY `tree_id` (`tree_id`),
          KEY `user_id` (`user_id`),
          CONSTRAINT `skill_trees_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_skills (
          `id` int NOT NULL AUTO_INCREMENT,
          `user_id` int NOT NULL,
          `skill_ids` text,
          PRIMARY KEY (`id`),
          UNIQUE KEY `user_id` (`user_id`),
          CONSTRAINT `user_skills_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)

    conn.commit()
    conn.close()

    # 创建表达训练相关表
    init_expression_tables()


def init_aiconsult_tables():
    """创建 AI 资讯板块相关表（GitHub 趋势 + 国内/国际资讯缓存 + AI 分析的快照/榜单/简介/当日产出）"""
    from db.connection import get_conn
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS aiconsult_items (
          `id` int NOT NULL AUTO_INCREMENT,
          `category` varchar(32) NOT NULL,
          `title` varchar(255) NOT NULL,
          `url` varchar(500),
          `summary` text,
          `stars` int DEFAULT NULL,
          `meta` text,
          `batch_time` text NOT NULL,
          `created_at` text NOT NULL,
          PRIMARY KEY (`id`),
          KEY `idx_aiconsult_items_category` (`category`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS aiconsult_raw (
          `id` int NOT NULL AUTO_INCREMENT,
          `category` varchar(32) NOT NULL,
          `query` varchar(32) NOT NULL,
          `round_key` varchar(64) NOT NULL,
          `payload` text NOT NULL,
          `created_at` text NOT NULL,
          PRIMARY KEY (`id`),
          KEY `idx_aiconsult_raw_round` (`round_key`,`category`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)

    # ── AI 分析：GitHub 星数快照（kind=weekly 每周日 15:05 一份，长期保留；
    #    kind=daily 每天 4 份，只保留今天+昨天）──
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS aiconsult_gh_snap (
          `id` int NOT NULL AUTO_INCREMENT,
          `kind` varchar(16) NOT NULL,
          `snap_date` varchar(16) NOT NULL,
          `snap_at` text NOT NULL,
          `repo` varchar(160) NOT NULL,
          `stars` int NOT NULL,
          `created_at` text NOT NULL,
          PRIMARY KEY (`id`),
          KEY `idx_aiconsult_snap_kind_date` (`kind`,`snap_date`),
          KEY `idx_aiconsult_snap_repo` (`repo`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)

    # ── AI 分析：榜单结果（kind=weekly / daily / news_hot，payload 存 JSON）──
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS aiconsult_board (
          `id` int NOT NULL AUTO_INCREMENT,
          `kind` varchar(16) NOT NULL,
          `period_key` varchar(32) NOT NULL,
          `payload` text NOT NULL,
          `created_at` text NOT NULL,
          PRIMARY KEY (`id`),
          UNIQUE KEY `idx_aiconsult_board_kind_period` (`kind`,`period_key`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)

    # ── AI 分析：仓库中文简介缓存（按仓库名缓存，只给新上榜的重新生成）──
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS aiconsult_repo_intro (
          `id` int NOT NULL AUTO_INCREMENT,
          `repo` varchar(160) NOT NULL,
          `intro_zh` text,
          `updated_at` text NOT NULL,
          PRIMARY KEY (`id`),
          UNIQUE KEY `idx_aiconsult_intro_repo` (`repo`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)

    # ── AI 分析：当日 LLM 产出（摘要 / 榜单中文 / 资讯打分），
    #    day 唯一 → 同时充当「今天生成过没」的哨兵（懒触发 + 每天最多一次）──
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS aiconsult_analysis (
          `id` int NOT NULL AUTO_INCREMENT,
          `day` varchar(16) NOT NULL,
          `payload` text NOT NULL,
          `created_at` text NOT NULL,
          `updated_at` text NOT NULL,
          PRIMARY KEY (`id`),
          UNIQUE KEY `idx_aiconsult_analysis_day` (`day`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)

    conn.commit()
    conn.close()


def init_expression_tables():
    """创建表达训练相关表"""
    from db.connection import get_conn
    conn = get_conn()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS expression_questions (
          `id` int NOT NULL AUTO_INCREMENT,
          `question` text NOT NULL,
          `question_type` varchar(32) NOT NULL,
          `hints` text,
          `source` varchar(255) DEFAULT '',
          `created_at` varchar(32) DEFAULT (now()),
          PRIMARY KEY (`id`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS expression_answers (
          `id` int NOT NULL AUTO_INCREMENT,
          `user_id` varchar(64) NOT NULL,
          `question_id` int NOT NULL,
          `attempt` int DEFAULT '1',
          `answer` text,
          `filler_words` text,
          `score_total` double DEFAULT NULL,
          `score_fluency` double DEFAULT NULL,
          `score_logic` double DEFAULT NULL,
          `score_content` double DEFAULT NULL,
          `score_language` double DEFAULT NULL,
          `strengths` text,
          `improvements` text,
          `suggestion` text,
          `status` varchar(255) DEFAULT 'answered',
          `created_at` varchar(32) DEFAULT (now()),
          PRIMARY KEY (`id`),
          KEY `question_id` (`question_id`),
          KEY `idx_exp_answers_user` (`user_id`,`question_id`),
          CONSTRAINT `expression_answers_ibfk_1` FOREIGN KEY (`question_id`) REFERENCES `expression_questions` (`id`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)

    conn.commit()
    conn.close()