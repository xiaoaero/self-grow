/* ================================================================
   Rewards Page — 奖励商城（结构化条件 + 后端驱动）
   ================================================================ */

let rewards = [];
let rewardFilter = 'all';
let rewardStateFilter = 'all';
let rewardModalActive = false;
let rewardHistoryExpanded = null;
let rewardEditMode = false;
let rewardDeleteMode = false;
let rewardSelectedForDelete = new Set();

/* ---- 条件类型定义 ---- */
const CONDITION_TYPES = [
    { value: 'level',           label: '等级达到',      needsTarget: false },
    { value: 'dim_level',       label: '维度等级达到',   needsTarget: true,  targetType: 'dimension' },
    { value: 'total_exp',       label: '累计经验值达到',  needsTarget: false },
    { value: 'exp_since_create',label: '创建后获得经验',  needsTarget: false },
    { value: 'habit_streak',    label: '习惯连续打卡',   needsTarget: true,  targetType: 'habit' },
    { value: 'habit_streak_any',label: '任意习惯连续打卡',needsTarget: false },
    { value: 'milestone',       label: '目标里程碑数',   needsTarget: true,  targetType: 'goal' },
    { value: 'tasks_done',      label: '完成任务数',     needsTarget: false },
    { value: 'goals_done',      label: '达成目标数',     needsTarget: false },
    { value: 'week_rate',       label: '本周完成率(%)',  needsTarget: false },
    { value: 'manual',          label: '手动确认完成',   needsTarget: false },
];

const DIMENSION_OPTIONS = [
    { key: 'health',   name: '健康' },
    { key: 'study',    name: '学习' },
    { key: 'relation', name: '关系' },
    { key: 'work',     name: '工作' },
    { key: 'create',   name: '创作' },
    { key: 'finance',  name: '财务' },
    { key: 'hobby',    name: '爱好' },
    { key: 'soul',     name: '心灵' },
];

/* ---- 条件描述（从前端数据结构生成可读文本） ---- */
function describeCondition(cond) {
    switch (cond.type) {
        case 'level':           return `等级达到 Lv${cond.threshold}`;
        case 'dim_level':       return `${dimNameByKey(cond.targetId)}维度达到 Lv${cond.threshold}`;
        case 'total_exp':       return `累计获得 ${cond.threshold} EXP`;
        case 'exp_since_create':return `创建后获得 ${cond.threshold} EXP`;
        case 'habit_streak':    return `「${habitNameById(cond.targetId)}」连续打卡 ${cond.threshold} 天`;
        case 'habit_streak_any':return `任意习惯连续打卡 ${cond.threshold} 天`;
        case 'milestone':       return `「${goalNameById(cond.targetId)}」达成 ${cond.threshold} 个里程碑`;
        case 'tasks_done':      return `完成 ${cond.threshold} 个任务`;
        case 'goals_done':      return `达成 ${cond.threshold} 个目标`;
        case 'week_rate':       return `本周完成率 ≥ ${cond.threshold}%`;
        case 'manual':          return '手动确认完成';
        default:                return '未知条件';
    }
}

function dimNameByKey(key) {
    const d = DIMENSION_OPTIONS.find(x => x.key === key);
    return d ? d.name : key;
}

function habitNameById(id) {
    const h = AppData.habits.find(x => x.id === Number(id));
    return h ? h.name : `#${id}`;
}

function goalNameById(id) {
    const g = AppData.goals.find(x => x.id === Number(id));
    return g ? g.title : `#${id}`;
}

/* ================================================================
   主渲染
   ================================================================ */

async function renderRewards() {
    // 从后端加载（含自动评估）
    const userId = AppData.user?.id;
    if (userId) {
        const result = await fetchRewards(userId);
        if (result && result.rewards) {
            rewards = result.rewards;
        }
    }

    const categories = [...new Set(rewards.map(r => r.category).filter(Boolean))];

    let filtered;
    if (rewardStateFilter === 'claimed') {
        filtered = rewards.filter(r => r.claimed);
    } else {
        filtered = rewards.filter(r => !r.claimed);
    }
    if (rewardFilter !== 'all') filtered = filtered.filter(r => r.category === rewardFilter);
    if (rewardStateFilter === 'unlocked') filtered = filtered.filter(r => r.unlocked);
    else if (rewardStateFilter === 'locked') filtered = filtered.filter(r => !r.unlocked);
    filtered.sort((a, b) => (a.unlocked ? 0 : 1) - (b.unlocked ? 0 : 1));

    const html = `
        <div class="page-header page-header--with-icon">
            <div class="page-header__icon" style="width:58px;height:58px">${HEADER_ICONS.rewards}</div>
            <div style="flex:1;display:flex;justify-content:space-between;align-items:flex-start">
                <div>
                    <h1 class="page-header__title">奖励商城</h1>
                    <p class="page-header__subtitle">达到条件解锁奖励，满足要求即可领取</p>
                </div>
                <button class="btn btn--primary" onclick="openRewardModal()">+ 自定义奖励</button>
            </div>
        </div>

        <div class="goal-toolbar" style="margin-bottom:20px">
            <div class="goal-toolbar__left" style="display:flex;align-items:center;gap:10px;flex-wrap:wrap">
                <div class="tag-group" style="margin:0">
                    <span class="tag ${rewardStateFilter === 'all' ? 'tag--active' : ''}" onclick="setRewardStateFilter('all')">全部</span>
                    <span class="tag ${rewardStateFilter === 'unlocked' ? 'tag--active' : ''}" onclick="setRewardStateFilter('unlocked')">可领取</span>
                    <span class="tag ${rewardStateFilter === 'locked' ? 'tag--active' : ''}" onclick="setRewardStateFilter('locked')">未解锁</span>
                    <span class="tag ${rewardStateFilter === 'claimed' ? 'tag--active' : ''}" onclick="setRewardStateFilter('claimed')">已领取</span>
                </div>
                <span style="color:#3f3f46;font-size:12px">|</span>
                <div class="tag-group" style="margin:0">
                    <span class="tag ${rewardFilter === 'all' ? 'tag--active' : ''}" onclick="setRewardFilter('all')">全部分类</span>
                    ${categories.map(cat => `
                        <span class="tag ${rewardFilter === cat ? 'tag--active' : ''}" onclick="setRewardFilter('${cat}')">${cat}</span>
                    `).join('')}
                </div>
            </div>
            <div class="goal-toolbar__right" style="display:flex;gap:8px">
                ${rewardDeleteMode ? `
                    <button class="goal-delete-mode-btn goal-delete-mode-btn--active" onclick="confirmRewardDelete()">确认删除（${rewardSelectedForDelete.size}）</button>
                    <button class="btn btn--ghost" onclick="toggleRewardDeleteMode()" style="font-size:12px;padding:4px 10px">取消</button>
                ` : `
                    <button class="btn btn--ghost" onclick="toggleRewardEditMode()" style="font-size:12px;padding:4px 12px">✎ 编辑</button>
                    <button class="btn btn--ghost habit-delete-entry" onclick="toggleRewardDeleteMode()" style="color:#f26b68;font-size:12px;padding:4px 10px">🗑 删除</button>
                `}
            </div>
        </div>

        <div class="reward-grid">
            ${filtered.map(reward => renderRewardCard(reward)).join('')}
        </div>

        ${filtered.length === 0 ? `
            <div class="empty-state">
                <div style="font-size:48px;margin-bottom:12px">🎁</div>
                <div class="empty-state__title">暂无奖励</div>
                <div class="empty-state__desc">添加一个自定义奖励来激励自己吧！</div>
            </div>
        ` : ''}

        ${renderClaimHistory()}
    `;

    document.getElementById('page-rewards').innerHTML = html;
}

/* ---- 渲染条件行 ---- */
function renderConditionRow(cond, reward) {
    const desc = describeCondition(cond);
    const autoMet = checkConditionLocally(cond, reward);
    const manualList = reward.manual_confirmed || [];
    const isManualConfirmed = manualList.includes(desc);
    const isMet = autoMet || isManualConfirmed;

    if (cond.type === 'manual') {
        const confirmed = manualList.includes(cond._label || desc);
        return `
            <div class="reward-card__cond-item">
                <span class="reward-card__cond-dot">●</span>
                <span>${cond._label || '手动确认'}</span>
                ${confirmed ? `<span class="reward-card__cond-check">✓</span>` : `
                    <button class="reward-cond-manual-btn" onclick="event.stopPropagation();doManualConfirm(${reward.id}, '${escapeHtml(cond._label || desc).replace(/'/g, "\\'")}')">☐ 确认完成</button>
                `}
            </div>
        `;
    }

    return `
        <div class="reward-card__cond-item">
            <span class="reward-card__cond-dot">●</span>
            <span>${desc}</span>
            ${isMet ? `<span class="reward-card__cond-check">✓</span>` : ''}
        </div>
    `;
}

/* ---- 前端本地快速判断（用于 UI 即时反馈，后端做权威判断） ---- */
function checkConditionLocally(cond, reward) {
    // 这个函数只做快速 UI 反馈，不替代后端评估
    // 后端在 GET /api/rewards 时已经评估过 unlocked 状态
    // 前端主要用于渲染 ✓ 标记
    const userId = AppData.user?.id;
    const ctype = cond.type;
    const threshold = cond.threshold || 0;
    const targetId = cond.targetId;

    if (ctype === 'level') return (AppData.user?.level || 0) >= threshold;
    if (ctype === 'dim_level') {
        const dim = (AppData.profile?.dimensions || []).find(d => d.key === targetId);
        return dim && dim.level >= threshold;
    }
    if (ctype === 'total_exp') return (AppData.user?.totalExp || 0) >= threshold;
    if (ctype === 'exp_since_create') {
        const base = reward.created_at_exp || 0;
        return (AppData.user?.totalExp || 0) - base >= threshold;
    }
    if (ctype === 'habit_streak') {
        const h = AppData.habits.find(x => x.id === Number(targetId));
        return h && (h.streak || 0) >= threshold;
    }
    if (ctype === 'habit_streak_any') {
        const maxStreak = Math.max(...AppData.habits.filter(h => h.active !== false).map(h => h.streak || 0), 0);
        return maxStreak >= threshold;
    }
    if (ctype === 'milestone') {
        const g = AppData.goals.find(x => x.id === Number(targetId));
        if (!g || !g.milestones) return false;
        return g.milestones.filter(m => m.done).length >= threshold;
    }
    if (ctype === 'tasks_done') return (AppData.profile?.tasksCompleted || 0) >= threshold;
    if (ctype === 'goals_done') return (AppData.profile?.goalsAchieved || 0) >= threshold;
    if (ctype === 'week_rate') {
        // 简略前端判断
        return false;
    }
    return false;
}

/* ---- 渲染单个奖励卡片 ---- */
function renderRewardCard(reward) {
    const unlockConds = reward.unlock_conditions || [];
    const claimConds = reward.claim_conditions || [];
    const isUnlocked = reward.unlocked;
    const isClaimed = reward.claimed;
    const isSelected = rewardSelectedForDelete.has(reward.id);

    let cardClass = '';
    let overlayHtml = '';
    let footerHtml = '';
    let topRightHtml = '';

    if (rewardEditMode && !rewardDeleteMode) {
        topRightHtml = `
            <div class="reward-card__edit-btn" onclick="event.stopPropagation();editRewardCard(${reward.id})" title="编辑">✎</div>
        `;
    }
    if (rewardDeleteMode) {
        topRightHtml = `
            <div class="reward-card__select ${isSelected ? 'reward-card__select--active' : ''}" onclick="event.stopPropagation();toggleRewardSelect(${reward.id})">
                ${isSelected ? '✓' : ''}
            </div>
        `;
    }

    if (isClaimed) {
        cardClass = 'reward-card--claimed';
        footerHtml = `<div class="reward-card__claimed-badge">✅ 已领取 ${reward.claimed_at || ''}</div>`;
    } else if (!isUnlocked) {
        cardClass = 'reward-card--locked';
        overlayHtml = `
            <div class="reward-card__lock-overlay">
                <div class="reward-card__lock-icon">🔒</div>
                <div class="reward-card__lock-text">未解锁</div>
            </div>
        `;
        footerHtml = `
            <div class="reward-card__cond-section">
                <div class="reward-card__cond-label">🔒 解锁条件</div>
                <div class="reward-card__conditions">
                    ${unlockConds.map(c => renderConditionRow(c, reward)).join('')}
                </div>
            </div>
        `;
    } else {
        const allClaimMet = claimConds.length === 0 || claimConds.every(c => {
            if (c.type === 'manual') return (reward.manual_confirmed || []).includes(c._label || describeCondition(c));
            return checkConditionLocally(c, reward);
        });
        footerHtml = `
            ${claimConds.length > 0 ? `
                <div class="reward-card__cond-section">
                    <div class="reward-card__cond-label">🎯 领取条件</div>
                    <div class="reward-card__conditions">
                        ${claimConds.map(c => renderConditionRow(c, reward)).join('')}
                    </div>
                </div>
            ` : ''}
            <div class="reward-card__footer">
                <div style="font-size:11px;color:#6b7280">${claimConds.length} 个领取条件</div>
                <button class="btn btn--accent btn--sm" ${!allClaimMet ? 'disabled' : ''}
                        onclick="claimReward(${reward.id})"
                        title="${!allClaimMet ? '领取条件未满足' : ''}">
                    🎁 领取
                </button>
            </div>
        `;
    }

    return `
        <div class="card reward-card ${cardClass}">
            ${topRightHtml}
            <div class="reward-card__image">
                ${reward.image ? `<img src="${reward.image}" style="width:100%;height:100%;object-fit:cover" onerror="this.style.display='none';this.nextElementSibling.style.display='flex'">` : ''}
                <span style="font-size:48px;${reward.image ? 'display:none' : ''}">${reward.icon || '🎁'}</span>
                ${overlayHtml}
            </div>
            <div class="reward-card__body">
                <div class="reward-card__title">${reward.title}</div>
                <div class="reward-card__desc">${reward.desc}</div>
                ${footerHtml}
            </div>
        </div>
    `;
}

/* ================================================================
   编辑 / 删除模式
   ================================================================ */

function toggleRewardEditMode() {
    rewardEditMode = !rewardEditMode;
    if (rewardEditMode) rewardDeleteMode = false;
    renderRewards();
}

function editRewardCard(id) {
    rewardEditMode = false;
    openRewardModal(id);
}

function toggleRewardDeleteMode() {
    rewardDeleteMode = !rewardDeleteMode;
    rewardSelectedForDelete = new Set();
    if (rewardDeleteMode) rewardEditMode = false;
    renderRewards();
}

function toggleRewardSelect(id) {
    if (rewardSelectedForDelete.has(id)) rewardSelectedForDelete.delete(id);
    else rewardSelectedForDelete.add(id);
    renderRewards();
}

async function confirmRewardDelete() {
    if (rewardSelectedForDelete.size === 0) {
        showToast('请先选择要删除的奖励', 'info');
        return;
    }
    if (!confirm(`确定要删除选中的 ${rewardSelectedForDelete.size} 个奖励吗？此操作不可撤销。`)) return;
    for (const id of rewardSelectedForDelete) {
        await deleteRewardOnBackend(id);
    }
    rewardDeleteMode = false;
    rewardSelectedForDelete = new Set();
    await renderRewards();
    showToast('已删除', 'info');
}

/* ================================================================
   领取奖励
   ================================================================ */

async function claimReward(id) {
    const reward = rewards.find(r => r.id === id);
    if (!reward || reward.claimed) return;
    if (!reward.unlocked) {
        showToast('奖励尚未解锁', 'info');
        return;
    }
    if (!confirm(`确定要领取「${reward.title}」吗？`)) return;

    const userId = AppData.user?.id;
    const result = await claimRewardOnBackend(userId, id);
    if (!result) {
        showToast('领取条件未满足或已领取', 'info');
        return;
    }
    showToast(`🎁 已领取：${reward.title}`, 'success');
    await renderRewards();
}

/* ---- 手动确认 ---- */
async function doManualConfirm(rewardId, conditionText) {
    const result = await manualConfirmConditionOnBackend(rewardId, conditionText);
    if (result) {
        showToast('条件已手动确认 ✓', 'success');
        await renderRewards();
    }
}

/* ================================================================
   领取历史
   ================================================================ */

function renderClaimHistory() {
    const claimed = rewards.filter(r => r.claimed);
    if (claimed.length === 0) return '';

    return `
        <div class="card" style="margin-top:24px">
            <div class="section__title">📜 领取历史</div>
            <div class="reward-history-list">
                ${claimed.map(r => {
                    const isExpanded = rewardHistoryExpanded === r.id;
                    const unlockConds = r.unlock_conditions || [];
                    const claimConds = r.claim_conditions || [];
                    return `
                        <div class="reward-history-item ${isExpanded ? 'reward-history-item--expanded' : ''}">
                            <div class="reward-history-item__main" onclick="toggleRewardHistory(${r.id})">
                                <div class="reward-history-item__icon" style="background:rgba(212,154,62,0.12)">
                                    ${r.icon || '🎁'}
                                </div>
                                <div class="reward-history-item__info">
                                    <div class="reward-history-item__title">${r.title}</div>
                                    <div class="reward-history-item__meta">${r.claimed_at}</div>
                                </div>
                                <span class="reward-history-item__arrow">${isExpanded ? '▾' : '▸'}</span>
                            </div>
                            ${isExpanded ? `
                                <div class="reward-history-item__detail">
                                    ${r.desc ? `<p style="margin-bottom:10px;color:#9ca3af;font-size:12px">${r.desc}</p>` : ''}
                                    ${unlockConds.length > 0 ? `
                                        <div class="reward-card__cond-section">
                                            <div class="reward-card__cond-label">🔒 解锁条件</div>
                                            <div class="reward-card__conditions">
                                                ${unlockConds.map(c => `
                                                    <div class="reward-card__cond-item">
                                                        <span class="reward-card__cond-dot">●</span>
                                                        <span>${describeCondition(c)} ✅</span>
                                                    </div>
                                                `).join('')}
                                            </div>
                                        </div>
                                    ` : ''}
                                    ${claimConds.length > 0 ? `
                                        <div class="reward-card__cond-section" style="margin-top:8px">
                                            <div class="reward-card__cond-label">🎯 领取条件</div>
                                            <div class="reward-card__conditions">
                                                ${claimConds.map(c => `
                                                    <div class="reward-card__cond-item">
                                                        <span class="reward-card__cond-dot reward-card__cond-dot--claim">●</span>
                                                        <span>${describeCondition(c)} ✅</span>
                                                    </div>
                                                `).join('')}
                                            </div>
                                        </div>
                                    ` : ''}
                                </div>
                            ` : ''}
                        </div>
                    `;
                }).join('')}
            </div>
        </div>
    `;
}

function toggleRewardHistory(id) {
    rewardHistoryExpanded = rewardHistoryExpanded === id ? null : id;
    renderRewards();
}

/* ================================================================
   筛选器
   ================================================================ */

function setRewardFilter(filter) {
    rewardFilter = filter;
    renderRewards();
}

function setRewardStateFilter(filter) {
    rewardStateFilter = filter;
    renderRewards();
}

/* ================================================================
   条件类型工具
   ================================================================ */

function getCondTypeInfo(value) {
    return CONDITION_TYPES.find(t => t.value === value) || CONDITION_TYPES[0];
}

/* ================================================================
   奖励编辑弹窗（结构化条件输入）
   ================================================================ */

function openRewardModal(editId) {
    const existing = editId ? rewards.find(r => r.id === editId) : null;
    const existingImage = existing && existing.image ? existing.image : '';
    const unlockConds = existing && existing.unlock_conditions ? existing.unlock_conditions : [null];
    const claimConds = existing && existing.claim_conditions ? existing.claim_conditions : [null];

    const content = `
        <div style="display:flex;flex-direction:column;gap:16px">
            <div>
                <label class="action-form__label">奖励名称</label>
                <input class="input" id="reward-title" placeholder="例如：看一部电影" value="${existing ? escapeHtml(existing.title) : ''}">
            </div>
            <div>
                <label class="action-form__label">描述</label>
                <textarea class="input" id="reward-desc" placeholder="描述这个奖励..." style="height:60px;resize:none">${existing ? escapeHtml(existing.desc || '') : ''}</textarea>
            </div>
            <div>
                <label class="action-form__label">分类</label>
                <input class="input" id="reward-category" placeholder="例如：娱乐、学习、生活" value="${existing ? escapeHtml(existing.category || '') : ''}">
            </div>
            <div>
                <label class="action-form__label">图标 (emoji)</label>
                <input class="input" id="reward-icon" placeholder="🎁" value="${existing ? escapeHtml(existing.icon || '🎁') : '🎁'}">
            </div>
            <div>
                <label class="action-form__label">解锁条件</label>
                <div id="reward-unlock-list" style="display:flex;flex-direction:column;gap:10px">
                    ${unlockConds.map((c, i) => renderConditionFormRow(c, i, 'unlock')).join('')}
                </div>
                <button class="btn btn--ghost" onclick="addConditionRow('unlock')" type="button" style="font-size:12px;margin-top:6px">+ 添加解锁条件</button>
                <div style="font-size:11px;color:#6b7280;margin-top:4px">最多3个解锁条件，全部满足后奖励才解锁</div>
            </div>
            <div>
                <label class="action-form__label">展示图片</label>
                <div style="display:flex;gap:8px;align-items:center">
                    <input class="input" id="reward-image" placeholder="图片URL" value="${existingImage}" style="flex:1">
                    <label class="btn btn--ghost" style="cursor:pointer;white-space:nowrap;padding:0 14px;line-height:36px">
                        📁 上传
                        <input type="file" accept="image/*" onchange="handleRewardImageUpload(event)" style="display:none">
                    </label>
                </div>
                ${existingImage ? `<div style="margin-top:8px"><img src="${existingImage}" style="max-width:200px;max-height:120px;border-radius:8px;border:1px solid #3f3f46" onerror="this.style.display='none'"></div>` : ''}
            </div>
            <div>
                <label class="action-form__label">领取条件</label>
                <div id="reward-claim-list" style="display:flex;flex-direction:column;gap:10px">
                    ${claimConds.map((c, i) => renderConditionFormRow(c, i, 'claim')).join('')}
                </div>
                <button class="btn btn--ghost" onclick="addConditionRow('claim')" type="button" style="font-size:12px;margin-top:6px">+ 添加领取条件</button>
                <div style="font-size:11px;color:#6b7280;margin-top:4px">最多5个领取条件，全部满足后才能领取</div>
            </div>
        </div>
        <div class="modal__actions">
            <button class="btn btn--ghost" onclick="cancelRewardModal()">取消</button>
            <button class="btn btn--primary" onclick="saveReward(${editId || 0})">${editId ? '保存' : '创建'}</button>
        </div>
    `;
    rewardModalActive = true;
    openModal(existing ? '编辑奖励' : '自定义奖励', content);
}

/* ---- 渲染单行条件输入 ---- */
function renderConditionFormRow(cond, index, listType) {
    const typeValue = cond ? cond.type : 'total_exp';
    const typeInfo = getCondTypeInfo(typeValue);
    const threshold = cond ? (cond.threshold || '') : '';
    const targetId = cond ? (cond.targetId || '') : '';

    let targetSelector = '';
    if (typeInfo.needsTarget) {
        if (typeInfo.targetType === 'dimension') {
            targetSelector = `
                <select class="input cond-target-select" style="width:auto;min-width:100px" data-list="${listType}" data-index="${index}">
                    <option value="">选择维度</option>
                    ${DIMENSION_OPTIONS.map(d => `
                        <option value="${d.key}" ${targetId === d.key ? 'selected' : ''}>${d.name}</option>
                    `).join('')}
                </select>
            `;
        } else if (typeInfo.targetType === 'habit') {
            const habits = AppData.habits || [];
            targetSelector = `
                <select class="input cond-target-select" style="width:auto;min-width:120px" data-list="${listType}" data-index="${index}">
                    <option value="">选择习惯</option>
                    ${habits.map(h => `
                        <option value="${h.id}" ${String(targetId) === String(h.id) ? 'selected' : ''}>${h.name}</option>
                    `).join('')}
                </select>
            `;
        } else if (typeInfo.targetType === 'goal') {
            const goals = AppData.goals || [];
            targetSelector = `
                <select class="input cond-target-select" style="width:auto;min-width:120px" data-list="${listType}" data-index="${index}">
                    <option value="">选择目标</option>
                    ${goals.map(g => `
                        <option value="${g.id}" ${String(targetId) === String(g.id) ? 'selected' : ''}>${escapeHtml(g.title)}</option>
                    `).join('')}
                </select>
            `;
        }
    }

    let manualLabelHtml = '';
    if (typeValue === 'manual') {
        manualLabelHtml = `
            <input class="input cond-manual-label" placeholder="描述需要手动确认的内容" value="${cond && cond._label ? escapeHtml(cond._label) : ''}" style="width:200px" data-list="${listType}" data-index="${index}">
        `;
    }

    return `
        <div class="reward-condition-row" style="display:flex;gap:6px;align-items:center;flex-wrap:wrap">
            <select class="input cond-type-select" style="width:auto;min-width:140px" data-list="${listType}" data-index="${index}" onchange="onCondTypeChange(this, ${index}, '${listType}')">
                ${CONDITION_TYPES.map(t => `
                    <option value="${t.value}" ${typeValue === t.value ? 'selected' : ''}>${t.label}</option>
                `).join('')}
            </select>
            ${targetSelector}
            ${manualLabelHtml}
            ${typeValue !== 'manual' ? `
                <input class="input cond-threshold-input" type="number" min="1" placeholder="阈值" value="${threshold}" style="width:80px" data-list="${listType}" data-index="${index}">
            ` : ''}
            <button class="btn btn--ghost" onclick="removeConditionFormRow(this)" type="button" style="font-size:16px;padding:0 8px;line-height:36px;color:#f26b68" title="删除条件">✕</button>
        </div>
    `;
}

/* ---- 条件类型切换时动态更新 ---- */
function onCondTypeChange(selectEl, index, listType) {
    const row = selectEl.closest('.reward-condition-row');
    const typeValue = selectEl.value;
    const typeInfo = getCondTypeInfo(typeValue);

    // 移除旧的 target selector / threshold / manual label
    row.querySelectorAll('.cond-target-select, .cond-threshold-input, .cond-manual-label').forEach(el => el.remove());

    let targetSelector = '';
    if (typeInfo.needsTarget) {
        if (typeInfo.targetType === 'dimension') {
            targetSelector = `
                <select class="input cond-target-select" style="width:auto;min-width:100px" data-list="${listType}" data-index="${index}">
                    <option value="">选择维度</option>
                    ${DIMENSION_OPTIONS.map(d => `<option value="${d.key}">${d.name}</option>`).join('')}
                </select>
            `;
        } else if (typeInfo.targetType === 'habit') {
            const habits = AppData.habits || [];
            targetSelector = `
                <select class="input cond-target-select" style="width:auto;min-width:120px" data-list="${listType}" data-index="${index}">
                    <option value="">选择习惯</option>
                    ${habits.map(h => `<option value="${h.id}">${h.name}</option>`).join('')}
                </select>
            `;
        } else if (typeInfo.targetType === 'goal') {
            const goals = AppData.goals || [];
            targetSelector = `
                <select class="input cond-target-select" style="width:auto;min-width:120px" data-list="${listType}" data-index="${index}">
                    <option value="">选择目标</option>
                    ${goals.map(g => `<option value="${g.id}">${escapeHtml(g.title)}</option>`).join('')}
                </select>
            `;
        }
    }

    let extraHtml = '';
    if (typeValue === 'manual') {
        extraHtml = `<input class="input cond-manual-label" placeholder="描述需要手动确认的内容" style="width:200px" data-list="${listType}" data-index="${index}">`;
    } else {
        extraHtml = `<input class="input cond-threshold-input" type="number" min="1" placeholder="阈值" value="" style="width:80px" data-list="${listType}" data-index="${index}">`;
    }

    // 在 ✕ 按钮前插入
    const removeBtn = row.querySelector('button:last-child');
    removeBtn.insertAdjacentHTML('beforebegin', targetSelector + extraHtml);
}

/* ---- 添加条件行 ---- */
function addConditionRow(listType) {
    const listId = listType === 'unlock' ? 'reward-unlock-list' : 'reward-claim-list';
    const list = document.getElementById(listId);
    const rows = list.querySelectorAll('.reward-condition-row');
    const max = listType === 'unlock' ? 3 : 5;
    if (rows.length >= max) {
        showToast(`最多支持${max}个条件`, 'info');
        return;
    }
    const index = rows.length;
    const div = document.createElement('div');
    div.style.cssText = 'display:flex;gap:6px;align-items:center;flex-wrap:wrap';
    div.innerHTML = renderConditionFormRow(null, index, listType);
    list.appendChild(div);
}

/* ---- 删除条件行 ---- */
function removeConditionFormRow(btn) {
    btn.closest('.reward-condition-row').remove();
}

/* ---- 图片上传 ---- */
async function handleRewardImageUpload(event) {
    const file = event.target.files[0];
    if (!file) return;
    // 如果有正在编辑的奖励，直接上传到后端
    const imageInput = document.getElementById('reward-image');
    // 暂时用 FileReader 预览（保存时若 editId 存在再上传到后端）
    const reader = new FileReader();
    reader.onload = function(e) {
        imageInput.value = e.target.result;
        showToast('图片已导入', 'success');
    };
    reader.readAsDataURL(file);
}

/* ---- 取消 ---- */
function cancelRewardModal() {
    rewardModalActive = false;
    closeModal();
}

/* ---- 保存 ---- */
async function saveReward(editId) {
    const title = document.getElementById('reward-title').value.trim();
    const desc = document.getElementById('reward-desc').value.trim();
    const category = document.getElementById('reward-category').value.trim();
    const icon = document.getElementById('reward-icon').value.trim() || '🎁';
    const image = document.getElementById('reward-image').value.trim();

    if (!title) { showToast('请输入奖励名称', 'error'); return; }

    // 收集解锁条件
    const unlockConditions = collectConditions('reward-unlock-list');
    // 收集领取条件
    const claimConditions = collectConditions('reward-claim-list');

    const userId = AppData.user?.id;

    if (editId) {
        const data = {
            title, desc, icon, category, image,
            unlock_conditions: unlockConditions,
            claim_conditions: claimConditions,
        };
        const result = await updateRewardOnBackend(editId, data);
        if (!result) { showToast('更新失败', 'error'); return; }
    } else {
        const data = {
            title, desc, icon, category, image,
            unlock_conditions: unlockConditions,
            claim_conditions: claimConditions,
        };
        const result = await createRewardOnBackend(userId, data);
        if (!result) { showToast('创建失败', 'error'); return; }
    }

    rewardModalActive = false;
    closeModal();
    await renderRewards();
    showToast(editId ? '奖励已更新' : '自定义奖励已创建！', 'success');
}

/* ---- 从 DOM 收集条件数据 ---- */
function collectConditions(listId) {
    const list = document.getElementById(listId);
    const rows = list.querySelectorAll('.reward-condition-row');
    const conditions = [];

    rows.forEach(row => {
        const typeSelect = row.querySelector('.cond-type-select');
        const thresholdInput = row.querySelector('.cond-threshold-input');
        const targetSelect = row.querySelector('.cond-target-select');
        const manualLabel = row.querySelector('.cond-manual-label');

        if (!typeSelect) return;
        const type = typeSelect.value;
        const threshold = thresholdInput ? parseInt(thresholdInput.value) || 1 : 1;
        const targetId = targetSelect ? targetSelect.value : undefined;
        const label = manualLabel ? manualLabel.value.trim() : undefined;

        const cond = { type };
        if (type !== 'manual') cond.threshold = threshold;
        if (targetId) cond.targetId = targetId;
        if (label) cond._label = label;

        conditions.push(cond);
    });

    return conditions;
}