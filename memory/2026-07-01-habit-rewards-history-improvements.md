---
name: habit-rewards-history-improvements
description: 习惯板块三大改造 + 奖励商城完善 + 成长记录SVG图标替换 + 日期计算修复
metadata:
  type: project
  created: 2026-07-01
---

## 概况

本轮改造涵盖习惯、奖励、成长记录三个板块，包含多个子任务。

## 一、习惯板块改造

### 1.1 打卡不结算经验（凌晨3点统一结算）
- `cycleHabitStatus()` 移除所有即时 EXP 增减，白天打卡只记录 done/skipped 状态
- 新增 `settleHabitExp()` 函数（在 `tasks.js`），凌晨3点后首次进入统计昨日已完成习惯的 XP 总和，统一发放
- 使用 localStorage 键 `habit_last_settle` 防止重复结算
- 结算后自动重置 `todayDone` 和 `habitsChecked`

### 1.2 新增习惯弹窗改造
- 新增 **习惯介绍** 字段（`habit.intro`，textarea max 200字），展示在卡片中（单行省略，hover tooltip）
- 图标输入框右侧新增 **"🤖 AI设计"按钮**（预留，`requestAIIcon()` 提示即将上线）
- 新增 `habitModalActive` 变量，弹窗禁止点击外部关闭
- `goals.js` 的 `closeModal` 检查增加 `habitModalActive`

### 1.3 删除模式改造
- 模块三标题栏新增红色"🗑 删除习惯"按钮
- 点击进入删除模式：卡片左侧显示勾选框（红色虚线圆），编辑/删除按钮隐藏
- 勾选后顶部显示"确认删除（N）"，点击弹出确认弹窗
- `habitDeleteMode` + `habitSelectedForDelete` (Set) 状态管理
- `toggleHabitDeleteMode()` / `toggleHabitSelect()` / `confirmDeleteHabits()` 函数

### 1.4 本周概览回归按日期聚合
- 从"每个习惯一行"回归为"每个日期列下面显示该天所有习惯的小圆点"
- 圆点一行最多6个，横向排列，占80%宽度
- 红色=未完成、绿色=已打卡、黄色=跳过、灰色虚线空心=未来日期

## 二、日期计算Bug修复

**问题**：`date.setDate(todayDate - todayDow + dayIdx)` 在周日（dayIdx=0）时回退到上周日
**修复**：改为以周一为基准 `date.setDate(todayDate - daysFromMonday + dayOffset)`

影响三处：
- `renderModule2_WeekOverview()` — 本周概览日期行
- `renderHabitCard()` — 习惯卡片周进度方块
- `renderModule1_Stats()` — 统计卡片本周完成率（只统计≤今天的日期）

## 三、5个统计卡片计算逻辑修复

- **今日完成**："较昨日"从 `Math.random()` 改为从 `weekDone` 读取实际数据
- **本周完成率**：只统计已过去的日期（≤今天），排除未来日期
- **本月打卡**：从 `streak * 3` 改为 `streak * 0.6` 保守估算
- **活跃习惯**：逻辑正确无变化

## 四、奖励商城完善

### 4.1 自定义奖励弹窗重构
从上到下字段：
1. 奖励名称
2. 描述（textarea）
3. **解锁条件**（动态输入框，最多3个，每行+/-按钮）
4. 展示图片（URL输入框 + "📁 导入"本地图片按钮）
5. **领取条件**（动态输入框，最多5个，每行+/-按钮）

- `rewardModalActive` 弹窗保护
- `addUnlockCondition()` / `addClaimCondition()` 复用 `addConditionRow()` 通用函数
- `removeConditionRow()` 通用删除行函数

### 4.2 奖励卡片展示
- 有图片显示图片，无图片显示 emoji
- 解锁条件区域：🔒 标签 + 黄色圆点列表
- 领取条件区域：🎯 标签 + 绿色圆点列表
- 按钮：条件未满足显示"条件未满"禁用

### 4.3 数据结构
- `reward.unlockConditions` — 解锁条件数组（最多3个）
- `reward.conditions` — 领取条件数组（最多5个）
- `reward.image` — 展示图片 URL/base64

## 五、成长记录 SVG 图标替换

### 5.1 设计来源
根目录 `成长记录图标.svg`，11个手绘图标

### 5.2 渐变定义（index.html）
新增 10 个：`g-gr`, `g-day`, `g-exp`, `g-task`, `g-score`, `g-target`, `g-rew`, `g-heat`, `g-radar`, `g-rank`, `g-trend`

### 5.3 图标对象（history.js）
`HIST_ICONS` 包含 11 个内联 SVG：
- `title` → 页面大标题（58×58，1.2倍于行动页的48×48）
- `days` / `xp` / `checkins` / `tasks` / `goals` / `rewards` → 6个统计卡片（22×22，与标签并排）
- `heatmap` / `radar` / `rank` / `trend` → 模块标题（24×24）

### 5.4 CSS 调整
- `.profile-stat-card__label` 改为 `display:flex; align-items:center`，图标和文字并排
- `.profile-bars-card` 去掉 `justify-content:center`，标题与雷达图对齐
- `.page-header__icon svg` 改为 `width:100%; height:100%`，父容器控制尺寸

## 涉及文件

| 文件 | 操作 |
|------|------|
| `js/pages/habits.js` | cycleHabitStatus 移除EXP；openHabitModal 新增字段+AI按钮+habitModalActive；renderHabitCard 新增intro行+删除模式；saveHabit 新增intro；删除模式全套函数；本周概览回归聚合；统计卡片修复；日期修复 |
| `js/pages/rewards.js` | 完全重写弹窗和保存逻辑；rewardModalActive保护；解锁/领取条件动态行；卡片展示条件区域 |
| `js/pages/history.js` | 新增 HIST_ICONS；renderProfileStatCard 改为图标+标签并排；所有emoji替换为SVG |
| `js/pages/goals.js` | closeModal 检查增加 habitModalActive 和 rewardModalActive |
| `js/pages/tasks.js` | 新增 settleHabitExp() 凌晨结算函数 |
| `js/data.js` | habits 新增 intro 字段 |
| `index.html` | 新增10个渐变定义 |
| `css/pages.css` | 习惯介绍行/删除模式/奖励条件/统计卡片图标/标题图标 样式 |
| `css/layout.css` | page-header__icon svg 改为百分比尺寸 |

**Why:** 习惯板块体验完善（延迟结算增加仪式感、介绍字段丰富信息、安全删除交互）；奖励商城功能补全（解锁+领取双条件体系、图片导入）；成长记录视觉统一（手绘SVG替换emoji）；日期计算bug影响本周概览和统计卡片准确性。

**How to apply:** 后续新增弹窗参考 habitModalActive/rewardModalActive 模式；图标替换参考 HIST_ICONS 模式；条件动态行参考 addConditionRow() 通用函数。
