/* ================================================================
   Attributes Page — 属性详情表
   ================================================================ */

// 属性介绍文案（纯展示，不来自后端）
const ATTR_INTROS = {
    health:   { notes: '运动、睡眠、饮食、冥想',          description: '衡量你的身体状态和生活习惯。通过规律运动、充足睡眠、均衡饮食和日常冥想积累经验。健康的身体是一切成长的基础，没有好身体其他维度都会受影响。' },
    study:    { notes: '读书、课程、研究、刷信息',        description: '衡量你的知识输入和认知提升。读书、上课程、研究课题、刷高质量信息流都属于学习范畴。学习是认知升级的核心引擎，决定你思考和解决问题的能力上限。' },
    relation: { notes: '家人、朋友、社交、社群维护',      description: '衡量你的人际连接质量。包括陪伴家人、维系朋友关系、参与社交活动和社群维护。人是社会性动物，良好的关系网络提供情感支持和机会资源。' },
    work:     { notes: '本职工作、项目推进、任务执行',    description: '衡量你的职业产出和项目推进能力。包括本职工作完成度、项目里程碑推进、任务执行效率。工作维度直接关联收入增长和职业发展，是现实世界价值创造的主战场。' },
    create:   { notes: '写作、出内容、做模板、录视频',    description: '衡量你的内容输出和创造能力。写作、出内容、做模板、录视频等创造性活动都属于这个维度。创作是把输入转化为输出的过程，也是建立个人品牌和影响力的关键路径。' },
    finance:  { notes: '记账、理财、副业变现相关',        description: '衡量你的财务管理能力。包括记账习惯、理财规划、副业变现等。财务健康给你选择权和自由度，是支撑其他维度发展的重要资源基础。' },
    hobby:    { notes: '游戏、音乐、旅行、纯放松',        description: '衡量你的生活丰富度和幸福感。游戏、音乐、旅行、各种纯放松活动都属于爱好。爱好不是浪费时间，而是给大脑充电、保持创造力和生活热情的重要方式。' },
    soul:     { notes: '穿搭、气质、社交表达、个人形象',  description: '衡量你的个人魅力和社交吸引力。穿搭品味、气质修养、谈吐举止、社交表达都是魅力的体现。魅力维度决定了你在社交场合中的影响力、给人留下的第一印象，以及自信从容地展现自我的能力。' },
};

async function renderAttributes() {
    // 优先从 AppData.profile 读取（已在 app.js 启动时加载），避免重复请求
    let dims = (AppData.profile && AppData.profile.dimensions) || [];

    // 数据缺失时尝试从后端拉取
    if (dims.length === 0 && AppData.user && AppData.user.id) {
        const result = await fetchProfileStats(AppData.user.id);
        if (result && result.dimensions) {
            dims = result.dimensions;
            AppData.profile = result;
        }
    }

    const rows = dims.map((d, i) => {
        const currentXp = d.xp || 0;
        const xpToNext = d.xpToNext || 1;
        const pct = xpToNext > 0 ? Math.round((currentXp / xpToNext) * 100) : 100;
        const displayPct = d.level >= 120 ? 100 : Math.min(pct, 100);
        const num = i + 1;
        const intro = ATTR_INTROS[d.key] || { notes: '', description: '' };

        return `
            <tr class="attr-row">
                <td class="attr-cell attr-cell--num">
                    <span class="attr-num">${num}</span>
                </td>
                <td class="attr-cell attr-cell--name">
                    <span class="attr-name-icon">${attrIcon(d.key, 22)}</span>
                    <span class="attr-name-text">${d.name}</span>
                </td>
                <td class="attr-cell attr-cell--lv">
                    <span class="attr-lv" style="background:${d.color}22;color:${d.color}">Lv${d.level}</span>
                </td>
                <td class="attr-cell attr-cell--xp">${Math.round(d.xp)}</td>
                <td class="attr-cell attr-cell--xp">${d.totalXp ? d.totalXp.toLocaleString() : Math.round(d.xp)}</td>
                <td class="attr-cell attr-cell--xp">${d.xpToNext}</td>
                <td class="attr-cell attr-cell--progress">
                    <div class="attr-progress">
                        <div class="attr-progress__bar">
                            <div class="attr-progress__fill" style="width:${displayPct}%;background:${d.color}"></div>
                        </div>
                        <span class="attr-progress__text">${displayPct}%</span>
                    </div>
                </td>
                <td class="attr-cell attr-cell--notes" title="${escapeHtml(intro.notes)}">${intro.notes}</td>
            </tr>
        `;
    }).join('');

    const introCards = dims.map((d, i) => {
        const intro = ATTR_INTROS[d.key] || { notes: '', description: '' };
        return `
            <div class="attr-intro-card">
                <div class="attr-intro-card__header">
                    <span class="attr-intro-card__icon">${attrIcon(d.key, 28)}</span>
                    <span class="attr-intro-card__name">${d.name}</span>
                    <span class="attr-intro-card__tagline">${escapeHtml(intro.notes)}</span>
                </div>
                <p class="attr-intro-card__desc">${escapeHtml(intro.description)}</p>
            </div>
        `;
    }).join('');

    const html = `
        <div class="page-header page-header--with-icon">
            <div class="page-header__icon" style="width:58px;height:58px">${HEADER_ICONS.attributes}</div>
            <div>
                <h1 class="page-header__title">属性面板</h1>
                <p class="page-header__subtitle">8大生活维度，全面追踪成长进度</p>
            </div>
        </div>

        ${dims.length === 0 ? `
            <div class="empty-state">
                <div style="font-size:48px;margin-bottom:12px">📊</div>
                <div class="empty-state__title">暂无数据</div>
                <div class="empty-state__desc">开始记录行动后，维度数据将在这里展示</div>
            </div>
        ` : `
            <div class="card attr-table-card">
                <div class="attr-table-wrap">
                    <table class="attr-table">
                        <thead>
                            <tr class="attr-head-row">
                                <th class="attr-th attr-th--num">#</th>
                                <th class="attr-th">🔤 属性</th>
                                <th class="attr-th attr-th--lv">🏆 等级</th>
                                <th class="attr-th attr-th--xp">∑ 本级已获</th>
                                <th class="attr-th attr-th--xp">∑ 累计EXP</th>
                                <th class="attr-th attr-th--xp">↑ 升级所需</th>
                                <th class="attr-th attr-th--progress">📊 升级进度</th>
                                <th class="attr-th">📝 备注</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${rows}
                        </tbody>
                    </table>
                </div>
            </div>

            <div class="attr-intro-section">
                <h2 class="attr-intro-section__title">📋 属性详情介绍</h2>
                <div class="attr-intro-grid">
                    ${introCards}
                </div>
            </div>
        `}
    `;

    document.getElementById('page-attributes').innerHTML = html;
}