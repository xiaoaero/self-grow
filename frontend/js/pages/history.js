/* ================================================================
   History Page — 成长记录（数据看板）
   ================================================================ */

// SVG icons extracted from 成长记录图标.svg
const HIST_ICONS = {
    // Page title: 成长记录 (clipboard with checkmark)
    title: `<svg viewBox="0 0 56 56" fill="none"><circle cx="28" cy="28" r="22" fill="#064e3b" opacity="0.4"/><circle cx="28" cy="28" r="16" fill="#065f46" opacity="0.25"/><rect x="18" y="18" width="20" height="24" rx="3" fill="url(#g-gr)" filter="url(#glow)"/><rect x="21" y="22" width="14" height="3" rx="1" fill="#a7f3d0"/><rect x="21" y="27" width="14" height="2" rx="1" fill="#a7f3d0" opacity="0.7"/><rect x="21" y="31" width="14" height="2" rx="1" fill="#a7f3d0" opacity="0.5"/><rect x="21" y="35" width="10" height="2" rx="1" fill="#a7f3d0" opacity="0.4"/><path d="M27 39 L30 42 L37 36" stroke="#fff" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg>`,

    // effortDays: 累计天数 (calendar grid)
    days: `<svg viewBox="0 0 56 56" fill="none"><circle cx="28" cy="28" r="22" fill="#1e3a8a" opacity="0.35"/><circle cx="28" cy="28" r="16" fill="#1d4ed8" opacity="0.2"/><rect x="16" y="20" width="24" height="24" rx="3" fill="#1f2937" stroke="#60a5fa" stroke-width="1.5"/><line x1="16" y1="28" x2="40" y2="28" stroke="#60a5fa" stroke-width="0.8" opacity="0.5"/><line x1="28" y1="20" x2="28" y2="44" stroke="#60a5fa" stroke-width="0.8" opacity="0.5"/><text x="22" y="26" text-anchor="middle" fill="#93c5fd" font-size="5" font-weight="600">30</text><text x="36" y="26" text-anchor="middle" fill="#93c5fd" font-size="5" font-weight="600">30</text><text x="22" y="36" text-anchor="middle" fill="#93c5fd" font-size="5" font-weight="600">30</text><text x="36" y="36" text-anchor="middle" fill="#60a5fa" font-size="5" font-weight="600">30</text><circle cx="22" cy="43" r="2" fill="#60a5fa"/><circle cx="36" cy="43" r="2" fill="#3b82f6"/></svg>`,

    // totalXP: 累计XP (star with XP text)
    xp: `<svg viewBox="0 0 56 56" fill="none"><circle cx="28" cy="28" r="22" fill="#78350f" opacity="0.35"/><circle cx="28" cy="28" r="16" fill="#92400e" opacity="0.2"/><path d="M28 14 L32 24 L44 25 L35 31 L37 42 L28 36 L19 42 L21 31 L12 25 L24 24 Z" fill="url(#g-exp)" filter="url(#glow)"/><circle cx="28" cy="28" r="5" fill="#fef3c7"/><text x="28" y="30" text-anchor="middle" fill="#92400e" font-size="5" font-weight="700">XP</text></svg>`,

    // habitCheckins: 习惯打卡 (checkmark box)
    checkins: `<svg viewBox="0 0 56 56" fill="none"><circle cx="28" cy="28" r="22" fill="#4c1d95" opacity="0.35"/><circle cx="28" cy="28" r="16" fill="#6d28d9" opacity="0.2"/><path d="M20 24 L28 20 L36 24 L36 40 L28 44 L20 40 Z" fill="url(#g-task)" filter="url(#glow)"/><path d="M24 30 L27 34 L33 27" stroke="#fff" stroke-width="2.5" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg>`,

    // tasksCompleted: 完成任务 (checklist with badge)
    tasks: `<svg viewBox="0 0 56 56" fill="none"><circle cx="28" cy="28" r="22" fill="#881337" opacity="0.3"/><circle cx="28" cy="28" r="16" fill="#be123c" opacity="0.2"/><rect x="14" y="16" width="28" height="32" rx="4" fill="url(#g-score)" filter="url(#glow)"/><rect x="22" y="12" width="12" height="7" rx="3" fill="#fecdd3"/><rect x="18" y="23" width="5" height="5" rx="1.5" fill="#fff"/><path d="M20 25 L22 27 L25 23" stroke="#e11d48" stroke-width="1.5" fill="none" stroke-linecap="round" stroke-linejoin="round"/><line x1="26" y1="25" x2="38" y2="25" stroke="#fecdd3" stroke-width="2" stroke-linecap="round" opacity="0.5"/><rect x="18" y="32" width="5" height="5" rx="1.5" fill="none" stroke="#fecdd3" stroke-width="1.2" opacity="0.5"/><line x1="26" y1="34" x2="35" y2="34" stroke="#fecdd3" stroke-width="1.5" stroke-linecap="round" opacity="0.3"/><rect x="18" y="41" width="5" height="5" rx="1.5" fill="#fff"/><path d="M20 43 L22 45 L25 41" stroke="#e11d48" stroke-width="1.5" fill="none" stroke-linecap="round" stroke-linejoin="round"/><line x1="26" y1="43" x2="33" y2="43" stroke="#fecdd3" stroke-width="2" stroke-linecap="round" opacity="0.35"/></svg>`,

    // goalsAchieved: 达成目标 (target/crosshair)
    goals: `<svg viewBox="0 0 56 56" fill="none"><circle cx="28" cy="28" r="22" fill="#155e75" opacity="0.35"/><circle cx="28" cy="28" r="16" fill="#0e7490" opacity="0.2"/><circle cx="28" cy="28" r="14" fill="none" stroke="url(#g-target)" stroke-width="2.5" filter="url(#glow)"/><circle cx="28" cy="28" r="9" fill="none" stroke="url(#g-target)" stroke-width="2" opacity="0.7"/><circle cx="28" cy="28" r="5" fill="url(#g-target)"/><circle cx="28" cy="28" r="2" fill="#cffafe"/><path d="M28 14 L28 18 M28 38 L28 42 M14 28 L18 28 M38 28 L42 28" stroke="url(#g-target)" stroke-width="2" stroke-linecap="round"/></svg>`,

    // rewardsUnlocked: 解锁奖励 (star with $)
    rewards: `<svg viewBox="0 0 56 56" fill="none"><circle cx="28" cy="28" r="22" fill="#831843" opacity="0.3"/><circle cx="28" cy="28" r="16" fill="#be185d" opacity="0.2"/><path d="M28 14 L33 24 L44 25 L35 31 L37 42 L28 36 L19 42 L21 31 L12 25 L23 24 Z" fill="url(#g-rew)" filter="url(#glow)"/><circle cx="28" cy="28" r="5" fill="#fff"/><text x="28" y="30" text-anchor="middle" fill="#be185d" font-size="5" font-weight="700">$</text></svg>`,

    // heatmap: 热力图 (colored blocks)
    heatmap: `<svg viewBox="0 0 56 56" fill="none"><circle cx="28" cy="28" r="22" fill="#7c2d12" opacity="0.35"/><circle cx="28" cy="28" r="16" fill="#9a3412" opacity="0.2"/><g transform="translate(28,28)"><rect x="-16" y="-7" width="5" height="5" rx="1" fill="#9a3412" opacity="0.5"/><rect x="-10" y="-7" width="5" height="5" rx="1" fill="#fb923c" opacity="0.7"/><rect x="-4" y="-7" width="5" height="5" rx="1" fill="#fb923c" opacity="0.8"/><rect x="2" y="-7" width="5" height="5" rx="1" fill="url(#g-heat)"/><rect x="8" y="-7" width="5" height="5" rx="1" fill="url(#g-heat)" filter="url(#glow)"/><rect x="14" y="-7" width="5" height="5" rx="1" fill="#fdba74"/><rect x="-16" y="0" width="5" height="5" rx="1" fill="#fb923c" opacity="0.6"/><rect x="-10" y="0" width="5" height="5" rx="1" fill="url(#g-heat)"/><rect x="-4" y="0" width="5" height="5" rx="1" fill="url(#g-heat)"/><rect x="2" y="0" width="5" height="5" rx="1" fill="url(#g-heat)" filter="url(#glow)"/><rect x="8" y="0" width="5" height="5" rx="1" fill="url(#g-heat)"/><rect x="14" y="0" width="5" height="5" rx="1" fill="#fb923c" opacity="0.6"/><rect x="-16" y="7" width="5" height="5" rx="1" fill="#9a3412" opacity="0.5"/><rect x="-10" y="7" width="5" height="5" rx="1" fill="#fb923c" opacity="0.6"/><rect x="-4" y="7" width="5" height="5" rx="1" fill="url(#g-heat)"/><rect x="2" y="7" width="5" height="5" rx="1" fill="url(#g-heat)"/><rect x="8" y="7" width="5" height="5" rx="1" fill="#fb923c" opacity="0.7"/><rect x="14" y="7" width="5" height="5" rx="1" fill="#9a3412" opacity="0.4"/></g></svg>`,

    // radar: 维度雷达 (hexagon)
    radar: `<svg viewBox="0 0 56 56" fill="none"><circle cx="28" cy="28" r="22" fill="#581c87" opacity="0.35"/><circle cx="28" cy="28" r="16" fill="#6b21a8" opacity="0.2"/><path d="M28 16 L38 20 L38 28 L28 36 L18 28 L18 20 Z" fill="none" stroke="url(#g-radar)" stroke-width="1.5" opacity="0.4"/><path d="M28 20 L34 23 L34 28 L28 32 L22 28 L22 23 Z" fill="none" stroke="url(#g-radar)" stroke-width="1.5" opacity="0.6"/><path d="M28 25 L31 26 L31 28 L28 30 L25 28 L25 26 Z" fill="url(#g-radar)" filter="url(#glow)"/></svg>`,

    // rank: 维度经验 (scatter nodes)
    rank: `<svg viewBox="0 0 56 56" fill="none"><circle cx="28" cy="28" r="22" fill="#14532d" opacity="0.35"/><circle cx="28" cy="28" r="16" fill="#166534" opacity="0.2"/><circle cx="20" cy="16" r="4" fill="#fb7185" filter="url(#glow)"/><circle cx="20" cy="16" r="1.5" fill="#fff1f2"/><circle cx="40" cy="14" r="4" fill="#22d3ee" filter="url(#glow)"/><circle cx="40" cy="14" r="1.5" fill="#cffafe"/><circle cx="46" cy="28" r="4" fill="#f472b6" filter="url(#glow)"/><circle cx="46" cy="28" r="1.5" fill="#fce7f3"/><circle cx="42" cy="42" r="4" fill="#fbbf24" filter="url(#glow)"/><circle cx="42" cy="42" r="1.5" fill="#fef3c7"/><circle cx="28" cy="46" r="4" fill="#8b5cf6" filter="url(#glow)"/><circle cx="28" cy="46" r="1.5" fill="#ede9fe"/><circle cx="14" cy="40" r="4" fill="#4ade80" filter="url(#glow)"/><circle cx="14" cy="40" r="1.5" fill="#dcfce7"/><circle cx="12" cy="26" r="4" fill="#e879f9" filter="url(#glow)"/><circle cx="12" cy="26" r="1.5" fill="#f5d0fe"/><circle cx="28" cy="28" r="6" fill="#166534" opacity="0.6"/><circle cx="28" cy="28" r="3" fill="#4ade80" filter="url(#glow)"/></svg>`,

    // trend: 每日经验趋势 (line chart)
    trend: `<svg viewBox="0 0 56 56" fill="none"><circle cx="28" cy="28" r="22" fill="#713f12" opacity="0.35"/><circle cx="28" cy="28" r="16" fill="#854d0e" opacity="0.2"/><path d="M14 42 L20 32 L26 36 L32 24 L38 28 L44 18" stroke="url(#g-trend)" stroke-width="2.5" fill="none" stroke-linecap="round" stroke-linejoin="round" filter="url(#glow)"/><circle cx="14" cy="42" r="2" fill="#facc15"/><circle cx="20" cy="32" r="2" fill="#facc15"/><circle cx="26" cy="36" r="2" fill="#facc15"/><circle cx="32" cy="24" r="2" fill="#facc15"/><circle cx="38" cy="28" r="2" fill="#facc15"/><circle cx="44" cy="18" r="3" fill="#fef3c7" filter="url(#glow)"/></svg>`,
};

/** Render a single stat card for Module 1 */
function renderProfileStatCard(iconSvg, value, label) {
    return `
        <div class="profile-stat-card">
            <div class="profile-stat-card__label"><span class="profile-stat-card__icon">${iconSvg}</span> ${label}</div>
            <div class="profile-stat-card__value">${value}</div>
        </div>
    `;
}

/**
 * Map EXP value to 0-5 heatmap level using linear scale
 * @param {number} exp - daily exp
 * @param {number} maxExp - max exp in the year
 * @param {number} minExp - min exp in the year
 */
function expToHeatmapLevel(exp, maxExp, minExp) {
    const range = maxExp - minExp || 1;
    const norm = (exp - minExp) / range;
    if (norm <= 0.05) return 0;
    if (norm <= 0.15) return 1;
    if (norm <= 0.35) return 2;
    if (norm <= 0.55) return 3;
    if (norm <= 0.75) return 4;
    return 5;
}

/** Render the yearly activity heatmap for Module 2 */
function renderYearlyHeatmap(activityData) {
    if (!activityData || activityData.length === 0) {
        return '<div class="profile-heatmap__empty" style="text-align:center;padding:40px;color:var(--color-muted)">暂无年度数据</div>';
    }
    const year = new Date().getFullYear();
    const firstDayOfWeek = new Date(year, 0, 1).getDay(); // 0=Sun
    const TOTAL_COLS = 53;
    const TOTAL_ROWS = 7;

    // Compute heatmap levels from exp values
    const expValues = activityData.map(d => d.exp);
    const maxExp = Math.max(...expValues);
    const minExp = Math.min(...expValues);

    // Build 2D grid: grid[row][col], row 0=Sun, col 0=first week
    const grid = Array.from({ length: TOTAL_ROWS }, () => Array(TOTAL_COLS).fill(null));
    // Use array to preserve month order: [month, firstCol]
    const monthColList = [];
    const seenMonths = new Set();

    for (let dayIndex = 0; dayIndex < 365; dayIndex++) {
        const item = activityData[dayIndex];
        const absoluteDay = firstDayOfWeek + dayIndex;
        const row = absoluteDay % 7;
        const col = Math.floor(absoluteDay / 7);
        grid[row][col] = item;

        const month = new Date(item.date).getMonth();
        if (!seenMonths.has(month)) {
            seenMonths.add(month);
            monthColList.push({ month, col });
        }
    }

    const MONTH_NAMES = ['1月', '2月', '3月', '4月', '5月', '6月', '7月', '8月', '9月', '10月', '11月', '12月'];

    // Render cells row-by-row → CSS Grid fills row-by-row, each column = one week
    const cellsHtml = [];
    for (let row = 0; row < TOTAL_ROWS; row++) {
        for (let col = 0; col < TOTAL_COLS; col++) {
            const cell = grid[row][col];
            if (!cell) {
                cellsHtml.push('<div class="profile-heatmap__cell profile-heatmap__cell--placeholder"></div>');
            } else {
                const level = expToHeatmapLevel(cell.exp, maxExp, minExp);
                const levelClass = ['empty', 'low', 'mid', 'high', 'peak', 'max'][level] || 'empty';
                const d = new Date(cell.date);
                const tooltip = `${d.getMonth() + 1}月${d.getDate()}日，EXP：${cell.exp}`;
                cellsHtml.push(`<div class="profile-heatmap__cell profile-heatmap__cell--${levelClass}" title="${tooltip}"></div>`);
            }
        }
    }

    // Month labels — monthColList is already in order (Jan→Dec by construction)
    const monthLabelsHtml = monthColList.map((mp, i) => {
        const nextCol = i < monthColList.length - 1 ? monthColList[i + 1].col : TOTAL_COLS;
        const spanCols = nextCol - mp.col;
        return `<span class="profile-heatmap__month-label" style="grid-column: ${mp.col + 1} / span ${spanCols}">${MONTH_NAMES[mp.month]}</span>`;
    }).join('');

    return `
        <div class="profile-heatmap__grid">
            ${cellsHtml.join('')}
        </div>
        <div class="profile-heatmap__months">
            ${monthLabelsHtml}
        </div>
    `;
}

/** Draw the dimension radar chart for Module 3
 *  Uses sqrt-like scaling: display = (raw / virtualMax)^0.55 * 100
 *  virtualMax = maxRaw * 1.15 — so the highest actual value never reaches
 *  the outer ring. This represents that growth never has a "ceiling".
 */
function drawProfileRadarChart() {
    const canvas = document.getElementById('profile-radar');
    if (!canvas) return;

    // 双重清理：Chart.js 注册表 + 自定义引用
    const existing = Chart.getChart(canvas);
    if (existing) existing.destroy();
    if (canvas._chart) {
        canvas._chart.destroy();
        canvas._chart = null;
    }

    const dims = AppData.profile.dimensions;
    const rawValues = dims.map(d => d.totalXp || d.xp);
    const maxRaw = Math.max(...rawValues);

    // Virtual max is ~15% above the actual max, so the highest point
    // sits around 85-93% of the outer ring — never "perfect"
    const HEADROOM = 1.15;
    const virtualMax = Math.ceil(maxRaw * HEADROOM / 50) * 50; // round to nearest 50
    const POWER = 0.55;
    const DISPLAY_MAX = 100;

    const displayValues = rawValues.map(v =>
        Math.round(Math.pow(v / virtualMax, POWER) * DISPLAY_MAX)
    );

    const labels = dims.map(d => d.name + ' Lv' + d.level);
    const colors = dims.map(d => d.color);

    // Build tick labels: reverse-map display → approximate raw
    const tickCount = 5;
    const displayTicks = [];
    const rawTickLabels = [];
    for (let i = 0; i <= tickCount; i++) {
        const displayVal = Math.round((i / tickCount) * DISPLAY_MAX);
        displayTicks.push(displayVal);
        const rawVal = Math.round(Math.pow(displayVal / DISPLAY_MAX, 1 / POWER) * virtualMax);
        rawTickLabels.push(rawVal);
    }

    canvas._chart = new Chart(canvas.getContext('2d'), {
        type: 'radar',
        data: {
            labels: labels,
            datasets: [{
                label: '维度经验',
                data: displayValues,
                backgroundColor: 'rgba(212, 154, 62, 0.2)',
                borderColor: 'rgba(212, 154, 62, 0.75)',
                borderWidth: 2,
                pointBackgroundColor: colors,
                pointBorderColor: colors,
                pointBorderWidth: 2,
                pointRadius: 5,
                pointHoverRadius: 7,
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            scales: {
                r: {
                    beginAtZero: true,
                    max: DISPLAY_MAX,
                    min: 0,
                    ticks: {
                        stepSize: DISPLAY_MAX / tickCount,
                        color: 'rgba(255,255,255,0.3)',
                        backdropColor: 'transparent',
                        font: { size: 10 },
                        callback: (val) => {
                            const idx = displayTicks.indexOf(val);
                            return idx >= 0 ? rawTickLabels[idx] : '';
                        },
                    },
                    grid: {
                        color: 'rgba(255,255,255,0.08)',
                    },
                    pointLabels: {
                        color: 'rgba(255,255,255,0.7)',
                        font: { size: 11, family: "'PingFang SC', 'Microsoft YaHei', sans-serif" },
                    },
                },
            },
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: (ctx) => {
                            const d = dims[ctx.dataIndex];
                            return d.name + ' Lv' + d.level + ': ' + (d.totalXp || d.xp).toLocaleString() + ' EXP';
                        },
                    },
                },
            },
        },
    });
}

/** Main render function for the History/Profile page */
async function renderHistory() {
    // 尝试从后端加载数据
    let profile = AppData.profile;
    let yearlyActivity = null;
    const uid = AppData.user?.id || 1;

    try {
        const profileData = await fetchProfileStats(uid);
        if (profileData) {
            profile = profileData;
            AppData.profile = profileData;
        }

        const yearData = await fetchYearlyActivity(uid);
        if (yearData && yearData.days) {
            yearlyActivity = yearData.days;
            AppData.profile.yearlyActivity = yearData.days;
        }
    } catch (e) {
        console.warn('后端不可用，使用前端降级数据:', e);
    }

    // 降级：如果后端没有数据，用 AppData 中的默认值
    const p = profile;
    const yData = yearlyActivity || AppData.profile.yearlyActivity || [];

    const html = `
        <div class="page-header page-header--with-icon">
            <div class="page-header__icon" style="width:58px;height:58px">${HIST_ICONS.title}</div>
            <div>
                <h1 class="page-header__title">成长记录</h1>
                <p class="page-header__subtitle">查看你的成长统计与维度分析</p>
            </div>
        </div>

        <!-- Module 1: Top Stats Cards -->
        <div class="profile-stats-grid">
            ${renderProfileStatCard(HIST_ICONS.days, p.effortDays, '努力天数')}
            ${renderProfileStatCard(HIST_ICONS.xp, (p.totalXP || 0).toLocaleString(), '累计获得EXP')}
            ${renderProfileStatCard(HIST_ICONS.checkins, p.habitCheckins || 0, '习惯打卡次数')}
            ${renderProfileStatCard(HIST_ICONS.tasks, p.tasksCompleted || 0, '完成任务数')}
            ${renderProfileStatCard(HIST_ICONS.goals, p.goalsAchieved || 0, '达成目标')}
            ${renderProfileStatCard(HIST_ICONS.rewards, p.rewardsUnlocked || 0, '解锁奖励')}
        </div>

        <!-- Module 2: Yearly Activity Heatmap -->
        <div class="profile-heatmap">
            <div class="profile-heatmap__header">
                <span class="section__title section__title--with-icon" style="margin-bottom:0">${HIST_ICONS.heatmap} 年度活跃热力图</span>
                <button class="btn btn--ghost btn--sm" onclick="navigateTo('action')">开始记录</button>
            </div>
            ${yData.length > 0 ? renderYearlyHeatmap(yData) : '<div class="profile-heatmap__empty" style="text-align:center;padding:40px;color:var(--color-muted)">暂无数据，开始记录行动吧</div>'}
            <div class="profile-heatmap__legend">
                <span>少</span>
                <div class="profile-heatmap__cell profile-heatmap__cell--empty"></div>
                <div class="profile-heatmap__cell profile-heatmap__cell--low"></div>
                <div class="profile-heatmap__cell profile-heatmap__cell--mid"></div>
                <div class="profile-heatmap__cell profile-heatmap__cell--high"></div>
                <div class="profile-heatmap__cell profile-heatmap__cell--peak"></div>
                <div class="profile-heatmap__cell profile-heatmap__cell--max"></div>
                <span>多</span>
            </div>
        </div>

        <!-- Module 3 & 4: Side by Side -->
        <div class="profile-bottom-grid">
            <!-- Module 3: Dimension Radar Chart -->
            <div class="profile-radar-card">
                <div class="section__title section__title--with-icon">${HIST_ICONS.radar} 维度雷达图</div>
                <div class="radar-chart-container" style="max-width:380px">
                    <canvas id="profile-radar"></canvas>
                </div>
            </div>

            <!-- Module 4: Dimension XP Bars -->
            <div class="profile-bars-card">
                <div class="section__title section__title--with-icon">${HIST_ICONS.rank} 维度经验</div>
                ${(p.dimensions || []).map(d => {
                    const rawPct = Math.round((d.xp / (d.xpToNext || 1)) * 100);
                    const pct = d.level >= 120 ? 100 : Math.min(rawPct, 100);
                    const remaining = d.level >= 120 ? 0 : Math.max(0, (d.xpToNext || 150) - d.xp);
                    const nextLv = d.level >= 120 ? d.level : d.level + 1;
                    const tooltip = d.level >= 120
                        ? `已达最高等级 Lv${d.level}`
                        : `升级进度 ${pct}% · 还需 ${remaining} EXP 升至 Lv${nextLv}`;
                    return `
                        <div class="profile-bar" title="${tooltip}">
                            <div class="profile-bar__header">
                                <span class="profile-bar__icon">${attrIcon(d.key, 20)}</span>
                                <span class="profile-bar__name">${d.name}</span>
                                <span class="profile-bar__level">Lv${d.level}</span>
                            </div>
                            <div class="profile-bar__track">
                                <div class="profile-bar__track-bg" style="background:${d.color}22"></div>
                                <div class="profile-bar__fill" style="width:${pct}%; background:${d.color}"></div>
                            </div>
                            <span class="profile-bar__xp">${Math.round(d.xp).toLocaleString()} EXP</span>
                        </div>
                    `;
                }).join('')}
            </div>
        </div>

        <!-- Module 5: Daily EXP Trend Line Chart -->
        <div class="profile-trend-card" style="margin-top:24px">
            <div class="profile-trend__header">
                <span class="section__title section__title--with-icon" style="margin-bottom:0">${HIST_ICONS.trend} 每日经验趋势</span>
                <div class="profile-trend__tabs">
                    <button class="profile-trend__tab profile-trend__tab--active" onclick="switchTrendRange(7)">近7天</button>
                    <button class="profile-trend__tab" onclick="switchTrendRange(15)">近15天</button>
                    <button class="profile-trend__tab" onclick="switchTrendRange(30)">近30天</button>
                    <button class="profile-trend__tab" onclick="switchTrendRange(90)">近90天</button>
                    <button class="profile-trend__tab" onclick="switchTrendRange(365)">近1年</button>
                </div>
            </div>
            <div class="profile-trend__chart">
                <canvas id="trend-chart"></canvas>
            </div>
        </div>
    `;

    document.getElementById('page-history').innerHTML = html;

    setTimeout(() => {
        drawProfileRadarChart();
        drawTrendChart(7);
    }, 100);
}

let trendRange = 7;

async function switchTrendRange(days) {
    trendRange = days;
    // Update active tab
    document.querySelectorAll('.profile-trend__tab').forEach(tab => {
        tab.classList.toggle('profile-trend__tab--active', parseInt(tab.textContent.match(/\d+/)?.[0] || '0') === days || (days === 365 && tab.textContent.includes('1年')));
    });
    await drawTrendChart(days);
}

async function drawTrendChart(days) {
    const canvas = document.getElementById('trend-chart');
    if (!canvas) return;
    // 安全销毁已有图表（双重保险）
    try {
        const existing = Chart.getChart(canvas);
        if (existing) existing.destroy();
    } catch (e) { /* ignore */ }
    try {
        if (canvas._chart) canvas._chart.destroy();
    } catch (e) { /* ignore */ }
    canvas._chart = null;

    // 从后端加载数据
    let data = [];
    const uid = AppData.user?.id || 1;
    try {
        const result = await fetchDailyExp(uid, days);
        if (result && result.days) {
            data = result.days;
        }
    } catch (e) {
        console.warn('获取每日经验趋势失败:', e);
    }

    // 降级：如果后端没有数据，显示空状态提示
    if (!data || data.length === 0) {
        const container = canvas.parentElement;
        if (container) {
            container.innerHTML = '<div class="profile-heatmap__empty" style="text-align:center;padding:40px;color:var(--color-muted)">暂无数据，开始记录行动后趋势图将在此展示</div>';
        }
        return;
    }
    const labels = data.map(d => {
        const parts = d.date.split('-');
        return parts[1] + '/' + parts[2];
    });
    const values = data.map(d => d.exp);

    canvas._chart = new Chart(canvas.getContext('2d'), {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: '每日EXP',
                data: values,
                borderColor: 'rgba(212, 154, 62, 0.85)',
                backgroundColor: 'rgba(212, 154, 62, 0.08)',
                borderWidth: 2,
                fill: true,
                tension: 0.35,
                pointRadius: days > 60 ? 0 : 3,
                pointHoverRadius: 6,
                pointBackgroundColor: 'rgba(212, 154, 62, 1)',
                pointBorderColor: 'rgba(212, 154, 62, 1)',
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: {
                intersect: false,
                mode: 'index',
            },
            scales: {
                x: {
                    ticks: {
                        color: 'rgba(255,255,255,0.3)',
                        font: { size: 10 },
                        maxTicksLimit: days > 60 ? 12 : days > 15 ? 10 : 7,
                    },
                    grid: {
                        color: 'rgba(255,255,255,0.05)',
                    },
                },
                y: {
                    beginAtZero: true,
                    ticks: {
                        color: 'rgba(255,255,255,0.3)',
                        font: { size: 10 },
                        callback: (v) => v + ' EXP',
                    },
                    grid: {
                        color: 'rgba(255,255,255,0.06)',
                    },
                },
            },
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        title: (ctx) => {
                            const idx = ctx[0].dataIndex;
                            return data[idx].date;
                        },
                        label: (ctx) => ctx.raw + ' EXP',
                    },
                },
            },
        },
    });
}
