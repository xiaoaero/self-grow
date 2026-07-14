"""
Self Grow — 常量定义

集中存放 CATEGORIES（8 维属性）、RANK_TABLE（10 段位）等全局常量。
"""

import math
from datetime import datetime, date

# ================================================================
# 8 维属性分类定义
# ================================================================
CATEGORIES = [
    {"id": "health",   "name": "健康", "color": "#FF7B72", "exp_rate": 10, "global_rate": 1.0},
    {"id": "study",    "name": "学习", "color": "#58D5C9", "exp_rate": 10, "global_rate": 1.0},
    {"id": "relation", "name": "关系", "color": "#FF91A8", "exp_rate": 8,  "global_rate": 0.5},
    {"id": "work",     "name": "工作", "color": "#FFCA40", "exp_rate": 12, "global_rate": 1.0},
    {"id": "create",   "name": "创作", "color": "#B794F6", "exp_rate": 8,  "global_rate": 0.5},
    {"id": "finance",  "name": "财务", "color": "#4ADE80", "exp_rate": 6,  "global_rate": 0.5},
    {"id": "hobby",    "name": "爱好", "color": "#F472B6", "exp_rate": 7,  "global_rate": 0.75},
    {"id": "soul",     "name": "魅力", "color": "#FBBF24", "exp_rate": 9,  "global_rate": 0.5},
]

DIMENSION_KEYS = ["health", "study", "relation", "work", "create", "finance", "hobby", "soul"]

DEFAULT_DIMENSIONS = [
    ("health", 1, 0, 150),
    ("study", 1, 0, 150),
    ("relation", 1, 0, 150),
    ("work", 1, 0, 150),
    ("create", 1, 0, 150),
    ("finance", 1, 0, 150),
    ("hobby", 1, 0, 150),
    ("soul", 1, 0, 150),
]

# 维度颜色映射（用于统计页面的中文名+颜色）
CATEGORY_MAP = {
    "health": ("健康", "#FF7B72"),
    "study": ("学习", "#58D5C9"),
    "relation": ("关系", "#FF91A8"),
    "work": ("工作", "#FFCA40"),
    "create": ("创作", "#B794F6"),
    "finance": ("财务", "#4ADE80"),
    "hobby": ("爱好", "#F472B6"),
    "soul": ("魅力", "#FBBF24"),
}


def get_category(category_id: str) -> dict:
    """按 ID 获取分类定义"""
    for c in CATEGORIES:
        if c["id"] == category_id:
            return c
    return None


# ================================================================
# 维度经验计算函数（新规则）
# ================================================================

def calculate_exp(category_id: str, duration: int, sub_type: str = None,
                  sleep_start: str = None, sleep_end: str = None,
                  today: str = None) -> dict:
    """
    根据新计分规则计算维度经验。

    参数:
        category_id: 维度ID
        duration: 时长（分钟）
        sub_type: 子类型（如 health-sport, health-sleep, relation-online 等）
        sleep_start: 睡觉时间（HH:MM）
        sleep_end: 起床时间（HH:MM）
        today: 当前日期（YYYY-MM-DD），用于作息规律检测，默认当天

    返回:
        {
            "dimension_exp": float,   # 维度经验值（原始值）
            "global_exp": float,      # 计入全局的经验值（dimension_exp × global_rate）
            "sub_type": str,          # 实际使用的子类型
            "sleep_valid": bool,      # 睡眠是否有效
            "routine_extra": float,   # 作息规律额外经验
        }
    """
    cat = get_category(category_id)
    if not cat:
        return {"dimension_exp": 0, "global_exp": 0, "sub_type": sub_type or "", "sleep_valid": False, "routine_extra": 0}

    global_rate = cat["global_rate"]
    result = {"dimension_exp": 0, "global_exp": 0, "sub_type": sub_type or "", "sleep_valid": False, "routine_extra": 0}

    if category_id == "health":
        return _calc_health(duration, sub_type, sleep_start, sleep_end, global_rate, today)
    elif category_id == "study":
        return _calc_study(duration, global_rate)
    elif category_id == "relation":
        return _calc_relation(duration, sub_type, global_rate)
    elif category_id == "work":
        return _calc_work(sub_type, global_rate)
    elif category_id == "create":
        return _calc_create(duration, sub_type, global_rate)
    elif category_id == "finance":
        return _calc_finance(duration, sub_type, global_rate, today)
    elif category_id == "hobby":
        return _calc_hobby(duration, global_rate)
    elif category_id == "soul":
        return _calc_soul(duration, global_rate)
    return result


def _calc_study(duration: int, global_rate: float) -> dict:
    """学习：floor(duration/20) × 10，最小20分钟"""
    blocks = duration // 20
    exp = blocks * 10
    return {"dimension_exp": exp, "global_exp": round(exp * global_rate), "sub_type": "", "sleep_valid": False, "routine_extra": 0}


def _calc_health(duration: int, sub_type: str, sleep_start: str, sleep_end: str,
                 global_rate: float, today_str: str) -> dict:
    """健康：运动或睡眠"""
    # 判断是否为睡眠模式
    is_sleep = (sub_type == "health-sleep") or (sleep_start and sleep_end)

    if is_sleep:
        return _calc_health_sleep(sleep_start, sleep_end, global_rate, today_str)
    else:
        return _calc_health_sport(duration, global_rate)


def _calc_health_sport(duration: int, global_rate: float) -> dict:
    """运动：floor(duration/15) × 3.75，最小15分钟"""
    blocks = duration // 15
    exp = blocks * 3.75
    return {"dimension_exp": exp, "global_exp": round(exp * global_rate), "sub_type": "health-sport", "sleep_valid": False, "routine_extra": 0}


def _calc_health_sleep(sleep_start: str, sleep_end: str, global_rate: float, today_str: str) -> dict:
    """睡眠：计算基础睡眠经验 + 作息规律额外经验"""
    if not sleep_start or not sleep_end:
        return {"dimension_exp": 0, "global_exp": 0, "sub_type": "health-sleep", "sleep_valid": False, "routine_extra": 0}

    # 解析时间
    try:
        sh, sm = map(int, sleep_start.split(":"))
        eh, em = map(int, sleep_end.split(":"))
    except (ValueError, AttributeError):
        return {"dimension_exp": 0, "global_exp": 0, "sub_type": "health-sleep", "sleep_valid": False, "routine_extra": 0}

    # 计算睡眠时长（跨天处理）
    start_minutes = sh * 60 + sm
    end_minutes = eh * 60 + em
    if end_minutes <= start_minutes:
        end_minutes += 24 * 60  # 跨天
    sleep_duration = end_minutes - start_minutes  # 分钟

    # 检查睡眠时长是否在6~9小时之间
    if sleep_duration < 360 or sleep_duration > 540:  # 6h=360min, 9h=540min
        return {"dimension_exp": 0, "global_exp": 0, "sub_type": "health-sleep", "sleep_valid": False, "routine_extra": 0}

    # 计算基础睡眠经验：23:00(1380分钟)为理想入睡时间
    ideal_bedtime = 23 * 60  # 1380分钟
    actual_bedtime = start_minutes
    # 如果入睡时间在0:00-12:00之间，视为跨天（前一天的晚睡）
    if actual_bedtime < 12 * 60:
        actual_bedtime += 24 * 60

    late_minutes = max(0, actual_bedtime - ideal_bedtime)
    base_exp = max(0, 20 - late_minutes // 4)

    # 作息规律检测
    routine_extra = 0
    is_routine = _check_is_routine(sleep_start, sleep_end)

    if is_routine:
        routine_extra = _calc_routine_bonus(today_str)

    total_exp = base_exp + routine_extra
    return {
        "dimension_exp": total_exp,
        "global_exp": round(total_exp * global_rate),
        "sub_type": "health-sleep",
        "sleep_valid": True,
        "routine_extra": routine_extra,
    }


def _check_is_routine(sleep_start: str, sleep_end: str) -> bool:
    """检查是否符合作息规律定义：23:00~00:00睡，07:00~08:00起"""
    try:
        sh, sm = map(int, sleep_start.split(":"))
        eh, em = map(int, sleep_end.split(":"))
    except (ValueError, AttributeError):
        return False

    # 睡觉时间在23:00~00:00之间
    sleep_minutes = sh * 60 + sm
    # 23:00(1380) ~ 00:00(1440)，跨天处理
    if sleep_minutes < 12 * 60:  # 0:00~12:00视为跨天
        sleep_minutes += 24 * 60
    if sleep_minutes < 23 * 60 or sleep_minutes > 24 * 60:
        return False

    # 起床时间在07:00~08:00之间
    wake_minutes = eh * 60 + em
    if wake_minutes < 7 * 60 or wake_minutes > 8 * 60:
        return False

    return True


# 作息规律数据存储（简化版：使用内存+数据库持久化）
_routine_cache = {}  # user_id -> {"streak": int, "has_protection": bool, "last_date": str}


def _calc_routine_bonus(today_str: str) -> float:
    """
    计算作息规律额外经验。
    从第6天起每天+15，保护机制处理。
    注意：此函数假设调用前已经确认今天符合规律定义。
    实际的连续天数管理由后端API负责持久化。
    """
    # 简化：返回15表示符合规律时应有的额外经验
    # 实际业务逻辑在 routers/actions.py 中处理
    return 15


def get_routine_info(user_id: int) -> dict:
    """获取用户的作息规律信息（从缓存或数据库）"""
    info = _routine_cache.get(user_id, {"streak": 0, "has_protection": False, "last_date": None})
    return info


def update_routine_info(user_id: int, is_routine_today: bool, today_str: str):
    """更新作息规律状态"""
    info = _routine_cache.get(user_id, {"streak": 0, "has_protection": False, "last_date": None})

    if not is_routine_today:
        if info["has_protection"]:
            # 消耗保护：不加经验但保留连续天数
            info["has_protection"] = False
        else:
            # 无保护：重置
            info["streak"] = 0
        info["last_date"] = today_str
        _routine_cache[user_id] = info
        return info

    # 今天符合规律
    if info["last_date"] is not None:
        # 检查是否连续（日期连续）
        from datetime import datetime, timedelta
        last = datetime.strptime(info["last_date"], "%Y-%m-%d").date()
        today = datetime.strptime(today_str, "%Y-%m-%d").date()
        if (today - last).days == 1:
            info["streak"] += 1
        elif (today - last).days > 1:
            # 不连续，重置
            info["streak"] = 1
        else:
            # 同一天，不重复计数
            pass
    else:
        info["streak"] = 1

    # 连续>=10天且没有保护机会时，获得保护
    if info["streak"] >= 10 and not info["has_protection"]:
        info["has_protection"] = True

    info["last_date"] = today_str
    _routine_cache[user_id] = info
    return info


def _calc_relation(duration: int, sub_type: str, global_rate: float) -> dict:
    """关系：线下+80/次，线上floor(duration/30)×20"""
    if sub_type == "relation-offline":
        exp = 80
        return {"dimension_exp": exp, "global_exp": round(exp * global_rate), "sub_type": sub_type, "sleep_valid": False, "routine_extra": 0}
    else:
        blocks = duration // 30
        exp = blocks * 20
        return {"dimension_exp": exp, "global_exp": round(exp * global_rate), "sub_type": "relation-online", "sleep_valid": False, "routine_extra": 0}


def _calc_work(sub_type: str, global_rate: float) -> dict:
    """工作：日常+10，工作日加班+20，休息日加班+30"""
    if sub_type == "work-overtime-weekend":
        exp = 30
    elif sub_type == "work-overtime-weekday":
        exp = 20
    else:
        exp = 10  # 日常
    return {"dimension_exp": exp, "global_exp": round(exp * global_rate), "sub_type": sub_type or "work-daily", "sleep_valid": False, "routine_extra": 0}


def _calc_create(duration: int, sub_type: str, global_rate: float) -> dict:
    """创作：产出120/h，素材40/h（最小30分钟），发布+160"""
    if sub_type == "create-publish":
        exp = 160
    elif sub_type == "create-material":
        blocks = duration // 30
        exp = blocks * 20  # 30分钟=20EXP，1h=40EXP
    else:
        # 产出
        exp = duration * 2  # 120/h = 2/分钟
    return {"dimension_exp": exp, "global_exp": round(exp * global_rate), "sub_type": sub_type or "create-output", "sleep_valid": False, "routine_extra": 0}


def _calc_finance(duration: int, sub_type: str, global_rate: float, today_str: str) -> dict:
    """财务：学习梳理80/h，月度复盘+100（每月限1次）"""
    if sub_type == "finance-review":
        exp = 100
    else:
        exp = duration * 4 / 3  # 80/h = 4/3每分钟
    return {"dimension_exp": exp, "global_exp": round(exp * global_rate), "sub_type": sub_type or "finance-study", "sleep_valid": False, "routine_extra": 0}


def _calc_hobby(duration: int, global_rate: float) -> dict:
    """爱好：40/h"""
    exp = duration * 2 / 3  # 40/h = 2/3每分钟
    return {"dimension_exp": exp, "global_exp": round(exp * global_rate), "sub_type": "", "sleep_valid": False, "routine_extra": 0}


def _calc_soul(duration: int, global_rate: float) -> dict:
    """魅力：50/h"""
    exp = duration * 5 / 6  # 50/h = 5/6每分钟
    return {"dimension_exp": exp, "global_exp": round(exp * global_rate), "sub_type": "", "sleep_valid": False, "routine_extra": 0}


# 旧的 calculate_exp 保留别名（向后兼容）
def calculate_exp_old(category_id: str, duration: int) -> int:
    """旧版：exp_rate × floor(duration / 15)"""
    cat = get_category(category_id)
    if not cat:
        return 0
    return cat["exp_rate"] * (duration // 15)


# ================================================================
# 段位系统（10 段位，每 20 级一段）
# ================================================================
RANK_TABLE = [
    {"tier": 1,  "min": 1,   "max": 20,   "name": "初阶冒险者"},
    {"tier": 2,  "min": 21,  "max": 40,   "name": "历练冒险者"},
    {"tier": 3,  "min": 41,  "max": 60,   "name": "资深冒险者"},
    {"tier": 4,  "min": 61,  "max": 80,   "name": "荒野冒险者"},
    {"tier": 5,  "min": 81,  "max": 100,  "name": "征途冒险者"},
    {"tier": 6,  "min": 101, "max": 120,  "name": "秘境冒险者"},
    {"tier": 7,  "min": 121, "max": 140,  "name": "破晓冒险者"},
    {"tier": 8,  "min": 141, "max": 160,  "name": "星途冒险者"},
    {"tier": 9,  "min": 161, "max": 180,  "name": "传奇冒险者"},
    {"tier": 10, "min": 181, "max": 200,  "name": "不朽冒险者"},
]


def get_rank_info(level: int) -> dict:
    """根据等级获取段位信息"""
    lv = max(1, min(level, 200))
    for r in RANK_TABLE:
        if r["min"] <= lv <= r["max"]:
            return r
    return RANK_TABLE[-1]