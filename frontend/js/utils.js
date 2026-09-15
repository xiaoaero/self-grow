/* ================================================================
   Utils — 工具函数
   ================================================================ */

/** Show toast notification */
function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = `toast toast--${type}`;

    const icons = { success: '✅', error: '❌', info: 'ℹ️' };
    toast.innerHTML = `<span>${icons[type] || 'ℹ️'}</span> ${message}`;
    container.appendChild(toast);

    setTimeout(() => toast.remove(), 3000);
}

/**
 * SVG 清洗：尺寸归一 + 危险属性消毒
 * - 剥掉 style / width / height，尺寸统一交给 CSS
 * - 剥掉 on* 事件属性与 href/xlink:href 外链，防 XSS
 * - 只保留纯图形标签，杜绝 script/foreignObject/image/a 等危险元素
 */
function sanitizeSvg(svg) {
    if (!svg) return '';
    let s = svg;

    // 1. 提取 <svg> 块（兼容 AI 返回 markdown 包裹或前后杂文）
    const m = s.match(/<svg[\s\S]*?<\/svg>/i);
    if (!m) return '';
    s = m[0];

    // 2. 删除危险标签（含其内容），再删除危险属性
    s = s.replace(/<(script|foreignObject|image|a|iframe|object|embed)[\s\S]*?<\/\1>/gi, '')
         .replace(/<(script|foreignObject|image|a|iframe|object|embed)[^>]*>/gi, '')
         .replace(/\son\w+\s*=\s*"[^"]*"/gi, '')
         .replace(/\son\w+\s*=\s*'[^']*'/gi, '')
         .replace(/\s(?:href|xlink:href)\s*=\s*"[^"]*"/gi, '')
         .replace(/\s(?:href|xlink:href)\s*=\s*'[^']*'/gi, '');

    // 3. 尺寸归一：去掉 style 与内联 width/height，统一交给 CSS 控制
    s = s.replace(/\sstyle\s*=\s*"[^"]*"/gi, '')
         .replace(/\sstyle\s*=\s*'[^']*'/gi, '')
         .replace(/\s*width\s*=\s*"[^"]*"/gi, '')
         .replace(/\s*width\s*=\s*'[^']*'/gi, '')
         .replace(/\s*height\s*=\s*"[^"]*"/gi, '')
         .replace(/\s*height\s*=\s*'[^']*'/gi, '');

    // 4. 兜底：确保有 viewBox，避免 AI 忘记输出导致缩放异常
    if (!/viewBox\s*=/.test(s)) {
        s = s.replace(/^<svg/i, '<svg viewBox="0 0 64 64"');
    }
    return s;
}

/** 渲染习惯图标：SVG 清洗后加样式包裹，文本原样显示 */
function renderHabitIcon(icon) {
    if (!icon) return '';
    if (icon.trim().startsWith('<svg')) {
        const clean = sanitizeSvg(icon);
        return clean ? `<span class="habit-card__icon-svg">${clean}</span>` : '';
    }
    return icon;
}

/** Open modal */
function openModal(title, contentHtml, clickOutsideToClose = true) {
    const overlay = document.getElementById('modal-overlay');
    const modal = document.getElementById('modal');
    modal.innerHTML = `
        <div class="modal__title">
            <span>${title}</span>
            <button class="modal__close-btn" onclick="closeModal()" title="关闭">✕</button>
        </div>
        <div>${contentHtml}</div>
    `;
    overlay.classList.add('modal-overlay--visible');
    modal.classList.add('modal--visible');
    // 记录当前弹窗是否允许外部点击关闭
    overlay.dataset.clickOutsideToClose = clickOutsideToClose ? 'true' : 'false';
    // 用 addEventListener 管理点击外部关闭，彻底避免 onclick property 的兼容问题
    // 先移除旧的监听器（防止重复绑定）
    if (overlay._clickOutsideHandler) {
        overlay.removeEventListener('click', overlay._clickOutsideHandler);
        overlay._clickOutsideHandler = null;
    }
    if (clickOutsideToClose) {
        var handler = function(e) {
            // 确保点击的是 overlay 本身（不是 modal 内部）
            if (e.target === overlay) {
                closeModalIfNotActive();
            }
        };
        overlay._clickOutsideHandler = handler;
        overlay.addEventListener('click', handler);
    }
}

/** Close modal */
function closeModal() {
    var overlay = document.getElementById('modal-overlay');
    overlay.classList.remove('modal-overlay--visible');
    document.getElementById('modal').classList.remove('modal--visible');
    // 清理 clickOutsideHandler，避免下次 openModal 时残留
    if (overlay._clickOutsideHandler) {
        overlay.removeEventListener('click', overlay._clickOutsideHandler);
        overlay._clickOutsideHandler = null;
    }
}

/**
 * 二次确认弹窗（与 skill-tree 的 showConfirm 同签名，主应用此前没有）
 * @param {string} message 提示文案
 * @param {Function} onConfirm 确认回调（支持 async）
 * @param {string} [confirmText] 确认按钮文字
 */
function showConfirm(message, onConfirm, confirmText) {
    const content = `
        <p style="margin:0 0 4px;line-height:1.6">${message}</p>
        <div class="modal__actions">
            <button class="btn btn--ghost" onclick="closeModal()">取消</button>
            <button class="btn btn--primary" id="__confirmOkBtn">${confirmText || '确定'}</button>
        </div>
    `;
    openModal('请确认', content, false);
    document.getElementById('__confirmOkBtn').onclick = function () {
        closeModal();
        if (typeof onConfirm === 'function') onConfirm();
    };
}

/** Close modal with protection for data-entry modals (goals, tasks, habits, rewards)
 *  Prevent accidental data loss when clicking outside. */
function closeModalIfNotActive() {
    const overlay = document.getElementById('modal-overlay');
    // If clickOutsideToClose is explicitly false, don't close
    if (overlay && overlay.dataset.clickOutsideToClose === 'false') return;
    // If any data-entry modal is active, don't close
    if (window._goalModalActive || window._taskModalActive || window._habitModalActive || window._rewardModalActive) return;
    closeModal();
}

/** Format minutes to readable */
function formatMinutes(min) {
    if (min < 60) return `${min}分钟`;
    const h = Math.floor(min / 60);
    const m = min % 60;
    return m > 0 ? `${h}小时${m}分钟` : `${h}小时`;
}

/** Format date */
function formatDate(dateStr) {
    const d = new Date(dateStr);
    return `${d.getMonth() + 1}月${d.getDate()}日`;
}

/** Get trend percentage */
function getTrend(current, previous) {
    if (previous === 0) return current === 0 ? 0 : 100;
    return Math.round(((current - previous) / previous) * 100);
}

/** Get category by id */
function getCategory(id) {
    return AppData.categories.find(c => c.id === id);
}

/** Get day of week label */
const DAY_LABELS = ['日', '一', '二', '三', '四', '五', '六'];

/** Header title icons — extracted from 大标题图标.svg, viewBox 58×58 matching HIST_ICONS.title */
const HEADER_ICONS = {
    // 1. 属性面板 — dark teal circle, radar with colored dots
    attributes: `<svg viewBox="0 0 58 58" fill="none"><g transform="translate(29,29) scale(0.82) translate(-29,-29)"><circle cx="29" cy="29" r="28" fill="url(#g-hdr-attr)"/><circle cx="29" cy="29" r="28" fill="none" stroke="#14b8a6" stroke-width="0.85" opacity="0.2"/><circle cx="29" cy="32" r="16" fill="none" stroke="#5eead4" stroke-width="2.2" stroke-linecap="round" stroke-dasharray="80 20" transform="rotate(135 29 32)"/><circle cx="29" cy="14.5" r="1.5" fill="#5eead4"/><circle cx="40.5" cy="17.5" r="1.5" fill="#a78bfa"/><circle cx="46.5" cy="26" r="1.5" fill="#f472b6"/><circle cx="45" cy="38" r="1.5" fill="#fbbf24"/><circle cx="16" cy="17.5" r="1.5" fill="#fb923c"/><circle cx="10" cy="26" r="1.5" fill="#22c55e"/><circle cx="14.5" cy="36" r="1.5" fill="#5eead4"/><circle cx="29" cy="43.5" r="1.5" fill="#a78bfa"/><circle cx="29" cy="32" r="3" fill="#14b8a6"/><line x1="29" y1="32" x2="40.5" y2="20" stroke="#fbbf24" stroke-width="1.5" stroke-linecap="round"/><circle cx="29" cy="32" r="1.5" fill="#fbbf24"/></g></svg>`,

    // 2. 目标 — dark green circle, target rings with arrow
    goals: `<svg viewBox="0 0 58 58" fill="none"><g transform="translate(29,29) scale(0.82) translate(-29,-29)"><circle cx="29" cy="29" r="28" fill="url(#g-hdr-goal)"/><circle cx="29" cy="29" r="28" fill="none" stroke="#22c55e" stroke-width="0.85" opacity="0.2"/><circle cx="29" cy="29" r="16" fill="none" stroke="#5eead4" stroke-width="1.8" opacity="0.5"/><circle cx="29" cy="29" r="11.5" fill="none" stroke="#5eead4" stroke-width="1.8" opacity="0.7"/><circle cx="29" cy="29" r="7" fill="none" stroke="#22c55e" stroke-width="1.8"/><circle cx="29" cy="29" r="3" fill="#fbbf24"/><g transform="rotate(-30 29 29)"><line x1="29" y1="29" x2="46.5" y2="29" stroke="#fbbf24" stroke-width="1.8" stroke-linecap="round"/><polygon points="46.5,29 43.5,26.8 43.5,31.2" fill="#fbbf24"/><polygon points="29,29 32,26.8 32,31.2 35,26.8 35,31.2" fill="#a78bfa"/></g><circle cx="24.5" cy="24.5" r="1" fill="#fbbf24"/><circle cx="33.5" cy="24.5" r="0.8" fill="#5eead4"/><circle cx="24.5" cy="33.5" r="0.8" fill="#22c55e"/></g></svg>`,

    // 3. 本日任务 — dark amber circle, clipboard with checklist
    todayTasks: `<svg viewBox="0 0 58 58" fill="none"><g transform="translate(29,29) scale(0.82) translate(-29,-29)"><circle cx="29" cy="29" r="28" fill="url(#g-hdr-today)"/><circle cx="29" cy="29" r="28" fill="none" stroke="#f59e0b" stroke-width="0.85" opacity="0.2"/><path d="M16 13 L40.5 13 L43.5 16 L43.5 45 L16 45 Z" fill="#fef3c7"/><path d="M40.5 13 L40.5 16 L43.5 16" fill="#fde68a" stroke="#d97706" stroke-width="0.4"/><rect x="16" y="13" width="4.5" height="32" fill="#ef4444"/><circle cx="18.2" cy="16" r="0.8" fill="#fff"/><circle cx="18.2" cy="23.2" r="0.8" fill="#fff"/><circle cx="18.2" cy="30.5" r="0.8" fill="#fff"/><circle cx="18.2" cy="37.8" r="0.8" fill="#fff"/><circle cx="18.2" cy="42" r="0.8" fill="#fff"/><rect x="24" y="19" width="4.5" height="4.5" rx="0.8" fill="#22c55e"/><path d="M24.7 21.2 L26.2 22.5 L27.7 19.5" stroke="#fff" stroke-width="1" fill="none" stroke-linecap="round" stroke-linejoin="round"/><line x1="30.5" y1="21.2" x2="40.5" y2="21.2" stroke="#92400e" stroke-width="0.8" opacity="0.5"/><rect x="24" y="27.5" width="4.5" height="4.5" rx="0.8" fill="#22c55e"/><path d="M24.7 29.7 L26.2 31 L27.7 28" stroke="#fff" stroke-width="1" fill="none" stroke-linecap="round" stroke-linejoin="round"/><line x1="30.5" y1="29.7" x2="40.5" y2="29.7" stroke="#92400e" stroke-width="0.8" opacity="0.5"/><rect x="24" y="36" width="4.5" height="4.5" rx="0.8" fill="none" stroke="#92400e" stroke-width="1" opacity="0.5"/><line x1="30.5" y1="38.2" x2="39" y2="38.2" stroke="#92400e" stroke-width="0.8" opacity="0.7"/></g></svg>`,

    // 4. 本周任务 — dark purple circle, calendar card with dots
    weekTasks: `<svg viewBox="0 0 58 58" fill="none"><g transform="translate(29,29) scale(0.82) translate(-29,-29)"><circle cx="29" cy="29" r="28" fill="url(#g-hdr-week)"/><circle cx="29" cy="29" r="28" fill="none" stroke="#a78bfa" stroke-width="0.85" opacity="0.2"/><rect x="11.5" y="14.5" width="35" height="32" rx="3" fill="#ede9fe"/><rect x="11.5" y="14.5" width="35" height="7.2" rx="3" fill="#a78bfa"/><rect x="11.5" y="18.5" width="35" height="3.2" fill="#a78bfa"/><rect x="17.5" y="10" width="2.2" height="7.2" rx="0.7" fill="#7c3aed"/><rect x="38.5" y="10" width="2.2" height="7.2" rx="0.7" fill="#7c3aed"/><g font-family="Arial" font-size="3.5" fill="#5b21b6" text-anchor="middle"><text x="16" y="26.2">一</text><text x="22" y="26.2">二</text><text x="28" y="26.2">三</text><text x="33.5" y="26.2">四</text><text x="39" y="26.2">五</text><text x="45" y="26.2">六</text><text x="49.5" y="26.2" font-size="2.5">日</text></g><circle cx="16" cy="32" r="1.8" fill="#22c55e"/><circle cx="22" cy="32" r="1.8" fill="#22c55e"/><circle cx="28" cy="32" r="1.8" fill="#22c55e"/><circle cx="33.5" cy="32" r="1.8" fill="#22c55e"/><circle cx="39" cy="32" r="1.8" fill="#22c55e"/><circle cx="45" cy="32" r="3.2" fill="#fbbf24" opacity="0.3"/><circle cx="45" cy="32" r="2.2" fill="#fbbf24"/><text x="45" y="33.5" font-family="Arial" font-size="2.5" font-weight="bold" fill="#fff" text-anchor="middle">15</text><rect x="16" y="40.5" width="23" height="2.2" rx="1.1" fill="#c4b5fd"/><rect x="16" y="40.5" width="23" height="2.2" rx="1.1" fill="#5eead4"/><text x="42" y="43" font-family="Arial" font-size="3" fill="#5b21b6" font-weight="bold">5/7</text></g></svg>`,

    // 5. 历史任务 — dark slate circle, archive box with checkmark
    historyTasks: `<svg viewBox="0 0 58 58" fill="none"><g transform="translate(29,29) scale(0.82) translate(-29,-29)"><circle cx="29" cy="29" r="28" fill="url(#g-hdr-hist)"/><circle cx="29" cy="29" r="28" fill="none" stroke="#94a3b8" stroke-width="0.85" opacity="0.2"/><path d="M11.5 21.7 L14.5 16 L43.5 16 L46.5 21.7 L46.5 43.5 L11.5 43.5 Z" fill="#475569"/><path d="M11.5 21.7 L46.5 21.7 L46.5 24 L11.5 24 Z" fill="#64748b"/><rect x="23" y="27.5" width="11.5" height="4.5" rx="1.5" fill="#1e293b"/><rect x="24.5" y="29" width="8.5" height="1.5" rx="0.8" fill="#475569"/><g transform="translate(39 36.5) rotate(15)"><circle cx="0" cy="0" r="6.5" fill="#22c55e"/><circle cx="0" cy="0" r="6.5" fill="none" stroke="#16a34a" stroke-width="0.8" stroke-dasharray="1.5 0.8"/><path d="M-3 0 L-0.8 2.2 L3 -2.2" stroke="#fff" stroke-width="1.5" fill="none" stroke-linecap="round" stroke-linejoin="round"/></g><line x1="17.5" y1="36.5" x2="29" y2="36.5" stroke="#94a3b8" stroke-width="0.6" opacity="0.5"/><line x1="17.5" y1="40" x2="27.5" y2="40" stroke="#94a3b8" stroke-width="0.6" opacity="0.5"/></g></svg>`,

    // 6. 习惯追踪 — dark green circle, flame with streak dots
    habits: `<svg viewBox="0 0 58 58" fill="none"><g transform="translate(29,29) scale(0.82) translate(-29,-29)"><circle cx="29" cy="29" r="28" fill="url(#g-hdr-habit)"/><circle cx="29" cy="29" r="28" fill="none" stroke="#22c55e" stroke-width="0.85" opacity="0.2"/><path d="M29 10 C26 16 21.5 19 21.5 26 C21.5 33.5 24.5 37.5 29 40.5 C33.5 37.5 36.5 33.5 36.5 26 C36.5 19 32 16 29 10 Z" fill="#fbbf24"/><path d="M29 16 C27.5 20 24.5 23 24.5 29 C24.5 35 26 37.5 29 39 C32 37.5 33.5 35 33.5 29 C33.5 23 30.5 20 29 16 Z" fill="#f97316"/><ellipse cx="29" cy="32" rx="2.2" ry="3.5" fill="#fef3c7"/><circle cx="16" cy="46.5" r="2.2" fill="#5eead4"/><path d="M14.5 46.5 L16 48 L17.5 45" stroke="#062820" stroke-width="0.8" fill="none" stroke-linecap="round" stroke-linejoin="round"/><circle cx="22" cy="46.5" r="2.2" fill="#5eead4"/><path d="M20.5 46.5 L22 48 L23.5 45" stroke="#062820" stroke-width="0.8" fill="none" stroke-linecap="round" stroke-linejoin="round"/><circle cx="28" cy="46.5" r="2.2" fill="#5eead4"/><path d="M26.5 46.5 L28 48 L29.5 45" stroke="#062820" stroke-width="0.8" fill="none" stroke-linecap="round" stroke-linejoin="round"/><circle cx="34" cy="46.5" r="2.2" fill="#5eead4"/><path d="M32.5 46.5 L34 48 L35.5 45" stroke="#062820" stroke-width="0.8" fill="none" stroke-linecap="round" stroke-linejoin="round"/><circle cx="39.5" cy="46.5" r="2.5" fill="#fbbf24"/><circle cx="39.5" cy="46.5" r="2.5" fill="none" stroke="#fef3c7" stroke-width="0.6" opacity="0.8"/></g></svg>`,

    // 7. 奖励商城 — dark amber circle, coins with star
    rewards: `<svg viewBox="0 0 58 58" fill="none"><g transform="translate(29,29) scale(0.82) translate(-29,-29)"><circle cx="29" cy="29" r="28" fill="url(#g-hdr-reward)"/><circle cx="29" cy="29" r="28" fill="none" stroke="#fbbf24" stroke-width="0.85" opacity="0.2"/><circle cx="13" cy="42" r="3.5" fill="#fde047" stroke="#d97706" stroke-width="0.6"/><text x="13" y="43.5" font-family="Arial" font-size="3.5" font-weight="bold" fill="#92400e" text-anchor="middle">$</text><circle cx="45" cy="42" r="3.2" fill="#fde047" stroke="#d97706" stroke-width="0.6"/><text x="45" y="43.5" font-family="Arial" font-size="3.2" font-weight="bold" fill="#92400e" text-anchor="middle">$</text><circle cx="11.5" cy="27.5" r="2.5" fill="#fde047" stroke="#d97706" stroke-width="0.5"/><text x="11.5" y="29" font-family="Arial" font-size="2.5" font-weight="bold" fill="#92400e" text-anchor="middle">$</text><circle cx="46.5" cy="26" r="3" fill="#fde047" stroke="#d97706" stroke-width="0.5"/><text x="46.5" y="27.5" font-family="Arial" font-size="3" font-weight="bold" fill="#92400e" text-anchor="middle">$</text><circle cx="29" cy="29" r="11.5" fill="#fbbf24"/><circle cx="29" cy="29" r="11.5" fill="none" stroke="#92400e" stroke-width="1"/><circle cx="29" cy="29" r="9.5" fill="none" stroke="#fde047" stroke-width="0.6" opacity="0.6"/><polygon points="29,21.5 31,26.5 36.5,27 32,29.5 33,35 29,31.5 25,35 26,29.5 21.5,27 27,26.5" fill="#fef3c7" stroke="#92400e" stroke-width="0.6" stroke-linejoin="round"/><ellipse cx="24.5" cy="24" rx="3" ry="1.5" fill="#fef3c7" opacity="0.6"/></g></svg>`,

    // 8. 表达训练 — dark purple circle, speech bubble with waves
    expression: `<svg viewBox="0 0 58 58" fill="none"><g transform="translate(29,29) scale(0.82) translate(-29,-29)"><circle cx="29" cy="29" r="28" fill="url(#g-hdr-expr)"/><circle cx="29" cy="29" r="28" fill="none" stroke="#c084fc" stroke-width="0.85" opacity="0.2"/><path d="M15 18 L43 18 L46 21 L46 38 L15 38 Z" fill="#ede9fe" rx="3"/><path d="M15 18 L43 18 L46 21 L46 38 L15 38 Z" fill="none" stroke="#a78bfa" stroke-width="1.2" rx="3"/><circle cx="22" cy="27" r="2.5" fill="#c084fc"/><circle cx="29" cy="27" r="2.5" fill="#c084fc"/><circle cx="36" cy="27" r="2.5" fill="#c084fc"/><path d="M20 33 Q24 37 29 33 Q34 29 38 33" stroke="#a78bfa" stroke-width="1.2" fill="none" stroke-linecap="round"/><circle cx="22" cy="27" r="1" fill="#fff"/><circle cx="29" cy="27" r="1" fill="#fff"/><circle cx="36" cy="27" r="1" fill="#fff"/><path d="M8 42 L13 38 L17 42 L21 38" stroke="#c084fc" stroke-width="0.8" fill="none" stroke-linecap="round" opacity="0.5"/><path d="M10 44 L14 40 L18 44 L22 40" stroke="#a78bfa" stroke-width="0.6" fill="none" stroke-linecap="round" opacity="0.3"/></g></svg>`
};

/** Escape HTML to prevent XSS */
function escapeHtml(str) {
    if (str == null) return '';
    const div = document.createElement('div');
    div.appendChild(document.createTextNode(str));
    return div.innerHTML;
}

/** Get SVG icon HTML for an attribute by its id
 *  @param {string} attrId - e.g. 'health', 'study', 'relation'
 *  @param {number} size - icon size in px (default 20)
 *  @returns {string} inline SVG HTML
 */
function attrIcon(attrId, size) {
    const s = size || 20;
    const svg = AttrIcons[attrId];
    if (!svg) return '';
    // Inject width/height into the svg tag
    return svg.replace('<svg', `<svg width="${s}" height="${s}"`);
}

/* ================================================================
   Level System — 等级计算 & 段位映射 & 阶段配色
   注：公式和段位定义逻辑后续迁移到后端，前端只保留配色映射
   ================================================================ */

const MAX_LEVEL = 200;

/** 单级升级门槛公式：从Lv.L升到Lv.L+1所需累计EXP */
function expForLevel(L) {
    if (L <= 0 || L >= 200) return 0;
    return Math.round(5.5632 * Math.pow(L - 1, 2) + 300);
}

/** 根据累计总经验计算等级（上限200） */
function levelFromTotalExp(totalExp) {
    if (totalExp <= 0) return 1;
    let level = 1;
    let cumulative = 0;
    while (level < 200) {
        const need = expForLevel(level);
        if (cumulative + need > totalExp) break;
        cumulative += need;
        level++;
    }
    return Math.min(level, 200);
}

/** 段位定义（每20级一段，共10段） */
const RANK_TABLE = [
    { tier: 1,  min: 1,   max: 20,  name: '初阶冒险者' },
    { tier: 2,  min: 21,  max: 40,  name: '历练冒险者' },
    { tier: 3,  min: 41,  max: 60,  name: '资深冒险者' },
    { tier: 4,  min: 61,  max: 80,  name: '荒野冒险者' },
    { tier: 5,  min: 81,  max: 100, name: '征途冒险者' },
    { tier: 6,  min: 101, max: 120, name: '秘境冒险者' },
    { tier: 7,  min: 121, max: 140, name: '破晓冒险者' },
    { tier: 8,  min: 141, max: 160, name: '星途冒险者' },
    { tier: 9,  min: 161, max: 180, name: '传奇冒险者' },
    { tier: 10, min: 181, max: 200, name: '不朽冒险者' },
];

/** 根据等级获取段位信息 */
function getRankInfo(level) {
    const lv = Math.min(Math.max(level, 1), MAX_LEVEL);
    return RANK_TABLE.find(r => lv >= r.min && lv <= r.max) || RANK_TABLE[9];
}

/** 分阶段配色 — 仅视觉层，保留在前端 */
const LEVEL_THEME = {
    // tier → { block (左侧方块渐变), bar (进度条渐变), barBg (进度条底色), accent (强调色) }
    // 1: 初阶 — 绿→暖黄浅渐变
    '1': { block: 'linear-gradient(135deg, #5B9A6C, #8CB870, #C4A84A)', bar: 'linear-gradient(90deg, #4A9C6C, #D49A3E)', barBg: 'rgba(74,156,108,0.12)', accent: '#6DBD8A' },
    // 2: 历练 — 黄绿均衡
    '2': { block: 'linear-gradient(135deg, #6B8A3C, #9AA84A, #D4A43A)', bar: 'linear-gradient(90deg, #7BAA3C, #D49A3E)', barBg: 'rgba(122,170,60,0.12)', accent: '#9AB84A' },
    // 3: 资深 — 暖金渐变
    '3': { block: 'linear-gradient(135deg, #8A6B2C, #B08A3C, #D4A43A)', bar: 'linear-gradient(90deg, #C49A3C, #E8B85A)', barBg: 'rgba(196,154,60,0.12)', accent: '#D4A43A' },
    // 4: 荒野 — 暗金哑光
    '4': { block: 'linear-gradient(135deg, #7B5B24, #A07830, #C4942A)', bar: 'linear-gradient(90deg, #B08A2E, #D4A030)', barBg: 'rgba(176,138,46,0.12)', accent: '#C4942A' },
    // 5: 征途 — 金底淡紫过渡
    '5': { block: 'linear-gradient(135deg, #8A6B3C, #A0805A, #B894C4)', bar: 'linear-gradient(90deg, #D49A3E, #B894C4)', barBg: 'rgba(184,148,196,0.10)', accent: '#C4A8D0' },
    // 6: 秘境 — 柔紫主色
    '6': { block: 'linear-gradient(135deg, #7B5B94, #A080B4, #C4A0D4)', bar: 'linear-gradient(90deg, #B894C4, #D4B8E0)', barBg: 'rgba(184,148,196,0.12)', accent: '#C4A0D4' },
    // 7: 破晓 — 深紫+银边
    '7': { block: 'linear-gradient(135deg, #6B4B84, #8B6BA4, #B090C4)', bar: 'linear-gradient(90deg, #9B6BB4, #C4A0D4)', barBg: 'rgba(155,107,180,0.12)', accent: '#B090C4' },
    // 8: 星途 — 暗紫晶微光
    '8': { block: 'linear-gradient(135deg, #5B3B74, #7B5BA4, #A080C4)', bar: 'linear-gradient(90deg, #8B5BB4, #B890D4)', barBg: 'rgba(139,91,180,0.12)', accent: '#A080C4' },
    // 9: 传奇 — 紫金交织+粗边框
    '9': { block: 'linear-gradient(135deg, #8B6B4C, #A0806A, #B898C4)', bar: 'linear-gradient(90deg, #C4943C, #B894C4)', barBg: 'rgba(196,148,60,0.10)', accent: '#D4B040' },
    // 10: 不朽 — 鎏金奢华
    '10': { block: 'linear-gradient(135deg, #B09030, #D4B850, #C4A0D0)', bar: 'linear-gradient(90deg, #D4B040, #C4A8D0, #E8D080)', barBg: 'rgba(212,176,64,0.12)', accent: '#E8D080' },
};

/** 获取给定等级对应的配色主题 */
function getLevelTheme(level) {
    const rank = getRankInfo(level);
    return LEVEL_THEME[String(rank.tier)] || LEVEL_THEME['1'];
}

/** Render sidebar footer with current user level/exp */
function renderSidebarFooter() {
    const user = AppData.user;
    const level = user.level;
    const currentExp = user.exp;
    const expToNext = user.expToNext;
    const pct = Math.min(Math.round((currentExp / expToNext) * 100), 100);
    const rank = getRankInfo(level);
    const theme = getLevelTheme(level);
    const isMaxLevel = level >= MAX_LEVEL;

    const footer = document.getElementById('sidebar-footer');
    if (!footer) return;

    footer.innerHTML = `
        <div class="sidebar__user-level" onclick="navigateTo('usercenter')" role="button" title="进入用户中心">
            <div class="sidebar__level-badge" style="background:${theme.block}">Lv.${level}</div>
            <div class="sidebar__level-info">
                <div class="sidebar__level-name-row">
                    <span class="sidebar__level-name" style="color:${theme.accent}">${rank.name}</span>
                    <svg class="sidebar__user-arrow" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 6l6 6-6 6"/></svg>
                </div>
                <div class="sidebar__exp-bar">
                    <div class="sidebar__exp-fill" style="width:${pct}%;background:${theme.bar}"></div>
                </div>
                <span class="sidebar__exp-text">${isMaxLevel ? '🏆 满级达成' : currentExp.toLocaleString() + ' / ' + expToNext.toLocaleString() + ' EXP'}</span>
            </div>
        </div>
    `;
}

/* ================================================================
   用户登录工具
   ================================================================ */

const API_BASE = window.__SELF_GROW_API_BASE__ || 'http://localhost:3001';

/* ================================================================
   时间工具（全项目统一口径：本地时间）

   ⚠️ 绝对不要用 `new Date().toISOString()` 来做这两件事：
     · toISOString() 给的是 **UTC 壁钟**，去掉 Z 当作本地时间发给后端 →
       数据会整体早 8 小时（UTC+8），凌晨 0~8 点记录的行动还会落到前一天
     · toISOString().slice(0,10) 取的是 **UTC 日期** → 同样在凌晨取到"昨天"

   要发给后端 / 要判断"今天"时，一律用下面这两个函数。
   ================================================================ */

/** 本地墙上时间的 ISO 串：2026-09-15T09:00:00（不带 Z、不带偏移） */
function toLocalIso(date) {
    const d = date || new Date();
    const p = n => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}` +
           `T${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}

/** 本地日期：2026-09-15（替代 toISOString().slice(0, 10)） */
function todayLocal(date) {
    return toLocalIso(date).slice(0, 10);
}

/** 获取当前登录用户信息（从 localStorage） */
function getCurrentUser() {
    try {
        const raw = localStorage.getItem('sg_user');
        return raw ? JSON.parse(raw) : null;
    } catch (e) {
        return null;
    }
}

/**
 * 检查是否已登录，未登录则跳转到登录页
 *
 * JWT 改造（2026-09-13）：以 **token 是否存在** 为准，
 * localStorage 里的用户信息只是缓存，不能作为登录凭据。
 * 本地免鉴权模式（TRUSTED_MODE）下后端本就不校验，不拦截。
 */
function requireLogin() {
    if (window.Auth && !window.Auth.isAuthenticated() && !window.Auth.isTrustedMode()) {
        window.Auth.clear();
        window.location.href = '../login.html';
        return false;
    }
    const user = getCurrentUser();
    if (!user) {
        window.location.href = '../login.html';
        return false;
    }
    return true;
}

/** 从后端加载用户完整 profile */
async function fetchUserProfile(userId) {
    try {
        const resp = await fetch(`${API_BASE}/api/users/profile?user_id=${userId}`);
        if (!resp.ok) return null;
        return await resp.json();
    } catch (e) {
        console.warn('后端不可用，返回 null:', e);
        return null;
    }
}

/** 向后端同步今日统计 */
async function syncTodayStats(userId, stats) {
    try {
        const resp = await fetch(`${API_BASE}/api/users/stats/sync?user_id=${userId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(stats),
        });
        if (!resp.ok) return null;
        return await resp.json();
    } catch (e) {
        console.warn('同步统计失败:', e);
        return null;
    }
}

/** 从后端加载习惯数据 */
async function fetchHabits(userId) {
    try {
        const resp = await fetch(`${API_BASE}/api/habits?user_id=${userId}`);
        if (!resp.ok) return null;
        return await resp.json();
    } catch (e) {
        console.warn('后端不可用，习惯数据返回 null:', e);
        return null;
    }
}

/** 从后端加载习惯统计 */
async function fetchHabitStats(userId) {
    try {
        const resp = await fetch(`${API_BASE}/api/habits/stats?user_id=${userId}`);
        if (!resp.ok) return null;
        return await resp.json();
    } catch (e) {
        console.warn('后端不可用，习惯统计返回 null:', e);
        return null;
    }
}

/** 从后端加载习惯洞察 */
async function fetchHabitInsights(userId) {
    try {
        const resp = await fetch(`${API_BASE}/api/habits/insights?user_id=${userId}`);
        if (!resp.ok) return null;
        return await resp.json();
    } catch (e) {
        console.warn('后端不可用，习惯洞察返回 null:', e);
        return null;
    }
}


/** AI 生成习惯图标：区分参数错误(400)与服务失败(5xx) */
async function fetchHabitAIIcon(userId, name, intro, category) {
    try {
        const resp = await fetch(`${API_BASE}/api/habits/ai-icon?user_id=${userId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, intro, category }),
        });
        if (resp.status === 400) {
            // 参数问题：后端 Pydantic 校验拦截（如空名称）
            return { ok: false, svg: null, message: '请先填写习惯名称' };
        }
        if (!resp.ok) {
            let message = '图标生成失败，请稍后重试';
            try {
                const err = await resp.json();
                if (err && err.detail) message = err.detail;
            } catch (_) { /* 非 JSON 错误体，用默认文案 */ }
            console.warn('AI 图标设计失败:', message);
            return { ok: false, svg: null, message };
        }
        const data = await resp.json();
        return { ok: true, svg: data.svg || null, message: null };
    } catch (e) {
        console.warn('后端不可用，AI 图标设计返回 null:', e);
        return { ok: false, svg: null, message: '后端服务不可用，请稍后重试' };
    }
}

/** 从后端加载上周习惯数据 */
async function fetchLastWeekHabits(userId) {
    try {
        const resp = await fetch(`${API_BASE}/api/habits/last-week?user_id=${userId}`);
        if (!resp.ok) return null;
        return await resp.json();
    } catch (e) {
        console.warn('后端不可用，上周习惯数据返回 null:', e);
        return null;
    }
}

/** 向后端创建习惯 */
async function createHabitOnBackend(userId, data) {
    try {
        const resp = await fetch(`${API_BASE}/api/habits?user_id=${userId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data),
        });
        if (!resp.ok) return null;
        return await resp.json();
    } catch (e) {
        console.warn('创建习惯失败:', e);
        return null;
    }
}

/** 向后端更新习惯 */
async function updateHabitOnBackend(habitId, data) {
    try {
        const resp = await fetch(`${API_BASE}/api/habits/${habitId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data),
        });
        if (!resp.ok) return null;
        return await resp.json();
    } catch (e) {
        console.warn('更新习惯失败:', e);
        return null;
    }
}

/** 向后端批量删除习惯 */
async function deleteHabitsOnBackend(userId, ids) {
    try {
        const resp = await fetch(`${API_BASE}/api/habits?user_id=${userId}`, {
            method: 'DELETE',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ids }),
        });
        if (!resp.ok) return null;
        return await resp.json();
    } catch (e) {
        console.warn('删除习惯失败:', e);
        return null;
    }
}

/** 向后端打卡切换 */
async function toggleHabitOnBackend(habitId) {
    try {
        const resp = await fetch(`${API_BASE}/api/habits/${habitId}/toggle`, {
            method: 'POST',
        });
        if (!resp.ok) return null;
        return await resp.json();
    } catch (e) {
        console.warn('打卡同步失败:', e);
        return null;
    }
}


// ================================================================
// 行动记录后端工具函数
// ================================================================

/** 向后端提交行动记录 */
async function submitActionToBackend(userId, data) {
    try {
        const resp = await fetch(`${API_BASE}/api/actions?user_id=${userId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data),
        });
        if (!resp.ok) return null;
        return await resp.json();
    } catch (e) {
        console.warn('提交行动失败:', e);
        return null;
    }
}

/** 发送 AI 行动解析对话消息 */
async function fetchAIActionChat(userId, messages) {
    try {
        const resp = await fetch(`${API_BASE}/api/actions/ai-chat?user_id=${userId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ messages }),
        });
        if (!resp.ok) return null;
        return await resp.json();
    } catch (e) {
        console.warn('AI 行动解析请求失败:', e);
        return null;
    }
}

/** 批量提交 AI 解析后的行动记录 */
async function submitAIActions(userId, actions) {
    try {
        const resp = await fetch(`${API_BASE}/api/actions/ai-submit?user_id=${userId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ actions }),
        });
        if (!resp.ok) return null;
        return await resp.json();
    } catch (e) {
        console.warn('批量提交 AI 行动失败:', e);
        return null;
    }
}

/** 从后端获取行动历史（分页） */
async function fetchActions(userId, params = {}) {
    try {
        const query = new URLSearchParams({ user_id: userId, ...params });
        const resp = await fetch(`${API_BASE}/api/actions?${query}`);
        if (!resp.ok) return null;
        return await resp.json();
    } catch (e) {
        console.warn('获取行动历史失败:', e);
        return null;
    }
}

/** 导出行动历史为 CSV（返回 Blob） */
async function exportActionsCSV(userId, params = {}) {
    try {
        const query = new URLSearchParams({ user_id: userId });
        if (params.category && params.category !== 'all') query.set('category', params.category);
        if (params.date_from) query.set('date_from', params.date_from);
        if (params.date_to) query.set('date_to', params.date_to);
        if (params.include_exp) query.set('include_exp', 'true');
        const resp = await fetch(`${API_BASE}/api/actions/export?${query}`);
        if (resp.status === 204) return null;  // 无内容
        if (!resp.ok) return null;
        return await resp.blob();
    } catch (e) {
        console.warn('导出行动历史失败:', e);
        return null;
    }
}

/** 从后端获取今日行动统计 */
async function fetchActionTodayStats(userId) {
    try {
        const resp = await fetch(`${API_BASE}/api/actions/today-stats?user_id=${userId}`);
        if (!resp.ok) return null;
        return await resp.json();
    } catch (e) {
        console.warn('获取今日行动统计失败:', e);
        return null;
    }
}

/** 检查当前半月是否已记录财务复盘 */
async function fetchFinanceReviewStatus() {
    try {
        const resp = await fetch(`${API_BASE}/api/actions/finance-review-status`);
        if (!resp.ok) return null;
        return await resp.json();
    } catch (e) {
        console.warn('获取财务复盘状态失败:', e);
        return null;
    }
}

/** 从后端获取动态播报 */
async function fetchActivityFeed(userId) {
    try {
        const resp = await fetch(`${API_BASE}/api/activities/feed?user_id=${userId}`);
        if (!resp.ok) return null;
        return await resp.json();
    } catch (e) {
        console.warn('获取动态播报失败:', e);
        return null;
    }
}


// ================================================================
// 目标后端工具函数
// ================================================================

/** 从后端获取所有目标 */
async function fetchGoals(userId) {
    try {
        const resp = await fetch(`${API_BASE}/api/goals?user_id=${userId}`);
        if (!resp.ok) return null;
        return await resp.json();
    } catch (e) {
        console.warn('获取目标失败:', e);
        return null;
    }
}

/** 向后端创建目标 */
async function createGoalOnBackend(userId, data) {
    try {
        const resp = await fetch(`${API_BASE}/api/goals?user_id=${userId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data),
        });
        if (!resp.ok) return null;
        return await resp.json();
    } catch (e) {
        console.warn('创建目标失败:', e);
        return null;
    }
}

/** 向后端更新目标 */
async function updateGoalOnBackend(goalId, data) {
    try {
        const resp = await fetch(`${API_BASE}/api/goals/${goalId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data),
        });
        if (!resp.ok) return null;
        return await resp.json();
    } catch (e) {
        console.warn('更新目标失败:', e);
        return null;
    }
}

/** 向后端删除目标 */
async function deleteGoalOnBackend(goalId) {
    try {
        const resp = await fetch(`${API_BASE}/api/goals/${goalId}`, {
            method: 'DELETE',
        });
        if (!resp.ok) return null;
        return await resp.json();
    } catch (e) {
        console.warn('删除目标失败:', e);
        return null;
    }
}

/** 向后端领取目标奖励 */
async function claimGoalOnBackend(goalId) {
    try {
        const resp = await fetch(`${API_BASE}/api/goals/${goalId}/claim`, {
            method: 'POST',
        });
        if (!resp.ok) return null;
        return await resp.json();
    } catch (e) {
        console.warn('领取目标奖励失败:', e);
        return null;
    }
}

// ================================================================
// 任务后端工具函数
// ================================================================

/** 从后端获取今日任务 */
async function fetchTodayTasks(userId) {
    try {
        const resp = await fetch(`${API_BASE}/api/tasks?user_id=${userId}`);
        if (!resp.ok) return null;
        return await resp.json();
    } catch (e) {
        console.warn('获取今日任务失败:', e);
        return null;
    }
}

/** 从后端获取本周任务 */
async function fetchWeekTasks(userId) {
    try {
        const resp = await fetch(`${API_BASE}/api/tasks/week?user_id=${userId}`);
        if (!resp.ok) return null;
        return await resp.json();
    } catch (e) {
        console.warn('获取本周任务失败:', e);
        return null;
    }
}

/** 从后端获取所有任务（分页） */
async function fetchAllTasks(userId, params = {}) {
    try {
        const query = new URLSearchParams({ user_id: userId, ...params });
        const resp = await fetch(`${API_BASE}/api/tasks/all?${query}`);
        if (!resp.ok) return null;
        return await resp.json();
    } catch (e) {
        console.warn('获取全部任务失败:', e);
        return null;
    }
}

/** 向后端创建任务 */
async function createTaskOnBackend(userId, data) {
    try {
        const resp = await fetch(`${API_BASE}/api/tasks?user_id=${userId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data),
        });
        if (!resp.ok) return null;
        return await resp.json();
    } catch (e) {
        console.warn('创建任务失败:', e);
        return null;
    }
}

/** 从后端获取任务历史（分页） */
async function fetchTaskHistory(userId, params = {}) {
    try {
        const query = new URLSearchParams({ user_id: userId, ...params });
        const resp = await fetch(`${API_BASE}/api/tasks/history?${query}`);
        if (!resp.ok) return null;
        return await resp.json();
    } catch (e) {
        console.warn('获取任务历史失败:', e);
        return null;
    }
}

/** 向后端更新任务 */
async function updateTaskOnBackend(taskId, data) {
    try {
        const resp = await fetch(`${API_BASE}/api/tasks/${taskId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data),
        });
        if (!resp.ok) return null;
        return await resp.json();
    } catch (e) {
        console.warn('更新任务失败:', e);
        return null;
    }
}

/** 向后端变更任务状态 */
async function patchTaskStatusOnBackend(taskId, status, completedAt) {
    try {
        const resp = await fetch(`${API_BASE}/api/tasks/${taskId}/status`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ status, completed_at: completedAt || null }),
        });
        if (!resp.ok) return null;
        return await resp.json();
    } catch (e) {
        console.warn('变更任务状态失败:', e);
        return null;
    }
}

/** 向后端领取任务 EXP */
async function claimTaskOnBackend(userId, taskId) {
    try {
        const resp = await fetch(`${API_BASE}/api/tasks/${taskId}/claim?user_id=${userId}`, {
            method: 'POST',
        });
        if (!resp.ok) return null;
        return await resp.json();
    } catch (e) {
        console.warn('领取任务奖励失败:', e);
        return null;
    }
}

/** 向后端删除任务 */
async function deleteTaskOnBackend(taskId) {
    try {
        const resp = await fetch(`${API_BASE}/api/tasks/${taskId}`, {
            method: 'DELETE',
        });
        if (!resp.ok) return null;
        return await resp.json();
    } catch (e) {
        console.warn('删除任务失败:', e);
        return null;
    }
}

/** 向后端清空历史任务 */
// ================================================================
// 定时任务模板后端工具函数
// ================================================================

/** 从后端获取模板 */
async function fetchScheduledTasks(userId) {
    try {
        const resp = await fetch(`${API_BASE}/api/scheduled-tasks?user_id=${userId}`);
        if (!resp.ok) return null;
        return await resp.json();
    } catch (e) {
        console.warn('获取模板失败:', e);
        return null;
    }
}

/** 向后端创建模板 */
async function createScheduledTaskOnBackend(userId, data) {
    try {
        const resp = await fetch(`${API_BASE}/api/scheduled-tasks?user_id=${userId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data),
        });
        if (!resp.ok) return null;
        return await resp.json();
    } catch (e) {
        console.warn('创建模板失败:', e);
        return null;
    }
}

/** 向后端更新模板 */
async function updateScheduledTaskOnBackend(taskId, data) {
    try {
        const resp = await fetch(`${API_BASE}/api/scheduled-tasks/${taskId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data),
        });
        if (!resp.ok) return null;
        return await resp.json();
    } catch (e) {
        console.warn('更新模板失败:', e);
        return null;
    }
}

/** 向后端删除模板 */
async function deleteScheduledTaskOnBackend(taskId) {
    try {
        const resp = await fetch(`${API_BASE}/api/scheduled-tasks/${taskId}`, {
            method: 'DELETE',
        });
        if (!resp.ok) return null;
        return await resp.json();
    } catch (e) {
        console.warn('删除模板失败:', e);
        return null;
    }
}


// ================================================================
// 统计/数据看板后端工具函数 (P5)
// ================================================================

/** 从后端获取个人统计（6 项卡片 + 8 维进度） */
async function fetchProfileStats(userId) {
    try {
        const resp = await fetch(`${API_BASE}/api/stats/profile?user_id=${userId}`);
        if (!resp.ok) return null;
        return await resp.json();
    } catch (e) {
        console.warn('获取个人统计失败:', e);
        return null;
    }
}

/** 从后端获取年度热力图数据 */
async function fetchYearlyActivity(userId, year) {
    try {
        const params = new URLSearchParams({ user_id: userId });
        if (year) params.set('year', year);
        const resp = await fetch(`${API_BASE}/api/stats/yearly-activity?${params}`);
        if (!resp.ok) return null;
        return await resp.json();
    } catch (e) {
        console.warn('获取年度热力图失败:', e);
        return null;
    }
}

/** 从后端获取每日 EXP 趋势 */
async function fetchDailyExp(userId, days) {
    try {
        const resp = await fetch(`${API_BASE}/api/stats/daily-exp?user_id=${userId}&days=${days}`);
        if (!resp.ok) return null;
        return await resp.json();
    } catch (e) {
        console.warn('获取每日经验趋势失败:', e);
        return null;
    }
}

/** 从后端获取近期动态（仪表盘用） */
async function fetchRecentActivities(userId, limit) {
    try {
        const params = new URLSearchParams({ user_id: userId });
        if (limit) params.set('limit', limit);
        const resp = await fetch(`${API_BASE}/api/activities/recent?${params}`);
        if (!resp.ok) return null;
        return await resp.json();
    } catch (e) {
        console.warn('获取近期动态失败:', e);
        return null;
    }
}


// ================================================================
// 奖励商城 API (P6)
// ================================================================

/** 获取所有奖励（自动评估解锁状态） */
async function fetchRewards(userId) {
    try {
        const resp = await fetch(`${API_BASE}/api/rewards?user_id=${userId}`);
        if (!resp.ok) return null;
        return await resp.json();
    } catch (e) {
        console.warn('获取奖励失败:', e);
        return null;
    }
}

/** 创建新奖励 */
async function createRewardOnBackend(userId, data) {
    try {
        const resp = await fetch(`${API_BASE}/api/rewards`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data),
        });
        if (!resp.ok) return null;
        return await resp.json();
    } catch (e) {
        console.warn('创建奖励失败:', e);
        return null;
    }
}

/** 更新奖励 */
async function updateRewardOnBackend(rewardId, data) {
    try {
        const resp = await fetch(`${API_BASE}/api/rewards/${rewardId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data),
        });
        if (!resp.ok) return null;
        return await resp.json();
    } catch (e) {
        console.warn('更新奖励失败:', e);
        return null;
    }
}

/** 删除奖励 */
async function deleteRewardOnBackend(rewardId) {
    try {
        const resp = await fetch(`${API_BASE}/api/rewards/${rewardId}`, {
            method: 'DELETE',
        });
        if (!resp.ok) return null;
        return await resp.json();
    } catch (e) {
        console.warn('删除奖励失败:', e);
        return null;
    }
}

/** 领取奖励 */
async function claimRewardOnBackend(userId, rewardId) {
    try {
        const resp = await fetch(`${API_BASE}/api/rewards/${rewardId}/claim?user_id=${userId}`, {
            method: 'POST',
        });
        if (!resp.ok) return null;
        return await resp.json();
    } catch (e) {
        console.warn('领取奖励失败:', e);
        return null;
    }
}

/** 手动确认条件 */
async function manualConfirmConditionOnBackend(rewardId, conditionText) {
    try {
        const resp = await fetch(`${API_BASE}/api/rewards/${rewardId}/manual-confirm`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ condition_text: conditionText }),
        });
        if (!resp.ok) return null;
        return await resp.json();
    } catch (e) {
        console.warn('手动确认条件失败:', e);
        return null;
    }
}

/** 重新评估所有奖励 */
async function reevaluateRewardsOnBackend(userId) {
    try {
        const resp = await fetch(`${API_BASE}/api/rewards/reevaluate?user_id=${userId}`, {
            method: 'POST',
        });
        if (!resp.ok) return null;
        return await resp.json();
    } catch (e) {
        console.warn('重新评估奖励失败:', e);
        return null;
    }
}

/** 上传奖励图片 */
async function uploadRewardImageOnBackend(rewardId, file) {
    try {
        const formData = new FormData();
        formData.append('file', file);
        const resp = await fetch(`${API_BASE}/api/rewards/${rewardId}/image`, {
            method: 'POST',
            body: formData,
        });
        if (!resp.ok) return null;
        return await resp.json();
    } catch (e) {
        console.warn('上传奖励图片失败:', e);
        return null;
    }
}

/** 保存奖励草稿 */
async function saveRewardDraftOnBackend(userId, data) {
    try {
        const resp = await fetch(`${API_BASE}/api/rewards/draft?user_id=${userId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data),
        });
        if (!resp.ok) return null;
        return await resp.json();
    } catch (e) {
        console.warn('保存奖励草稿失败:', e);
        return null;
    }
}

/** 获取奖励草稿 */
async function fetchRewardDraftOnBackend(userId) {
    try {
        const resp = await fetch(`${API_BASE}/api/rewards/draft?user_id=${userId}`);
        if (!resp.ok) return null;
        const data = await resp.json();
        return data.draft || null;
    } catch (e) {
        console.warn('获取奖励草稿失败:', e);
        return null;
    }
}

/** 删除奖励草稿 */
async function deleteRewardDraftOnBackend(userId) {
    try {
        const resp = await fetch(`${API_BASE}/api/rewards/draft?user_id=${userId}`, {
            method: 'DELETE',
        });
        if (!resp.ok) return null;
        return await resp.json();
    } catch (e) {
        console.warn('删除奖励草稿失败:', e);
        return null;
    }
}
