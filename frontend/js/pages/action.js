/* ================================================================
   Action Page — 行动（开始行动 + 行动中心）
   ================================================================ */

let selectedActionCategory = null;
let actionDuration = 30;
let actionNote = '';
let actionStartHour = 9;
let actionStartMin = 0;
let actionRecordMode = 'quick'; // 'quick' | 'describe'

// 新计分规则：子类型和附加状态
let actionSubType = '';         // 当前选中的子类型
let actionSleepStart = '';      // 健康-睡眠：睡觉时间 (HH:MM)
let actionSleepEnd = '';        // 健康-睡眠：起床时间 (HH:MM)
let actionWorkExtra = '';       // 工作-加班类型：work-overtime-weekday | work-overtime-weekend

// AI 描述记录模式状态
let actionChatMessages = [];        // [{role: 'user'|'assistant', content: string}]
let actionChatPendingSubmit = null; // AI 返回的待提交 actions 列表
let actionChatSummary = '';         // AI 的总结消息

// 计分规则描述（用于快速行动按钮预览）
const DIMENSION_RULES = {
    health: {
        hasSubTypes: true,
        subTypes: [
            { id: 'health-sport', label: '🏃 运动', desc: '15 EXP/h', hasDuration: true },
            { id: 'health-sleep', label: '😴 睡眠', desc: '基础20EXP+规律额外', hasDuration: false, specialInput: 'sleep' },
        ],
        calcPreview: function(subType, duration) {
            if (subType === 'health-sleep') return '20EXP(基础)+15EXP(规律)';
            return (duration / 60 * 15).toFixed(1) + ' EXP';
        }
    },
    study: {
        hasSubTypes: false,
        calcPreview: function(duration) {
            var blocks = Math.floor(duration / 20);
            var exp = blocks * 10;
            var globalExp = Math.floor(exp * 1.0);
            return exp + ' → 全局' + globalExp + ' EXP';
        }
    },
    relation: {
        hasSubTypes: true,
        subTypes: [
            { id: 'relation-online', label: '💬 线上闲聊', desc: '40 EXP/h，最低30分钟', hasDuration: true },
            { id: 'relation-offline', label: '🤝 线下见面', desc: '80 EXP/次', hasDuration: false },
        ],
        calcPreview: function(subType, duration) {
            if (subType === 'relation-offline') return '80→全局40 EXP';
            var blocks = Math.floor(duration / 30);
            var exp = blocks * 20;
            var globalExp = Math.floor(exp * 0.5);
            return exp + ' → 全局' + globalExp + ' EXP';
        }
    },
    work: {
        hasSubTypes: true,
        subTypes: [
            { id: 'work-daily', label: '📋 日常', desc: '10 EXP', hasDuration: false },
            { id: 'work-overtime', label: '💪 加班', desc: '20~30 EXP', hasDuration: false, subSubTypes: true },
        ],
        calcPreview: function(subType, duration) {
            if (subType === 'work-daily') return '10 EXP';
            if (subType === 'work-overtime-weekday') return '20 EXP';
            if (subType === 'work-overtime-weekend') return '30 EXP';
            return '10 EXP';
        }
    },
    create: {
        hasSubTypes: true,
        subTypes: [
            { id: 'create-output', label: '✍️ 产出', desc: '120 EXP/h', hasDuration: true },
            { id: 'create-material', label: '📚 素材收集', desc: '40 EXP/h，最低30分钟', hasDuration: true },
            { id: 'create-publish', label: '🚀 发布', desc: '160 EXP/次', hasDuration: false },
        ],
        calcPreview: function(subType, duration) {
            if (subType === 'create-publish') return '160→全局80 EXP';
            if (subType === 'create-material') {
                var blocks = Math.floor(duration / 30);
                var exp = blocks * 20;
                var globalExp = Math.floor(exp * 0.5);
                return exp + ' → 全局' + globalExp + ' EXP';
            }
            var exp = duration * 2;
            var globalExp = Math.floor(exp * 0.5);
            return exp + ' → 全局' + globalExp + ' EXP';
        }
    },
    finance: {
        hasSubTypes: true,
        subTypes: [
            { id: 'finance-study', label: '📊 学习梳理', desc: '80 EXP/h', hasDuration: true },
            { id: 'finance-review', label: '📋 月度复盘', desc: '100 EXP/次', hasDuration: false },
        ],
        calcPreview: function(subType, duration) {
            if (subType === 'finance-review') return '100→全局50 EXP';
            var exp = duration * 4 / 3;
            var globalExp = Math.floor(exp * 0.5);
            return Math.round(exp) + ' → 全局' + globalExp + ' EXP';
        }
    },
    hobby: {
        hasSubTypes: false,
        calcPreview: function(duration) {
            var exp = duration * 2 / 3;
            var globalExp = Math.floor(exp * 0.75);
            return Math.round(exp) + ' → 全局' + globalExp + ' EXP';
        }
    },
    soul: {
        hasSubTypes: false,
        calcPreview: function(duration) {
            var exp = duration * 5 / 6;
            var globalExp = Math.floor(exp * 0.5);
            return Math.round(exp) + ' → 全局' + globalExp + ' EXP';
        }
    },
};

// ================================================================
// Action page SVG icons — extracted from 行动-*.svg design files
// ================================================================
const ACTION_ICONS = {
    // ---- 开始行动板块 (from 行动-开始行动图标.svg) ----
    // 标题：开始行动
    quick_title: `<svg viewBox="0 0 48 48" width="48" height="48" fill="none"><path d="M27 8L15 27h9l-3 16 15-19h-9l4-16z" fill="#00d9c0"/><path d="M25.5 13L18.5 27h7.5l-2 10 10-13h-7.5l3-11z" fill="#5dffe9"/><circle cx="14" cy="17" r="1.5" fill="#5dffe9"/><circle cx="35" cy="19" r="1" fill="#e0fffa"/><circle cx="17" cy="35" r="1" fill="#e0fffa"/><path d="M11 22c3-3 7-4 10-5M34 14c3 1.5 5 4 7 7" stroke="#00d9c0" stroke-width="1.5" fill="none" stroke-linecap="round"/></svg>`,
    // 记录努力卡片
    record_effort: `<svg viewBox="0 0 80 80" width="80" height="80" fill="none"><rect width="80" height="80" rx="18" fill="#2a1e0c" stroke="#f5a623" stroke-width="1.5"/><circle cx="40" cy="40" r="28" fill="#4a3414"/><rect x="26" y="22" width="28" height="42" rx="4" fill="#d48a0e"/><rect x="29" y="25" width="22" height="36" rx="2" fill="#f5c96a"/><line x1="33" y1="34" x2="47" y2="34" stroke="#a05f08" stroke-width="2" stroke-linecap="round"/><line x1="33" y1="42" x2="47" y2="42" stroke="#a05f08" stroke-width="2" stroke-linecap="round"/><line x1="33" y1="50" x2="42" y2="50" stroke="#a05f08" stroke-width="2" stroke-linecap="round"/><circle cx="55" cy="26" r="7" fill="#f5a623"/><path d="M52 26l2 2 4-4" fill="none" stroke="#fff8e6" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/><rect x="24" y="52" width="8" height="14" rx="1" fill="#c4740a"/><rect x="25" y="53" width="6" height="12" rx="1" fill="#f5d28a"/></svg>`,
    // 今日统计
    today_stats: `<svg viewBox="0 0 80 80" width="80" height="80" fill="none"><rect width="80" height="80" rx="18" fill="#1f1633" stroke="#8b5cf6" stroke-width="1.5"/><circle cx="40" cy="40" r="28" fill="#332355"/><rect x="22" y="52" width="9" height="16" rx="2" fill="#6d3add"/><rect x="35" y="42" width="9" height="26" rx="2" fill="#8b5cf6"/><rect x="48" y="30" width="9" height="38" rx="2" fill="#a78bfa"/><circle cx="26.5" cy="46" r="2" fill="#a78bfa"/><circle cx="39.5" cy="36" r="2" fill="#ddd6ff"/><circle cx="52.5" cy="24" r="2" fill="#ddd6ff"/><path d="M26.5 46l13-10 13-12" fill="none" stroke="#ddd6ff" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>`,
    // 今日分类分布
    category_dist: `<svg viewBox="0 0 80 80" width="80" height="80" fill="none"><rect width="80" height="80" rx="18" fill="#2d1512" stroke="#f97066" stroke-width="1.5"/><circle cx="40" cy="40" r="28" fill="#4a201b"/><circle cx="40" cy="40" r="20" fill="none" stroke="#c0392b" stroke-width="6" stroke-dasharray="60 66" transform="rotate(-90 40 40)"/><circle cx="40" cy="40" r="20" fill="none" stroke="#f97066" stroke-width="6" stroke-dasharray="38 88" stroke-dashoffset="-62" transform="rotate(-90 40 40)"/><circle cx="40" cy="40" r="20" fill="none" stroke="#ffaaa3" stroke-width="6" stroke-dasharray="22 104" stroke-dashoffset="-102" transform="rotate(-90 40 40)"/><circle cx="40" cy="40" r="8" fill="#ffddd9"/><circle cx="40" cy="40" r="3" fill="#fff5f4"/><circle cx="22" cy="28" r="2" fill="#ffaaa3"/><circle cx="58" cy="52" r="1.8" fill="#ffddd9"/><path d="M18 52c3-3 7-5 11-6" stroke="#f97066" stroke-width="1.5" fill="none" stroke-linecap="round"/></svg>`,
    // 最近行动
    recent_actions: `<svg viewBox="0 0 80 80" width="80" height="80" fill="none"><rect width="80" height="80" rx="18" fill="#101b2d" stroke="#3b82f6" stroke-width="1.5"/><circle cx="40" cy="40" r="28" fill="#182d4d"/><circle cx="40" cy="40" r="18" fill="none" stroke="#3b82f6" stroke-width="4"/><circle cx="40" cy="40" r="18" fill="none" stroke="#60a5fa" stroke-width="2" stroke-dasharray="20 93" transform="rotate(-90 40 40)"/><circle cx="40" cy="40" r="4" fill="#dbeafe"/><line x1="40" y1="40" x2="40" y2="28" stroke="#dbeafe" stroke-width="2" stroke-linecap="round"/><line x1="40" y1="40" x2="49" y2="45" stroke="#60a5fa" stroke-width="2" stroke-linecap="round"/><rect x="24" y="58" width="32" height="6" rx="3" fill="#3b82f6"/><rect x="26" y="60" width="20" height="2" rx="1" fill="#dbeafe"/></svg>`,

    // ---- 行动中心板块 (from 行动-行动中心图标.svg) ----
    // 标题：行动中心
    center_title: `<svg viewBox="0 0 48 48" width="48" height="48" fill="none"><circle cx="24" cy="24" r="18" fill="#134e4a" opacity="0.4"/><path d="M24 10L28 20L38 21L30 29L32 39L24 32L16 39L18 29L10 21L20 20 Z" fill="#2dd4bf"/><circle cx="24" cy="24" r="5" fill="#ccfbf1"/><circle cx="10" cy="39" r="1.5" fill="#2dd4bf"/><circle cx="38" cy="39" r="1.5" fill="#2dd4bf"/></svg>`,
    // 升级进度
    level_progress: `<svg viewBox="0 0 90 90" width="90" height="90" fill="none"><rect width="90" height="90" rx="18" fill="#1f2937" stroke="#374151" stroke-width="1"/><circle cx="45" cy="45" r="32" fill="#713f12" opacity="0.35"/><circle cx="45" cy="45" r="24" fill="#a16207" opacity="0.2"/><path d="M30 62 L40 62 L45 68 L50 62 L60 62 L55 42 L60 28 L45 34 L30 28 L35 42 Z" fill="#fbbf24"/><circle cx="45" cy="24" r="4" fill="#fef3c7"/><path d="M38 40 L45 33 L52 40 L49 40 L49 52 L41 52 L41 40 Z" fill="#78350f"/><circle cx="28" cy="30" r="2" fill="#fbbf24" opacity="0.7"/><circle cx="62" cy="30" r="2" fill="#fbbf24" opacity="0.7"/><path d="M45 70 L45 76" stroke="#f59e0b" stroke-width="2" stroke-linecap="round"/><path d="M42 73 L45 76 L48 73" stroke="#f59e0b" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" fill="none"/></svg>`,
    // 动态播报
    activity_feed: `<svg viewBox="0 0 90 90" width="90" height="90" fill="none"><rect width="90" height="90" rx="18" fill="#1f2937" stroke="#374151" stroke-width="1"/><circle cx="45" cy="45" r="32" fill="#881337" opacity="0.3"/><circle cx="45" cy="45" r="24" fill="#be123c" opacity="0.2"/><path d="M32 35 L32 55 L45 62 L58 55 L58 35 L45 42 Z" fill="#fb7185"/><path d="M58 40 Q68 42 68 48 Q68 54 58 56" stroke="#fda4af" stroke-width="3" fill="none" stroke-linecap="round"/><path d="M62 34 Q74 38 74 48 Q74 58 62 62" stroke="#fda4af" stroke-width="2" fill="none" stroke-linecap="round" opacity="0.6"/><circle cx="26" cy="38" r="2.5" fill="#fb7185"/><circle cx="26" cy="48" r="2.5" fill="#fb7185"/><circle cx="26" cy="58" r="2.5" fill="#fb7185"/><circle cx="70" cy="28" r="2" fill="#fda4af" opacity="0.8"/></svg>`,
    // 习惯打卡
    habit_checkin: `<svg viewBox="0 0 90 90" width="90" height="90" fill="none"><rect width="90" height="90" rx="18" fill="#1f2937" stroke="#374151" stroke-width="1"/><circle cx="45" cy="45" r="32" fill="#14532d" opacity="0.3"/><circle cx="45" cy="45" r="24" fill="#166534" opacity="0.2"/><rect x="28" y="30" width="34" height="38" rx="4" fill="#dcfce7" stroke="#22c55e" stroke-width="1.5"/><rect x="28" y="30" width="34" height="10" rx="4" fill="#22c55e"/><circle cx="35" cy="35" r="2" fill="#dcfce7"/><circle cx="45" cy="35" r="2" fill="#dcfce7"/><circle cx="55" cy="35" r="2" fill="#dcfce7"/><path d="M36 50 L43 57 L56 44" stroke="#15803d" stroke-width="3" fill="none" stroke-linecap="round" stroke-linejoin="round"/><circle cx="62" cy="62" r="6" fill="#22c55e"/><path d="M59 62 L62 65 L66 59" stroke="#dcfce7" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg>`,
    // 目标
    goals: `<svg viewBox="0 0 90 90" width="90" height="90" fill="none"><rect width="90" height="90" rx="18" fill="#1f2937" stroke="#374151" stroke-width="1"/><circle cx="45" cy="45" r="32" fill="#4c1d95" opacity="0.3"/><circle cx="45" cy="45" r="24" fill="#6d28d9" opacity="0.2"/><circle cx="45" cy="45" r="18" fill="none" stroke="#a78bfa" stroke-width="2" opacity="0.8"/><circle cx="45" cy="45" r="12" fill="none" stroke="#a78bfa" stroke-width="2" opacity="0.6"/><circle cx="45" cy="45" r="6" fill="#ede9fe"/><circle cx="45" cy="45" r="2.5" fill="#7c3aed"/><path d="M62 30 L62 38 L56 35 Z" fill="#fbbf24"/><path d="M62 30 L74 26 L74 42 L62 38 Z" fill="#f59e0b" opacity="0.8"/><circle cx="28" cy="28" r="2" fill="#a78bfa" opacity="0.7"/><circle cx="62" cy="62" r="2" fill="#a78bfa" opacity="0.7"/></svg>`,
    // 本周任务
    week_tasks: `<svg viewBox="0 0 90 90" width="90" height="90" fill="none"><rect width="90" height="90" rx="18" fill="#1f2937" stroke="#374151" stroke-width="1"/><circle cx="45" cy="45" r="32" fill="#1e3a8a" opacity="0.3"/><circle cx="45" cy="45" r="24" fill="#1d4ed8" opacity="0.2"/><rect x="28" y="32" width="34" height="40" rx="3" fill="#dbeafe" stroke="#3b82f6" stroke-width="1.5"/><rect x="32" y="38" width="8" height="8" rx="2" fill="#3b82f6" opacity="0.8"/><rect x="44" y="38" width="14" height="2" rx="1" fill="#60a5fa"/><rect x="44" y="44" width="10" height="2" rx="1" fill="#60a5fa" opacity="0.7"/><rect x="32" y="52" width="8" height="8" rx="2" fill="#3b82f6" opacity="0.8"/><rect x="44" y="54" width="14" height="2" rx="1" fill="#60a5fa" opacity="0.7"/><path d="M34 56 L36 58 L39 54" stroke="#dbeafe" stroke-width="1.5" fill="none" stroke-linecap="round" stroke-linejoin="round"/><path d="M28 70 Q45 75 62 70" stroke="#3b82f6" stroke-width="3" fill="none" stroke-linecap="round"/><circle cx="62" cy="70" r="3" fill="#60a5fa"/></svg>`,

    // ---- 行动历史板块 (from 行动-历史行动图标.svg) ----
    // 标题：行动历史
    history_title: `<svg viewBox="0 0 48 48" width="48" height="48" fill="none"><circle cx="24" cy="24" r="18" fill="#78350f" opacity="0.35"/><path d="M14 16 Q24 11 34 16 L34 36 Q24 31 14 36 Z" fill="#fbbf24"/><path d="M17 19 Q24 15 31 19 L31 33 Q24 29 17 33 Z" fill="#fffbeb" opacity="0.9"/><path d="M20 24 L28 24" stroke="#b45309" stroke-width="1.5" stroke-linecap="round"/><path d="M20 28 L26 28" stroke="#b45309" stroke-width="1.5" stroke-linecap="round" opacity="0.7"/><path d="M20 32 L26 32" stroke="#b45309" stroke-width="1.5" stroke-linecap="round" opacity="0.5"/><circle cx="35" cy="14" r="5.5" fill="#fbbf24" stroke="#78350f" stroke-width="1.2"/><path d="M35 11 L35 14 L37 16" stroke="#78350f" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round" fill="none"/></svg>`,
    // 搜索
    search: `<svg viewBox="0 0 90 90" width="90" height="90" fill="none"><rect width="90" height="90" rx="18" fill="#1f2937" stroke="#374151" stroke-width="1"/><circle cx="45" cy="45" r="32" fill="#1e3a8a" opacity="0.3"/><circle cx="45" cy="45" r="24" fill="#1d4ed8" opacity="0.2"/><circle cx="42" cy="42" r="18" fill="none" stroke="#60a5fa" stroke-width="5"/><circle cx="42" cy="42" r="12" fill="#dbeafe" opacity="0.3"/><path d="M54 54 L68 68" stroke="#60a5fa" stroke-width="5" stroke-linecap="round"/><path d="M54 54 L66 66" stroke="#93c5fd" stroke-width="2" stroke-linecap="round"/><circle cx="42" cy="42" r="4" fill="#60a5fa"/><path d="M30 30 Q42 18 54 30" stroke="#93c5fd" stroke-width="1.5" fill="none" stroke-linecap="round" opacity="0.5"/><circle cx="65" cy="28" r="2" fill="#60a5fa" opacity="0.8"/><circle cx="28" cy="65" r="2" fill="#60a5fa" opacity="0.6"/><circle cx="70" cy="70" r="2.5" fill="#2563eb" opacity="0.7"/></svg>`,
};
let actionCenterActivityFilter = 'all';
let actionCenterHabitFilter = 'all';

/* ---- Log-scale duration slider mapping (0-300 min, slider 0-100) ---- */
const DURATION_MAX = 300;    // actual max minutes
const DURATION_SLIDER_MAX = 100; // slider position range

// Inverse-log: slider position (0-100) → actual minutes (1-300)
function sliderToMin(sliderVal) {
    if (sliderVal <= 0) return 1;
    // Use exponential curve: minutes = 1 + (max-1) * (pos/max)^2.5
    // This makes early range fine-grained (pos 0-20 covers 0-22 min) and later coarse
    const ratio = sliderVal / DURATION_SLIDER_MAX;
    const expRatio = Math.pow(ratio, 2.5);
    return Math.round(1 + (DURATION_MAX - 1) * expRatio);
}

// Forward: actual minutes → slider position (0-100)
function minToSlider(minutes) {
    if (minutes <= 1) return 0;
    const ratio = (minutes - 1) / (DURATION_MAX - 1);
    const sliderRatio = Math.pow(ratio, 1 / 2.5);
    return Math.round(sliderRatio * DURATION_SLIDER_MAX);
}

function sliderChange(sliderVal) {
    actionDuration = sliderToMin(sliderVal);
    document.getElementById('duration-val').textContent = actionDuration + '分钟';
    document.getElementById('duration-num').value = actionDuration;
    updateEndTime();
}

function numChange(minutes) {
    actionDuration = minutes;
    document.getElementById('duration-val').textContent = actionDuration + '分钟';
    document.getElementById('duration-slider').value = minToSlider(minutes);
    updateEndTime();
}
let actionCenterGoalFilter = 'all';
let activityModalOpen = false;

// 模块五：本周任务筛选/排序状态
let taskAttrFilter = 'all';
let taskStatusFilter = 'all';
let taskSortBy = 'default';

/* ---- 主入口：根据子页面路由 ---- */
function renderAction(subPage) {
    const tab = subPage || 'quick';
    if (tab === 'center') {
        renderActionCenter();
    } else if (tab === 'history') {
        renderActionHistory();
    } else {
        renderQuickAction();
    }
}

/* ================================================================
   子板块一：开始行动
   ================================================================ */

function renderQuickAction() {
    const cats = AppData.categories;

    // Compute end time from start + duration
    const endH = (actionStartHour + Math.floor((actionStartMin + actionDuration) / 60)) % 24;
    const endM = (actionStartMin + actionDuration) % 60;
    const pad2 = n => String(n).padStart(2, '0');
    const startTimeStr = `${pad2(actionStartHour)}:${pad2(actionStartMin)}`;
    const endTimeStr = `${pad2(endH)}:${pad2(endM)}`;

    const html = `
        <div class="page-header page-header--with-icon">
            <div class="page-header__icon">${ACTION_ICONS.quick_title}</div>
            <div>
                <h1 class="page-header__title">开始行动</h1>
                <p class="page-header__subtitle">记录今日每一份努力，让成长看得见</p>
            </div>
        </div>

        <div class="qa-layout">
            <!-- 左侧：记录努力 (flex: 0 0 55%) -->
            <div class="qa-left">
                <div class="card qa-record-card">
                    <div class="section__title">
                        <span class="section__title-icon">${ACTION_ICONS.record_effort}</span>
                        记录努力
                    </div>

                    <!-- Mode tabs -->
                    <div class="qa-mode-tabs">
                        <button class="qa-mode-tab ${actionRecordMode === 'quick' ? 'qa-mode-tab--active' : ''}"
                                onclick="actionRecordMode='quick';renderQuickAction()">⚡ 快速记录</button>
                        <button class="qa-mode-tab ${actionRecordMode === 'describe' ? 'qa-mode-tab--active' : ''}"
                                onclick="actionRecordMode='describe';renderQuickAction()">🤖 描述记录</button>
                    </div>

                    ${actionRecordMode === 'quick' ? `
                    <div class="action-form">
                        <!-- Category -->
                        <div>
                            <div class="action-form__label">选择分类</div>
                            <div class="action-category-grid">
                                ${cats.map(cat => `
                                    <div class="action-category-item ${selectedActionCategory === cat.id ? 'action-category-item--selected' : ''}"
                                         onclick="selectCategory('${cat.id}')" id="cat-${cat.id}">
                                        <span class="action-category-item__icon">${attrIcon(cat.id, 48)}</span>
                                        <span>${cat.name}</span>
                                    </div>
                                `).join('')}
                            </div>
                        </div>

                        <!-- Dynamic form area (子类型/时长/备注/按钮) -->
                        <div id="qa-dynamic-form">
                            ${renderDynamicForm()}
                        </div>
                    </div>
                    ` : `
                    <div class="action-form">
                        ${renderDescribeMode()}
                    </div>
                    `}
                </div>
            </div>

            <!-- 右侧：统计卡片 + 行动历史 -->
            <div class="qa-right">
                <div class="card">
                    <div class="section__title">
                        <span class="section__title-icon">${ACTION_ICONS.today_stats}</span>
                        今日统计
                    </div>
                    <div style="display:flex;flex-direction:column;gap:16px">
                        <div style="display:flex;justify-content:space-between;align-items:center">
                            <span style="color:var(--color-text-secondary)">已记录行动</span>
                            <span style="font-weight:700;font-size:18px">${AppData.todayStats.tasksDone} 次</span>
                        </div>
                        <div style="display:flex;justify-content:space-between;align-items:center">
                            <span style="color:var(--color-text-secondary)">今日专注</span>
                            <span style="font-weight:700;font-size:18px">${formatMinutes(AppData.todayStats.focusMinutes)}</span>
                        </div>
                        <div style="display:flex;justify-content:space-between;align-items:center">
                            <span style="color:var(--color-text-secondary)">获得经验</span>
                            <span style="font-weight:700;font-size:18px;color:var(--color-accent-light)">+${AppData.todayStats.expEarned} EXP</span>
                        </div>
                        ${renderTripleProgress(AppData.todayStats.expEarned)}
                    </div>
                </div>

                <div class="card">
                    <div class="section__title">
                        <span class="section__title-icon">${ACTION_ICONS.category_dist}</span>
                        今日分类分布
                    </div>
                    <div id="category-dist" style="display:flex;flex-direction:column;gap:10px">
                        ${cats.map(cat => {
                            return `
                                <div style="display:flex;align-items:center;gap:10px">
                                    <span style="width:24px;text-align:center">${attrIcon(cat.id, 18)}</span>
                                    <span style="width:40px;font-size:12px;color:var(--color-text-secondary)">${cat.name}</span>
                                    <span style="width:60px;text-align:right;font-size:11px;color:var(--color-accent-light);font-weight:600" class="cat-dist-exp" data-cat="${cat.id}">0 EXP</span>
                                    <div style="flex:1;height:6px;border-radius:999px;background:rgba(255,255,255,0.06);overflow:hidden">
                                        <div class="cat-dist-fill" style="height:100%;width:0%;border-radius:999px;background:${cat.color};transition:width 0.6s ease" data-cat="${cat.id}"></div>
                                    </div>
                                    <span style="width:36px;text-align:right;font-size:12px;font-weight:600" class="cat-dist-pct" data-cat="${cat.id}">0%</span>
                                </div>
                            `;
                        }).join('')}
                    </div>
                </div>

                <!-- 行动历史 -->
                ${renderActionHistoryCard()}
            </div>
        </div>
    `;

    document.getElementById('page-action').innerHTML = html;

    // 异步加载今日分类分布和最近行动
    loadCategoryDistribution();
    loadRecentActions();
}

function updateEndTime() {
    // Update end time display without full re-render
    const endH = (actionStartHour + Math.floor((actionStartMin + actionDuration) / 60)) % 24;
    const endM = (actionStartMin + actionDuration) % 60;
    const pad2 = n => String(n).padStart(2, '0');
    const endEl = document.getElementById('end-time-display');
    if (endEl) {
        endEl.textContent = `${pad2(endH)}:${pad2(endM)}`;
    }
    const durVal = document.getElementById('duration-val');
    if (durVal) {
        durVal.textContent = actionDuration + '分钟';
    }
}

/* ================================================================
   新计分规则：子类型渲染和辅助函数
   ================================================================ */

/** 判断是否显示时长/开始时间输入 */
function shouldShowDuration(catId, subType) {
    if (!catId) return true;
    // 固定值的子类型不显示时长
    var fixedTypes = [
        'relation-offline', 'work-daily', 'work-overtime',
        'work-overtime-weekday', 'work-overtime-weekend',
        'create-publish', 'finance-review',
    ];
    if (fixedTypes.indexOf(subType) !== -1) return false;
    // 健康睡眠特殊处理
    if (catId === 'health' && subType === 'health-sleep') return false;
    return true;
}

/** 渲染子类型选择区域 */
function renderSubTypeArea(catId) {
    var rule = DIMENSION_RULES[catId];
    if (!rule) return '';

    // 没有子类型的维度（学习、爱好、魅力）
    if (!rule.hasSubTypes) {
        return '<div style="margin-top:8px;color:var(--color-text-secondary);font-size:13px">' +
            '预计: ' + rule.calcPreview(actionDuration) +
            '</div>';
    }

    // 有子类型，渲染子类型按钮
    var subTypeHtml = '<div class="action-form__label" style="margin-top:12px">选择类型</div>' +
        '<div class="qa-subtype-grid" style="display:flex;flex-wrap:wrap;gap:8px;margin-top:4px">';

    rule.subTypes.forEach(function(st) {
        var isActive = (actionSubType === st.id);
        // 工作维度特殊处理
        if (catId === 'work') {
            if (st.id === 'work-daily' && actionSubType === 'work-daily') isActive = true;
            if (st.id === 'work-overtime' && (actionSubType === 'work-overtime' || actionSubType === 'work-overtime-weekday' || actionSubType === 'work-overtime-weekend')) isActive = true;
        }
        subTypeHtml += '<div class="action-category-item ' + (isActive ? 'action-category-item--selected' : '') + '" ' +
            'style="padding:8px 14px;font-size:13px;cursor:pointer" ' +
            'onclick="selectSubType(\'' + catId + '\',\'' + st.id + '\')">' +
            st.label + ' <span style="color:var(--color-accent-light);font-size:11px;margin-left:4px">' + st.desc + '</span></div>';
    });
    subTypeHtml += '</div>';

    // 工作维度：加班子选项
    if (catId === 'work' && (actionSubType === 'work-overtime' || actionSubType === 'work-overtime-weekday' || actionSubType === 'work-overtime-weekend')) {
        subTypeHtml += '<div style="margin-top:8px;margin-left:12px;padding:8px 12px;background:rgba(255,255,255,0.03);border-radius:8px">';
        subTypeHtml += '<div style="font-size:12px;color:var(--color-text-secondary);margin-bottom:6px">加班类型</div>';
        var isWeekday = (actionWorkExtra === 'work-overtime-weekday' || actionSubType === 'work-overtime-weekday');
        var isWeekend = (actionWorkExtra === 'work-overtime-weekend' || actionSubType === 'work-overtime-weekend');
        // 默认选择
        if (!actionWorkExtra && actionSubType === 'work-overtime') {
            var today = new Date();
            var dayOfWeek = today.getDay();
            if (dayOfWeek === 0 || dayOfWeek === 6) {
                isWeekend = true;
            } else {
                isWeekday = true;
            }
        }
        subTypeHtml += '<div style="display:flex;gap:8px">' +
            '<div class="action-category-item ' + (isWeekday ? 'action-category-item--selected' : '') + '" ' +
            'style="padding:6px 12px;font-size:12px;cursor:pointer" ' +
            'onclick="actionWorkExtra=\'work-overtime-weekday\';actionSubType=\'work-overtime-weekday\';updateDynamicForm()">' +
            '📅 工作日加班 <span style="color:var(--color-accent-light)">+20 EXP</span></div>' +
            '<div class="action-category-item ' + (isWeekend ? 'action-category-item--selected' : '') + '" ' +
            'style="padding:6px 12px;font-size:12px;cursor:pointer" ' +
            'onclick="actionWorkExtra=\'work-overtime-weekend\';actionSubType=\'work-overtime-weekend\';updateDynamicForm()">' +
            '🎉 休息日加班 <span style="color:var(--color-accent-light)">+30 EXP</span></div></div>';
        subTypeHtml += '</div>';
    }

    // 健康睡眠特殊输入
    if (catId === 'health' && actionSubType === 'health-sleep') {
        subTypeHtml += '<div style="margin-top:12px;padding:12px;background:rgba(88,213,201,0.06);border-radius:10px;border:1px solid rgba(88,213,201,0.15)">';
        subTypeHtml += '<div style="font-size:13px;color:var(--color-text-secondary);margin-bottom:8px">🌙 记录睡眠时间</div>';
        subTypeHtml += '<div style="display:flex;gap:12px;align-items:center;flex-wrap:wrap">';
        subTypeHtml += '<span style="font-size:13px">😴 睡觉</span>';
        subTypeHtml += '<input type="time" class="input" style="width:130px;padding:6px 10px" value="' + actionSleepStart + '" ' +
            'onchange="actionSleepStart=this.value;updateDynamicForm()">';
        subTypeHtml += '<span style="font-size:13px">→ 起床</span>';
        subTypeHtml += '<input type="time" class="input" style="width:130px;padding:6px 10px" value="' + actionSleepEnd + '" ' +
            'onchange="actionSleepEnd=this.value;updateDynamicForm()">';
        subTypeHtml += '</div>';
        // 睡眠时长和经验的实时预览
        if (actionSleepStart && actionSleepEnd) {
            var sleepInfo = calcSleepPreview(actionSleepStart, actionSleepEnd);
            subTypeHtml += '<div style="margin-top:8px;font-size:12px;color:var(--color-accent-light)">' + sleepInfo + '</div>';
        }
        subTypeHtml += '</div>';
    }

    // 显示预览
    subTypeHtml += '<div style="margin-top:8px;color:var(--color-text-secondary);font-size:13px">' +
        '预计: ' + getActionButtonPreview(catId, actionSubType, actionDuration) +
        '</div>';

    return subTypeHtml;
}

/** 选择子类型 */
function selectSubType(catId, subType) {
    actionSubType = subType;

    // 工作维度特殊处理
    if (catId === 'work' && subType === 'work-overtime') {
        var today = new Date();
        var dayOfWeek = today.getDay();
        if (dayOfWeek === 0 || dayOfWeek === 6) {
            actionWorkExtra = 'work-overtime-weekend';
        } else {
            actionWorkExtra = 'work-overtime-weekday';
        }
    }

    // 健康睡眠重置时间
    if (catId === 'health' && subType !== 'health-sleep') {
        actionSleepStart = '';
        actionSleepEnd = '';
    }

    // 非固定值子类型恢复默认时长
    if (catId === 'health' && subType === 'health-sport') {
        actionDuration = 30;
    } else if (subType === 'relation-online') {
        actionDuration = 30;
    } else if (subType === 'create-output') {
        actionDuration = 60;
    } else if (subType === 'create-material') {
        actionDuration = 30;
    } else if (subType === 'finance-study') {
        actionDuration = 60;
    } else if (subType === 'hobby' || subType === 'soul') {
        actionDuration = 60;
    }

    updateDynamicForm();
}

/** 计算睡眠经验预览 */
function calcSleepPreview(sleepStart, sleepEnd) {
    if (!sleepStart || !sleepEnd) return '';
    var sh = parseInt(sleepStart.split(':')[0]);
    var sm = parseInt(sleepStart.split(':')[1]);
    var eh = parseInt(sleepEnd.split(':')[0]);
    var em = parseInt(sleepEnd.split(':')[1]);

    var startMin = sh * 60 + sm;
    var endMin = eh * 60 + em;
    if (endMin <= startMin) endMin += 24 * 60;
    var durationMin = endMin - startMin;

    if (durationMin < 360 || durationMin > 540) {
        return '⚠️ 睡眠时长 ' + Math.round(durationMin / 60) + 'h' + (durationMin % 60) + 'm，不在6-9h范围内，无效';
    }

    var idealBedtime = 23 * 60;
    var actualBedtime = startMin;
    if (actualBedtime < 12 * 60) actualBedtime += 24 * 60;
    var lateMin = Math.max(0, actualBedtime - idealBedtime);
    var baseExp = Math.max(0, 20 - Math.floor(lateMin / 4));

    var sleepHours = Math.floor(durationMin / 60);
    var sleepMins = durationMin % 60;
    return '睡眠' + sleepHours + 'h' + sleepMins + 'm · 基础+' + baseExp + ' EXP' +
        '（' + sh + ':' + String(sm).padStart(2,'0') + '→' + eh + ':' + String(em).padStart(2,'0') + '）';
}

/** 获取按钮预览文本 */
function getActionButtonPreview(catId, subType, duration) {
    if (!catId) return '(请选择分类)';
    var rule = DIMENSION_RULES[catId];
    if (!rule) return '';

    // 健康睡眠特殊处理
    if (catId === 'health' && subType === 'health-sleep') {
        if (!actionSleepStart || !actionSleepEnd) return '(请填写睡眠时间)';
        var sh = parseInt(actionSleepStart.split(':')[0]);
        var sm = parseInt(actionSleepStart.split(':')[1]);
        var eh = parseInt(actionSleepEnd.split(':')[0]);
        var em = parseInt(actionSleepEnd.split(':')[1]);
        var startMin = sh * 60 + sm;
        var endMin = eh * 60 + em;
        if (endMin <= startMin) endMin += 24 * 60;
        var durMin = endMin - startMin;
        if (durMin < 360 || durMin > 540) return '(睡眠时长无效，需6-9h)';
        var idealBedtime = 23 * 60;
        var actualBedtime = startMin;
        if (actualBedtime < 12 * 60) actualBedtime += 24 * 60;
        var lateMin = Math.max(0, actualBedtime - idealBedtime);
        var baseExp = Math.max(0, 20 - Math.floor(lateMin / 4));
        return '+约' + baseExp + ' EXP' + (baseExp >= 15 ? ' + 规律?' : '');
    }

    // 工作维度
    if (catId === 'work') {
        if (subType === 'work-overtime-weekday' || actionWorkExtra === 'work-overtime-weekday') return '+20 EXP';
        if (subType === 'work-overtime-weekend' || actionWorkExtra === 'work-overtime-weekend') return '+30 EXP';
        if (subType === 'work-daily' || !subType) return '+10 EXP';
        if (subType === 'work-overtime') return '+20~30 EXP';
        return '+10 EXP';
    }

    // 没有子类型或已有子类型
    if (!subType && rule.hasSubTypes) {
        // 自动选择第一个有子类型的预览
        if (rule.subTypes && rule.subTypes.length > 0) {
            var first = rule.subTypes[0];
            return rule.calcPreview(first.id, duration);
        }
        return '';
    }

    return rule.calcPreview(subType, duration);
}

/** 获取提交的 sub_type */
function getSubmitSubType(catId) {
    if (!catId) return '';

    // 健康维度：根据是否有睡眠时间判断
    if (catId === 'health') {
        if (actionSleepStart && actionSleepEnd) return 'health-sleep';
        return 'health-sport';
    }

    // 工作维度
    if (catId === 'work') {
        if (actionWorkExtra === 'work-overtime-weekday') return 'work-overtime-weekday';
        if (actionWorkExtra === 'work-overtime-weekend') return 'work-overtime-weekend';
        if (actionSubType === 'work-overtime-weekday') return 'work-overtime-weekday';
        if (actionSubType === 'work-overtime-weekend') return 'work-overtime-weekend';
        if (actionSubType === 'work-overtime') return 'work-overtime-weekday'; // 默认工作日加班
        return 'work-daily';
    }

    // 有子类型
    if (actionSubType) return actionSubType;

    // 没有子类型的维度
    return '';
}

/** 获取提交的 duration（固定值子类型返回0） */
function getSubmitDuration(catId) {
    if (!catId) return actionDuration;
    var subType = getSubmitSubType(catId);
    var fixedTypes = [
        'relation-offline', 'work-daily', 'work-overtime-weekday', 'work-overtime-weekend',
        'create-publish', 'finance-review', 'health-sleep',
    ];
    if (fixedTypes.indexOf(subType) !== -1) return 0;
    return actionDuration;
}

/** 渲染动态表单区域（子类型/时长/备注/按钮），分类改变时只更新这个区域 */
function renderDynamicForm() {
    if (!selectedActionCategory) return '';

    var pad2 = function(n) { return String(n).padStart(2, '0'); };
    var endH = (actionStartHour + Math.floor((actionStartMin + actionDuration) / 60)) % 24;
    var endM = (actionStartMin + actionDuration) % 60;
    var startTimeStr = pad2(actionStartHour) + ':' + pad2(actionStartMin);
    var endTimeStr = pad2(endH) + ':' + pad2(endM);

    return (renderSubTypeArea(selectedActionCategory) || '') +
        (shouldShowDuration(selectedActionCategory, actionSubType) ? `
        <div>
            <div class="action-form__label">开始时间</div>
            <div class="qa-time-row">
                <input type="number" class="qa-time-input" min="0" max="23" value="${actionStartHour}"
                       onchange="actionStartHour=Math.min(23,Math.max(0,parseInt(this.value)||0));updateDynamicForm()">
                <span class="qa-time-colon">:</span>
                <input type="number" class="qa-time-input" min="0" max="59" value="${pad2(actionStartMin)}"
                       onchange="actionStartMin=Math.min(59,Math.max(0,parseInt(this.value)||0));updateDynamicForm()">
                <span class="qa-time-arrow">→</span>
                <span class="qa-time-end" id="end-time-display">${endTimeStr}</span>
                <span class="qa-time-hint">结束时间</span>
            </div>
        </div>

        <!-- Duration -->
        <div>
            <div class="action-form__label">投入时长（分钟）</div>
            <div class="qa-duration-row">
                <input type="range" min="0" max="100" value="${minToSlider(actionDuration)}" step="1"
                       style="flex:1;accent-color:var(--color-primary)"
                       id="duration-slider"
                       oninput="sliderChange(parseInt(this.value))">
                <input type="number" class="qa-duration-input" min="1" max="300" value="${actionDuration}"
                       id="duration-num"
                       onchange="numChange(Math.max(1,Math.min(300,parseInt(this.value)||5)))">
                <span class="qa-duration-unit">分钟</span>
            </div>
            <div style="text-align:center;font-size:20px;font-weight:700;margin-top:8px;color:var(--color-primary-light)" id="duration-val">${actionDuration}分钟</div>
        </div>
        ` : '') + `
        <div>
            <div class="action-form__label">备注（可选）</div>
            <textarea class="input" placeholder="记录一些心得..." id="action-note"
                      oninput="actionNote=this.value">${actionNote}</textarea>
        </div>

        <button class="btn btn--primary btn--lg" style="width:100%" onclick="submitAction()">
            ⭐ 记录努力 ${getActionButtonPreview(selectedActionCategory, actionSubType, actionDuration)}
        </button>
    `;
}

/** 局部更新动态表单区域，不重绘整个页面 */
function updateDynamicForm() {
    var container = document.getElementById('qa-dynamic-form');
    if (container) {
        container.innerHTML = renderDynamicForm();
    }
    // 同步更新结束时间显示（如果 end-time-display 在容器外）
    var endEl = document.getElementById('end-time-display');
    if (endEl) {
        var pad2 = function(n) { return String(n).padStart(2, '0'); };
        var endH = (actionStartHour + Math.floor((actionStartMin + actionDuration) / 60)) % 24;
        var endM = (actionStartMin + actionDuration) % 60;
        endEl.textContent = pad2(endH) + ':' + pad2(endM);
    }
}

// ================================================================
// AI 描述记录模式 — 聊天界面
// ================================================================

/** 渲染描述记录模式 */
function renderDescribeMode() {
    var chatHistoryHtml = actionChatMessages.length === 0
        ? '<div class="qa-chat-welcome">' +
            '<div style="font-size:24px;margin-bottom:8px">🤖</div>' +
            '<div style="font-weight:600;margin-bottom:4px">描述你做了什么</div>' +
            '<div style="font-size:13px;color:var(--color-text-muted)">用自然语言告诉我你今天做了什么，我来帮你记录！<br>例如：<em>"下午学习了2小时React，晚上跑了30分钟步"</em></div>' +
          '</div>'
        : actionChatMessages.map(function(m) {
            return '<div class="qa-chat-msg qa-chat-msg--' + m.role + '">' +
                '<div class="qa-chat-msg__avatar">' + (m.role === 'user' ? '👤' : '🤖') + '</div>' +
                '<div class="qa-chat-msg__bubble">' + escapeHtml(m.content) + '</div>' +
                '</div>';
          }).join('');

    var previewHtml = '';
    if (actionChatPendingSubmit) {
        previewHtml = renderEditablePreview();
    }

    var inputRowDisplay = actionChatPendingSubmit ? 'none' : 'flex';
    var actionBtnsDisplay = actionChatPendingSubmit ? 'flex' : 'none';
    var actionCount = actionChatPendingSubmit ? actionChatPendingSubmit.length : 0;

    return '<div class="qa-chat-history" id="chat-history">' +
        chatHistoryHtml +
        previewHtml +
        '</div>' +
        '<div class="qa-chat-input-row" id="chat-input-row" style="display:' + inputRowDisplay + '">' +
        '<textarea class="input qa-chat-input" placeholder="描述你做了什么..." id="chat-input" ' +
        'onkeydown="if(event.key===\'Enter\'&&!event.shiftKey){event.preventDefault();sendChatMessage()}"></textarea>' +
        '<button class="btn btn--primary" onclick="sendChatMessage()" id="chat-send-btn">发送</button>' +
        '</div>' +
        '<div id="chat-actions" style="display:' + actionBtnsDisplay + ';gap:10px;margin-top:12px">' +
        '<button class="btn" style="flex:1" onclick="resetChat()">重新描述</button>' +
        '<button class="btn btn--primary" style="flex:2" onclick="confirmAISubmit()">' +
        '✅ 确认提交' + (actionCount > 0 ? ' (' + actionCount + '条)' : '') +
        '</button>' +
        '</div>';
}

/** 渲染可编辑的预览卡片 */
function renderEditablePreview() {
    if (!actionChatPendingSubmit || actionChatPendingSubmit.length === 0) return '';

    var items = actionChatPendingSubmit.map(function(a, i) {
        var cat = getCategory(a.category_id);
        var catName = cat ? cat.name : a.category_id;
        var globalRate = cat ? cat.globalRate : 1.0;
        var globalExp = Math.floor(a.dimension_exp * globalRate);

        var catOptions = AppData.categories.map(function(c) {
            var selected = c.id === a.category_id ? 'selected' : '';
            return '<option value="' + c.id + '" ' + selected + '>' + c.name + '</option>';
        }).join('');

        var subTypeHtml = '';
        if (a.sub_type) {
            subTypeHtml = '<span class="qa-preview-subtype" style="color:var(--color-text-muted);font-size:11px">' +
                escapeHtml(a.sub_type) + '</span>';
        }

        return '<div class="qa-preview-item" data-index="' + i + '">' +
            '<div class="qa-preview-item__header">' +
            '<select class="qa-preview-category" data-index="' + i + '" ' +
            'onchange="editPreviewItem(' + i + ', \'category_id\', this.value)">' +
            catOptions +
            '</select>' +
            '<span class="qa-preview-item__exp">' +
            '<span class="qa-preview-exp-val">' + Math.round(a.dimension_exp) + '</span> 维度EXP ' +
            '→ <span class="qa-preview-global">' + globalExp + '</span> 全局EXP' +
            '</span>' +
            '</div>' +
            '<textarea class="input qa-preview-note" data-index="' + i + '" ' +
            'onchange="editPreviewItem(' + i + ', \'note\', this.value)">' + escapeHtml(a.note || '') + '</textarea>' +
            '<div class="qa-preview-item__footer" style="display:flex;gap:12px;align-items:center;margin-top:6px">' +
            '<label style="font-size:13px;color:var(--color-text-secondary)">时长：' +
            '<input type="number" class="qa-preview-duration" value="' + (a.duration || 0) + '" min="0" max="600" ' +
            'data-index="' + i + '" ' +
            'onchange="editPreviewItem(' + i + ', \'duration\', parseInt(this.value)||0)" ' +
            'style="width:60px;padding:4px 6px;border-radius:6px;border:1px solid rgba(255,255,255,0.1);background:rgba(255,255,255,0.05);color:inherit;text-align:center"> 分钟' +
            '</label>' +
            subTypeHtml +
            '</div>' +
            '</div>';
    }).join('');

    var summaryText = actionChatSummary
        ? escapeHtml(actionChatSummary)
        : '📋 已识别到以下记录，请确认或修改';

    return '<div class="qa-preview-panel" style="margin-top:12px">' +
        '<div class="qa-preview-panel__title" style="font-size:14px;font-weight:600;margin-bottom:10px;color:var(--color-accent-light)">' +
        summaryText +
        '</div>' +
        '<div class="qa-preview-list" style="display:flex;flex-direction:column;gap:8px">' + items + '</div>' +
        '</div>';
}

/** 编辑预览项 */
function editPreviewItem(index, field, value) {
    if (!actionChatPendingSubmit) return;
    actionChatPendingSubmit[index][field] = value;
    // 更新 EXP 显示
    var item = actionChatPendingSubmit[index];
    var cat = getCategory(item.category_id);
    if (cat) {
        var globalExp = Math.floor((item.dimension_exp || 0) * cat.globalRate);
        var expEl = document.querySelector('.qa-preview-item[data-index="' + index + '"] .qa-preview-global');
        if (expEl) expEl.textContent = globalExp;
    }
}

/** 发送聊天消息 */
async function sendChatMessage() {
    var input = document.getElementById('chat-input');
    var text = input.value.trim();
    if (!text) return;

    input.value = '';
    actionChatMessages.push({ role: 'user', content: text });
    renderChatHistory();
    scrollChatToBottom();

    var sendBtn = document.getElementById('chat-send-btn');
    sendBtn.disabled = true;
    sendBtn.textContent = '思考中...';

    var curUser = getCurrentUser();
    if (!curUser) { showToast('请先登录', 'error'); return; }

    var result = await fetchAIActionChat(curUser.id, actionChatMessages);

    if (result && result.content) {
        // AI 纯文本回复（反问或确认）
        actionChatMessages.push({ role: 'assistant', content: result.content });
    } else if (result && result.tool_calls) {
        // 检查是否有 submit_actions
        var submitCall = result.tool_calls.find(function(tc) { return tc.name === 'submit_actions'; });
        if (submitCall) {
            actionChatPendingSubmit = submitCall.arguments.actions;
            actionChatSummary = submitCall.arguments.summary || '';
            // 如果 AI 同时也发了 send_message，加入对话
            var msgCall = result.tool_calls.find(function(tc) { return tc.name === 'send_message'; });
            if (msgCall) {
                actionChatMessages.push({ role: 'assistant', content: msgCall.arguments.content });
            }
        } else {
            // send_message 反问
            var msgCall2 = result.tool_calls.find(function(tc) { return tc.name === 'send_message'; });
            if (msgCall2) {
                actionChatMessages.push({ role: 'assistant', content: msgCall2.arguments.content });
            }
        }
    } else {
        showToast('AI 服务暂时不可用，请稍后重试', 'error');
    }

    renderChatHistory();
    sendBtn.disabled = false;
    sendBtn.textContent = '发送';
    scrollChatToBottom();
}

/** 确认提交 */
async function confirmAISubmit() {
    if (!actionChatPendingSubmit || actionChatPendingSubmit.length === 0) return;

    var curUser = getCurrentUser();
    if (!curUser) { showToast('请先登录', 'error'); return; }

    // 从 DOM 中收集编辑后的值
    var actions = actionChatPendingSubmit.map(function(a) {
        return {
            category_id: a.category_id,
            sub_type: a.sub_type || '',
            duration: a.duration || 0,
            note: a.note || '',
            dimension_exp: a.dimension_exp || 0,
            sleep_start: a.sleep_start || '',
            sleep_end: a.sleep_end || '',
        };
    });

    var result = await submitAIActions(curUser.id, actions);
    if (result && result.records) {
        AppData.todayStats = result.today_stats;
        AppData.user.exp = result.exp_result.exp;
        AppData.user.level = result.exp_result.level;
        AppData.user.totalExp = result.exp_result.totalExp;

        showToast('🎉 成功记录 ' + result.records.length + ' 条行动！', 'success');

        // 重置对话
        actionChatMessages = [];
        actionChatPendingSubmit = null;
        actionChatSummary = '';
        renderQuickAction();
    } else {
        showToast('提交失败，请重试', 'error');
    }
}

/** 重置对话 */
function resetChat() {
    actionChatMessages = [];
    actionChatPendingSubmit = null;
    actionChatSummary = '';
    renderChatHistory();
}

/** 渲染聊天历史 */
function renderChatHistory() {
    var container = document.getElementById('chat-history');
    if (!container) return;
    // 重新渲染整个描述模式区域
    var actionForm = container.closest('.action-form');
    if (actionForm) {
        actionForm.innerHTML = renderDescribeMode();
    }
}

/** 滚动到底部 */
function scrollChatToBottom() {
    var history = document.getElementById('chat-history');
    if (history) {
        history.scrollTop = history.scrollHeight;
    }
}

function selectCategory(catId) {
    selectedActionCategory = catId;
    // 重置子类型状态
    actionSubType = '';
    actionSleepStart = '';
    actionSleepEnd = '';
    actionWorkExtra = '';

    // 工作维度：按日期默认
    if (catId === 'work') {
        var today = new Date();
        var dayOfWeek = today.getDay();
        if (dayOfWeek === 0 || dayOfWeek === 6) {
            actionSubType = 'work-overtime';
            actionWorkExtra = 'work-overtime-weekend';
        } else {
            actionSubType = 'work-daily';
        }
    }

    // 更新分类按钮的选中样式
    var allCats = document.querySelectorAll('.action-category-item');
    allCats.forEach(function(el) { el.classList.remove('action-category-item--selected'); });
    var activeEl = document.getElementById('cat-' + catId);
    if (activeEl) activeEl.classList.add('action-category-item--selected');

    // 局部更新动态表单
    updateDynamicForm();
}

function submitAction() {
    if (!selectedActionCategory) {
        showToast('请先选择一个分类', 'error');
        return;
    }
    const cat = getCategory(selectedActionCategory);

    // 检查子类型选择
    const rule = DIMENSION_RULES[selectedActionCategory];
    if (rule && rule.hasSubTypes) {
        // 健康维度需要判断睡眠/运动
        if (selectedActionCategory === 'health') {
            if (!actionSleepStart && !actionSleepEnd) {
                // 运动模式，不需要额外检查
            } else if (!actionSleepStart || !actionSleepEnd) {
                showToast('请填写完整的睡眠时间（睡觉和起床时间）', 'error');
                return;
            }
        } else if (!actionSubType && !actionWorkExtra) {
            showToast('请选择具体类型', 'error');
            return;
        }
    }

    const subType = getSubmitSubType(selectedActionCategory);
    const submitDuration = getSubmitDuration(selectedActionCategory);

    // 构建开始时间
    const now = new Date();
    const startTime = new Date(now);
    startTime.setHours(actionStartHour, actionStartMin, 0, 0);
    const pad2 = n => String(n).padStart(2, '0');
    const startTimeStr = pad2(actionStartHour) + ':' + pad2(actionStartMin);
    const endH = (actionStartHour + Math.floor((actionStartMin + submitDuration) / 60)) % 24;
    const endM = (actionStartMin + submitDuration) % 60;
    const endTimeStr = pad2(endH) + ':' + pad2(endM);

    // 获取子类型名称
    var subTypeName = '';
    if (rule && rule.subTypes) {
        var found = rule.subTypes.find(function(st) { return st.id === subType; });
        if (found) subTypeName = found.label;
    }

    // 计算 EXP 预览
    var expPreview = getActionButtonPreview(selectedActionCategory, subType, submitDuration);

    // 确认弹窗内容
    var confirmHtml = `
        <div style="display:flex;flex-direction:column;gap:14px;padding:8px 0">
            <div style="display:flex;align-items:center;gap:12px;padding:12px 16px;background:rgba(255,255,255,0.03);border-radius:12px">
                <span style="font-size:32px">${attrIcon(cat.id, 40)}</span>
                <div>
                    <div style="font-size:16px;font-weight:700">${cat.name}${subTypeName ? ' · ' + subTypeName : ''}</div>
                    <div style="font-size:12px;color:var(--color-text-secondary);margin-top:2px">${startTimeStr} → ${endTimeStr}${submitDuration > 0 ? ' · ' + submitDuration + '分钟' : ''}</div>
                </div>
            </div>
            ${actionNote ? `
            <div style="padding:10px 14px;background:rgba(255,255,255,0.03);border-radius:8px;font-size:13px;color:var(--color-text-secondary)">
                📝 ${escapeHtml(actionNote)}
            </div>
            ` : ''}
            <div style="display:flex;justify-content:space-between;align-items:center;padding:8px 4px">
                <span style="font-size:14px;color:var(--color-text-secondary)">预计获得</span>
                <span style="font-size:22px;font-weight:800;color:var(--color-accent-light)">${expPreview}</span>
            </div>
            <div style="display:flex;gap:10px;margin-top:4px">
                <button class="btn" style="flex:1;padding:12px;border-radius:10px;font-size:15px" onclick="closeModal()">取消</button>
                <button class="btn btn--primary" style="flex:2;padding:12px;border-radius:10px;font-size:15px;font-weight:700" onclick="confirmSubmitAction()">✅ 确认记录</button>
            </div>
        </div>
    `;

    // 保存 payload 到全局，供 confirmSubmitAction 使用
    const startIso = startTime.toISOString().replace('Z', '');
    window._pendingActionPayload = {
        category_id: selectedActionCategory,
        start_time: startIso,
        duration: submitDuration,
        note: actionNote || '',
        sub_type: subType,
    };
    if (actionSleepStart && actionSleepEnd) {
        window._pendingActionPayload.sleep_start = actionSleepStart;
        window._pendingActionPayload.sleep_end = actionSleepEnd;
    }

    openModal('📋 确认记录', confirmHtml, false);
}

/** 确认提交行动记录 */
function confirmSubmitAction() {
    closeModal();
    var payload = window._pendingActionPayload;
    if (!payload) return;
    window._pendingActionPayload = null;

    var cat = getCategory(payload.category_id);
    var curUser = getCurrentUser();
    if (!curUser) {
        showToast('请先登录', 'error');
        return;
    }

    submitActionToBackend(curUser.id, payload).then(function(result) {
        if (result) {
            AppData.todayStats.focusMinutes = result.today_stats.focusMinutes;
            AppData.todayStats.tasksDone = result.today_stats.tasksDone;
            AppData.todayStats.habitsChecked = result.today_stats.habitsChecked;
            AppData.todayStats.expEarned = result.today_stats.expEarned;
            AppData.user.exp = result.exp_result.exp;
            AppData.user.level = result.exp_result.level;
            AppData.user.totalExp = result.exp_result.totalExp;

            actionNote = '';
            var expMsg = result.exp_earned + ' EXP';
            if (result.dimension_exp) {
                expMsg = result.dimension_exp + '→全局' + result.exp_earned + ' EXP';
            }
            showToast('记录成功！' + cat.name + ' · +' + expMsg, 'success');

            if (result.exp_result.leveledUp) {
                setTimeout(function() {
                    showToast('🎉 升级！Lv.' + result.exp_result.oldLevel + ' → Lv.' + result.exp_result.level, 'success');
                }, 500);
            }

            var newNow = new Date();
            actionStartHour = newNow.getHours();
            actionStartMin = newNow.getMinutes();
            actionSleepStart = '';
            actionSleepEnd = '';

            renderQuickAction();

            var curUserId = AppData.user && AppData.user.id;
            if (curUserId) reevaluateRewardsOnBackend(curUserId);
        } else {
            showToast('后端暂不可用，请稍后重试', 'error');
        }
    }).catch(function() {
        showToast('后端暂不可用，请稍后重试', 'error');
    });
}

/* ---- 行动历史卡片（开始行动页面右侧） ---- */
function renderActionHistoryCard() {
    // 尝试从后端获取最近行动，降级到本地
    return '<div class="card qa-history-card" id="recent-actions-card">' +
        '<div class="section__title">' +
            '<span class="section__title-icon">' + ACTION_ICONS.recent_actions + '</span>' +
            '最近行动' +
        '</div>' +
        '<div class="qa-history-list" id="recent-actions-list">' +
            '<div style="text-align:center;padding:20px;color:var(--color-text-secondary)">加载中...</div>' +
        '</div>' +
        '<div class="qa-history-tip">' +
            '💡 查看完整历史记录、搜索和筛选，请前往 <a href="javascript:void(0)" onclick="navigateTo(\'action\',\'history\')" style="color:var(--color-accent-light);text-decoration:underline">行动历史</a> 板块' +
        '</div>' +
    '</div>';
}

/** 三层叠加进度条：每轮200EXP，三轮共600EXP封顶 */
function renderTripleProgress(expEarned) {
    var ROUND_MAX = 200;
    var MAX_TOTAL = 600;
    var total = Math.min(expEarned, MAX_TOTAL);
    var isMaxed = expEarned >= MAX_TOTAL;

    // 计算每一层的宽度（%）
    var layer1 = Math.min(total / ROUND_MAX, 1) * 100;
    var layer2 = total > ROUND_MAX
        ? Math.min((total - ROUND_MAX) / ROUND_MAX, 1) * 100
        : 0;
    var layer3 = total > ROUND_MAX * 2
        ? Math.min((total - ROUND_MAX * 2) / ROUND_MAX, 1) * 100
        : 0;

    // 当前轮次信息（用于文字显示）
    var currentRound, currentExp, pct, roundColor;
    if (total <= ROUND_MAX) {
        currentRound = 1;
        currentExp = total;
        pct = Math.round(layer1);
        roundColor = '#A8DDD1';
    } else if (total <= ROUND_MAX * 2) {
        currentRound = 2;
        currentExp = total - ROUND_MAX;
        pct = Math.round(layer2);
        roundColor = '#B2C9EC';
    } else {
        currentRound = 3;
        currentExp = total - ROUND_MAX * 2;
        pct = Math.round(layer3);
        roundColor = '#C9BBE8';
    }

    var roundLabel = isMaxed
        ? '🏆 今日满贯'
        : ['🥉 第一轮', '🥈 第二轮', '🥇 第三轮'][currentRound - 1];

    // 满贯时三层全100%，否则按实际宽度显示
    var w1 = isMaxed ? 100 : layer1;
    var w2 = isMaxed ? 100 : layer2;
    var w3 = isMaxed ? 100 : layer3;

    // 下层宽度取 max(自身宽度, 上层宽度)，保证下层不会被上层"缩短"
    var baseW1 = Math.max(w1, w2 > 0 ? 100 : 0, w3 > 0 ? 100 : 0);
    var baseW2 = Math.max(w2, w3 > 0 ? 100 : 0);

    return `
        <div>
            <div style="display:flex;justify-content:space-between;margin-bottom:6px;font-size:12px">
                <span style="color:var(--color-text-muted)">${roundLabel}</span>
                <span style="font-weight:600;color:${isMaxed ? '#C9BBE8' : roundColor}">${isMaxed ? '100%' : pct + '%'}</span>
            </div>
            <div style="position:relative;height:10px;border-radius:4px;background:rgba(42,51,50,0.6);overflow:hidden">
                <!-- 第一层：薄荷 #86C9B8 -->
                <div style="position:absolute;top:0;left:0;height:100%;width:${baseW1}%;border-radius:4px;background:rgba(134,201,184,0.95);transition:width 0.6s ease;z-index:1"></div>
                <!-- 第二层：蓝色 #729CD9 -->
                <div style="position:absolute;top:0;left:0;height:100%;width:${baseW2}%;border-radius:4px;background:rgba(114,156,217,0.95);transition:width 0.6s ease;z-index:2"></div>
                <!-- 第三层：紫色 #A893D4 -->
                <div style="position:absolute;top:0;left:0;height:100%;width:${w3}%;border-radius:4px;background:rgba(168,147,212,0.95);transition:width 0.6s ease;z-index:3"></div>
            </div>
            <div style="display:flex;justify-content:space-between;margin-top:4px;font-size:11px;color:var(--color-text-muted)">
                <span>${isMaxed ? '600/600 EXP' : currentExp + '/200 EXP'}</span>
                <span>${isMaxed ? '🎉 今日经验已拿满！' : '距下一轮 ' + (200 - currentExp) + ' EXP'}</span>
            </div>
        </div>
    `;
}
async function loadRecentActions() {
    const listEl = document.getElementById('recent-actions-list');
    if (!listEl) return;

    const curUser = getCurrentUser();
    if (curUser) {
        const result = await fetchActionTodayStats(curUser.id);
        if (result && result.recent_actions && result.recent_actions.length > 0) {
            renderRecentActionsList(listEl, result.recent_actions);
            return;
        }
    }
    // 无数据时的空状态
    listEl.innerHTML = '<div class="empty-state"><div class="empty-state__title">📭 暂无记录</div></div>';
}

/** 渲染最近行动列表 */
function renderRecentActionsList(container, records) {
    const pad2 = n => String(n).padStart(2, '0');
    const fmtDateTime = d => {
        const date = `${d.getFullYear()}/${pad2(d.getMonth() + 1)}/${pad2(d.getDate())}`;
        const time = `${pad2(d.getHours())}:${pad2(d.getMinutes())}`;
        return `${date} ${time}`;
    };

    const items = records.slice(0, 8).map(r => {
        let startDate = '--', startTime = '--', endHour = '--', endMin = '--';
        let duration = r.duration || 0;
        try {
            const sd = new Date(r.start_time);
            startDate = fmtDateTime(sd);
            startTime = `${pad2(sd.getHours())}:${pad2(sd.getMinutes())}`;
            const ed = new Date(r.end_time || new Date(sd.getTime() + duration * 60000));
            endHour = pad2(ed.getHours());
            endMin = pad2(ed.getMinutes());
        } catch (e) {}

        const exp = r.exp_earned || r.exp || 0;
        return `
            <div class="qa-history-item">
                <div class="qa-history-item__left">
                    <span class="qa-history-item__icon">${attrIcon(r.category_id, 20)}</span>
                    <div class="qa-history-item__info">
                        <span class="qa-history-item__cat">${r.category_name || ''}</span>
                        <span class="qa-history-item__time">${startDate} ${startTime} → ${endHour}:${endMin} · ${duration}分钟</span>
                        <span class="qa-history-item__note" title="${escapeHtml(r.note || '')}">${r.note || '(无备注)'}</span>
                    </div>
                </div>
                <span class="qa-history-item__exp">+${exp}</span>
            </div>
        `;
    }).join('');

    container.innerHTML = items || '<div class="empty-state"><div class="empty-state__title">📭 暂无记录</div></div>';
}

/** 从后端加载今日分类分布并更新 DOM */
async function loadCategoryDistribution() {
    const fills = document.querySelectorAll('.cat-dist-fill');
    const pcts = document.querySelectorAll('.cat-dist-pct');
    const exps = document.querySelectorAll('.cat-dist-exp');
    if (!fills.length) return;

    const curUser = getCurrentUser();
    if (!curUser) return;

    const result = await fetchActionTodayStats(curUser.id);
    if (!result || !result.category_dist) return;

    // 计算每个维度的全局经验贡献
    var catGlobalExp = {};
    var totalGlobalExp = 0;
    result.category_dist.forEach(function(cd) {
        var cat = getCategory(cd.category_id);
        var globalRate = cat ? cat.globalRate : 1.0;
        var globalExp = Math.floor(cd.exp * globalRate);
        catGlobalExp[cd.category_id] = globalExp;
        totalGlobalExp += globalExp;
    });

    fills.forEach(function(el) {
        var catId = el.dataset.cat;
        var globalExp = catGlobalExp[catId] || 0;
        var pct = totalGlobalExp > 0 ? Math.round((globalExp / totalGlobalExp) * 100) : 0;
        el.style.width = pct + '%';
    });
    pcts.forEach(function(el) {
        var catId = el.dataset.cat;
        var globalExp = catGlobalExp[catId] || 0;
        var pct = totalGlobalExp > 0 ? Math.round((globalExp / totalGlobalExp) * 100) : 0;
        el.textContent = pct + '%';
    });
    exps.forEach(function(el) {
        var catId = el.dataset.cat;
        var globalExp = catGlobalExp[catId] || 0;
        el.textContent = '+' + globalExp + ' EXP';
    });
}

/* ================================================================
   子板块二：行动历史 — 完整历史记录（搜索/筛选/排序/分页）
   ================================================================ */
let historyPage = 1;
const HISTORY_PAGE_SIZE = 20;
let historyFilterCategory = 'all';
let historySortBy = 'newest';        // newest | oldest | exp-desc | exp-asc | duration-desc | duration-asc
let historySearchQuery = '';
let historyDateFrom = '';
let historyDateTo = '';

function renderActionHistory() {
    const cats = AppData.categories;
    const pad2 = n => String(n).padStart(2, '0');
    const fmtDate = d => `${d.getFullYear()}/${pad2(d.getMonth() + 1)}/${pad2(d.getDate())}`;
    const fmtTime = d => `${pad2(d.getHours())}:${pad2(d.getMinutes())}`;

    // 从后端加载数据
    var curUser = getCurrentUser();
    if (curUser) {
        loadActionHistoryFromBackend(curUser, cats, pad2, fmtDate, fmtTime);
    } else {
        showToast('请先登录', 'error');
    }
}

/** 后端模式：加载行动历史 */
async function loadActionHistoryFromBackend(curUser, cats, pad2, fmtDate, fmtTime) {
    const params = { page: historyPage, page_size: HISTORY_PAGE_SIZE };
    if (historyFilterCategory !== 'all') params.category = historyFilterCategory;
    if (historySortBy !== 'newest') params.sort = historySortBy;
    if (historySearchQuery.trim()) params.search = historySearchQuery.trim();
    if (historyDateFrom) params.date_from = historyDateFrom;
    if (historyDateTo) params.date_to = historyDateTo;

    const result = await fetchActions(curUser.id, params);
    if (result) {
        renderActionHistoryTable(result, cats, pad2, fmtDate, fmtTime);
    } else {
        showToast('后端暂不可用，无法加载历史记录', 'error');
    }
}

/** 渲染行动历史表格（通用，后端数据和本地降级共用） */
function renderActionHistoryTable(result, cats, pad2, fmtDate, fmtTime) {
    const totalPages = Math.max(1, Math.ceil(result.total / result.page_size));
    const records = result.records || [];
    const totalMinutes = result.total_duration || 0;
    const totalXP = result.total_exp || 0;

    // 格式化记录
    const rows = records.length === 0
        ? `<tr><td colspan="7" class="ac-task-empty">没有匹配的记录</td></tr>`
        : records.map(r => {
            const startStr = r.start_time || '';
            const endStr = r.end_time || '';
            let sDate = '--', sTime = '--', eTime = '--';
            try {
                const sd = new Date(startStr);
                sDate = fmtDate(sd);
                sTime = fmtTime(sd);
            } catch (e) {}
            try {
                const ed = new Date(endStr);
                eTime = fmtTime(ed);
            } catch (e) {}

            return `
            <tr class="ac-task-row">
                <td class="ac-task-cell ac-task-cell--task">${sDate}</td>
                <td class="ac-task-cell ac-task-cell--attr">
                    <span class="ac-task-attr">${attrIcon(r.category_id, 18)} ${r.category_name || ''}</span>
                </td>
                <td class="ac-task-cell ac-task-cell--num">${sTime}</td>
                <td class="ac-task-cell ac-task-cell--num">${eTime}</td>
                <td class="ac-task-cell ac-task-cell--num">${r.duration}分钟</td>
                <td class="ac-task-cell ac-task-cell--note">
                    <span class="qa-history-item__note" title="${escapeHtml(r.note || '')}" style="max-width:200px;display:inline-block">${r.note || '—'}</span>
                </td>
                <td class="ac-task-cell ac-task-cell--xp">
                    <span class="ac-task-xp">+${r.exp_earned}</span>
                </td>
            </tr>
        `}).join('');

    // 分页按钮
    let paginationHtml = '';
    if (totalPages > 1) {
        const pages = [];
        for (let i = 1; i <= totalPages; i++) {
            if (i === 1 || i === totalPages || (i >= historyPage - 2 && i <= historyPage + 2)) {
                pages.push(i);
            } else if (pages[pages.length - 1] !== -1) {
                pages.push(-1);
            }
        }
        paginationHtml = pages.map(p => {
            if (p === -1) return '<span class="ah-pager-dots">…</span>';
            return `<button class="ah-pager-btn ${p === historyPage ? 'ah-pager-btn--active' : ''}"
                          onclick="historyPage=${p};renderActionHistory()">${p}</button>`;
        }).join('');
    }

    const html = `
        <div class="page-header page-header--with-icon">
            <div class="page-header__icon">${ACTION_ICONS.history_title}</div>
            <div>
                <h1 class="page-header__title">行动历史</h1>
                <p class="page-header__subtitle">共 ${result.total} 条记录 · 累计 ${formatMinutes(totalMinutes)} · 获得 ${totalXP} EXP</p>
            </div>
        </div>

        <!-- Stats row -->
        <div class="ah-stats-row">
            <div class="ah-stat-chip">
                <span class="ah-stat-chip__label">总记录</span>
                <span class="ah-stat-chip__value">${result.total}</span>
            </div>
            <div class="ah-stat-chip">
                <span class="ah-stat-chip__label">累计时长</span>
                <span class="ah-stat-chip__value">${formatMinutes(totalMinutes)}</span>
            </div>
            <div class="ah-stat-chip">
                <span class="ah-stat-chip__label">累计EXP</span>
                <span class="ah-stat-chip__value ah-stat-chip__value--xp">${totalXP}</span>
            </div>
        </div>

        <!-- Filters -->
        <div class="card ah-filter-card">
            <div class="ah-filter-row">
                <div class="ah-search-wrapper">
                    <span class="ah-search-icon">${ACTION_ICONS.search}</span>
                    <input type="text" class="input ah-search-input" placeholder="搜索备注或分类..." value="${escapeHtml(historySearchQuery)}"
                           oninput="historySearchQuery=this.value;historyPage=1;renderActionHistory()">
                </div>
                <select class="ac-mini-select" onchange="historyFilterCategory=this.value;historyPage=1;renderActionHistory()">
                    <option value="all" ${historyFilterCategory === 'all' ? 'selected' : ''}>全部分类</option>
                    ${cats.map(c => `<option value="${c.id}" ${historyFilterCategory === c.id ? 'selected' : ''}>${c.name}</option>`).join('')}
                </select>
                <select class="ac-mini-select" onchange="historySortBy=this.value;historyPage=1;renderActionHistory()">
                    <option value="newest" ${historySortBy === 'newest' ? 'selected' : ''}>最新优先</option>
                    <option value="oldest" ${historySortBy === 'oldest' ? 'selected' : ''}>最早优先</option>
                    <option value="exp-desc" ${historySortBy === 'exp-desc' ? 'selected' : ''}>EXP高→低</option>
                    <option value="exp-asc" ${historySortBy === 'exp-asc' ? 'selected' : ''}>EXP低→高</option>
                    <option value="duration-desc" ${historySortBy === 'duration-desc' ? 'selected' : ''}>时长高→低</option>
                    <option value="duration-asc" ${historySortBy === 'duration-asc' ? 'selected' : ''}>时长低→高</option>
                </select>
                <input type="date" class="ah-date-input" value="${historyDateFrom}"
                       onchange="historyDateFrom=this.value;historyPage=1;renderActionHistory()" title="开始日期">
                <span class="ah-date-sep">至</span>
                <input type="date" class="ah-date-input" value="${historyDateTo}"
                       onchange="historyDateTo=this.value;historyPage=1;renderActionHistory()" title="结束日期">
            </div>
        </div>

        <!-- Table -->
        <div class="card ah-table-card">
            <div class="ac-task-table-wrap">
                <table class="ac-task-table">
                    <thead>
                        <tr class="ac-task-head-row">
                            <th class="ac-task-th ac-task-th--date">日期</th>
                            <th class="ac-task-th">分类</th>
                            <th class="ac-task-th ac-task-th--num">开始</th>
                            <th class="ac-task-th ac-task-th--num">结束</th>
                            <th class="ac-task-th ac-task-th--num">时长</th>
                            <th class="ac-task-th">备注</th>
                            <th class="ac-task-th ac-task-th--xp">奖励EXP</th>
                        </tr>
                    </thead>
                    <tbody>${rows}</tbody>
                </table>
            </div>
            ${totalPages > 1 ? `
            <div class="ah-pager">
                <button class="ah-pager-btn" onclick="historyPage=1;renderActionHistory()" ${historyPage === 1 ? 'disabled' : ''}>«</button>
                <button class="ah-pager-btn" onclick="historyPage=Math.max(1,historyPage-1);renderActionHistory()" ${historyPage === 1 ? 'disabled' : ''}>‹</button>
                ${paginationHtml}
                <button class="ah-pager-btn" onclick="historyPage=Math.min(${totalPages},historyPage+1);renderActionHistory()" ${historyPage === totalPages ? 'disabled' : ''}>›</button>
                <button class="ah-pager-btn" onclick="historyPage=${totalPages};renderActionHistory()" ${historyPage === totalPages ? 'disabled' : ''}>»</button>
            </div>
            ` : ''}
        </div>
    `;

    document.getElementById('page-action').innerHTML = html;
}

/* ================================================================
   子板块三：行动中心 — 4模块数据看板
   ================================================================ */
function renderActionCenter() {
    const html = `
        <div class="page-header page-header--with-icon">
            <div class="page-header__icon">${ACTION_ICONS.center_title}</div>
            <div>
                <h1 class="page-header__title">行动中心</h1>
                <p class="page-header__subtitle">全面追踪你的成长数据</p>
            </div>
        </div>

        <!-- 上半部分：模块一（左50%）+ 模块二（右50%） -->
        <div class="ac-top-row">
            <div class="card ac-level-card" id="ac-level-progress">
                <div style="text-align:center;padding:30px;color:var(--color-text-secondary)">加载中...</div>
            </div>
            <div class="card ac-activity-card" id="ac-activity-feed">
                <div style="text-align:center;padding:30px;color:var(--color-text-secondary)">加载中...</div>
            </div>
        </div>

        <!-- 下半部分：模块三（左~55%）+ 模块四（右~45%） -->
        <div class="ac-bottom-row">
            ${renderModule3_HabitCheckin()}
            ${renderModule4_GoalTracker()}
        </div>

        <!-- 模块五：本周任务（全宽表格） -->
        <div class="card ac-task-module" id="ac-weekly-tasks">
            <div style="text-align:center;padding:30px;color:var(--color-text-secondary)">加载中...</div>
        </div>

        <!-- 模块二弹出放大面板 -->
        <div class="ac-activity-overlay" id="activity-overlay" style="display:none" onclick="closeActivityModal(event)">
            <div class="ac-activity-panel" onclick="event.stopPropagation()">
                <div class="ac-activity-panel__header">
                    <span class="ac-activity-panel__title">动态播报</span>
                    <div class="ac-activity-panel__actions">
                        <select class="ac-mini-select" onchange="actionCenterActivityFilter=this.value;refreshActivityModal()">
                            <option value="all">全部</option>
                            <option value="health">健康</option>
                            <option value="study">学习</option>
                            <option value="relation">关系</option>
                            <option value="work">工作</option>
                            <option value="create">创作</option>
                            <option value="finance">财务</option>
                            <option value="hobby">爱好</option>
                            <option value="soul">魅力</option>
                        </select>
                        <button class="ac-icon-btn" onclick="closeActivityModal()" title="关闭">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                        </button>
                    </div>
                </div>
                <div class="ac-activity-panel__body" id="activity-panel-body">
                    <div style="text-align:center;padding:20px;color:var(--color-text-secondary)">加载中...</div>
                </div>
            </div>
        </div>
    `;

    document.getElementById('page-action').innerHTML = html;

    // 异步加载各模块数据
    loadActionCenterData();
}

/** 异步加载行动中心数据 */
async function loadActionCenterData() {
    const curUser = getCurrentUser();
    if (!curUser) return;

    // 并行加载
    const [feedResult, goalsResult] = await Promise.all([
        fetchActivityFeed(curUser.id),
        fetchGoals(curUser.id),
    ]);

    // 更新 AppData.goals（供模块四目标追踪使用）
    if (goalsResult && goalsResult.goals) {
        AppData.goals = goalsResult.goals;
    }

    // 模块一：升级进度（从 AppData.profile.dimensions 读取，已由后端加载）
    const dimensions = AppData.profile?.dimensions || [];
    const levelCard = document.getElementById('ac-level-progress');
    if (levelCard) {
        levelCard.innerHTML = renderModule1_LevelProgress(dimensions);
    }

    // 模块二：动态播报
    const activities = (feedResult && feedResult.activities) || AppData.actionCenter.activities || [];
    const feedCard = document.getElementById('ac-activity-feed');
    if (feedCard) {
        feedCard.innerHTML = renderModule2_ActivityFeed(activities);
    }

    // 模块五：本周任务（从 AppData.tasks 映射，后端每日 03:00 自动刷新）
    const taskCard = document.getElementById('ac-weekly-tasks');
    if (taskCard) {
        // 优先用后端拉取的分页数据，降级到 AppData.tasks
        const tasksResult = await fetchAllTasks(curUser.id, { page_size: 50, sort: 'newest' }).catch(() => null);
        if (tasksResult && tasksResult.records && tasksResult.records.length > 0) {
            const mapped = tasksResult.records
                .filter(t => t.status === 'todo' || t.status === 'doing' || t.status === 'done')
                .map(t => ({
                    task: t.title,
                    attribute: t.category,
                    attrId: t.category,
                    targetValue: 1,
                    resultValue: t.claimed ? 1 : 0,
                    progress: t.claimed ? 100 : (t.status === 'done' ? 100 : 0),
                    status: t.status === 'done' ? 'completed' : (t.status === 'todo' ? 'pending' : 'in_progress'),
                    deadline: t.deadline || t.created_at?.slice(0, 10) || '',
                    rewardXP: t.exp || 0,
                    goal: t.intro || '',
                }));
            taskCard.innerHTML = renderModule5_WeeklyTasks(mapped);
        } else {
            // 降级：从 AppData.tasks 映射
            const fallbackTasks = [];
            ['todo', 'doing', 'done'].forEach(s => {
                (AppData.tasks[s] || []).forEach(t => {
                    fallbackTasks.push({
                        task: t.title,
                        attribute: t.category,
                        attrId: t.category,
                        targetValue: 1,
                        resultValue: t.claimed ? 1 : 0,
                        progress: t.claimed ? 100 : (t.status === 'done' ? 100 : 0),
                        status: t.status === 'done' ? 'completed' : (t.status === 'todo' ? 'pending' : 'in_progress'),
                        deadline: t.deadline || '',
                        rewardXP: t.exp || 0,
                        goal: t.intro || '',
                    });
                });
            });
            taskCard.innerHTML = renderModule5_WeeklyTasks(fallbackTasks);
        }
    }

    // 更新弹窗中的活动列表（如果有打开）
    refreshActivityModal();
}

/* ---- 模块一：升级进度条 ---- */
function renderModule1_LevelProgress(dimensions) {
    const maxCap = Math.max(...dimensions.map(d => d.xpToNext || d.xpCap || 150));
    const rows = dimensions.map(d => {
        const xpCap = d.xpToNext || d.xpCap || 150;
        const id = d.key || d.id;
        const pct = d.level >= 120 ? 100 : Math.min(100, Math.round((d.xp / xpCap) * 100));
        const color = d.color || 'var(--color-accent)';
        const xpDisplay = d.level >= 120 ? 'MAX' : d.xp;
        return `
            <div class="ac-level-row">
                <div class="ac-level-row__label">
                    <span class="ac-level-row__icon">${attrIcon(id, 22)}</span>
                    <span class="ac-level-row__name">${d.name}</span>
                    <span class="ac-level-row__lv">Lv${d.level}</span>
                </div>
                <div class="ac-level-row__bar-wrap">
                    <div class="ac-level-row__bar">
                        <div class="ac-level-row__fill" style="width:${pct}%;background:${color}"></div>
                    </div>
                </div>
                <span class="ac-level-row__xp">${xpDisplay}</span>
            </div>
        `;
    }).join('');

    return `
        <div class="card ac-level-card">
            <div class="ac-module-header">
                <span class="ac-module-header__title">
                    <span class="ac-module-header__icon">${ACTION_ICONS.level_progress}</span>
                    升级进度
                </span>
            </div>
            <div class="ac-level-list">
                ${rows}
            </div>
        </div>
    `;
}

/* ---- 模块二：动态播报 ---- */
function renderModule2_ActivityFeed(activities) {
    const filtered = actionCenterActivityFilter === 'all'
        ? activities
        : activities.filter(a => a.category === actionCenterActivityFilter);

    const listHtml = filtered.length === 0
        ? `<div class="empty-state"><div class="empty-state__title">📭 暂无记录</div><div class="empty-state__desc">快去开始行动吧！</div></div>`
        : filtered.map((a, i) => {
            const feedXp = a.exp_earned || a.xp || 0;
            const feedCat = a.category || a.category_id || '';
            return `
            <div class="ac-activity-item ${i < filtered.length - 1 ? 'ac-activity-item--divider' : ''}">
                <div class="ac-activity-item__left">
                    <span class="ac-activity-item__icon">${attrIcon(feedCat, 20)}</span>
                    <span class="ac-activity-item__cat">${a.category_name || ''}</span>
                </div>
                <div class="ac-activity-item__mid">
                    <span class="ac-activity-item__xp">EXP +${feedXp}</span>
                    <span class="ac-activity-item__desc">${a.description}</span>
                </div>
                <span class="ac-activity-item__time">${a.timestamp}</span>
            </div>
        `;}).join('');

    // Category filter options
    const catOptions = [
        { value: 'all', label: '全部' },
        { value: 'health', label: '健康' },
        { value: 'study', label: '学习' },
        { value: 'relation', label: '关系' },
        { value: 'work', label: '工作' },
        { value: 'create', label: '创作' },
        { value: 'finance', label: '财务' },
        { value: 'hobby', label: '爱好' },
        { value: 'soul', label: '魅力' },
    ];

    return `
        <div class="card ac-activity-card">
            <div class="ac-module-header">
                <span class="ac-module-header__title">
                    <span class="ac-module-header__icon">${ACTION_ICONS.activity_feed}</span>
                    动态播报
                </span>
                <div class="ac-module-header__actions">
                    <select class="ac-mini-select" onchange="actionCenterActivityFilter=this.value;reloadActionCenterActivityFeed()">
                        ${catOptions.map(o => `<option value="${o.value}" ${actionCenterActivityFilter === o.value ? 'selected' : ''}>${o.label}</option>`).join('')}
                    </select>
                    <button class="ac-icon-btn" onclick="openActivityModal()" title="放大查看">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="15 3 21 3 21 9"/><polyline points="9 21 3 21 3 15"/><line x1="21" y1="3" x2="14" y2="10"/><line x1="3" y1="21" x2="10" y2="14"/></svg>
                    </button>
                </div>
            </div>
            <div class="ac-activity-list">
                ${listHtml}
            </div>
        </div>
    `;
}

/* ---- 模块二弹出放大面板 ---- */
function renderActivityModal(activities) {
    const filtered = actionCenterActivityFilter === 'all'
        ? activities
        : activities.filter(a => a.category === actionCenterActivityFilter);

    const catOptions = [
        { value: 'all', label: '全部' },
        { value: 'health', label: '健康' },
        { value: 'study', label: '学习' },
        { value: 'relation', label: '关系' },
        { value: 'work', label: '工作' },
        { value: 'create', label: '创作' },
        { value: 'finance', label: '财务' },
        { value: 'hobby', label: '爱好' },
        { value: 'soul', label: '魅力' },
    ];

    return `
        <div class="ac-activity-overlay" id="activity-overlay" style="display:none" onclick="closeActivityModal(event)">
            <div class="ac-activity-panel" onclick="event.stopPropagation()">
                <div class="ac-activity-panel__header">
                    <span class="ac-activity-panel__title">动态播报</span>
                    <div class="ac-activity-panel__actions">
                        <select class="ac-mini-select" onchange="actionCenterActivityFilter=this.value;refreshActivityModal()">
                            ${catOptions.map(o => `<option value="${o.value}" ${actionCenterActivityFilter === o.value ? 'selected' : ''}>${o.label}</option>`).join('')}
                        </select>
                        <button class="ac-icon-btn" onclick="closeActivityModal()" title="关闭">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                        </button>
                    </div>
                </div>
                <div class="ac-activity-panel__body" id="activity-panel-body">
                    ${filtered.length === 0
                        ? `<div class="empty-state"><div class="empty-state__title">📭 暂无记录</div></div>`
                        : filtered.map((a, i) => `
                            <div class="ac-activity-item ${i < filtered.length - 1 ? 'ac-activity-item--divider' : ''}">
                                <div class="ac-activity-item__left">
                                    <span class="ac-activity-item__icon">${attrIcon(a.category || a.category_id || '', 20)}</span>
                                    <span class="ac-activity-item__cat">${a.category_name || ''}</span>
                                </div>
                                <div class="ac-activity-item__mid">
                                    <span class="ac-activity-item__xp">EXP +${a.exp_earned || a.xp || 0}</span>
                                    <span class="ac-activity-item__desc">${a.description}</span>
                                </div>
                                <span class="ac-activity-item__time">${a.timestamp}</span>
                            </div>
                        `).join('')}
                </div>
            </div>
        </div>
    `;
}

function openActivityModal() {
    document.getElementById('activity-overlay').style.display = 'flex';
    activityModalOpen = true;
}

function closeActivityModal(e) {
    if (e && e.target !== document.getElementById('activity-overlay')) return;
    document.getElementById('activity-overlay').style.display = 'none';
    activityModalOpen = false;
}

function refreshActivityModal() {
    const body = document.getElementById('activity-panel-body');
    if (!body) return;

    // 尝试从后端加载
    const curUser = getCurrentUser();
    if (curUser) {
        fetchActivityFeed(curUser.id).then(feedResult => {
            const activities = (feedResult && feedResult.activities) || AppData.actionCenter.activities || [];
            renderActivityModalBody(body, activities);
        }).catch(() => {
            renderActivityModalBody(body, AppData.actionCenter.activities || []);
        });
    } else {
        renderActivityModalBody(body, AppData.actionCenter.activities || []);
    }
}

function renderActivityModalBody(body, activities) {
    const filtered = actionCenterActivityFilter === 'all'
        ? activities
        : activities.filter(a => a.category === actionCenterActivityFilter || a.category_id === actionCenterActivityFilter);

    body.innerHTML = filtered.length === 0
        ? `<div class="empty-state"><div class="empty-state__title">📭 暂无记录</div></div>`
        : filtered.map((a, i) => {
            const feedXp = a.exp_earned || a.xp || 0;
            const feedCat = a.category || a.category_id || '';
            return `
            <div class="ac-activity-item ${i < filtered.length - 1 ? 'ac-activity-item--divider' : ''}">
                <div class="ac-activity-item__left">
                    <span class="ac-activity-item__icon">${attrIcon(feedCat, 20)}</span>
                    <span class="ac-activity-item__cat">${a.category_name || ''}</span>
                </div>
                <div class="ac-activity-item__mid">
                    <span class="ac-activity-item__xp">EXP +${feedXp}</span>
                    <span class="ac-activity-item__desc">${a.description}</span>
                </div>
                <span class="ac-activity-item__time">${a.timestamp}</span>
            </div>
        `;}).join('');
}

/** 重新加载行动中心动态播报模块（不刷新整个页面） */
function reloadActionCenterActivityFeed() {
    const curUser = getCurrentUser();
    if (curUser) {
        fetchActivityFeed(curUser.id).then(feedResult => {
            const activities = (feedResult && feedResult.activities) || AppData.actionCenter.activities || [];
            const feedCard = document.getElementById('ac-activity-feed');
            if (feedCard) {
                feedCard.innerHTML = renderModule2_ActivityFeed(activities);
            }
            refreshActivityModal();
        }).catch(() => {
            refreshActivityModal();
        });
    } else {
        refreshActivityModal();
    }
}

/* ---- 模块三：习惯打卡 ---- */
function renderModule3_HabitCheckin() {
    const habits = AppData.habits;
    const filtered = actionCenterHabitFilter === 'all'
        ? habits
        : habits.filter(h => h.todayDone === (actionCenterHabitFilter === 'done'));

    const cards = filtered.map(h => {
        const weekDone = h.weekDone || [0,0,0,0,0,0,0];
        const doneCount = weekDone.filter(Boolean).length;
        const weeklyPct = Math.round((doneCount / 7) * 100);
        const checkedClass = h.todayDone ? 'ac-habit-card--done' : '';

        return `
            <div class="ac-habit-card ${checkedClass}">
                <div class="ac-habit-card__name">${h.name}</div>
                <div class="ac-habit-card__icon-row">
                    <span class="ac-habit-card__emoji">${h.icon}</span>
                    <span class="ac-habit-card__status">
                        <span class="ac-habit-dot ${h.todayDone ? 'ac-habit-dot--done' : ''}"></span>
                        ${h.todayDone ? '已打卡' : '未打卡'}
                    </span>
                </div>
                <div class="ac-habit-card__progress">
                    <div class="ac-habit-card__bar">
                        <div class="ac-habit-card__bar-fill" style="width:${weeklyPct}%"></div>
                    </div>
                    <span class="ac-habit-card__pct">${weeklyPct}%</span>
                </div>
                <div class="ac-habit-card__footer">
                    <span class="ac-habit-card__streak">🔥 连击${h.streak}天</span>
                    <span class="ac-habit-card__status-tag ${h.todayDone ? 'ac-habit-card__status-tag--done' : 'ac-habit-card__status-tag--pending'}">
                        ${h.todayDone ? '✅ 已打卡' : '⏳ 待打卡'}
                    </span>
                </div>
            </div>
        `;
    }).join('');

    return `
        <div class="card ac-habit-module">
            <div class="ac-module-header">
                <span class="ac-module-header__title">
                    <span class="ac-module-header__icon">${ACTION_ICONS.habit_checkin}</span>
                    习惯打卡
                </span>
                <div class="ac-module-header__actions">
                    <select class="ac-mini-select" onchange="actionCenterHabitFilter=this.value;renderActionCenter()">
                        <option value="all" ${actionCenterHabitFilter === 'all' ? 'selected' : ''}>全部</option>
                        <option value="undone" ${actionCenterHabitFilter === 'undone' ? 'selected' : ''}>未打卡</option>
                        <option value="done" ${actionCenterHabitFilter === 'done' ? 'selected' : ''}>已打卡</option>
                    </select>
                </div>
            </div>
            <div class="ac-habit-grid">
                ${cards}
            </div>
        </div>
    `;
}

/* ---- 模块四：目标追踪（数据来自 AppData.goals，与目标板块同步） ---- */
function renderModule4_GoalTracker() {
    const allGoals = AppData.goals;

    // Determine status from progress
    const getStatus = g => g.progress >= 100 ? 'completed' : 'active';

    const filtered = actionCenterGoalFilter === 'all'
        ? allGoals
        : allGoals.filter(g => getStatus(g) === actionCenterGoalFilter);

    const statusLabels = { active: '进行中', paused: '暂停中', completed: '已完成' };
    const statusClass = { active: 'badge--success', paused: 'badge--info', completed: 'badge--primary' };

    const listHtml = filtered.length === 0
        ? `<div class="empty-state"><div class="empty-state__title">暂无目标</div><div class="empty-state__desc">前往目标页面创建你的第一个目标</div></div>`
        : filtered.map(g => {
            const cat = getCategory(g.category);
            const catColor = cat ? cat.color : '#888';
            const deadlineDate = new Date(g.deadline + 'T23:59:59');
            const now = new Date();
            const daysLeft = Math.ceil((deadlineDate - now) / (1000 * 60 * 60 * 24));
            const urgencyColor = daysLeft < 30 ? '#F26B68' : daysLeft < 60 ? '#F7C242' : '#A0A8A6';

            // Find next incomplete milestone
            const nextMs = g.milestones ? g.milestones.find(m => !m.done) : null;
            const nextMsText = nextMs ? nextMs.note : '全部完成 🎉';

            const imgHtml = g.category_image
                ? `<div class="ac-goal-item__img" style="background-image:url('${g.category_image}')"></div>`
                : `<div class="ac-goal-item__img ac-goal-item__img--placeholder" style="color:${catColor}">${cat ? attrIcon(cat.id, 28) : '🎯'}</div>`;

            return `
                <div class="ac-goal-item">
                    ${imgHtml}
                    <div class="ac-goal-item__info">
                        <span class="ac-goal-item__name">${g.title}</span>
                        <div class="ac-goal-item__meta-row">
                            <span class="ac-goal-item__dim">${cat ? cat.name : ''}</span>
                            <span class="ac-goal-item__deadline" style="color:${urgencyColor}">剩余 ${daysLeft} 天</span>
                        </div>
                        <span class="ac-goal-item__next-ms" title="${escapeHtml(nextMsText)}">
                            下一里程：${escapeHtml(nextMsText)}
                        </span>
                    </div>
                </div>
            `;
        }).join('');

    return `
        <div class="card ac-goal-module">
            <div class="ac-module-header">
                <span class="ac-module-header__title">
                    <span class="ac-module-header__icon">${ACTION_ICONS.goals}</span>
                    目标
                </span>
                <div class="ac-module-header__actions">
                    <select class="ac-mini-select" onchange="actionCenterGoalFilter=this.value;renderActionCenter()">
                        <option value="all" ${actionCenterGoalFilter === 'all' ? 'selected' : ''}>全部</option>
                        <option value="active" ${actionCenterGoalFilter === 'active' ? 'selected' : ''}>进行中</option>
                        <option value="completed" ${actionCenterGoalFilter === 'completed' ? 'selected' : ''}>已完成</option>
                    </select>
                </div>
            </div>
            <div class="ac-goal-list">
                ${listHtml}
            </div>
        </div>
    `;
}

/* ---- 模块五：本周任务（全宽表格） ---- */
function renderModule5_WeeklyTasks(tasks) {
    // ---- Filter ----
    let filtered = tasks;
    if (taskAttrFilter !== 'all') {
        filtered = filtered.filter(t => t.attribute === taskAttrFilter);
    }
    if (taskStatusFilter !== 'all') {
        filtered = filtered.filter(t => t.status === taskStatusFilter);
    }

    // ---- Sort ----
    const sortFns = {
        'az':       (a, b) => a.task.localeCompare(b.task, 'zh'),
        'za':       (a, b) => b.task.localeCompare(a.task, 'zh'),
        'progress-desc': (a, b) => b.progress - a.progress,
        'progress-asc':  (a, b) => a.progress - b.progress,
        'deadline': (a, b) => new Date(a.deadline) - new Date(b.deadline),
    };
    if (taskSortBy && sortFns[taskSortBy]) {
        filtered = [...filtered].sort(sortFns[taskSortBy]);
    }

    // ---- Unique attribute list for filter ----
    const attrs = [...new Set(tasks.map(t => t.attribute))];

    const rows = filtered.length === 0
        ? `<tr><td colspan="8" class="ac-task-empty">暂无匹配的任务</td></tr>`
        : filtered.map(t => {
            const statusLabels = { completed: '已完成', in_progress: '进行中', pending: '待开始' };
            const statusLabel = statusLabels[t.status] || t.status;
            return `
            <tr class="ac-task-row">
                <td class="ac-task-cell ac-task-cell--task">${t.task}</td>
                <td class="ac-task-cell ac-task-cell--attr">
                    <span class="ac-task-attr">${attrIcon(t.attrId, 18)} ${t.attribute}</span>
                </td>
                <td class="ac-task-cell ac-task-cell--num">${t.targetValue}</td>
                <td class="ac-task-cell ac-task-cell--num">${t.resultValue}</td>
                <td class="ac-task-cell ac-task-cell--progress">
                    <div class="ac-task-progress">
                        <div class="ac-task-progress__bar">
                            <div class="ac-task-progress__fill" style="width:${t.progress}%"></div>
                        </div>
                        <span class="ac-task-progress__text">${t.progress}%</span>
                    </div>
                </td>
                <td class="ac-task-cell ac-task-cell--status">
                    <span class="ac-task-status ac-task-status--${t.status}">${statusLabel}</span>
                </td>
                <td class="ac-task-cell ac-task-cell--date">${t.deadline}</td>
                <td class="ac-task-cell ac-task-cell--xp">
                    <span class="ac-task-xp">${t.rewardXP}</span>
                </td>
                <td class="ac-task-cell ac-task-cell--goal">
                    <span class="ac-task-goal">${t.goal}</span>
                    <button class="ac-task-expand" onclick="toggleTaskGoalExpand(event)" title="展开">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 5v14M5 12h14"/></svg>
                    </button>
                </td>
            </tr>
        `;
    }).join('');

    return `
        <div class="card ac-task-module">
            <div class="ac-module-header">
                <span class="ac-module-header__title">
                    <span class="ac-module-header__icon">${ACTION_ICONS.week_tasks}</span>
                    本周任务
                </span>
                <div class="ac-module-header__actions">
                    <select class="ac-mini-select" onchange="taskAttrFilter=this.value;renderActionCenter()">
                        <option value="all" ${taskAttrFilter === 'all' ? 'selected' : ''}>全部属性</option>
                        ${attrs.map(a => `<option value="${a}" ${taskAttrFilter === a ? 'selected' : ''}>${a}</option>`).join('')}
                    </select>
                    <select class="ac-mini-select" onchange="taskStatusFilter=this.value;renderActionCenter()">
                        <option value="all" ${taskStatusFilter === 'all' ? 'selected' : ''}>全部状态</option>
                        <option value="completed" ${taskStatusFilter === 'completed' ? 'selected' : ''}>已完成</option>
                        <option value="in_progress" ${taskStatusFilter === 'in_progress' ? 'selected' : ''}>进行中</option>
                        <option value="pending" ${taskStatusFilter === 'pending' ? 'selected' : ''}>待开始</option>
                    </select>
                    <button class="ac-toolbar-btn ${taskSortBy === 'az' ? 'ac-toolbar-btn--active' : ''}" onclick="taskSortBy='az';renderActionCenter()" title="A-Z">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="15 12 12 19 9 12"/><line x1="12" y1="5" x2="12" y2="19"/></svg>
                    </button>
                    <button class="ac-toolbar-btn ${taskSortBy === 'za' ? 'ac-toolbar-btn--active' : ''}" onclick="taskSortBy='za';renderActionCenter()" title="Z-A">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 12 12 5 15 12"/><line x1="12" y1="19" x2="12" y2="5"/></svg>
                    </button>
                    <button class="ac-toolbar-btn ${taskSortBy === 'progress-desc' ? 'ac-toolbar-btn--active' : ''}" onclick="taskSortBy='progress-desc';renderActionCenter()" title="完成度高-低">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="17 11 12 6 7 11"/><polyline points="17 18 12 13 7 18"/></svg>
                    </button>
                    <button class="ac-toolbar-btn ${taskSortBy === 'progress-asc' ? 'ac-toolbar-btn--active' : ''}" onclick="taskSortBy='progress-asc';renderActionCenter()" title="完成度低-高">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="7 13 12 18 17 13"/><polyline points="7 6 12 11 17 6"/></svg>
                    </button>
                    <button class="ac-toolbar-btn ${taskSortBy === 'deadline' ? 'ac-toolbar-btn--active' : ''}" onclick="taskSortBy='deadline';renderActionCenter()" title="截止日期">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>
                    </button>
                </div>
            </div>
            <div class="ac-task-table-wrap">
                <table class="ac-task-table">
                    <thead>
                        <tr class="ac-task-head-row">
                            <th class="ac-task-th">任务</th>
                            <th class="ac-task-th">属性</th>
                            <th class="ac-task-th">目标值</th>
                            <th class="ac-task-th">结果值</th>
                            <th class="ac-task-th">进度</th>
                            <th class="ac-task-th">状态</th>
                            <th class="ac-task-th">截止日期</th>
                            <th class="ac-task-th">奖励EXP</th>
                            <th class="ac-task-th">目标</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${rows}
                    </tbody>
                </table>
            </div>
        </div>
    `;
}

function toggleTaskGoalExpand(e) {
    // Placeholder: toggle expand for goal column
    const btn = e.currentTarget;
    const goalSpan = btn.parentElement.querySelector('.ac-task-goal');
    goalSpan.classList.toggle('ac-task-goal--expanded');
}
