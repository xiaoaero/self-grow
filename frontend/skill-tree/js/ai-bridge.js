/* ================================================================
   ai-bridge.js — AI 集成模块
   通过后端代理调用 AI，支持 Tool Use
   ================================================================ */

class AIBridge {
  constructor() {
    this.serverUrl = window.API_BASE || 'http://localhost:3001';
    this.messages = [];   // 对话历史
    this.abortController = null;

    // UI
    this.panel = document.getElementById('ai-panel');
    this.messagesEl = document.getElementById('ai-messages');
    this.inputEl = document.getElementById('ai-input');
    this.sendBtn = document.getElementById('btn-ai-send');
    this.quickBtns = document.querySelectorAll('.ai-quick-btn');

    // 最大工具调用轮次（防止无限循环）
    this.maxToolRounds = 5;

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

    try {
      await this.sendToAI(0);
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
   * 递归调用 AI，支持多轮 Tool Use 循环
   * @param {number} round 当前轮次
   */
  async sendToAI(round) {
    if (round >= this.maxToolRounds) {
      this.addMessage('system', `⚠️ AI 已达到最大工具调用轮次 (${this.maxToolRounds})`);
      return;
    }

    this.abortController = new AbortController();

    const response = await fetch(`${this.serverUrl}/api/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        messages: this.messages.slice(-20), // 只发最近 20 条
        tree_state: this.buildTreeState()
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
      // 执行工具并收集结果
      const toolResults = await this.executeToolCalls(data.tool_calls);

      // 将工具调用和结果加入对话历史（让 AI 知道发生了什么）
      for (const tc of data.tool_calls) {
        this.messages.push({
          role: 'assistant',
          content: null,
          tool_calls: [{
            id: tc.id,
            type: 'function',
            function: {
              name: tc.name,
              arguments: JSON.stringify(tc.arguments)
            }
          }]
        });
        // 工具执行结果
        const result = toolResults.find(r => r.id === tc.id);
        this.messages.push({
          role: 'tool',
          tool_call_id: tc.id,
          content: result ? result.content : '执行成功'
        });
      }

      // 继续下一轮 AI 推理（AI 根据工具结果决定下一步操作还是回复用户）
      await this.sendToAI(round + 1);
    }

    // 处理文本回复（可能在有 tool_calls 时也有 content，也可能纯文本回复）
    if (data.content) {
      this.messages.push({ role: 'assistant', content: data.content });
      this.addMessage('assistant', data.content);
    }
  }

  /**
   * 构建当前树状态用于发送给 AI
   */
  buildTreeState() {
    const app = window.__app;
    if (!app) return null;
    return {
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
    };
  }

  /**
   * 执行 AI 返回的工具调用
   * @returns {Array<{id: string, content: string}>} 工具执行结果列表
   */
  async executeToolCalls(toolCalls) {
    const app = window.__app;
    if (!app) {
      this.addMessage('system', '❌ 应用未初始化');
      return toolCalls.map(tc => ({ id: tc.id, content: '应用未初始化' }));
    }

    const results = [];

    for (const tc of toolCalls) {
      const { name, arguments: args } = tc;
      let resultContent = '';

      switch (name) {
        case 'get_tree_state': {
          resultContent = '树状态已提供。';
          break;
        }

        case 'create_node': {
          app.saveHistory();
          const parentNode = args.parent_name
            ? app.nodes.find(n => n.name === args.parent_name)
            : null;

          let x = 200, y = 200;
          if (parentNode) {
            const parentCenter = app.renderer.getNodeCenter(parentNode);
            x = parentCenter.cx + 180;
            y = parentCenter.cy + (app.connections.filter(c => c.from === parentNode.id).length - 0) * 80 + 40;
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
          resultContent = `已创建节点"${node.name}"，ID: ${node.id}。`;
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
            resultContent = `已更新节点"${args.name}"。`;
          } else {
            resultContent = `未找到节点"${args.name}"。当前节点列表: ${app.nodes.map(n => n.name).join(', ')}`;
          }
          break;
        }

        case 'delete_node': {
          const node = app.nodes.find(n => n.name === args.name);
          if (node) {
            app.saveHistory();
            app.deleteNode(node.id);
            app.renderConnections();
            resultContent = `已删除节点"${args.name}"。`;
          } else {
            resultContent = `未找到节点"${args.name}"。当前节点列表: ${app.nodes.map(n => n.name).join(', ')}`;
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
            resultContent = `已建立连线：${args.from} → ${args.to}。`;
          } else {
            const missing = !fromNode ? args.from : args.to;
            resultContent = `未找到节点"${missing}"。当前节点列表: ${app.nodes.map(n => n.name).join(', ')}`;
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
            resultContent = `已删除连线：${args.from} → ${args.to}。`;
          } else {
            resultContent = `未找到相关节点。`;
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
            resultContent = `已移动节点"${args.name}"到 (${args.x}, ${args.y})。`;
          } else {
            resultContent = `未找到节点"${args.name}"。`;
          }
          break;
        }

        case 'replace_tree': {
          app.replaceTree(args.nodes || [], []);
          resultContent = `已生成知识树，共 ${(args.nodes || []).length} 个节点。`;
          break;
        }

        case 'send_message': {
          // AI 想发消息给用户，在 data.content 中会包含
          resultContent = '消息已展示给用户。';
          break;
        }

        default: {
          resultContent = `未知工具: ${name}`;
        }
      }

      results.push({ id: tc.id, content: resultContent });
    }

    // 将工具执行结果展示给用户
    const summary = results.map(r => r.content).join('\n');
    this.addMessage('assistant', `🔧 已执行操作:\n${summary}`);

    return results;
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