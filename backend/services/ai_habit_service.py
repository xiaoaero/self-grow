"""
Self Grow — AI 习惯服务

AI 图标设计（SVG 生成 + 白名单校验）。
习惯 AI 分析功能已移除，待重新设计。
"""

import logging
import re
from xml.etree import ElementTree

from fastapi import HTTPException

from config import AI_API_KEY
from prompts import HABIT_ICON_SYSTEM_PROMPT
from services.ai_client import call_ai_text

log = logging.getLogger(__name__)

# SVG 图标白名单：只允许纯图形标签，杜绝 script/foreignObject/image 等危险元素
SVG_ALLOWED_TAGS = {"svg", "g", "path", "rect", "circle", "ellipse", "line",
                    "polyline", "polygon"}


def extract_svg(text: str) -> str:
    """从 AI 回复中提取第一个 <svg>...</svg> 块。

    兼容 ```svg / ```XML / ```html 等任意 markdown 语言标注，
    以及前后夹杂说明文字的情况。
    """
    m = re.search(r"<svg[\s\S]*?</svg>", text, re.IGNORECASE)
    return m.group(0) if m else ""


def validate_svg(svg: str) -> bool:
    """校验 SVG 是否为合法的纯图形 XML。

    - 能被 XML 解析
    - 所有标签在白名单内
    - 剥离后仍以 <svg 开头（防止 AI 返回 <g> 等碎片）
    """
    if not svg.strip():
        return False
    try:
        root = ElementTree.fromstring(svg)
    except ElementTree.ParseError:
        return False
    if root.tag.lower() != "svg":
        # 带默认命名空间时 tag 为 {ns}svg，取本地名比较
        local = root.tag.split("}", 1)[1] if "}" in root.tag else root.tag
        if local.lower() != "svg":
            return False
    for el in root.iter():
        tag = el.tag.lower()
        # 命名空间前缀（如 {http://www.w3.org/2000/svg}path）
        if "}" in tag:
            tag = tag.split("}", 1)[1]
        if tag not in SVG_ALLOWED_TAGS:
            return False
        # 拒绝事件属性（onload/onclick...）与外部引用属性（href/xlink:href），防 XSS
        for attr in el.attrib:
            al = attr.lower()
            if al.startswith("on") or al in ("href", "xlink:href"):
                return False
    return True


async def call_ai_for_icon(name: str, intro: str, category: str, user_id: int = None) -> str:
    """根据习惯名称、简介、维度分类，调用 AI 生成 SVG 图标"""
    if not AI_API_KEY:
        raise HTTPException(status_code=500, detail="AI_API_KEY 未配置")

    # 构建用户消息
    user_message = (
        f"为一个习惯设计 SVG 图标。\n"
        f"习惯名称：{name}\n"
        f"习惯简介：{intro or '无'}\n"
        f"维度分类：{category}\n"
        f"请根据以上信息生成一个简洁的 64x64 SVG 图标。"
    )

    try:
        log.info(f"→ AI 图标设计请求: {name} ({category})")
        svg = await call_ai_text(
            system_prompt=HABIT_ICON_SYSTEM_PROMPT,
            user_message=user_message,
            temperature=0.8,
            max_tokens=10000,
            user_id=user_id,
        )
        # 提取 <svg> 块（兼容 markdown 包裹与前后杂文），再做合法性校验
        svg = extract_svg(svg)
        if not validate_svg(svg):
            log.warning(f"✗ AI 图标校验未通过: {len(svg)} 字符")
            raise HTTPException(
                status_code=502,
                detail="AI 生成的图标无效，请重试",
            )

        log.info(f"← AI 图标设计完成: {len(svg)} 字符")
        return svg

    except HTTPException:
        raise
    except Exception as e:
        log.exception("AI 图标设计调用失败")
        raise HTTPException(status_code=500, detail=f"AI 图标设计失败: {str(e)}")