---
name: skill-tree-embed-plan
description: 技能树嵌入另一项目的双模式方案（编辑器 + 查看器）
metadata:
  type: reference
  date: 2026-07-08
---

## 目标

将 ai-skill-tree 作为子模块嵌入另一个原生 HTML 项目。一个技能对应一棵技能树。

## 核心设计：双模式 + 数据分离

### 两种模式

| 模式 | 使用者 | 能力 |
|---|---|---|
| `editor` | 管理员 | 增删改技能树、节点、连线、位置、图标、名称 |
| `viewer` | 普通用户 | 查看画布、缩放平移、点击节点看详情、开始学习/标记完成 |

### 数据存储分离

```
localStorage:
  tree_{treeId}              ← 编辑器发布的数据（结构：节点位置、连线、名称、图标等）
  tree_{treeId}_learner      ← 用户学习进度（只存 progress: { node_xxx: 50, node_yyy: 100 }）
```

编辑器可以多次修改发布结构，学习进度按 nodeId 匹配合并，不会丢失。

### 另一个项目集成方式

同域下通过 iframe 嵌入，共享 localStorage：

```html
<iframe src="skill-tree/frontend/viewer.html?treeId=css-basics" width="100%" height="600px"></iframe>
```

管理员入口：`viewer.html?treeId=xxx&admin=1` 或跳转到编辑器页面。

## 工作流程

### 编辑器创建/发布
1. 管理员在编辑器中创建/编辑技能树（节点位置、连线、名称、图标等）
2. 点击「发布」→ 写入 `tree_{treeId}`
3. 用户端看到最新结构

### 编辑器修改/同步
1. 管理员修改已发布的技能树（增删节点、调整位置等）
2. 点击「同步」→ 读取 `tree_{treeId}_learner`，按 nodeId 合并进度到新结构 → 写入 `tree_{treeId}`
3. 用户端刷新后看到新结构 + 保留的学习进度

### 用户学习
1. 用户查看技能树，点击节点看详情
2. 点击「开始学习」/「标记为已学」
3. 学习进度写入 `tree_{treeId}_learner`（只存 nodeId → progress 映射）

## 代码改动计划

### 新增文件
- `frontend/viewer.html` — 查看器入口，精简 HTML（无左侧栏、无 AI 面板、无编辑工具栏）

### 修改文件

| 文件 | 改动 |
|---|---|
| `frontend/js/app.js` | 构造器加 `options.mode` 和 `options.treeId`；viewer 模式跳过编辑器绑定；加 `publishTree()` / `syncTree()` 方法 |
| `frontend/js/interaction.js` | viewer 模式禁用：Ctrl+拖拽、右键菜单、双击编辑、连接模式、Delete/Ctrl+Z/Ctrl+A 快捷键 |
| `frontend/js/detail-panel.js` | 小改：viewer 模式学习按钮行为不变（本来就是学习操作） |
| `frontend/css/style.css` | 加 `.mode-viewer` 类控制隐藏编辑相关 UI |

### 关键逻辑：同步合并

```js
syncTree(treeId, editorNodes, editorConnections) {
  // 1. 读取用户学习进度
  const learnerData = loadFromStorage('tree_' + treeId + '_learner', {});
  // 2. 将用户进度合并到新节点（按 nodeId 匹配）
  editorNodes.forEach(n => {
    if (learnerData[n.id] !== undefined) {
      n.progress = learnerData[n.id];
    }
  });
  // 3. 写入编辑器数据
  saveToStorage('tree_' + treeId, { nodes: editorNodes, connections: editorConnections });
}
```

### 未来迁移

整个编辑器功能会移入主项目，管理员登录后可见。viewer 模式作为普通用户的技能树查看器。

## 相关记忆
- [[work-session-2026-07-07]] — 当前项目的功能实现基础