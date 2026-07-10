/* ================================================================
   Dashboard Page — 仪表盘主页
   ================================================================ */

// Dashboard SVG icons (from 冒险者面板图标-竞技版.svg)
const DASH_ICONS = {
    welcome: `<svg viewBox="0 0 80 80" width="42" height="42"><circle cx="40" cy="40" r="28" fill="#4a3b1f"/><path d="M26 48c0-8 6-18 14-22 8 4 14 14 14 22" fill="#b08d39"/><path d="M30 46c0-6 4-14 10-18 6 4 10 12 10 18" fill="#e6c05c"/><path d="M36 44c0-4 2-9 4-12 2 3 4 8 4 12" fill="#fff4c7"/><circle cx="22" cy="26" r="3" fill="#e6c05c"/><circle cx="58" cy="30" r="2.5" fill="#fff4c7"/><path d="M20 34c2-3 5-5 8-6M52 24c3 1 6 3 8 6" stroke="#b08d39" stroke-width="1.5" fill="none" stroke-linecap="round"/></svg>`,
    streak: `<svg viewBox="0 0 80 80" width="72" height="72"><circle cx="40" cy="40" r="28" fill="#4a1f14"/><path d="M40 20c8 6 14 16 14 26 0 12-10 22-14 22s-14-10-14-22c0-10 6-20 14-26z" fill="#c94a2e"/><path d="M40 26c6 5 10 13 10 20 0 9-7 17-10 17s-10-8-10-17c0-7 4-15 10-20z" fill="#e86a3a"/><path d="M40 32c4 4 6 10 6 14 0 6-4 11-6 11s-6-5-6-11c0-4 2-10 6-14z" fill="#ffab4a"/><circle cx="28" cy="34" r="2" fill="#ffab4a"/><circle cx="52" cy="30" r="1.8" fill="#ffd47a"/><circle cx="30" cy="52" r="1.5" fill="#ffd47a"/><circle cx="50" cy="48" r="1.2" fill="#fff0c7"/></svg>`,
    level: `<svg viewBox="0 0 80 80" width="30" height="30"><circle cx="40" cy="40" r="28" fill="#4a3d18"/><polygon points="40,18 45,33 61,33 48,43 53,58 40,49 27,58 32,43 19,33 35,33" fill="#d4a72c"/><polygon points="40,24 43,34 54,34 45,41 48,52 40,45 32,52 35,41 26,34 37,34" fill="#f5c94c"/><circle cx="40" cy="38" r="7" fill="#fff4c7"/><text x="40" y="42" text-anchor="middle" font-family="Arial, sans-serif" font-size="10" font-weight="700" fill="#b08d39">LV</text><path d="M40 12v4M40 64v4M12 40h4M64 40h4" stroke="#d4a72c" stroke-width="1.5" stroke-linecap="round"/><circle cx="40" cy="10" r="2" fill="#fff4c7"/><circle cx="40" cy="70" r="2" fill="#fff4c7"/><circle cx="10" cy="40" r="2" fill="#fff4c7"/><circle cx="70" cy="40" r="2" fill="#fff4c7"/></svg>`,
    focus: `<svg viewBox="0 0 80 80" width="42" height="42"><circle cx="40" cy="40" r="28" fill="#222a4a"/><circle cx="40" cy="40" r="18" fill="#3a4a7a"/><ellipse cx="40" cy="40" rx="32" ry="8" fill="none" stroke="#7a9af5" stroke-width="2" transform="rotate(-25 40 40)"/><ellipse cx="40" cy="40" rx="32" ry="8" fill="none" stroke="#aabfff" stroke-width="1.2" transform="rotate(-25 40 40)"/><circle cx="40" cy="40" r="10" fill="#aabfff"/><circle cx="40" cy="40" r="5" fill="#e6eeff"/><circle cx="22" cy="22" r="2" fill="#aabfff"/><circle cx="58" cy="24" r="1.5" fill="#e6eeff"/><circle cx="62" cy="56" r="2" fill="#aabfff"/><path d="M18 50l4-1M58 64l-1-4M66 30l-3 2" stroke="#7a9af5" stroke-width="1" stroke-linecap="round"/></svg>`,
    tasks: `<svg viewBox="0 0 80 80" width="42" height="42"><circle cx="40" cy="40" r="28" fill="#1a3d28"/><path d="M24 38c8-4 16-4 24 0s16 4 24 0c-4 12-14 20-24 20s-20-8-24-20z" fill="#3ebf75"/><path d="M28 40c6-3 12-3 18 0s12 3 18 0c-3 9-10 15-18 15s-15-6-18-15z" fill="#5dd992"/><path d="M32 42c4-2 8-2 12 0s8 2 12 0c-2 6-6 10-12 10s-10-4-12-10z" fill="#aaffc7"/><path d="M38 42l6 7 14-14" fill="none" stroke="#0f2e1b" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round"/><path d="M38 42l6 7 14-14" fill="none" stroke="#e6fff0" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/><circle cx="22" cy="28" r="2" fill="#aaffc7"/><circle cx="60" cy="54" r="1.8" fill="#aaffc7"/></svg>`,
    habits: `<svg viewBox="0 0 80 80" width="42" height="42"><circle cx="40" cy="40" r="28" fill="#183048"/><rect x="26" y="24" width="28" height="36" rx="4" fill="#2a5580"/><rect x="29" y="27" width="22" height="30" rx="2" fill="#3a75a8"/><line x1="33" y1="34" x2="47" y2="34" stroke="#7ab8e6" stroke-width="2" stroke-linecap="round"/><line x1="33" y1="42" x2="47" y2="42" stroke="#7ab8e6" stroke-width="2" stroke-linecap="round"/><line x1="33" y1="50" x2="42" y2="50" stroke="#7ab8e6" stroke-width="2" stroke-linecap="round"/><circle cx="54" cy="28" r="7" fill="#4a9fd8"/><path d="M51 28l2.5 2.5L57 25" fill="none" stroke="#e6f4ff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/><path d="M28 60c2 2 6 2 8 0" stroke="#4a9fd8" stroke-width="1.5" fill="none" stroke-linecap="round"/></svg>`,
    exp: `<svg viewBox="0 0 80 80" width="42" height="42"><circle cx="40" cy="40" r="28" fill="#4a2818"/><polygon points="40,14 46,32 66,32 50,44 56,62 40,51 24,62 30,44 14,32 34,32" fill="#e87b35"/><polygon points="40,20 44,33 58,33 47,41 51,55 40,47 29,55 33,41 22,33 36,33" fill="#f5a04c"/><polygon points="40,26 42,34 51,34 44,40 47,49 40,43 33,49 36,40 29,34 38,34" fill="#ffdb9e"/><text x="40" y="42" text-anchor="middle" font-family="Arial, sans-serif" font-size="12" font-weight="700" fill="#9e4a18">+</text><circle cx="20" cy="36" r="2" fill="#ffdb9e"/><circle cx="60" cy="36" r="1.8" fill="#ffdb9e"/><circle cx="40" cy="68" r="2" fill="#ffdb9e"/><path d="M28 20c3-2 7-3 12-3s9 1 12 3" stroke="#e87b35" stroke-width="1.5" fill="none" stroke-linecap="round"/></svg>`,
};

function renderDashboard() {
    // 重新拉取最新数据
    const userData = getCurrentUser();
    if (userData) {
        Promise.all([
            fetchUserProfile(userData.id),
            fetchHabits(userData.id),
        ]).then(([profile, habitsData]) => {
            if (profile) {
                AppData.user = {
                    ...AppData.user,
                    ...profile.user,
                    get expToNext() { return expForLevel(this.level); },
                    get title() { return getRankInfo(this.level).name; },
                };
                AppData.todayStats = profile.todayStats;
                AppData.yesterdayStats = profile.yesterdayStats;
            }
            if (habitsData) {
                AppData.habits = habitsData;
            }
            renderDashboardContent();
        }).catch(() => renderDashboardContent());
    } else {
        renderDashboardContent();
    }
}

function renderDashboardContent() {
    const { user, todayStats, yesterdayStats, recentActivities } = AppData;

    const focusTrend = getTrend(todayStats.focusMinutes, yesterdayStats.focusMinutes);
    const taskTrend = getTrend(todayStats.tasksDone, yesterdayStats.tasksDone);
    const habitTrend = getTrend(todayStats.habitsChecked, yesterdayStats.habitsChecked);
    const expTrend = getTrend(todayStats.expEarned, yesterdayStats.expEarned);

    const html = `
        <!-- Welcome Banner -->
        <div class="welcome-banner">
            <div class="welcome-banner__text">
                <h2><span style="display:inline-flex;vertical-align:middle;margin-right:8px">${DASH_ICONS.welcome}</span>欢迎回来，${user.name}</h2>
                <p>${user.title} · 继续今天的成长之旅吧</p>
            </div>
            <div class="welcome-banner__streak">
                <div style="display:flex;align-items:center;gap:6px">
                    ${DASH_ICONS.streak}
                    <div>
                        <div class="welcome-banner__streak-num">${user.streak}</div>
                        <div class="welcome-banner__streak-label">连续打卡天数</div>
                    </div>
                </div>
            </div>
        </div>

        <!-- EXP Bar -->
        ${renderExpBar(user.exp, user.expToNext, user.level, DASH_ICONS.level)}

        <!-- Today Stats -->
        <div class="section">
            <div class="section__title">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18"/></svg>
                今日概览
            </div>
            <div class="grid-4col">
                ${renderStatCard(DASH_ICONS.focus, formatMinutes(todayStats.focusMinutes), '专注时长', focusTrend, focusTrend >= 0)}
                ${renderStatCard(DASH_ICONS.tasks, todayStats.tasksDone + ' 个', '完成任务', taskTrend, taskTrend >= 0)}
                ${renderStatCard(DASH_ICONS.habits, todayStats.habitsChecked + '/' + (AppData.habits.filter(h => h.active !== false).length || 6), '习惯打卡', habitTrend, habitTrend >= 0)}
                ${renderStatCard(DASH_ICONS.exp, '+' + todayStats.expEarned, '获得经验', expTrend, expTrend >= 0)}
            </div>
        </div>

        <!-- Pending Habits + Recent Activity -->
        <div class="grid-2col">
            <!-- Pending Habits (replaces 八维属性概览) -->
            <div class="card">
                <div class="section__title">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2L2 22h20L12 2z"/><circle cx="12" cy="16" r="2"/></svg>
                    待打卡习惯
                </div>
                ${renderPendingHabits()}
            </div>

            <!-- Recent Activity -->
            <div class="card">
                <div class="section__title">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
                    近期动态
                </div>
                <div class="timeline">
                    ${recentActivities.map(act => {
                        const cat = getCategory(act.category);
                        return `
                            <div class="timeline__item ${act.category === 'health' ? 'timeline__item--accent' : ''}">
                                <div class="timeline__time">${act.time}</div>
                                <div class="timeline__text">
                                    ${act.action} <strong>${act.target}</strong>
                                    ${cat ? `<span class="badge badge--primary" style="margin-left:6px;display:inline-flex;align-items:center;gap:4px">${attrIcon(cat.id, 14)} ${cat.name}</span>` : ''}
                                    <span style="color:var(--color-accent-light);margin-left:6px;font-weight:600">+${act.exp} EXP</span>
                                </div>
                            </div>
                        `;
                    }).join('')}
                </div>
            </div>
        </div>
    `;

    document.getElementById('page-dashboard').innerHTML = html;
}

/** Render pending habits list for dashboard (read-only, no check-in) */
function renderPendingHabits() {
    const pending = AppData.habits.filter(h =>
        h.active !== false && !h.todayDone && !h.todaySkipped
    );

    if (pending.length === 0) {
        return `
            <div class="dash-habit-empty">
                <div class="dash-habit-empty__icon">🎉</div>
                <div class="dash-habit-empty__text">今日习惯全部完成！</div>
            </div>
        `;
    }

    return `
        <div class="dash-habit-list">
            ${pending.map(h => {
                const cat = getCategory(h.category);
                return `
                    <div class="dash-habit-item">
                        <span class="dash-habit-item__icon">${h.icon}</span>
                        <span class="dash-habit-item__name">${h.name}</span>
                        <span class="dash-habit-item__cat" style="color:${cat ? cat.color : '#9ca3af'}">${cat ? cat.name : ''}</span>
                        <span class="dash-habit-item__streak">🔥 ${h.streak}天</span>
                    </div>
                `;
            }).join('')}
        </div>
    `;
}
