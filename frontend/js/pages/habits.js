/* ================================================================
   Habits Page — 习惯追踪（全面改造版）
   ================================================================ */

let habits = [];
let habitStats = null;
let habitInsights = null;
let habitFilterCategory = 'all';
let habitSortBy = 'default';
let habitWeekView = 'this';

let habitModalActive = false;
let habitDeleteMode = false;
let habitSelectedForDelete = new Set();

// DAY_LABELS already defined in utils.js

/* ================================================================
   Main render
   ================================================================ */

/** 从 AppData 刷新本地数据后渲染 */
function refreshHabitsData() {
    habits = [...AppData.habits];
    // 异步加载统计和洞察（不阻塞渲染）
    var user = getCurrentUser();
    if (user) {
        fetchHabitStats(user.id).then(function(s) { if (s) habitStats = s; });
        fetchHabitInsights(user.id).then(function(i) { if (i) habitInsights = i; });
    }
}

function renderHabits() {
    // 确保本地数据是最新的
    refreshHabitsData();

    const html = `
        <div class="page-header page-header--with-icon">
            <div class="page-header__icon" style="width:58px;height:58px">${HEADER_ICONS.habits}</div>
            <div style="flex:1;display:flex;justify-content:space-between;align-items:flex-start">
                <div>
                    <h1 class="page-header__title">习惯追踪</h1>
                    <p class="page-header__subtitle">坚持的每一天，都在变好</p>
                </div>
                <button class="goal-create-btn" onclick="openHabitModal()">+ 新建习惯</button>
            </div>
        </div>

        <!-- Module 1: Stats cards -->
        ${renderModule1_Stats()}

        <!-- Module 2: Weekly overview -->
        ${renderModule2_WeekOverview()}

        <!-- Module 3: Habit cards grid -->
        ${renderModule3_HabitGrid()}

        <!-- Module 4 & 5: Bottom row -->
        <div class="habit-bottom-row">
            ${renderModule4_StreakRanking()}
            ${renderModule5_Insights()}
        </div>
    `;

    document.getElementById('page-habits').innerHTML = html;
}

/* ================================================================
   Module 1: Top Stats Cards (5 columns) — 数据从后端 API 获取
   ================================================================ */
function renderModule1_Stats() {
    // 优先用后端统计，降级到本地计算
    var s = habitStats;
    var activeHabits = habits.filter(function(h) { return h.active !== false; });
    var totalActive = activeHabits.length;
    var inactiveCount = habits.length - totalActive;

    var doneToday, bestStreak, bestStreakHabit, weekRate, rateDiff, monthlyTotal, monthlyXP, diffToday;

    if (s) {
        doneToday = s.doneToday;
        bestStreak = s.bestStreak;
        bestStreakHabit = activeHabits.find(function(h) { return h.streak === s.bestStreak; });
        weekRate = s.weekRate;
        rateDiff = s.rateDiff;
        monthlyTotal = s.monthlyTotal;
        monthlyXP = s.monthlyXP;
        diffToday = s.diffToday;
    } else {
        // 降级：本地计算（后端不可用时）
        doneToday = activeHabits.filter(function(h) { return h.todayDone; }).length;
        bestStreak = activeHabits.length > 0 ? Math.max.apply(null, activeHabits.map(function(h) { return h.streak; })) : 0;
        bestStreakHabit = activeHabits.find(function(h) { return h.streak === bestStreak; });
        weekRate = 0;
        rateDiff = 0;
        monthlyTotal = 0;
        monthlyXP = 0;
        diffToday = 0;
    }

    var diffText = diffToday >= 0 ? '较昨日 +' + diffToday + ' 个' : '较昨日 ' + diffToday + ' 个';
    var diffColor = diffToday >= 0 ? '#22c55e' : '#ef4444';

    var cards = [
        { label: '今日完成', value: doneToday + ' / ' + totalActive, sub: diffText, color: '#22c55e' },
        { label: '最长连续', value: bestStreak + ' 天', sub: bestStreakHabit ? '🔥 ' + bestStreakHabit.name : '-', color: '#f59e0b' },
        { label: '本周完成率', value: weekRate + '%', sub: rateDiff >= 0 ? '↑ 较上周 +' + rateDiff + '%' : '↓ 较上周 ' + rateDiff + '%', color: '#3b82f6' },
        { label: '本月打卡', value: '' + monthlyTotal, sub: '累计 XP +' + monthlyXP, color: '#ec4899' },
        { label: '活跃习惯', value: '' + totalActive, sub: inactiveCount > 0 ? '暂停中 ' + inactiveCount + ' 个' : '全部活跃', color: '#14b8a6' },
    ];

    return `
        <div class="habit-stats-grid">
            ${cards.map(c => `
                <div class="habit-stat-card" style="border-left:3px solid ${c.color}">
                    <div class="habit-stat-card__label">${c.label}</div>
                    <div class="habit-stat-card__value" style="color:${c.color}">${c.value}</div>
                    <div class="habit-stat-card__sub">${c.sub}</div>
                </div>
            `).join('')}
        </div>
    `;
}

/* ================================================================
   Module 2: Weekly Overview
   ================================================================ */
function renderModule2_WeekOverview() {
    const today = new Date();
    const todayDow = today.getDay(); // 0=Sun
    const todayDate = today.getDate();
    const daysFromMonday = todayDow === 0 ? 6 : todayDow - 1;

    // Helper: get date object for a day offset from Monday (0=Mon..6=Sun)
    const getDayDate = (dayOffset) => {
        const d = new Date(today);
        d.setDate(todayDate - daysFromMonday + dayOffset);
        return d;
    };

    const activeHabits = habits.filter(h => h.active !== false);

    // Build 7 columns: Mon..Sun, each with habit dots
    const cols = [];
    for (let i = 0; i < 7; i++) {
        const dayIdx = (i + 1) % 7; // Mon=1..Sun=0
        const date = getDayDate(i);
        const dateNum = date.getDate();
        const isToday = dateNum === todayDate && date.getMonth() === today.getMonth();
        const isFuture = date > today;

        // Build dots for each habit on this day
        const dots = [];
        for (let hi = 0; hi < activeHabits.length; hi++) {
            const h = activeHabits[hi];
            if (isFuture) {
                dots.push('empty');
            } else if (isToday && habitWeekView === 'this') {
                // For today in this-week view, use todayDone/todaySkipped
                // which is the actual live state, rather than weekDone array
                // which may contain stale data from a previous week
                if (h.todayDone) dots.push('done');
                else if (h.todaySkipped) dots.push('skipped');
                else dots.push('missed');
            } else {
                const weekData = habitWeekView === 'this' ? h : (AppData.lastWeekHabits || []).find(lw => lw.id === h.id);
                const doneArr = weekData ? (weekData.weekDone || []) : [];
                const skipArr = habitWeekView === 'this' ? (h.weekSkipped || []) : (weekData ? (weekData.weekSkipped || []) : []);
                const isDone = doneArr[dayIdx] === 1;
                const isSkipped = skipArr[dayIdx] === 1;
                if (isDone) dots.push('done');
                else if (isSkipped) dots.push('skipped');
                else dots.push('missed');
            }
        }

        cols.push({ dayIdx, dateNum, isToday, isFuture, dots, dowLabel: ['一','二','三','四','五','六','日'][i] });
    }

    return `
        <div class="habit-week-overview">
            <div class="habit-week-overview__header">
                <span class="habit-week-overview__title">本周概览</span>
                <div class="habit-week-overview__tabs">
                    <button class="habit-week-tab ${habitWeekView === 'last' ? 'habit-week-tab--active' : ''}"
                            onclick="habitWeekView='last';renderHabits()">上周</button>
                    <button class="habit-week-tab ${habitWeekView === 'this' ? 'habit-week-tab--active' : ''}"
                            onclick="habitWeekView='this';renderHabits()">本周</button>
                </div>
            </div>
            <div class="habit-week-overview__cols">
                ${cols.map(col => `
                    <div class="habit-week-col ${col.isToday ? 'habit-week-col--today' : ''}">
                        <div class="habit-week-col__day">${col.dowLabel}</div>
                        <div class="habit-week-col__date ${col.isToday ? 'habit-week-col__date--today' : ''}">${col.dateNum}</div>
                        <div class="habit-week-col__dots">
                            ${col.dots.map(d => {
                                if (d === 'done') return '<span class="habit-week-dot habit-week-dot--done"></span>';
                                if (d === 'skipped') return '<span class="habit-week-dot habit-week-dot--skipped"></span>';
                                if (d === 'missed') return '<span class="habit-week-dot habit-week-dot--missed"></span>';
                                return '<span class="habit-week-dot habit-week-dot--empty"></span>';
                            }).join('')}
                        </div>
                    </div>
                `).join('')}
            </div>
        </div>
    `;
}

/* ================================================================
   Module 3: Habit Cards Grid (2 columns)
   ================================================================ */
function renderModule3_HabitGrid() {
    let filtered = habits.filter(h => h.active !== false);
    if (habitFilterCategory !== 'all') {
        filtered = filtered.filter(h => h.category === habitFilterCategory);
    }

    // Sort
    switch (habitSortBy) {
        case 'streak-desc':
            filtered.sort((a, b) => b.streak - a.streak);
            break;
        case 'streak-asc':
            filtered.sort((a, b) => a.streak - b.streak);
            break;
        case 'done-first':
            filtered.sort((a, b) => (b.todayDone ? 1 : 0) - (a.todayDone ? 1 : 0));
            break;
        case 'pending-first':
            filtered.sort((a, b) => (a.todayDone ? 1 : 0) - (b.todayDone ? 1 : 0));
            break;
    }

    const categories = AppData.categories;

    return `
        <div class="habit-grid-section">
            <div class="habit-grid-section__header">
                <span class="habit-grid-section__title">已有习惯</span>
                <div class="habit-grid-section__actions">
                    <select class="ac-mini-select" onchange="habitFilterCategory=this.value;renderHabits()">
                        <option value="all" ${habitFilterCategory === 'all' ? 'selected' : ''}>全部维度</option>
                        ${categories.map(c => `
                            <option value="${c.id}" ${habitFilterCategory === c.id ? 'selected' : ''}>${c.name}</option>
                        `).join('')}
                    </select>
                    <select class="ac-mini-select" onchange="habitSortBy=this.value;renderHabits()">
                        <option value="default" ${habitSortBy === 'default' ? 'selected' : ''}>默认排序</option>
                        <option value="streak-desc" ${habitSortBy === 'streak-desc' ? 'selected' : ''}>连续天数 ↓</option>
                        <option value="streak-asc" ${habitSortBy === 'streak-asc' ? 'selected' : ''}>连续天数 ↑</option>
                        <option value="done-first" ${habitSortBy === 'done-first' ? 'selected' : ''}>已完成优先</option>
                        <option value="pending-first" ${habitSortBy === 'pending-first' ? 'selected' : ''}>待完成优先</option>
                    </select>
                    ${habitDeleteMode ? `
                        <button class="goal-delete-mode-btn habit-delete-active" onclick="confirmDeleteHabits()">确认删除（${habitSelectedForDelete.size}）</button>
                        <button class="btn btn--ghost" onclick="toggleHabitDeleteMode()" style="font-size:12px;padding:4px 10px">取消</button>
                    ` : `
                        <button class="btn btn--ghost habit-delete-entry" onclick="toggleHabitDeleteMode()" style="color:#f26b68;font-size:12px;padding:4px 10px">🗑 删除习惯</button>
                    `}
                </div>
            </div>

            ${filtered.length === 0 ? `
                <div class="empty-state">
                    <div style="font-size:48px;margin-bottom:12px">🔄</div>
                    <div class="empty-state__title">还没有习惯</div>
                    <div class="empty-state__desc">创建一个你想要坚持的好习惯吧！</div>
                </div>
            ` : `
                <div class="habit-cards-grid">
                    ${filtered.map(h => renderHabitCard(h)).join('')}
                </div>
            `}
        </div>
    `;
}

function renderHabitCard(habit) {
    const cat = getCategory(habit.category);
    const catColor = cat ? cat.color : '#6b7280';
    const status = habit.todayDone ? 'done' : (habit.todaySkipped ? 'skipped' : 'pending');
    const borderColor = status === 'done' ? '#22c55e' : (status === 'skipped' ? '#f59e0b' : '#3f3f46');

    // Week blocks — only show status for days <= today
    const today = new Date();
    const todayDow = today.getDay();
    const todayDate = today.getDate();
    const daysFromMonday = todayDow === 0 ? 6 : todayDow - 1;
    const getDayDate = (dayOffset) => {
        const d = new Date(today);
        d.setDate(todayDate - daysFromMonday + dayOffset);
        return d;
    };
    const weekBlocks = [];
    for (let i = 0; i < 7; i++) {
        const d = (i + 1) % 7; // Reorder to Mon..Sun
        const date = getDayDate(i);
        const isToday = d === todayDow && date.getDate() === todayDate && date.getMonth() === today.getMonth();
        const isFuture = date > today;

        let cls, text;
        if (isFuture) {
            cls = 'habit-card-v2__wblock--future';
            text = '';
        } else if (isToday) {
            // For today, use todayDone/todaySkipped as the live source of truth
            if (habit.todayDone) { cls = 'habit-card-v2__wblock--done'; text = '✓'; }
            else if (habit.todaySkipped) { cls = 'habit-card-v2__wblock--skipped'; text = '→'; }
            else { cls = 'habit-card-v2__wblock--missed'; text = '✗'; }
        } else {
            const isDone = habit.weekDone[d] === 1;
            const isSkipped = (habit.weekSkipped || [])[d] === 1;
            if (isDone) { cls = 'habit-card-v2__wblock--done'; text = '✓'; }
            else if (isSkipped) { cls = 'habit-card-v2__wblock--skipped'; text = '→'; }
            else { cls = 'habit-card-v2__wblock--missed'; text = '✗'; }
        }
        weekBlocks.push({ cls, text, dayIdx: d });
    }

    // Progress
    const weekCompleted = habit.weekDone.reduce((a, b) => a + b, 0);
    const target = habit.weeklyTarget || 7;
    const pct = Math.min(Math.round((weekCompleted / target) * 100), 100);

    // Today day label
    const todayLabel = DAY_LABELS[todayDow];

    const isSelected = habitSelectedForDelete.has(habit.id);

    return `
        <div class="habit-card-v2 habit-card-v2--${status}" style="border-left:3px solid ${borderColor}">
            <!-- Top row: delete checkbox or status checkbox + name + streak + actions -->
            <div class="habit-card-v2__top">
                ${habitDeleteMode ? `
                    <div class="habit-card-v2__checkbox habit-card-v2__checkbox--del ${isSelected ? 'habit-card-v2__checkbox--del-active' : ''}"
                         onclick="toggleHabitSelect(${habit.id})">
                        ${isSelected ? '✓' : ''}
                    </div>
                ` : `
                    <div class="habit-card-v2__checkbox ${status === 'done' ? 'habit-card-v2__checkbox--done' : (status === 'skipped' ? 'habit-card-v2__checkbox--skipped' : '')}"
                         onclick="cycleHabitStatus(${habit.id})">
                        ${status === 'done' ? '✓' : (status === 'skipped' ? '→' : '')}
                    </div>
                `}
                <div class="habit-card-v2__info">
                    <span class="habit-card-v2__name">${habit.icon} ${habit.name}</span>
                    <span class="habit-card-v2__streak">🔥 ${habit.streak} 天连续</span>
                </div>
                ${habitDeleteMode ? '' : `
                    <div class="habit-card-v2__actions">
                        <button class="habit-card-v2__action-btn" onclick="editHabit(${habit.id})" title="编辑">✎</button>
                        <button class="habit-card-v2__action-btn habit-card-v2__action-btn--del" onclick="deleteHabit(${habit.id})" title="删除">✕</button>
                    </div>
                `}
            </div>

            <!-- Week blocks -->
            <div class="habit-card-v2__week-blocks">
                ${weekBlocks.map((wb, i) => `
                    <div class="habit-card-v2__wblock ${wb.cls}" title="${DAY_LABELS[wb.dayIdx]}">${wb.text}</div>
                `).join('')}
            </div>

            <!-- Habit intro -->
            ${habit.intro ? `
                <div class="habit-card-v2__intro" title="${escapeHtml(habit.intro)}">${escapeHtml(habit.intro)}</div>
            ` : ''}

            <!-- Progress bar -->
            <div class="habit-card-v2__progress">
                <div class="habit-card-v2__progress-bar" style="width:${pct}%;background:${status === 'skipped' ? '#f59e0b' : '#22c55e'}"></div>
            </div>

            <!-- Bottom row -->
            <div class="habit-card-v2__bottom">
                <span class="habit-card-v2__dim" style="color:${catColor}">${cat ? cat.name : ''}</span>
                <span class="habit-card-v2__week-stat">本周 ${weekCompleted}/${target}</span>
                ${status === 'done' ? `
                    <span class="habit-card-v2__xp">+${habit.xpReward || 15} XP</span>
                ` : ''}
                ${status === 'skipped' ? `
                    <span class="habit-card-v2__skipped-label">已跳过</span>
                ` : ''}
            </div>
        </div>
    `;
}

function cycleHabitStatus(id) {
    var habit = habits.find(function(h) { return h.id === id; });
    if (!habit) return;

    // 先调后端 API
    var user = getCurrentUser();
    if (user) {
        toggleHabitOnBackend(id).then(function(result) {
            if (result) {
                // 用后端返回的状态和 streak 更新本地
                var todayDow = new Date().getDay();
                if (result.status === 'done') {
                    habit.todayDone = true;
                    habit.todaySkipped = false;
                    habit.weekDone[todayDow] = 1;
                    habit.weekSkipped[todayDow] = 0;
                    AppData.todayStats.habitsChecked++;
                    showToast(habit.icon + ' ' + habit.name + ' 打卡成功！', 'success');
                } else if (result.status === 'skipped') {
                    habit.todayDone = false;
                    habit.todaySkipped = true;
                    habit.weekDone[todayDow] = 0;
                    habit.weekSkipped[todayDow] = 1;
                    AppData.todayStats.habitsChecked = Math.max(0, AppData.todayStats.habitsChecked - 1);
                    showToast(habit.icon + ' ' + habit.name + ' 已跳过', 'info');
                } else {
                    // pending
                    habit.todayDone = false;
                    habit.todaySkipped = false;
                    habit.weekDone[todayDow] = 0;
                    habit.weekSkipped[todayDow] = 0;
                    showToast(habit.icon + ' ' + habit.name + ' 恢复待打卡', 'info');
                }
                habit.streak = result.streak;

                // 同步统计到后端
                if (user) {
                    syncTodayStats(user.id, {
                        focus_minutes: AppData.todayStats.focusMinutes,
                        tasks_done: AppData.todayStats.tasksDone,
                        habits_checked: AppData.todayStats.habitsChecked,
                        exp_earned: AppData.todayStats.expEarned,
                    });
                }

                renderHabits();

                // 重新评估奖励解锁状态
                var curUserId = AppData.user?.id;
                if (curUserId) reevaluateRewardsOnBackend(curUserId);
            } else {
                // 后端失败，用本地状态（兼容旧逻辑）
                fallbackCycleHabitStatus(habit, user);
            }
        });
    } else {
        fallbackCycleHabitStatus(habit, null);
    }
}

/** 后端不可用时的降级打卡逻辑 */
function fallbackCycleHabitStatus(habit, user) {
    var todayDow = new Date().getDay();

    if (habit.todayDone) {
        habit.todayDone = false;
        habit.todaySkipped = true;
        habit.weekDone[todayDow] = 0;
        habit.weekSkipped[todayDow] = 1;
        habit.streak = Math.max(0, habit.streak - 1);
        AppData.todayStats.habitsChecked = Math.max(0, AppData.todayStats.habitsChecked - 1);
        showToast(habit.icon + ' ' + habit.name + ' 已跳过', 'info');
    } else if (habit.todaySkipped) {
        habit.todaySkipped = false;
        habit.weekSkipped[todayDow] = 0;
        showToast(habit.icon + ' ' + habit.name + ' 恢复待打卡', 'info');
    } else {
        habit.todayDone = true;
        habit.todaySkipped = false;
        habit.streak++;
        habit.weekDone[todayDow] = 1;
        habit.weekSkipped[todayDow] = 0;
        AppData.todayStats.habitsChecked++;
        showToast(habit.icon + ' ' + habit.name + ' 打卡成功！', 'success');
    }

    if (user) {
        syncTodayStats(user.id, {
            focus_minutes: AppData.todayStats.focusMinutes,
            tasks_done: AppData.todayStats.tasksDone,
            habits_checked: AppData.todayStats.habitsChecked,
            exp_earned: AppData.todayStats.expEarned,
        });
    }

    renderHabits();
}

/* ================================================================
   Module 4: Streak Ranking
   ================================================================ */
function renderModule4_StreakRanking() {
    const activeHabits = habits.filter(h => h.active !== false && h.streak > 0);
    activeHabits.sort((a, b) => b.streak - a.streak);
    const top4 = activeHabits.slice(0, 4);

    // Dim color mapping
    const dimBgColors = {
        health: '#3f1823', study: '#1a3d34', relation: '#3f1828',
        work: '#3d2e10', create: '#2d1f3d', finance: '#143820',
        hobby: '#3d1a30', soul: '#3d240e',
    };

    return `
        <div class="habit-panel">
            <div class="habit-panel__title">🔥 连续排行</div>
            <div class="habit-panel__body">
                ${top4.length === 0 ? `
                    <div class="habit-panel__empty">暂无连续记录</div>
                ` : top4.map((h, i) => {
                    const cat = getCategory(h.category);
                    const bgColor = dimBgColors[h.category] || '#272a34';
                    const rankBadge = ['#fbbf24','#9ca3af','#b45309','#6b7280'][i];
                    return `
                        <div class="habit-rank-item">
                            <div class="habit-rank-item__icon" style="background:${bgColor};color:${cat ? cat.color : '#9ca3af'}">
                                ${h.icon}
                            </div>
                            <span class="habit-rank-item__name">${h.name}</span>
                            <div class="habit-rank-item__right">
                                <span class="habit-rank-item__streak">${h.streak} 天</span>
                                <span class="habit-rank-item__badge" style="color:${rankBadge}">#${i + 1}</span>
                            </div>
                        </div>
                    `;
                }).join('')}
            </div>
        </div>
    `;
}

/* ================================================================
   Module 5: Smart Insights — 数据从后端 API 获取
   ================================================================ */
function renderModule5_Insights() {
    // 优先用后端洞察，降级到本地
    var insights = [];

    if (habitInsights && habitInsights.insights) {
        insights = habitInsights.insights.map(function(i) { return i.text; });
    } else {
        // 降级：本地简单计算
        var activeHabits = habits.filter(function(h) { return h.active !== false; });
        var pending = activeHabits.filter(function(h) { return !h.todayDone && !h.todaySkipped; });
        if (pending.length > 0) {
            insights.push('今日还剩 ' + pending.length + ' 个习惯未完成——「' + pending[0].name + '」，现在开始还不晚');
        }
    }

    return `
        <div class="habit-panel">
            <div class="habit-panel__title">
                <span>💡 智能洞察</span>
                <button class="habit-insight-btn" onclick="showToast('AI 智能洞察功能完善中，敬请期待！', 'info')" title="AI 智能分析">✨ AI 分析</button>
            </div>
            <div class="habit-panel__body">
                ${insights.length === 0 ? `
                    <div class="habit-panel__empty">暂无洞察数据</div>
                ` : insights.map(text => `
                    <div class="habit-insight-item">
                        <span class="habit-insight-item__dot">●</span>
                        <span class="habit-insight-item__text">${text}</span>
                    </div>
                `).join('')}
            </div>
        </div>
    `;
}

/* ================================================================
   Habit Modal — 新建/编辑习惯
   ================================================================ */
function openHabitModal(editId) {
    const existing = editId ? habits.find(h => h.id === editId) : null;
    const cats = AppData.categories;

    const content = `
        <div style="display:flex;flex-direction:column;gap:16px">
            <div>
                <label class="action-form__label">习惯名称</label>
                <input class="input" id="habit-name" placeholder="例如：早起 (7:00前)" value="${existing ? existing.name : ''}">
            </div>
            <div>
                <label class="action-form__label">习惯介绍</label>
                <textarea class="input" id="habit-intro" placeholder="简单描述这个习惯，例如：每天早上7点前起床，开启高效的一天" maxlength="200" style="height:60px;resize:none">${existing && existing.intro ? existing.intro : ''}</textarea>
            </div>
            <div>
                <label class="action-form__label">图标</label>
                <div style="display:flex;gap:8px">
                    <input class="input" id="habit-icon" placeholder="例如：🌅 或留空" maxlength="4" value="${existing && existing.icon !== '✅' ? existing.icon : ''}" style="flex:1">
                    <button class="btn btn--accent" onclick="showToast('AI图标生成功能即将上线，请手动输入emoji或留空', 'info')" type="button" style="white-space:nowrap;padding:0 14px">🤖 AI设计</button>
                </div>
            </div>
            <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px">
                <div>
                    <label class="action-form__label">维度分类</label>
                    <select class="select" id="habit-category" style="width:100%">
                        ${cats.map(c => `<option value="${c.id}" ${existing && existing.category === c.id ? 'selected' : ''}>${c.name}</option>`).join('')}
                    </select>
                </div>
                <div>
                    <label class="action-form__label">每周目标（次）</label>
                    <input class="input" type="number" id="habit-target" value="${existing ? (existing.weeklyTarget || 7) : 7}" min="1" max="14">
                </div>
                <div>
                    <label class="action-form__label">经验值奖励</label>
                    <input class="input" type="number" id="habit-xp" value="${existing ? (existing.xpReward || 15) : 15}" min="5" max="100" step="5">
                </div>
            </div>
        </div>
        <div class="modal__actions">
            <button class="btn btn--ghost" onclick="cancelHabitModal()">取消</button>
            <button class="btn btn--primary" onclick="saveHabit(${editId || 0})">${editId ? '保存' : '创建'}</button>
        </div>
    `;
    habitModalActive = true;
    openModal(existing ? '编辑习惯' : '新建习惯', content);
}

function cancelHabitModal() {
    habitModalActive = false;
    closeModal();
}

function saveHabit(editId) {
    var name = document.getElementById('habit-name').value.trim();
    var icon = document.getElementById('habit-icon').value.trim() || '';
    var intro = document.getElementById('habit-intro').value.trim();
    var category = document.getElementById('habit-category').value;
    var weeklyTarget = parseInt(document.getElementById('habit-target').value) || 7;
    var xpReward = parseInt(document.getElementById('habit-xp').value) || 15;

    if (!name) {
        showToast('请输入习惯名称', 'error');
        return;
    }

    var user = getCurrentUser();
    if (!user) {
        showToast('请先登录', 'error');
        return;
    }

    if (editId) {
        // 编辑 — 调后端 API
        updateHabitOnBackend(editId, {
            name: name,
            icon: icon,
            intro: intro,
            category: category,
            weekly_target: weeklyTarget,
            xp_reward: xpReward,
        }).then(function() {
            // 成功后重新加载习惯数据
            fetchHabits(user.id).then(function(data) {
                if (data) {
                    AppData.habits = data;
                    refreshHabitsData();
                }
                habitModalActive = false;
                closeModal();
                renderHabits();
                showToast('习惯已更新', 'success');
            });
        });
    } else {
        // 新建 — 调后端 API
        createHabitOnBackend(user.id, {
            name: name,
            icon: icon,
            intro: intro,
            category: category,
            weekly_target: weeklyTarget,
            xp_reward: xpReward,
        }).then(function(newHabit) {
            if (newHabit) {
                // 追加到 AppData
                AppData.habits = AppData.habits.concat([newHabit]);
                refreshHabitsData();
            }
            habitModalActive = false;
            closeModal();
            renderHabits();
            showToast('习惯已创建！', 'success');
        });
    }
}

function toggleHabitDeleteMode() {
    habitDeleteMode = !habitDeleteMode;
    habitSelectedForDelete = new Set();
    renderHabits();
}

function toggleHabitSelect(id) {
    if (habitSelectedForDelete.has(id)) {
        habitSelectedForDelete.delete(id);
    } else {
        habitSelectedForDelete.add(id);
    }
    renderHabits();
}

function confirmDeleteHabits() {
    if (habitSelectedForDelete.size === 0) {
        showToast('请先选择要删除的习惯', 'info');
        return;
    }
    var count = habitSelectedForDelete.size;
    var ids = Array.from(habitSelectedForDelete);
    if (confirm('确定要删除选中的 ' + count + ' 个习惯吗？此操作不可撤销。')) {
        var user = getCurrentUser();
        if (user) {
            deleteHabitsOnBackend(user.id, ids).then(function() {
                AppData.habits = AppData.habits.filter(function(h) { return ids.indexOf(h.id) === -1; });
                refreshHabitsData();
                habitDeleteMode = false;
                habitSelectedForDelete = new Set();
                renderHabits();
                showToast('已删除 ' + count + ' 个习惯', 'info');
            });
        } else {
            habitDeleteMode = false;
            habitSelectedForDelete = new Set();
            renderHabits();
        }
    }
}

function editHabit(id) {
    openHabitModal(id);
}

function deleteHabit(id) {
    if (confirm('确定要删除这个习惯吗？')) {
        var user = getCurrentUser();
        if (user) {
            deleteHabitsOnBackend(user.id, [id]).then(function() {
                AppData.habits = AppData.habits.filter(function(h) { return h.id !== id; });
                refreshHabitsData();
                renderHabits();
                showToast('习惯已删除', 'info');
            });
        } else {
            renderHabits();
        }
    }
}
