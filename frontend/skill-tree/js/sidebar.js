/* ================================================================
   sidebar.js — 左侧栏：技能树列表管理
   ================================================================ */

/**
 * 管理多个技能树的创建、切换、删除
 * 数据存储：localStorage 中 'skill_tree_index' 存列表，'tree_{id}' 存每棵树数据
 *
 * 排序规则：按创建时间（createdAt）升序排列，固定顺序，不变动。
 */
class SkillTreeManager {
  constructor(app) {
    this.app = app;
    this.trees = [];
    this.currentId = null;

    // 异步初始化：先尝试从后端加载，失败则从 localStorage 加载
    this._initIndex();
    this._renderList();
    this._bindEvents();
  }

  /* ---- 异步初始化 ---- */

  async _initIndex() {
    const serverTrees = await fetchSkillTreeIndex();
    if (serverTrees && serverTrees.length > 0) {
      // 后端有数据，以后端为准
      this.trees = serverTrees;
      this.trees.sort((a, b) => new Date(a.createdAt) - new Date(b.createdAt));
      // 同步到 localStorage 作为缓存
      saveToStorage('skill_tree_index', this.trees);
      this._renderList();

      // 如果有 currentId 且后端有对应树，自动加载
      if (this.currentId && this.trees.find(t => t.id === this.currentId)) {
        this.switchToTree(this.currentId);
      } else if (this.trees.length > 0 && !this.currentId) {
        this.currentId = this.trees[0].id;
        this.switchToTree(this.currentId);
      }
    } else {
      // 后端不可用或无数据，从 localStorage 加载
      this._loadIndex();
      this._renderList();
    }
  }

  /* ---- 索引管理 ---- */

  _loadIndex() {
    this.trees = loadFromStorage('skill_tree_index', []);
    // 按创建时间升序排列，保证列表顺序固定
    this.trees.sort((a, b) => new Date(a.createdAt) - new Date(b.createdAt));
  }

  _saveIndex() {
    saveToStorage('skill_tree_index', this.trees);
  }

  _getStorageKey(treeId) {
    return 'tree_' + treeId;
  }

  /* ---- API 方法 ---- */

  getCurrentTreeData() {
    return loadFromStorage(this._getStorageKey(this.currentId), null);
  }

  createTree(name = '新建技能树', description = '') {
    const id = 'tree_' + Date.now().toString(36) + '_' + Math.random().toString(36).slice(2, 6);
    const now = new Date().toISOString();
    const entry = {
      id,
      name,
      description,
      createdAt: now,
      updatedAt: now,
      nodeCount: 0,
      completedCount: 0,
      updateHistory: []
    };
    this.trees.push(entry);
    this._saveIndex();

    const data = { name, description, nodes: [], connections: [] };
    saveToStorage(this._getStorageKey(id), data);

    // 异步同步到后端
    createSkillTreeOnServer(id, name, description);
    saveSkillTreeDraft(id, {
      name, description, data,
      node_count: 0, completed_count: 0, image: '', remark: '',
    });

    return id;
  }

  deleteTree(treeId) {
    const idx = this.trees.findIndex(t => t.id === treeId);
    if (idx === -1) return false;

    this.trees.splice(idx, 1);
    this._saveIndex();

    try {
      localStorage.removeItem(this._getStorageKey(treeId));
      localStorage.removeItem(this._getPublishedKey(treeId));
      localStorage.removeItem(this._getLearnerKey(treeId));
    } catch (e) {
      console.warn('Failed to remove tree data:', e);
    }

    // 异步删除后端数据
    deleteSkillTreeOnServer(treeId);

    return true;
  }

  switchToTree(treeId) {
    if (treeId === this.currentId) return;

    this._saveCurrentTree();

    this.currentId = treeId;
    const data = this.getCurrentTreeData();
    if (data) {
      this.app.loadData(data);
    }
    this._renderList();
  }

  _saveCurrentTree() {
    if (!this.currentId) return;

    const data = {
      name: this.app.treeName,
      description: this.app.treeDescription,
      nodes: this.app.nodes.map(n => {
        const { _selected, _linking, _learningState, ...rest } = n;
        return rest;
      }),
      connections: this.app.connections
    };

    saveToStorage(this._getStorageKey(this.currentId), data);

    const entry = this.trees.find(t => t.id === this.currentId);
    if (entry) {
      entry.name = this.app.treeName;
      entry.description = this.app.treeDescription;
      entry.nodeCount = this.app.nodes.length;
      entry.completedCount = this.app.nodes.filter(n => n.progress === 100).length;
      this._saveIndex();
    }

    // 异步同步到后端
    saveSkillTreeDraft(this.currentId, {
      name: this.app.treeName,
      description: this.app.treeDescription,
      data: data,
      node_count: this.app.nodes.length,
      completed_count: this.app.nodes.filter(n => n.progress === 100).length,
      image: entry && entry.image ? entry.image : '',
      remark: entry && entry.remark ? entry.remark : '',
    });
  }

  getCurrentEntry() {
    return this.trees.find(t => t.id === this.currentId) || null;
  }

  refreshStats() {
    const entry = this.trees.find(t => t.id === this.currentId);
    if (entry) {
      entry.name = this.app.treeName;
      entry.description = this.app.treeDescription;
      entry.nodeCount = this.app.nodes.length;
      entry.completedCount = this.app.nodes.filter(n => n.progress === 100).length;
      this._saveIndex();
      this._renderList();
    }
  }

  /** 发布（上线）当前技能树到查看器存储区 */
  publishTree(treeId) {
    // 如果要发布的不是当前树，先切换到它
    if (treeId !== this.currentId) {
      this.switchToTree(treeId);
    }

    // 先保存当前编辑内容
    this._saveCurrentTree();

    // 读取完整的草稿数据
    const draftData = loadFromStorage(this._getStorageKey(treeId));
    if (!draftData || !draftData.nodes) {
      showToast('技能树为空，无法上线', 'error');
      return;
    }

    // 读取已有的发布版数据中保留的学习者进度
    const publishedKey = this._getPublishedKey(treeId);
    const existingPublished = loadFromStorage(publishedKey);
    const existingLearner = loadFromStorage(this._getLearnerKey(treeId), {});

    // 如果已有发布版，合并 learner 进度（保留旧的已完成节点进度）
    if (existingPublished && existingPublished.learner) {
      Object.keys(existingPublished.learner).forEach(nodeId => {
        if (existingLearner[nodeId] === undefined) {
          existingLearner[nodeId] = existingPublished.learner[nodeId];
        }
      });
    }

    // 构建发布数据：纯树结构 + 学习者进度
    const publishedData = {
      name: draftData.name,
      description: draftData.description,
      nodes: draftData.nodes,
      connections: draftData.connections,
      learner: existingLearner,
      publishedAt: new Date().toISOString()
    };

    // 保存发布版到 localStorage
    saveToStorage(publishedKey, publishedData);

    // 更新索引中的发布状态和更新历史
    const entry = this.trees.find(t => t.id === treeId);
    if (entry) {
      const isUpdate = !!entry.publishedAt;
      entry.publishedAt = publishedData.publishedAt;
      entry.updateHistory = entry.updateHistory || [];
      entry.updateHistory.push({
        type: isUpdate ? 'update' : 'publish',
        timestamp: new Date().toISOString(),
        nodeCount: draftData.nodes.length
      });
      this._saveIndex();
    }

    this._renderList();

    // 异步同步到后端
    publishSkillTreeOnServer(treeId, publishedData, draftData.nodes.length,
      draftData.nodes.filter(n => n.progress === 100).length);

    showToast(entry && entry.publishedAt ? '🔄 已更新上线版本' : '🚀 已上线：' + (entry ? entry.name : ''), 'success');
  }

  /** 检查是否已发布 */
  _isPublished(treeId) {
    return loadFromStorage(this._getPublishedKey(treeId)) !== null;
  }

  /** 获取发布版存储 key */
  _getPublishedKey(treeId) {
    return treeId + '_published';
  }

  /** 获取学习者进度存储 key（按用户隔离） */
  _getLearnerKey(treeId) {
    var userId = new URLSearchParams(location.search).get('userId') || '';
    return treeId + (userId ? '_learner_' + userId : '_learner');
  }

  /* ---- 渲染 ---- */

  _renderList() {
    const container = document.getElementById('tree-list');
    if (!container) return;

    if (this.trees.length === 0) {
      container.innerHTML = '<div class="tree-list-empty">暂无技能树<br>点击上方 ➕ 创建</div>';
      return;
    }

    // 直接按 trees 数组顺序渲染（_loadIndex 已按 createdAt 排序，后续 push 追加到末尾）
    container.innerHTML = this.trees.map(t => {
      const isActive = t.id === this.currentId;
      return `
        <div class="tree-list-item ${isActive ? 'active' : ''}" data-tree-id="${t.id}">
          <div class="tree-item-body">
            <div class="tree-item-header">
              <span class="tree-item-name">${this._escapeHtml(t.name)}</span>
            </div>
            <div class="tree-item-meta">
              <span class="tree-item-meta-node">${t.nodeCount ?? 0} 节点</span>
              <span class="tree-item-meta-date">创建 ${this._formatDate(t.createdAt)}</span>
            </div>
            <div class="tree-item-updated">上次更新 ${this._formatDateTime(t.updatedAt)}</div>
          </div>
          <button class="tree-item-menu-btn" data-tree-id="${t.id}">⋮</button>
          <div class="tree-item-menu" data-menu-id="${t.id}">
            <div class="tree-item-menu-item" data-action="edit-intro" data-tree-id="${t.id}">✏️ 更改介绍</div>
            <div class="tree-item-menu-item" data-action="delete" data-tree-id="${t.id}">🗑️ 删除</div>
          </div>
        </div>`;
    }).join('');
  }

  /* ---- 事件 ---- */

  _bindEvents() {
    const treeList = document.getElementById('tree-list');

    // 点击列表项：切换树（排除菜单和菜单按钮的点击）
    treeList.addEventListener('click', (e) => {
      // 如果点的是菜单按钮或菜单内部，不触发切换
      if (e.target.closest('.tree-item-menu-btn') || e.target.closest('.tree-item-menu')) return;

      const item = e.target.closest('.tree-list-item');
      if (item) {
        const treeId = item.dataset.treeId;
        if (treeId && treeId !== this.currentId) {
          this.switchToTree(treeId);
        }
      }
    });

    // 三点菜单按钮：打开/关闭菜单
    treeList.addEventListener('click', (e) => {
      const menuBtn = e.target.closest('.tree-item-menu-btn');
      if (!menuBtn) return;
      e.stopPropagation();

      const treeId = menuBtn.dataset.treeId;
      const menu = document.querySelector(`.tree-item-menu[data-menu-id="${treeId}"]`);
      if (!menu) return;

      // 关闭其他所有菜单
      document.querySelectorAll('.tree-item-menu.open').forEach(m => {
        if (m !== menu) m.classList.remove('open');
      });

      // 切换当前菜单
      menu.classList.toggle('open');
    });

    // 菜单项点击
    treeList.addEventListener('click', (e) => {
      const menuItem = e.target.closest('.tree-item-menu-item');
      if (!menuItem) return;
      e.stopPropagation();

      const action = menuItem.dataset.action;
      const treeId = menuItem.dataset.treeId;

      // 关闭菜单
      const menu = menuItem.closest('.tree-item-menu');
      if (menu) menu.classList.remove('open');

      if (action === 'delete') {
        this._handleDelete(treeId);
      } else if (action === 'edit-intro') {
        this._handleEditIntro(treeId);
      }
    });

    // 点击空白区域关闭菜单
    document.addEventListener('click', () => {
      document.querySelectorAll('.tree-item-menu.open').forEach(m => m.classList.remove('open'));
    });

    // 新建：打开自定义模态框
    document.getElementById('btn-new-tree-sidebar').addEventListener('click', () => {
      const modal = document.getElementById('new-tree-modal');
      const input = document.getElementById('new-tree-name');
      const desc = document.getElementById('new-tree-description');
      input.value = '';
      desc.value = '';
      modal.classList.remove('hidden');
      // 自动聚焦
      setTimeout(() => input.focus(), 100);
    });

    // 新建树确认
    document.getElementById('btn-confirm-new-tree').addEventListener('click', () => {
      this._confirmCreateTree();
    });

    // 新建树输入框回车确认
    document.getElementById('new-tree-name').addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        this._confirmCreateTree();
      }
    });
  }

  _confirmCreateTree() {
    const input = document.getElementById('new-tree-name');
    const descInput = document.getElementById('new-tree-description');
    const name = input.value.trim();
    if (!name) {
      showToast('请输入技能树名称', 'error');
      input.focus();
      return;
    }
    const description = descInput.value.trim();

    const id = this.createTree(name, description);
    this.currentId = id;
    this._renderList();
    this.app.newTree();
    this.app.treeName = name;
    this.app.treeDescription = description;
    this._saveCurrentTree();
    document.getElementById('new-tree-modal').classList.add('hidden');
    showToast('已创建技能树：' + name);
  }

  /* ---- 菜单操作处理 ---- */

  _handleDelete(treeId) {
    const entry = this.trees.find(t => t.id === treeId);
    if (!entry) return;
    showConfirm(`确定要删除「${entry.name}」吗？此操作不可恢复。`, () => {
      this.deleteTree(treeId);

      if (this.currentId === treeId) {
        this.currentId = null;
        this.app.newTree();
        this.app._updatePublishButtons();
      }

      this._renderList();
      showToast('已删除：' + entry.name);
    });
  }

  _handleEditIntro(treeId) {
    const entry = this.trees.find(t => t.id === treeId);
    if (!entry) return;

    // 如果当前不是该树，先切换
    if (treeId !== this.currentId) {
      this.switchToTree(treeId);
    }

    // 用 prompt 修改介绍
    const newDesc = prompt('修改技能介绍：', entry.description || '');
    if (newDesc === null) return; // 取消

    entry.description = newDesc.trim();
    this.app.treeDescription = entry.description;
    this._saveCurrentTree();
    this._renderList();
    showToast('✅ 已更新技能介绍', 'success');
  }

  /* ---- 工具 ---- */

  _formatDate(iso) {
    if (!iso) return '-';
    const d = new Date(iso);
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  }

  _formatDateTime(iso) {
    if (!iso) return '-';
    const d = new Date(iso);
    const now = new Date();
    const diffMs = now - d;
    const diffMin = Math.floor(diffMs / 60000);
    if (diffMin < 1) return '刚刚';
    if (diffMin < 60) return `${diffMin} 分钟前`;
    const diffHour = Math.floor(diffMin / 60);
    if (diffHour < 24) return `${diffHour} 小时前`;
    const diffDay = Math.floor(diffHour / 24);
    if (diffDay < 7) return `${diffDay} 天前`;
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  }

  _escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }
}