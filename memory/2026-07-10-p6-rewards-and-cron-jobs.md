---
name: 2026-07-10-p6-rewards-and-cron-jobs
description: P6奖励商城后端迁移完成 + 前端mock清理 + 后端定时任务基础设施搭建 + 数据修复与用户隔离
metadata:
  type: project
---

## 2026-07-10 工作记录

### P6 奖励商城后端迁移（完成）
- **数据库**：新建 `rewards` 表，CRUD 函数（`get_rewards`/`create_reward`/`update_reward`/`delete_reward`/`claim_reward`/`manual_confirm_condition`）
- **条件评估引擎**：10 种结构化条件类型，后端 `evaluate_condition()` + `evaluate_all_rewards()`
- **API 端点**：8 个（GET/POST/PUT/DELETE rewards + claim + manual-confirm + reevaluate + image upload）
- **前端**：`rewards.js` 重写为结构化条件输入表单，删除旧文本正则匹配逻辑
- **默认数据**：6 条默认奖励，初始化时自动插入 test/admin 用户
- **修复**：`init_default_dimensions()` 连接锁 bug

### 前端 mock 清理
- `data.js`：attributes/attributeDetails/advancedAttributes/actionCenter/historyRecords 全部置空
- `attributes.js`：改为从后端 `/api/stats/profile` 加载维度数据
- `history.js`：修复 Chart.js "Canvas is already in use" 重复创建图表错误

### 后端定时任务基础设施
- 添加 `apscheduler` 依赖
- 7 个批处理函数：archive_incomplete_tasks/refresh_daily_tasks/refresh_weekly_tasks/settle_habit_exp_for_user/snapshot_daily_stats
- 2 个 cron 任务（每日 03:00 + 每周一 03:05）

### 后端迁移完成度确认（~95%）
- 扫描后端 `server.py` 全部 API 路由（~47 个）和 `database.py` 全部数据库表（11 张）
- 确认 P0-P6 所有模块：用户、习惯、行动、目标、任务、定时模板、奖励、统计/热力图/趋势图、活动feed、定时任务全部由后端 API 驱动
- 唯一未迁移的是 skill-tree 独立 SPA（架构上自成一体，用 localStorage）
- APScheduler 定时任务（每日 03:00 任务刷新+习惯结算+统计快照，每周一 03:05 本周任务刷新）已集成在 server.py lifespan 中

### 用户数据修复
- 修复 test/admin 两个默认用户的 `total_exp` 和 `user_dimensions` 数据不一致问题
- `users.total_exp` 从 6,682 → 12,221,688（test）/ 45,000 → 1,793,120（admin）
- 维度 `xp` 恢复为"剩余经验"语义，后端 `get_total_exp_from_dimensions` 改为 `SUM(total_exp_for_level(level) + xp)`
- 后端 `get_profile_stats` 返回维度时新增 `totalXp` 字段（总经验）
- 维度上限从 100 级调整为 120 级（`database.py` + 3 个前端文件中的满级判断）
- 各页面展示修正：attributes.js 的"累计XP"列用 totalXp，history.js 雷达图用 totalXp，action.js 满级显示 MAX

### 前端硬编码修复
- `history.js`：3 处 `fetchProfileStats(1)`/`fetchYearlyActivity(1)`/`fetchDailyExp(1, days)` 改为用 `AppData.user?.id`

### 技能板块用户隔离
- `skills.js`：`my_skills` → `my_skills_{userId}`，`{treeId}_learner` → `{treeId}_learner_{userId}`
- `viewer.html`：learnerKey 从 URL 参数 `userId` 拼接
- `app.js`：`_loadPublishedTree` 和 `_saveLearnerProgress` 中 learner key 带 userId
- `sidebar.js`：`_getLearnerKey()` 返回带 userId 的键名
- 主页面 iframe 通过 `&userId=` 参数传递当前用户 ID

### 删除的残留代码
- `action.js`：删除 `initActionHistory()`（35 条硬编码假数据）、`fallbackSubmitAction()`（本地降级 EXP 计算）、`loadActionHistoryFromLocal()`（本地降级分页筛选），共 ~200 行
- 删除 `actionHistory` 全局变量和 3 个 `Math.random()` ID 生成器

**Why:** 后端迁移完成后，所有核心模块由后端驱动，前端 mock 数据和降级代码不再需要。用户数据修复确保后端逻辑自洽。技能板块用户隔离让 test/admin 的学习进度互不干扰。

**How to apply:** 启动后端后，所有数据通过 API 加载。skill-tree 学习进度通过 iframe URL 中的 `userId` 参数实现隔离。

**Related:** [[2026-07-09-p0-p1-migration]] [[2026-07-09-p2-p3-migration]]