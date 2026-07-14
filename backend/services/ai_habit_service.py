"""
Self Grow — AI 习惯分析服务

使用 LangChain + OpenAI 兼容 API 对用户习惯数据进行分析并给出建议。
提示词从 prompts/ 模块导入，AI 调用通过 ai_client 统一处理。
"""

import json
import logging
from datetime import datetime, date

from fastapi import HTTPException

from config import AI_API_KEY
from prompts import HABIT_ANALYSIS_SYSTEM_PROMPT, HABIT_ICON_SYSTEM_PROMPT
from services.ai_client import call_ai_text
from db.habits import get_habits, get_all_checkins_in_range

log = logging.getLogger(__name__)


async def call_ai_for_habits(user_id: int, date_from: str, date_to: str) -> str:
    """调用 AI 分析习惯数据，返回分析报告文本"""
    if not AI_API_KEY:
        raise HTTPException(status_code=500, detail="AI_API_KEY 未配置")

    # 1. 查询用户习惯
    habits = get_habits(user_id)
    active_habits = [h for h in habits if h["active"]]

    if not active_habits:
        return "📭 还没有习惯数据可供分析，请先创建一些习惯吧！"

    # 2. 查询打卡记录
    checkins = get_all_checkins_in_range(user_id, date_from, date_to)

    # 3. 构建习惯数据摘要
    habit_map = {h["id"]: h for h in active_habits}

    # 按日期和习惯组织打卡数据
    checkin_by_date = {}
    for c in checkins:
        d = c["date"]
        if d not in checkin_by_date:
            checkin_by_date[d] = {}
        checkin_by_date[d][c["habit_id"]] = c["status"]

    # 统计每个习惯的完成情况
    habit_stats = []
    for h in active_habits:
        done_count = 0
        skip_count = 0
        total_days = 0

        # 遍历日期范围内的每一天
        d_from = date.fromisoformat(date_from)
        d_to = date.fromisoformat(date_to)
        current = d_from
        while current <= d_to:
            total_days += 1
            d_str = current.isoformat()
            status = checkin_by_date.get(d_str, {}).get(h["id"])
            if status == "done":
                done_count += 1
            elif status == "skipped":
                skip_count += 1
            current = date.fromordinal(current.toordinal() + 1)

        habit_stats.append({
            "name": h["name"],
            "icon": h["icon"] or "✅",
            "category": h["category"],
            "weekly_target": h["weekly_target"],
            "done_count": done_count,
            "skip_count": skip_count,
            "total_days": total_days,
            "completion_rate": round(done_count / total_days * 100) if total_days > 0 else 0,
        })

    # 维度汇总
    dim_map = {
        "health": "健康", "study": "学习", "relation": "关系",
        "work": "工作", "create": "创作", "finance": "财务",
        "hobby": "爱好", "soul": "魅力",
    }
    dim_stats = {}
    for s in habit_stats:
        cat = s["category"]
        if cat not in dim_stats:
            dim_stats[cat] = {"done": 0, "total": 0, "habits": []}
        dim_stats[cat]["done"] += s["done_count"]
        dim_stats[cat]["total"] += s["total_days"]
        dim_stats[cat]["habits"].append(s["name"])

    dim_summary = []
    for cat_id, ds in dim_stats.items():
        dim_summary.append({
            "dimension": dim_map.get(cat_id, cat_id),
            "completion_rate": round(ds["done"] / ds["total"] * 100) if ds["total"] > 0 else 0,
            "habit_count": len(ds["habits"]),
            "habit_names": ds["habits"],
        })
    dim_summary.sort(key=lambda x: -x["completion_rate"])

    # 4. 构建发送给 AI 的消息
    data_summary = {
        "分析时间范围": f"{date_from} ~ {date_to}",
        "总天数": (date.fromisoformat(date_to) - date.fromisoformat(date_from)).days + 1,
        "习惯总数": len(active_habits),
        "各习惯完成情况": habit_stats,
        "各维度完成率": dim_summary,
    }

    data_json = json.dumps(data_summary, ensure_ascii=False, indent=2)

    # 5. 通过统一客户端调用 AI
    try:
        user_message = f"请分析以下习惯数据：\n\n```json\n{data_json}\n```"
        log.info(f"→ AI 习惯分析请求: {date_from} ~ {date_to}, {len(active_habits)} 个习惯")
        content = await call_ai_text(
            system_prompt=HABIT_ANALYSIS_SYSTEM_PROMPT,
            user_message=user_message,
            max_tokens=2048,
        )
        log.info(f"← AI 习惯分析完成: {len(content)} 字符")
        return content

    except Exception as e:
        log.exception("AI 习惯分析调用失败")
        raise HTTPException(status_code=500, detail=f"AI 分析失败: {str(e)}")


async def call_ai_for_icon(name: str, intro: str, category: str) -> str:
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
            max_tokens=1024,
        )
        # 清理可能存在的 markdown 包裹
        svg = svg.strip()
        if svg.startswith("```svg"):
            svg = svg[6:]
        elif svg.startswith("```"):
            svg = svg[3:]
        if svg.endswith("```"):
            svg = svg[:-3]

        svg = svg.strip()
        log.info(f"← AI 图标设计完成: {len(svg)} 字符")
        return svg

    except Exception as e:
        log.exception("AI 图标设计调用失败")
        raise HTTPException(status_code=500, detail=f"AI 图标设计失败: {str(e)}")