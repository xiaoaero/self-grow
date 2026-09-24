/* ================================================================
   ai-bridge.js — AI 集成模块（LangGraph 版）
   对接后端 /api/skill-trees/{tree_id}/chat 端点：
   - 服务端维护会话（checkpointer），前端只持有 thread_id
   - 后端工具按节点 ID 操作内存中的树，返回完整 tree + 执行日志
   - 危险操作（替换整棵树/级联删除）走 pending_confirmation 确认卡片
   ================================================================ */

/** 每棵树最多留多少条对话记录（防止 localStorage 无限涨） */
const AI_HISTORY_MAX = 100;

class AIBridge {
  constructor() {
    this.serverUrl = window.__SELF_GROW_API_BASE__ || window.API_BASE || 'http://localhost:3001';

    // 会话状态
    this.threadId = null;      // LangGraph thread_id，服务端持久化
    this.isLoading = false;

    // 对话记录持久化（按树存 localStorage，重进页面能接着看）
    // ⚠️ 后端 checkpointer 是**内存**的（MemorySaver）→ 后端一重启服务端上下文就没了；
    //    所以「重进后还有原来的记录」只能靠**前端**存。thread_id 也一起存，
    //    没失效就接着用（AI 还能记得上下文），失效了会自动开新一轮。
    this._treeId = null;
    this._history = [];        // [{role, content}]

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

    const path = `/api/skill-trees/${app.sidebar.currentId}/chat`;
    const body = {
      tree: this.buildTreePayload(app),
      message: text,
      selected_node_ids: [...app.selectedIds],
      thread_id: this.threadId,
    };
    try {
      let data;
      try {
        data = await this._requestStream(path, body);
      } catch (err) {
        // 「技能树不存在」= 这棵树只存在于浏览器，服务器上没有 → 先补传再重试一次
        const verdict = await this._recoverMissingTree(err);
        if (verdict === 'passthrough') throw err;
        if (verdict === 'reported') return;
        data = await this._requestStream(path, body);
      }
      this.threadId = data.thread_id;
      this._persist();          // thread_id 落盘：重进页面还能接着这一轮
      this._handleResponse(data);
    } catch (err) {
      // 后端 checkpointer 是内存的 → 重启后旧 thread_id 会失效。
      // 这时不该继续报错，直接开新一轮（历史消息仍留在面板上）。
      if (/404|会话|thread/i.test(err.message)) {
        this.threadId = null;
        this._persist();
        this.addMessage('system',
          '⚠️ AI 会话已失效（后端可能重启），已开启新会话。上面的历史仍在，但 AI 不再记得。');
      } else {
        this.addMessage('system', `❌ ${err.message}`);
      }
    } finally {
      this.setLoading(false);
    }
  }

  /**
   * 「技能树不存在」（404）时自救
   *
   * ⚠️ 这个提示来自后端 `routers/skill_tree_ai.py` 的归属校验 ——
   * AI 编辑要求 `tree_id + user_id` 在库里有记录。而技能树的同步曾经是
   * "发出去就不管"的后台调用，失败也没人看，于是会出现
   * 「界面上有树、服务器上一行都没有」的状态：AI 每次都回这句，
   * 用户看着莫名其妙（2026-09-23 用户就是这么被卡住的）。
   *
   * @returns {Promise<'retry'|'reported'|'passthrough'>}
   *   retry      = 已补传到服务器，可以原样重试
   *   reported   = 已给出人话解释，**不要再显示后端原始 detail**
   *   passthrough= 与这个错误无关，交给上层照常显示
   */
  async _recoverMissingTree(err) {
    const msg = (err && err.message) || '';
    if (!/技能树不存在/.test(msg)) return 'passthrough';

    const app = window.__app;
    if (!app || typeof app.syncLocalTreesToServer !== 'function') return 'passthrough';

    this.setLoadingTip('这棵技能树还没同步到服务器，正在补传…');
    const r = await app.syncLocalTreesToServer();
    if (r && r.synced > 0) {
      this.addMessage('system', 'ℹ️ 这棵技能树原本只存在浏览器里，已同步到服务器，正在重试…');
      return 'retry';
    }
    // 说不清楚"卡在哪"的提示等于没说 —— 按实际原因给话（2026-09-24 补）
    switch (r && r.reason) {
      case 'backend-unreachable':
        this.addMessage('system long',
          '❌ 连不上后端接口，所以既没法把树传上去、也没法确认它是否存在。\n' +
          '页面地址与后端地址可能不是同一个（技能树列表用的是相对路径 /api/…，' +
          '而这句话是打后端绝对地址过来的）。请用后端同一个地址打开本页面后重试。');
        break;
      case 'readonly':
        this.addMessage('system', '当前是**查看模式**（URL 上带 role=user/viewer），不能编辑，也无法同步。');
        break;
      case 'nothing-missing':
        this.addMessage('system long',
          '⚠️ 本地这些树在服务器上其实都查得到，但服务端仍报「技能树不存在」——\n' +
          '通常是**页面上用的 id 与服务端要的不是同一个**（比如用了数据库自增主键而不是 tree_id）。\n' +
          '请硬刷新页面（Ctrl+Shift+R）后重试；仍不行就把这行消息发我。');
        break;
      case 'no-local-trees':
        this.addMessage('system long',
          '❌ 服务器上没有这棵树，浏览器里也没有它的本地数据（可能是换了浏览器/清了缓存）。\n' +
          '请回到技能库重新打开，或新建一棵技能树。');
        break;
      default:
        this.addMessage('system', '❌ 技能树只存在浏览器里，补传服务器失败。请刷新页面后重试。');
    }
    return 'reported';
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
      // checkpointer 是内存存储，后端重启后 thread_id 会失效。
      // ⚠️ 只丢 thread，**不清历史消息** —— 会话没了不等于对话记录该消失
      //    （以前这里调 resetSession()，会把面板整个清空）。
      if (/404|会话|thread/i.test(err.message)) {
        this.threadId = null;
        this._persist();
        this.addMessage('system',
          '⚠️ AI 会话已失效（后端可能重启），已开启新会话。上面的历史仍在，但 AI 不再记得。');
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
    // ⚠️ 与 `utils.js::apiBase()` 用**同一个**基址解析顺序。
    //    以前这里自己拼了一套（丢了 `Auth.API_BASE` 这一档），
    //    结果同一页面里 AI 走绝对地址、技能树列表走相对路径 ——
    //    不同源打开时只有 AI 能连上后端，症状是"AI 一直说技能树不存在"。
    const base = (typeof apiBase === 'function') ? apiBase() : this.serverUrl;
    return streamSSE(
      `${base}${path}?user_id=${userId}`,
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

    // 防连点：点击后立刻把两个按钮禁掉并移除卡片。
    // `el.isConnected` 是第二道保险 —— 万一同一帧内派发了两次 click，
    // 第二次会因为元素已脱离文档而直接返回
    const decide = (confirmed, text, message) => {
      if (el.__decided || !el.isConnected) return;
      el.__decided = true;
      el.querySelectorAll('button').forEach((b) => { b.disabled = true; });
      el.remove();
      this.addMessage('user', text);
      this.resume(confirmed, message);
    };

    el.querySelector('.ok').addEventListener('click', () => decide(true, '确认执行', ''));
    el.querySelector('.cancel').addEventListener('click',
      () => decide(false, '取消该操作', '用户取消了该操作，请不要执行它'));
  }

  /* ================================================================
     会话管理
     ================================================================ */

  /* ---- 存储键 ---- */

  _msgsKey(treeId) { return 'skilltree_ai_msgs_' + treeId; }

  _threadKey(treeId) { return 'skilltree_ai_thread_' + treeId; }

  /* ---- 切到某棵树：恢复它的对话记录 ---- */

  /**
   * 跟着当前树走（树没变就是空操作）
   *
   * 由 `app.loadData()` 末尾调用 —— 切树 / 新建 / 初始加载都会走到那里，
   * 所以不用在每个入口分别记得调一次。
   */
  syncTree(treeId) {
    if (this._treeId === (treeId || null)) return;
    if (!treeId) { this.useTree(null); return; }
    this.useTree(treeId);
  }

  /**
   * 载入某棵树的会话（历史消息 + thread_id）
   *
   * ⚠️ 以前切树是 `resetSession()`（清空），用户切走再切回来对话就没了。
   *    现在每棵树的对话各自存一份，切回来原样恢复。
   */
  useTree(treeId) {
    this._treeId = treeId || null;
    this._history = [];
    this.threadId = null;
    if (this.messagesEl) this.messagesEl.innerHTML = '';

    if (this._treeId) {
      this.threadId = loadFromStorage(this._threadKey(this._treeId), null) || null;
      const hist = loadFromStorage(this._msgsKey(this._treeId), []);
      (Array.isArray(hist) ? hist : []).forEach(m => {
        if (m && typeof m.content === 'string') {
          this._render(m.role, m.content);
          this._history.push({ role: m.role, content: m.content });
        }
      });
    }
    this._syncClearButton();
    this.scrollToBottom();
  }

  /** 删掉某棵树的对话记录（删除树时调用，别把垃圾留在 localStorage 里） */
  forgetTree(treeId) {
    if (!treeId) return;
    try {
      localStorage.removeItem(this._msgsKey(treeId));
      localStorage.removeItem(this._threadKey(treeId));
    } catch (e) { /* 隐私模式下 localStorage 可能不可用，忽略 */ }
    if (this._treeId === treeId) this.useTree(null);
  }

  _persist() {
    if (!this._treeId) return;
    try {
      saveToStorage(this._msgsKey(this._treeId), this._history.slice(-AI_HISTORY_MAX));
      if (this.threadId) saveToStorage(this._threadKey(this._treeId), this.threadId);
    } catch (e) { /* 存不下就算了，不影响使用 */ }
  }

  /** 清空当前这棵树的会话（「清空对话」按钮） */
  resetSession() {
    this.threadId = null;
    this._history = [];
    if (this._treeId) {
      try {
        localStorage.removeItem(this._msgsKey(this._treeId));
        localStorage.removeItem(this._threadKey(this._treeId));
      } catch (e) { /* 同上 */ }
    }
    if (this.messagesEl) this.messagesEl.innerHTML = '';
    this._syncClearButton();
  }

  /* ================================================================
     UI
     ================================================================ */

  addMessage(role, content) {
    this._render(role, content);
    // 记进历史并落盘（重进页面能恢复）
    this._history.push({ role, content });
    if (this._history.length > AI_HISTORY_MAX) {
      this._history = this._history.slice(-AI_HISTORY_MAX);
    }
    this._persist();
    this._syncClearButton();
  }

  /** 只渲染，不记历史（恢复历史记录时用，避免重复写盘） */
  _render(role, content) {
    const el = document.createElement('div');
    el.className = `ai-message ${role}`;
    el.textContent = content;
    this.messagesEl.appendChild(el);
    this.scrollToBottom();
  }

  /** 让「清空对话」按钮跟着消息数变可用/禁用 */
  _syncClearButton() {
    const app = window.__app;
    if (app && typeof app.refreshAiClearButton === 'function') app.refreshAiClearButton();
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
