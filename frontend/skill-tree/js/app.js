/* ================================================================
   app.js — 主控制器
   数据模型、状态管理、CRUD 操作、模块编排
   ================================================================ */

class App {
  constructor(role) {
    this.role = role || 'admin';
    this.isAdmin = this.role === 'admin';
    this.isUser = this.role === 'user';
    this.isPreview = typeof SKILL_TREE_PREVIEW !== 'undefined' && SKILL_TREE_PREVIEW;

    // ---- 数据 ----
    this.nodes = [];
    this.connections = [];
    this.nodeCounter = 0;
    this.treeName = '未命名知识树';
    this.treeDescription = '';

    // 选中状态
    this.selectedIds = new Set();

    // ---- 防抖守卫（0.1s 内阻止重复触发） ----
    this._debounceTimers = {};

    // ---- 模块 ----
    this.renderer = new TreeRenderer('canvas-container');
    this.interaction = new InteractionManager(this);
    this.history = new HistoryManager();
    this.ai = new AIBridge();
    this.sidebar = new SkillTreeManager(this);
    this.detailPanel = new DetailPanel(this);

    // 全局引用（AI 模块需要）
    window.__app = this;

    // ---- 根据角色初始化 ----
    if (this.isPreview) {
      this.initPreviewMode();
    } else if (this.isAdmin) {
      this.initToolbar();
      this.initModals();
      this.initDefaultTree();
      this.updateUndoRedoButtons();
    } else {
      this.initUserMode();
    }
  }

  /* ================================================================
     工具栏事件
     ================================================================ */

  initToolbar() {
    // 保存
    document.getElementById('btn-save').addEventListener('click', () => this.saveTree());

    // 上线
    document.getElementById('btn-publish').addEventListener('click', () => this.publishTree());

    // 更新
    document.getElementById('btn-update').addEventListener('click', () => this.updatePublishedTree());

    // 撤销/重做
    document.getElementById('btn-undo').addEventListener('click', () => this.undo());
    document.getElementById('btn-redo').addEventListener('click', () => this.redo());

    // 添加节点
    document.getElementById('btn-add-root').addEventListener('click', () => this.addRootNode());
    document.getElementById('btn-add-child').addEventListener('click', () => {
      const sel = [...this.selectedIds];
      if (sel.length === 1) this.addChildNode(sel[0]);
      else showToast('请先选中一个父节点', 'error');
    });
    document.getElementById('btn-delete-selected').addEventListener('click', () => this.deleteSelectedNodes());

    // 缩放
    document.getElementById('btn-zoom-in').addEventListener('click', () => {
      this.interaction.scale = clamp(this.interaction.scale + 0.15, this.interaction.minScale, this.interaction.maxScale);
      this.interaction.updateTransform();
      this.renderer.renderGrid(this.interaction.scale, this.interaction.panX, this.interaction.panY);
      this.renderConnections();
    });
    document.getElementById('btn-zoom-out').addEventListener('click', () => {
      this.interaction.scale = clamp(this.interaction.scale - 0.15, this.interaction.minScale, this.interaction.maxScale);
      this.interaction.updateTransform();
      this.renderer.renderGrid(this.interaction.scale, this.interaction.panX, this.interaction.panY);
      this.renderConnections();
    });
    document.getElementById('btn-fit').addEventListener('click', () => {
      this.interaction.fitToScreen(this.nodes);
    });

    // AI 面板切换
    document.getElementById('btn-toggle-ai').addEventListener('click', () => {
      const panel = document.getElementById('ai-panel');
      const btn = document.getElementById('btn-toggle-ai');
      panel.classList.toggle('panel-closed');
      btn.classList.toggle('active');
    });
    document.getElementById('btn-minimize-ai').addEventListener('click', () => {
      const panel = document.getElementById('ai-panel');
      const btn = document.getElementById('btn-toggle-ai');
      panel.classList.add('panel-closed');
      btn.classList.remove('active');
    });

    // 清空 AI 对话（同时丢弃服务端会话）
    document.getElementById('btn-clear-ai').addEventListener('click', () => {
      this.ai.resetSession();
      showToast('已清空 AI 对话');
    });

    // 设置
    document.getElementById('btn-settings').addEventListener('click', () => {
      this.openSettings();
    });
  }

  /* ================================================================
     弹窗管理
     ================================================================ */

  initModals() {
    // 关闭按钮
    document.querySelectorAll('.btn-close-modal').forEach(btn => {
      btn.addEventListener('click', () => {
        btn.closest('.modal').classList.add('hidden');
      });
    });

    // 保存节点编辑
    document.getElementById('btn-save-node').addEventListener('click', () => this.saveNodeEdit());

    // 保存设置
    document.getElementById('btn-save-settings').addEventListener('click', () => this.saveSettings());
  }

  openNodeEditor(nodeId) {
    if (this.isUser) return;
    const node = this.nodes.find(n => n.id === nodeId);
    if (!node) return;

    document.getElementById('edit-name').value = node.name || '';
    document.getElementById('edit-description').value = node.description || '';
    document.getElementById('edit-tags').value = (node.tags || []).join(', ');
    document.getElementById('edit-color').value = node.color || '#2a2a4a';
    document.getElementById('edit-icon').value = node.icon || '📚';
    document.getElementById('edit-priority').value = node.priority || 'none';
    document.getElementById('edit-progress').value = node.progress || 0;

    document.getElementById('node-editor').dataset.nodeId = nodeId;
    document.getElementById('node-editor').classList.remove('hidden');
  }

  saveNodeEdit() {
    const nodeId = document.getElementById('node-editor').dataset.nodeId;
    const node = this.nodes.find(n => n.id === nodeId);
    if (!node) return;

    node.name = document.getElementById('edit-name').value.trim() || node.name;
    node.description = document.getElementById('edit-description').value.trim();
    node.tags = document.getElementById('edit-tags').value.split(',').map(t => t.trim()).filter(Boolean);
    node.color = document.getElementById('edit-color').value;
    node.icon = document.getElementById('edit-icon').value;
    node.priority = document.getElementById('edit-priority').value;
    node.progress = parseInt(document.getElementById('edit-progress').value);

    // 历史栈语义为「改后快照」：先修改再压栈，保证 undo/redo 都能正确工作
    this.saveHistory();
    this.updateLearningStates();
    this.renderNode(node);
    this.renderConnections();
    this.checkDuplicateNames();
    this._updatePublishButtons();
    this.detailPanel.refreshCurrent();
    this.sidebar.refreshStats();
    document.getElementById('node-editor').classList.add('hidden');
  }

  openSettings() {
    if (this.isUser) return;
    document.getElementById('settings-modal').classList.remove('hidden');
  }

  saveSettings() {
    if (this.isUser) return;
    // 后端地址已写死在代码中，无需配置
    document.getElementById('settings-modal').classList.add('hidden');
    showToast('设置已保存', 'success');
  }

  /* ================================================================
     节点 CRUD
     ================================================================ */

  createNode(x, y, options = {}) {
    const size = options.size || 70;
    const node = {
      id: uid(),
      name: options.name || `节点 ${++this.nodeCounter}`,
      x: x - size / 2,
      y: y - size / 2,
      size: size,
      shape: options.shape || 'round',
      icon: options.icon || '📚',
      color: options.color || '#2a2a4a',
      borderColor: options.borderColor || '#444466',
      description: options.description || '',
      tags: options.tags || [],
      priority: options.priority || 'none',
      progress: options.progress || 0,
      _selected: false,
      _linking: false,
      _learningState: 'locked'
    };

    this.nodes.push(node);
    this.updateLearningStates();
    this.renderNode(node);
    this.checkDuplicateNames();
    this.saveHistory();
    return node;
  }

  addRootNode() {
    if (this.isUser) return;
    if (!this._debounce('addRoot')) return;
    const containerW = document.getElementById('canvas-container').clientWidth;
    const containerH = document.getElementById('canvas-container').clientHeight;
    const canvasPos = {
      x: (containerW / 2 - this.interaction.panX) / this.interaction.scale,
      y: (containerH / 3 - this.interaction.panY) / this.interaction.scale
    };
    this.createNode(canvasPos.x, canvasPos.y, { name: '根节点', icon: '🌟', color: '#0f3460' });
    showToast('已添加根节点');
  }

  addChildNode(parentId) {
    if (this.isUser) return;
    if (!this._debounce('addChild')) return;
    const parent = this.nodes.find(n => n.id === parentId);
    if (!parent) return;

    const parentCenter = this.renderer.getNodeCenter(parent);
    const offsetX = (parent.size || 70) + 40;
    // 已有 n 个子节点时，新的排在父节点中心下方依次错开；
    // 原写法 (n-1)*80 会让第一个子节点偏移 -120px（明显偏上且不居中）
    const existingChildren = this.connections.filter(c => c.from === parentId).length;
    const yOffset = existingChildren * 80;

    const child = this.createNode(
      parentCenter.cx + offsetX,
      parentCenter.cy - 40 + yOffset,
      { name: '子节点', icon: '📚' }
    );

    // 自动创建连线
    this.addConnection(parentId, child.id);
    this.updateLearningStates();
    this.renderConnections();
    this.sidebar.refreshStats();
  }

  deleteNode(nodeId, opts = {}) {
    if (this.isUser) return;
    // 删除相关连线
    this.connections = this.connections.filter(c => c.from !== nodeId && c.to !== nodeId);
    // 删除节点
    this.nodes = this.nodes.filter(n => n.id !== nodeId);
    this.selectedIds.delete(nodeId);
    // 详情面板正显示这个节点时关闭，避免展示已删除节点
    if (this.detailPanel && this.detailPanel.currentNodeId === nodeId) {
      this.detailPanel.hideDetail();
    }
    this.renderer.removeNode(nodeId);
    this.updateLearningStates();
    // 立即重渲染连线，避免节点删除后连线残留在画布上
    // 批量删除时（deleteSelectedNodes）由调用方统一渲染一次
    if (!opts.deferRender) this.renderConnections();
  }

  deleteSelectedNodes() {
    if (this.isUser) return;
    if (this.selectedIds.size === 0) return;
    const ids = [...this.selectedIds];
    ids.forEach(id => this.deleteNode(id, { deferRender: true }));
    this.selectedIds.clear();
    this.saveHistory();
    this.renderConnections();
    this.checkDuplicateNames();
    this._updatePublishButtons();
    this.sidebar.refreshStats();
    showToast(`已删除 ${ids.length} 个节点`);
  }

  addConnection(fromId, toId) {
    if (this.isUser) return;
    // 检查是否已存在
    const exists = this.connections.some(c => c.from === fromId && c.to === toId);
    if (exists) return;

    this.connections.push({
      id: uid(),
      from: fromId,
      to: toId,
      color: '#666680',
      dashed: false,
      showArrow: true
    });
  }

  /* ================================================================
     选中操作
     ================================================================ */

  selectNode(nodeId, additive = false) {
    if (!additive) this.deselectAll();
    this.selectedIds.add(nodeId);
    this.syncSelection();
    // 点击节点时打开详情面板（预览模式不打开）
    if (!additive && !this.isPreview) {
      this.onNodeClick(nodeId);
    }
  }

  selectNodes(nodeIds, additive = false) {
    if (!additive) this.deselectAll();
    nodeIds.forEach(id => this.selectedIds.add(id));
    this.syncSelection();
  }

  deselectNode(nodeId) {
    this.selectedIds.delete(nodeId);
    this.syncSelection();
  }

  deselectAll() {
    this.selectedIds.clear();
    this.syncSelection();
  }

  selectAll() {
    this.nodes.forEach(n => this.selectedIds.add(n.id));
    this.syncSelection();
  }

  syncSelection() {
    // 只切换视觉 class，不重建节点 DOM（原实现每个节点都 renderNode，树大时卡顿）
    this.nodes.forEach(n => {
      n._selected = this.selectedIds.has(n.id);
      this.renderer.updateNodeVisual(n);
    });
  }

  getSelectedNodes() {
    return this.nodes.filter(n => this.selectedIds.has(n.id));
  }

  /* ================================================================
     名称重复检测
     ================================================================ */

  /**
   * 检查当前技能树中是否有同名节点
   * 将所有重复节点标记 _nameDuplicate，并清除无重复的标记
   * @returns {boolean} 是否有重复
   */
  checkDuplicateNames() {
    const nameCount = {};
    this.nodes.forEach(n => {
      nameCount[n.name] = (nameCount[n.name] || 0) + 1;
    });

    let hasDuplicate = false;
    this.nodes.forEach(n => {
      const isDup = nameCount[n.name] > 1;
      if (isDup !== n._nameDuplicate) {
        n._nameDuplicate = isDup;
        // 只是切换 class，无需重建节点内容
        this.renderer.updateNodeVisual(n);
      }
      if (isDup) hasDuplicate = true;
    });
    return hasDuplicate;
  }

  /** 是否有名称重复 */
  hasDuplicateNames() {
    const names = this.nodes.map(n => n.name);
    return new Set(names).size !== names.length;
  }

  /* ================================================================
     渲染
     ================================================================ */

  renderNode(node) {
    this.renderer.renderNode(node);
  }

  renderConnections() {
    this.renderer.renderConnections(this.connections, this.nodes);
  }

  renderAll() {
    this.renderer.renderAllNodes(this.nodes);
    this.renderConnections();
    this.renderer.renderGrid(this.interaction.scale, this.interaction.panX, this.interaction.panY);
  }

  /* ================================================================
     学习状态管理
     ================================================================ */

  /**
   * 计算并更新所有节点的学习状态
   * 状态：locked（未解锁）、available（可学习）、completed（已学习）
   */
  updateLearningStates() {
    // 计算每个节点的前置条件是否已满足
    const nodeMap = new Map(this.nodes.map(n => [n.id, n]));

    // 递归查找所有祖先（前置节点）
    const getAncestors = (nodeId, visited = new Set()) => {
      const ancestors = [];
      const parents = this.connections
        .filter(c => c.to === nodeId)
        .map(c => c.from);
      for (const parentId of parents) {
        if (visited.has(parentId)) continue;
        visited.add(parentId);
        const parentNode = nodeMap.get(parentId);
        if (parentNode) {
          ancestors.push(parentNode);
          ancestors.push(...getAncestors(parentId, visited));
        }
      }
      return ancestors;
    };

    // 检查前置条件是否全部完成
    const arePrereqsMet = (nodeId) => {
      const ancestors = getAncestors(nodeId);
      return ancestors.length === 0 || ancestors.every(a => a.progress === 100);
    };

    // 更新每个节点的 _learningState
    this.nodes.forEach(n => {
      if (n.progress === 100) {
        n._learningState = 'completed';
      } else if (n.progress > 0 && n.progress < 100) {
        // 学习中（progress=50）
        n._learningState = 'learning';
      } else if (arePrereqsMet(n.id)) {
        n._learningState = 'available';
      } else {
        n._learningState = 'locked';
      }
    });
  }

  /**
   * 标记节点为「开始学习」
   * 将节点设为学习中状态（progress=50）
   */
  markNodeAsLearning(nodeId) {
    const node = this.nodes.find(n => n.id === nodeId);
    if (!node) return;
    if (node.progress === 100) {
      showToast('该节点已经学习过了', 'error');
      return;
    }
    if (node.progress > 0 && node.progress < 100) {
      showToast('该节点正在学习中', 'info');
      return;
    }
    if (!this._arePrerequisitesMet(nodeId)) {
      showToast('请先完成所有前置条件', 'error');
      return;
    }

    // 用户模式：直接持久化，不走历史栈
    if (this.isUser) {
      node.progress = 50;
      this.updateLearningStates();
      this.renderNode(node);
      this.renderConnections();
      this.detailPanel.refreshCurrent();
      this._saveLearnerProgress();
      showToast(`📖 开始学习：${node.name}`, 'success');
      return;
    }

    node.progress = 50;
    this.updateLearningStates();
    this.renderNode(node);
    this.renderConnections();
    this.detailPanel.refreshCurrent();
    this.sidebar.refreshStats();
    this.saveHistory();
    showToast(`📖 开始学习：${node.name}`, 'success');
  }

  /**
   * 标记节点为已完成
   * 允许从 learning 或 available 状态直接完成
   */
  markNodeCompleted(nodeId) {
    const node = this.nodes.find(n => n.id === nodeId);
    if (!node) return;
    if (node.progress === 100) {
      showToast('该节点已经标记为已学', 'error');
      return;
    }
    if (!this._arePrerequisitesMet(nodeId)) {
      showToast('请先完成所有前置条件', 'error');
      return;
    }

    // 用户模式：直接持久化，不走历史栈
    if (this.isUser) {
      node.progress = 100;
      this.updateLearningStates();
      this.renderNode(node);
      this.renderConnections();
      this.detailPanel.refreshCurrent();
      this._saveLearnerProgress();
      showToast(`✅ 已完成：${node.name}`);
      return;
    }

    node.progress = 100;
    this.updateLearningStates();
    this.renderNode(node);
    this.renderConnections();
    this.detailPanel.refreshCurrent();
    this.sidebar.refreshStats();
    this.saveHistory();
    showToast(`✅ 已完成：${node.name}`);
  }

  /**
   * 检查某节点前置条件是否已满足
   * 注意：学习中（learning）不算满足条件，只有已完成（completed）才算
   */
  _arePrerequisitesMet(nodeId) {
    const nodeMap = new Map(this.nodes.map(n => [n.id, n]));
    const getAncestors = (nodeId, visited = new Set()) => {
      const ancestors = [];
      const parents = this.connections
        .filter(c => c.to === nodeId)
        .map(c => c.from);
      for (const parentId of parents) {
        if (visited.has(parentId)) continue;
        visited.add(parentId);
        const parentNode = nodeMap.get(parentId);
        if (parentNode) {
          ancestors.push(parentNode);
          ancestors.push(...getAncestors(parentId, visited));
        }
      }
      return ancestors;
    };

    const ancestors = getAncestors(nodeId);
    return ancestors.length === 0 || ancestors.every(a => a.progress === 100);
  }

  /**
   * 当点击节点时，同时更新选中状态并打开详情面板
   */
  onNodeClick(nodeId) {
    this.updateLearningStates();
    // 只刷新状态颜色与连线，不再整体重建所有节点的 innerHTML
    this.nodes.forEach(n => this.renderer.updateNodeVisual(n));
    this.renderConnections();
    this.detailPanel.showNodeDetail(nodeId);
  }

  /* ================================================================
     撤销/重做
     ================================================================ */

  saveHistory() {
    if (this.isUser) return;
    this.history.push({
      nodes: deepClone(this.nodes.map(n => {
        const { _selected, _linking, _learningState, ...rest } = n;
        return rest;
      })),
      connections: deepClone(this.connections),
      treeName: this.treeName,
      treeDescription: this.treeDescription
    });
    this.updateUndoRedoButtons();
  }

  /**
   * 防抖守卫：0.1s 内同一 key 的调用只放行第一次
   */
  _debounce(key) {
    const now = Date.now();
    if (this._debounceTimers[key] && now - this._debounceTimers[key] < 100) {
      return false;
    }
    this._debounceTimers[key] = now;
    return true;
  }

  undo() {
    if (this.isUser) return;
    if (!this._debounce('undo')) return;
    const state = this.history.undo();
    if (!state) return;
    this.restoreState(state);
    this.updateUndoRedoButtons();
    showToast('已撤销');
  }

  redo() {
    if (this.isUser) return;
    if (!this._debounce('redo')) return;
    const state = this.history.redo();
    if (!state) return;
    this.restoreState(state);
    this.updateUndoRedoButtons();
    showToast('已重做');
  }

  /**
   * 跳转到指定节点并高亮（从右侧前置条件点击触发）
   */
  jumpToNode(nodeId) {
    // 选中该节点
    this.deselectAll();
    this.selectNode(nodeId, false);
    // 高亮边框
    const node = this.nodes.find(n => n.id === nodeId);
    if (node) {
      node._highlight = true;
      this.renderer.updateNodeVisual(node);
      showToast(`跳转到：${node.name}`);
    }
  }

  /**
   * 清除所有节点的高亮状态
   */
  clearHighlight() {
    let changed = false;
    this.nodes.forEach(n => {
      if (n._highlight) {
        n._highlight = false;
        changed = true;
      }
    });
    if (changed) {
      // 只是去掉高亮 class，不需要整体重建（renderAll 会重建全部节点 DOM）
      this.nodes.forEach(n => this.renderer.updateNodeVisual(n));
    }
  }

  restoreState(state) {
    this.nodes = state.nodes.map(n => ({ ...n, _selected: false, _linking: false, _learningState: 'locked' }));
    this.connections = state.connections;
    this.treeName = state.treeName;
    this.treeDescription = state.treeDescription;
    this.selectedIds.clear();
    // 撤销/重做后节点集合可能已变，详情面板继续显示可能指向已不存在的节点
    if (this.detailPanel && !this.nodes.some(n => n.id === this.detailPanel.currentNodeId)) {
      this.detailPanel.hideDetail();
    }
    this.updateLearningStates();
    this.renderAll();
    this.checkDuplicateNames();
    this._updatePublishButtons();
  }

  updateUndoRedoButtons() {
    if (this.isUser) return;
    document.getElementById('btn-undo').disabled = !this.history.canUndo();
    document.getElementById('btn-redo').disabled = !this.history.canRedo();
  }

  /* ================================================================
     AI 操作
     ================================================================ */

  /**
   * AI 扩展节点（从右键菜单触发）
   */
  aiExpandNode(nodeId) {
    if (this.isUser) return;
    const node = this.nodes.find(n => n.id === nodeId);
    if (!node) return;
    this.ai.expandNode(node.name, node);
  }

  /* ================================================================
     保存 / 上线 / 更新
     ================================================================ */

  saveTree() {
    if (this.isUser) return;
    if (!this.sidebar.currentId) {
      showToast('请先创建一棵技能树', 'error');
      return;
    }
    this.sidebar._saveCurrentTree();
    this.sidebar.refreshStats();
    this._updatePublishButtons();
    showToast('✅ 已保存', 'success');
  }

  publishTree() {
    if (this.isUser) return;
    if (!this.sidebar.currentId) {
      showToast('请先创建一棵技能树', 'error');
      return;
    }
    if (this.nodes.length === 0) {
      showToast('技能树为空，无法上线', 'error');
      return;
    }
    if (this.hasDuplicateNames()) {
      showToast('存在同名节点，请先修改后再上线', 'error');
      return;
    }
    showConfirm('确定要上线当前技能树吗？上线后将在技能库中可见。', () => {
      this.sidebar.publishTree(this.sidebar.currentId);
      this._updatePublishButtons();
    });
  }

  updatePublishedTree() {
    if (this.isUser) return;
    if (!this.sidebar.currentId) return;
    const entry = this.sidebar.getCurrentEntry();
    if (!entry || !entry.publishedAt) {
      showToast('该技能树尚未上线，无法更新', 'error');
      return;
    }
    if (this.hasDuplicateNames()) {
      showToast('存在同名节点，请先修改后再更新', 'error');
      return;
    }
    showConfirm('确定要更新已上线的技能树吗？学习者进度将被保留。', () => {
      // toast 由 sidebar.publishTree 统一显示，这里不再叠加
      this.sidebar.publishTree(this.sidebar.currentId);
      this._updatePublishButtons();
    });
  }

  _updatePublishButtons() {
    if (this.isUser) return;
    const entry = this.sidebar.getCurrentEntry();
    const isPublished = entry && !!entry.publishedAt;
    document.getElementById('btn-publish').style.display = isPublished ? 'none' : '';
    document.getElementById('btn-update').disabled = !isPublished;
  }

  loadData(data) {
    // 清空撤销栈：加载新数据（切换树/初始化）是全新基线。
    // 注意不能在开头压栈——否则会把当前树的内容带进新树的撤销栈，
    // 切到树 B 后撤销会恢复树 A 内容，保存时把 A 写进 B，造成跨树数据污染。
    this.history.clear();
    this.nodes = (data.nodes || []).map(n => ({ ...n, _selected: false, _linking: false, _learningState: 'locked' }));
    this.connections = data.connections || [];
    this.treeName = data.name || '未命名知识树';
    this.treeDescription = data.description || '';
    this.selectedIds.clear();
    this.renderer.nodeEls.forEach(el => el.remove());
    this.renderer.nodeEls.clear();
    // 切换树后旧节点 ID 已失效，关闭详情面板避免残留上一个树的内容
    if (this.detailPanel) this.detailPanel.hideDetail();
    this.updateLearningStates();
    this.renderAll();
    this.checkDuplicateNames();
    this.interaction.fitToScreen(this.nodes);
    // 压入加载后的基线快照（栈底），保证加载后的第一次编辑可撤销
    this.saveHistory();
    this._updatePublishButtons();
  }

  /* ================================================================
     新建
     ================================================================ */

  newTree() {
    if (this.isUser) return;
    this.nodes = [];
    this.connections = [];
    this.selectedIds.clear();
    this.treeName = '未命名知识树';
    this.treeDescription = '';
    this.nodeCounter = 0;
    this.history.clear();
    this.renderer.nodeEls.forEach(el => el.remove());
    this.renderer.nodeEls.clear();
    this.detailPanel.hideDetail();
    this.renderAll();
    this.interaction.scale = 1;
    this.interaction.panX = 0;
    this.interaction.panY = 0;
    this.interaction.updateTransform();
    // 压入空树基线快照，保证新建后的第一次编辑可撤销
    this.saveHistory();
    this.updateUndoRedoButtons();
    showToast('已创建新的知识树');
  }

  /* ================================================================
     用户模式初始化
     ================================================================ */

  initUserMode() {
    var treeId = new URLSearchParams(location.search).get('treeId') || 'default';
    this._loadPublishedTree(treeId);
  }

  initPreviewMode() {
    var treeId = new URLSearchParams(location.search).get('treeId') || 'default';
    var self = this;
    this._loadPublishedTree(treeId);
    // 在 _loadPublishedTree 的回调中会调用 loadData，
    // 我们在这里用 setTimeout 等第一次渲染完成后强制设置 progress=100
    var checkInterval = setInterval(function() {
      if (self.nodes && self.nodes.length > 0) {
        self.nodes.forEach(function(n) { n.progress = 100; });
        self.updateLearningStates();
        self.renderAll();
        clearInterval(checkInterval);
      }
    }, 100);
    // 5秒后停止检查
    setTimeout(function() { clearInterval(checkInterval); }, 5000);
  }

  /** 用户模式 / 预览模式：加载已发布的技能树，优先从后端，降级到 localStorage */
  _loadPublishedTree(treeId) {
    var userId = new URLSearchParams(location.search).get('userId') || '';
    var learnerKey = treeId + (userId ? '_learner_' + userId : '_learner');
    var self = this;

    // 异步尝试从后端加载
    fetchPublishedSkillTree(treeId).then(function(serverTree) {
      if (serverTree && serverTree.published_data) {
        var pd = serverTree.published_data;
        // 合并 learner 进度
        var learner = pd.learner || {};
        (pd.nodes || []).forEach(function(n) {
          var p = learner[n.id];
          if (p !== undefined) n.progress = p;
        });
        // 缓存到 localStorage
        saveToStorage(treeId + '_published', pd);
        self.loadData(pd);
        return;
      }
      // 后端无数据，尝试 localStorage
      self._loadPublishedTreeFromLocal(treeId);
    }).catch(function() {
      // 后端不可用，降级到 localStorage
      self._loadPublishedTreeFromLocal(treeId);
    });
  }

  /** 从 localStorage 加载已发布的技能树（降级方案） */
  _loadPublishedTreeFromLocal(treeId) {
    var userId = new URLSearchParams(location.search).get('userId') || '';
    var learnerKey = treeId + (userId ? '_learner_' + userId : '_learner');
    // 1. 优先读发布版
    var published = loadFromStorage(treeId + '_published');
    if (published) {
      var learner = loadFromStorage(learnerKey, {});
      (published.nodes || []).forEach(function(n) {
        var p = learner[n.id];
        if (p !== undefined) n.progress = p;
      });
      this.loadData(published);
      return;
    }
    // 2. 回退到草稿版
    var draft = loadFromStorage('tree_' + treeId);
    if (draft) {
      this.loadData(draft);
      return;
    }
    showToast('未找到该技能树数据', 'error');
  }

  /** 用户模式：持久化学习进度 */
  _saveLearnerProgress() {
    var treeId = new URLSearchParams(location.search).get('treeId');
    if (!treeId) return;
    var userId = new URLSearchParams(location.search).get('userId') || '';
    var learnerKey = treeId + (userId ? '_learner_' + userId : '_learner');
    var learner = {};
    this.nodes.forEach(function(n) { learner[n.id] = n.progress; });
    saveToStorage(learnerKey, learner);

    // 同时写入发布版的 learner 字段
    var published = loadFromStorage(treeId + '_published');
    if (published) {
      published.learner = JSON.parse(JSON.stringify(learner));
      saveToStorage(treeId + '_published', published);
    }

    // 异步同步到后端
    saveLearnerProgressOnServer(treeId, learner);
  }

  /* ================================================================
     默认示例
     ================================================================ */

  initDefaultTree() {
    var self = this;

    // 先尝试从后端加载索引
    fetchSkillTreeIndex().then(function(serverTrees) {
      if (serverTrees && serverTrees.length > 0) {
        // 后端有数据，加载第一棵
        self.sidebar.trees = serverTrees;
        self.sidebar._saveIndex();
        self.sidebar.currentId = serverTrees[0].id;

        // 从后端加载草稿数据
        fetchSkillTreeDraft(serverTrees[0].id).then(function(draft) {
          if (draft && draft.data) {
            self.loadData(draft.data);
          } else {
            var data = self.sidebar.getCurrentTreeData();
            if (data) self.loadData(data);
          }
          self.sidebar._renderList();
          self._updatePublishButtons();
          self.interaction.fitToScreen(self.nodes);
        }).catch(function() {
          // 降级到 localStorage
          self._initDefaultTreeFromLocal();
        });
        return;
      }
      // 后端无数据，降级到 localStorage
      self._initDefaultTreeFromLocal();
    }).catch(function() {
      // 后端不可用，降级到 localStorage
      self._initDefaultTreeFromLocal();
    });
  }

  /** 从 localStorage 初始化默认树（降级方案） */
  _initDefaultTreeFromLocal() {
    const index = loadFromStorage('skill_tree_index', []);
    const validTrees = index.filter(t => {
      const data = loadFromStorage('tree_' + t.id);
      return data !== null;
    });

    if (validTrees.length > 0) {
      this.sidebar.trees = validTrees;
      this.sidebar._saveIndex();
      this.sidebar.currentId = validTrees[0].id;
      const data = this.sidebar.getCurrentTreeData();
      if (data) {
        this.loadData(data);
      }
      this.sidebar._renderList();
      this._updatePublishButtons();
      return;
    }

    // 无有效树，空编辑器启动
    this.sidebar.trees = [];
    this.sidebar._saveIndex();
    this.newTree();
    this.sidebar._renderList();
    this._updatePublishButtons();
  }
}

/* ================================================================
   启动（由 index.html 内联脚本调用 new App(SKILL_TREE_ROLE)）
   ================================================================ */
