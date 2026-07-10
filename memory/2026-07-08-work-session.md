---
name: work-session-2026-07-08
description: 技能树嵌入主项目 + 项目目录整理
metadata:
  type: project
---

# 工作记录 2026-07-08

## 今日完成

### 1. 技能树嵌入主项目（skill → 我的技能/技能库）

- **新增** `frontend/viewer.html` — 技能树精简查看器，支持 iframe 嵌入 + postMessage 数据传递
- **新增** `frontend/js/pages/skills.js` — 技能页面渲染（我的技能卡片 + 技能库模板 + 模态层 iframe viewer）
- **修改** `index.html` — 侧边栏在习惯和奖励之间插入「技能」导航项，带子菜单
- **修改** `frontend/js/router.js` — 加 skill 路由和 subnav 控制
- **修改** `frontend/js/data.js` — 初始化两棵默认技能树（前端开发、设计模式）到 localStorage
- **修改** `frontend/css/pages.css` — 添加技能卡片、技能库列表、查看器模态层样式

### 2. 项目目录结构整理

- 7 个 `.svg` 散落根目录 → `assets/icons/`
- `后端迁移模块.md` → 根目录保留
- `memory/` + `memory1/` → 合并为根目录 `memory/`
- `frontend/` 重命名后恢复 → 统一为：`index.html` 在根目录，前端代码在 `frontend/` (`css/`, `js/`, `skill-tree/`, `assets/`)
- 所有路径引用统一加 `frontend/` 前缀
- `README.md` 重写为完整项目文档

### 3. 启动方式

```bash
cd D:\pycharm\projec\self_grow_system
npx serve .
# 浏览器打开 http://localhost:3000
```

不要直接双击 `index.html`（`file://` 协议下 iframe 的 localStorage 隔离）。

### 技能树数据存储

- `sg_skills` — 技能列表（localStorage）
- `tree_{treeId}` — 技能树结构（节点/连线）
- `tree_{treeId}_learner` — 学习进度 `{nodeId: progress}`

**Why:** 将 ai-skill-tree 作为项目的一个板块集成，而非独立子模块。
**How to apply:** 当前使用 localStorage，后续迁移到后端后可无缝替换数据读取方式。