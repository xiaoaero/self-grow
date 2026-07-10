/* ================================================================
   Goals Page — 目标管理
   ================================================================ */

let goals = [];
let goalsLoaded = false;
let goalFilterCategory = 'all';
let goalDeleteMode = false;

/** Migrate old milestone format [0,1,0] → [{done,note},...] */
function migrateMilestones(milestones) {
    if (!milestones || milestones.length === 0) return [];
    // If first element is a plain number, migrate
    if (typeof milestones[0] === 'number') {
        return milestones.map(v => ({ done: v, note: '' }));
    }
    return milestones;
}

// Migrate on load
goals.forEach(g => { g.milestones = migrateMilestones(g.milestones); });

/** Category → progress bar gradient & icon color mapping */
const GOAL_COLORS = {
    health:   { bar: 'linear-gradient(90deg, #F26B68, #FF7B72)', icon: '#FF7B72' },
    study:    { bar: 'linear-gradient(90deg, #32B8B0, #46C9C0)', icon: '#46C9C0' },
    relation: { bar: 'linear-gradient(90deg, #F06590, #FF91A8)', icon: '#FF91A8' },
    work:     { bar: 'linear-gradient(90deg, #F7C242, #FFCA40)', icon: '#FFCA40' },
    create:   { bar: 'linear-gradient(90deg, #8B5CF6, #B794F6)', icon: '#B794F6' },
    finance:  { bar: 'linear-gradient(90deg, #22C55E, #4ADE80)', icon: '#4ADE80' },
    hobby:    { bar: 'linear-gradient(90deg, #E879F9, #F472B6)', icon: '#F472B6' },
    soul:     { bar: 'linear-gradient(90deg, #F97316, #FBBF24)', icon: '#FBBF24' },
};

function renderGoals() {
    // 从后端加载
    if (!goalsLoaded) {
        loadGoalsFromBackend();
        // 先显示 loading
        document.getElementById('page-goals').innerHTML = `
            <div style="text-align:center;padding:60px;color:var(--color-text-secondary)">加载中...</div>
        `;
        return;
    }

    const filtered = goalFilterCategory === 'all'
        ? goals
        : goals.filter(g => g.category === goalFilterCategory);

    const html = `
        <div class="page-header page-header--with-icon">
            <div class="page-header__icon" style="width:58px;height:58px">${HEADER_ICONS.goals}</div>
            <div style="flex:1;display:flex;justify-content:space-between;align-items:flex-start">
                <div>
                    <h1 class="page-header__title">目标</h1>
                    <p class="page-header__subtitle">设定长期目标，追踪每一个里程碑</p>
                </div>
                <button class="goal-create-btn" onclick="openGoalModal()">+ 新建目标</button>
            </div>
        </div>

        <!-- Toolbar: filter + delete mode -->
        <div class="goal-toolbar">
            <div class="goal-toolbar__left">
                <span class="goal-toolbar__label">筛选</span>
                <select class="goal-filter-select" onchange="goalFilterCategory=this.value;renderGoals()">
                    <option value="all" ${goalFilterCategory === 'all' ? 'selected' : ''}>全部属性</option>
                    ${AppData.categories.map(c => `
                        <option value="${c.id}" ${goalFilterCategory === c.id ? 'selected' : ''}>${c.name}</option>
                    `).join('')}
                </select>
                <span class="goal-toolbar__count">${filtered.length} 个目标</span>
            </div>
            <button class="goal-delete-mode-btn ${goalDeleteMode ? 'goal-delete-mode-btn--active' : ''}"
                    onclick="toggleDeleteMode()">
                ${goalDeleteMode ? '完成删除' : '删除目标'}
            </button>
        </div>

        <div class="goal-list">
            ${filtered.map(goal => renderGoalCard(goal)).join('')}
        </div>

        ${filtered.length === 0 ? `
            <div class="empty-state">
                <div style="font-size:48px;margin-bottom:12px">🎯</div>
                <div class="empty-state__title">${goalFilterCategory !== 'all' ? '该分类下还没有目标' : '还没有目标'}</div>
                <div class="empty-state__desc">设定你的第一个成长目标吧！</div>
            </div>
        ` : ''}
    `;

    document.getElementById('page-goals').innerHTML = html;
}

/** 从后端加载目标数据 */
async function loadGoalsFromBackend() {
    var curUser = getCurrentUser();
    if (!curUser) {
        // 降级到本地 mock
        goals = [...AppData.goals];
        goalsLoaded = true;
        renderGoals();
        return;
    }
    const result = await fetchGoals(curUser.id);
    if (result && result.goals) {
        goals = result.goals;
    } else {
        goals = [...AppData.goals];
    }
    goalsLoaded = true;
    renderGoals();
}

function renderGoalCard(goal) {
    const cat = getCategory(goal.category);
    const catColors = GOAL_COLORS[goal.category] || GOAL_COLORS.study;
    const deadlineDate = new Date(goal.deadline);
    const now = new Date();
    const daysLeft = Math.ceil((deadlineDate - now) / (1000 * 60 * 60 * 24));
    const urgencyColor = daysLeft < 30 ? '#F26B68' : daysLeft < 60 ? '#F7C242' : '#A0A8A6';
    const doneCount = goal.milestones.filter(m => m.done).length;
    const totalCount = goal.milestones.length;

    return `
        <div class="goal-card">
            <!-- Header row: icon + title + time + percentage -->
            <div class="goal-card__header">
                <div class="goal-card__header-left">
                    <span class="goal-card__icon" style="color:${catColors.icon}">
                        ${goal.categoryImage
                            ? `<span class="goal-card__ai-img" style="background-image:url('${goal.categoryImage}')"></span>`
                            : (cat ? attrIcon(cat.id, 20) : '')}
                    </span>
                    <div class="goal-card__header-info">
                        <span class="goal-card__title">${goal.title}</span>
                        <span class="goal-card__meta">
                            ${goal.deadline} · 剩余 <span style="color:${urgencyColor};font-weight:600">${daysLeft} 天</span>
                        </span>
                    </div>
                </div>
                <span class="goal-card__pct">
                    <span class="goal-card__pct-num">${goal.progress}</span><span class="goal-card__pct-sym">%</span>
                </span>
            </div>

            <!-- Milestone dots with tooltip -->
            <div class="goal-card__mstones">
                ${goal.milestones.map((m, i) => {
                    const noteText = m.note || ('里程碑 ' + (i + 1));
                    return `
                        <div class="goal-card__mstone ${m.done ? 'goal-card__mstone--done' : ''} tooltip"
                             style="${m.done ? 'background:' + catColors.bar : ''}"
                             data-tooltip="${escapeHtml(noteText)}"></div>
                    `;
                }).join('')}
            </div>

            ${goal.intro ? `
                <p class="goal-card__intro">${escapeHtml(goal.intro)}</p>
            ` : ''}

            <!-- Bottom row: milestone count + claim/actions -->
            <div class="goal-card__footer">
                <span class="goal-card__mstone-count">${doneCount} / ${totalCount} 里程碑</span>
                <div class="goal-card__actions">
                    ${goal.progress >= 100 && !goal.claimed ? `
                        <button class="goal-card__claim-btn" onclick="claimGoalReward(${goal.id})">
                            🎁 领取 ${goal.rewardExp || 0} EXP
                        </button>
                    ` : goal.claimed ? `
                        <span class="goal-card__claimed">✅ 已领取</span>
                    ` : ''}
                    <button class="goal-card__action goal-card__action--edit" onclick="editGoal(${goal.id})">编辑</button>
                    ${goalDeleteMode ? `
                        <button class="goal-card__action goal-card__action--delete" onclick="deleteGoal(${goal.id})">删除</button>
                    ` : ''}
                </div>
            </div>
        </div>
    `;
}

function toggleDeleteMode() {
    goalDeleteMode = !goalDeleteMode;
    renderGoals();
}

/* ---- Modal ---- */
let goalModalActive = false;

function openGoalModal(editId) {
    const existing = editId ? goals.find(g => g.id === editId) : null;
    const cats = AppData.categories;
    // Default to existing count, or 5 for new goals
    const initialMsCount = existing ? existing.milestones.length : 5;

    function buildMilestonesHtml(count, existingMs) {
        return Array.from({ length: count }, (_, i) => {
            const ms = (existingMs && i < existingMs.length) ? existingMs[i] : null;
            const note = ms ? ms.note : '';
            const done = ms ? ms.done : 0;
            return `
                <div class="goal-ms-edit-row">
                    <span class="goal-ms-edit-row__num">#${i + 1}</span>
                    <input class="goal-ms-edit-row__input"
                           id="goal-ms-note-${i}"
                           placeholder="里程碑 ${i + 1} 备注"
                           value="${escapeHtml(note)}"
                           maxlength="30">
                    <label class="goal-ms-edit-row__check">
                        <input type="checkbox" id="goal-ms-done-${i}" ${done ? 'checked' : ''}
                               onchange="updateMsDoneStyle(${i})">
                        <span class="goal-ms-edit-row__check-label" id="goal-ms-label-${i}">${done ? '已完成' : '未开始'}</span>
                    </label>
                </div>
            `;
        }).join('');
    }

    const content = `
        <div style="display:flex;flex-direction:column;gap:16px">
            <div>
                <label class="action-form__label">目标名称</label>
                <input class="input" id="goal-title" placeholder="例如：完成全栈开发课程" value="${existing ? escapeHtml(existing.title) : ''}">
            </div>
            <div>
                <label class="action-form__label">项目介绍 <span style="font-weight:400;color:var(--color-text-muted)">（简要描述这个目标的意义和预期成果）</span></label>
                <textarea class="input goal-intro-textarea" id="goal-intro" placeholder="例如：系统学习 Web 全栈开发，从前端到后端到部署，打通完整技术链路…" maxlength="200">${existing && existing.intro ? escapeHtml(existing.intro) : ''}</textarea>
            </div>
            <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px">
                <div>
                    <label class="action-form__label">分类</label>
                    <select class="select" id="goal-category" style="width:100%">
                        ${cats.map(cat => `
                            <option value="${cat.id}" ${existing && existing.category === cat.id ? 'selected' : ''}>${cat.name}</option>
                        `).join('')}
                    </select>
                </div>
                <div>
                    <label class="action-form__label">截止日期</label>
                    <input class="input" type="date" id="goal-deadline" value="${existing ? existing.deadline : '2026-12-31'}">
                </div>
                <div>
                    <label class="action-form__label">奖励经验值</label>
                    <input class="input" type="number" id="goal-reward-exp" value="${existing ? (existing.rewardExp || 0) : 300}" min="0" max="9999" step="50">
                </div>
            </div>
            <div>
                <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px">
                    <label class="action-form__label" style="margin-bottom:0">里程碑详情</label>
                    <div style="display:flex;align-items:center;gap:8px">
                        <span style="font-size:12px;color:var(--color-text-muted)">数量</span>
                        <input class="goal-ms-count-input" type="number" id="goal-ms-count"
                               value="${initialMsCount}" min="1" max="20"
                               oninput="this.value = Math.min(20, Math.max(1, this.value || 1))">
                        <button class="goal-ms-apply-btn" onclick="applyMsCount(${editId || 0}, ${initialMsCount})">应用</button>
                    </div>
                </div>
                <div class="goal-ms-edit-list" id="goal-ms-edit-list">
                    ${buildMilestonesHtml(initialMsCount, existing ? existing.milestones : null)}
                </div>
            </div>
        </div>
        <div class="modal__actions">
            <button class="btn btn--ghost" onclick="closeGoalModal()">取消</button>
            <button class="btn btn--primary" onclick="saveGoal(${editId || 0})">${editId ? '保存' : '创建'}</button>
        </div>
    `;

    goalModalActive = true;
    // Store existing reference for applyMsCount
    window._goalEditId = editId || 0;
    window._goalExisting = existing;
    openModal(existing ? '编辑目标' : '新建目标', content);
}

/** Rebuild milestone editor rows when count changes */
function applyMsCount(editId, oldCount) {
    const countInput = document.getElementById('goal-ms-count');
    const newCount = parseInt(countInput.value) || oldCount;
    countInput.value = newCount;

    // Collect current values from existing rows before replacing
    const listEl = document.getElementById('goal-ms-edit-list');
    if (!listEl) return;
    const oldRows = listEl.querySelectorAll('.goal-ms-edit-row');
    const oldData = [];
    oldRows.forEach(row => {
        const noteInput = row.querySelector('.goal-ms-edit-row__input');
        const doneCb = row.querySelector('input[type="checkbox"]');
        oldData.push({
            note: noteInput ? noteInput.value : '',
            done: doneCb && doneCb.checked ? 1 : 0,
        });
    });

    // Build new rows, preserving old data where possible
    let html = '';
    for (let i = 0; i < newCount; i++) {
        const prev = i < oldData.length ? oldData[i] : { note: '', done: 0 };
        html += `
            <div class="goal-ms-edit-row">
                <span class="goal-ms-edit-row__num">#${i + 1}</span>
                <input class="goal-ms-edit-row__input"
                       id="goal-ms-note-${i}"
                       placeholder="里程碑 ${i + 1} 备注"
                       value="${escapeHtml(prev.note)}"
                       maxlength="30">
                <label class="goal-ms-edit-row__check">
                    <input type="checkbox" id="goal-ms-done-${i}" ${prev.done ? 'checked' : ''}
                           onchange="updateMsDoneStyle(${i})">
                    <span class="goal-ms-edit-row__check-label" id="goal-ms-label-${i}">${prev.done ? '已完成' : '未开始'}</span>
                </label>
            </div>
        `;
    }
    listEl.innerHTML = html;
}

function updateMsDoneStyle(idx) {
    const cb = document.getElementById('goal-ms-done-' + idx);
    const label = document.getElementById('goal-ms-label-' + idx);
    if (label) {
        label.textContent = cb && cb.checked ? '已完成' : '未开始';
    }
}

function saveGoal(editId) {
    const title = document.getElementById('goal-title').value.trim();
    const intro = document.getElementById('goal-intro').value.trim();
    const category = document.getElementById('goal-category').value;
    const deadline = document.getElementById('goal-deadline').value;
    const rewardExp = parseInt(document.getElementById('goal-reward-exp').value) || 0;
    const msList = document.getElementById('goal-ms-edit-list');
    const msRows = msList ? msList.querySelectorAll('.goal-ms-edit-row') : [];

    if (!title) {
        showToast('请输入目标名称', 'error');
        return;
    }

    const milestones = [];
    msRows.forEach((row, i) => {
        const noteInput = row.querySelector('.goal-ms-edit-row__input');
        const doneCb = row.querySelector('input[type="checkbox"]');
        milestones.push({
            done: doneCb && doneCb.checked ? 1 : 0,
            note: noteInput ? noteInput.value.trim() : '',
        });
    });

    const curUser = getCurrentUser();
    const goalData = {
        title,
        intro,
        category,
        deadline,
        reward_exp: rewardExp,
        milestones,
    };

    function handleSaveSuccess(savedGoal) {
        closeGoalModal();
        // 刷新列表
        goalsLoaded = false;
        renderGoals();
        showToast(editId ? '目标已更新' : '目标已创建！', 'success');
    }

    function handleSaveLocal() {
        // 降级到本地
        const progress = milestones.length > 0
            ? Math.round((milestones.filter(m => m.done).length / milestones.length) * 100)
            : 0;

        if (editId) {
            const goal = goals.find(g => g.id === editId);
            if (goal) {
                Object.assign(goal, {
                    title, intro, category, deadline,
                    rewardExp, milestones, progress,
                });
            }
        } else {
            goals.push({
                id: Date.now(),
                title, intro, category, deadline,
                rewardExp, milestones, progress,
                claimed: false,
                status: progress >= 100 ? 'completed' : 'active',
                categoryImage: null,
            });
        }
        closeGoalModal();
        renderGoals();
        showToast(editId ? '目标已更新' : '目标已创建！', 'success');
    }

    if (curUser) {
        if (editId) {
            updateGoalOnBackend(editId, goalData).then(result => {
                if (result) handleSaveSuccess(result);
                else handleSaveLocal();
            }).catch(() => handleSaveLocal());
        } else {
            createGoalOnBackend(curUser.id, goalData).then(result => {
                if (result) handleSaveSuccess(result);
                else handleSaveLocal();
            }).catch(() => handleSaveLocal());
        }
    } else {
        handleSaveLocal();
    }
}

function editGoal(id) {
    openGoalModal(id);
}

function deleteGoal(id) {
    if (!confirm('确定要删除这个目标吗？删除后不可恢复。')) return;

    var curUser = getCurrentUser();
    if (curUser) {
        deleteGoalOnBackend(id).then(result => {
            if (result) {
                goals = goals.filter(g => g.id !== id);
                if (goals.length === 0) goalDeleteMode = false;
                renderGoals();
                showToast('目标已删除', 'info');
            } else {
                localDeleteGoal(id);
            }
        }).catch(() => localDeleteGoal(id));
    } else {
        localDeleteGoal(id);
    }
}

function localDeleteGoal(id) {
    goals = goals.filter(g => g.id !== id);
    if (goals.length === 0) goalDeleteMode = false;
    renderGoals();
    showToast('目标已删除', 'info');
}

function claimGoalReward(id) {
    const goal = goals.find(g => g.id === id);
    if (!goal || goal.claimed || goal.progress < 100) return;

    var curUser = getCurrentUser();
    if (curUser) {
        claimGoalOnBackend(id).then(result => {
            if (result) {
                goal.claimed = true;
                AppData.user.exp = result.exp_result.exp;
                AppData.user.level = result.exp_result.level;
                AppData.todayStats.expEarned = result.today_stats.expEarned;
                renderGoals();
                showToast(`目标达成！获得 +${result.exp_earned} EXP`, 'success');
                if (result.exp_result.leveledUp) {
                    setTimeout(() => {
                        showToast(`🎉 升级！Lv.${result.exp_result.oldLevel} → Lv.${result.exp_result.level}`, 'success');
                    }, 500);
                }
                // 重新评估奖励
                if (curUser) reevaluateRewardsOnBackend(curUser.id);
            } else {
                localClaimGoal(id);
            }
        }).catch(() => localClaimGoal(id));
    } else {
        localClaimGoal(id);
    }
}

function localClaimGoal(id) {
    const goal = goals.find(g => g.id === id);
    if (!goal || goal.claimed || goal.progress < 100) return;
    goal.claimed = true;
    AppData.user.exp += goal.rewardExp || 0;
    AppData.todayStats.expEarned += goal.rewardExp || 0;
    renderGoals();
    showToast(`目标达成！获得 +${goal.rewardExp || 0} EXP`, 'success');
}

/** Close goal modal (called by cancel button, not overlay click) */
function closeGoalModal() {
    goalModalActive = false;
    closeModal();
}

// Override closeModal for goal, task, habit & reward modal protection (block outside click)
const _origCloseModal = closeModal;
closeModal = function() {
    if (goalModalActive || (typeof taskModalActive !== 'undefined' && taskModalActive) || (typeof habitModalActive !== 'undefined' && habitModalActive) || (typeof rewardModalActive !== 'undefined' && rewardModalActive)) return;
    _origCloseModal();
};
