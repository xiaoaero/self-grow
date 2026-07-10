"""
Self Grow — 数据库操作（向后兼容层）

⚠️ 警告：所有代码已迁移到 db/ 子模块。
此文件仅作为向后兼容的 re-export 层，请优先使用 from db.<module> import xxx。

新的导入方式：
  from db.connection import get_conn
  from db.init import init_db
  from db.users import get_user
  from db.habits import get_habits
  from db.actions import create_action_log
  from db.goals import get_goals
  from db.tasks import get_tasks
  from db.dimensions import upsert_dimension
  from db.stats import get_profile_stats
  from db.rewards import get_rewards
  from db.batch import archive_incomplete_tasks
  from models.level import exp_for_level, total_exp_for_level, level_from_total_exp
  from models.constants import CATEGORIES, RANK_TABLE, get_rank_info, get_category, calculate_exp
"""

import warnings
warnings.warn(
    "Importing from 'database' is deprecated. Use 'db.<module>' instead.",
    DeprecationWarning,
    stacklevel=2,
)

# db.connection
from db.connection import get_conn, DB_PATH

# db.init
from db.init import init_db, init_default_dimensions, migrate_total_exp_to_dimensions

# db.users
from db.users import get_user, get_user_by_name, get_all_users, get_user_stats, upsert_user_stats, update_user_exp

# db.habits
from db.habits import get_habits, get_habit, create_habit, update_habit, delete_habits, get_checkins_in_range, get_all_checkins_in_range, upsert_checkin, delete_checkin, calculate_streak

# db.actions
from db.actions import create_action_log, get_action_logs, get_today_action_stats, get_activity_feed

# db.goals
from db.goals import get_goals, get_goal, get_goal_milestones, create_goal, update_goal, delete_goal, claim_goal_reward

# db.tasks
from db.tasks import get_task, get_tasks_by_status, get_tasks_paginated, get_today_tasks, create_task, update_task, delete_task, clear_task_history, claim_task_reward

# db.scheduled_tasks
from db.scheduled_tasks import get_scheduled_tasks, create_scheduled_task, update_scheduled_task, delete_scheduled_task, get_scheduled_tasks_by_type

# db.dimensions
from db.dimensions import get_user_dimensions, upsert_dimension, recalc_dimensions_from_actions, get_total_exp_from_dimensions

# db.stats
from db.stats import get_recent_activities, get_yearly_activity, get_daily_exp_trend, get_profile_stats

# db.rewards
from db.rewards import get_rewards, get_reward, create_reward, update_reward, delete_reward, claim_reward, manual_confirm_condition, evaluate_all_rewards, evaluate_reward, calculate_week_completion_rate, evaluate_condition

# db.batch
from db.batch import archive_incomplete_tasks, refresh_daily_tasks, refresh_weekly_tasks, settle_habit_exp_for_user, snapshot_daily_stats

# models.level（原 database.py 中的等级公式）
from models.level import exp_for_level, total_exp_for_level, level_from_total_exp

# models.constants（原 database.py 中的常量）
from models.constants import CATEGORIES, RANK_TABLE, get_rank_info, get_category, calculate_exp