/* ================================================================
   Skills Page — 技能板块
   子页面：我的技能 / 技能库
   ================================================================ */

/* ================================================================
   SKILL_ICONS — 页面头部图标
   ================================================================ */

const SKILL_ICONS = {
    skills: `<svg viewBox="0 0 58 58" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M29 6L6 17l23 11 23-11L29 6z" fill="url(#g-hdr-today)" stroke="#fbbf24" stroke-width="1.2" stroke-linejoin="round"/>
        <path d="M6 30l23 11 23-11" fill="none" stroke="#fbbf24" stroke-width="1.2"/>
        <path d="M6 23l23 11 23-11" fill="none" stroke="#fbbf24" stroke-width="1.2" opacity="0.6"/>
        <circle cx="29" cy="17" r="3" fill="#fbbf24"/>
        <path d="M29 30v18" stroke="#fbbf24" stroke-width="1.5" stroke-linecap="round"/>
        <circle cx="29" cy="45" r="4" fill="none" stroke="#fbbf24" stroke-width="1.2"/>
    </svg>`
};

/* ================================================================
   后端 API 工具函数
   ================================================================ */

/** 从后端获取技能树索引，降级到 localStorage */
async function fetchSkillTreeIndexAsync() {
    const uid = getCurrentUser()?.id;
    if (uid) {
        try {
            const res = await fetch(API_BASE + '/api/skill-trees?user_id=' + uid);
            if (res.ok) {
                const data = await res.json();
                if (data.trees && data.trees.length > 0) {
                    // 缓存到 localStorage
                    localStorage.setItem('skill_tree_index', JSON.stringify(data.trees));
                    return data.trees;
                }
            }
        } catch(e) {}
    }
    // 降级：从 localStorage 读取
    return loadSkillTreeIndexLocal();
}

/** 从后端获取用户已添加的技能列表，降级到 localStorage */
async function fetchMySkillsAsync() {
    const uid = getCurrentUser()?.id;
    if (uid) {
        try {
            const res = await fetch(API_BASE + '/api/skill-trees/user-skills/list?user_id=' + uid);
            if (res.ok) {
                const data = await res.json();
                if (data.skill_ids) {
                    localStorage.setItem('my_skills_' + uid, JSON.stringify(data.skill_ids));
                    return data.skill_ids;
                }
            }
        } catch(e) {}
    }
    return loadMySkillsLocal();
}

/** 保存用户已添加的技能列表到后端 */
async function saveMySkillsAsync(list) {
    const uid = getCurrentUser()?.id;
    if (uid) {
        localStorage.setItem('my_skills_' + uid, JSON.stringify(list));
        try {
            await fetch(API_BASE + '/api/skill-trees/user-skills/list?user_id=' + uid, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ skill_ids: list }),
            });
        } catch(e) {}
    }
}

/** 从后端获取学习进度，降级到 localStorage */
async function fetchLearnerAsync(treeId) {
    const uid = getCurrentUser()?.id;
    if (uid) {
        try {
            const res = await fetch(API_BASE + '/api/skill-trees/' + treeId + '/published');
            if (res.ok) {
                const data = await res.json();
                if (data && data.published_data && data.published_data.learner) {
                    return data.published_data.learner;
                }
            }
        } catch(e) {}
    }
    return loadLearnerLocal(treeId);
}

/** 从后端获取已发布的技能树，降级到 localStorage */
async function fetchPublishedTreeAsync(treeId) {
    try {
        const res = await fetch(API_BASE + '/api/skill-trees/' + treeId + '/published');
        if (res.ok) {
            const data = await res.json();
            if (data && data.published_data) {
                return data.published_data;
            }
        }
    } catch(e) {}
    return loadPublishedTreeLocal(treeId);
}

/* ================================================================
   localStorage 降级函数（保持原有逻辑不变）
   ================================================================ */

/** 从 localStorage 读取 skill_tree_index */
function loadSkillTreeIndexLocal() {
    try {
        const raw = localStorage.getItem('skill_tree_index');
        return raw ? JSON.parse(raw) : [];
    } catch(e) { return []; }
}

function saveSkillTreeIndexLocal(index) {
    localStorage.setItem('skill_tree_index', JSON.stringify(index));
}

/** 读取用户已添加的技能列表（localStorage，按用户隔离） */
function loadMySkillsLocal() {
    try {
        const uid = getCurrentUser()?.id || 'guest';
        const raw = localStorage.getItem('my_skills_' + uid);
        return raw ? JSON.parse(raw) : [];
    } catch(e) { return []; }
}

function saveMySkillsLocal(list) {
    const uid = getCurrentUser()?.id || 'guest';
    localStorage.setItem('my_skills_' + uid, JSON.stringify(list));
}

/** 判断某技能是否已被添加 */
function isSkillAdded(treeId) {
    return loadMySkillsLocal().indexOf(treeId) !== -1;
}

/** 读取 tree_{id}_learner_{userId} 进度（localStorage 降级） */
function loadLearnerLocal(treeId) {
    try {
        const uid = getCurrentUser()?.id || 'guest';
        const raw = localStorage.getItem(treeId + '_learner_' + uid);
        return raw ? JSON.parse(raw) : {};
    } catch(e) { return {}; }
}

/** 读取 tree_{id}_published（localStorage 降级） */
function loadPublishedTreeLocal(treeId) {
    try {
        const raw = localStorage.getItem(treeId + '_published');
        return raw ? JSON.parse(raw) : null;
    } catch(e) { return null; }
}

/** 获取当前在学的第一个节点名称 */
function getCurrentLearningNode(treeId, publishedTree) {
    const learner = publishedTree ? (publishedTree.learner || {}) : {};
    const learningIds = Object.keys(learner).filter(function(id) { return learner[id] === 50; });
    if (learningIds.length > 0) {
        const tree = publishedTree;
        if (tree && tree.nodes) {
            for (var i = 0; i < tree.nodes.length; i++) {
                if (tree.nodes[i].id === learningIds[0]) {
                    return tree.nodes[i].name;
                }
            }
        }
        return '学习中...';
    }
    return null; // 没有在学的节点
}

/* ================================================================
   Render
   ================================================================ */

function renderSkills(subPage) {
    const tab = subPage || 'mine';
    if (tab === 'mine') renderSkillMine();
    else renderSkillLib();
}

async function renderSkillMine() {
    const user = getCurrentUser();
    const isAdmin = user && user.role === 'admin';

    // 异步加载数据
    const index = await fetchSkillTreeIndexAsync();
    const mySkillIds = await fetchMySkillsAsync();
    const myTrees = index.filter(t => mySkillIds.indexOf(t.id) !== -1);

    // 并行加载每棵树的发布数据和 learner
    const treeDataPromises = myTrees.map(async (t) => {
        const publishedTree = await fetchPublishedTreeAsync(t.id);
        const learner = publishedTree ? (publishedTree.learner || {}) : {};
        const nodeCount = t.nodeCount || (publishedTree ? publishedTree.nodes.length : 0);
        const completedCount = Object.values(learner).filter(function(v) { return v >= 100; }).length;
        const progressPct = nodeCount > 0 ? Math.round(completedCount / nodeCount * 100) : 0;
        const learningNode = publishedTree ? getCurrentLearningNode(t.id, publishedTree) : null;
        return { t, publishedTree, learner, nodeCount, completedCount, progressPct, learningNode };
    });
    const treeData = await Promise.all(treeDataPromises);

    let listHtml = '';
    if (myTrees.length === 0) {
        listHtml = `
            <div class="skill-empty">
                <svg class="skill-empty__visual" viewBox="0 0 240 200" xmlns="http://www.w3.org/2000/svg">
                    <defs>
                        <radialGradient id="skill-mine-glow" cx="50%" cy="55%">
                            <stop offset="0%" stop-color="#2dd4bf" stop-opacity="0.12"/>
                            <stop offset="100%" stop-color="#2dd4bf" stop-opacity="0"/>
                        </radialGradient>
                    </defs>
                    <circle cx="120" cy="110" r="90" fill="url(#skill-mine-glow)"/>
                    <g transform="translate(120, 130)">
                        <ellipse cx="0" cy="42" rx="82" ry="4" fill="#000" opacity="0.4"/>
                        <path d="M -72 28 L -67 -32 L 67 -32 L 72 28 Z" fill="#15171c" stroke="#475569" stroke-width="1.5" stroke-linejoin="round"/>
                        <path d="M -62 -28 Q -26 -24 0 -24 Q 26 -24 62 -28 L 62 22 Q 26 18 0 18 Q -26 18 -62 22 Z" fill="#0f172a" stroke="#475569" stroke-width="1.5" stroke-linejoin="round"/>
                        <line x1="0" y1="-24" x2="0" y2="18" stroke="#334155" stroke-width="1"/>
                        <line x1="-46" y1="-12" x2="-10" y2="-10" stroke="#475569" stroke-width="1.5" stroke-dasharray="3 3" stroke-linecap="round"/>
                        <line x1="-46" y1="2" x2="-15" y2="4" stroke="#475569" stroke-width="1.5" stroke-dasharray="3 3" stroke-linecap="round"/>
                        <line x1="10" y1="-10" x2="46" y2="-12" stroke="#2dd4bf" stroke-width="1.5" stroke-linecap="round"/>
                        <line x1="15" y1="4" x2="46" y2="2" stroke="#475569" stroke-width="1.5" stroke-dasharray="3 3" stroke-linecap="round"/>
                        <circle cx="-30" cy="-12" r="1.5" fill="#2dd4bf"/>
                    </g>
                    <g transform="translate(120, 96)">
                        <path d="M 0 0 L 0 -42" stroke="#2dd4bf" stroke-width="2" stroke-linecap="round"/>
                        <path d="M 0 -18 Q -14 -22 -20 -36 Q -7 -32 0 -22 Z" fill="#2dd4bf" opacity="0.85"/>
                        <path d="M 0 -28 Q 14 -32 20 -46 Q 7 -42 0 -32 Z" fill="#5eead4" opacity="0.85"/>
                        <circle cx="0" cy="-42" r="2.5" fill="#5eead4"/>
                        <circle cx="0" cy="-42" r="5.5" fill="none" stroke="#5eead4" stroke-width="0.8" opacity="0.4"/>
                    </g>
                    <g transform="translate(50, 56)">
                        <circle cx="0" cy="0" r="15" fill="#1e2028" stroke="#475569" stroke-width="1" stroke-dasharray="2 2"/>
                        <g fill="none" stroke="#5eead4" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round" opacity="0.55">
                            <path d="M -6 -4 L -6 5 Q -3 4 0 4 L 0 -4 Q -3 -5 -6 -4 Z"/>
                            <path d="M 6 -4 L 6 5 Q 3 4 0 4 L 0 -4 Q 3 -5 6 -4 Z"/>
                        </g>
                    </g>
                    <g transform="translate(190, 56)">
                        <circle cx="0" cy="0" r="15" fill="#1e2028" stroke="#475569" stroke-width="1" stroke-dasharray="2 2"/>
                        <g fill="none" stroke="#5eead4" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round" opacity="0.55">
                            <circle cx="0" cy="0" r="6"/>
                            <circle cx="0" cy="0" r="3"/>
                            <circle cx="0" cy="0" r="1" fill="#2dd4bf" stroke="none"/>
                        </g>
                    </g>
                    <g transform="translate(50, 168)">
                        <circle cx="0" cy="0" r="15" fill="#1e2028" stroke="#475569" stroke-width="1" stroke-dasharray="2 2"/>
                        <g fill="none" stroke="#5eead4" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round" opacity="0.55">
                            <circle cx="0" cy="-2" r="5"/>
                            <path d="M -3 3 L -1 9 L 0 7 L 1 9 L 3 3"/>
                        </g>
                    </g>
                    <g transform="translate(190, 168)">
                        <circle cx="0" cy="0" r="15" fill="#1e2028" stroke="#475569" stroke-width="1" stroke-dasharray="2 2"/>
                        <line x1="-5" y1="0" x2="5" y2="0" stroke="#5eead4" stroke-width="1.5" stroke-linecap="round" opacity="0.55"/>
                        <line x1="0" y1="-5" x2="0" y2="5" stroke="#5eead4" stroke-width="1.5" stroke-linecap="round" opacity="0.55"/>
                    </g>
                </svg>
                <h3 class="skill-empty__title">还没有添加任何技能</h3>
                <p class="skill-empty__desc">前往技能库选择你想学习的技能，<br>开启你的成长之旅</p>
                <button class="skill-empty__btn" onclick="navigateTo('skill', 'lib')">
                    前往技能库
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M5 12h14M12 5l7 7-7 7"/></svg>
                </button>
            </div>
        `;
    } else {
        listHtml = `
            <div class="skill-mine-list">
                ${treeData.map(({ t, nodeCount, completedCount, progressPct, learningNode }) => {
                    const imageSrc = t.image || '';
                    const hasImage = imageSrc !== '';
                    return `
                        <div class="skill-mine-card" onclick="openSkillViewer('${t.id}', '${escapeHtml(t.name)}')">
                            <button class="skill-mine-card__edit" onclick="event.stopPropagation();openSkillEditModal('${t.id}')" title="编辑">✎</button>
                            <div class="skill-mine-card__image">
                                ${hasImage
                                    ? '<img src="' + escapeHtml(imageSrc) + '" alt="' + escapeHtml(t.name) + '">'
                                    : '<span class="skill-mine-card__image-default">📚</span>'
                                }
                            </div>
                            <div class="skill-mine-card__name-row">
                                <div class="skill-mine-card__name">${escapeHtml(t.name)}</div>
                                ${t.remark ? '<div class="skill-mine-card__remark">' + escapeHtml(t.remark) + '</div>' : ''}
                            </div>
                            <div class="skill-mine-card__desc" title="${escapeHtml(t.description || '无简介')}">${escapeHtml(t.description) || '<span class="skill-mine-card__empty-text">无简介</span>'}</div>
                            <div class="skill-mine-card__learning">
                                ${learningNode ? '<span class="skill-mine-card__learning-icon">▶</span>' + escapeHtml(learningNode) : '<span class="skill-mine-card__empty-text">无在学节点</span>'}
                            </div>
                            <div class="skill-mine-card__progress-area">
                                <div class="skill-mine-card__progress-bar">
                                    <div class="skill-mine-card__progress-fill" style="width:${progressPct}%"></div>
                                </div>
                                <span class="skill-mine-card__progress-text">${completedCount}/${nodeCount} · ${progressPct}%</span>
                            </div>
                        </div>
                    `;
                }).join('')}
            </div>
        `;
    }

    const html = `
        <div class="page-header page-header--with-icon">
            <div class="page-header__icon" style="width:58px;height:58px">${SKILL_ICONS.skills}</div>
            <div style="flex:1;display:flex;justify-content:space-between;align-items:flex-start">
                <div>
                    <h1 class="page-header__title">我的技能</h1>
                    <p class="page-header__subtitle">掌握技能，成就非凡</p>
                </div>
                <button class="goal-create-btn" onclick="navigateTo('skill', 'lib')">+ 添加技能</button>
            </div>
        </div>
        ${listHtml}
    `;
    document.getElementById('page-skill').innerHTML = html;
}

async function renderSkillLib() {
    const user = getCurrentUser();
    const isAdmin = user && user.role === 'admin';

    // 异步加载数据
    const index = await fetchSkillTreeIndexAsync();
    const publishedTrees = index.filter(t => t.publishedAt);

    let listHtml = '';
    if (publishedTrees.length === 0) {
        listHtml = `
            <div class="skill-empty">
                <svg class="skill-empty__visual" viewBox="0 0 240 200" xmlns="http://www.w3.org/2000/svg">
                    <defs>
                        <radialGradient id="skill-lib-glow" cx="50%" cy="55%">
                            <stop offset="0%" stop-color="#2dd4bf" stop-opacity="0.1"/>
                            <stop offset="100%" stop-color="#2dd4bf" stop-opacity="0"/>
                        </radialGradient>
                    </defs>
                    <circle cx="120" cy="115" r="90" fill="url(#skill-lib-glow)"/>
                    <g transform="translate(120, 45)">
                        <path d="M -18 -22 L 18 -22 L 18 -18 L 5 0 L 18 18 L 18 22 L -18 22 L -18 18 L -5 0 L -18 -18 Z" fill="none" stroke="#2dd4bf" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
                        <path d="M -14 -19 L 14 -19 L 4 -3 L -4 -3 Z" fill="#2dd4bf" opacity="0.7"/>
                        <path d="M -10 19 L 10 19 L 6 5 L -6 5 Z" fill="#2dd4bf" opacity="0.7"/>
                        <circle cx="0" cy="0" r="1" fill="#5eead4"/>
                        <line x1="-20" y1="-22" x2="20" y2="-22" stroke="#2dd4bf" stroke-width="1.5" stroke-linecap="round"/>
                        <line x1="-20" y1="22" x2="20" y2="22" stroke="#2dd4bf" stroke-width="1.5" stroke-linecap="round"/>
                        <circle cx="0" cy="6" r="0.8" fill="#5eead4" opacity="0.6"/>
                        <circle cx="0" cy="10" r="0.6" fill="#5eead4" opacity="0.4"/>
                    </g>
                    <g fill="none" stroke="#2dd4bf" stroke-width="1" stroke-dasharray="2 3" stroke-linecap="round" opacity="0.4">
                        <line x1="106" y1="68" x2="78" y2="118"/>
                        <line x1="134" y1="68" x2="162" y2="118"/>
                    </g>
                    <g fill="#1e2028" stroke="#475569" stroke-width="1.3" stroke-dasharray="3 3">
                        <circle cx="70" cy="125" r="7"/>
                        <circle cx="170" cy="125" r="7"/>
                    </g>
                    <g transform="translate(120, 145)">
                        <circle cx="0" cy="0" r="16" fill="none" stroke="#2dd4bf" stroke-width="0.8" opacity="0.3"/>
                        <circle cx="0" cy="0" r="11" fill="none" stroke="#2dd4bf" stroke-width="0.8" opacity="0.5"/>
                        <circle cx="0" cy="0" r="7" fill="#1e2028" stroke="#2dd4bf" stroke-width="1.5" stroke-dasharray="3 3"/>
                        <circle cx="0" cy="0" r="2.5" fill="#2dd4bf"/>
                    </g>
                    <g fill="none" stroke="#475569" stroke-width="1.2" stroke-dasharray="3 3" stroke-linecap="round">
                        <line x1="76" y1="128" x2="115" y2="143"/>
                        <line x1="164" y1="128" x2="125" y2="143"/>
                    </g>
                    <g fill="none" stroke="#475569" stroke-width="1.2" stroke-dasharray="3 3" stroke-linecap="round">
                        <line x1="115" y1="151" x2="92" y2="172"/>
                        <line x1="125" y1="151" x2="148" y2="172"/>
                    </g>
                    <g fill="#1e2028" stroke="#475569" stroke-width="1.3" stroke-dasharray="3 3">
                        <circle cx="88" cy="178" r="5"/>
                        <circle cx="152" cy="178" r="5"/>
                    </g>
                    <circle cx="120" cy="74" r="3" fill="none" stroke="#2dd4bf" stroke-width="1" stroke-dasharray="2 2"/>
                </svg>
                <h3 class="skill-empty__title">暂无已上线的技能树</h3>
                <p class="skill-empty__desc">等待管理员创建并上线技能树，<br>届时可在此处选择学习</p>
                <button class="skill-empty__btn skill-empty__btn--ghost" onclick="renderSkillLib()">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M23 4v6h-6M1 20v-6h6"/><path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15"/></svg>
                    刷新
                </button>
            </div>
        `;
    } else {
        listHtml = `
            <div class="skill-lib-list">
                ${publishedTrees.map(t => {
                    const dateStr = new Date(t.publishedAt).toLocaleDateString('zh-CN');
                    const added = isSkillAdded(t.id);
                    return `
                        <div class="skill-lib-item">
                            <div class="skill-lib-item__icon">📚</div>
                            <div class="skill-lib-item__info">
                                <div class="skill-lib-item__name">${escapeHtml(t.name)}</div>
                                <div class="skill-lib-item__desc">${escapeHtml(t.description || '')}</div>
                                <span style="font-size:11px;color:#666680">${t.nodeCount} 节点 · 上线于 ${dateStr}</span>
                            </div>
                            <button class="skill-lib-item__btn" onclick="openSkillDetailModal('${t.id}', '${escapeHtml(t.name)}', ${t.nodeCount || 0}, '${escapeHtml(t.description || '')}')">查看</button>
                        </div>
                    `;
                }).join('')}
            </div>
        `;
    }

    const html = `
        <div class="page-header page-header--with-icon">
            <div class="page-header__icon" style="width:58px;height:58px">${SKILL_ICONS.skills}</div>
            <div style="flex:1;display:flex;justify-content:space-between;align-items:flex-start">
                <div>
                    <h1 class="page-header__title">技能库</h1>
                    <p class="page-header__subtitle">选择你想学习的技能</p>
                </div>
                ${isAdmin ? '<button class="goal-create-btn" onclick="window.open(\'skill-tree/index.html\', \'_blank\')">✏️ 编辑技能</button>' : ''}
            </div>
        </div>
        ${listHtml}
    `;
    document.getElementById('page-skill').innerHTML = html;
}

/* ================================================================
   技能详情弹窗（技能库 "查看" 按钮）
   ================================================================ */

function openSkillDetailModal(treeId, treeName, nodeCount, description) {
    // 移除旧弹窗
    var old = document.getElementById('skill-detail-modal');
    if (old) old.remove();

    var added = isSkillAdded(treeId);

    var modal = document.createElement('div');
    modal.className = 'skill-detail-modal';
    modal.id = 'skill-detail-modal';
    modal.innerHTML = [
        '<div class="skill-detail-modal__header">',
        '  <span class="skill-detail-modal__title">技能详情</span>',
        '  <button class="skill-detail-modal__close" onclick="closeSkillDetailModal()">✕</button>',
        '</div>',
        '<div class="skill-detail-modal__body">',
        '  <div class="skill-detail-modal__left">',
        '    <div class="skill-detail-modal__info-row">',
        '      <div class="skill-detail-modal__info-label">技能名：</div>',
        '      <div class="skill-detail-modal__info-value">' + escapeHtml(treeName) + '</div>',
        '    </div>',
        '    <div class="skill-detail-modal__info-row">',
        '      <div class="skill-detail-modal__info-label">节点数：</div>',
        '      <div class="skill-detail-modal__info-value">' + nodeCount + '</div>',
        '    </div>',
        '    <div class="skill-detail-modal__info-row">',
        '      <div class="skill-detail-modal__info-label">技能介绍：</div>',
        '      <div class="skill-detail-modal__info-value skill-detail-modal__info-value--dim">' + escapeHtml(description || '暂无介绍') + '</div>',
        '    </div>',
        '    <div class="skill-detail-modal__left-bottom">',
        '      <button class="skill-detail-modal__add-btn' + (added ? ' skill-detail-modal__add-btn--added' : '') + '" id="btn-skill-add" onclick="handleSkillAdd(\'' + treeId + '\')">' + (added ? '✅ 已添加' : '添加') + '</button>',
        '    </div>',
        '  </div>',
        '  <div class="skill-detail-modal__right">',
        '    <iframe class="skill-detail-modal__preview" src="skill-tree/index.html?role=user&preview=true&treeId=' + encodeURIComponent(treeId) + '&userId=' + (getCurrentUser()?.id || '') + '"></iframe>',
        '  </div>',
        '</div>'
    ].join('');

    document.body.appendChild(modal);

    requestAnimationFrame(function() {
        modal.classList.add('skill-detail-modal--visible');
    });
}

function closeSkillDetailModal() {
    var modal = document.getElementById('skill-detail-modal');
    if (modal) modal.remove();
}

async function handleSkillAdd(treeId) {
    if (isSkillAdded(treeId)) return;
    var list = loadMySkillsLocal();
    list.push(treeId);
    saveMySkillsLocal(list);
    await saveMySkillsAsync(list);
    var btn = document.getElementById('btn-skill-add');
    if (btn) {
        btn.textContent = '✅ 已添加';
        btn.classList.add('skill-detail-modal__add-btn--added');
    }
    showToast('✅ 已添加到我的技能');
}

/* ================================================================
   查看器（从我的技能打开 — 全屏 iframe）
   ================================================================ */

function openSkillViewer(treeId, skillName) {
    var oldOverlay = document.getElementById('skill-viewer-overlay');
    if (oldOverlay) oldOverlay.remove();
    var oldModal = document.getElementById('skill-viewer-modal');
    if (oldModal) oldModal.remove();

    var overlay = document.createElement('div');
    overlay.className = 'modal-overlay';
    overlay.id = 'skill-viewer-overlay';
    overlay.onclick = function(e) { if (e.target === overlay) closeSkillViewer(); };

    var modal = document.createElement('div');
    modal.className = 'skill-viewer-modal';
    modal.id = 'skill-viewer-modal';
    modal.innerHTML = [
        '<div class="skill-viewer-modal__header">',
        '  <span class="skill-viewer-modal__title">' + escapeHtml(skillName || '技能树') + '</span>',
        '  <div class="skill-viewer-modal__actions">',
        '    <button class="skill-viewer-modal__close" onclick="closeSkillViewer()">✕</button>',
        '  </div>',
        '</div>',
        '<iframe class="skill-viewer-modal__iframe" src="skill-tree/index.html?role=user&treeId=' + encodeURIComponent(treeId) + '&userId=' + (getCurrentUser()?.id || '') + '"></iframe>'
    ].join('');

    document.body.appendChild(overlay);
    document.body.appendChild(modal);

    requestAnimationFrame(function() {
        overlay.classList.add('modal-overlay--visible');
        modal.classList.add('skill-viewer-modal--visible');
    });
}

function closeSkillViewer() {
    var overlay = document.getElementById('skill-viewer-overlay');
    var modal = document.getElementById('skill-viewer-modal');
    if (overlay) overlay.remove();
    if (modal) modal.remove();
}

/* ================================================================
   编辑弹窗 — 图片上传 + 备注编辑
   ================================================================ */

function openSkillEditModal(treeId) {
    // 移除旧弹窗
    var old = document.getElementById('skill-edit-modal');
    if (old) old.remove();

    var index = loadSkillTreeIndexLocal();
    var entry = null;
    for (var i = 0; i < index.length; i++) {
        if (index[i].id === treeId) { entry = index[i]; break; }
    }
    if (!entry) { showToast('技能数据异常', 'error'); return; }

    var currentImage = entry.image || '';
    var currentRemark = entry.remark || '';

    var modal = document.createElement('div');
    modal.className = 'skill-edit-modal';
    modal.id = 'skill-edit-modal';
    modal.innerHTML = [
        '<div class="skill-edit-modal__header">',
        '  <span class="skill-edit-modal__title">编辑技能</span>',
        '  <button class="skill-edit-modal__close" onclick="closeSkillEditModal()">✕</button>',
        '</div>',
        '<div class="skill-edit-modal__body">',
        '  <div class="skill-edit-modal__section">',
        '    <label class="skill-edit-modal__label">图片</label>',
        '    <div class="skill-edit-modal__upload" id="skill-edit-upload-area">',
        '      <div class="skill-edit-modal__upload-placeholder" id="skill-edit-upload-placeholder">',
        '        <div class="skill-edit-modal__upload-icon">📷</div>',
        '        <div class="skill-edit-modal__upload-text">点击选择图片</div>',
        '        <div class="skill-edit-modal__upload-hint">或拖拽图片到此处</div>',
        '        <div class="skill-edit-modal__upload-hint">推荐 1:1 比例，最大 1MB</div>',
        '      </div>',
        '      <div class="skill-edit-modal__upload-preview" id="skill-edit-upload-preview" style="display:none">',
        '        <img id="skill-edit-preview-img" src="" alt="预览">',
        '        <button class="skill-edit-modal__upload-clear" onclick="clearSkillEditImage()" title="清除图片">✕</button>',
        '      </div>',
        '      <input type="file" id="skill-edit-file-input" accept="image/*" style="display:none">',
        '    </div>',
        '  </div>',
        '  <div class="skill-edit-modal__section">',
        '    <label class="skill-edit-modal__label">备注</label>',
        '    <textarea class="skill-edit-modal__textarea" id="skill-edit-remark" placeholder="添加个人备注...">' + escapeHtml(currentRemark) + '</textarea>',
        '  </div>',
        '  <div class="skill-edit-modal__section">',
        '    <div class="skill-edit-modal__info">技能名称和简介请在技能树编辑器中修改</div>',
        '  </div>',
        '</div>',
        '<div class="skill-edit-modal__footer">',
        '  <button class="skill-edit-modal__btn skill-edit-modal__btn--cancel" onclick="closeSkillEditModal()">取消</button>',
        '  <button class="skill-edit-modal__btn skill-edit-modal__btn--save" onclick="saveSkillEdit(\'' + treeId + '\')">保存</button>',
        '</div>'
    ].join('');

    document.body.appendChild(modal);
    requestAnimationFrame(function() { modal.classList.add('skill-edit-modal--visible'); });

    // 如果有已有图片，显示预览
    if (currentImage) {
        showEditPreview(currentImage);
    }

    // 绑定上传事件
    var uploadArea = document.getElementById('skill-edit-upload-area');
    var fileInput = document.getElementById('skill-edit-file-input');

    uploadArea.addEventListener('click', function() {
        fileInput.click();
    });

    fileInput.addEventListener('change', function(e) {
        handleEditFileSelect(e.target.files);
    });

    // 拖拽事件
    uploadArea.addEventListener('dragover', function(e) {
        e.preventDefault();
        uploadArea.classList.add('skill-edit-modal__upload--dragover');
    });

    uploadArea.addEventListener('dragleave', function() {
        uploadArea.classList.remove('skill-edit-modal__upload--dragover');
    });

    uploadArea.addEventListener('drop', function(e) {
        e.preventDefault();
        uploadArea.classList.remove('skill-edit-modal__upload--dragover');
        handleEditFileSelect(e.dataTransfer.files);
    });
}

function handleEditFileSelect(files) {
    if (!files || files.length === 0) return;
    var file = files[0];
    // 检查类型
    if (!file.type.match(/^image\//)) {
        showToast('请选择图片文件', 'error');
        return;
    }
    // 检查大小（1MB）
    if (file.size > 1024 * 1024) {
        showToast('图片大小不能超过 1MB', 'error');
        return;
    }
    var reader = new FileReader();
    reader.onload = function(e) {
        showEditPreview(e.target.result);
    };
    reader.readAsDataURL(file);
}

function showEditPreview(src) {
    var placeholder = document.getElementById('skill-edit-upload-placeholder');
    var preview = document.getElementById('skill-edit-upload-preview');
    var img = document.getElementById('skill-edit-preview-img');
    if (placeholder) placeholder.style.display = 'none';
    if (preview) preview.style.display = 'block';
    if (img) img.src = src;
    // 存储到临时属性
    var modal = document.getElementById('skill-edit-modal');
    if (modal) modal.dataset.tempImage = src;
}

function clearSkillEditImage() {
    var placeholder = document.getElementById('skill-edit-upload-placeholder');
    var preview = document.getElementById('skill-edit-upload-preview');
    var fileInput = document.getElementById('skill-edit-file-input');
    if (placeholder) placeholder.style.display = '';
    if (preview) preview.style.display = 'none';
    if (fileInput) fileInput.value = '';
    var modal = document.getElementById('skill-edit-modal');
    if (modal) modal.dataset.tempImage = '';
}

function closeSkillEditModal() {
    var modal = document.getElementById('skill-edit-modal');
    if (modal) modal.remove();
}

function saveSkillEdit(treeId) {
    var index = loadSkillTreeIndexLocal();
    var found = false;
    for (var i = 0; i < index.length; i++) {
        if (index[i].id === treeId) {
            var modal = document.getElementById('skill-edit-modal');
            // 图片：优先取上传的临时图片，无则清空
            var newImage = modal ? (modal.dataset.tempImage !== undefined ? modal.dataset.tempImage : '') : '';
            index[i].image = newImage;
            // 备注
            var remarkInput = document.getElementById('skill-edit-remark');
            index[i].remark = remarkInput ? remarkInput.value.trim() : '';
            index[i].updatedAt = new Date().toISOString();
            found = true;
            break;
        }
    }
    if (!found) { showToast('技能数据异常', 'error'); return; }

    saveSkillTreeIndexLocal(index);
    closeSkillEditModal();
    showToast('✅ 已保存');
    // 重新渲染
    renderSkillMine();
}