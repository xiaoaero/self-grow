---
name: 2026-07-09-performance-optimization
description: 应用启动性能优化 — 后端请求并行化 + 页面 JS 懒加载 + README 更新
metadata:
  type: project
---

# 2026-07-09 性能优化 — 启动加速 + 懒加载

## 背景

项目持续迭代后，所有页面 JS 和 CSS 在一个 HTML 中同步加载，初始体积约 **400 KB**，加上启动时串行等待后端 3 个 API 请求，打开速度越来越慢。

## 改动

### 1. 后端请求并行化（`app.js`）

将 `fetchUserProfile` → `fetchHabits` → `fetchLastWeekHabits` 三个串行 `await` 改为 `Promise.all` 并行发出。后端响应时间从 3×RTT 降为 1×（最慢请求）。

- 失败容错：每个请求都 `.catch(() => null)`，后端不可用时静默降级

### 2. 页面 JS 懒加载（`router.js` + `index.html`）

- **`index.html`**：移除 9 个页面 JS 的 `<script>` 标签，只保留 core（data.js/router.js/utils.js/components.js/app.js）
- **`router.js`**：新增 `loadPageJS(pageName)` 函数，通过 `document.createElement('script')` 动态加载。首次访问某页面才加载其 JS，加载成功后才执行渲染函数
- 加载失败显示友好提示，不会崩

首次加载 JS 体积从 **~400 KB → ~30 KB**。

### 3. 依赖处理

- `initTaskRefresh`（位于 tasks.js）在 `app.js` 启动时通过 `await loadPageJS('tasks')` 预加载 tasks.js 后再执行
- 各页面之间无交叉引用，懒加载安全

### 4. README 更新

- 结构图更新（移除不存在文件，匹配实际目录）
- 新增「性能优化」章节说明懒加载和并行化
- 新增「架构特点」章节（等级系统、数据迁移进度）
- 新增「开发指引」章节（新增页面、技能树开发、后端开发）
- 数据迁移进度用 ✅/⬜ 标注

## 效果

| 指标 | 改前 | 改后 |
|------|------|------|
| 初始加载 JS 体积 | ~400 KB | ~30 KB |
| 后端请求 | 串行（3×RTT） | 并行（1×最慢） |
| 页面切换 | 全部已加载 | 首次进入时动态加载 |

**Why:** 用户感知到的"打开慢"主要来自两个源头：页面加载时浏览器解析/编译 400 KB JS 的耗时，以及后端 3 个串行请求等待后端响应的空闲时间。懒加载让首次渲染只处理 30 KB，`Promise.all` 让等待时间由最慢的请求决定而非三者之和。

**How to apply:** 新增页面时，在 `router.js` 的 `PAGE_JS_MAP` 和 `renderers` 映射表中添加条目即可，无需修改 `index.html`。