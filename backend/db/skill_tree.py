"""
Self Grow — 技能树 CRUD

技能树数据存储：1 张表替代原来的 5 个 localStorage key。
JSON 字段处理模式参考 db/rewards.py。
"""

from db.connection import get_conn
import json


# ================================================================
# 技能树 CRUD
# ================================================================

def get_skill_trees(user_id: int) -> list:
    """获取用户所有技能树（索引列表）"""
    conn = get_conn()
    rows = conn.execute(
        """SELECT id, tree_id, name, description, image, remark,
                  node_count, completed_count, created_at, updated_at,
                  published_at, update_history
           FROM skill_trees WHERE user_id = ? ORDER BY updated_at DESC""",
        (user_id,),
    ).fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        d["update_history"] = json.loads(d.get("update_history", "[]"))
        result.append(d)
    return result


def get_skill_tree_by_tree_id(tree_id: str, user_id: int = None):
    """根据 tree_id 获取技能树草稿数据"""
    conn = get_conn()
    if user_id:
        row = conn.execute(
            "SELECT * FROM skill_trees WHERE tree_id = ? AND user_id = ?",
            (tree_id, user_id),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT * FROM skill_trees WHERE tree_id = ?",
            (tree_id,),
        ).fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    d["data"] = json.loads(d.get("data", "{}"))
    d["published_data"] = json.loads(d.get("published_data", "null"))
    d["update_history"] = json.loads(d.get("update_history", "[]"))
    return d


def create_skill_tree(user_id: int, tree_id: str, name: str, description: str = "") -> int:
    """创建新技能树，返回数据库 id"""
    data = json.dumps({"name": name, "description": description, "nodes": [], "connections": []}, ensure_ascii=False)
    conn = get_conn()
    cursor = conn.execute(
        """INSERT INTO skill_trees (user_id, tree_id, name, description, data, node_count)
           VALUES (?, ?, ?, ?, ?, 0)""",
        (user_id, tree_id, name, description, data),
    )
    new_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return new_id


def save_skill_tree_draft(tree_id: str, user_id: int, name: str, description: str,
                          data: dict, node_count: int, completed_count: int,
                          image: str = "", remark: str = "") -> bool:
    """保存技能树草稿"""
    data_json = json.dumps(data, ensure_ascii=False)
    conn = get_conn()
    conn.execute(
        """UPDATE skill_trees SET name = ?, description = ?, data = ?,
           node_count = ?, completed_count = ?, image = ?, remark = ?,
           updated_at = datetime('now')
           WHERE tree_id = ? AND user_id = ?""",
        (name, description, data_json, node_count, completed_count,
         image, remark, tree_id, user_id),
    )
    conn.commit()
    conn.close()
    return True


def publish_skill_tree(tree_id: str, user_id: int, published_data: dict,
                       node_count: int, completed_count: int) -> bool:
    """发布/更新技能树"""
    published_json = json.dumps(published_data, ensure_ascii=False)
    conn = get_conn()

    # 获取现有的 update_history
    row = conn.execute(
        "SELECT update_history, published_at FROM skill_trees WHERE tree_id = ? AND user_id = ?",
        (tree_id, user_id),
    ).fetchone()

    history = json.loads(row["update_history"]) if row and row["update_history"] else []
    is_new_publish = not row or not row["published_at"]
    history.append({
        "type": "publish" if is_new_publish else "update",
        "timestamp": published_data.get("publishedAt", ""),
        "nodeCount": node_count,
    })

    conn.execute(
        """UPDATE skill_trees SET published_data = ?, published_at = ?,
           node_count = ?, completed_count = ?, update_history = ?,
           updated_at = datetime('now')
           WHERE tree_id = ? AND user_id = ?""",
        (published_json, published_data.get("publishedAt"),
         node_count, completed_count, json.dumps(history, ensure_ascii=False),
         tree_id, user_id),
    )
    conn.commit()
    conn.close()
    return True


def get_published_skill_tree(tree_id: str):
    """获取已发布的技能树（含学习进度）"""
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM skill_trees WHERE tree_id = ? AND published_at IS NOT NULL",
        (tree_id,),
    ).fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    d["published_data"] = json.loads(d.get("published_data", "null"))
    d["update_history"] = json.loads(d.get("update_history", "[]"))
    return d


def save_learner_progress(tree_id: str, user_id: int, learner: dict) -> bool:
    """保存学习进度到 published_data 中的 learner 字段"""
    conn = get_conn()
    row = conn.execute(
        "SELECT published_data FROM skill_trees WHERE tree_id = ?",
        (tree_id,),
    ).fetchone()
    if not row:
        conn.close()
        return False

    published = json.loads(row["published_data"]) if row["published_data"] else {}
    published["learner"] = learner
    conn.execute(
        "UPDATE skill_trees SET published_data = ? WHERE tree_id = ?",
        (json.dumps(published, ensure_ascii=False), tree_id),
    )
    conn.commit()
    conn.close()
    return True


def delete_skill_tree(tree_id: str, user_id: int) -> bool:
    """删除技能树，返回是否实际删除了记录"""
    conn = get_conn()
    cursor = conn.execute(
        "DELETE FROM skill_trees WHERE tree_id = ? AND user_id = ?",
        (tree_id, user_id),
    )
    deleted = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return deleted


# ================================================================
# 用户技能列表
# ================================================================

def get_user_skill_ids(user_id: int) -> list:
    """获取用户已添加的技能 tree_id 列表"""
    conn = get_conn()
    row = conn.execute(
        "SELECT skill_ids FROM user_skills WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    conn.close()
    if not row:
        return []
    return json.loads(row["skill_ids"])


def save_user_skill_ids(user_id: int, skill_ids: list) -> bool:
    """保存用户已添加的技能 tree_id 列表"""
    conn = get_conn()
    conn.execute(
        """INSERT INTO user_skills (user_id, skill_ids) VALUES (?, ?)
           ON CONFLICT(user_id) DO UPDATE SET skill_ids = ?""",
        (user_id, json.dumps(skill_ids, ensure_ascii=False),
         json.dumps(skill_ids, ensure_ascii=False)),
    )
    conn.commit()
    conn.close()
    return True