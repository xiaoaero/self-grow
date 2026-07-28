/* ================================================================
   tree-renderer.js — 树渲染引擎
   ================================================================ */

class TreeRenderer {
  constructor(containerId) {
    this.container = document.getElementById(containerId);
    this.nodeLayer = document.getElementById('node-layer');
    this.connectionLayer = document.getElementById('connection-layer');
    this.gridLayer = document.getElementById('grid-layer');
    this.gridSize = 30;
    this.showGrid = true;

    // 缓存
    this.nodeEls = new Map();       // nodeId -> DOM element
    this.connPaths = new Map();     // connId -> SVGPathElement

    // 对齐参考线
    this._alignLineH = null;
    this._alignLineV = null;
    this._initAlignLines();
  }

  _initAlignLines() {
    const svg = this.connectionLayer;
    const ns = 'http://www.w3.org/2000/svg';
    this._alignLineH = document.createElementNS(ns, 'line');
    this._alignLineH.setAttribute('stroke', '#4fc3f7');
    this._alignLineH.setAttribute('stroke-width', '1');
    this._alignLineH.setAttribute('stroke-dasharray', '6 4');
    this._alignLineH.setAttribute('opacity', '0.6');
    this._alignLineH.style.display = 'none';
    svg.appendChild(this._alignLineH);

    this._alignLineV = document.createElementNS(ns, 'line');
    this._alignLineV.setAttribute('stroke', '#4fc3f7');
    this._alignLineV.setAttribute('stroke-width', '1');
    this._alignLineV.setAttribute('stroke-dasharray', '6 4');
    this._alignLineV.setAttribute('opacity', '0.6');
    this._alignLineV.style.display = 'none';
    svg.appendChild(this._alignLineV);
  }

  /* ---------- 网格 ---------- */

  renderGrid(scale = 1, panX = 0, panY = 0) {
    if (!this.showGrid) {
      this.gridLayer.innerHTML = '';
      return;
    }
    const w = this.container.clientWidth;
    const h = this.container.clientHeight;
    const size = this.gridSize * scale;
    const effectiveSize = size < 15 ? size * 2 : size;

    const offsetX = ((panX % effectiveSize) + effectiveSize) % effectiveSize;
    const offsetY = ((panY % effectiveSize) + effectiveSize) % effectiveSize;

    let html = '';
    for (let x = offsetX; x < w; x += effectiveSize) {
      html += `<line x1="${x}" y1="0" x2="${x}" y2="${h}" class="grid-line"/>`;
    }
    for (let y = offsetY; y < h; y += effectiveSize) {
      html += `<line x1="0" y1="${y}" x2="${w}" y2="${y}" class="grid-line"/>`;
    }
    this.gridLayer.innerHTML = `<g>${html}</g>`;
  }

  /* ---------- 节点 ---------- */

  renderNode(node) {
    let el = this.nodeEls.get(node.id);
    if (!el) {
      el = document.createElement('div');
      el.className = 'skill-node';
      el.setAttribute('data-id', node.id);
      this.nodeLayer.appendChild(el);
      this.nodeEls.set(node.id, el);
    }

    el.className = 'skill-node ' + (node.shape || 'round');
    el.style.setProperty('--node-size', (node.size || 70) + 'px');
    el.style.setProperty('--node-color', node.color || '#2a2a4a');
    el.style.setProperty('--node-border', node.borderColor || '#444466');

    // 用 transform 定位（走 compositor，不触发 layout）
    el.style.transform = `translate(${node.x}px, ${node.y}px)`;
    el.style.left = '0';
    el.style.top = '0';

    // 选中态
    el.classList.toggle('selected', node._selected || false);
    el.classList.toggle('node-highlight', node._highlight || false);

    // 名称重复
    el.classList.toggle('node-name-duplicate', node._nameDuplicate || false);

    // 学习状态
    el.classList.toggle('node-locked', node._learningState === 'locked');
    el.classList.toggle('node-available', node._learningState === 'available');
    el.classList.toggle('node-learning', node._learningState === 'learning');
    el.classList.toggle('node-completed', node._learningState === 'completed');

    const priorityHtml = node.priority && node.priority !== 'none'
      ? `<span class="node-priority ${node.priority}"></span>` : '';

    el.innerHTML = `
      <div class="node-body" style="background:${node.color || '#2a2a4a'};border-color:${node.borderColor || '#444466'}">
        ${priorityHtml}
        <span class="node-content">${node.icon || '📚'}</span>
      </div>
      <span class="node-title">${node.name || '未命名'}</span>`;

    // 预览模式：添加 hover tooltip
    if (window.__app && window.__app.isPreview) {
      this._attachTooltip(el, node);
    }

    return el;
  }

  /** 为预览模式节点添加 hover 0.5s tooltip */
  _attachTooltip(el, node) {
    // 移除旧 tooltip
    var oldTip = el.querySelector('.node-tooltip');
    if (oldTip) oldTip.remove();

    var prereqsHtml = this._getPrereqsHtml(node);
    var tagsHtml = (node.tags && node.tags.length > 0)
      ? '<div class="node-tooltip__tags">' + node.tags.map(function(t) {
          return '<span class="node-tooltip__tag">' + escapeHtml(t) + '</span>';
        }).join('') + '</div>'
      : '';

    var priorityLabel = '';
    switch (node.priority) {
      case 'high': priorityLabel = '🔴 高'; break;
      case 'medium': priorityLabel = '🟡 中'; break;
      case 'low': priorityLabel = '🟢 低'; break;
    }

    var html = '<div class="node-tooltip__name">' + escapeHtml(node.name) + '</div>';

    if (node.description) {
      html += '<div class="node-tooltip__section">';
      html += '<div class="node-tooltip__label">描述</div>';
      html += '<div class="node-tooltip__text">' + escapeHtml(node.description).replace(/\n/g,'<br>') + '</div>';
      html += '</div>';
    }

    if (tagsHtml) {
      html += '<div class="node-tooltip__section">';
      html += '<div class="node-tooltip__label">标签</div>';
      html += tagsHtml;
      html += '</div>';
    }

    if (priorityLabel) {
      html += '<div class="node-tooltip__section">';
      html += '<div class="node-tooltip__label">优先级</div>';
      html += '<div class="node-tooltip__text">' + priorityLabel + '</div>';
      html += '</div>';
    }

    if (prereqsHtml) {
      html += '<div class="node-tooltip__section">';
      html += '<div class="node-tooltip__label">前置条件</div>';
      html += prereqsHtml;
      html += '</div>';
    }

    var tooltip = document.createElement('div');
    tooltip.className = 'node-tooltip';
    tooltip.innerHTML = html;
    el.appendChild(tooltip);

    var timer = null;
    var self = this;

    el.addEventListener('mouseenter', function() {
      // 判断 tooltip 是否会超出右侧边界
      timer = setTimeout(function() {
        tooltip.classList.add('node-tooltip--visible');
        // 检查是否超出右边界，超出则切到左侧
        var rect = tooltip.getBoundingClientRect();
        if (rect.right > window.innerWidth) {
          tooltip.classList.add('node-tooltip--left');
        }
      }, 500);
    });

    el.addEventListener('mouseleave', function() {
      if (timer) { clearTimeout(timer); timer = null; }
      tooltip.classList.remove('node-tooltip--visible');
      tooltip.classList.remove('node-tooltip--left');
    });
  }

  /** 获取前置条件的 HTML */
  _getPrereqsHtml(node) {
    if (!window.__app) return '';
    var app = window.__app;
    var parents = app.connections
      .filter(function(c) { return c.to === node.id; })
      .map(function(c) { return c.from; });
    if (parents.length === 0) return '';

    var nodeMap = {};
    app.nodes.forEach(function(n) { nodeMap[n.id] = n; });

    return parents.map(function(pid) {
      var pn = nodeMap[pid];
      if (!pn) return '';
      return '<div class="node-tooltip__prereq">' + escapeHtml(pn.name) + '</div>';
    }).filter(Boolean).join('');
  }

  renderAllNodes(nodes) {
    const activeIds = new Set(nodes.map(n => n.id));
    for (const [id, el] of this.nodeEls) {
      if (!activeIds.has(id)) { el.remove(); this.nodeEls.delete(id); }
    }
    nodes.forEach(n => this.renderNode(n));
  }

  removeNode(nodeId) {
    const el = this.nodeEls.get(nodeId);
    if (el) { el.remove(); this.nodeEls.delete(nodeId); }
  }

  getNodeCenter(node) {
    return {
      cx: node.x + (node.size || 70) / 2,
      cy: node.y + (node.size || 70) / 2
    };
  }

  /* ---------- 连线 ---------- */

  /** 完全重建连线 */
  renderConnections(connections, nodes) {
    this.connPaths.clear();
    const nodeMap = new Map(nodes.map(n => [n.id, n]));
    let pathsHtml = '';
    let needGlow = false;

    for (const conn of connections) {
      const from = nodeMap.get(conn.from);
      const to = nodeMap.get(conn.to);
      if (!from || !to) continue;

      const fromCenter = this.getNodeCenter(from);
      const toCenter = this.getNodeCenter(to);
      const fromEdge = getEdgePoint(fromCenter.cx, fromCenter.cy, from.size || 70, toCenter.cx, toCenter.cy);
      const toEdge = getEdgePoint(toCenter.cx, toCenter.cy, to.size || 70, fromCenter.cx, fromCenter.cy);

      // 箭头始终从 from 指向 to（语义方向），不根据左右交换
      const fromPt = fromEdge, toPt = toEdge;

      // 计算箭头指向的方向——指向目标节点圆心
      const dirTargetX = toCenter.cx;
      const dirTargetY = toCenter.cy;

      // 贝塞尔曲线后加一段 1px 直线指向目标圆心，使 orient="auto" 感知正确方向
      const dx_dir = dirTargetX - toPt.x;
      const dy_dir = dirTargetY - toPt.y;
      const dist_dir = Math.sqrt(dx_dir * dx_dir + dy_dir * dy_dir);
      let extendX = toPt.x, extendY = toPt.y;
      if (dist_dir > 0) {
        const ratio = 1 / dist_dir;
        extendX = toPt.x + dx_dir * ratio;
        extendY = toPt.y + dy_dir * ratio;
      }
      const d = bezierPath(fromPt.x, fromPt.y, toPt.x, toPt.y) + ` L ${extendX} ${extendY}`;

      // 计算贝塞尔曲线中点 (t=0.5) 的位置和切线角度
      // B(0.5) = 0.125*P0 + 0.375*P1 + 0.375*P2 + 0.125*P3
      // P0 = fromPt, P1 = (fromPt.x+dx, fromPt.y), P2 = (toPt.x-dx, toPt.y), P3 = toPt
      const dx_c = Math.abs(toPt.x - fromPt.x) * 0.4;
      const mx = 0.125 * fromPt.x + 0.375 * (fromPt.x + dx_c) + 0.375 * (toPt.x - dx_c) + 0.125 * toPt.x;
      const my = 0.125 * fromPt.y + 0.375 * fromPt.y + 0.375 * toPt.y + 0.125 * toPt.y;
      // B'(0.5) = 1.5 * (toPt.x - fromPt.x - dx_c, toPt.y - fromPt.y)
      const tx = 1.5 * (toPt.x - fromPt.x - dx_c);
      const ty = 1.5 * (toPt.y - fromPt.y);
      const angle = Math.atan2(ty, tx) * 180 / Math.PI;

      // 判断目标节点（即箭头指向的 to 节点）的学习状态
      const targetNode = to;
      const isCompleted = targetNode._learningState === 'completed';
      if (isCompleted) needGlow = true;

      // 高亮已完成连接
      const connColor = isCompleted ? '#ffd700' : (conn.color || '#666680');
      const strokeWidth = isCompleted ? 3 : 2;

      const extraClass = isCompleted ? ' connection-completed' : '';
      const glowFilter = isCompleted ? ' filter="url(#glow)"' : '';

      // 在连线中点添加三角形箭头，方向和线在该点的切线方向一致
      // 三角形：M -5 -4 L 5 0 L -5 4 z（指向右的三角形，以 (0,0) 为旋转中心）
      // 箭头仅在有 showArrow 时显示
      const arrowHtml = conn.showArrow !== false ? `
        <polygon points="-5,-4 5,0 -5,4"
                 fill="${connColor}"
                 transform="translate(${mx},${my}) rotate(${angle})"/>` : '';

      pathsHtml += `
        <path d="${d}" id="conn-${conn.id}"
              class="tree-connection${conn._selected ? ' selected' : ''}${extraClass}"
              style="stroke:${connColor};stroke-width:${strokeWidth};${conn.dashed ? 'stroke-dasharray:8 4;' : ''}"/>${arrowHtml}`;
    }

    // 添加发光滤镜定义
    let defsHtml = '';
    if (needGlow) {
      defsHtml += `
        <filter id="glow" x="-20%" y="-20%" width="140%" height="140%">
          <feGaussianBlur stdDeviation="2" result="blur"/>
          <feMerge>
            <feMergeNode in="blur"/>
            <feMergeNode in="SourceGraphic"/>
          </feMerge>
        </filter>`;
    }

    this.connectionLayer.innerHTML = `
      <defs>${defsHtml}</defs>
      <g>${pathsHtml}</g>`;

    // 缓存 path 引用
    const svg = this.connectionLayer;
    for (const conn of connections) {
      const p = svg.querySelector(`#conn-${conn.id}`);
      if (p) this.connPaths.set(conn.id, p);
    }
  }

  /** 增量更新连线位置（O(1) 查表，不查 DOM） */
  updateConnectionPaths(connections, nodes) {
    const nodeMap = new Map(nodes.map(n => [n.id, n]));

    for (const conn of connections) {
      const pathEl = this.connPaths.get(conn.id);
      if (!pathEl) continue;

      const from = nodeMap.get(conn.from);
      const to = nodeMap.get(conn.to);
      if (!from || !to) continue;

      const fromCenter = this.getNodeCenter(from);
      const toCenter = this.getNodeCenter(to);
      const fromEdge = getEdgePoint(fromCenter.cx, fromCenter.cy, from.size || 70, toCenter.cx, toCenter.cy);
      const toEdge = getEdgePoint(toCenter.cx, toCenter.cy, to.size || 70, fromCenter.cx, fromCenter.cy);

      // 箭头始终从 from 指向 to（语义方向）
      const fromPt = fromEdge, toPt = toEdge;

      // 更新路径
      const d = bezierPath(fromPt.x, fromPt.y, toPt.x, toPt.y);
      pathEl.setAttribute('d', d);

      // 更新中点箭头的位置和角度
      const arrowEl = pathEl.nextElementSibling;
      if (arrowEl && arrowEl.tagName === 'polygon') {
        const dx_c = Math.abs(toPt.x - fromPt.x) * 0.4;
        const mx = 0.125 * fromPt.x + 0.375 * (fromPt.x + dx_c) + 0.375 * (toPt.x - dx_c) + 0.125 * toPt.x;
        const my = 0.125 * fromPt.y + 0.375 * fromPt.y + 0.375 * toPt.y + 0.125 * toPt.y;
        const tx = 1.5 * (toPt.x - fromPt.x - dx_c);
        const ty = 1.5 * (toPt.y - fromPt.y);
        const angle = Math.atan2(ty, tx) * 180 / Math.PI;
        arrowEl.setAttribute('transform', `translate(${mx},${my}) rotate(${angle})`);
      }
    }
  }

  /* ---------- 对齐线 ---------- */

  showAlignLines(draggedNodes, allNodes, threshold = 6) {
    this._alignLineH.style.display = 'none';
    this._alignLineV.style.display = 'none';
    if (draggedNodes.length === 0) return;

    // 用第一个被拖拽节点做参照
    const d = draggedNodes[0];
    const dCx = d.x + (d.size || 70) / 2;
    const dCy = d.y + (d.size || 70) / 2;

    // 收集所有其他节点的中心和边缘（排除被拖拽的）
    const draggedIds = new Set(draggedNodes.map(n => n.id));
    let bestH = null, bestV = null;
    let bestHdist = threshold, bestVdist = threshold;

    for (const n of allNodes) {
      if (draggedIds.has(n.id)) continue;
      const cx = n.x + (n.size || 70) / 2;
      const cy = n.y + (n.size || 70) / 2;

      // 水平对齐：Y 坐标接近
      const dy = Math.abs(dCy - cy);
      if (dy < bestHdist) {
        bestHdist = dy;
        bestH = { y: cy };
      }
      // 同时检查顶边和底边对齐
      const topDy = Math.abs(d.y - n.y);
      if (topDy < bestHdist) { bestHdist = topDy; bestH = { y: n.y }; }
      const bottomDy = Math.abs((d.y + (d.size || 70)) - (n.y + (n.size || 70)));
      if (bottomDy < bestHdist) { bestHdist = bottomDy; bestH = { y: n.y + (n.size || 70) }; }

      // 垂直对齐：X 坐标接近
      const dx = Math.abs(dCx - cx);
      if (dx < bestVdist) {
        bestVdist = dx;
        bestV = { x: cx };
      }
      const leftDx = Math.abs(d.x - n.x);
      if (leftDx < bestVdist) { bestVdist = leftDx; bestV = { x: n.x }; }
      const rightDx = Math.abs((d.x + (d.size || 70)) - (n.x + (n.size || 70)));
      if (rightDx < bestVdist) { bestVdist = rightDx; bestV = { x: n.x + (n.size || 70) }; }
    }

    if (bestH) {
      this._alignLineH.setAttribute('x1', '-5000');
      this._alignLineH.setAttribute('x2', '5000');
      this._alignLineH.setAttribute('y1', bestH.y);
      this._alignLineH.setAttribute('y2', bestH.y);
      this._alignLineH.style.display = '';
    }
    if (bestV) {
      this._alignLineV.setAttribute('y1', '-5000');
      this._alignLineV.setAttribute('y2', '5000');
      this._alignLineV.setAttribute('x1', bestV.x);
      this._alignLineV.setAttribute('x2', bestV.x);
      this._alignLineV.style.display = '';
    }
  }

  hideAlignLines() {
    this._alignLineH.style.display = 'none';
    this._alignLineV.style.display = 'none';
  }

  /* ---------- 工具 ---------- */

  hitTestNode(x, y, nodes) {
    for (let i = nodes.length - 1; i >= 0; i--) {
      const n = nodes[i];
      const half = (n.size || 70) / 2;
      const cx = n.x + half;
      const cy = n.y + half;
      if ((x - cx) ** 2 + (y - cy) ** 2 <= half * half) return n;
    }
    return null;
  }

  hitTestRect(x1, y1, x2, y2, nodes) {
    const left = Math.min(x1, x2), right = Math.max(x1, x2);
    const top = Math.min(y1, y2), bottom = Math.max(y1, y2);
    return nodes.filter(n => {
      const s = n.size || 70;
      return n.x + s > left && n.x < right && n.y + s > top && n.y < bottom;
    });
  }
}
