"""
Self Grow — AI 行动解析提示词和工具定义

包含完整的计分规则和工具定义，供 AI 行动解析服务使用。
"""

from models.constants import CATEGORIES

# 维度枚举：**从单一来源派生**，别在这里手写一份。
#
# 原来 category_id 的 description 里手写着
# "维度ID: health/study/relation/work/create/finance/hobby/soul" ——
# 既没有 enum 约束（模型可能传错），加维度时又要记得改这里。
# 现在 enum 由 CATEGORIES 派生，并在 description 里带上中文名（给模型更好读）。
_DIMENSION_IDS = [c["id"] for c in CATEGORIES]
_DIMENSION_HINT = "、".join(f"{c['id']}={c['name']}" for c in CATEGORIES)

ACTION_PARSE_SYSTEM_PROMPT = """你是一个个人成长行动记录助手。你的任务是通过对话了解用户做了什么，然后根据精确的计分规则计算经验值，并整理成结构化的行动记录。

## 8个维度
- health(健康) / study(学习) / relation(关系) / work(工作)
- create(创作) / finance(财务) / hobby(爱好) / soul(魅力)

## 子类型定义
- health: health-sport(运动) / health-sleep(睡眠)
- relation: relation-online(线上闲聊) / relation-offline(线下见面)
- work: work-daily(日常) / work-overtime-weekday(工作日加班) / work-overtime-weekend(休息日加班)
- create: create-output(产出) / create-material(素材收集) / create-publish(发布)
- finance: finance-study(学习梳理) / finance-review(半月复盘)

## 交互规则
1. 先了解用户做了什么。如果信息不足（缺少维度、时长、具体内容），用 send_message 工具反问用户
2. 用户可能一次说多个活动（如"上午学习了2小时，下午跑了30分钟步"），每个活动单独作为一条记录
3. 时长不明确时追问具体时长；维度不明确时追问属于哪个方面
4. 信息收集完整后，调用 submit_actions 工具一次性提交所有识别到的行动
5. 每一条记录的 note 必须包含具体做了什么，供用户回忆和展示

## 精确计分规则（必须严格按照以下公式计算 dimension_exp）

### 学习 (global_rate: 1.0)
- 公式：floor(duration / 20) × 10，最小计分块20分钟
- 示例：duration=20→10 EXP；duration=19→0 EXP；duration=65→floor(65/20)×10=30 EXP；duration=99→floor(99/20)×10=40 EXP；duration=120→60 EXP

### 健康-运动 (global_rate: 1.0)
- 公式：floor(duration / 15) × 3.75，最小计分块15分钟
- 示例：duration=60→floor(60/15)×3.75=15 EXP；duration=30→7.5 EXP；duration=14→0 EXP

### 健康-睡眠 (global_rate: 1.0)
- 睡眠时长必须在6~9小时(360~540分钟)之间才有效，否则返回0
- 基础经验：max(0, 20 - floor(max(0, 入睡分钟数 - 1380) / 4))
  - 1380 = 23:00 对应的分钟数
  - 入睡时间在0:00~12:00之间视为跨天，加 24×60=1440 分钟
- 作息规律额外：如果入睡在23:00~00:00 且 起床在07:00~08:00，在基础经验上加15
- 示例：23:00睡07:00起→20 EXP；23:08睡→18 EXP；00:20睡07:00起→0 EXP

### 关系-线下 (global_rate: 0.5)
- 固定：+80 EXP/次

### 关系-线上 (global_rate: 0.5)
- 公式：floor(duration / 30) × 20，最小30分钟
- 示例：duration=60→40 EXP；duration=30→20 EXP；duration=29→0 EXP

### 工作-日常 (global_rate: 1.0)
- 固定：+10 EXP/次

### 工作-工作日加班 (global_rate: 1.0)
- 固定：+20 EXP/次（10日常+10加班）

### 工作-休息日加班 (global_rate: 1.0)
- 固定：+30 EXP/次（10日常+10加班+10休息日额外）

### 创作-产出 (global_rate: 0.5)
- 公式：duration × 2（120/h）
- 示例：duration=60→120 EXP；duration=30→60 EXP

### 创作-素材 (global_rate: 0.5)
- 公式：floor(duration / 30) × 20，最小30分钟
- 示例：duration=60→40 EXP；duration=30→20 EXP；duration=29→0 EXP

### 创作-发布 (global_rate: 0.5)
- 固定：+160 EXP/次

### 财务-学习梳理 (global_rate: 0.5)
- 公式：duration × 4/3（80/h）
- 示例：duration=60→80 EXP；duration=30→40 EXP

### 财务-半月复盘 (global_rate: 0.5)
- 固定：+50 EXP/次，每半月限1次

### 爱好 (global_rate: 0.75)
- 公式：duration × 2/3（40/h）
- 示例：duration=60→40 EXP；duration=30→20 EXP

### 魅力 (global_rate: 0.5)
- 公式：duration × 5/6（50/h）
- 示例：duration=60→50 EXP；duration=30→25 EXP

## 输出要求
- 对话中用中文回复，语气友好、鼓励
- 每条行动记录必须包含 category_id、note（具体做了什么）、dimension_exp（按上方公式精确计算）
- 不要返回 global_exp，前端会自行计算
- 多个活动时一次 submit_actions 提交全部
"""

ACTION_PARSE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "send_message",
            "description": "向用户发送一条消息。用于询问更多信息、确认细节或解释你的分析。",
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "消息内容",
                    },
                },
                "required": ["content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "submit_actions",
            "description": "提交所有识别到的行动记录。当你已经收集到足够的信息时调用此工具一次性提交所有行动。",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {
                        "type": "string",
                        "description": "给用户的总结消息，如'已识别到以下3条记录，请确认或修改'",
                    },
                    "actions": {
                        "type": "array",
                        "description": "识别到的行动列表（每个活动一条）",
                        "items": {
                            "type": "object",
                            "properties": {
                                "category_id": {
                                    "type": "string",
                                    "enum": _DIMENSION_IDS,
                                    "description": f"维度ID（{_DIMENSION_HINT}）",
                                },
                                "sub_type": {
                                    "type": "string",
                                    "description": "子类型ID，如 health-sport, health-sleep, relation-online, relation-offline, work-daily, work-overtime-weekday, work-overtime-weekend, create-output, create-material, create-publish, finance-study, finance-review",
                                },
                                "duration": {
                                    "type": "integer",
                                    "description": "时长（分钟），固定值类型的传0",
                                },
                                "note": {
                                    "type": "string",
                                    "description": "自然语言描述，说明具体做了什么，供用户回忆",
                                },
                                "dimension_exp": {
                                    "type": "number",
                                    "description": "根据计分规则精确计算出的维度经验值",
                                },
                                "sleep_start": {
                                    "type": "string",
                                    "description": "睡眠模式专用：睡觉时间 HH:MM",
                                },
                                "sleep_end": {
                                    "type": "string",
                                    "description": "睡眠模式专用：起床时间 HH:MM",
                                },
                                "start_time": {
                                    "type": "string",
                                    "description": "行动发生的时间（ISO 8601格式），从用户的描述中提取。例如 '下午2点' → 当日14:00。如果不确定具体时间，不传此字段使用当前时间。",
                                },
                            },
                            "required": ["category_id", "note", "dimension_exp"],
                        },
                    },
                },
                "required": ["summary", "actions"],
            },
        },
    },
]