"""
维度数据的「不变式」回归测试

为什么专门给这件事写测试：这条不变式**踩过两次坑**，而且两次都是"静默的" ——
不报错、不崩，只是前端进度条显示错的数字，要很久以后才有人发现。

背景（见 db/init.py 顶部注释）：
    user_dimensions 每行三个字段必须配套 ——
        level       当前维度等级
        xp          该等级内的进度（**不是累计**）
        xp_to_next  从 level 升到 level+1 需要多少经验

    不变式：  0 <= xp < xp_to_next          （前端用它算进度百分比）
              xp_to_next == exp_for_level(level)   （刻度必须来自等级公式）

两次真实事故：
    ① 早期 DEFAULT_DIMENSIONS 写死 `level=1, xp_to_next=150`，
       而 exp_for_level(1) == 300 —— 刻度错一倍。当时还叠加了
       「把 total_exp//8 当成 xp」的错，于是库里出现
       「Lv1 却有 5625 经验、还差 150 升级」这种自相矛盾的行，
       前端 min(xp/xp_to_next, 1) 渲染成 100% 满格，其实是脏数据。
    ② 2026-09-17 全代码审查时发现 ① 的**修复没覆盖到 fallback 分支**：
       DEFAULT_DIMENSIONS 仍留着 150（demo 名单里的用户走的是
       DEFAULT_DEMO_DIMENSIONS，所以不容易暴露）。
       同时 demo 用户 test 的 `exp` 与 `total_exp` 差 30，违反恒等式 ①。

修完就把这三条恒等式固化成断言 —— 以后改等级公式或种子数据，这里会先红。
"""

from models.constants import (
    CATEGORIES, DIMENSION_KEYS, CATEGORY_MAP, DEFAULT_DIMENSIONS,
)
from models.level import exp_for_level, total_exp_for_level


# ================================================================
# 工具
# ================================================================

def _check_dimension_rows(rows, where: str):
    """断言一批 (key, level, xp, xp_to_next) 满足不变式"""
    assert rows, f"{where}：维度行不该为空"
    for key, lv, xp, xp_to_next in rows:
        want = exp_for_level(lv)
        assert xp_to_next == want, (
            f"{where} 的 {key}：xp_to_next={xp_to_next}，"
            f"但 exp_for_level({lv})={want} —— 刻度与等级公式不一致"
        )
        assert 0 <= xp < xp_to_next, (
            f"{where} 的 {key}：xp={xp} 不满足 0 <= xp < {xp_to_next}"
        )


# ================================================================
# 恒定不变式
# ================================================================

def test_default_dimensions_satisfy_invariant():
    """fallback 的 DEFAULT_DIMENSIONS 必须满足不变式（事故 ② 就是这里）"""
    _check_dimension_rows(DEFAULT_DIMENSIONS, "DEFAULT_DIMENSIONS")

    # 顺带钉死：新用户是从 Lv1 起步、xp 为 0，刻度必须是 exp_for_level(1)
    for key, lv, xp, xp_to_next in DEFAULT_DIMENSIONS:
        assert lv == 1, f"{key} 的初始等级应为 1，实际 {lv}"
        assert xp == 0, f"{key} 的初始 xp 应为 0，实际 {xp}"
        assert xp_to_next == exp_for_level(1), (
            f"{key} 的初始刻度应为 exp_for_level(1)={exp_for_level(1)}，"
            f"实际 {xp_to_next}（历史上这里写死过 150）"
        )


def test_demo_dimensions_satisfy_invariant():
    """空库种子里的 demo 维度数据也必须满足不变式"""
    from db.init import DEFAULT_DEMO_DIMENSIONS

    assert DEFAULT_DEMO_DIMENSIONS, "demo 维度数据不该为空"
    for name, rows in DEFAULT_DEMO_DIMENSIONS.items():
        _check_dimension_rows(rows, f"DEFAULT_DEMO_DIMENSIONS[{name}]")


def test_demo_users_are_self_consistent():
    """demo 用户的两个总经验口径必须对得上（事故 ② 的第二半）"""
    from db.init import DEFAULT_DEMO_USERS, DEFAULT_DEMO_DIMENSIONS

    for name, role, lv, exp, total_exp, streak, joined in DEFAULT_DEMO_USERS:
        # ① 用户行自身：total_exp == total_exp_for_level(level) + exp
        derived = total_exp_for_level(lv) + exp
        assert derived == total_exp, (
            f"{name}：total_exp_for_level({lv})+{exp}={derived}，"
            f"但用户行填的 total_exp={total_exp}（差 {total_exp - derived}）"
        )

        # ② 与 8 维反推之和一致
        rows = DEFAULT_DEMO_DIMENSIONS.get(name)
        if rows is None:
            continue                      # 没配 demo 维度的用户走 fallback，跳过
        summed = round(sum(total_exp_for_level(r[1]) + r[2] for r in rows))
        assert summed == total_exp, (
            f"{name}：8 维反推之和={summed}，用户行 total_exp={total_exp}"
        )


def test_dimension_level_cap_matches_documented_range():
    """维度等级上限 140 —— db/dimensions.py 与文档必须一致

    注：用户总等级上限是 200（models/level.py），维度上限是 140，两者不同，
    别把它们当成同一个上限。这里只钉住维度侧，改上限时应该同时改这里和文档。
    """
    import io
    import os

    src = io.open(
        os.path.join(os.path.dirname(__file__), "..", "db", "dimensions.py"),
        encoding="utf-8",
    ).read()
    assert "140" in src, "db/dimensions.py 里找不到维度等级上限 140，可能被改动"


# ================================================================
# 派生常量：不允许再出现「手工维护的第二份副本」
# ================================================================

def test_dimension_keys_derived_from_categories():
    assert DIMENSION_KEYS == [c["id"] for c in CATEGORIES]
    assert len(DIMENSION_KEYS) == len(set(DIMENSION_KEYS)) == 8, "应恰好 8 个维度且不重复"


def test_category_map_matches_categories():
    """CATEGORY_MAP 必须与 CATEGORIES 完全对应（名字 + 颜色）"""
    assert set(CATEGORY_MAP) == set(DIMENSION_KEYS)
    for c in CATEGORIES:
        assert CATEGORY_MAP[c["id"]] == (c["name"], c["color"]), (
            f"{c['id']} 的 (名称, 颜色) 与 CATEGORIES 不一致"
        )
