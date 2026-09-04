/* ================================================================
   ai-bridge.js — AI 集成模块（LangGraph 版）
   对接后端 /api/skill-trees/{tree_id}/chat 端点：
   - 服务端维护会话（checkpointer），前端只持有 thread_id
   - 后端工具按节点 ID 操作内存中的树，返回完整 tree + 执行日志
   - 危险操作（替换整棵树/级联删除）走 pending_confirmation 确认卡片
   ================================================================ */

class AIBridge {
  constructor() {
    this.serverUrl = window.__SELF_GROW_API_BASE__ || window.API_BASE || 'http://localhost:3001';

    // 会话状态
    this.threadId = null;      // LangGraph thread_id，服务端持久化
    this.isLoading = false;

    // UI
    this.panel = document.getElementById('ai-panel');
    this.messagesEl = document.getElementById('ai-messages');
    this.inputEl = document.getElementById('ai-input');
    this.sendBtn = document.getElementById('btn-ai-send');
    this.quickBtns = document.querySelectorAll('.ai-quick-btn');

    this.bindUI();
  }

  bindUI() {
    this.sendBtn.addEventListener('click', () => this.sendMessage());
    this.inputEl.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        this.sendMessage();
      }
    });

    // 快捷按钮：data-fill 模式的只填充不发送（需要用户补充主题），
    // 其余直接发送
    this.quickBtns.forEach(btn => {
      btn.addEventListener('click', () => {
        const prompt = btn.dataset.prompt;
        if (btn.dataset.fill) {
          this.inputEl.value = prompt;
          this.inputEl.focus();
        } else {
          this.inputEl.value = prompt;
          this.sendMessage();
        }
      });
    });
  }

  /* ================================================================
     发送消息
     ================================================================ */

  async sendMessage() {
    const text = this.inputEl.value.trim();
    if (!text || this.isLoading) return;

    const app = window.__app;
    if (!app || !app.sidebar.currentId) {
      showToast('请先创建一棵技能树', 'error');
      return;
    }

    this.inputEl.value = '';
    this.addMessage('user', text);
    this.setLoading(true);

    try {
      const data = await this._request(
        `/api/skill-trees/${app.sidebar.currentId}/chat`,
        {
          tree: this.buildTreePayload(app),
          message: text,
          selected_node_ids: [...app.selectedIds],
          thread_id: this.threadId,
        }
      );
      this.threadId = data.thread_id;
      this._handleResponse(data);
    } catch (err) {
      this.addMessage('system', `❌ ${err.message}`);
    } finally {
      this.setLoading(false);
    }
  }

  /**
   * 恢复会话：回答确认卡片（确认/取消）或补充信息
   */
  async resume(confirm, message = '') {
    if (this.isLoading || !this.threadId) return;
    const app = window.__app;

    this.setLoading(true);
    try {
      const data = await this._request(
        `/api/skill-trees/${app.sidebar.currentId}/chat/resume`,
        {
          thread_id: this.threadId,
          message: message,
          confirm: confirm,
        }
      );
      this._handleResponse(data);
    } catch (err) {
      this.addMessage('system', `❌ ${err.message}`);
    } finally {
      this.setLoading(false);
    }
  }

  /** 统一请求封装 */
  async _request(path, body) {
    const userId = getCurrentUserId() || 1;
    const resp = await fetch(`${this.serverUrl}${path}?user_id=${userId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!resp.ok) {
      let detail = `HTTP ${resp.status}`;
      try {
        const err = await resp.json();
        if (err.detail) detail = err.detail;
      } catch (e) { /* 忽略解析失败 */ }
      throw new Error(detail);
    }
    return resp.json();
  }

  /* ================================================================
     响应处理
     ================================================================ */

  _handleResponse(data) {
    // 1. AI 回复
    if (data.reply) {
      this.addMessage('assistant', data.reply);
    }

    // 2. 工具执行日志
    if (data.executed_tools && data.executed_tools.length > 0) {
      const summary = data.executed_tools
        .map(t => `${t.success ? '✅' : '❌'} ${t.message || t.tool}`)
        .join('\n');
      this.addMessage('assistant', `🔧 已执行操作:\n${summary}`);
    }

    // 3. 应用树变更（有工具实际修改过树才应用）
    const app = window.__app;
    const touched = (data.executed_tools || []).some(
      t => t.success && t.status !== 'needs_confirmation'
    );
    if (app && touched && data.tree && Array.isArray(data.tree.nodes)) {
      this._applyTree(app, data.tree);
    }

    // 4. 待确认操作 → 渲染确认卡片
    if (data.pending_confirmation) {
      this._renderConfirmCard(data.pending_confirmation);
    }
  }

  /**
   * 将后端返回的树应用到画布。
   * 注意：不走 loadData()（它会清空撤销栈）——这里手动
   * push「改前快照 + 改后快照」，保证 AI 的修改可以用 Ctrl+Z 撤销。
   */
  _applyTree(app, tree) {
    // 改前快照
    app.saveHistory();

    app.nodes = (tree.nodes || []).map(n => ({
      ...n,
      _selected: false, _linking: false, _learningState: 'locked'
    }));
    app.connections = tree.connections || [];
    app.treeName = tree.name || app.treeName;
    app.selectedIds.clear();
    app.renderer.nodeEls.forEach(el => el.remove());
    app.renderer.nodeEls.clear();
    app.updateLearningStates();
    app.renderAll();
    app.checkDuplicateNames();
    app.sidebar.refreshStats();
    app._updatePublishButtons();

    // 改后快照
    app.saveHistory();
    showToast('🎨 AI 已更新技能树');
  }

  /* ================================================================
     构建请求负载
     ================================================================ */

  buildTreePayload(app) {
    return {
      name: app.treeName || '未命名知识树',
      description: app.treeDescription || '',
      nodes: app.nodes.map(n => ({
        id: n.id,
        name: n.name,
        x: n.x,
        y: n.y,
        size: n.size || 70,
        shape: n.shape || 'round',
        icon: n.icon || '📚',
        color: n.color || '#2a2a4a',
        borderColor: n.borderColor || '#444466',
        description: n.description || '',
        tags: n.tags || [],
        priority: n.priority || 'none',
        progress: n.progress || 0,
      })),
      connections: app.connections.map(c => ({
        id: c.id,
        from: c.from,
        to: c.to,
      })),
    };
  }

  /* ================================================================
     确认卡片（危险操作二次确认）
     ================================================================ */

  _renderConfirmCard(pending) {
    const el = document.createElement('div');
    el.className = 'ai-message system ai-confirm-card';
    el.innerHTML = `
      <div class="ai-confirm-text">⚠️ ${this._escapeHtml(pending.message || '请确认此操作')}</div>
      <div class="ai-confirm-actions">
        <button class="ai-confirm-btn ok">确认执行</button>
        <button class="ai-confirm-btn cancel">取消</button>
      </div>`;
    this.messagesEl.appendChild(el);
    this.scrollToBottom();

    const remove = () => el.remove();
    el.querySelector('.ok').addEventListener('click', () => {
      remove();
      this.addMessage('user', '确认执行');
      this.resume(true);
    });
    el.querySelector('.cancel').addEventListener('click', () => {
      remove();
      this.addMessage('user', '取消该操作');
      this.resume(false, '用户取消了该操作，请不要执行它');
    });
  }

  /* ================================================================
     会话管理
     ================================================================ */

  /** 重置会话（切换树/新建树时调用）：丢弃 thread_id 并清空消息区 */
  resetSession() {
    this.threadId = null;
    if (this.messagesEl) this.messagesEl.innerHTML = '';
  }

  /* ================================================================
     UI
     ================================================================ */

  addMessage(role, content) {
    const el = document.createElement('div');
    el.className = `ai-message ${role}`;
    el.textContent = content;
    this.messagesEl.appendChild(el);
    this.scrollToBottom();
  }

  setLoading(loading) {
    this.isLoading = loading;
    this.sendBtn.disabled = loading;
    const old = document.getElementById('ai-loading');
    if (old) old.remove();
    if (loading) {
      const el = document.createElement('div');
      el.className = 'ai-message loading';
      el.id = 'ai-loading';
      this.messagesEl.appendChild(el);
      this.scrollToBottom();
    }
  }

  scrollToBottom() {
    const chat = document.getElementById('ai-chat');
    chat.scrollTop = chat.scrollHeight;
  }

  /**
   * 从右键菜单触发的 AI 扩展：自动打开面板并发送
   */
  async expandNode(nodeName) {
    // 确保面板可见
    const panel = document.getElementById('ai-panel');
    const toggleBtn = document.getElementById('btn-toggle-ai');
    if (panel && panel.classList.contains('panel-closed')) {
      panel.classList.remove('panel-closed');
      if (toggleBtn) toggleBtn.classList.add('active');
    }
    this.inputEl.value = `请为节点「${nodeName}」扩展3-5个子节点`;
    await this.sendMessage();
  }

  _escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str == null ? '' : String(str);
    return div.innerHTML;
  }
}
