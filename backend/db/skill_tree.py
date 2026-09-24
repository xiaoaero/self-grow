"""
Self Grow — 技能树 CRUD

技能树数据存储：1 张表替代原来的 5 个 localStorage key。

⚠️ 2026-09-23 修了一套**静默失败**（用户表现为「AI 一直说技能树不存在」）：
   ① `skill_trees.data` 是 `varchar(255)`（SQLite 无类型，迁移后固化了），
      真实树 JSON 几 KB → `1406 Data too long`；而 SQLite 时代完全看不出来
   ② `save_skill_tree_draft` 原来是无条件 `return True`（UPDATE 改到 0 行也算成功）
   ③ 原来只 UPDATE 不 INSERT → 树只活在浏览器里时永远写不进来
   ④ 写操作异常时 `close()` 没执行 → 事务与行锁留在连接池里，
      之后对该行任何 DELETE 都 `Lock wait timeout`（`SELECT` 照常成功，因为快照读）
   ⇒ 所以下面的写函数统一：**先判定归属 → 再写 → except 里 rollback → finally 里 close**，
     并且返回「到底写没写进去」，让调用方能看见失败。
"""

import json
import logging

from db.connection import get_conn
from db.jsoncols import jloads

log = logging.getLogger(__name__)


# ================================================================
# 技能树 CRUD
# ================================================================

def get_skill_trees(user_id: int) -> list:
    """获取用户所有技能树（索引列表）"""
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT id, tree_id, name, description, image, remark,
                      node_count, completed_count, created_at, updated_at,
                      published_at, update_history
               FROM skill_trees WHERE user_id = %s ORDER BY updated_at DESC""",
            (user_id,),
        ).fetchall()
    finally:
        conn.close()
    result = []
    for r in rows:
        d = dict(r)
        d["update_history"] = jloads(d.get("update_history"), [])
        # ⚠️ 对外必须用 **tree_id 字符串** 当 `id`，不能把自增主键漏出去。
        #
        # 踩过（2026-09-24）：两个前端（技能树编辑器、技能库页）到处都用 `t.id`
        # 当树的标识 —— 侧边栏选中项、localStorage key、以及 API 路径
        # `/api/skill-trees/{id}/...`。而 API 要的是 `tree_id` 字符串。
        # 原来直接把行里的自增 id 给出去，于是「服务器上第一次有数据」之后：
        #   · 编辑器 currentId 变成 `3` → `POST /api/skill-trees/3/chat` → **404
        #     「技能树不存在」**（症状和"树没存上"一模一样，但这次树明明在库里）
        #   · 技能库页 `mySkillIds.indexOf(t.id)`（skill_ids 里存的是 tree_id 字符串）
        #     永远匹配不上 → 「我的技能」空着
        # 自增 id 改为 `db_id` 保留，前端不用它，但别丢信息。
        d["db_id"] = d.get("id")
        d["id"] = d.get("tree_id")
        result.append(d)
    return result


def get_skill_tree_by_tree_id(tree_id: str, user_id: int = None):
    """根据 tree_id 获取技能树草稿数据"""
    conn = get_conn()
    try:
        if user_id:
            row = conn.execute(
                """SELECT * FROM skill_trees WHERE tree_id = %s AND user_id = %s""",
                (tree_id, user_id),
            ).fetchone()
        else:
            row = conn.execute(
                """SELECT * FROM skill_trees WHERE tree_id = %s""",
                (tree_id,),
            ).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    d = dict(row)
    d["data"] = jloads(d.get("data"), {})
    d["published_data"] = jloads(d.get("published_data"), None)
    d["update_history"] = jloads(d.get("update_history"), [])
    return d


def create_skill_tree(user_id: int, tree_id: str, name: str, description: str = "") -> int:
    """创建新技能树，返回数据库 id

    **幂等 + 原子**：同一个 tree_id 重复创建不报错，返回已有记录的 id
    （用 `ON DUPLICATE KEY UPDATE id = LAST_INSERT_ID(id)`，见下方注释）。
    返回 0 表示「这个 tree_id 已经被**别人**占了」—— 路由层据此报 409，
    不能假装成功。
    """
    data = json.dumps({"name": name, "description": description, "nodes": [], "connections": []},
                      ensure_ascii=False)
    conn = get_conn()
    try:
        # ⚠️ 不能「先 SELECT 判断、再 INSERT」：并发时两个请求都查到「不存在」，
        #    后一个 INSERT 撞唯一键直接报 **1062 Duplicate entry**（实测踩到：
        #    编辑器的保存与「本地树补传」几乎同时发出）。
        #    改成一条原子语句：冲突时 `id = LAST_INSERT_ID(id)` 把 lastrowid
        #    指到**已有那一行**，既幂等又能拿到 id，且不动已有数据。
        cursor = conn.execute(
            """INSERT INTO skill_trees (user_id, tree_id, name, description, data, node_count)
               VALUES (%s, %s, %s, %s, %s, 0)
               ON DUPLICATE KEY UPDATE id = LAST_INSERT_ID(id)""",
            (user_id, tree_id, name, description, data),
        )
        new_id = cursor.lastrowid

        # 归属单独判定（rowcount 区分不了"已存在"与"刚插入"，别用它）
        owner = conn.execute(
            """SELECT user_id FROM skill_trees WHERE tree_id = %s""", (tree_id,)
        ).fetchone()
        conn.commit()
        # 自己的 → 幂等返回 id；别人的 → 0（路由层据此报 409）
        return new_id if (owner and owner["user_id"] == user_id) else 0
    except Exception:
        conn.rollback()     # 不留未结束的事务（否则行锁会挂住，见模块 docstring ④）
        raise
    finally:
        conn.close()


def save_skill_tree_draft(tree_id: str, user_id: int, name: str, description: str,
                          data: dict, node_count: int, completed_count: int,
                          image: str = "", remark: str = "") -> bool:
    """保存技能树草稿，返回**是否真的写进去了**

    ⚠️ 调用方必须看返回值 —— 这个函数以前无条件 return True，
    于是「保存失败」在界面上和「保存成功」长得一模一样。

    实现是**一条原子 upsert**（`INSERT ... ON DUPLICATE KEY UPDATE`）：
      · tree_id 不存在       → INSERT（顺手把「只存在于浏览器」的树补到服务器）
      · 属于当前用户         → 更新各字段
      · 属于别人             → 一个字段都不动（守卫写在每个 SET 里），返回 False

    ⚠️ 为什么不用「先 SELECT 判断、再 UPDATE / INSERT」：那是 check-then-act，
    并发时两个请求都会查到「不存在」，然后都去 INSERT → 后一个撞唯一键报
    **1062 Duplicate entry**（2026-09-24 实测踩到：编辑器保存 与 本地树补传 同时发出）。

    ⚠️ 也**不用 `rowcount` 判断写没写**：MySQL 返回的是「实际改变的行数」，
    内容没变化时是 0，会被误判成「没写」；归属只看那一行的 `user_id`。
    （唯一的例外：`rowcount == 1` 可以确定"本次是 INSERT"，用来打一条补建日志。）
    """
    data_json = json.dumps(data, ensure_ascii=False)
    conn = get_conn()
    try:
        # ⚠️ 一条**原子 upsert** 顶掉原来的「先 SELECT 再分支」：
        #    并发时两个请求都查到「不存在」→ 都去 INSERT → 后一个撞唯一键报
        #    **1062 Duplicate entry**（实测踩到：编辑器保存 与 本地树补传 同时发出）。
        #
        #    归属守卫写在每个 SET 里：`IF(user_id = VALUES(user_id), 新值, 旧值)` ——
        #    即"只有所有者才更新"，别人的行原样不动（不能用 WHERE，ODKU 不支持）。
        #    不存在的 tree_id 会走到 INSERT 分支 → 顺手补建成功。
        cursor = conn.execute(
            """INSERT INTO skill_trees (user_id, tree_id, name, description, data,
               node_count, completed_count, image, remark)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
               ON DUPLICATE KEY UPDATE
                 name             = IF(user_id = VALUES(user_id), VALUES(name), name),
                 description      = IF(user_id = VALUES(user_id), VALUES(description), description),
                 data             = IF(user_id = VALUES(user_id), VALUES(data), data),
                 node_count       = IF(user_id = VALUES(user_id), VALUES(node_count), node_count),
                 completed_count  = IF(user_id = VALUES(user_id), VALUES(completed_count), completed_count),
                 image            = IF(user_id = VALUES(user_id), VALUES(image), image),
                 remark           = IF(user_id = VALUES(user_id), VALUES(remark), remark),
                 updated_at       = IF(user_id = VALUES(user_id), now(), updated_at)""",
            (user_id, tree_id, name, description, data_json,
             node_count, completed_count, image, remark),
        )

        owner = conn.execute(
            """SELECT user_id FROM skill_trees WHERE tree_id = %s""", (tree_id,)
        ).fetchone()
        conn.commit()

        # 写没写进去 = 这行是不是我的（**不用 rowcount**：它区分不了"内容没变化"）
        if not owner or owner["user_id"] != user_id:
            log.warning("技能树归属不符，拒绝保存：tree=%s 属于 user=%s，请求来自 user=%s",
                        tree_id, owner["user_id"] if owner else None, user_id)
            return False
        if cursor.rowcount == 1:      # 1 = 本次是 INSERT（之前服务器上没有这棵树）
            log.info("技能树在服务器上不存在，自动补建：tree=%s user=%s", tree_id, user_id)
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def publish_skill_tree(tree_id: str, user_id: int, published_data: dict,
                       node_count: int, completed_count: int) -> bool:
    """发布/更新技能树，返回是否写成功（树不存在或不属于当前用户 → False）"""
    published_json = json.dumps(published_data, ensure_ascii=False)
    conn = get_conn()
    try:
        # 获取现有的 update_history
        row = conn.execute(
            """SELECT update_history, published_at FROM skill_trees WHERE tree_id = %s AND user_id = %s""",
            (tree_id, user_id),
        ).fetchone()
        if not row:
            log.warning("发布失败：服务器上没有这棵树 tree=%s user=%s", tree_id, user_id)
            conn.rollback()
            return False

        history = jloads(row["update_history"], [])
        history.append({
            "type": "publish" if not row["published_at"] else "update",
            "timestamp": published_data.get("publishedAt", ""),
            "nodeCount": node_count,
        })

        conn.execute(
            """UPDATE skill_trees SET published_data = %s, published_at = %s,
               node_count = %s, completed_count = %s, update_history = %s,
               updated_at = now()
               WHERE tree_id = %s AND user_id = %s""",
            (published_json, published_data.get("publishedAt"),
             node_count, completed_count, json.dumps(history, ensure_ascii=False),
             tree_id, user_id),
        )
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_published_skill_tree(tree_id: str):
    """获取已发布的技能树（含学习进度）"""
    conn = get_conn()
    try:
        row = conn.execute(
            """SELECT * FROM skill_trees WHERE tree_id = %s AND published_at IS NOT NULL""",
            (tree_id,),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    d = dict(row)
    # ⚠️ 这个函数的调用方是**不需要登录**的 `/published` 端点，
    #    而它是 `SELECT *` —— 会把未发布的草稿 `data` 一起带出去。
    #    学习页只用 `published_data` / `learner`，所以草稿直接摘掉。
    d.pop("data", None)
    d["published_data"] = jloads(d.get("published_data"), None)
    d["update_history"] = jloads(d.get("update_history"), [])
    return d


def save_learner_progress(tree_id: str, user_id: int, learner: dict) -> bool:
    """保存学习进度到 published_data 中的 learner 字段"""
    conn = get_conn()
    try:
        row = conn.execute(
            """SELECT published_data FROM skill_trees WHERE tree_id = %s""",
            (tree_id,),
        ).fetchone()
        if not row:
            return False

        published = jloads(row["published_data"], {})
        published["learner"] = learner
        conn.execute(
            """UPDATE skill_trees SET published_data = %s WHERE tree_id = %s""",
            (json.dumps(published, ensure_ascii=False), tree_id),
        )
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def delete_skill_tree(tree_id: str, user_id: int) -> bool:
    """删除技能树，返回是否实际删除了记录"""
    conn = get_conn()
    try:
        cursor = conn.execute(
            """DELETE FROM skill_trees WHERE tree_id = %s AND user_id = %s""",
            (tree_id, user_id),
        )
        deleted = cursor.rowcount > 0
        conn.commit()
        return deleted
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ================================================================
# 用户技能列表
# ================================================================

def get_user_skill_ids(user_id: int) -> list:
    """获取用户已添加的技能 tree_id 列表"""
    conn = get_conn()
    try:
        row = conn.execute(
            """SELECT skill_ids FROM user_skills WHERE user_id = %s""",
            (user_id,),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return []
    return jloads(row["skill_ids"], [])


def save_user_skill_ids(user_id: int, skill_ids: list) -> bool:
    """保存用户已添加的技能 tree_id 列表"""
    payload = json.dumps(skill_ids, ensure_ascii=False)
    conn = get_conn()
    try:
        conn.execute(
            """INSERT INTO user_skills (user_id, skill_ids) VALUES (%s, %s)
               ON DUPLICATE KEY UPDATE skill_ids = %s""",
            (user_id, payload, payload),
        )
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
