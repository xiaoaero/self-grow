"""
Self Grow — 等级公式（唯一来源）

提供经验值与等级的相互转换函数。
前端 utils.js 中的等级公式应从此处同步，不再各自维护。
"""

import math


def exp_for_level(L: int) -> int:
    """计算从 L 级升到 L+1 级所需的经验值"""
    if L <= 0 or L >= 200:
        return 0
    return round(5.5632 * (L - 1) ** 2 + 300)


def total_exp_for_level(L: int) -> int:
    """计算从 1 级升到 L 级所需的累计经验值"""
    total = 0
    for i in range(1, L):
        total += exp_for_level(i)
    return total


def level_from_total_exp(total_exp: int) -> int:
    """根据累计总经验值计算当前等级（上限 200 级）
    total_exp 可能是浮点数（维度表 xp 为 REAL），取整后计算等级
    """
    if total_exp <= 0:
        return 1
    level = 1
    cumulative = 0
    while level < 200:
        need = exp_for_level(level)
        if cumulative + need > total_exp:
            break
        cumulative += need
        level += 1
    return min(level, 200)