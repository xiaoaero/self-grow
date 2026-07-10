---
name: attribute-icon-system
description: 属性面板改造 — 编号替换复选框 + 属性介绍卡片 + SVG图标系统全面替换
metadata:
  type: project
  created: 2026-06-27
  updated: 2026-06-27
---

## 概况

本轮改造包含三个主要任务：
1. 属性面板复选框改为编号 + 新增属性详细介绍卡片
2. 全系统从6维属性升级为8维属性（对齐SVG设计稿）
3. 所有属性图标从emoji替换为自定义SVG矢量图标

## 属性面板改造

### 复选框 → 编号
- 第一列从空复选框 `☐` 改为带圆形底数的序号 `#1` ~ `#8`
- CSS: `.attr-cell--check`/`.attr-check` → `.attr-cell--num`/`.attr-num`
- 表头改为 `#`

### 新增属性介绍卡片
- 表格下方增加 `📋 属性详情介绍` 区域
- 2列网格排列 8 张卡片（≤600px 变 1 列）
- 每张卡片：SVG图标 + 属性名 + 关键词标签 + 详细介绍段落
- 数据新增 `description` 字段，每属性 50-60 字介绍
- CSS: 完整 `.attr-intro-*` 样式体系

## 8维属性体系（替代旧6维）

### 旧 → 新映射

旧 6 维（D&D风格）：力量/敏捷/智力/魅力/耐力/幸运
新 8 维（生活维度）：健康/学习/关系/工作/创作/财务/爱好/心灵

旧 9 分类：学习/健康/健身/爱好/穿搭/技能/阅读/社交/冥想
新 8 分类：健康/学习/关系/工作/创作/财务/爱好/心灵

### 涉及的属性字段
- `data.js`: `categories`（9→8）、`attributes`（6→8）、`advancedAttributes`（8→8重定义）、`attributeDetails`、`profile.dimensions`（6→8）、`actionCenter.dimensions`（7→8）、`actionCenter.activities`、`actionCenter.goals`、`actionCenter.weeklyTasks`
- `dashboard.js`: 标题"六维属性概览"→"八维属性概览"，雷达图使用 `advancedAttributes`，快速按钮 6→8
- `action.js`: `initActionHistory()` 35条数据分类索引重新映射，筛选下拉全部更新
- `history.js`: `drawProfileRadarChart()` 从 `profile.dimensions`（已是8维）读取

## SVG 图标系统

### 设计来源
根目录 `属性图标.svg` — 用户手绘的 680x520 设计稿，8个属性各含独立图标 + 渐变配色

### 配色方案（来自SVG渐变）

| 属性 | 颜色 | 渐变 |
|------|------|------|
| 健康 Health | `#FF7B72` | → `#E5534D` 珊瑚红 |
| 学习 Learning | `#58D5C9` | → `#2DBBAF` 青绿 |
| 关系 Relations | `#FF91A8` | → `#F06590` 暖粉 |
| 工作 Work | `#FFCA40` | → `#F5A623` 琥珀金 |
| 创作 Creation | `#B794F6` | → `#8B5CF6` 紫 |
| 财务 Finance | `#4ADE80` | → `#22C55E` 翠绿 |
| 爱好 Hobbies | `#F472B6` | → `#E879F9` 洋红 |
| 心灵 Spirit | `#FBBF24` | → `#F97316` 金橙 |

### 技术实现
- `data.js` 新增 `AttrIcons` 对象，8个 key 对应 SVG inner HTML（24x24 viewBox）
- `index.html` `<body>` 顶部新增隐藏 `<svg>` 元素，包含 8 个 `<linearGradient>` 定义（id: `g-health`, `g-study`, `g-relate`, `g-work`, `g-create`, `g-money`, `g-hobby`, `g-soul`）
- `utils.js` 新增 `attrIcon(attrId, size)` 函数 —— 根据属性 ID 返回带尺寸的内联 SVG 字符串
- 所有数据对象移除 `icon` emoji 字段，改用 `attrId` 字段
- 所有渲染处统一使用 `attrIcon(id, size)` 生成图标

### 进度条/Lv标签颜色化
- 属性表进度条：行内 `style="background:${d.color}"`，每个属性用自己颜色
- Lv 标签：行内 `style="background:${d.color}22;color:${d.color}"` 半透明底+同色文字
- 行动中心模块一进度条：同步使用 `d.color`
- CSS 清理：移除 `attr-progress__fill--lv1/2/3`、`attr-lv--high`/`attr-lv--lv3`

## 涉及文件

| 文件 | 操作 | 说明 |
|------|------|------|
| `index.html` | 修改 | 新增隐藏SVG渐变定义（8个linearGradient）|
| `js/data.js` | 大幅修改 | 新增AttrIcons；categories/attributes/advancedAttributes/attributeDetails/profile.dimensions/actionCenter全部重构为8维 |
| `js/utils.js` | 扩展 | 新增 `attrIcon()`、`drawRadarChart()` 两个函数 |
| `js/pages/attributes.js` | 修改 | 复选框→编号；进度条/Lv颜色化；新增introCards；emoji→attrIcon() |
| `js/pages/dashboard.js` | 修改 | 六维→八维标题；雷达图用advancedAttributes；快速按钮8个；emoji→attrIcon() |
| `js/pages/action.js` | 大幅修改 | initActionHistory分类映射；所有渲染处emoji→attrIcon()；catOptions去emoji |
| `js/pages/history.js` | 修改 | profile-bar图标→attrIcon()；雷达标签去emoji |
| `js/pages/goals.js` | 修改 | 目标卡片/分类下拉→attrIcon() |
| `js/pages/tasks.js` | 修改 | kanban卡片/分类下拉→attrIcon() |
| `css/pages.css` | 修改 | .attr-cell--check→.attr-cell--num；.attr-num新增；.attr-intro-*全套新增；.attr-lv清理旧变体；.attr-progress__fill清理旧变体 |

## 配色一致性

所有 8 个属性在整个系统中使用统一的渐变色：
- 进度条填充色 = 属性色
- Lv 标签 = 属性色 15% 透明底 + 属性色文字
- 雷达图顶点 = 属性色（Chart.js pointBackgroundColor）
- SVG 图标 = 属性渐变色填充

