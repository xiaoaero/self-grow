/* ================================================================
   ai-bridge.js — AI 集成模块
   通过后端代理调用 AI，支持 Tool Use
   ================================================================ */

class AIBridge {
  constructor() {
    this.serverUrl = 'http://localhost:3001';
    this.messages = [];   // 对话历史
    this.abortController = null;

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

    this.quickBtns.forEach(btn => {
      btn.addEventListener('click', () => {
        const prompt = btn.dataset.prompt;
        // 替换占位符
        this.inputEl.value = prompt.replace('"主题名"', '');
        this.sendMessage();
      });
    });
  }

  /**
   * 发送消息
   */
  async sendMessage() {
    const text = this.inputEl.value.trim();
    if (!text) return;

    this.inputEl.value = '';
    this.messages.push({ role: 'user', content: text });
    this.addMessage('user', text);
    this.setLoading(true);

    // 构建树状态
    const app = window.__app;
    const treeState = app ? {
      name: app.treeName || '未命名知识树',
      nodes: app.nodes.map(n => ({
        id: n.id,
        name: n.name,
        icon: n.icon,
        color: n.color,
        description: n.description,
        tags: n.tags,
        priority: n.priority,
        progress: n.progress
      })),
      connections: app.connections.map(c => ({
        from: (() => { const n = app.nodes.find(nn => nn.id === c.from); return n ? n.name : ''; })(),
        to: (() => { const n = app.nodes.find(nn => nn.id === c.to); return n ? n.name : ''; })(),
      })),
      selectedNodes: app.getSelectedNodes().map(n => n.name)
    } : null;

    try {
      this.abortController = new AbortController();
      const response = await fetch(`${this.serverUrl}/api/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          messages: this.messages.slice(-10), // 只发最近 10 条
          tree_state: treeState
        }),
        signal: this.abortController.signal
      });

      if (!response.ok) {
        const err = await response.text();
        throw new Error(`服务器错误 ${response.status}: ${err}`);
      }

      const data = await response.json();

      // 处理工具调用
      if (data.tool_calls && data.tool_calls.length > 0) {
        await this.executeToolCalls(data.tool_calls);
      }

      // 处理文本回复
      if (data.content) {
        this.messages.push({ role: 'assistant', content: data.content });
        this.addMessage('assistant', data.content);
      }

    } catch (err) {
      if (err.name === 'AbortError') {
        this.addMessage('system', '已取消');
      } else {
        this.addMessage('system', `❌ ${err.message}`);
      }
    } finally {
      this.setLoading(false);
      this.abortController = null;
    }
  }

  /**
   * 执行 AI 返回的工具调用
   */
  async executeToolCalls(toolCalls) {
    const app = window.__app;
    if (!app) {
      this.addMessage('system', '❌ 应用未初始化');
      return;
    }

    let resultMessages = '';

    for (const tc of toolCalls) {
      const { name, arguments: args } = tc;

      switch (name) {
        case 'get_tree_state': {
          // 不需要额外操作，前端已经发了 tree_state
          resultMessages += `树状态已提供。`;
          break;
        }

        case 'create_node': {
          app.saveHistory();
          // 找一个合适的位置
          const parentNode = args.parent_name
            ? app.nodes.find(n => n.name === args.parent_name)
            : null;

          // 计算位置
          let x = 200, y = 200;
          if (parentNode) {
            x = parentNode.x + 180;
            y = parentNode.y + (app.connections.filter(c => c.from === parentNode.id).length - 0) * 80 + 40;
          } else if (app.nodes.length > 0) {
            x = app.nodes[0].x;
            y = Math.max(...app.nodes.map(n => n.y)) + 100;
          }

          const node = app.createNode(x, y, {
            name: args.name || '新节点',
            icon: args.icon || '📚',
            color: args.color || '#2a2a4a',
            description: args.description || '',
            tags: args.tags || [],
            priority: args.priority || 'none',
          });

          if (parentNode) {
            app.addConnection(parentNode.id, node.id);
            app.renderConnections();
          }
          app.renderAll();
          resultMessages += `已创建节点"${node.name}"。`;
          break;
        }

        case 'update_node': {
          const node = app.nodes.find(n => n.name === args.name);
          if (node) {
            app.saveHistory();
            const changes = args.changes || {};
            Object.keys(changes).forEach(key => {
              if (key in node && key !== 'id') {
                node[key] = changes[key];
              }
            });
            app.renderNode(node);
            app.renderConnections();
            resultMessages += `已更新节点"${args.name}"。`;
          } else {
            resultMessages += `未找到节点"${args.name}"。`;
          }
          break;
        }

        case 'delete_node': {
          const node = app.nodes.find(n => n.name === args.name);
          if (node) {
            app.saveHistory();
            app.deleteNode(node.id);
            app.renderConnections();
            resultMessages += `已删除节点"${args.name}"。`;
          } else {
            resultMessages += `未找到节点"${args.name}"。`;
          }
          break;
        }

        case 'add_connection': {
          const fromNode = app.nodes.find(n => n.name === args.from);
          const toNode = app.nodes.find(n => n.name === args.to);
          if (fromNode && toNode) {
            app.saveHistory();
            app.addConnection(fromNode.id, toNode.id);
            app.renderConnections();
            resultMessages += `已建立连线：${args.from} → ${args.to}。`;
          } else {
            resultMessages += `未找到节点"${!fromNode ? args.from : args.to}"。`;
          }
          break;
        }

        case 'delete_connection': {
          const fromNode = app.nodes.find(n => n.name === args.from);
          const toNode = app.nodes.find(n => n.name === args.to);
          if (fromNode && toNode) {
            app.saveHistory();
            app.connections = app.connections.filter(
              c => !(c.from === fromNode.id && c.to === toNode.id)
            );
            app.renderConnections();
            resultMessages += `已删除连线：${args.from} → ${args.to}。`;
          } else {
            resultMessages += `未找到相关节点。`;
          }
          break;
        }

        case 'move_node': {
          const node = app.nodes.find(n => n.name === args.name);
          if (node) {
            app.saveHistory();
            node.x = args.x;
            node.y = args.y;
            const el = app.renderer.nodeEls.get(node.id);
            if (el) el.style.transform = `translate(${node.x}px, ${node.y}px)`;
            app.renderer.updateConnectionPaths(app.connections, app.nodes);
            resultMessages += `已移动节点"${args.name}"到 (${args.x}, ${args.y})。`;
          } else {
            resultMessages += `未找到节点"${args.name}"。`;
          }
          break;
        }

        case 'replace_tree': {
          app.replaceTree(args.nodes || [], []);
          resultMessages += `已生成知识树。`;
          break;
        }

        case 'send_message': {
          // AI 想要发消息给用户，在返回 data.content 中会包含
          break;
        }
      }
    }

    // 把执行结果发给后端，让 AI 做下一轮
    if (resultMessages) {
      this.messages.push({ role: 'assistant', content: resultMessages });
      this.addMessage('assistant', resultMessages);
    }
  }

  /* ---- UI ---- */

  addMessage(role, content) {
    const el = document.createElement('div');
    el.className = `ai-message ${role}`;
    el.textContent = content;
    this.messagesEl.appendChild(el);
    this.scrollToBottom();
  }

  setLoading(loading) {
    this.sendBtn.disabled = loading;
    if (loading) {
      const el = document.createElement('div');
      el.className = 'ai-message loading';
      el.id = 'ai-loading';
      this.messagesEl.appendChild(el);
      this.scrollToBottom();
    } else {
      const el = document.getElementById('ai-loading');
      if (el) el.remove();
    }
  }

  scrollToBottom() {
    const chat = document.getElementById('ai-chat');
    chat.scrollTop = chat.scrollHeight;
  }

  async expandNode(nodeName) {
    this.inputEl.value = `为节点"${nodeName}"扩展3-5个子节点`;
    this.sendMessage();
  }
}