"""
Self Grow — 常量定义

集中存放 CATEGORIES（8 维属性）、RANK_TABLE（10 段位）等全局常量。
"""

# ================================================================
# 8 维属性分类定义
# ================================================================
CATEGORIES = [
    {"id": "health",   "name": "健康", "color": "#FF7B72", "exp_rate": 10},
    {"id": "study",    "name": "学习", "color": "#58D5C9", "exp_rate": 10},
    {"id": "relation", "name": "关系", "color": "#FF91A8", "exp_rate": 8},
    {"id": "work",     "name": "工作", "color": "#FFCA40", "exp_rate": 12},
    {"id": "create",   "name": "创作", "color": "#B794F6", "exp_rate": 8},
    {"id": "finance",  "name": "财务", "color": "#4ADE80", "exp_rate": 6},
    {"id": "hobby",    "name": "爱好", "color": "#F472B6", "exp_rate": 7},
    {"id": "soul",     "name": "心灵", "color": "#FBBF24", "exp_rate": 9},
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
    "soul": ("心灵", "#FBBF24"),
}


def get_category(category_id: str) -> dict:
    """按 ID 获取分类定义"""
    for c in CATEGORIES:
        if c["id"] == category_id:
            return c
    return None


def calculate_exp(category_id: str, duration: int) -> int:
    """计算行动经验值：exp_rate × floor(duration / 15)"""
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