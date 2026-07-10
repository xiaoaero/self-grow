---
name: goals-page-redesign
description: 目标页面全面改造 — 统一深色卡片风格 + 属性筛选 + 删除模式 + 里程碑备注
metadata:
  type: project
  created: 2026-06-28
  updated: 2026-06-28
---

## 概况

目标页面全面视觉改造，与行动中心、成长记录页面风格完全统一。第二轮新增属性筛选、删除模式、里程碑备注编辑功能。

## 全局变更

- **页面底色**：body background 从 `--color-bg-deep` (#1A1817) 改为 `#1A1C1E`
- **页面标题**：`.page-header__title` 从渐变色改为薄荷绿 `#96D8B8` 纯色
- **页面副标题**：`.page-header__subtitle` 改为 `#A0A8A6`，字号 13px

## 目标卡片设计

### 卡片容器
- 背景色：`#242928`，圆角：`10px`
- 内阴影：`inset 0 1px 3px rgba(255,255,255,0.04)`
- 间距：`gap: 16px`

### 头部区域
- 左侧：分类 SVG 图标 + 目标名称（`#F5F5F5` 加粗）+ 日期/剩余天数（`#A0A8A6`）
- 右侧：百分比数字（白色加粗）+ % 符号（`#707876` 淡灰），无底色纯文字

### 里程碑
- 数据结构：`[{ done: 0|1, note: '备注内容' }, ...]`
- 完成状态使用分类渐变色填充
- 鼠标悬停 tooltip 显示备注内容（无备注显示"里程碑 N"）
- 底部计数文字 `#707876`

### 编辑/删除按钮
- 背景：`#2C3231`，文字：`#A0A8A6`
- 编辑 hover：`#96D8B8` 浅绿
- 删除 hover：`#F26B68` 浅红
- **删除按钮条件显示**：仅在删除模式下可见

### 新建目标按钮
- 背景：`#38A878`，hover：`#42B886`

## 工具栏

### 属性筛选
- 下拉框：全部属性 / 8个分类
- 右侧显示匹配数量
- 筛选后空态提示"该分类下还没有目标"

### 删除模式
- 红色按钮 `#C85A4A` 系列配色
- 点击进入删除模式：每张卡片显示删除按钮，按钮变高亮+脉冲动画
- 再次点击"完成删除"退出，删除按钮隐藏
- 删除所有目标后自动退出删除模式

## 弹窗改造

### 里程碑备注编辑器
- 每个里程碑一行：序号 + 备注输入框(max 30字) + 完成勾选框
- 勾选时标签文字在"未开始"/"已完成"之间切换
- 列表区域 max-height 320px 可滚动
- 编辑时保留已有备注和完成状态

### 禁止点击外部关闭
- `goalModalActive` 标记控制
- 重写 `closeModal()` 函数：goal modal 激活时忽略 overlay 点击
- 只能通过"取消"或"创建/保存"按钮关闭

## 数据兼容
- `migrateMilestones()` 自动将旧格式 `[0,1,0]` 迁移为 `[{done,note},...]`

## 涉及文件

| 文件 | 操作 | 说明 |
|------|------|------|
| `js/pages/goals.js` | 完全重写 | 筛选/删除模式状态、renderGoals 工具栏、renderGoalCard 条件删除+toltip、openGoalModal 里程碑编辑器、closeModal 拦截 |
| `css/pages.css` | 追加 | `.goal-toolbar`、`.goal-filter-select`、`.goal-delete-mode-btn` + pulse动画、`.goal-ms-edit-*` 里程碑编辑器样式 |
| `js/data.js` | 修改 | goals 数据 milestones 从数字数组改为对象数组（含 note 字段） |
| `css/layout.css` | 修改 | body background → #1A1C1E；page-header__title → #96D8B8；page-header__subtitle → #A0A8A6 |

**Why:** 目标页面需要筛选能力、安全的删除交互、以及里程碑级别的备注追踪。
**How to apply:** 新增目标时自动生成带备注的里程碑对象，旧数据自动迁移。
