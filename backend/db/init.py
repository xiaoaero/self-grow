"""
Self Grow — 数据库初始化

建表（15 张表）+ 插入默认用户和默认奖励。
"""

import json
import datetime

from db.connection import get_conn
from db.dimensions import get_total_exp_from_dimensions
from models.constants import DIMENSION_KEYS, DEFAULT_DIMENSIONS
from models.level import level_from_total_exp, total_exp_for_level


def init_default_dimensions(user_id: int, conn=None):
    """为指定用户插入 8 维默认数据（如果还不存在）"""
    if conn:
        for key, lv, xp, xpn in DEFAULT_DIMENSIONS:
            conn.execute(
                """INSERT OR IGNORE INTO user_dimensions (user_id, dimension_key, level, xp, xp_to_next)
                   VALUES (?, ?, ?, ?, ?)""",
                (user_id, key, lv, xp, xpn),
            )
    else:
        conn2 = get_conn()
        for key, lv, xp, xpn in DEFAULT_DIMENSIONS:
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
            icon TEXT NOT NULL DEFAULT '✅',
            intro TEXT DEFAULT '',
            category TEXT NOT NULL,
            weekly_target INTEGER NOT NULL DEFAULT 7,
            xp_reward INTEGER NOT NULL DEFAULT 15,
            active INTEGER NOT NULL DEFAULT 1,
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
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
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_action_logs_user_date
        ON action_logs(user_id, start_time)
    """)

    # 用户维度经验表（八维属性）
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_dimensions (
            user_id INTEGER NOT NULL,
            dimension_key TEXT NOT NULL,
            level INTEGER NOT NULL DEFAULT 1,
            xp INTEGER NOT NULL DEFAULT 0,
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
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
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
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
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
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
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
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    # 插入默认用户
    existing = cursor.execute("SELECT id FROM users").fetchall()
    if not existing:
        users = [
            ("test", "user", 188, 136388, 6682, 21, "2026-01-15"),
            ("admin", "admin", 99, 45000, 45000, 7, "2026-06-01"),
        ]
        cursor.executemany(
            "INSERT INTO users (name, role, level, exp, total_exp, streak, joined) VALUES (?, ?, ?, ?, ?, ?, ?)",
            users,
        )

        # 为默认用户初始化 8 维数据
        for u in cursor.execute("SELECT id FROM users").fetchall():
            init_default_dimensions(u["id"], conn=conn)

        # 为默认用户插入默认奖励
        DEFAULT_REWARDS = [
            {"title": "看一部电影", "desc": "奖励自己看一场想看的电影", "icon": "🎬", "category": "娱乐",
             "unlock_conditions": [{"type": "total_exp", "threshold": 500}],
             "claim_conditions": [{"type": "week_rate", "threshold": 100}]},
            {"title": "游戏时间2小时", "desc": "尽情享受游戏时光", "icon": "🎮", "category": "娱乐",
             "unlock_conditions": [{"type": "total_exp", "threshold": 1000}],
             "claim_conditions": [{"type": "habit_streak_any", "threshold": 7}]},
            {"title": "买一本新书", "desc": "挑选一本心仪已久的书", "icon": "📚", "category": "学习",
             "unlock_conditions": [{"type": "goals_done", "threshold": 1}],
             "claim_conditions": [{"type": "tasks_done", "threshold": 10}]},
            {"title": "一次SPA放松", "desc": "预约一次SPA或按摩", "icon": "💆", "category": "健康",
             "unlock_conditions": [{"type": "total_exp", "threshold": 1500}],
             "claim_conditions": [{"type": "habit_streak_any", "threshold": 30}],
             "unlocked": 1, "claimed": 1, "claimed_at": "2026-06-20"},
            {"title": "美食大餐", "desc": "去喜欢的餐厅吃一顿", "icon": "🍽️", "category": "生活",
             "unlock_conditions": [{"type": "total_exp", "threshold": 2000}],
             "claim_conditions": [{"type": "habit_streak_any", "threshold": 14}, {"type": "week_rate", "threshold": 80}],
             "unlocked": 1, "claimed": 1, "claimed_at": "2026-06-15"},
            {"title": "新运动装备", "desc": "购买一件运动装备", "icon": "👟", "category": "购物",
             "unlock_conditions": [{"type": "total_exp", "threshold": 3000}],
             "claim_conditions": [{"type": "dim_level", "targetId": "health", "threshold": 5}, {"type": "habit_streak_any", "threshold": 30}]},
            {"title": "短途旅行", "desc": "周末去周边城市游玩", "icon": "✈️", "category": "旅行",
             "unlock_conditions": [{"type": "total_exp", "threshold": 5000}, {"type": "goals_done", "threshold": 3}],
             "claim_conditions": [{"type": "habit_streak_any", "threshold": 60}, {"type": "tasks_done", "threshold": 50}]},
        ]
        for u in cursor.execute("SELECT id, total_exp FROM users").fetchall():
            for rw in DEFAULT_REWARDS:
                unlock_json = json.dumps(rw["unlock_conditions"], ensure_ascii=False)
                claim_json = json.dumps(rw["claim_conditions"], ensure_ascii=False)
                cursor.execute(
                    """INSERT INTO rewards (user_id, title, desc, icon, category, unlock_conditions, claim_conditions, unlocked, claimed, claimed_at, created_at_exp)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (u["id"], rw["title"], rw["desc"], rw["icon"], rw["category"],
                     unlock_json, claim_json,
                     rw.get("unlocked", 0), rw.get("claimed", 0),
                     rw.get("claimed_at", None), u["total_exp"]),
                )

    conn.commit()
    conn.close()

    # 数据迁移：检测现有用户的 total_exp 是否已经分配到维度
    migrate_total_exp_to_dimensions()


def migrate_total_exp_to_dimensions():
    """将 users.total_exp 按比例分配到 8 维（仅在维度 SUM 为 0 时执行一次）"""
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
            xp = per_dim + (1 if i < remainder else 0)
            if xp > 0:
                conn.execute(
                    """INSERT INTO user_dimensions (user_id, dimension_key, level, xp, xp_to_next)
                       VALUES (?, ?, 1, ?, 150)
                       ON CONFLICT(user_id, dimension_key) DO UPDATE SET xp = xp + ?""",
                    (u["id"], key, xp, xp),
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