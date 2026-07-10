---
name: scheduled-tasks-and-weekly-templates
description: 任务板块新增定时任务和每周任务功能 + 行动页面SVG图标替换 + 行动中心目标卡片改造 + 仪表盘精简 + 习惯页面全面改造
metadata:
  type: project
  created: 2026-06-30
---

## 概况

两轮改造：
1. 任务板块新增定时任务（按周几凌晨3点自动创建）和每周任务（每周一凌晨3点自动创建）
2. 行动页面三个子板块标题和卡片标题用SVG图标替换emoji
3. 行动中心目标卡片改造，与目标板块数据统一
4. 仪表盘删除快速行动，热力图按经验值深浅

## 一、定时任务 + 每周任务

### 数据结构（data.js）
- `AppData.scheduledTasks[]`：定时任务模板，含 type/daily、weekdays（1-7数字数组）、active 字段。3条预置数据。localStorage 持久化键名 `sg_scheduled_tasks`
- `AppData.weeklyTaskTemplates[]`：每周任务模板，含 type/weekly、active 字段。2条预置数据。localStorage 持久化键名 `sg_weekly_task_templates`
- `getTodayDayOfWeek()`：返回 1=Mon..7=Sun

### 弹窗改造（tasks.js）
- `openTaskModal()`：新增类型切换tab（常规任务/定时任务/每周任务）。本日任务显示常规+定时，本周任务显示常规+每周
- 定时任务：周几圆形勾选器（flex:1撑满）+ 3个预设按钮（工作日/周末/每天）
- `saveTask()`：根据 `taskModalType` 分流保存
- `switchTaskType()` / `toggleWeekday()` / `presetWeekdays()` / `getSelectedWeekdays()`：新辅助函数

### 刷新增强
- `checkTodayRefresh()`：清空后遍历 `scheduledTasks`，weekdays 匹配今天周几的自动创建到 todo
- `checkWeekRefresh()`：清空后遍历 `weeklyTaskTemplates`，active=true 的自动创建到 todo
- 新建 task 带 `sourceTemplateId` 字段追溯来源

### 模板管理UI
- 本日任务底部：`renderScheduledTemplates()` — 可折叠模板列表，每行显示周几标签+任务名+分类图标+EXP，支持启用/停用/编辑/删除
- 本周任务底部：`renderWeeklyTemplates()` — 同上，显示"每周一凌晨3点"调度
- `editTemplate()` / `editWeeklyTemplate()` / `deleteTemplate()` 等全套CRUD函数

### 样式（pages.css）
- `.task-type-tabs` / `.task-type-tab`：类型切换tab
- `.weekday-picker` / `.weekday-btn`：圆形勾选器→圆角矩形撑满
- `.weekday-presets` / `.weekday-preset-btn`：预设按钮 flex:1 撑满
- `.template-section` / `.template-card`：模板区域折叠+卡片样式

### CSS修复
- `components.css`：`.select option { background:#242928; color:var(--color-text-primary) }` 修复下拉白底白字

## 二、行动页面SVG图标替换

### 设计来源
三个根目录SVG文件：`行动-开始行动图标.svg` / `行动-行动中心图标.svg` / `行动-历史行动图标.svg`

### 实现（action.js）
- 新增 `ACTION_ICONS` 对象，13个内联SVG图标
- 开始行动板块：quick_title（闪电）、record_effort（笔记本）、today_stats（柱图）、category_dist（饼图）、recent_actions（时钟）
- 行动中心板块：center_title（星形）、level_progress（奖杯）、activity_feed（喇叭）、habit_checkin（日历勾选）、goals（靶心）、week_tasks（清单）
- 行动历史板块：history_title（书卷）、search（放大镜）

### 标题图标（三个page-header）
- `page-header--with-icon` class：`display:flex;align-items:center;gap:16px`
- 三个标题图标 viewBox 缩为 48×48，去掉方形边框（rect/circle背景），CSS 统一 48×48

### 卡片标题图标
- 开始行动：`.section__title-icon svg` 32×32
- 行动中心：`.ac-module-header__icon svg` 34×34，`margin-top:-4px` 对齐文字

### 搜索框（行动历史）
- `.ah-search-wrapper`：relative容器 + `.ah-search-icon` absolute定位（20×20）+ input padding-left

### 全局滤镜（index.html）
- 隐藏SVG新增 `#glow` filter（feGaussianBlur + feComposite）

## 三、行动中心目标卡片改造

### 数据统一
- `AppData.goals` 每条新增 `status`（active/completed）、`categoryImage`（null=未生成AI图案）
- 删除 `AppData.actionCenter.goals` 冗余数组
- `renderModule4_GoalTracker()` 改为直接从 `AppData.goals` 读取

### 新卡片布局
```
[AI图案48×48]  目标名称
               属性标签 · 剩余 N 天
               下一里程：XXX
```
- 图案：有 `categoryImage` 显示AI图，否则显示分类 SVG 占位
- 剩余天数紧迫色：<30红/<60黄/≥60灰
- 下一里程：milestones 中首个 undone 的 note

### AI图案预留
- `generateGoalImage(goal)`：预留函数，后端就绪后实现
- `saveGoal` 新建后注释掉的异步调用
- `renderGoalCard` 头部图标支持展示AI图案（`.goal-card__ai-img`）

### 筛选改为 active/completed 两状态

## 四、仪表盘精简

- 删除快速行动区域（8分类按钮 + `quickLog` 函数）

## 五、热力图按经验值深浅

- `generateYearlyActivity()`：从 `generateDailyExp(365)` 获取每日EXP，用分位数映射0-5级色阶
- tooltip：从"活跃值"改为"EXP"

## 涉及文件

| 文件 | 操作 | 说明 |
|------|------|------|
| `js/data.js` | 大幅修改 | scheduledTasks/weeklyTaskTemplates + localStorage；generateYearlyActivity 改为EXP驱动；goals新增status/categoryImage；删除actionCenter.goals |
| `js/pages/tasks.js` | 大幅修改 | 弹窗类型切换+周几选择器+分流保存；刷新增强；模板管理全套CRUD |
| `js/pages/action.js` | 大幅修改 | ACTION_ICONS 13个SVG；三板块标题和卡片全面替换；renderModule4_GoalTracker改造；generateGoalImage预留 |
| `js/pages/goals.js` | 修改 | saveGoal新增字段+预留AI生成；renderGoalCard展示AI图案 |
| `js/pages/dashboard.js` | 修改 | 删除快速行动区域+quickLog函数 |
| `js/pages/history.js` | 修改 | 热力图tooltip改为EXP |
| `css/pages.css` | 大量追加 | 任务类型tab/周几选择器/预设按钮/模板区域；page-header图标/卡片标题图标/搜索框；目标卡片新布局 |
| `css/layout.css` | 修改 | page-header--with-icon flex布局；page-header__icon 48×48 |
| `css/components.css` | 修改 | .select option 深色背景 |
| `index.html` | 修改 | 隐藏SVG新增#glow filter |
| `memory/` | 新建/更新 | 本文件 |

**Why:** 任务板块缺少周期自动创建能力；行动页emoji不够精致需要手绘SVG替换；行动中心目标数据冗余需要统一；仪表盘快速行动功能鸡肋；热力图随机数据无意义需要关联实际EXP。

**How to apply:** 定时/每周任务模板通过localStorage持久化，刷新机制在initTaskRefresh()中统一调用。后续新增子板块参考task的三级路由模式。AI图案生成后端就绪后取消generateGoalImage中的注释即可。

## 六、习惯页面全面改造（2026-06-30 第二轮）

### 数据结构扩展（data.js）
`AppData.habits` 每条新增：`category`（关联维度）、`weekSkipped`（跳过标记数组）、`todaySkipped`、`weeklyTarget`（周目标次数）、`xpReward`（每次打卡XP）、`active`（启用状态）
新增 `AppData.lastWeekHabits` 用于本周/上周对比

### 页面结构（habits.js 完全重写）
5 个模块：

**模块一：顶部统计卡片（5列）**
- 今日完成（绿）、最长连续（橙）、本周完成率（蓝）、本月打卡（粉）、活跃习惯（青）
- 每卡片：左侧3px彩色竖线 + 11px灰色标签 + 28px加粗数字 + 11px辅助文字
- 较昨日对比、较上周趋势计算

**模块二：本周概览**
- 7列（周一~周日），每列：星期名 + 日期数字 + 微型圆点阵列
- 今天列绿色高亮边框
- 圆点：绿色=完成、红色=未完成、黄色=跳过、灰色虚线=空
- 本周/上周切换tab

**模块三：习惯卡片网格（2列）**
- 左侧3px彩色边框（完成绿/跳过橙/待办灰）
- 顶部：26px圆形勾选框 + 习惯名 + 🔥连续天数 + 编辑/删除按钮
- 中间：7个22×22星期方块（完成深绿底/未完成红底/跳过黄底）
- 进度条：5px高，底轨#272a34
- 底部：维度标签 + 本周统计(如"5/7") + XP标签(#fbbf24)
- 三种状态：done/skipped/pending，跳过态opacity 0.75
- 点击勾选框三态循环：待办→完成→跳过→待办
- 维度筛选 + 排序（连续天数/已完成优先/待完成优先）

**模块四：连续排行**
- 按streak降序排列top4
- 每行：维度色32px圆角方框(emoji) + 习惯名 + 18px橙色大号数字 + 排名徽章
- 1px分割线#272a34

**模块五：智能洞察**
- 4条mock洞察规则：连续>20成就预警、本周<50%薄弱警告、维度完成率对比、今日剩余待办
- 每条：绿色圆点● + 12px灰色文字
- AI分析按钮（紫色边框），点击显示"功能完善中"

### 样式（pages.css 全部替换旧.habit-*）
- 暗色扁平风格：页面底#15171c，卡片#1e2028，内嵌#16181e
- 无渐变无阴影，按钮#272a34灰底
- 响应式：≤1100px统计卡片3列，≤700px全单列

### 涉及文件

| 文件 | 操作 | 说明 |
|------|------|------|
| `js/data.js` | 修改 | habits扩展字段 + lastWeekHabits |
| `js/pages/habits.js` | 完全重写 | 5模块渲染 + 三态打卡 + 筛选排序 + AI按钮预留 |
| `css/pages.css` | 大量修改 | 替换全部旧habit样式为新暗色扁平风格 |
| `memory/` | 更新 | 本文件追加第六部分 |
