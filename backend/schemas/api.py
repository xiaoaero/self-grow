"""
Self Grow — Pydantic 请求/响应模型

所有 API 的请求体和响应体定义。
"""

from typing import Optional, List
from pydantic import BaseModel


# ================================================================
# AI Chat
# ================================================================
class ChatRequest(BaseModel):
    messages: list
    tree_state: Optional[dict] = None


class ChatResponse(BaseModel):
    content: Optional[str] = None
    tool_calls: Optional[list] = None


# ================================================================
# 用户
# ================================================================
class LoginRequest(BaseModel):
    user_id: int


class StatsSyncRequest(BaseModel):
    focus_minutes: int = 0
    tasks_done: int = 0
    habits_checked: int = 0
    exp_earned: int = 0


class ExpAddRequest(BaseModel):
    amount: int
    category: str = None


# ================================================================
# 习惯
# ================================================================
class CreateHabitRequest(BaseModel):
    name: str
    icon: str = '✅'
    intro: str = ''
    category: str
    weekly_target: int = 7
    xp_reward: int = 15


class UpdateHabitRequest(BaseModel):
    name: str = None
    icon: str = None
    intro: str = None
    category: str = None
    weekly_target: int = None
    xp_reward: int = None
    active: int = None


class DeleteHabitsRequest(BaseModel):
    ids: List[int]


class ToggleCheckinResponse(BaseModel):
    status: str
    streak: int


# ================================================================
# AI 行动解析对话
# ================================================================
class AIChatActionRequest(BaseModel):
    messages: list  # 对话历史 [{role, content}, ...]


class AISubmitActionItem(BaseModel):
    category_id: str
    sub_type: str = ""
    duration: int = 0
    note: str = ""
    dimension_exp: float = 0
    sleep_start: str = ""
    sleep_end: str = ""


class AISubmitActionsRequest(BaseModel):
    actions: list[AISubmitActionItem]


# ================================================================
# 行动记录
# ================================================================
class CreateActionRequest(BaseModel):
    category_id: str
    start_time: str
    duration: int = 0
    note: str = ''
    sub_type: str = ''  # 子类型：health-sport/health-sleep/relation-online/relation-offline/work-daily/work-overtime-weekday/work-overtime-weekend/create-output/create-material/create-publish/finance-study/finance-review
    sleep_start: str = ''  # 睡觉时间 HH:MM（健康-睡眠模式用）
    sleep_end: str = ''  # 起床时间 HH:MM（健康-睡眠模式用）


class ActionLogResponse(BaseModel):
    id: int
    category_id: str
    category_name: str
    start_time: str
    end_time: str
    duration: int
    note: str
    exp_earned: int
    sub_type: str = ''
    sleep_start: str = ''
    sleep_end: str = ''


class RoutineStatusResponse(BaseModel):
    streak: int = 0
    has_protection: bool = False
    last_date: str = ''
    next_bonus: int = 0


# ================================================================
# 目标
# ================================================================
class GoalMilestoneItem(BaseModel):
    done: int = 0
    note: str = ''


class CreateGoalRequest(BaseModel):
    title: str
    intro: str = ''
    category: str
    deadline: str = ''
    reward_exp: int = 0
    category_image: str = ''
    milestones: list[GoalMilestoneItem] = []


class UpdateGoalRequest(BaseModel):
    title: str = None
    intro: str = None
    category: str = None
    deadline: str = None
    reward_exp: int = None
    category_image: str = None
    milestones: list[GoalMilestoneItem] = None


# ================================================================
# 任务
# ================================================================
class CreateTaskRequest(BaseModel):
    title: str
    category: str
    priority: str = 'mid'
    exp: int = 50
    intro: str = ''
    status: str = 'todo'
    source_type: str = 'today'
    source_template_id: int = None


class UpdateTaskRequest(BaseModel):
    title: str = None
    category: str = None
    priority: str = None
    exp: int = None
    intro: str = None
    status: str = None
    deadline: str = None
    completed_at: str = None
    claimed: int = None
    source_type: str = None
    source_template_id: int = None


class PatchTaskStatusRequest(BaseModel):
    status: str


# ================================================================
# 定时任务模板
# ================================================================
class CreateScheduledTaskRequest(BaseModel):
    type: str
    title: str
    category: str
    priority: str = 'mid'
    exp: int = 50
    intro: str = ''
    weekdays: list[int] = []
    active: int = 1


class UpdateScheduledTaskRequest(BaseModel):
    type: str = None
    title: str = None
    category: str = None
    priority: str = None
    exp: int = None
    intro: str = None
    weekdays: list[int] = None
    active: int = None


# ================================================================
# 奖励商城
# ================================================================
class CreateRewardRequest(BaseModel):
    title: str
    desc: str = ''
    icon: str = '🎁'
    category: str = ''
    image: str = ''
    unlock_conditions: list = []
    claim_conditions: list = []


class UpdateRewardRequest(BaseModel):
    title: str = None
    desc: str = None
    icon: str = None
    category: str = None
    image: str = None
    unlock_conditions: list = None
    claim_conditions: list = None
    unlocked: int = None
    claimed: int = None
    claimed_at: str = None


class ManualConfirmRequest(BaseModel):
    condition_text: str


# ================================================================
# 习惯 AI 分析
# ================================================================
class HabitAIInsightRequest(BaseModel):
    date_from: str  # ISO date: YYYY-MM-DD
    date_to: str  # ISO date: YYYY-MM-DD


# ================================================================
# 习惯 AI 图标设计
# ================================================================
class HabitAIIconRequest(BaseModel):
    name: str
    intro: str = ""
    category: str