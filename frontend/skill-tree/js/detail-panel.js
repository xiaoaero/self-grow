/* ================================================================
   detail-panel.js — 右侧详情面板
   ================================================================ */

class DetailPanel {
  constructor(app) {
    this.app = app;
    this.currentNodeId = null;
    this._bindEvents();
  }

  /** 显示节点详情 */
  showNodeDetail(nodeId) {
    const node = this.app.nodes.find(n => n.id === nodeId);
    if (!node) return;

    this.currentNodeId = nodeId;

    const panel = document.getElementById('detail-panel');
    const content = document.getElementById('detail-content');
    const title = document.getElementById('detail-title');

    panel.classList.remove('collapsed');
    title.textContent = '节点详情';

    // 学习状态
    const isLocked = node._learningState === 'locked';
    const isAvailable = node._learningState === 'available';
    const isLearning = node._learningState === 'learning';
    const isCompleted = node._learningState === 'completed';

    const stateLabel = this._getStateLabel(node);
    const stateClass = isCompleted ? 'status-completed' : (isLearning ? 'status-learning' : (isAvailable ? 'status-available' : 'status-locked'));

    // 前置条件
    const prereqs = this._getPrerequisites(nodeId);
    const prereqsMet = prereqs.length === 0 || prereqs.every(p => p.completed);

    content.innerHTML = `
      <div class="detail-node-header">
        <div class="detail-node-icon" style="background:${node.color};border-color:${node.borderColor}">
          ${node.icon}
        </div>
        <div class="detail-node-info">
          <div class="detail-node-name">${this._escapeHtml(node.name)}</div>
          <span class="detail-node-status ${stateClass}">${stateLabel}</span>
        </div>
      </div>

      ${node.description ? `
        <div class="detail-section">
          <div class="detail-section-title">描述</div>
          <div class="detail-description">${this._escapeHtml(node.description)}</div>
        </div>` : ''}

      ${node.tags && node.tags.length > 0 ? `
        <div class="detail-section">
          <div class="detail-section-title">标签</div>
          <div class="detail-tags">
            ${node.tags.map(t => `<span class="detail-tag">${this._escapeHtml(t)}</span>`).join('')}
          </div>
        </div>` : ''}

      <div class="detail-section">
        <div class="detail-section-title">优先级</div>
        <div class="detail-priority">${this._getPriorityLabel(node.priority)}</div>
      </div>

      ${prereqs.length > 0 ? `
        <div class="detail-section">
          <div class="detail-section-title">前置条件</div>
          <div class="prerequisite-list">
            ${prereqs.map(p => `
              <div class="prerequisite-item ${p.completed ? 'prereq-met' : 'prereq-unmet'}" data-node-id="${p.id}" style="cursor:pointer;">
                <span class="prereq-icon">${p.completed ? '✅' : '❌'}</span>
                <span class="prereq-name">${this._escapeHtml(p.name)}</span>
              </div>`).join('')}
          </div>
        </div>` : ''}

      <div class="detail-actions">
        ${isCompleted ? `
          <button class="detail-btn btn-mark-complete" disabled>✓ 已完成</button>` :
         isLearning ? `
          <button class="detail-btn btn-learning" disabled>🔄 学习中</button>
          <button class="detail-btn btn-mark-complete"
                  onclick="window.__app.markNodeCompleted('${nodeId}')">
            ✅ 标记为已学
          </button>` : `
          <button class="detail-btn btn-learn" ${isAvailable ? '' : 'disabled'}
                  onclick="window.__app.markNodeAsLearning('${nodeId}')">
            📖 开始学习
          </button>
          <button class="detail-btn btn-mark-complete" ${isAvailable ? '' : 'disabled'}
                  onclick="window.__app.markNodeCompleted('${nodeId}')">
            ✅ 标记为已学
          </button>
          ${!isAvailable && !isCompleted ? '<div class="detail-btn-hint">⛔ 需先完成所有前置条件</div>' : ''}`}
      </div>`;
  }

  /** 隐藏详情面板 */
  hideDetail() {
    this.currentNodeId = null;
    const panel = document.getElementById('detail-panel');
    panel.classList.add('collapsed');
    document.getElementById('detail-title').textContent = '节点详情';
    document.getElementById('detail-content').innerHTML = '<div class="detail-empty">点击节点查看详情</div>';
  }

  /** 刷新当前显示的详情 */
  refreshCurrent() {
    if (this.currentNodeId) {
      this.showNodeDetail(this.currentNodeId);
    }
  }

  /* ---- 前置条件 ---- */

  _getPrerequisites(nodeId) {
    // 只获取最近一级的直接父节点
    const parents = this.app.connections
      .filter(c => c.to === nodeId)
      .map(c => c.from);

    return parents.map(parentId => {
      const parentNode = this.app.nodes.find(n => n.id === parentId);
      return parentNode ? {
        id: parentId,
        name: parentNode.name,
        completed: parentNode.progress === 100
      } : null;
    }).filter(Boolean);
  }

  _arePrerequisitesMet(nodeId) {
    const prereqs = this._getPrerequisites(nodeId);
    return prereqs.length === 0 || prereqs.every(p => p.completed);
  }

  /* ---- 工具 ---- */

  _getStateLabel(node) {
    switch (node._learningState) {
      case 'completed': return '✅ 已学习';
      case 'learning': return '🔄 学习中';
      case 'available': return '🔵 可学习';
      default: return '⛔ 未解锁';
    }
  }

  _getPriorityLabel(priority) {
    switch (priority) {
      case 'high': return '🔴 高';
      case 'medium': return '🟡 中';
      case 'low': return '🟢 低';
      default: return '—';
    }
  }

  _escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }

  _bindEvents() {
    document.getElementById('btn-close-detail').addEventListener('click', () => {
      this.hideDetail();
    });

    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        this.hideDetail();
      }
    });

    // 点击前置节点跳转
    document.getElementById('detail-content').addEventListener('click', (e) => {
      const prereqItem = e.target.closest('.prerequisite-item');
      if (prereqItem) {
        const nodeId = prereqItem.dataset.nodeId;
        if (nodeId) {
          this.app.jumpToNode(nodeId);
        }
      }
    });
  }
}