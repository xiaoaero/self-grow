"""
Self Grow — 工具参数容错

⚠️ 为什么需要（2026-09-24 实测事故）

模型经常把**数组/对象参数序列化成 JSON 字符串**再传过来：

    create_nodes_batch(connections='[{"from_name": "后端", "to_name": "项目实战"}]')

而工具签名声明的是 `connections: list[dict] | None`，LangChain 会做参数校验，
于是每次都抛：

    1 validation error for create_nodes_batch
    connections
      Input should be a valid list [type=list_type, input_value='[...]', input_type=str]

后果特别难看：工具**永远执行不了**，模型看到报错就换个写法重试，
一轮对话白烧 90 秒、10 个节点只建出 1 个（实测 `create_node` 的 `tags` 也一样）。

这不是"模型的错"——多模型热切换下不同厂商的行为本来就不一样
（有的会自动 parse、有的原样传字符串）。**边界要容错**：能确定语义的转换
在这里统一做掉，而不是让每个工具各自去猜。

同时在提示词里明确"数组要传数组"（见 `skill_tree_ai/prompts.py`）——
容错是兜底，不是让模型随便传。
"""

import json
import logging
import types
from typing import Union, get_args, get_origin

log = logging.getLogger(__name__)

_UNION_TYPES = (Union, getattr(types, "UnionType", Union))


def _is_container(annotation) -> bool:
    """注解是否表示 list / dict（含 Optional[...] / X | None 包裹）"""
    if annotation in (list, dict):
        return True
    origin = get_origin(annotation)
    if origin is None:
        return False
    if origin in (list, dict):
        return True
    if origin in _UNION_TYPES:                      # Optional[list[dict]]
        return any(_is_container(a) for a in get_args(annotation))
    return False


def coerce_json_args(tool_fn, args: dict) -> dict:
    """把"被序列化成字符串"的容器参数解析回 list / dict

    只处理**确定是容器类型**的字段（`list` / `dict` / `Optional[list]` …），
    且字符串必须看起来像 JSON（以 `[` 或 `{` 开头）才尝试解析 ——
    解析失败就原样放行，让框架照常报它的参数错误（不要吞掉真正的类型问题）。

    Args:
        tool_fn: LangChain 工具对象（需要带 `args_schema`）
        args: 模型给的原始参数

    Returns:
        新的参数 dict（不改原对象）
    """
    if not isinstance(args, dict) or not args:
        return args

    try:
        fields = tool_fn.args_schema.model_fields      # pydantic v2
    except Exception:                                  # noqa: BLE001
        return args                                    # 拿不到 schema 就不动（如 dict schema）

    fixed = dict(args)
    for key, value in args.items():
        if not isinstance(value, str):
            continue
        field = fields.get(key)
        if field is None or not _is_container(field.annotation):
            continue
        text = value.strip()
        if not text.startswith(("[", "{")):
            continue
        try:
            parsed = json.loads(text)
        except (ValueError, TypeError):
            log.warning("参数 %s 看起来像 JSON 但解析失败，原样交给框架校验：%r", key, text[:80])
            continue
        if isinstance(parsed, (list, dict)):
            fixed[key] = parsed
            log.info("工具参数 %s 是 JSON 字符串，已自动解析成 %s", key, type(parsed).__name__)
    return fixed
