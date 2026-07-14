/* ================================================================
   Components — 可复用组件渲染函数
   ================================================================ */

/** Render stat card */
function renderStatCard(icon, value, label, trend, trendUp) {
    const trendHtml = trend !== undefined
        ? `<div class="stat-card__trend stat-card__trend--${trendUp ? 'up' : 'down'}">${trendUp ? '↑' : '↓'} ${Math.abs(trend)}% vs 昨日</div>`
        : '';
    const isSvg = typeof icon === 'string' && icon.startsWith('<svg');
    return `
        <div class="card stat-card">
            <div class="stat-card__icon stat-card__icon--primary">
                ${isSvg ? icon : `<span style="font-size:22px">${icon}</span>`}
            </div>
            <div class="stat-card__info">
                <div class="stat-card__value">${value}</div>
                <div class="stat-card__label">${label}</div>
                ${trendHtml}
            </div>
        </div>
    `;
}

/** Render progress bar */
function renderProgress(value, max, variant = 'primary', showText = true) {
    const pct = max > 0 ? Math.min(Math.round((value / max) * 100), 100) : 0;
    return `
        <div>
            ${showText ? `<div style="display:flex;justify-content:space-between;margin-bottom:6px;font-size:12px">
                <span style="color:var(--color-text-muted)">进度</span>
                <span style="font-weight:600">${pct}%</span>
            </div>` : ''}
            <div class="progress">
                <div class="progress__fill progress__fill--${variant}" style="width:${pct}%"></div>
            </div>
        </div>
    `;
}

/** Render exp bar — 等级系统全面改造版
 *  布局：[左侧渐变方块 | Lv.XX] [段位称呼] [渐变进度条] [EXP数值]
 *  配色按段位分10阶段，Lv.200满级有专属高光特效
 */
function renderExpBar(current, max, level, levelIcon) {
    const pct = max > 0 ? Math.min(Math.round((current / max) * 100), 100) : 0;
    const rank = getRankInfo(level);
    const theme = getLevelTheme(level);
    const isMaxLevel = level >= MAX_LEVEL;
    const remaining = max - current;

    const iconHtml = levelIcon
        ? `<span style="display:inline-flex;vertical-align:middle;margin-right:4px">${levelIcon}</span>`
        : '';

    return `
        <div class="card exp-card ${isMaxLevel ? 'exp-card--max' : ''}">
            <div class="exp-card__inner">
                <!-- 左侧等级方块 -->
                <div class="exp-card__lv-block" style="background:${theme.block}">
                    <span class="exp-card__lv-num">Lv.</span>
                    <span class="exp-card__lv-val">${level}</span>
                </div>
                <!-- 右侧信息区 -->
                <div class="exp-card__info">
                    <div class="exp-card__rank-row">
                        <span class="exp-card__rank" style="color:${theme.accent}">${rank.name}</span>
                        ${isMaxLevel ? '<span class="exp-card__max-badge">MAX</span>' : ''}
                    </div>
                    <div class="exp-card__bar" style="background:${theme.barBg}">
                        <div class="exp-card__bar-fill ${isMaxLevel ? 'exp-card__bar-fill--max' : ''}"
                             style="width:${pct}%;background:${theme.bar}">
                        </div>
                    </div>
                    <div class="exp-card__meta">
                        <span class="exp-card__exp-text">${current.toLocaleString()} / ${max.toLocaleString()} EXP</span>
                        ${isMaxLevel ? `
                            <span class="exp-card__max-text">🏆 满级达成</span>
                        ` : `
                            <span class="exp-card__remaining">还需 ${remaining.toLocaleString()} EXP 升级</span>
                        `}
                    </div>
                </div>
            </div>
        </div>
    `;
}
