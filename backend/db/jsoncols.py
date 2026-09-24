"""
Self Grow — JSON 列的读取助手

⚠️ 为什么需要它（2026-09-23 真踩过的线上 500）

    json.loads(row.get("published_data", "null"))

看着有兜底，其实**没有**。`dict.get()` 的默认值只在「**键不存在**」时才生效，
而 MySQL 驱动返回的行是普通 dict —— 列可为 NULL 时**键是存在的、值是 None**：

    >>> json.loads(None)
    TypeError: the JSON object must be str, bytes or bytearray, not NoneType

后果：任何「该列为 NULL」的历史数据，一读就是 500。
（SQLite 时代用的是 `sqlite3.Row`，同样有这个语义差异，只是那时候
 JSON 列基本都有值，所以一直没暴露。）

    row.get(k, default)  ≠  SQL 的 COALESCE(k, default)

正确写法就是本模块的 `jloads()`：

    d["published_data"] = jloads(d.get("published_data"), None)
"""

import json
import logging

log = logging.getLogger(__name__)


def jloads(value, default):
    """把数据库里的 JSON 列解析成对象；NULL / 空串 / 坏 JSON 都返回 default

    Args:
        value: 列值。可能是 None（NULL）、''、bytes、str，或已经是 dict/list
        default: 兜底值。⚠️ 传字面量（`[]` / `{}` / `None`），
                 因为每次调用都会返回**同一个对象**，传可变共享对象会被调用方改坏

    Returns:
        解析后的对象，或 default
    """
    if value is None or value == "":
        return default
    if isinstance(value, (dict, list)):      # 上游已经解析过（比如 dict(row) 后再处理）
        return value
    if isinstance(value, (bytes, bytearray)):
        try:
            value = value.decode("utf-8")
        except UnicodeDecodeError:
            log.warning("JSON 列不是合法 UTF-8，按默认值处理")
            return default
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        # 坏 JSON 说明数据被写坏过（比如列宽截断）。这里不抛 ——
        # 一个坏字段不该让整个列表接口 500；但要留下日志，别静默。
        log.warning("JSON 列解析失败，按默认值处理：%r", str(value)[:120])
        return default
