/* ================================================================
   utils.js — 工具函数
   ================================================================ */

/**
 * 生成唯一 ID
 */
function uid() {
  return 'node_' + Date.now().toString(36) + '_' + Math.random().toString(36).slice(2, 8);
}

/**
 * 深拷贝对象
 */
function deepClone(obj) {
  return JSON.parse(JSON.stringify(obj));
}

/**
 * 显示 Toast
 */
function showToast(message, type = '') {
  const toast = document.getElementById('toast');
  toast.textContent = message;
  toast.className = type;
  void toast.offsetWidth; // 触发重排
  toast.classList.remove('hidden');
  clearTimeout(toast._timeout);
  toast._timeout = setTimeout(() => toast.classList.add('hidden'), 2000);
}

/**
 * 显示确认弹窗（替换浏览器原生 confirm）
 * @param {string} message - 确认消息
 * @param {Function} onConfirm - 确认回调
 * @param {string} [confirmText] - 确认按钮文字
 */
function showConfirm(message, onConfirm, confirmText) {
  const overlay = document.getElementById('modal-overlay');
  if (!overlay) return;
  overlay.classList.remove('hidden');
  const modal = overlay.querySelector('.modal-content') || overlay;
  modal.innerHTML = `
    <div class="modal-header">
      <span>⚠️ 确认操作</span>
    </div>
    <div class="modal-body">
      <p style="margin:0;line-height:1.6">${message}</p>
    </div>
    <div class="modal-footer">
      <button class="btn-cancel" onclick="document.getElementById('modal-overlay').classList.add('hidden')">取消</button>
      <button id="btn-confirm-action" style="background:var(--accent,#4fc3f7);color:#000;border:none;padding:8px 20px;border-radius:6px;cursor:pointer;font-weight:600">${confirmText || '确定'}</button>
    </div>`;
  document.getElementById('btn-confirm-action').onclick = function() {
    document.getElementById('modal-overlay').classList.add('hidden');
    onConfirm();
  };
}

/**
 * 保存到 localStorage
 */
function saveToStorage(key, value) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch (e) {
    console.warn('localStorage save failed:', e);
  }
}

/**
 * 从 localStorage 读取
 */
function loadFromStorage(key, fallback = null) {
  try {
    const raw = localStorage.getItem(key);
    return raw ? JSON.parse(raw) : fallback;
  } catch (e) {
    return fallback;
  }
}

/**
 * 计算贝塞尔曲线路径
 * @param {number} x1 - 起点x
 * @param {number} y1 - 起点y
 * @param {number} x2 - 终点x
 * @param {number} y2 - 终点y
 * @param {number} curvature - 曲率，默认 0.4
 * @returns {string} SVG path d 属性
 */
function bezierPath(x1, y1, x2, y2, curvature = 0.4) {
  const dx = Math.abs(x2 - x1) * curvature;
  const dy = Math.abs(y2 - y1) * curvature;
  return `M ${x1} ${y1} C ${x1 + dx} ${y1}, ${x2 - dx} ${y2}, ${x2} ${y2}`;
}

/**
 * 计算连线起点/终点（节点边缘）
 */
function getEdgePoint(cx, cy, size, targetCx, targetCy) {
  const half = size / 2;
  const dx = targetCx - cx;
  const dy = targetCy - cy;
  const dist = Math.sqrt(dx * dx + dy * dy);
  if (dist === 0) return { x: cx, y: cy };
  const ratio = half / dist;
  return {
    x: cx + dx * ratio,
    y: cy + dy * ratio
  };
}

/**
 * 网格吸附
 */
function snapToGrid(value, gridSize = 20) {
  return Math.round(value / gridSize) * gridSize;
}

/**
 * 限制范围
 */
function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

/**
 * HTML 转义
 */
function escapeHtml(str) {
  if (!str) return '';
  var div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}
