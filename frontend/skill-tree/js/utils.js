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
 * 获取当前用户 ID（从 URL 参数或 localStorage）
 */
function getCurrentUserId() {
  const params = new URLSearchParams(window.location.search);
  if (params.get('userId')) return params.get('userId');
  try {
    // 主应用登录后写入的是 'sg_user'（login.html:95），'currentUser' 为历史遗留 key，保留兜底
    const raw = localStorage.getItem('sg_user') || localStorage.getItem('currentUser');
    const user = raw ? JSON.parse(raw) : null;
    return user ? user.id : null;
  } catch (e) {
    return null;
  }
}

/**
 * 后端 API 的基址
 *
 * ⚠️ 本文件原来所有请求都写**相对路径**（`/api/skill-trees`）—— 只有
 * 「页面与后端同源」时才通。而 `ai-bridge.js` 用的是**绝对地址**
 * （`window.__SELF_GROW_API_BASE__ || 'http://localhost:3001'`）。
 *
 * 两者不一致会出现很难查的现象（2026-09-24 实测）：技能树列表/保存/删除全部
 * 静默失败（`res.ok` 为 false，函数只返回 false，没人看），**只有 AI 对话能连上**
 * （它走绝对地址）→ 用户看到的就是「AI 一直说技能树不存在」。
 *
 * 所以这里统一：**全页面用同一个基址**，与 ai-bridge 保持一致。
 */
function apiBase() {
  return (window.__SELF_GROW_API_BASE__)
      || (window.Auth && window.Auth.API_BASE)
      || window.API_BASE
      || 'http://localhost:3001';
}

/**
 * 调后端（绝对地址 + 显式带 token）
 *
 * 为什么要显式带 token：`auth.js` 的 fetch 包装只给「以它认得的 API_BASE 开头」
 * 或「以 /api/ 开头的相对路径」加 Authorization。当页面与后端不同源、
 * 而我们用绝对地址时，它认不出来 → 请求会 401。
 * （同源时重复加一个头无害。）
 */
function apiFetch(path, init) {
  init = init || {};
  const headers = new Headers(init.headers || {});
  // ⚠️ 判据用 `typeof Auth !== 'undefined'`，**不是** `window.Auth` ——
  //    后者会因为加载顺序/加载失败而**静默不加 token**，
  //    症状是清一色 401，比直接报错更难查。
  try {
    if (typeof Auth !== 'undefined' && Auth && typeof Auth.getAuthHeaders === 'function') {
      const h = Auth.getAuthHeaders() || {};
      if (h.Authorization && !headers.has('Authorization')) {
        headers.set('Authorization', h.Authorization);
      }
    }
  } catch (e) { /* 拿不到就算了：同源时 auth.js 的 fetch 包装会自动补上 */ }
  return fetch(apiBase() + path, Object.assign({}, init, { headers }));
}

/**
 * 算「网格区域」（单位区域的外框）
 *
 * 规则（用户要的）：一开始只有一个单位区域；节点跑到区域外面 →
 * 就在那个方向多补一格。实现上 = 内容包围盒按 unit 向外取整。
 *
 * @param {Array} nodes 当前节点（含 x/y/size）
 * @param {number} unit 一个「单位区域」的边长（画布坐标）
 * @param {object} view 空树时用来定位"中间那一格"：{w, h, panX, panY, scale}
 * @returns {{x0:number,y0:number,x1:number,y1:number}}
 */
function gridRegionFor(nodes, unit, view) {
  const u = unit || 300;
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  (nodes || []).forEach(function (n) {
    const s = n.size || 70;
    minX = Math.min(minX, n.x);
    minY = Math.min(minY, n.y);
    maxX = Math.max(maxX, n.x + s);
    maxY = Math.max(maxY, n.y + s);
  });

  if (isFinite(minX)) {
    return {
      x0: Math.floor(minX / u) * u,
      y0: Math.floor(minY / u) * u,
      x1: Math.ceil(maxX / u) * u,
      y1: Math.ceil(maxY / u) * u,
    };
  }

  // 空树：视口中心那一格
  const v = view || {};
  const sc = v.scale || 1;
  const cx = ((v.w || 0) / 2 - (v.panX || 0)) / sc;
  const cy = ((v.h || 0) / 2 - (v.panY || 0)) / sc;
  const x0 = Math.floor(cx / u) * u;
  const y0 = Math.floor(cy / u) * u;
  return { x0, y0, x1: x0 + u, y1: y0 + u };
}

/**
 * 选出「两端都在选中集合里」的连线
 *
 * 用于多选右键菜单里的「删除边」：只删选中的这些节点**互相之间**的连线，
 * 不动它们连向外部节点的边（那条边也属于外面那个节点，不该被顺手删掉）。
 *
 * @param {Array} connections 连线数组
 * @param {Set|Array} ids      选中的节点 id 集合
 * @returns {Array} 命中的连线
 */
function edgesAmong(connections, ids) {
  const set = ids instanceof Set ? ids : new Set(ids || []);
  if (!set.size || !connections) return [];
  return connections.filter(c => set.has(c.from) && set.has(c.to));
}

/**
 * 规整技能树索引条目 —— 保证 `id` 就是 `tree_id` 字符串
 *
 * ⚠️ 为什么要在这里兜一层（2026-09-24 事故的尾巴）
 *
 * 后端曾经在列表里把**数据库自增主键**当 `id` 返回（现在已修成 tree_id），
 * 而那段"坏"列表已经被写进了用户的 localStorage。历史条目长这样：
 *
 *     { id: 3, tree_id: "tree_ms35mznq_d9bk", name: "…" }
 *
 * 不处理的话会有两个后果：
 *   · 选中它 → `currentId = 3` → `/api/skill-trees/3/chat` → 404「技能树不存在」
 *   · 同步逻辑把它当成"本地独有的树"去后台上传 → 服务器上多出一棵叫 "3" 的垃圾树
 *
 * 规则：有 `tree_id` 就用它当 `id`；纯数字 id 且没有 tree_id 的直接丢掉
 * （它对应的是 `tree_<数字>` 这种死键，真数据在 tree_id 那套 key 下）。
 */
function normalizeTreeEntry(entry) {
  if (!entry || typeof entry !== 'object') return null;
  const id = entry.tree_id || entry.id;
  if (!id) return null;
  if (!entry.tree_id && /^\d+$/.test(String(id))) return null;   // 陈旧的自增 id，丢弃

  const e = Object.assign({}, entry, { id: id });

  // ⚠️ 字段对齐：后端行是 **snake_case**，前端渲染用 **camelCase**。
  //    不映射的话列表会显示「0 节点」+ 空白的创建/更新时间 ——
  //    而且**只有点开那棵树之后**才变对（因为点开会把本地索引刷成 camelCase），
  //    于是症状看起来像"要点击一下才更新"（2026-09-24 用户反馈）。
  if (e.nodeCount == null && e.node_count != null) e.nodeCount = e.node_count;
  if (e.completedCount == null && e.completed_count != null) e.completedCount = e.completed_count;
  if (!e.createdAt && e.created_at) e.createdAt = e.created_at;
  if (!e.updatedAt && e.updated_at) e.updatedAt = e.updated_at;
  return e;
}

function normalizeTreeEntries(list) {
  const out = [];
  const seen = new Set();
  (list || []).forEach(function (t) {
    const e = normalizeTreeEntry(t);
    if (e && !seen.has(e.id)) { seen.add(e.id); out.push(e); }
  });
  return out;
}

/**
 * 从后端 API 加载技能树索引
 */
async function fetchSkillTreeIndex() {
  const userId = getCurrentUserId();
  if (!userId) return null;
  try {
    const res = await apiFetch('/api/skill-trees?user_id=' + userId);
    if (!res.ok) {
      console.warn('[skill-tree] 拉取技能树列表失败：HTTP', res.status, apiBase());
      return null;
    }
    const data = await res.json();
    // 出口就规整：保证调用方拿到的 `id` 一定是 tree_id 字符串
    return normalizeTreeEntries(data.trees || []);
  } catch (e) {
    console.warn('[skill-tree] 拉取技能树列表异常（后端地址：' + apiBase() + '）：', e);
    return null;
  }
}

/**
 * 从后端 API 创建技能树
 */
async function createSkillTreeOnServer(treeId, name, description) {
  const userId = getCurrentUserId();
  if (!userId) return false;
  try {
    const res = await apiFetch('/api/skill-trees?user_id=' + userId, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tree_id: treeId, name: name, description: description }),
    });
    return res.ok;
  } catch (e) {
    return false;
  }
}

/**
 * 从后端 API 保存技能树草稿
 */
async function saveSkillTreeDraft(treeId, data) {
  const userId = getCurrentUserId();
  if (!userId) return false;
  try {
    const res = await apiFetch('/api/skill-trees/' + treeId + '?user_id=' + userId, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    return res.ok;
  } catch (e) {
    return false;
  }
}

/**
 * 从后端 API 发布技能树
 */
async function publishSkillTreeOnServer(treeId, publishedData, nodeCount, completedCount) {
  const userId = getCurrentUserId();
  if (!userId) return false;
  try {
    const res = await apiFetch('/api/skill-trees/' + treeId + '/publish?user_id=' + userId, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        published_data: publishedData,
        node_count: nodeCount,
        completed_count: completedCount,
      }),
    });
    return res.ok;
  } catch (e) {
    return false;
  }
}

/**
 * 从后端 API 获取已发布的技能树
 */
async function fetchPublishedSkillTree(treeId) {
  try {
    const res = await apiFetch('/api/skill-trees/' + treeId + '/published');
    if (!res.ok) return null;
    return await res.json();
  } catch (e) {
    return null;
  }
}

/**
 * 从后端 API 获取单个技能树草稿
 */
async function fetchSkillTreeDraft(treeId) {
  const userId = getCurrentUserId();
  if (!userId) return null;
  try {
    const res = await apiFetch('/api/skill-trees/' + treeId + '?user_id=' + userId);
    if (!res.ok) return null;
    return await res.json();
  } catch (e) {
    return null;
  }
}

/**
 * 从后端 API 保存学习进度
 */
async function saveLearnerProgressOnServer(treeId, learner) {
  const userId = getCurrentUserId();
  if (!userId) return false;
  try {
    const res = await apiFetch('/api/skill-trees/' + treeId + '/learner?user_id=' + userId, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ learner: learner }),
    });
    return res.ok;
  } catch (e) {
    return false;
  }
}

/**
 * 从后端 API 删除技能树
 */
async function deleteSkillTreeOnServer(treeId) {
  const userId = getCurrentUserId();
  if (!userId) return false;
  try {
    const res = await apiFetch('/api/skill-trees/' + treeId + '?user_id=' + userId, {
      method: 'DELETE',
    });
    return res.ok;
  } catch (e) {
    return false;
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
