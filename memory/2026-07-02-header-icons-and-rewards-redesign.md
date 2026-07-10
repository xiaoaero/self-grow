---
name: header-icons-and-rewards-redesign
description: 大标题图标替换7个页面 + 习惯每天默认未打卡 + 奖励商城改为条件解锁/领取机制
metadata:
  type: project
  created: 2026-07-02
---

## 概况

本轮改造包含三大块：所有页面大标题SVG图标替换、习惯板块每日重置、奖励商城去EXP改为条件机制。

## 一、大标题图标替换

### 设计来源
根目录 `大标题图标.svg` — 7个手绘图标，原为80×80深色圆角矩形容器。

### 实现
- `js/utils.js` 新增 `HEADER_ICONS` 对象，7个内联SVG（58×58 viewBox）
- `index.html` 新增7个渐变定义 `g-hdr-attr` ~ `g-hdr-reward`
- 图标背景改为**圆形**（`circle r="28"`），与历史页/行动页标题图标风格统一
- 用 `<g transform="scale(0.82)">` 整体缩放，圆边框略粗有呼吸感
- 边框 opacity 0.2，淡色不抢视觉

### 替换的页面
| 图标 | 页面 |
|------|------|
| `HEADER_ICONS.attributes` | 属性面板 |
| `HEADER_ICONS.goals` | 目标 |
| `HEADER_ICONS.todayTasks` | 本日任务 |
| `HEADER_ICONS.weekTasks` | 本周任务 |
| `HEADER_ICONS.historyTasks` | 历史任务 |
| `HEADER_ICONS.habits` | 习惯追踪 |
| `HEADER_ICONS.rewards` | 奖励商城 |

### 成长记录统计卡片调整
- 图标从22×22缩小到16×16
- 标签字号12→13px，数字28→24px
- 数字letter-spacing从-1px→-0.5px
- 标签行居中

## 二、习惯板块：每天默认未打卡

### 问题
`settleHabitExp()` 凌晨结算后只重置 `todayDone`/`todaySkipped`，没有清除 `weekDone[todayDow]`，导致新一天可能残留旧标记。

### 修改
`js/pages/tasks.js` — `settleHabitExp()`：
- 新增 `todayDow` 变量
- 所有习惯（不管是否已打卡）统一重置 `todayDone=false`, `todaySkipped=false`
- 清除当天 `weekDone[todayDow]` 和 `weekSkipped[todayDow]`
- 确保每天开始时所有习惯都处于"待打卡"状态

## 三、奖励商城全面改造

### 核心变化
- **去掉 EXP 兑换逻辑**，改为"解锁条件→领取条件"两步机制
- 副标题改为"达到条件解锁奖励，满足要求即可领取"
- 删除 EXP 余额卡片
- 已领取的奖励不显示在卡片区，只在领取历史中展示

### 数据结构（data.js）
rewards 每条新增：`unlocked`, `claimed`, `claimedAt`, `image`, `unlockConditions`, `conditions`
移除 `cost` 字段

### 卡片三种状态
- **未解锁**：半透明 + 🔒 锁蒙层 + 显示解锁条件（达成的带绿色 ✓）
- **已解锁**：正常显示 + 领取条件（达成的带绿色 ✓）+ 🎁 领取按钮（条件全满才可用）
- **已领取**：不在卡片区展示

### 双筛选
- **状态筛选**（rewardStateFilter）：全部 / 已解锁 / 未解锁
- **分类筛选**（rewardFilter）：全部分类 / 各分类标签
- 两者可同时生效，工具栏同一行用竖线分隔

### 编辑/删除模式
- **编辑**：每张卡片右上角 ✎ 按钮，点击进弹窗编辑
- **删除**：每张卡片右上角红色虚线选框，勾选后"确认删除（N）"脉冲按钮，弹confirm确认
- 编辑和删除互斥

### 条件自动检测
`isConditionMet()` 函数解析条件文本：
- `累计获得 N EXP` → `AppData.user.exp`
- `连续打卡 N 天` → 习惯最大 streak
- `完成 N 个任务` → `profile.tasksCompleted`
- `达成 N 个目标` → `profile.goalsAchieved`
- `XX维度达到 LvN` → 维度 level
- `本周完成率 ≥ N%` → 实时计算习惯完成率

### 领取历史
- 只显示已领取的奖励
- 点击展开详情：解锁条件 + 领取条件（均标记 ✅）

## 涉及文件

| 文件 | 操作 |
|------|------|
| `js/utils.js` | 新增 HEADER_ICONS 7个 SVG 图标 |
| `index.html` | 新增7个渐变定义 g-hdr-* |
| `js/pages/attributes.js` | 标题 emoji→HEADER_ICONS |
| `js/pages/goals.js` | 标题→HEADER_ICONS |
| `js/pages/tasks.js` | 3个子板块标题→HEADER_ICONS + settleHabitExp 清零修复 |
| `js/pages/habits.js` | 标题→HEADER_ICONS |
| `js/pages/rewards.js` | 标题→HEADER_ICONS + 完全重写奖励逻辑 |
| `js/data.js` | rewards 数据结构扩展 |
| `css/pages.css` | 统计卡片尺寸调整 + 锁蒙层 + 编辑按钮 + 领取历史样式 |
| `css/layout.css` | 无需修改（已有 page-header--with-icon 支持） |

**Why:** 大标题图标从SVG设计稿提取，统一视觉风格；习惯每天从待打卡开始避免状态残留；奖励商城从EXP兑换改为条件制更符合成长系统的核心逻辑。

**How to apply:** 后续新增页面标题图标参考 HEADER_ICONS 模式（58×58 圆形背景 + scale(0.82) transform）；奖励条件文本遵循关键词模式可自动检测达成状态。
