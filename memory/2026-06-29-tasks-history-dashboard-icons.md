---
name: tasks-history-dashboard-icons
description: 任务板块历史任务子板块 + 刷新机制 + 任务描述展开/收起 + 仪表盘SVG图标替换 + 时长对数滑块
metadata:
  type: project
  created: 2026-06-29
---

## 概况

本轮改造包含五大块：任务板块新增历史任务子板块、本日/本周自动刷新机制、任务描述功能、仪表盘SVG图标替换、开始行动时长对数滑块。

## 一、任务板块新增「历史任务」子板块

### 侧边栏
- `index.html`：`#subnav-tasks` 新增第三项「历史任务」，`data-subpage="tasks.history"`

### 数据层
- `data.js`：tasks 每条新增 `intro`、`createdAt`、`deadline`、`completedAt`、`claimed` 字段
- 新增 `AppData.taskHistory` 数组，15条预置数据（已完成 + 超期混合，覆盖8分类）
- todo 6条 / doing 3条 / done 3条，覆盖全8分类

### 页面
- `tasks.js` 新增 `renderHistoryTasks()` — 统计芯片 + 属性筛选 + 状态筛选 + 4种排序 + 20条/页分页
- 新增 `renderHistoryPagination()` — 页码导航（首/前/页码/后/尾）
- 新增 `clearTaskHistory()` — 清空历史记录（带确认）

## 二、自动刷新机制

### 本日任务凌晨3点刷新
- `checkTodayRefresh()`：每天凌晨3点后首次进入，未完成任务→超期归档，已完成→完成归档，清空 tasks
- localStorage 键 `task_last_refresh_today` 防止重复刷新

### 本周任务周一凌晨3点刷新
- `checkWeekRefresh()`：每周一凌晨3点后首次进入，同样归档+清空
- localStorage 键 `task_last_refresh_week`

### 调用时机
- `app.js` DOMContentLoaded 时调用 `initTaskRefresh()`
- `renderTodayTasks()` 调用前 `checkTodayRefresh()`
- `renderWeekTasks()` 调用前 `checkWeekRefresh()`
- 本日和本周共用 `tasks` 数据池，两个刷新独立触发

## 三、任务描述展开/收起

### 数据结构
- task 新增 `intro` 字段（max 200字），新建时在模态框输入

### 渲染
- `renderTaskIntro(taskId, intro)` — 一行省略 + "展开 ▼" 按钮
- `toggleTaskIntro()` — 点击展开/收起，`100ms` 防抖（`taskIntroDebounce` 对象）
- CSS `.task-intro` / `.task-intro--expanded`：展开时 `white-space: normal`

### 三处使用
- 本日任务卡片 → `renderTodayTaskCard()` 中调用
- 本周任务看板卡片 → `renderKanbanIntro()`
- 历史任务卡片 → `renderHistoryCard()` 中调用

## 四、仪表盘 SVG 图标替换

### 设计来源
- `冒险者面板图标-竞技版.svg` — 7个自定义图标

### 实现
- `dashboard.js` 新增 `DASH_ICONS` 对象，7个独立内联SVG
- 替换位置：
  - 欢迎横幅标题 → `DASH_ICONS.welcome`（42x42）
  - 连续打卡 → `DASH_ICONS.streak`（72x72）
  - 等级LV → `DASH_ICONS.level`（30x30）
  - 今日统计4卡片 → `focus/tasks/habits/exp`（42x42，CSS统一控制）
- `components.js`：`renderStatCard` 支持SVG字符串 icon，`renderExpBar` 新增 levelIcon 参数
- `components.css`：`.stat-card__icon svg` 42x42，背景色淡化

## 五、时长对数滑块

### 实现
- `action.js`：新增 `sliderToMin()` / `minToSlider()` / `sliderChange()` / `numChange()`
- 映射曲线：`minutes = 1 + 299 * (pos/100)^2.5`
- 滑块0-100线性，映射到1-300分钟，指数2.5使前段密集后段稀疏
- 范围从原来的 5-180 扩大到 1-300
- 输入框和滑块双向同步

## 六、本周任务按钮流程改造

- 待办 → "▶ 开始任务"（`startTask(id)`）
- 进行中 → "✅ 完成任务"（`completeTask(id)`）
- 已完成 → "🎁 领取 N EXP" / "已领取"
- 拖拽功能保留

## 七、变量冲突修复

- `tasks.js` 和 `action.js` 中 `historyFilterCategory` 等变量冲突 → tasks.js 中加 `task` 前缀（`taskHistoryFilterCategory` 等）
- `let tasks` 改为 `var tasks` 避免重复声明
- `closeModal` 重复重写 → 合并到 `goals.js`，统一检查 `goalModalActive || taskModalActive`

## 涉及文件

| 文件 | 操作 | 说明 |
|------|------|------|
| `index.html` | 修改 | 侧边栏新增「历史任务」子项 |
| `js/data.js` | 修改 | tasks扩展字段 + taskHistory预置数据 + 模拟任务增多 |
| `js/pages/tasks.js` | 大幅重写 | +历史任务/+刷新机制/+intro展开/+按钮流程 |
| `js/pages/dashboard.js` | 修改 | DASH_ICONS + 7处图标替换 |
| `js/pages/action.js` | 修改 | 对数滑块映射函数 + 时长范围1-300 |
| `js/pages/goals.js` | 修改 | closeModal 合并 taskModalActive 检查 |
| `js/components.js` | 修改 | renderStatCard支持SVG + renderExpBar支持levelIcon |
| `js/app.js` | 修改 | DOMContentLoaded 先调 initTaskRefresh() |
| `css/pages.css` | 追加 | .task-intro-* / .task-history-* / .task-history-pagination-* / .task-modal__intro / 分类按钮放大 |
| `css/components.css` | 修改 | stat-card__icon 尺寸42px / 背景色淡化 |

**Why:** 任务板块需要历史归档能力避免数据丢失；自动刷新机制保证每日/每周任务周期性重置；仪表盘图标使用手绘SVG统一视觉风格；对数滑块提升时长选择的精确度和操作体验。
**How to apply:** 后续新增子板块参考 tasks 的三级路由模式；图标替换参考 DASH_ICONS 模式；滑块参考 log 映射函数。
