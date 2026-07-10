---
name: profile-stats-page
description: 成长记录页面改造为数据看板 — 5模块统计面板
metadata:
  type: project
  created: 2026-06-26
---

## 概况

将原有的"成长记录"页面（月历热力图+记录列表）完全替换为个人成长数据看板，包含 5 个模块。

## 页面结构

成长记录页面（`#page-history`）现在渲染 5 个模块：

1. **顶部统计卡片**（6列） — 努力天数、累计XP、打卡次数、完成任务、达成目标、解锁奖励
2. **年度活跃热力图** — GitHub风格，53列×7行，琥珀暖色渐变6级，月份标签，hover tooltip
3. **维度雷达图**（左50%） — 6维（爱好/健康/财务/工作/创作/关系），幂函数缩放防触顶
4. **维度经验条形图**（右50%） — 双层进度条（浅色已获得+深色目标线），hover显示升级进度
5. **每日EXP趋势折线图**（全宽） — Chart.js line，支持7/15/30/90天/1年切换

## 设计决策

- **配色**：热力图用琥珀金 `#D49A3E` 不同透明度（非绿色），折线图用琥珀金，雷达图用琥珀填充
- **卡片面**：`--color-bg-elevated` (#2C2927)，在深色底上形成层次
- **雷达图缩放**：`display = (raw / virtualMax)^0.55 × 100`，virtualMax = maxRaw × 1.15，确保永不触顶
- **热力图布局**：CSS Grid `repeat(53, 1fr)`，按行优先输出（每列=一周），时间从左到右
- **热力图列优先渲染**：`grid[row][col]` 按 row-major 输出到 CSS Grid，自然形成列=周的布局
- **日期格式化**：全项目统一用本地日期格式 `${year}-${month}-${day}`，避免 `toISOString()` 时区偏移

## 新增/修改文件

| 文件 | 操作 |
|------|------|
| `js/pages/history.js` | 重写 — renderHistory() 渲染5模块，+趋势图绘制和切换逻辑 |
| `js/data.js` | 扩展 — profile数据对象、generateYearlyActivity()、generateDailyExp() |
| `css/pages.css` | 追加 — profile-* BEM样式（统计卡片、热力图、雷达图卡片、条形图、趋势图） |

## 数据流

- `AppData.profile` — 统计数值 + 六维数据（含 xpToNext）
- `AppData.profile.yearlyActivity` — `generateYearlyActivity()` 生成365天活跃数据
- `AppData.generateDailyExp(days)` — 按需生成N天每日EXP聚合数据

## 关键技术点

- **热力图方向**：`firstDayOfWeek` 计算 Jan 1 偏移，`grid[row][col]` 二维数组按行输出
- **雷达图防触顶**：幂函数 `Math.pow(v/virtualMax, 0.55) * 100`，外圈刻度反向映射显示原始值
- **趋势图自适应**：`maxTicksLimit` 根据天数调整，长范围隐藏数据点（`pointRadius: 0`）
- **Chart.js 生命周期**：实例存 `canvas._chart`，切换时 destroy 再重建

**Why:** 成长记录页面需要展示更全面的数据看板，包含统计、热力图、雷达图、经验进度和趋势。
**How to apply:** 后续新增统计模块遵循相同的 BEM 命名和渲染模式。
