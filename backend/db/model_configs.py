"""
Self Grow — 模型配置 CRUD

管理用户可配置的 AI 模型（LLM / ASR），支持多模型 + 切换启用。
"""

from db.connection import get_conn


def get_configs(user_id: int, type: str = None) -> list:
    """获取用户的模型配置列表（可按 type 过滤：llm/asr）"""
    conn = get_conn()
    if type:
        rows = conn.execute(
            "SELECT * FROM model_configs WHERE user_id = ? AND type = ? ORDER BY id ASC",
            (user_id, type),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM model_configs WHERE user_id = ? ORDER BY type, id ASC",
            (user_id,),
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_config(config_id: int) -> dict:
    """获取单个模型配置"""
    conn = get_conn()
    row = conn.execute("SELECT * FROM model_configs WHERE id = ?", (config_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def create_config(user_id: int, type: str, name: str, model: str,
                  base_url: str = "", api_key: str = "") -> int:
    """创建模型配置，返回 id"""
    conn = get_conn()
    cursor = conn.execute(
        """INSERT INTO model_configs (user_id, type, name, model, base_url, api_key, is_active)
           VALUES (?, ?, ?, ?, ?, ?, 0)""",
        (user_id, type, name, model, base_url, api_key),
    )
    new_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return new_id


def update_config(config_id: int, **kwargs) -> bool:
    """更新模型配置字段"""
    allowed = ["type", "name", "model", "base_url", "api_key", "is_active"]
    fields = []
    values = []
    for k, v in kwargs.items():
        if k in allowed and v is not None:
            fields.append(f"{k} = ?")
            values.append(v)
    if not fields:
        return False
    values.append(config_id)
    conn = get_conn()
    conn.execute(
        f"UPDATE model_configs SET {', '.join(fields)}, updated_at = datetime('now','localtime') WHERE id = ?",
        values,
    )
    conn.commit()
    conn.close()
    return True


def delete_config(config_id: int) -> bool:
    """删除模型配置"""
    conn = get_conn()
    conn.execute("DELETE FROM model_configs WHERE id = ?", (config_id,))
    conn.commit()
    conn.close()
    return True


def set_active(user_id: int, type: str, config_id: int) -> bool:
    """切换启用：把该 type 下其它配置置 0，目标配置置 1（互斥）"""
    conn = get_conn()
    conn.execute(
        "UPDATE model_configs SET is_active = 0 WHERE user_id = ? AND type = ?",
        (user_id, type),
    )
    conn.execute(
        "UPDATE model_configs SET is_active = 1 WHERE id = ? AND user_id = ?",
        (config_id, user_id),
    )
    conn.commit()
    conn.close()
    return True


def get_active_config(user_id: int, type: str) -> dict:
    """获取某类型当前启用的配置（无则返回 None）"""
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM model_configs WHERE user_id = ? AND type = ? AND is_active = 1 LIMIT 1",
        (user_id, type),
    ).fetchone()
    conn.close()
    return dict(row) if row else None
