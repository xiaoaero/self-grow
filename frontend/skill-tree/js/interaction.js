/* ================================================================
   interaction.js — 交互系统
   ================================================================ */

class InteractionManager {
  constructor(app) {
    this.app = app;
    this.container = document.getElementById('canvas-container');
    this.treeCanvas = document.getElementById('tree-canvas');

    // 画布变换
    this.scale = 1;
    this.panX = 0;
    this.panY = 0;
    this.minScale = 0.2;
    this.maxScale = 3;
    this.scaleStep = 0.1;

    // 拖拽
    this.isDragging = false;
    this.isPanning = false;
    this.dragOffset = { x: 0, y: 0 };
    this.dragMoved = false;
    this.dragThreshold = 4;
    this._dragRaf = null;
    this._pendingDx = 0;
    this._pendingDy = 0;

    // 框选
    this.isSelecting = false;
    this.selectStart = { x: 0, y: 0 };
    this.selectionBox = document.getElementById('selection-box');

    // 连线
    this.isConnecting = false;
    this.connectFrom = null;
    this.tempLine = null;

    // 空格平移
    this.spaceDown = false;

    // 右键菜单
    this.contextMenu = document.getElementById('context-menu');
    this.contextNode = null;

    // 防快速重复点击：记录上次选中节点和时间
    this._lastClickNodeId = null;
    this._lastClickTime = 0;
    this._multiClickMinGap = 100; // ms，多选时同一节点最短间隔

    this.bindEvents();
  }

  /* ---- 事件绑定 ---- */

  bindEvents() {
    this.container.addEventListener('mousedown', this.onMouseDown.bind(this));
    window.addEventListener('mousemove', this.onMouseMove.bind(this));
    window.addEventListener('mouseup', this.onMouseUp.bind(this));
    this.container.addEventListener('wheel', this.onWheel.bind(this), { passive: false });
    window.addEventListener('keydown', this.onKeyDown.bind(this));
    window.addEventListener('keyup', this.onKeyUp.bind(this));
    this.container.addEventListener('contextmenu', this.onContextMenu.bind(this));

    // 全局点击：关闭右键菜单 + 取消节点选中（如果点的是画布外的空白）
    document.addEventListener('click', this.onGlobalClick.bind(this));
  }

  /* ---- 坐标转换 ---- */

  screenToCanvas(screenX, screenY) {
    const rect = this.container.getBoundingClientRect();
    return {
      x: (screenX - rect.left - this.panX) / this.scale,
      y: (screenY - rect.top - this.panY) / this.scale
    };
  }

  /* ---- 变换 ---- */

  updateTransform() {
    this.treeCanvas.style.transform = `translate(${this.panX}px, ${this.panY}px) scale(${this.scale})`;
    document.getElementById('zoom-level').textContent = Math.round(this.scale * 100) + '%';
  }

  /* ---- 全局点击：关闭右键菜单 ---- */

  onGlobalClick(e) {
    // 不处理右键菜单项上的点击
    if (this.contextMenu.contains(e.target)) return;
    this.hideContextMenu();
  }

  /* ---- mousedown ---- */

  onMouseDown(e) {
    if (e.button === 2) return; // 右键单独处理

    // 左键点任何地方都关闭右键菜单
    this.hideContextMenu();

    // 清除节点高亮
    this.app.clearHighlight();

    const pos = this.screenToCanvas(e.clientX, e.clientY);
    const node = this.app.renderer.hitTestNode(pos.x, pos.y, this.app.nodes);

    // 空格 / 中键 平移（用户模式保留）
    if (this.spaceDown || e.button === 1) {
      this.isPanning = true;
      this.panStart = { x: e.clientX - this.panX, y: e.clientY - this.panY };
      this.container.style.cursor = 'grabbing';
      return;
    }

    // 连线模式完成（用户模式跳过）
    if (this.isConnecting && node) {
      if (this.app.isUser) return;
      if (node.id !== this.connectFrom) {
        this.app.addConnection(this.connectFrom, node.id);
        this.app.saveHistory();
        this.app.renderConnections();
        this.cancelConnecting();
        showToast('连线完成');
      }
      return;
    }

    if (node) {
      // 用户模式：点击即选中，无 drag/多选/连线
      if (this.app.isUser) {
        this.app.selectNode(node.id, false);
        return;
      }

      const multi = e.shiftKey;
      const already = this.app.selectedIds.has(node.id);
      const now = Date.now();

      // --- 防快速重复点击同一节点：0.1s 内再次点击只选中，不触发编辑 ---
      if (node.id === this._lastClickNodeId && (now - this._lastClickTime) < 100) {
        // 0.1s 内第二次点击：选中节点，但不触发编辑
        this.app.selectNode(node.id, multi);
        this._lastClickNodeId = null; // 重置，让第三次点击可以正常进入编辑
        this._lastClickTime = 0;
        return;
      }
      this._lastClickNodeId = node.id;
      this._lastClickTime = now;

      // --- 选中逻辑 ---
      if (multi && already) {
        this.app.deselectNode(node.id);
      } else if (multi) {
        this.app.selectNode(node.id, true);
      } else if (!already) {
        this.app.selectNode(node.id, false);
      }

      // --- Ctrl+左键 拖拽 ---
      if (e.ctrlKey || e.metaKey) {
        const sel = this.app.getSelectedNodes();
        if (sel.length > 0) {
          this.isDragging = true;
          this.dragOffset = { x: pos.x, y: pos.y };
          this.dragMoved = false;
        }
      }
      // 不按 Ctrl 不拖拽，只选中
    } else {
      // 空白区域
      if (this.app.isUser) {
        // 用户模式：空白区域开始平移，不框选
        this.isPanning = true;
        this.panStart = { x: e.clientX - this.panX, y: e.clientY - this.panY };
        this.container.style.cursor = 'grabbing';
        return;
      }
      if (!e.shiftKey) this.app.deselectAll();
      this.isSelecting = true;
      this.selectStart = { x: pos.x, y: pos.y };
      this.selectionBox.style.display = 'block';
      this.selectionBox.style.left = pos.x + 'px';
      this.selectionBox.style.top = pos.y + 'px';
      this.selectionBox.style.width = '0px';
      this.selectionBox.style.height = '0px';
    }
  }

  /* ---- mousemove ---- */

  onMouseMove(e) {
    const pos = this.screenToCanvas(e.clientX, e.clientY);

    // 平移
    if (this.isPanning) {
      this.panX = e.clientX - this.panStart.x;
      this.panY = e.clientY - this.panStart.y;
      this.updateTransform();
      this.app.renderer.renderGrid(this.scale, this.panX, this.panY);
      return;
    }

    // 拖拽
    if (this.isDragging) {
      const dx = pos.x - this.dragOffset.x;
      const dy = pos.y - this.dragOffset.y;

      if (!this.dragMoved && (Math.abs(dx) > this.dragThreshold || Math.abs(dy) > this.dragThreshold)) {
        this.dragMoved = true;
        this.container.style.cursor = 'grabbing';
      }

      if (this.dragMoved) {
        this.dragOffset = { x: pos.x, y: pos.y };
        this._pendingDx += dx;
        this._pendingDy += dy;
        if (!this._dragRaf) {
          this._dragRaf = requestAnimationFrame(() => this._flushDrag());
        }
      }
      return;
    }

    // 框选
    if (this.isSelecting) {
      this.selectionBox.style.left = Math.min(this.selectStart.x, pos.x) + 'px';
      this.selectionBox.style.top = Math.min(this.selectStart.y, pos.y) + 'px';
      this.selectionBox.style.width = Math.abs(pos.x - this.selectStart.x) + 'px';
      this.selectionBox.style.height = Math.abs(pos.y - this.selectStart.y) + 'px';
      return;
    }

    // 连线临时线
    if (this.isConnecting) {
      this.renderTempLine(pos.x, pos.y);
    }

    // 光标
    const hoverNode = this.app.renderer.hitTestNode(pos.x, pos.y, this.app.nodes);
    if (hoverNode && !this.isDragging && !this.isSelecting) {
      this.container.style.cursor = 'pointer';
    } else if (!this.isPanning) {
      this.container.style.cursor = this.spaceDown ? 'grab' : 'default';
    }
  }

  /* ---- mouseup ---- */

  onMouseUp(e) {
    if (this.isPanning) {
      this.isPanning = false;
      this.container.style.cursor = this.spaceDown ? 'grab' : 'default';
      return;
    }

    if (this.isDragging) {
      if (this.app.isUser) { this.isDragging = false; return; }
      if (this._dragRaf) { cancelAnimationFrame(this._dragRaf); this._dragRaf = null; }
      if (this.dragMoved) {
        this._flushDrag();
        this.app.saveHistory();
      }
      this.isDragging = false;
      this.dragMoved = false;
      this.container.style.cursor = 'default';
      this.app.renderer.hideAlignLines();
      return;
    }

    if (this.isSelecting) {
      if (this.app.isUser) { this.isSelecting = false; return; }
      const pos = this.screenToCanvas(e.clientX, e.clientY);
      const sel = this.app.renderer.hitTestRect(this.selectStart.x, this.selectStart.y, pos.x, pos.y, this.app.nodes);
      if (sel.length > 0) {
        this.app.selectNodes(sel.map(n => n.id), e.shiftKey);
      }
      this.isSelecting = false;
      this.selectionBox.style.display = 'none';
    }
  }

  /* ---- wheel ---- */

  onWheel(e) {
    e.preventDefault();
    const rect = this.container.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;
    const oldScale = this.scale;
    this.scale = clamp(this.scale + (e.deltaY > 0 ? -this.scaleStep : this.scaleStep), this.minScale, this.maxScale);
    const ratio = this.scale / oldScale;
    this.panX = mx - (mx - this.panX) * ratio;
    this.panY = my - (my - this.panY) * ratio;
    this.updateTransform();
    this.app.renderer.renderGrid(this.scale, this.panX, this.panY);
    this.app.renderConnections();
  }

  /* ---- keyboard ---- */

  onKeyDown(e) {
    // 用户模式：只保留 Space 平移和 Escape 取消选中
    if (this.app.isUser) {
      if (e.code === 'Space' && !this.isInputFocused()) {
        e.preventDefault();
        if (!this.spaceDown) { this.spaceDown = true; this.container.style.cursor = 'grab'; }
      }
      if (e.key === 'Escape') {
        this.app.deselectAll();
      }
      return;
    }

    if (e.code === 'Space' && !this.isInputFocused()) {
      e.preventDefault();
      if (!this.spaceDown) { this.spaceDown = true; this.container.style.cursor = 'grab'; }
    }
    if (e.key === 'Delete' && !this.isInputFocused()) {
      e.preventDefault(); this.app.deleteSelectedNodes();
    }
    if ((e.ctrlKey || e.metaKey) && e.key === 'z' && !e.shiftKey) {
      e.preventDefault(); this.app.undo();
    }
    if ((e.ctrlKey || e.metaKey) && (e.key === 'y' || (e.key === 'z' && e.shiftKey))) {
      e.preventDefault(); this.app.redo();
    }
    if ((e.ctrlKey || e.metaKey) && e.key === 'a') {
      e.preventDefault(); this.app.selectAll();
    }
    if (e.key === 'Escape') {
      this.app.deselectAll(); this.hideContextMenu(); this.cancelConnecting();
    }
    if (e.key === 'l' && !this.isInputFocused() && this.app.selectedIds.size === 1) {
      this.startConnecting([...this.app.selectedIds][0]);
    }
  }

  onKeyUp(e) {
    if (e.code === 'Space') { this.spaceDown = false; this.container.style.cursor = 'default'; }
  }

  isInputFocused() {
    const t = document.activeElement.tagName;
    return t === 'INPUT' || t === 'TEXTAREA' || t === 'SELECT' || document.activeElement.isContentEditable;
  }

  /* ---- 拖拽帧 ---- */

  _flushDrag() {
    this._dragRaf = null;
    const dx = this._pendingDx;
    const dy = this._pendingDy;
    this._pendingDx = 0;
    this._pendingDy = 0;

    const sel = this.app.getSelectedNodes();

    // 直接应用位移
    sel.forEach(n => { n.x += dx; n.y += dy; });

    // 更新 DOM
    sel.forEach(n => {
      const el = this.app.renderer.nodeEls.get(n.id);
      if (el) el.style.transform = `translate(${n.x}px, ${n.y}px)`;
    });

    // 对齐参考线
    this.app.renderer.showAlignLines(sel, this.app.nodes);

    // 增量更新连线
    this.app.renderer.updateConnectionPaths(this.app.connections, this.app.nodes);
  }

  /* ---- 连线模式 ---- */

  startConnecting(fromId) {
    this.isConnecting = true;
    this.connectFrom = fromId;
    const node = this.app.nodes.find(n => n.id === fromId);
    if (node) { node._linking = true; this.app.renderer.renderNode(node); }
    showToast('点击另一个节点完成连线 (Esc 取消)');
  }

  cancelConnecting() {
    if (this.connectFrom) {
      const node = this.app.nodes.find(n => n.id === this.connectFrom);
      if (node) { node._linking = false; this.app.renderer.renderNode(node); }
    }
    this.isConnecting = false;
    this.connectFrom = null;
    this.removeTempLine();
  }

  renderTempLine(x, y) {
    if (!this.connectFrom) return;
    const from = this.app.nodes.find(n => n.id === this.connectFrom);
    if (!from) return;
    const fc = this.app.renderer.getNodeCenter(from);
    if (!this.tempLine) {
      const ns = 'http://www.w3.org/2000/svg';
      this.tempLine = document.createElementNS(ns, 'path');
      this.tempLine.setAttribute('stroke', '#ffa726');
      this.tempLine.setAttribute('stroke-width', '2');
      this.tempLine.setAttribute('stroke-dasharray', '6 4');
      this.tempLine.setAttribute('fill', 'none');
      this.app.renderer.connectionLayer.appendChild(this.tempLine);
    }
    this.tempLine.setAttribute('d', bezierPath(fc.cx, fc.cy, x, y));
  }

  removeTempLine() {
    if (this.tempLine) { this.tempLine.remove(); this.tempLine = null; }
  }

  /* ---- 右键菜单 ---- */

  onContextMenu(e) {
    if (this.app.isUser) return;
    e.preventDefault();
    const pos = this.screenToCanvas(e.clientX, e.clientY);
    const node = this.app.renderer.hitTestNode(pos.x, pos.y, this.app.nodes);
    if (node) {
      this.contextNode = node;
      if (!this.app.selectedIds.has(node.id)) this.app.selectNode(node.id, false);
      this.contextMenu.style.left = e.clientX + 'px';
      this.contextMenu.style.top = e.clientY + 'px';
      this.contextMenu.classList.remove('hidden');
      this.contextMenu.querySelectorAll('.context-item').forEach(item => {
        item.onclick = (ev) => {
          ev.stopPropagation();
          this.handleContextAction(item.dataset.action, node);
          this.hideContextMenu();
        };
      });
    }
  }

  hideContextMenu() {
    this.contextMenu.classList.add('hidden');
    // 右键菜单关闭时，取消相关节点的选中态
    if (this.contextNode && this.app.selectedIds.has(this.contextNode.id)) {
      this.app.deselectNode(this.contextNode.id);
    }
    this.contextNode = null;
  }

  handleContextAction(action, node) {
    switch (action) {
      case 'edit': this.app.openNodeEditor(node.id); break;
      case 'add-child': this.app.addChildNode(node.id); break;
      case 'connect': this.startConnecting(node.id); break;
      case 'expand-ai': this.app.aiExpandNode(node.id); break;
      case 'delete': this.app.deleteNode(node.id); break;
    }
  }

  
  /* ---- fit ---- */

  fitToScreen(nodes) {
    if (nodes.length === 0) {
      this.scale = 1; this.panX = 0; this.panY = 0; this.updateTransform(); return;
    }
    const cw = this.container.clientWidth, ch = this.container.clientHeight;
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    nodes.forEach(n => { const s = n.size || 70; minX = Math.min(minX, n.x); minY = Math.min(minY, n.y); maxX = Math.max(maxX, n.x + s); maxY = Math.max(maxY, n.y + s); });
    const tw = maxX - minX + 100, th = maxY - minY + 100;
    this.scale = clamp(Math.min(cw / tw, ch / th) * 0.9, this.minScale, this.maxScale);
    this.panX = (cw - tw * this.scale) / 2 - minX * this.scale;
    this.panY = (ch - th * this.scale) / 2 - minY * this.scale;
    this.updateTransform();
    this.app.renderer.renderGrid(this.scale, this.panX, this.panY);
    this.app.renderConnections();
  }
}
