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

    // 右键菜单（单选 / 多选两套）
    this.contextMenu = document.getElementById('context-menu');
    this.multiMenu = document.getElementById('context-menu-multi');
    this.contextNode = null;

    // 「移动」模式：选中一批节点后跟随鼠标，再次点击才放下
    this.isMoveMode = false;
    this._moveModeStart = 0;
    this._moveLast = null;
    this.moveModeMinMs = 100;   // 防抖：进入模式后 0.1s 内的点击不算"放下"

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
    if (this.multiMenu && this.multiMenu.contains(e.target)) return;
    this.hideContextMenu();
  }

  /* ---- mousedown ---- */

  onMouseDown(e) {
    if (e.button === 2) return; // 右键单独处理

    // 「移动」模式：这次点击 = 放下（但要看防抖时间）
    if (this.isMoveMode) {
      e.preventDefault && e.preventDefault();
      if (Date.now() - this._moveModeStart < this.moveModeMinMs) {
        // 刚进入模式（比如鼠标没松开就又点了一下），忽略这次点击
        return;
      }
      this.endMoveMode();
      return;
    }

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

      // --- 拖拽 ---
      // ⚠️ 用户明确的约定（2026-09-24，别再改）：
      //    **左键不能拖节点**，必须 **Ctrl/Cmd + 左键** 才拖；
      //    框选多个之后同样要按 Ctrl+左键才能整体拖。
      //    Shift = 加减选（不拖）；右键菜单里的「移动」是另一套（跟随鼠标、再点放下）。
      //
      //    位移超过 4px 才算拖动，所以 Ctrl+单击仍然只是选中。
      const wantDrag = e.ctrlKey || e.metaKey;
      // 上面的选中逻辑已经处理过「点未选中的节点 → 选它一个」，
      // 所以这里只需要在「已是选中项」或「刚被选中」时进入拖动。
      if (wantDrag && !multi) {
        const sel = this.app.getSelectedNodes();
        if (sel.length > 0) {
          this.isDragging = true;
          this.dragOffset = { x: pos.x, y: pos.y };
          this.dragMoved = false;
        }
      }
    } else {
      // 空白区域
      if (this.app.isUser) {
        // 用户模式：空白区域开始平移，不框选
        this.isPanning = true;
        this.panStart = { x: e.clientX - this.panX, y: e.clientY - this.panY };
        this.container.style.cursor = 'grabbing';
        return;
      }
      // 连线模式下点空白处 = 取消连线（原来会开始框选，用户以为卡住了）
      if (this.isConnecting) {
        this.cancelConnecting();
        return;
      }
      if (!e.shiftKey) this.app.deselectAll();
      this.isSelecting = true;
      this.selectStart = { x: pos.x, y: pos.y };
      this.selectionBox.style.display = 'block';
      this._setSelectionBox(pos.x, pos.y, 0, 0);
    }
  }

  /* ---- mousemove ---- */

  onMouseMove(e) {
    const pos = this.screenToCanvas(e.clientX, e.clientY);

    // 「移动」模式：选中的节点整体跟随鼠标（1:1 位移）
    if (this.isMoveMode) {
      if (!this._moveLast) this._moveLast = { x: pos.x, y: pos.y };
      const dx = pos.x - this._moveLast.x;
      const dy = pos.y - this._moveLast.y;
      this._moveLast = { x: pos.x, y: pos.y };
      this._moveSelectedBy(dx, dy);
      return;
    }

    // 平移
    if (this.isPanning) {
      this.panX = e.clientX - this.panStart.x;
      this.panY = e.clientY - this.panStart.y;
      this.updateTransform();
      this.app.renderer.renderGrid(this.scale, this.panX, this.panY, this.app.nodes);
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
      const x = Math.min(this.selectStart.x, pos.x);
      const y = Math.min(this.selectStart.y, pos.y);
      this._setSelectionBox(x, y,
        Math.abs(pos.x - this.selectStart.x),
        Math.abs(pos.y - this.selectStart.y));
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
      // 用户模式下也要把框选矩形收起来，否则会残留一个虚线框
      if (this.app.isUser) {
        this.isSelecting = false;
        this.selectionBox.style.display = 'none';
        return;
      }
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
    this.app.renderer.renderGrid(this.scale, this.panX, this.panY, this.app.nodes);
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
    // ⚠️ 输入框里的 Ctrl+Z / Ctrl+A 不能劫持（在 AI 面板打字时按 Ctrl+Z
    //    应该是撤销文字，而不是把整棵树回滚一步）
    if ((e.ctrlKey || e.metaKey) && e.key === 'z' && !e.shiftKey && !this.isInputFocused()) {
      e.preventDefault(); this.app.undo();
    }
    if ((e.ctrlKey || e.metaKey) && (e.key === 'y' || (e.key === 'z' && e.shiftKey))
        && !this.isInputFocused()) {
      e.preventDefault(); this.app.redo();
    }
    if ((e.ctrlKey || e.metaKey) && e.key === 'a' && !this.isInputFocused()) {
      e.preventDefault(); this.app.selectAll();
    }
    if (e.key === 'Escape') {
      this.app.deselectAll(); this.hideContextMenu(); this.cancelConnecting();
      // Esc 也算"放下"（移动模式里没法点画布空白，不然会一直挂着）
      if (this.isMoveMode) this.endMoveMode();
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

    // 直接应用位移 + 更新 DOM / 连线 / 网格（与「移动」模式同一套逻辑）
    this._moveSelectedBy(dx, dy);

    // 对齐参考线
    this.app.renderer.showAlignLines(sel, this.app.nodes);
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
    // renderConnections 会整体重建图层，临时线若被移除则重新挂载
    if (!this.tempLine.isConnected) {
      this.app.renderer.connectionLayer.appendChild(this.tempLine);
    }
    this.tempLine.setAttribute('d', bezierPath(fc.cx, fc.cy, x, y));
  }

  removeTempLine() {
    if (this.tempLine) { this.tempLine.remove(); this.tempLine = null; }
  }

  /**
   * 画框选矩形
   *
   * ⚠️ 这是**SVG `<rect>`**，不是 HTML div：必须用 `x/y/width/height` **属性**。
   *    以前这里写的是 `style.left/top/width/height` —— 那些对 SVG 元素**完全无效**
   *    （CSS 里还有一条对 SVG 无效的 `#selection-box { border: … }`），
   *    所以框选矩形**从来没显示过**（用户原话：「框呢？鼠标拖动我都不知道我拖了多大」）。
   *
   * 坐标是**画布坐标**：这个 rect 在 `#tree-canvas` 里，跟着画布一起做 transform。
   */
  _setSelectionBox(x, y, w, h) {
    const r = this.selectionBox;
    r.setAttribute('x', x);
    r.setAttribute('y', y);
    r.setAttribute('width', Math.max(0, w));
    r.setAttribute('height', Math.max(0, h));
  }

  /* ---- 右键菜单 ---- */

  onContextMenu(e) {
    if (this.app.isUser) return;
    // 「移动」模式下右键 = 取消移动（原地放下）
    if (this.isMoveMode) { e.preventDefault(); this.endMoveMode(); return; }
    e.preventDefault();
    const pos = this.screenToCanvas(e.clientX, e.clientY);
    const node = this.app.renderer.hitTestNode(pos.x, pos.y, this.app.nodes);
    if (!node) return;

    // 右键落在"没被选中的节点"上 → 只选它一个（单选菜单）
    if (!this.app.selectedIds.has(node.id)) {
      this.app.selectNode(node.id, false);
    }

    const multi = this.app.selectedIds.size > 1;
    const menu = multi ? this.multiMenu : this.contextMenu;
    this.contextNode = multi ? null : node;
    menu.style.left = e.clientX + 'px';
    menu.style.top = e.clientY + 'px';
    menu.classList.remove('hidden');
    menu.querySelectorAll('.context-item').forEach(item => {
      item.onclick = (ev) => {
        ev.stopPropagation();
        this.handleContextAction(item.dataset.action, node);
        this.hideContextMenu();
      };
    });
  }

  hideContextMenu() {
    this.contextMenu.classList.add('hidden');
    if (this.multiMenu) this.multiMenu.classList.add('hidden');
    // 右键菜单关闭时，取消相关节点的选中态（仅单选菜单记了 contextNode）
    if (this.contextNode && this.app.selectedIds.has(this.contextNode.id)) {
      this.app.deselectNode(this.contextNode.id);
    }
    this.contextNode = null;
  }

  /* ---- 「移动」模式 ---- */

  startMoveMode() {
    const sel = this.app.getSelectedNodes();
    if (!sel.length) return;
    this.isMoveMode = true;
    this._moveModeStart = Date.now();
    this._moveLast = null;
    this.container.style.cursor = 'move';
    showToast(`移动 ${sel.length} 个节点：移动鼠标定位，再点一下放下`);
  }

  endMoveMode() {
    if (!this.isMoveMode) return;
    this.isMoveMode = false;
    this._moveLast = null;
    this.container.style.cursor = 'default';
    // 让 Ctrl+Z 能撤销这次移动
    this.app.saveHistory();
    this.app.renderer.hideAlignLines();
    showToast('已放下');
  }

  /**
   * 把选中的节点整体位移（拖动 / 移动模式共用）
   */
  _moveSelectedBy(dx, dy) {
    const sel = this.app.getSelectedNodes();
    sel.forEach(n => {
      n.x += dx;
      n.y += dy;
      const el = this.app.renderer.nodeEls.get(n.id);
      if (el) el.style.transform = `translate(${n.x}px, ${n.y}px)`;
    });
    this.app.renderer.updateConnectionPaths(this.app.connections, this.app.nodes);
    // 节点被拖出「单位区域」时，网格在那个方向多补一格
    this.app.renderer.renderGrid(this.scale, this.panX, this.panY, this.app.nodes);
  }

  handleContextAction(action, node) {
    switch (action) {
      case 'move-selected':
        this.startMoveMode();
        break;
      case 'delete-edges':
        this.app.deleteEdgesAmongSelected();
        break;
      case 'delete-selected':
        this.app.deleteSelectedNodes();
        break;
      case 'edit': this.app.openNodeEditor(node.id); break;
      case 'add-child': this.app.addChildNode(node.id); break;
      case 'connect': this.startConnecting(node.id); break;
      case 'expand-ai': this.app.aiExpandNode(node.id); break;
      case 'delete':
        // 与 deleteSelectedNodes 保持一致的完整删除流程：删除后压栈（改后快照）+ 刷新连线/统计
        this.app.deleteNode(node.id);
        this.app.saveHistory();
        this.app.checkDuplicateNames();
        this.app._updatePublishButtons();
        this.app.sidebar.refreshStats();
        showToast(`已删除节点：${node.name}`);
        break;
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
    this.app.renderer.renderGrid(this.scale, this.panX, this.panY, this.app.nodes);
    this.app.renderConnections();
  }
}
