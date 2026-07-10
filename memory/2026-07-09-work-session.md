---
name: 2026-07-09-work-session
description: 7月9日全量工作 — 后端迁移P0-P3、技能树编辑器重构、查看器修复、性能优化、路由修复
metadata:
  type: project
---

# 2026-07-09 工作记录

> 今天的改动横跨后端迁移、技能树重构、性能优化三大块。

---

## 一、后端迁移 P0-P3

根据 [[后端迁移模块]] 文档，完成了 P0 到 P3 的迁移。

### P0 用户数据 + 统计
- **新增** `backend/database.py` — SQLite 数据库，首次启动自动建 users 表并插入 test / admin 两个用户
- **改造** `backend/server.py` — 新增三个用户 API：`POST /api/users/login`、`GET /api/users`、`GET /api/users/profile`
- **新增** `login.html` — 登录选择页，从后端 API 加载用户列表
- **新增** `frontend/js/utils.js` — 用户工具函数（`getCurrentUser`、`setCurrentUser`、`requireLogin`、`fetchUserProfile`）
- **新增** 根目录 `index.html` — 自动跳转登录页
- 后端等级计算（`expForLevel`、`getRankInfo`、`RANK_TABLE`）与前端保持同步

### P1 习惯板块（此前完成，本日对接）
- 习惯 CRUD、周视图打卡、连续天数统计对接后端 API

### P2 行动记录
- 新增 `action_logs` 数据库表 + 4 个 API：`POST /api/actions`、`GET /api/actions`、`GET /api/actions/today-stats`、`GET /api/activities/feed`
- EXP 计算权完全移到后端：`exp_rate × floor(duration/15)`
- `submitAction()` 改为先调后端 API，后端不可用时降级到本地
- 行动历史的分页/筛选/排序全部由后端 SQL 完成

### P3 目标 + 任务
- 新增 5 张表：`goals`、`goal_milestones`（ON DELETE CASCADE）、`tasks`、`scheduled_tasks`
- 新增 15 个 API 端点（目标 CRUD + claim，任务今日/历史/CRUD/状态流转/claim/删除/清空，模板 CRUD）
- 清理 data.js 中 30+ 行 mock 数据（goals/tasks/taskHistory）
- 所有操作有降级模式（后端不可用时 → 本地操作）

**Why:** 逐步将前端模拟数据 + localStorage 持久化替换为后端 SQLite，为后续多用户/数据统计/定时任务打基础。P0-P3 覆盖了用户、习惯、行动、目标、任务五个核心板块。

---

## 二、技能树改造

### 编辑器重构
- **工具栏替换**：删除导入/导出 JSON、导出 HTML 按钮，替换为"💾 保存"、"🚀 上线"、"🔄 更新"三个按钮。上线后"上线"隐藏、"更新"启用
- **新建弹窗**：增加"技能介绍"textarea，`createTree(name, description)` 接受 description 参数
- **侧边栏改造**：增加⋮菜单扩展（重命名、删除、分享），编辑器侧边栏显示技能统计（节点数/已完成/连线数）
- **清理旧业务代码**：删除 `skills.js` 全部旧业务逻辑（技能列表变量、localStorage 读写、进度计算、查看器模态层、演示数据生成），只保留函数壳。删除 `pages.css` 中技能板块全部样式

### 编辑器优化
- **按钮防抖**（`app.js`）：`_debounce(key)` 方法，100ms 同一 key 只放行首次。为 `undo()`、`redo()`、`addRootNode()`、`addChildNode()` 添加防抖
- **交互优化**：去掉左键双击编辑（只能通过右键菜单进入）、去掉按钮文字只留图标（撤销 `↩` 重做 `↪`）、"根节点"→"节点"
- **遮罩层修复**：去掉 `#modal-overlay` 内联 `display:flex`，改为 CSS 控制 `.hidden { display: none !important }`

### 查看器修复
- **viewer.html**：复用编辑器 CSS（`css/style.css` + `css/sidebar.css` + `css/detail-panel.css`）+ 复用 `js/tree-renderer.js` 的 `TreeRenderer` 类，一比一复刻编辑器渲染
- **顶栏修复**：删除 `#viewer-title`，`#viewer-desc` 改为顶栏左侧主文本，优先显示 `treeData.description`，没有则回退到 `treeData.name`
- **节点详情**：点击节点只打开详情面板，仅叉号关闭。修复 `escapeHtml` 缺失导致详情空白
- **连线修复**：箭头指向父节点 → 子节点

**Why:** 技能树从独立开发阶段进入集成阶段。编辑器从"可编辑即可"转向"可发布可分享"的产品形态，查看器从"能看就行"转向"和编辑器视觉一致"。

---

## 三、性能优化

### 后端请求并行化（`app.js`）
- 将 `fetchUserProfile` → `fetchHabits` → `fetchLastWeekHabits` 三个串行 `await` 改为 `Promise.all` 并行发出
- 每个请求 `.catch(() => null)`，后端不可用时静默降级

### 页面 JS 懒加载（`router.js` + `index.html`）
- `index.html` 移除 9 个页面 JS 的 `<script>` 标签，只保留 core（~30 KB）
- `router.js` 新增 `loadPageJS(pageName)` 函数，切换到哪个页面才加载其 JS
- `initTaskRefresh` 位于 tasks.js，启动时通过 `await loadPageJS('tasks')` 预加载

### 效果
| 指标 | 改前 | 改后 |
|------|------|------|
| 初始加载 JS 体积 | ~400 KB | ~30 KB |
| 后端请求 | 串行（3×RTT） | 并行（1×最慢） |

**Why:** 项目持续迭代后，所有页面 JS 同步加载 + 后端请求串行等待，打开越来越慢。懒加载让首次渲染只处理 30 KB，`Promise.all` 让等待时间由最慢请求决定而非三者之和。

---

## 四、其他

- **路由修复**：`serve` 14.x 301 重定向导致路由白屏。启动方式改为 `npx http-server -p 3000`（或 `python -m http.server 3000`），`http-server` 不做 `.html` 后缀重定向
- **README.md 更新**：结构图更新、新增性能优化/架构特点/开发指引章节、数据迁移进度用 ✅/⬜ 标注

**How to apply:** 新增页面时在 `router.js` 的 `PAGE_JS_MAP` 和 `renderers` 映射表中添加条目即可，无需修改 `index.html`。新增 API 端点在 `backend/server.py` 搜索 `@app.get`/`@app.post` 添加。