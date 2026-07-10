---
name: tasks-page-redesign
description: 任务页面拆分本日任务/本周任务子板块 + EXP手动领取 + 筛选/删除模式
metadata:
  type: project
  created: 2026-06-28
---

## 概况

将原有单一三栏看板任务页拆分为两个子板块，统一深色卡片风格，EXP 不再自动发放。

## 侧边栏 & 路由

- 侧边栏「任务」新增箭头 + 子菜单：「本日任务」(`tasks.today`) /「本周任务」(`tasks.week`)
- Router: `currentTasksSubPage` 状态变量，`navigateTo('tasks', 'today'|'week')`
- 父级点击切换子菜单展开/收起

## 本日任务（`renderTodayTasks`）

### 布局
- 左右两栏：左侧「待办」+ 右侧「已完成」
- 每栏：`#242928` 卡片容器，10px 圆角，inset 阴影
- 任务卡片：分类 SVG 图标 + 标题 + 分类名 + 优先级标签 + EXP 数值

### 交互
- 待办任务点击「完成」→ 移入已完成栏（不自动发放 EXP）
- 已完成栏中未领取的任务显示琥珀金「领取 N EXP」按钮（带 glow 动画）
- 点击领取 → `AppData.user.exp` 增加，标记 `claimed = true`
- 已领取显示「✅ 已领取」

### 工具栏
- 属性筛选下拉 + 匹配计数
- 红色「删除任务」按钮切换删除模式（复用 goals 的 `.goal-delete-mode-btn` 样式）
- 删除模式下每张卡片出现删除按钮

## 本周任务（`renderWeekTasks`）

- 保留原有三栏 Kanban 布局（待办/进行中/已完成）
- 新增工具栏：属性筛选 + 删除模式（同本日任务）
- EXP 不自动发放：拖入/右移到 done 栏不触发 EXP
- 已完成栏中显示「领取」按钮，点击领取 EXP
- 删除模式下每张卡片出现删除按钮

## 弹窗

- 三列布局：分类 / 优先级 / 经验值奖励
- `taskModalActive` 标记，禁止点击外部关闭（同 goals 弹窗逻辑）
- `closeModal` 合并检查 `goalModalActive || taskModalActive`

## 涉及文件

| 文件 | 操作 | 说明 |
|------|------|------|
| `js/pages/tasks.js` | 完全重写 | renderTasks 分派、renderTodayTasks、renderWeekTasks、moveTaskToDone、claimTaskExp、open/close/saveTaskModal |
| `css/pages.css` | 追加 | `.task-today-*` 两栏布局 + 卡片样式 + 按钮样式 + 响应式 |
| `js/router.js` | 修改 | currentTasksSubPage、tasks 子菜单展开/收起逻辑 |
| `index.html` | 修改 | 侧边栏 tasks nav-item 改为可展开 + 2个子项 |
| `js/pages/goals.js` | 追加 | claimGoalReward 函数 |

**Why:** 任务页需要区分日视图和周视图，EXP 不应自动发放而是用户手动领取增加仪式感。
**How to apply:** 本日任务和本周任务共享 tasks 数据池，筛选和删除模式复用 goals 页面的工具栏样式。
