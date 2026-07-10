---
name: action-center
description: 行动页面完整改造 — 侧边栏3个子板块 + 行动中心5模块看板 + 开始行动重构 + 行动历史独立页面
metadata:
  type: project
  created: 2026-06-27
  updated: 2026-06-27
---

## 概况

将侧边栏"行动中心"改为"行动"，下面拆分三个子板块。整个改造分多轮迭代完成。

## 侧边栏结构

- **父级**："行动"（原"行动中心"），点击展开/收起子菜单，箭头旋转180°
- **子项1**："开始行动" (`action.quick`) — 记录努力 + 今日统计 + 分类分布 + 最近行动
- **子项2**："行动中心" (`action.center`) — 5模块数据看板
- **子项3**："行动历史" (`action.history`) — 完整历史记录页（搜索/筛选/排序/分页）
- 子项样式：缩进24px，小圆点标记，激活态用琥珀金色（`--color-accent`）

## 路由设计

- `navigateTo(pageName, subPage)` — 第二个参数指定子页面
- `currentSubPage` 存储短格式：`'quick'` / `'center'` / `'history'`
- HTML `data-subpage` 使用 `'action.xxx'` 格式，比较时拼接前缀 `'action.' + targetSub`
- `renderAction(subPage)` 分发到三个渲染函数

---

## 子板块一：开始行动 (`renderQuickAction`)

### 布局
- 左侧（~55%）：记录努力卡片
- 右侧（~45%）：今日统计 + 今日分类分布 + 最近行动卡片

### 记录努力卡片
- **模式切换**：顶部两个 tab — "⚡ 快速记录" / "🤖 描述记录"
- **快速记录**：
  - 9分类网格选择
  - 开始时间（24h制数字输入，时:分）
  - 结束时间（自动计算，根据开始时间+时长）
  - 时长滑块 + 数字输入框（支持自定义输入）
  - 备注文本框
  - 提交按钮 + 实时EXP预览
- **描述记录**：大文本框 + AI解析提示，按钮禁用显示"AI 解析（即将上线）"
- 开始时间和时长变化时，结束时间通过 `updateEndTime()` 局部更新DOM，不触发全量渲染

### 最近行动卡片
- 显示最近 8 条记录
- 每条：emoji + 分类名 + 时间范围（日期+起止时间）+ 时长 + 备注（单行省略，hover tooltip）+ EXP
- 底部温馨提示链接 → 跳转到"行动历史"板块

### 数据存储
- `actionHistory` 数组（内存），`initActionHistory()` 初始化35条模拟数据
- `submitAction()` 提交后写入 `actionHistory`，同步更新 `AppData.todayStats`

---

## 子板块二：行动中心 (`renderActionCenter`)

### 5模块布局
```
上半部分（grid 1fr 1fr）：
  左50%：模块一 升级进度条
  右50%：模块二 动态播报（可点击放大弹出面板）

下半部分（grid 1.15fr 0.85fr）：
  左~55%：模块三 习惯打卡（两列卡片网格）
  右~45%：模块四 目标追踪（列表）

底部全宽：
  模块五：本周任务表格
```

### 模块一：升级进度条
- 7维度：爱好/健康/财务/工作/学习/创作/关系
- 每行：emoji + 名称 + Lv标签（翡翠绿底）+ 进度条（琥珀金填充）+ 当前XP数值
- 数据来源：`AppData.actionCenter.dimensions`

### 模块二：动态播报
- 记录列表 + 分类筛选下拉 + 放大按钮
- 放大面板：全屏浮层，筛选下拉 + 关闭按钮 + 点击遮罩关闭
- 数据来源：`AppData.actionCenter.activities`

### 模块三：习惯打卡
- 复用 `AppData.habits`，两列卡片网格
- 每张卡片：习惯名、emoji+打卡状态圆点、本周进度条+百分比、连击天数+打卡按钮
- 点击打卡切换状态，同步更新 todayStats
- 筛选：全部/未打卡/已打卡

### 模块四：目标追踪
- 列表项：emoji + 目标名 + 维度标签 + 状态badge
- 状态：进行中(绿色)/暂停中(灰色)/已完成(蓝色)
- 筛选下拉
- 数据来源：`AppData.actionCenter.goals`

### 模块五：本周任务表格
- 8列（去掉了多选框）：任务 | 属性(emoji) | 目标值 | 结果值 | 进度(进度条) | 状态(药丸) | 截止日期 | 奖励XP | 目标(+展开)
- **两个筛选下拉**：属性筛选 + 状态筛选，可同时生效
- **排序按钮**（5个，激活态琥珀高亮）：A-Z / Z-A / 完成度高→低 / 完成度低→高 / 截止日期
- 筛选和排序可叠加
- 6条示例数据，覆盖6维度×3状态
- 数据来源：`AppData.actionCenter.weeklyTasks`

---

## 子板块三：行动历史 (`renderActionHistory`)

### 统计栏
- 3个芯片：总记录数 / 累计时长 / 累计EXP

### 筛选栏（一行）
- 搜索框（匹配备注和分类名）
- 分类下拉（全部分类/按9分类筛选）
- 排序下拉（6种：最新优先/最早优先/EXP高→低/EXP低→高/时长高→低/时长低→高）
- 日期范围选择器（开始日期 ~ 结束日期）

### 表格（7列）
日期 | 分类(emoji) | 开始 | 结束 | 时长 | 备注(hover tooltip显示完整) | 奖励XP(琥珀底)

### 分页
- 每页 20 条
- 底部页码导航：« ‹ 页码（含省略号） › »
- 当前页按钮琥珀高亮

### 数据
- 35条预置模拟记录，覆盖15天×8分类，可测试分页和筛选组合

---

## 涉及文件

| 文件 | 操作 | 说明 |
|------|------|------|
| `index.html` | 修改 | 侧边栏：父级"行动"+箭头 + 3个子项 + 子菜单容器 |
| `css/sidebar.css` | 追加 | 箭头旋转、子菜单展开/收起、子项样式 |
| `js/router.js` | 修改 | `navigateTo(pageName, subPage)`，子菜单状态管理，拼接 `'action.' + targetSub` 匹配 |
| `js/pages/action.js` | 完全重写 | `renderAction()` 三分发 + `renderQuickAction()` + `renderActionCenter()` + `renderActionHistory()` + 各模块渲染函数 + 状态变量 |
| `js/data.js` | 扩展 | `AppData.actionCenter`（dimensions/activities/goals/weeklyTasks）|
| `js/utils.js` | 追加 | `escapeHtml()` 防XSS |
| `css/pages.css` | 大量追加 | `qa-*` 开始行动布局样式、`ac-*` 行动中心样式、`ah-*` 行动历史样式、响应式断点 |
| `memory/MEMORY.md` | 新建 | 记忆索引 |
| `memory/action-center.md` | 更新 | 本文件 |

## 关键修复记录

- **action.js 筛选框样式**：分离 `background-color` 和 `background-image`，添加 `option` 深色样式，修复白底白字问题
- **模块五工具栏按钮**：CSS `:hover` 和 `svg` 规则被意外覆盖，修复后正常
- **路由子页面匹配**：`data-subpage="action.xxx"` vs `subPage="xxx"` 不匹配，改为拼接前缀比较
- **`renderActionCenter` 函数声明丢失**：编辑时函数头被删，补充 `function renderActionCenter() {`

## 配色（延续现有深色暖灰主题）

- 进度条填充：`--color-accent` (#D49A3E) 琥珀金
- Lv标签：`--color-primary-bg` 翡翠绿底
- XP高亮：`--color-accent-light` (#E8B85A)
- 打卡按钮/主操作：`.btn--accent` 琥珀渐变
- 进行中/已打卡：`--color-success` (#5CAD6C)
- 已完成状态：`--color-info` (#6BA3B8)
- 暂停/灰色态：`--color-text-muted`
