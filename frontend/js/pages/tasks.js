/* ================================================================
   Tasks Page — 任务（本日任务 + 本周任务 + 历史任务）
   ================================================================ */

var tasks = {
    todo: [],
    doing: [],
    done: [],
};
var tasksLoaded = false;
let taskFilterCategory = 'all';
let taskDeleteMode = false;
let taskModalActive = false;
// 同步到 window 供 utils.js 的 closeModalIfNotActive 使用
Object.defineProperty(window, '_taskModalActive', { get: () => taskModalActive });

/** Category → color mapping (same as GOAL_COLORS) */
const TASK_COLORS = {
    health:   '#FF7B72',
    study:    '#46C9C0',
    relation: '#FF91A8',
    work:     '#FFCA40',
    create:   '#B794F6',
    finance:  '#4ADE80',
    hobby:    '#F472B6',
    soul:     '#FBBF24',
};

/* ---- Main entry ---- */
function renderTasks(subPage) {
    const tab = subPage || 'today';
    if (tab === 'week') {
        renderWeekTasks();
    } else if (tab === 'history') {
        renderHistoryTasks();
    } else {
        renderTodayTasks();
    }
}

/* ================================================================
   刷新机制 — 已由后端定时任务（每日 03:00）替代
   保留函数作为降级备用
   ================================================================ */

function checkTodayRefresh() {
    // 已由后端定时任务替代
}
function checkWeekRefresh() {
    // 已由后端定时任务替代
}
function initTaskRefresh() {
    // 已由后端定时任务替代
}
function settleHabitExp() {
    // 已由后端定时任务替代
}

/* ================================================================
   本日任务 — 左右两栏：待办 | 已完成
   ================================================================ */
function renderTodayTasks() {
    // 从后端加载
    if (!tasksLoaded) {
        loadTodayTasksFromBackend();
        document.getElementById('page-tasks').innerHTML = '<div style="text-align:center;padding:60px;color:var(--color-text-secondary)">加载中...</div>';
        return;
    }

    const allToday = [...tasks.todo, ...tasks.doing, ...tasks.done];
    const filtered = taskFilterCategory === 'all'
        ? allToday
        : allToday.filter(t => t.category === taskFilterCategory);

    const todoItems = filtered.filter(t => tasks.todo.some(x => x.id === t.id) || tasks.doing.some(x => x.id === t.id));
    const doneItems = filtered.filter(t => tasks.done.some(x => x.id === t.id));

    const html = `
        <div class="page-header page-header--with-icon">
            <div class="page-header__icon" style="width:58px;height:58px">${HEADER_ICONS.todayTasks}</div>
            <div style="flex:1;display:flex;justify-content:space-between;align-items:flex-start">
                <div>
                    <h1 class="page-header__title">本日任务</h1>
                    <p class="page-header__subtitle">专注今天，一件一件完成</p>
                </div>
                <button class="goal-create-btn" onclick="openTaskModal()">+ 新建任务</button>
            </div>
        </div>

        <!-- Toolbar -->
        <div class="goal-toolbar">
            <div class="goal-toolbar__left">
                <span class="goal-toolbar__label">筛选</span>
                <select class="goal-filter-select" onchange="taskFilterCategory=this.value;renderTodayTasks()">
                    <option value="all" ${taskFilterCategory === 'all' ? 'selected' : ''}>全部属性</option>
                    ${AppData.categories.map(c => `
                        <option value="${c.id}" ${taskFilterCategory === c.id ? 'selected' : ''}>${c.name}</option>
                    `).join('')}
                </select>
                <span class="goal-toolbar__count">${filtered.length} 个任务</span>
            </div>
            <button class="goal-delete-mode-btn ${taskDeleteMode ? 'goal-delete-mode-btn--active' : ''}"
                    onclick="taskDeleteMode=!taskDeleteMode;renderTodayTasks()">
                ${taskDeleteMode ? '完成删除' : '删除任务'}
            </button>
        </div>

        <!-- Two-column layout -->
        <div class="task-today-grid">
            <!-- Left: Todo -->
            <div class="task-today-col">
                <div class="task-today-col__head">
                    <span>📋 待办</span>
                    <span class="task-today-col__count">${todoItems.length}</span>
                </div>
                <div class="task-today-list">
                    ${todoItems.map(t => renderTodayTaskCard(t, false)).join('')}
                    ${todoItems.length === 0 ? `<div class="task-today-empty">暂无待办任务</div>` : ''}
                </div>
            </div>
            <!-- Right: Done -->
            <div class="task-today-col">
                <div class="task-today-col__head task-today-col__head--done">
                    <span>✅ 已完成</span>
                    <span class="task-today-col__count">${doneItems.length}</span>
                </div>
                <div class="task-today-list">
                    ${doneItems.map(t => renderTodayTaskCard(t, true)).join('')}
                    ${doneItems.length === 0 ? `<div class="task-today-empty">暂无已完成任务</div>` : ''}
                </div>
            </div>
        </div>

        <!-- Scheduled task templates -->
        ${renderScheduledTemplates()}
    `;

    document.getElementById('page-tasks').innerHTML = html;
}

/** 从后端加载今日任务 */
async function loadTodayTasksFromBackend() {
    var curUser = getCurrentUser();
    if (!curUser) {
        tasks = { todo: [...AppData.tasks.todo], doing: [...AppData.tasks.doing], done: [...AppData.tasks.done] };
        tasksLoaded = true;
        renderTodayTasks();
        return;
    }
    const result = await fetchTodayTasks(curUser.id);
    if (result && result.todo !== undefined) {
        tasks = result;
    } else {
        tasks = { todo: [...AppData.tasks.todo], doing: [...AppData.tasks.doing], done: [...AppData.tasks.done] };
    }
    tasksLoaded = true;
    renderTodayTasks();
}

/** 从后端加载本周任务 */
async function loadWeekTasksFromBackend() {
    var curUser = getCurrentUser();
    if (!curUser) {
        tasks = { todo: [...AppData.tasks.todo], doing: [...AppData.tasks.doing], done: [...AppData.tasks.done] };
        tasksLoaded = true;
        renderWeekTasks();
        return;
    }
    const result = await fetchTodayTasks(curUser.id);
    if (result && result.todo !== undefined) {
        tasks = result;
    } else {
        tasks = { todo: [...AppData.tasks.todo], doing: [...AppData.tasks.doing], done: [...AppData.tasks.done] };
    }
    tasksLoaded = true;
    renderWeekTasks();
}

function renderTodayTaskCard(task, isDone) {
    const cat = getCategory(task.category);
    const iconColor = TASK_COLORS[task.category] || '#46C9C0';
    const priorityBadge = task.priority === 'high' ? 'danger' : task.priority === 'mid' ? 'accent' : 'info';
    const priorityText = task.priority === 'high' ? '高' : task.priority === 'mid' ? '中' : '低';

    return `
        <div class="task-today-card ${isDone ? 'task-today-card--done' : ''}">
            <div class="task-today-card__main">
                <span class="task-today-card__icon" style="color:${iconColor}">
                    ${cat ? attrIcon(cat.id, 18) : ''}
                </span>
                <div class="task-today-card__info">
                    <span class="task-today-card__title">${task.title}</span>
                    <div class="task-today-card__meta">
                        ${cat ? `<span>${cat.name}</span>` : ''}
                        <span class="badge badge--${priorityBadge}">${priorityText}优先</span>
                        <span style="color:var(--color-accent-light);font-weight:600">+${task.exp} EXP</span>
                    </div>
                    ${task.intro ? renderTaskIntro(task.id, task.intro) : ''}
                </div>
            </div>
            <div class="task-today-card__actions">
                ${!isDone ? `
                    <button class="task-today-card__btn task-today-card__btn--done"
                            onclick="moveTaskToDone(${task.id})">完成</button>
                ` : !task.claimed ? `
                    <button class="task-today-card__btn task-today-card__btn--claim"
                            onclick="claimTaskExp(${task.id})">🎁 领取 ${task.exp} EXP</button>
                ` : `
                    <span class="task-today-card__claimed">✅ 已领取</span>
                `}
                ${taskDeleteMode ? `
                    <button class="task-today-card__btn task-today-card__btn--del"
                            onclick="removeTodayTask(${task.id})">删除</button>
                ` : ''}
            </div>
        </div>
    `;
}

/* ---- Task intro expand/collapse ---- */
const taskIntroDebounce = {};

function renderTaskIntro(taskId, intro) {
    if (!intro) return '';
    const id = `task-intro-${taskId}`;
    return `
        <div class="task-intro" id="${id}">
            <span class="task-intro__line">${escapeHtml(intro)}</span>
            <span class="task-intro__toggle" onclick="toggleTaskIntro(${taskId}, '${id}')">展开 ▼</span>
        </div>
    `;
}

function toggleTaskIntro(taskId, containerId) {
    // 100ms 防抖
    if (taskIntroDebounce[taskId]) return;
    taskIntroDebounce[taskId] = true;
    setTimeout(() => { taskIntroDebounce[taskId] = false; }, 100);

    const el = document.getElementById(containerId);
    if (!el) return;

    const line = el.querySelector('.task-intro__line');
    const toggle = el.querySelector('.task-intro__toggle');

    if (el.classList.contains('task-intro--expanded')) {
        // 收起
        el.classList.remove('task-intro--expanded');
        toggle.textContent = '展开 ▼';
    } else {
        // 展开
        el.classList.add('task-intro--expanded');
        toggle.textContent = '收起 ▲';
    }
}

/* ---- Task operations (today) ---- */

function moveTaskToDone(id) {
    let fromCol = null;
    if (tasks.todo.find(t => t.id === id)) fromCol = 'todo';
    else if (tasks.doing.find(t => t.id === id)) fromCol = 'doing';
    if (!fromCol) return;

    const idx = tasks[fromCol].findIndex(t => t.id === id);
    if (idx >= 0) {
        const [task] = tasks[fromCol].splice(idx, 1);
        task.claimed = false;
        task.completedAt = formatDate(new Date());
        task.status = 'done';
        tasks.done.push(task);

        // 同步到后端
        var curUser = getCurrentUser();
        if (curUser) {
            patchTaskStatusOnBackend(id, 'done');
        }
    }
    renderTodayTasks();
}

function claimTaskExp(id) {
    const task = tasks.done.find(t => t.id === id);
    if (!task || task.claimed) return;

    var curUser = getCurrentUser();
    if (curUser) {
        claimTaskOnBackend(curUser.id, id).then(result => {
            if (result) {
                task.claimed = true;
                AppData.user.exp = result.exp_result.exp;
                AppData.user.level = result.exp_result.level;
                AppData.todayStats.expEarned = result.today_stats.expEarned;
                AppData.todayStats.tasksDone = result.today_stats.tasksDone;
                renderTodayTasks();
                showToast(`任务完成！+${result.exp_earned} EXP`, 'success');
                if (result.exp_result.leveledUp) {
                    setTimeout(() => {
                        showToast(`🎉 升级！Lv.${result.exp_result.oldLevel} → Lv.${result.exp_result.level}`, 'success');
                    }, 500);
                }
                // 重新评估奖励
                if (curUser) reevaluateRewardsOnBackend(curUser.id);
            } else {
                localClaimTaskExp(task);
            }
        }).catch(() => localClaimTaskExp(task));
    } else {
        localClaimTaskExp(task);
    }
}

function localClaimTaskExp(task) {
    task.claimed = true;
    AppData.user.exp += task.exp;
    AppData.todayStats.tasksDone++;
    AppData.todayStats.expEarned += task.exp;
    // 重新计算等级
    const oldLevel = AppData.user.level;
    AppData.user.level = levelFromTotalExp(AppData.user.exp);
    if (AppData.user.level > oldLevel) {
        setTimeout(() => showToast(`🎉 升级！Lv.${oldLevel} → Lv.${AppData.user.level}`, 'success'), 500);
    }
    renderTodayTasks();
    showToast(`任务完成！+${task.exp} EXP`, 'success');
}

function removeTodayTask(id) {
    ['todo', 'doing', 'done'].forEach(col => {
        tasks[col] = tasks[col].filter(t => t.id !== id);
    });
    if (tasks.todo.length === 0 && tasks.doing.length === 0 && tasks.done.length === 0) {
        taskDeleteMode = false;
    }

    var curUser = getCurrentUser();
    if (curUser) {
        deleteTaskOnBackend(id);
    }

    renderTodayTasks();
    showToast('任务已删除', 'info');
}

/* ================================================================
   本周任务 — 三栏 Kanban（保留原有结构）
   ================================================================ */
function renderWeekTasks() {
    // 从后端加载
    if (!tasksLoaded) {
        loadWeekTasksFromBackend();
        document.getElementById('page-tasks').innerHTML = '<div style="text-align:center;padding:60px;color:var(--color-text-secondary)">加载中...</div>';
        return;
    }

    checkWeekRefresh();

    const columns = [
        { key: 'todo',  title: '📋 待办', color: 'var(--color-text-muted)' },
        { key: 'doing', title: '🔄 进行中', color: 'var(--color-accent-light)' },
        { key: 'done',  title: '✅ 已完成', color: 'var(--color-primary-light)' },
    ];

    const html = `
        <div class="page-header page-header--with-icon">
            <div class="page-header__icon" style="width:58px;height:58px">${HEADER_ICONS.weekTasks}</div>
            <div style="flex:1;display:flex;justify-content:space-between;align-items:flex-start">
                <div>
                    <h1 class="page-header__title">本周任务</h1>
                    <p class="page-header__subtitle">看板管理，追踪本周所有任务进度</p>
                </div>
                <button class="goal-create-btn" onclick="openTaskModal()">+ 新建任务</button>
            </div>
        </div>

        <!-- Toolbar -->
        <div class="goal-toolbar">
            <div class="goal-toolbar__left">
                <span class="goal-toolbar__label">筛选</span>
                <select class="goal-filter-select" onchange="taskFilterCategory=this.value;renderWeekTasks()">
                    <option value="all" ${taskFilterCategory === 'all' ? 'selected' : ''}>全部属性</option>
                    ${AppData.categories.map(c => `
                        <option value="${c.id}" ${taskFilterCategory === c.id ? 'selected' : ''}>${c.name}</option>
                    `).join('')}
                </select>
            </div>
            <button class="goal-delete-mode-btn ${taskDeleteMode ? 'goal-delete-mode-btn--active' : ''}"
                    onclick="taskDeleteMode=!taskDeleteMode;renderWeekTasks()">
                ${taskDeleteMode ? '完成删除' : '删除任务'}
            </button>
        </div>

        <div class="kanban-board">
            ${columns.map(col => {
                const colTasks = tasks[col.key].filter(t =>
                    taskFilterCategory === 'all' || t.category === taskFilterCategory
                );
                return `
                    <div class="kanban-column">
                        <div class="kanban-column__title">
                            <span>${col.title}</span>
                            <span class="kanban-column__count">${colTasks.length}</span>
                        </div>
                        ${colTasks.map(task => {
                            const cat = getCategory(task.category);
                            const iconColor = TASK_COLORS[task.category] || '#46C9C0';
                            const priorityBadge = task.priority === 'high' ? 'danger' : task.priority === 'mid' ? 'accent' : 'info';
                            const priorityText = task.priority === 'high' ? '高' : task.priority === 'mid' ? '中' : '低';
                            return `
                                <div class="kanban-card" draggable="true"
                                     ondragstart="dragTask(event, ${task.id}, '${col.key}')"
                                     ondragover="event.preventDefault()"
                                     ondrop="dropTask(event, '${col.key}')">
                                    <div class="kanban-card__title">${task.title}</div>
                                    <div class="kanban-card__meta">
                                        ${cat ? `<span style="display:inline-flex;align-items:center;gap:3px;color:${iconColor}">${attrIcon(cat.id, 14)} ${cat.name}</span>` : ''}
                                        <span class="badge badge--${priorityBadge}">${priorityText}优先</span>
                                        <span style="color:var(--color-accent-light);font-weight:600">+${task.exp} EXP</span>
                                    </div>
                                    ${task.intro ? renderKanbanIntro(task.id, task.intro) : ''}
                                    <div style="display:flex;gap:6px;margin-top:8px">
                                        ${col.key === 'todo' ? `
                                            <button class="btn btn--ghost btn--sm" style="font-size:10px;color:var(--color-accent-light)"
                                                    onclick="startTask(${task.id})">▶ 开始任务</button>
                                        ` : ''}
                                        ${col.key === 'doing' ? `
                                            <button class="btn btn--ghost btn--sm" style="font-size:10px;color:var(--color-success)"
                                                    onclick="completeTask(${task.id})">✅ 完成任务</button>
                                        ` : ''}
                                        ${col.key === 'done' && !task.claimed ? `
                                            <button class="btn btn--ghost btn--sm" style="font-size:10px;color:var(--color-accent-light)"
                                                    onclick="claimTaskExp(${task.id});renderWeekTasks()">🎁 领取 ${task.exp} EXP</button>
                                        ` : col.key === 'done' && task.claimed ? `
                                            <span style="font-size:10px;color:var(--color-success)">已领取</span>
                                        ` : ''}
                                        ${taskDeleteMode ? `
                                            <button class="btn btn--ghost btn--sm" style="font-size:10px;color:var(--color-danger);margin-left:auto"
                                                    onclick="removeTodayTask(${task.id});renderWeekTasks()">删除</button>
                                        ` : ''}
                                    </div>
                                </div>
                            `;
                        }).join('')}
                        ${colTasks.length === 0 ? `
                            <div style="text-align:center;padding:20px;color:var(--color-text-muted);font-size:13px">
                                拖放任务到这里
                            </div>
                        ` : ''}
                    </div>
                `;
            }).join('')}
        </div>

        <!-- Weekly task templates -->
        ${renderWeeklyTemplates()}
    `;

    document.getElementById('page-tasks').innerHTML = html;
}

function renderKanbanIntro(taskId, intro) {
    if (!intro) return '';
    const id = `kanban-intro-${taskId}`;
    return `
        <div class="task-intro task-intro--kanban" id="${id}">
            <span class="task-intro__line">${escapeHtml(intro)}</span>
            <span class="task-intro__toggle" onclick="toggleTaskIntro(${taskId}, '${id}')">展开 ▼</span>
        </div>
    `;
}

/* ---- Button-driven task flow (week kanban) ---- */
function startTask(id) {
    const idx = tasks.todo.findIndex(t => t.id === id);
    if (idx >= 0) {
        const [task] = tasks.todo.splice(idx, 1);
        tasks.doing.push(task);
    }
    renderWeekTasks();
}

function completeTask(id) {
    const idx = tasks.doing.findIndex(t => t.id === id);
    if (idx >= 0) {
        const [task] = tasks.doing.splice(idx, 1);
        task.claimed = false;
        task.completedAt = formatDate(new Date());
        tasks.done.push(task);
    }
    renderWeekTasks();
}

// Drag and drop
let dragTaskId = null;
let dragFromCol = null;

function dragTask(event, taskId, col) {
    dragTaskId = taskId;
    dragFromCol = col;
    event.dataTransfer.effectAllowed = 'move';
}

function dropTask(event, toCol) {
    event.preventDefault();
    if (dragTaskId && dragFromCol && dragFromCol !== toCol) {
        const taskIdx = tasks[dragFromCol].findIndex(t => t.id === dragTaskId);
        if (taskIdx >= 0) {
            const [task] = tasks[dragFromCol].splice(taskIdx, 1);
            if (toCol === 'done') {
                task.claimed = false;
                task.completedAt = formatDate(new Date());
            }
            tasks[toCol].push(task);
        }
    }
    dragTaskId = null;
    dragFromCol = null;
    renderWeekTasks();
}

/* ================================================================
   历史任务 — 已完成 & 超期的任务存档
   ================================================================ */
let taskHistoryFilterCategory = 'all';
let taskHistoryFilterStatus = 'all';
let taskHistorySortBy = 'newest';
let taskHistoryPage = 1;
const TASK_HISTORY_PAGE_SIZE = 20;

function renderHistoryTasks() {
    const all = AppData.taskHistory;

    // Filter
    let filtered = all.filter(t => {
        if (taskHistoryFilterCategory !== 'all' && t.category !== taskHistoryFilterCategory) return false;
        if (taskHistoryFilterStatus !== 'all' && t.status !== taskHistoryFilterStatus) return false;
        return true;
    });

    // Sort
    switch (taskHistorySortBy) {
        case 'newest':
            filtered.sort((a, b) => {
                const da = a.completedAt || a.createdAt || '';
                const db = b.completedAt || b.createdAt || '';
                return db.localeCompare(da);
            });
            break;
        case 'oldest':
            filtered.sort((a, b) => {
                const da = a.completedAt || a.createdAt || '';
                const db = b.completedAt || b.createdAt || '';
                return da.localeCompare(db);
            });
            break;
        case 'exp-high':
            filtered.sort((a, b) => b.exp - a.exp);
            break;
        case 'exp-low':
            filtered.sort((a, b) => a.exp - b.exp);
            break;
    }

    // Pagination
    const totalPages = Math.ceil(filtered.length / TASK_HISTORY_PAGE_SIZE) || 1;
    if (taskHistoryPage > totalPages) taskHistoryPage = totalPages;
    const start = (taskHistoryPage - 1) * TASK_HISTORY_PAGE_SIZE;
    const pageItems = filtered.slice(start, start + TASK_HISTORY_PAGE_SIZE);

    // Status counts
    const completedCount = all.filter(t => t.status === 'completed').length;
    const expiredCount = all.filter(t => t.status === 'expired').length;

    const html = `
        <div class="page-header page-header--with-icon">
            <div class="page-header__icon" style="width:58px;height:58px">${HEADER_ICONS.historyTasks}</div>
            <div style="flex:1;display:flex;justify-content:space-between;align-items:flex-start">
                <div>
                    <h1 class="page-header__title">历史任务</h1>
                    <p class="page-header__subtitle">已完成和超期的任务存档</p>
                </div>
                ${all.length > 0 ? `
                    <button class="task-history-clear-btn" onclick="clearTaskHistory()">清空记录</button>
                ` : ''}
            </div>
        </div>

        <!-- Stats chips -->
        <div class="task-history-stats">
            <span class="task-history-stat">📦 总记录 <strong>${all.length}</strong></span>
            <span class="task-history-stat task-history-stat--done">✅ 已完成 <strong>${completedCount}</strong></span>
            <span class="task-history-stat task-history-stat--expired">⏰ 超期 <strong>${expiredCount}</strong></span>
        </div>

        <!-- Toolbar -->
        <div class="goal-toolbar">
            <div class="goal-toolbar__left" style="gap:10px">
                <span class="goal-toolbar__label">筛选</span>
                <select class="goal-filter-select" onchange="taskHistoryFilterCategory=this.value;taskHistoryPage=1;renderHistoryTasks()">
                    <option value="all" ${taskHistoryFilterCategory === 'all' ? 'selected' : ''}>全部属性</option>
                    ${AppData.categories.map(c => `
                        <option value="${c.id}" ${taskHistoryFilterCategory === c.id ? 'selected' : ''}>${c.name}</option>
                    `).join('')}
                </select>
                <select class="goal-filter-select" onchange="taskHistoryFilterStatus=this.value;taskHistoryPage=1;renderHistoryTasks()">
                    <option value="all" ${taskHistoryFilterStatus === 'all' ? 'selected' : ''}>全部状态</option>
                    <option value="completed" ${taskHistoryFilterStatus === 'completed' ? 'selected' : ''}>✅ 已完成</option>
                    <option value="expired" ${taskHistoryFilterStatus === 'expired' ? 'selected' : ''}>⏰ 超期</option>
                </select>
                <select class="goal-filter-select" onchange="taskHistorySortBy=this.value;taskHistoryPage=1;renderHistoryTasks()">
                    <option value="newest" ${taskHistorySortBy === 'newest' ? 'selected' : ''}>最新优先</option>
                    <option value="oldest" ${taskHistorySortBy === 'oldest' ? 'selected' : ''}>最早优先</option>
                    <option value="exp-high" ${taskHistorySortBy === 'exp-high' ? 'selected' : ''}>EXP 高→低</option>
                    <option value="exp-low" ${taskHistorySortBy === 'exp-low' ? 'selected' : ''}>EXP 低→高</option>
                </select>
            </div>
            <span class="goal-toolbar__count">共 ${filtered.length} 条</span>
        </div>

        <!-- Card list -->
        <div class="task-history-list">
            ${pageItems.map(t => renderHistoryCard(t)).join('')}
            ${pageItems.length === 0 ? `<div class="task-today-empty">暂无匹配的历史任务</div>` : ''}
        </div>

        <!-- Pagination -->
        ${totalPages > 1 ? renderHistoryPagination(taskHistoryPage, totalPages) : ''}
    `;

    document.getElementById('page-tasks').innerHTML = html;
}

function renderHistoryCard(task) {
    const cat = getCategory(task.category);
    const iconColor = TASK_COLORS[task.category] || '#46C9C0';
    const isCompleted = task.status === 'completed';
    const priorityText = task.priority === 'high' ? '高' : task.priority === 'mid' ? '中' : '低';
    const dateLabel = isCompleted ? (task.completedAt || '未知日期') : ('截止 ' + (task.deadline || '未知日期'));

    return `
        <div class="task-history-card">
            <div class="task-history-card__header">
                <span class="task-history-card__icon" style="color:${iconColor}">
                    ${cat ? attrIcon(cat.id, 18) : ''}
                </span>
                <span class="task-history-card__title">${task.title}</span>
                <span class="task-history-card__status ${isCompleted ? 'task-history-card__status--done' : 'task-history-card__status--expired'}">
                    ${isCompleted ? '✅ 已完成' : '⏰ 超期'}
                </span>
                <span class="task-history-card__exp">+${task.exp} EXP</span>
            </div>
            <div class="task-history-card__meta">
                <span>${cat ? cat.name : ''}</span>
                <span>·</span>
                <span>${priorityText}优先</span>
                <span>·</span>
                <span>${dateLabel}</span>
            </div>
            ${task.intro ? renderTaskIntro(task.id, task.intro) : ''}
        </div>
    `;
}

function renderHistoryPagination(page, total) {
    let pages = [];
    if (total <= 7) {
        for (let i = 1; i <= total; i++) pages.push(i);
    } else {
        pages.push(1);
        if (page > 3) pages.push('...');
        for (let i = Math.max(2, page - 1); i <= Math.min(total - 1, page + 1); i++) {
            pages.push(i);
        }
        if (page < total - 2) pages.push('...');
        pages.push(total);
    }

    return `
        <div class="task-history-pagination">
            <button class="task-history-pagination__btn" ${page <= 1 ? 'disabled' : ''}
                    onclick="taskHistoryPage=1;renderHistoryTasks()">«</button>
            <button class="task-history-pagination__btn" ${page <= 1 ? 'disabled' : ''}
                    onclick="taskHistoryPage=${page - 1};renderHistoryTasks()">‹</button>
            ${pages.map(p => p === '...' ? `
                <span class="task-history-pagination__ellipsis">...</span>
            ` : `
                <button class="task-history-pagination__btn ${p === page ? 'task-history-pagination__btn--active' : ''}"
                        onclick="taskHistoryPage=${p};renderHistoryTasks()">${p}</button>
            `).join('')}
            <button class="task-history-pagination__btn" ${page >= total ? 'disabled' : ''}
                    onclick="taskHistoryPage=${page + 1};renderHistoryTasks()">›</button>
            <button class="task-history-pagination__btn" ${page >= total ? 'disabled' : ''}
                    onclick="taskHistoryPage=${total};renderHistoryTasks()">»</button>
        </div>
    `;
}

function clearTaskHistory() {
    if (confirm('确定要清空所有历史任务记录吗？此操作不可撤销。')) {
        AppData.taskHistory = [];

        var curUser = getCurrentUser();
        if (curUser) {
            clearTaskHistoryOnBackend(curUser.id);
        }

        taskHistoryPage = 1;
        renderHistoryTasks();
        showToast('历史记录已清空', 'info');
    }
}

/* ================================================================
   Task Modal — 新建任务（支持常规/定时/每周）
   ================================================================ */

let taskModalType = 'normal'; // 'normal' | 'daily' | 'weekly'

function openTaskModal() {
    const cats = AppData.categories;
    const isToday = currentTasksSubPage !== 'week'; // 本日任务 or 历史

    // Determine which types are available
    const showDaily = isToday;       // 定时任务仅在本日任务
    const showWeekly = !isToday;     // 每周任务仅在本周任务

    taskModalType = 'normal';

    const typeTabs = [];
    typeTabs.push(`<button class="task-type-tab task-type-tab--active" data-type="normal" onclick="switchTaskType('normal')">常规任务</button>`);
    if (showDaily) {
        typeTabs.push(`<button class="task-type-tab" data-type="daily" onclick="switchTaskType('daily')">定时任务</button>`);
    }
    if (showWeekly) {
        typeTabs.push(`<button class="task-type-tab" data-type="weekly" onclick="switchTaskType('weekly')">每周任务</button>`);
    }

    const content = `
        <div style="display:flex;flex-direction:column;gap:16px">
            <!-- Type tabs -->
            <div class="task-type-tabs" id="task-type-tabs">
                ${typeTabs.join('')}
            </div>

            <!-- Daily hint -->
            <div id="task-daily-hint" class="task-daily-hint" style="display:none">
                <span>将在选中的每个日期的<strong>凌晨3点</strong>自动创建到本日任务</span>
            </div>

            <!-- Weekly hint -->
            <div id="task-weekly-hint" class="task-daily-hint" style="display:none">
                <span>将在<strong>每周一凌晨3点</strong>自动创建到本周任务，持续整个自然周</span>
            </div>

            <!-- Title -->
            <div>
                <label class="action-form__label">任务名称</label>
                <input class="input" id="task-title" placeholder="任务描述...">
            </div>

            <!-- Intro -->
            <div>
                <label class="action-form__label">任务介绍（可选）</label>
                <textarea class="input task-modal__intro" id="task-intro" placeholder="简单描述这个任务的内容和目标..." maxlength="200" style="min-height:70px;resize:vertical"></textarea>
            </div>

            <!-- Weekday picker (daily only) -->
            <div id="task-weekday-picker" style="display:none">
                <label class="action-form__label">重复日期</label>
                <div class="weekday-picker" id="weekday-picker">
                    ${renderWeekdayPicker()}
                </div>
                <div class="weekday-presets">
                    <button class="weekday-preset-btn" onclick="presetWeekdays('workday')">工作日</button>
                    <button class="weekday-preset-btn" onclick="presetWeekdays('weekend')">周末</button>
                    <button class="weekday-preset-btn" onclick="presetWeekdays('all')">每天</button>
                </div>
            </div>

            <!-- Category / Priority / EXP -->
            <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px">
                <div>
                    <label class="action-form__label">分类</label>
                    <select class="select" id="task-category" style="width:100%">
                        ${cats.map(cat => `<option value="${cat.id}">${cat.name}</option>`).join('')}
                    </select>
                </div>
                <div>
                    <label class="action-form__label">优先级</label>
                    <select class="select" id="task-priority" style="width:100%">
                        <option value="high">🔴 高优先级</option>
                        <option value="mid" selected>🟡 中等优先级</option>
                        <option value="low">🟢 低优先级</option>
                    </select>
                </div>
                <div>
                    <label class="action-form__label">经验值奖励</label>
                    <input class="input" type="number" id="task-exp" value="50" min="10" max="500" step="10">
                </div>
            </div>
        </div>
        <div class="modal__actions">
            <button class="btn btn--ghost" onclick="closeTaskModal()">取消</button>
            <button class="btn btn--primary" onclick="saveTask()">创建任务</button>
        </div>
    `;

    taskModalActive = true;
    openModal('新建任务', content, false);
}

function renderWeekdayPicker() {
    const days = ['一', '二', '三', '四', '五', '六', '日'];
    return days.map((d, i) => {
        const dayNum = i + 1;
        return `<button class="weekday-btn" data-day="${dayNum}" onclick="toggleWeekday(this, ${dayNum})">${d}</button>`;
    }).join('');
}

function switchTaskType(type) {
    taskModalType = type;

    // Update tab active state
    document.querySelectorAll('.task-type-tab').forEach(tab => {
        tab.classList.toggle('task-type-tab--active', tab.dataset.type === type);
    });

    // Show/hide weekday picker
    const picker = document.getElementById('task-weekday-picker');
    const dailyHint = document.getElementById('task-daily-hint');
    const weeklyHint = document.getElementById('task-weekly-hint');

    picker.style.display = type === 'daily' ? '' : 'none';
    dailyHint.style.display = type === 'daily' ? '' : 'none';
    weeklyHint.style.display = type === 'weekly' ? '' : 'none';
}

function toggleWeekday(btn, dayNum) {
    btn.classList.toggle('weekday-btn--active');
}

function presetWeekdays(preset) {
    const btns = document.querySelectorAll('.weekday-btn');
    btns.forEach(btn => {
        const day = parseInt(btn.dataset.day);
        let active;
        if (preset === 'workday') active = day >= 1 && day <= 5;
        else if (preset === 'weekend') active = day === 6 || day === 7;
        else active = true; // all
        btn.classList.toggle('weekday-btn--active', active);
    });
}

function getSelectedWeekdays() {
    const activeBtns = document.querySelectorAll('.weekday-btn--active');
    return Array.from(activeBtns).map(btn => parseInt(btn.dataset.day));
}

function saveTask() {
    const title = document.getElementById('task-title').value.trim();
    const category = document.getElementById('task-category').value;
    const priority = document.getElementById('task-priority').value;
    const exp = parseInt(document.getElementById('task-exp').value) || 50;
    const intro = document.getElementById('task-intro').value.trim();

    if (!title) {
        showToast('请输入任务名称', 'error');
        return;
    }

    if (taskModalType === 'daily') {
        // 定时任务模板
        const weekdays = getSelectedWeekdays();
        if (weekdays.length === 0) {
            showToast('请至少选择一个重复日期', 'error');
            return;
        }

        var curUser = getCurrentUser();
        const templateData = { type: 'daily', title, intro: intro || '', category, priority, exp, weekdays };

        function addLocalTemplate() {
            AppData.scheduledTasks.push({ id: Date.now(), ...templateData, active: true, createdAt: formatDate(new Date()) });
            closeTaskModal();
            renderTodayTasks();
            showToast(`定时任务模板已创建！每周 ${weekdays.map(d => ['一','二','三','四','五','六','日'][d-1]).join('、')} 自动创建`, 'success');
        }

        if (curUser) {
            createScheduledTaskOnBackend(curUser.id, templateData).then(result => {
                if (result) {
                    const daysLabel = weekdays.map(d => ['一','二','三','四','五','六','日'][d-1]).join('、');
                    closeTaskModal();
                    showToast(`定时任务模板已创建！每周 ${daysLabel} 自动创建`, 'success');
                } else {
                    addLocalTemplate();
                }
            }).catch(() => addLocalTemplate());
        } else {
            addLocalTemplate();
        }

    } else if (taskModalType === 'weekly') {
        // 每周任务模板
        var curUser = getCurrentUser();
        const templateData = { type: 'weekly', title, intro: intro || '', category, priority, exp };

        function addLocalWeeklyTemplate() {
            AppData.weeklyTaskTemplates.push({ id: Date.now(), ...templateData, active: true, createdAt: formatDate(new Date()) });
            closeTaskModal();
            renderWeekTasks();
            showToast('每周任务模板已创建！每周一凌晨自动创建', 'success');
        }

        if (curUser) {
            createScheduledTaskOnBackend(curUser.id, templateData).then(result => {
                if (result) {
                    closeTaskModal();
                    showToast('每周任务模板已创建！每周一凌晨自动创建', 'success');
                } else {
                    addLocalWeeklyTemplate();
                }
            }).catch(() => addLocalWeeklyTemplate());
        } else {
            addLocalWeeklyTemplate();
        }

    } else {
        // 常规任务
        var curUser = getCurrentUser();
        const taskData = { title, category, priority, exp, intro: intro || '' };

        function addLocalTask() {
            tasks.todo.push({
                id: Date.now(), ...taskData,
                createdAt: formatDate(new Date()), deadline: null,
                claimed: false, sourceTemplateId: null,
            });
            closeTaskModal();
            reRenderTasks();
            showToast('任务已创建！', 'success');
        }

        if (curUser) {
            createTaskOnBackend(curUser.id, taskData).then(result => {
                if (result) {
                    closeTaskModal();
                    tasksLoaded = false; // 下次渲染时重新加载
                    reRenderTasks();
                    showToast('任务已创建！', 'success');
                } else {
                    addLocalTask();
                }
            }).catch(() => addLocalTask());
        } else {
            addLocalTask();
        }
    }
}

function reRenderTasks() {
    if (currentTasksSubPage === 'week') renderWeekTasks();
    else if (currentTasksSubPage === 'history') renderHistoryTasks();
    else renderTodayTasks();
}

function closeTaskModal() {
    taskModalType = 'normal';
    taskModalActive = false;
    closeModal();
}

/* ================================================================
   定时任务模板管理（本日任务底部）
   ================================================================ */

let scheduledTemplatesExpanded = false;

function renderScheduledTemplates() {
    const templates = AppData.scheduledTasks.filter(t => t.type === 'daily');
    if (templates.length === 0) {
        return `<div class="template-section">
            <div class="template-section__header" onclick="scheduledTemplatesExpanded=!scheduledTemplatesExpanded;renderTodayTasks()">
                <span class="template-section__title">📋 定时任务模板 (0)</span>
                <span class="template-section__toggle">${scheduledTemplatesExpanded ? '收起 ▲' : '展开 ▼'}</span>
            </div>
            ${scheduledTemplatesExpanded ? `<div class="template-empty">还没有定时任务模板，点击"新建任务" → "定时任务"创建</div>` : ''}
        </div>`;
    }

    const activeCount = templates.filter(t => t.active).length;
    const days = ['一', '二', '三', '四', '五', '六', '日'];

    return `
        <div class="template-section">
            <div class="template-section__header" onclick="scheduledTemplatesExpanded=!scheduledTemplatesExpanded;renderTodayTasks()">
                <span class="template-section__title">📋 定时任务模板 (${templates.length})</span>
                <span class="template-section__badge">${activeCount} 个启用</span>
                <span class="template-section__toggle">${scheduledTemplatesExpanded ? '收起 ▲' : '展开 ▼'}</span>
            </div>
            ${scheduledTemplatesExpanded ? `
                <div class="template-list">
                    ${templates.map(t => {
                        const cat = getCategory(t.category);
                        const iconColor = TASK_COLORS[t.category] || '#46C9C0';
                        const weekLabels = t.weekdays.map(d => days[d - 1]).join(' ');
                        return `
                            <div class="template-card ${t.active ? '' : 'template-card--inactive'}">
                                <div class="template-card__main">
                                    <span class="template-card__icon" style="color:${iconColor}">${cat ? attrIcon(cat.id, 16) : ''}</span>
                                    <div class="template-card__info">
                                        <span class="template-card__title">${t.title}</span>
                                        <div class="template-card__meta">
                                            <span class="template-card__weekdays">${weekLabels.split(' ').map(d => `<span class="template-card__day">${d}</span>`).join('')}</span>
                                            <span style="color:var(--color-accent-light);font-weight:600">+${t.exp} EXP</span>
                                        </div>
                                    </div>
                                </div>
                                <div class="template-card__actions">
                                    <button class="template-card__toggle ${t.active ? 'template-card__toggle--on' : ''}"
                                            onclick="event.stopPropagation();toggleTemplateActive(${t.id})">
                                        ${t.active ? '启用' : '暂停'}
                                    </button>
                                    <button class="template-card__edit" onclick="event.stopPropagation();editTemplate(${t.id})">编辑</button>
                                    <button class="template-card__del" onclick="event.stopPropagation();deleteTemplate(${t.id})">删除</button>
                                </div>
                            </div>
                        `;
                    }).join('')}
                </div>
            ` : ''}
        </div>
    `;
}

function toggleTemplateActive(id) {
    const tmpl = AppData.scheduledTasks.find(t => t.id === id);
    if (tmpl) {
        tmpl.active = !tmpl.active;

        var curUser = getCurrentUser();
        if (curUser) {
            updateScheduledTaskOnBackend(id, { active: tmpl.active ? 1 : 0 });
        }

        renderTodayTasks();
        showToast(tmpl.active ? '定时任务已启用' : '定时任务已暂停', 'info');
    }
}

function deleteTemplate(id) {
    if (!confirm('确定要删除这个定时任务模板吗？已创建的任务不受影响。')) return;
    AppData.scheduledTasks = AppData.scheduledTasks.filter(t => t.id !== id);

    var curUser = getCurrentUser();
    if (curUser) {
        deleteScheduledTaskOnBackend(id);
    }

    renderTodayTasks();
    showToast('定时任务模板已删除', 'info');
}

function editTemplate(id) {
    const tmpl = AppData.scheduledTasks.find(t => t.id === id);
    if (!tmpl) return;

    const cats = AppData.categories;
    const days = ['一', '二', '三', '四', '五', '六', '日'];

    const content = `
        <div style="display:flex;flex-direction:column;gap:16px">
            <div>
                <label class="action-form__label">任务名称</label>
                <input class="input" id="edit-task-title" value="${escapeHtml(tmpl.title)}" placeholder="任务描述...">
            </div>
            <div>
                <label class="action-form__label">任务介绍（可选）</label>
                <textarea class="input task-modal__intro" id="edit-task-intro" placeholder="简单描述这个任务的内容和目标..." maxlength="200" style="min-height:70px;resize:vertical">${escapeHtml(tmpl.intro || '')}</textarea>
            </div>
            <div>
                <label class="action-form__label">重复日期</label>
                <div class="weekday-picker" id="edit-weekday-picker">
                    ${days.map((d, i) => {
                        const dayNum = i + 1;
                        const active = tmpl.weekdays.includes(dayNum);
                        return `<button class="weekday-btn ${active ? 'weekday-btn--active' : ''}" data-day="${dayNum}" onclick="this.classList.toggle('weekday-btn--active')">${d}</button>`;
                    }).join('')}
                </div>
                <div class="weekday-presets">
                    <button class="weekday-preset-btn" onclick="presetEditWeekdays('workday')">工作日</button>
                    <button class="weekday-preset-btn" onclick="presetEditWeekdays('weekend')">周末</button>
                    <button class="weekday-preset-btn" onclick="presetEditWeekdays('all')">每天</button>
                </div>
            </div>
            <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px">
                <div>
                    <label class="action-form__label">分类</label>
                    <select class="select" id="edit-task-category" style="width:100%">
                        ${cats.map(cat => `<option value="${cat.id}" ${cat.id === tmpl.category ? 'selected' : ''}>${cat.name}</option>`).join('')}
                    </select>
                </div>
                <div>
                    <label class="action-form__label">优先级</label>
                    <select class="select" id="edit-task-priority" style="width:100%">
                        <option value="high" ${tmpl.priority === 'high' ? 'selected' : ''}>🔴 高优先级</option>
                        <option value="mid" ${tmpl.priority === 'mid' ? 'selected' : ''}>🟡 中等优先级</option>
                        <option value="low" ${tmpl.priority === 'low' ? 'selected' : ''}>🟢 低优先级</option>
                    </select>
                </div>
                <div>
                    <label class="action-form__label">经验值奖励</label>
                    <input class="input" type="number" id="edit-task-exp" value="${tmpl.exp}" min="10" max="500" step="10">
                </div>
            </div>
        </div>
        <div class="modal__actions">
            <button class="btn btn--ghost" onclick="closeModal()">取消</button>
            <button class="btn btn--primary" onclick="saveEditTemplate(${id})">保存修改</button>
        </div>
    `;

    taskModalActive = true;
    openModal('编辑定时任务模板', content, false);
}

function presetEditWeekdays(preset) {
    const btns = document.querySelectorAll('#edit-weekday-picker .weekday-btn');
    btns.forEach(btn => {
        const day = parseInt(btn.dataset.day);
        let active;
        if (preset === 'workday') active = day >= 1 && day <= 5;
        else if (preset === 'weekend') active = day === 6 || day === 7;
        else active = true;
        btn.classList.toggle('weekday-btn--active', active);
    });
}

function saveEditTemplate(id) {
    const tmpl = AppData.scheduledTasks.find(t => t.id === id);
    if (!tmpl) return;

    const title = document.getElementById('edit-task-title').value.trim();
    if (!title) { showToast('请输入任务名称', 'error'); return; }

    const weekdays = Array.from(document.querySelectorAll('#edit-weekday-picker .weekday-btn--active'))
        .map(btn => parseInt(btn.dataset.day));
    if (weekdays.length === 0) { showToast('请至少选择一个重复日期', 'error'); return; }

    tmpl.title = title;
    tmpl.intro = document.getElementById('edit-task-intro').value.trim();
    tmpl.category = document.getElementById('edit-task-category').value;
    tmpl.priority = document.getElementById('edit-task-priority').value;
    tmpl.exp = parseInt(document.getElementById('edit-task-exp').value) || 50;
    tmpl.weekdays = weekdays;

    taskModalActive = false;
    closeModal();
    renderTodayTasks();
    showToast('定时任务模板已更新', 'success');
}

/* ================================================================
   每周任务模板管理（本周任务底部）
   ================================================================ */

let weeklyTemplatesExpanded = false;

function renderWeeklyTemplates() {
    const templates = AppData.weeklyTaskTemplates.filter(t => t.type === 'weekly');
    if (templates.length === 0) {
        return `<div class="template-section">
            <div class="template-section__header" onclick="weeklyTemplatesExpanded=!weeklyTemplatesExpanded;renderWeekTasks()">
                <span class="template-section__title">📅 每周任务模板 (0)</span>
                <span class="template-section__toggle">${weeklyTemplatesExpanded ? '收起 ▲' : '展开 ▼'}</span>
            </div>
            ${weeklyTemplatesExpanded ? `<div class="template-empty">还没有每周任务模板，点击"新建任务" → "每周任务"创建</div>` : ''}
        </div>`;
    }

    const activeCount = templates.filter(t => t.active).length;

    return `
        <div class="template-section">
            <div class="template-section__header" onclick="weeklyTemplatesExpanded=!weeklyTemplatesExpanded;renderWeekTasks()">
                <span class="template-section__title">📅 每周任务模板 (${templates.length})</span>
                <span class="template-section__badge">${activeCount} 个启用</span>
                <span class="template-section__toggle">${weeklyTemplatesExpanded ? '收起 ▲' : '展开 ▼'}</span>
            </div>
            ${weeklyTemplatesExpanded ? `
                <div class="template-list">
                    ${templates.map(t => {
                        const cat = getCategory(t.category);
                        const iconColor = TASK_COLORS[t.category] || '#46C9C0';
                        return `
                            <div class="template-card ${t.active ? '' : 'template-card--inactive'}">
                                <div class="template-card__main">
                                    <span class="template-card__icon" style="color:${iconColor}">${cat ? attrIcon(cat.id, 16) : ''}</span>
                                    <div class="template-card__info">
                                        <span class="template-card__title">${t.title}</span>
                                        <div class="template-card__meta">
                                            <span class="template-card__schedule">🔄 每周一凌晨3点</span>
                                            <span style="color:var(--color-accent-light);font-weight:600">+${t.exp} EXP</span>
                                        </div>
                                    </div>
                                </div>
                                <div class="template-card__actions">
                                    <button class="template-card__toggle ${t.active ? 'template-card__toggle--on' : ''}"
                                            onclick="event.stopPropagation();toggleWeeklyTemplateActive(${t.id})">
                                        ${t.active ? '启用' : '暂停'}
                                    </button>
                                    <button class="template-card__edit" onclick="event.stopPropagation();editWeeklyTemplate(${t.id})">编辑</button>
                                    <button class="template-card__del" onclick="event.stopPropagation();deleteWeeklyTemplate(${t.id})">删除</button>
                                </div>
                            </div>
                        `;
                    }).join('')}
                </div>
            ` : ''}
        </div>
    `;
}

function toggleWeeklyTemplateActive(id) {
    const tmpl = AppData.weeklyTaskTemplates.find(t => t.id === id);
    if (tmpl) {
        tmpl.active = !tmpl.active;

        var curUser = getCurrentUser();
        if (curUser) {
            updateScheduledTaskOnBackend(id, { active: tmpl.active ? 1 : 0 });
        }

        renderWeekTasks();
        showToast(tmpl.active ? '每周任务已启用' : '每周任务已暂停', 'info');
    }
}

function deleteWeeklyTemplate(id) {
    if (!confirm('确定要删除这个每周任务模板吗？已创建的任务不受影响。')) return;
    AppData.weeklyTaskTemplates = AppData.weeklyTaskTemplates.filter(t => t.id !== id);

    var curUser = getCurrentUser();
    if (curUser) {
        deleteScheduledTaskOnBackend(id);
    }

    renderWeekTasks();
    showToast('每周任务模板已删除', 'info');
}

function editWeeklyTemplate(id) {
    const tmpl = AppData.weeklyTaskTemplates.find(t => t.id === id);
    if (!tmpl) return;

    const cats = AppData.categories;

    const content = `
        <div style="display:flex;flex-direction:column;gap:16px">
            <div style="padding:8px 12px;background:rgba(212,154,62,0.1);border-radius:8px;font-size:12px;color:var(--color-accent-light)">
                🔄 此任务将在<strong>每周一凌晨3点</strong>自动创建，持续一周
            </div>
            <div>
                <label class="action-form__label">任务名称</label>
                <input class="input" id="edit-weekly-title" value="${escapeHtml(tmpl.title)}" placeholder="任务描述...">
            </div>
            <div>
                <label class="action-form__label">任务介绍（可选）</label>
                <textarea class="input task-modal__intro" id="edit-weekly-intro" placeholder="简单描述这个任务的内容和目标..." maxlength="200" style="min-height:70px;resize:vertical">${escapeHtml(tmpl.intro || '')}</textarea>
            </div>
            <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px">
                <div>
                    <label class="action-form__label">分类</label>
                    <select class="select" id="edit-weekly-category" style="width:100%">
                        ${cats.map(cat => `<option value="${cat.id}" ${cat.id === tmpl.category ? 'selected' : ''}>${cat.name}</option>`).join('')}
                    </select>
                </div>
                <div>
                    <label class="action-form__label">优先级</label>
                    <select class="select" id="edit-weekly-priority" style="width:100%">
                        <option value="high" ${tmpl.priority === 'high' ? 'selected' : ''}>🔴 高优先级</option>
                        <option value="mid" ${tmpl.priority === 'mid' ? 'selected' : ''}>🟡 中等优先级</option>
                        <option value="low" ${tmpl.priority === 'low' ? 'selected' : ''}>🟢 低优先级</option>
                    </select>
                </div>
                <div>
                    <label class="action-form__label">经验值奖励</label>
                    <input class="input" type="number" id="edit-weekly-exp" value="${tmpl.exp}" min="10" max="500" step="10">
                </div>
            </div>
        </div>
        <div class="modal__actions">
            <button class="btn btn--ghost" onclick="closeModal()">取消</button>
            <button class="btn btn--primary" onclick="saveEditWeeklyTemplate(${id})">保存修改</button>
        </div>
    `;

    taskModalActive = true;
    openModal('编辑每周任务模板', content, false);
}

function saveEditWeeklyTemplate(id) {
    const tmpl = AppData.weeklyTaskTemplates.find(t => t.id === id);
    if (!tmpl) return;

    const title = document.getElementById('edit-weekly-title').value.trim();
    if (!title) { showToast('请输入任务名称', 'error'); return; }

    tmpl.title = title;
    tmpl.intro = document.getElementById('edit-weekly-intro').value.trim();
    tmpl.category = document.getElementById('edit-weekly-category').value;
    tmpl.priority = document.getElementById('edit-weekly-priority').value;
    tmpl.exp = parseInt(document.getElementById('edit-weekly-exp').value) || 50;

    taskModalActive = false;
    closeModal();
    renderWeekTasks();
    showToast('每周任务模板已更新', 'success');
}
