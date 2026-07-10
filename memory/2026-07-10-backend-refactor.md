---
name: backend-module-refactor-2026-07-10
description: 后端代码模块化重构完成，从2个单体文件拆分为36个模块文件
metadata:
  type: project
---

# 后端模块化重构（2026-07-10）

将原有的两个单体文件（`server.py` ~1915行 + `database.py` ~1900行）拆分为模块化架构。

## 拆分结果

- **models/** — 等级公式唯一来源（`level.py`）、常量定义（`constants.py`）
- **schemas/** — Pydantic 请求/响应模型（`api.py`）
- **db/** — 数据访问层（12个子模块，按功能域拆分）
- **services/** — 业务逻辑层（`exp_service.py` + `ai_service.py`）
- **routers/** — API 路由层（10个子模块 + 依赖注入）
- **main.py** — 入口点，注册路由 + 生命周期 + 定时任务
- **database.py** — 保留为向后兼容的 re-export 层

## 修复的 BUG

1. `create_action` 中维度经验双倍累加（原 server.py L1014-1021 + L1035-1042）
2. `claim_task` 中硬编码 `sqlite3.connect('data.db')` 绕过数据库模块
3. 等级公式在三处重复 → 统一到 `models/level.py`

## 消除的重复模式

- "用户是否存在"检查 ~31次 → 使用 FastAPI `Depends(get_current_user)`
- "加经验→更新维度→重算等级→更新今日统计" 5次 → 封装到 `services/exp_service.award_exp_and_recalc()`

## 验证结果

- 启动正常，APScheduler 定时任务正常
- 全部 38 个 API 路径通过 OpenAPI 注册
- 19 个端点集成测试全部通过
- 旧 `server.py` 已备份为 `server.py.bak`，不再依赖

**Why:** 单体文件（1900+行）难以维护和扩展，模块化后每个文件职责清晰，修复了已知 BUG，消除了大量重复代码模式。

**How to apply:** 启动后端时使用 `pixi run python main.py`（不再使用 `server.py`）。新添加功能时，按域选择对应模块添加。