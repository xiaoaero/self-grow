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
    this.setLoading(true, '正在分析…');

    try {
      const data = await this._requestStream(
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

    this.setLoading(true, '正在处理…');
    try {
      const data = await this._requestStream(
        `/api/skill-trees/${app.sidebar.currentId}/chat/resume`,
        {
          thread_id: this.threadId,
          message: message,
          confirm: confirm,
          // 带上当前树，避免 AI 基于 checkpoint 里的旧快照继续编辑
          tree: this.buildTreePayload(app),
        }
      );
      this._handleResponse(data);
    } catch (err) {
      // checkpointer 是内存存储，后端重启后 thread_id 会失效
      if (/404|会话|thread/i.test(err.message)) {
        this.resetSession();
        this.addMessage('system', '⚠️ AI 会话已失效（后端可能重启），已自动重置，请重新提问');
      } else {
        this.addMessage('system', `❌ ${err.message}`);
      }
    } finally {
      this.setLoading(false);
    }
  }

  /**
   * 统一请求封装（**流式**）
   *
   * 后端 `/chat` 与 `/chat/resume` 已是 SSE：会推阶段事件
   * （第 N 轮推理 / 正在执行哪个工具 / 需要确认），最后用 done 送完整结果。
   * done 的字段与改造前完全一致，所以 `_handleResponse(data)` 不用改。
   *
   * 用共享的 `js/sse.js`（与主应用同一份实现）——
   * 它走 `fetch` + `resp.body.getReader()`，因此能被 `js/auth.js` 的
   * fetch 包装自动带上 `Authorization`（原生 EventSource 做不到这点）。
   *
   * @param {string} path
   * @param {object} body
   * @returns {Promise<object>} done 事件的完整内容
   */
  async _requestStream(path, body) {
    const userId = getCurrentUserId() || 1;
    return streamSSE(
      `${this.serverUrl}${path}?user_id=${userId}`,
      body,
      {
        onStage: (p) => { if (p.label) this.setLoadingTip(p.label); },
      }
    );
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

    // 3. 应用树变更
    //    以 diffs 为准：只有真正产生了变更记录才应用。
    //    原来用 executed_tools 判断，send_reply 之类也会命中，
    //    导致纯聊天时也会刷一遍画布并弹"AI 已更新技能树"
    const app = window.__app;
    const changed = (data.diffs || []).length > 0;
    if (app && changed && data.tree && Array.isArray(data.tree.nodes)) {
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
    // 立即落盘（localStorage + 后端草稿），否则 AI 的改动要等用户手动点保存
    app.sidebar._saveCurrentTree();

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
      // 带上样式字段，否则服务端重建连线后会丢掉颜色/虚线设置
      connections: app.connections.map(c => ({
        id: c.id,
        from: c.from,
        to: c.to,
        color: c.color || '#666680',
        dashed: !!c.dashed,
        showArrow: c.showArrow !== false,
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

  setLoading(loading, tip) {
    this.isLoading = loading;
    this.sendBtn.disabled = loading;
    const old = document.getElementById('ai-loading');
    if (old) old.remove();
    if (loading) {
      const el = document.createElement('div');
      el.className = 'ai-message loading';
      el.id = 'ai-loading';
      if (tip) {
        const span = document.createElement('span');
        span.className = 'ai-loading__tip';
        span.textContent = tip;
        el.appendChild(span);
      }
      this.messagesEl.appendChild(el);
      this.scrollToBottom();
    }
  }

  /** 更新加载中的提示文案（由流式的阶段事件驱动） */
  setLoadingTip(tip) {
    const el = document.getElementById('ai-loading');
    if (!el) return;
    let span = el.querySelector('.ai-loading__tip');
    if (!span) {
      span = document.createElement('span');
      span.className = 'ai-loading__tip';
      el.insertBefore(span, el.firstChild);
    }
    if (span.textContent !== tip) {
      span.textContent = tip;
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
