---
name: level-system-and-dashboard-2026-07-06
description: 等级系统全面改造、仪表盘待打卡习惯替换、侧边栏动态等级渲染、奖励条件模糊检测+手动确认、后端迁移文档v3、本周概览红绿点bug修复
metadata:
  type: project
---

# 2026-07-06 工作记录

## 一、等级系统全面改造

### 1.1 二次经验公式

**文件**: `js/utils.js`

```js
const MAX_LEVEL = 200;
function expForLevel(L) { return Math.round(5.5632 * Math.pow(L-1, 2) + 300); }
function totalExpForLevel(L) { /* 累计求和 */ }
function levelFromTotalExp(totalExp) { /* 反算等级 */ }
```

### 1.2 十段位映射

**文件**: `js/utils.js` — `RANK_TABLE` 数组，每20级一段：

| tier | 等级区间 | 名称 |
|------|----------|------|
| 1 | Lv1-20 | 初阶冒险者 |
| 2 | Lv21-40 | 历练冒险者 |
| 3 | Lv41-60 | 资深冒险者 |
| 4 | Lv61-80 | 荒野冒险者 |
| 5 | Lv81-100 | 征途冒险者 |
| 6 | Lv101-120 | 秘境冒险者 |
| 7 | Lv121-140 | 破晓冒险者 |
| 8 | Lv141-160 | 星途冒险者 |
| 9 | Lv161-180 | 传奇冒险者 |
| 10 | Lv181-200 | 不朽冒险者 |

### 1.3 十阶段配色主题

**文件**: `js/utils.js` — `LEVEL_THEME` 对象，每段位独立渐变配色（block/bar/barBg/accent），前端保留。

### 1.4 EXP Bar 组件改造

**文件**: `js/components.js` — `renderExpBar()` 完全重写：
- 布局：`[左侧渐变方块 | Lv.XX] [段位称呼] [渐变进度条] [EXP数值]`
- Lv.200 满级专属动画：`maxBadgePulse`、`maxShimmer`、`maxTextShine`、`maxCardGlow`

**文件**: `css/pages.css` — 新增 `.exp-card__*` 全套样式 + 4 个 `@keyframes` 动画

### 1.5 AppData.user 改造

**文件**: `js/data.js`
- `user.expToNext` → getter：`expForLevel(this.level)`
- `user.title` → getter：`getRankInfo(this.level).name`
- 当前模拟数据：`level: 188, exp: 136388`（传奇冒险者，进度~70%）

---

## 二、本周概览红绿点 Bug 修复

**问题**: 习惯板块"本周概览"红绿点与实际情况不一致，`weekDone[dayIdx]` 数组含过期 mock 数据。

**修复**（`js/pages/habits.js`）:
1. `renderModule2_WeekOverview()` — 今天列改用 `todayDone`/`todaySkipped` 作为实时数据源
2. `renderHabitCard()` — 同上，周进度块今天位置改用实时状态
3. `settleHabitExp()`（`js/pages/tasks.js`）— 周一（`todayDow===1`）清零整个 `weekDone`/`weekSkipped` 数组

---

## 三、仪表盘"八维属性概览" → "待打卡习惯"

**文件**: `js/pages/dashboard.js`
- 左侧卡片从八维雷达图（canvas + `drawRadarChart()`）替换为"待打卡习惯"列表
- 新增 `renderPendingHabits()` — 筛选 `active && !todayDone && !todaySkipped`，纯展示（无勾选框、不可交互）
- 全部完成时显示 "🎉 今日习惯全部完成！"
- 右侧"近期动态"卡片不变

**文件**: `css/pages.css` — 新增 `.dash-habit-item` / `.dash-habit-list` / `.dash-habit-empty` 样式

**设计决策**: 仪表盘只做展示，打卡操作留在习惯板块。后续接后端时，数据源从 `AppData.habits` 改为 API GET。

---

## 四、侧边栏 Footer 等级动态渲染

**问题**: `index.html:151-161` 侧边栏 footer 硬编码 `Lv.12`、`1,240 / 2,000 EXP`、`width: 65%`。

**修复**:
- `index.html` — 硬编码替换为 `<div id="sidebar-footer">` 空容器
- `js/utils.js` — 新增 `renderSidebarFooter()`，读取 `AppData.user` + `getRankInfo()` + `getLevelTheme()` 渲染完整 footer（等级徽章 + 段位名 + 进度条 + EXP 数值 + 配色渐变）
- `js/app.js` — `DOMContentLoaded` 时调用 `renderSidebarFooter()`

---

## 五、后端迁移文档 v3

**文件**: `后端迁移模块.md`（根目录）

基于全部 `.js` 文件 + `index.html` 全量扫描，123 项清单：
- 🟢纯UI不迁移 / 🟡需迁移计算逻辑 / 🔴需迁移数据+逻辑 三级标记
- 15 个数据库表设计
- 4 个后端定时任务（每日3am任务刷新 + 每周一刷新 + 每日习惯结算 + 每日统计快照）
- 5 个 localStorage 键清理清单
- 所有 `AppData.user.exp` 和 `AppData.todayStats` 写入位置精确到文件:行号
- 所有 `Math.random()` / `Date.now()` / ID生成模式记录
- P0-P7 迁移优先级

补充遗漏项（vs v2）：`toggleHabitCheckin()`、`migrateMilestones()`、`claimGoalReward()`、`handleRewardImageUpload()`、`saveGoal()` progress计算、`renderModule5_Insights()` 4条规则、`generateGoalImage()` AI预留、`drawTrendChart()` 调用链

---

## 六、UI 微调

| 位置 | 改动 |
|------|------|
| 侧边栏等级徽章 | `width: 46px; height: 46px; border-radius: 10px` — 正方形小圆角 |
| EXP 卡片方块 | `68×68`，`Lv.` `margin-top: -5px` 上移，数字 `font-size: 30px` |

---

## 本轮涉及的全部文件

| 文件 | 改动类型 |
|------|----------|
| `js/utils.js` | 新增等级公式 + RANK_TABLE + LEVEL_THEME + renderSidebarFooter() |
| `js/data.js` | user.expToNext/title 改 getter，Lv.188 mock |
| `js/components.js` | renderExpBar() 完全重写 |
| `js/pages/dashboard.js` | 八维雷达图→待打卡习惯 + renderPendingHabits() |
| `js/pages/habits.js` | 本周概览 todayDone/todaySkipped 修复 |
| `js/pages/tasks.js` | settleHabitExp() 周一重置 weekDone/weekSkipped |
| `css/pages.css` | exp-card 等级系统样式 + dash-habit 样式 + 动画 keyframes |
| `css/sidebar.css` | level-badge 尺寸/圆角调整 |
| `index.html` | sidebar-footer 硬编码→空容器 |
| `js/app.js` | 初始化调用 renderSidebarFooter() |
| `后端迁移模块.md` | 新建（v3，123项全量扫描） |

## 关键设计决策

- **等级公式放后端还是前端？** 公式和段位定义后端持有，升级判定在每次 EXP 变更时由服务端完成。前端只保留 `LEVEL_THEME` 配色映射（纯视觉层）。
- **仪表盘待打卡只展示不交互** — 打卡操作统一在习惯板块，避免数据同步问题。
- **侧边栏 footer 动态渲染** — 与仪表盘 EXP Bar 共享同一套等级/段位/配色系统。

---

## 七、奖励条件模糊检测 + 手动确认

### 7.1 Bug 修复：自动解锁

**问题**: `reward.unlocked` 从未被自动设为 `true`，条件满足但卡片仍显示锁蒙层。

**修复**: `renderRewards()` 开头遍历未解锁奖励，全部条件满足则自动 `unlocked = true`。

### 7.2 条件自动检测：7类模糊正则

按 1→7 顺序匹配，命中自动判定，不命中走手动确认。

| # | 类别 | 正则覆盖 | 数据源 |
|---|------|----------|--------|
| 1 | 等级 | `达到Lv5` `健康升到Lv3` `Lv10等级` | 维度 level / 最高维度等级 |
| 2 | 创建后经验 | `创建后获得500经验` `从创建起拿到1000EXP` | `user.exp - createdAtExp` |
| 3 | 习惯打卡天数 | `早起习惯打卡7天` `连续打卡30天` | habit.streak / 最大 streak |
| 4 | 目标里程碑 | `全栈课程达到里程碑5` `完成"全栈"的第3个里程碑` | milestones done 计数 |
| 5 | 完成任务数 | `完成10个任务` `做完20个任务` `搞定5个任务` | `profile.tasksCompleted` |
| 6 | 达成目标数 | `达成3个目标` `实现2个目标` | `profile.goalsAchieved` |
| 7 | 本周完成率 | `本周完成率≥80%` | 实时计算习惯完成率 |

**关键**: 经验只做"从创建开始计算"，不做累计总经验。新建奖励时快照 `createdAtExp`。

### 7.3 习惯/目标模糊名称查找

`findHabitByName()` / `findGoalByName()` — `includes` 模糊匹配，返回 `{found, ambiguous}`。

歧义处理:
1. 多匹配 → 选匹配位置最靠前
2. 位置相同 → 选名称最短
3. 仍有歧义 → 条件行下方红字提示

### 7.4 手动确认

条件不匹配任何自动模式 → `☐ 确认完成` 按钮 → 弹窗 + 不可撤回警告 → 确认后标记 ✓

### 7.5 新增函数

| 函数 | 用途 |
|------|------|
| `findHabitByName(nameHint)` | 习惯模糊查找，返回 `{found, ambiguous}` |
| `findGoalByName(nameHint)` | 目标模糊查找，返回 `{found, ambiguous}` |
| `isAutoDetectable(condText)` | 判断是否命中任一自动检测模式 |
| `isConditionFulfilled(condText, reward)` | 自动 OR 手动，任一满足即 true |
| `checkAmbiguous(condText)` | 检测名称歧义 |
| `renderConditionRow(condText, reward)` | 条件行渲染（✓ / 确认按钮 / 歧义红字） |
| `openManualConfirmModal(condText, rewardId)` | 手动确认弹窗 |
| `confirmManualCondition(condText, rewardId)` | 执行手动确认 |

### 7.6 奖励系统涉及文件

| 文件 | 操作 |
|------|------|
| `js/pages/rewards.js` | 重写 `isConditionMet`/`isAutoDetectable`；新增 8 个函数；`renderRewards` 自动 unlock；`saveReward` 加 `createdAtExp`；`renderRewardCard` 条件行重构；`claimReward` 改用 `isConditionFulfilled` |
| `css/pages.css` | 新增 `.reward-cond-manual-btn` 和 `.reward-cond-ambiguous` 样式 |

**Why:** 奖励条件检测从固定句式升级为模糊正则 + 手动确认双轨制，7类可量化自动判定，不可量化用户确认。修复解锁状态 Bug。歧义处理避免误匹配。

**How to apply:** 后续扩展条件类型按顺序在 `isConditionMet` 追加正则，同步更新 `isAutoDetectable`。新增实体查找参考 `findHabitByName` 歧义返回模式。
