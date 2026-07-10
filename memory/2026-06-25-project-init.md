---
name: project-init
description: 个人成长系统项目初始化 — 完整前端界面搭建
metadata:
  type: project
  created: 2026-06-25
---

## 项目概况

项目名称：**个人成长系统 (Self Grow System)**
项目路径：`D:/pycharm/projec/self_grow_system/`
技术栈：原生 HTML/CSS/JS（无框架），Chart.js CDN 用于雷达图

## 设计决策

- **UI风格**：现代玻璃态（毛玻璃效果），暖色调配色
- **主色调**：翡翠绿 #4A9C6C + 琥珀金 #D49A3E + 暖灰底
- **配色原则**：明确避免 AI 经典蓝紫配色
- **架构**：单页面应用，侧边栏切换 8 个栏目，代码按模块拆分

## 文件结构

```
self_grow_system/
├── index.html                  # 入口文件，引入所有 CSS/JS
├── css/
│   ├── variables.css           # CSS变量、主题色、字体、圆角、阴影
│   ├── layout.css              # 全局布局、背景装饰球体、响应式断点
│   ├── sidebar.css             # 侧边栏导航样式
│   ├── components.css          # 通用组件：卡片、按钮、进度条、徽章、输入框、模态框、Toast
│   └── pages.css               # 页面特定样式
├── js/
│   ├── data.js                 # 模拟数据层（用户、属性、习惯、目标、任务、奖励等）
│   ├── router.js               # 页面路由切换 navigateTo()
│   ├── utils.js                # 工具函数（Toast、Modal、格式化等）
│   ├── components.js           # 可复用渲染函数（统计卡片、进度条、EXP条）
│   ├── app.js                  # 应用入口，DOMContentLoaded 初始化
│   └── pages/
│       ├── dashboard.js        # 仪表盘：欢迎区、统计卡片、雷达图、动态时间线
│       ├── action.js           # 行动中心：分类选择、时长记录、EXP计算
│       ├── history.js          # 成长记录：月历热力图、分类筛选、记录列表
│       ├── attributes.js       # 属性面板：六维/八维雷达图、属性详情、经验来源
│       ├── goals.js            # 目标管理：目标卡片、里程碑、截止日期
│       ├── tasks.js            # 任务看板：三列拖拽、优先级、完成获EXP
│       ├── habits.js           # 习惯追踪：打卡、连续天数、周视图
│       └── rewards.js          # 奖励商城：EXP兑换、自定义奖励、兑换历史
└── memory/                     # 项目记忆文档
```

## 8个页面功能详情

1. **仪表盘 (dashboard)**：欢迎横幅、连续打卡天数、EXP进度条、4项今日统计（专注时长/完成任务/习惯打卡/获得经验）、六维雷达图预览、近期动态时间线、快速行动按钮
2. **行动 (action)**：拆分为两个子板块 — "开始行动"（原行动中心：9分类网格选择、时长滑块5-180分钟、备注输入、实时EXP预览、今日统计面板、分类分布图）和"行动中心"（4模块数据看板：升级进度条、动态播报、习惯打卡、目标追踪）
3. **成长记录 (history)**：GitHub风格月历热力图、分类标签筛选、月份切换、记录列表（图标/名称/日期/时长/EXP）
4. **属性面板 (attributes)**：六维/八维图切换（Chart.js radar）、6项属性详情进度条、属性经验获取来源映射
5. **目标管理 (goals)**：目标卡片、里程碑进度条、截止日期倒计时（颜色编码紧急度）、新建/编辑/删除弹窗
6. **任务看板 (tasks)**：三列Kanban（待办/进行中/已完成）、HTML5拖拽、优先级标签、左右移动按钮、完成自动获EXP
7. **习惯追踪 (habits)**：打卡卡片（点击切换）、连续天数火焰、周视图7点、今日完成率统计
8. **奖励商城 (rewards)**：EXP余额展示、分类筛选、奖励卡片网格、兑换按钮（余额不足禁用）、自定义奖励弹窗、兑换历史列表

## 关键技术实现

- **玻璃态效果**：`backdrop-filter: blur(16px)` + 半透明背景 + 细边框
- **雷达图**：Chart.js radar 类型，六维/八维动态切换，destroy 后重建避免冲突
- **页面切换**：CSS动画 `pageEnter`（opacity + translateY），sidebar active 状态同步
- **热力图**：根据每日记录数分5级颜色（empty/low/mid/high/peak）
- **拖拽看板**：HTML5 Drag and Drop API，ondragstart/ondragover/ondrop
- **响应式**：1200px/900px/700px 三个断点，移动端侧边栏可收起

## 待完成

- 后端 API 接口对接（当前为模拟数据）
- 数据持久化（localStorage 或后端数据库）
- 用户认证系统
- 数据统计图表增强（趋势折线图、分类饼图等）

**Why:** 项目从零开始搭建，需要记录初始架构和设计决策，方便后续开发和维护。
**How to apply:** 后续开发时参考此文档了解项目结构和设计原则，新增页面遵循相同的模块拆分模式。
