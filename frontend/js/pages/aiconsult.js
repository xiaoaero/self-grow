/* ================================================================
   AI 资讯 — 顶栏滑块切换两个视图：
     · 资讯     —— GitHub 趋势（左 3/4）+ 国内/国际 AI 资讯（右 1/4）
     · AI 分析  —— 由大模型把每日资讯归纳成结论与建议（规划中）

   数据由后端定时任务落库，本页只读展示。
   - GitHub：一行两张横向卡片（名称 / 简介 / 底部 星标+语言），可纵向拉伸
   - 资讯：一行一条，新闻体（标题 / 摘要 / 来源）；每块默认只露 5 条，超出上下滚动
   - 右侧两个框可拖拽互换顺序 —— **不持久化**，刷新 / 离开页面即回默认
   - 整页完全没数据时，资讯视图显示空状态 + 「立即刷新」按钮
   ================================================================ */

let AICONSULT_DATA = null;

/* 顶栏图标（内联 SVG，配色跟暖色主题；HEADER_ICONS 里没有资讯类的，所以自带一个） */
const AIC_HEADER_ICON = `<svg viewBox="0 0 58 58" fill="none">
  <circle cx="29" cy="29" r="28" fill="#123a33"/>
  <circle cx="29" cy="29" r="28" fill="none" stroke="#4A9C6C" stroke-width="0.85" opacity="0.3"/>
  <rect x="13.5" y="17" width="23" height="25" rx="2.6" fill="#e8f5ee"/>
  <rect x="13.5" y="17" width="23" height="6.2" rx="2.6" fill="#4A9C6C"/>
  <rect x="13.5" y="20.4" width="23" height="2.8" fill="#4A9C6C"/>
  <line x1="17.6" y1="28.6" x2="32.4" y2="28.6" stroke="#357A4F" stroke-width="1.5" stroke-linecap="round" opacity="0.65"/>
  <line x1="17.6" y1="32.7" x2="32.4" y2="32.7" stroke="#357A4F" stroke-width="1.5" stroke-linecap="round" opacity="0.45"/>
  <line x1="17.6" y1="36.8" x2="26.4" y2="36.8" stroke="#357A4F" stroke-width="1.5" stroke-linecap="round" opacity="0.3"/>
  <path d="M42.6 13 L44.3 18.4 L49.7 20.1 L44.3 21.8 L42.6 27.2 L40.9 21.8 L35.5 20.1 L40.9 18.4 Z" fill="#D49A3E"/>
  <circle cx="44.6" cy="35.6" r="2.1" fill="#6DBD8A"/>
  <circle cx="41" cy="41.6" r="1.4" fill="#D49A3E" opacity="0.85"/>
</svg>`;

const AIC_EMPTY_ICON = `<svg viewBox="0 0 64 64" fill="none">
  <circle cx="32" cy="32" r="30" stroke="rgba(255,255,255,0.13)" stroke-width="1.5" stroke-dasharray="4 5"/>
  <path d="M32 19 L32 39" stroke="#4A9C6C" stroke-width="2.6" stroke-linecap="round"/>
  <path d="M24 32 L32 40 L40 32" stroke="#4A9C6C" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/>
</svg>`;

/* ── API ─────────────────────────────────────────────────────── */

function aiApiBase() {
    // 兜底必须与 auth.js 的兜底一致（localhost:3001）：auth.js 包装了 window.fetch，
    // 靠「URL 以 API_BASE 开头」来判断是否补 Authorization 头。若这里用 127.0.0.1，
    // 而 config.js 又没加载成功（auth.js 回落 localhost），前缀对不上 → 不补 token → 401。
    return window.__SELF_GROW_API_BASE__ || 'http://localhost:3001';
}
async function aiApiGet(path) {
    const r = await fetch(aiApiBase() + path);
    if (!r.ok) throw new Error('API ' + r.status);
    return r.json();
}
async function aiApiPost(path) {
    const r = await fetch(aiApiBase() + path, { method: 'POST' });
    if (!r.ok) throw new Error('API ' + r.status);
    return r.json();
}

/* ── 小工具 ───────────────────────────────────────────────────── */

function escapeHtml(s) {
    return String(s == null ? '' : s)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}
function truncate(s, n) {
    s = s || '';
    return s.length > n ? s.slice(0, n) + '…' : s;
}
/** 星数紧凑显示：1234 → 1.2k，12345 → 12k */
function formatStars(n) {
    n = Number(n) || 0;
    if (n >= 10000) return Math.round(n / 1000) + 'k';
    if (n >= 1000) return (n / 1000).toFixed(1) + 'k';
    return String(n);
}
/** batch_time（2026-09-22 01:30:00）→ 09-22 01:30 */
function fmtBatch(t) {
    if (!t) return '';
    const m = String(t).match(/(\d{4})-(\d{2})-(\d{2})[ T](\d{2}:\d{2})/);
    return m ? `${m[2]}-${m[3]} ${m[4]}` : String(t);
}
/** 语言色点（GitHub 风格） */
const LANG_COLORS = {
    Python: '#3572A5', JavaScript: '#f1e05a', TypeScript: '#3178c6', Go: '#00ADD8',
    Rust: '#dea584', Java: '#b07219', 'C++': '#f34b7d', C: '#8a8a8a', 'C#': '#178600',
    Shell: '#89e051', HTML: '#e34c26', CSS: '#563d7c', 'Jupyter Notebook': '#DA5B0B',
    Ruby: '#701516', PHP: '#4F5D95', Swift: '#F05138', Kotlin: '#A97BFF', Dart: '#00B4AB',
    Vue: '#41b883', Svelte: '#ff3e00', Zig: '#ec915c', Lua: '#3f7ec2', Scala: '#c22d40',
    'Objective-C': '#438eff', Perl: '#0298c3', R: '#198CE7', Haskell: '#5e5086'
};
function langColor(l) { return LANG_COLORS[l] || 'rgba(255,255,255,0.45)'; }

/* ── 卡片 ─────────────────────────────────────────────────────── */

/** GitHub 卡片：名称 / 简介 /（留白）/ 底部 星标 + 语言 */
function ghCard(it) {
    const meta = (it.meta && typeof it.meta === 'object') ? it.meta : {};
    const lang = meta.language || '';
    const desc = it.summary
        ? escapeHtml(truncate(it.summary, 160))
        : '<span class="gh-card__nodesc">暂无简介</span>';
    const langHtml = lang
        ? `<span class="gh-card__lang"><i style="background:${langColor(lang)}"></i>${escapeHtml(lang)}</span>`
        : '';
    return `<a class="gh-card" href="${escapeHtml(it.url || '#')}" target="_blank" rel="noopener">
        <div class="gh-card__title" title="${escapeHtml(it.title || '')}">${escapeHtml(it.title || '未命名')}</div>
        <p class="gh-card__desc">${desc}</p>
        <div class="gh-card__meta">
            <span class="gh-card__stars">★ ${formatStars(it.stars)}</span>
            ${langHtml}
        </div>
    </a>`;
}

/** 资讯卡片：新闻体（标题 / 摘要 / 来源域名） */
function newsCard(it) {
    const url = it.url || '#';
    let host = '';
    try { host = new URL(url).hostname.replace(/^www\./, ''); } catch (e) { host = ''; }
    const desc = it.summary ? `<div class="news-item__desc">${escapeHtml(truncate(it.summary, 150))}</div>` : '';
    const src = host ? `<span class="news-item__src">${escapeHtml(host)}</span>` : '<span></span>';
    return `<a class="news-item" href="${escapeHtml(url)}" target="_blank" rel="noopener">
        <div class="news-item__title">${escapeHtml(it.title || '未命名')}</div>
        ${desc}
        <div class="news-item__foot">${src}<span class="news-item__arrow">↗</span></div>
    </a>`;
}

function aiEmpty(msg) {
    return `<div class="ai-box__empty">${escapeHtml(msg || '暂无数据')}</div>`;
}

/* ── 布局 ─────────────────────────────────────────────────────── */

function getAIConsultLayout() {
    return `
    <style>
      .aic__wrap { padding: 4px 2px; }

      /* 顶栏滑块 —— 视觉参考「表达训练」的 .expr__tabs，但：
         ① 用独立类名（.aic__tab*），避免和表达训��页全局 .expr__tab 选择器互相干扰；
         ② 滑块底色用**已定义**的变量（表达训练那边的 --color-bg-secondary 在 :root 里
            根本没定义 → 那块高亮其实是透明的，选中态只剩文字变亮）。 */
      .aic__tabs { position:relative; display:flex; flex-shrink:0; gap:2px; padding:3px;
                   background:var(--glass-bg); border:1px solid var(--glass-border);
                   border-radius:10px; cursor:pointer; }
      .aic__tab { position:relative; z-index:2; padding:7px 22px; font-size:13px; font-weight:600;
                  color:var(--color-text-muted); border-radius:8px; user-select:none;
                  transition:color .3s ease; }
      .aic__tab.aic__tab--active { color:var(--color-text-primary); }
      .aic__tab-slider { position:absolute; z-index:1; top:3px; bottom:3px; left:3px;
                         width:calc(50% - 3px); border-radius:7px;
                         background:var(--color-bg-high); box-shadow:0 1px 3px rgba(0,0,0,.35);
                         transition:transform .3s cubic-bezier(.4,0,.2,1); }
      .aic__tabs[data-active="analysis"] .aic__tab-slider { transform:translateX(100%); }

      /* 视图 */
      .aic__view { display:none; }
      .aic__view.aic__view--active { display:block; }

      /* 空状态（整页无数据时替代网格） */
      .aic__empty-all { display:flex; flex-direction:column; align-items:center; justify-content:center;
                        gap:10px; padding:70px 20px; text-align:center;
                        background:var(--color-bg-elevated); border:1px dashed var(--color-border);
                        border-radius:var(--radius-lg); }
      .aic__empty-all svg { width:64px; height:64px; }
      .aic__empty-all-title { font-size:16px; font-weight:700; color:var(--color-text-primary); }
      .aic__empty-all-sub { font-size:13px; color:var(--color-text-muted); }
      .aic__refresh { margin-top:14px; padding:8px 22px; border-radius:var(--radius-full);
                      border:1px solid var(--color-primary); background:var(--color-primary-bg);
                      color:var(--color-primary-light); cursor:pointer; font-size:13px;
                      font-weight:600; transition:var(--transition-fast); }
      .aic__refresh:hover { background:var(--color-primary); color:#fff; }
      .aic__refresh:disabled { opacity:.55; cursor:default; }

      /* 左 3/4 GitHub · 右 1/4 资讯 */
      .aic__body { display:grid; grid-template-columns:3fr 1fr; gap:18px; align-items:start; }
      .aic__side { display:flex; flex-direction:column; gap:18px; min-width:0; }

      /* 框 */
      .ai-box { background:var(--color-bg-elevated); border:1px solid var(--color-border);
                border-radius:var(--radius-lg); padding:16px 16px 14px; min-width:0;
                resize:vertical; overflow:auto; box-shadow:var(--shadow-sm); }
      .ai-box__head { display:flex; align-items:center; gap:8px; margin-bottom:14px; }
      .ai-box__title { font-size:15px; font-weight:700; color:var(--color-text-primary);
                       display:flex; align-items:center; gap:9px; }
      .ai-box__title::before { content:''; width:3px; height:15px; border-radius:2px;
                               background:linear-gradient(180deg, var(--color-primary), var(--color-accent)); }
      .ai-box__sub { margin-left:auto; font-size:11.5px; color:var(--color-text-muted); white-space:nowrap; }
      .ai-box--dragging { opacity:.45; }

      /* Tab（本周 / 今日） */
      .ai-box__tabs { display:flex; gap:8px; margin-bottom:14px; }
      .ai-tab { padding:5px 15px; border-radius:var(--radius-full);
                border:1px solid var(--color-border); background:transparent;
                color:var(--color-text-secondary); cursor:pointer; font-size:12.5px;
                transition:var(--transition-fast); }
      .ai-tab:hover { color:var(--color-text-primary); border-color:rgba(255,255,255,.22); }
      .ai-tab.active { background:var(--color-primary-bg); color:var(--color-primary-light);
                       border-color:var(--color-primary); font-weight:600; }

      /* GitHub：一行两张，横向长方形 */
      .gh-grid { display:grid; grid-template-columns:1fr 1fr; gap:12px; }
      .gh-card { position:relative; display:flex; flex-direction:column; min-height:142px;
                 padding:14px 15px; overflow:hidden; text-decoration:none;
                 background:var(--color-bg-surface); border:1px solid var(--color-border-light);
                 border-radius:var(--radius-md);
                 transition:transform var(--transition-fast), border-color var(--transition-fast),
                            box-shadow var(--transition-fast); }
      .gh-card::after { content:''; position:absolute; left:0; right:0; top:0; height:2px;
                        background:linear-gradient(90deg, var(--color-primary), var(--color-accent));
                        opacity:0; transition:opacity var(--transition-fast); }
      .gh-card:hover { transform:translateY(-3px); border-color:var(--color-primary);
                       box-shadow:var(--shadow-md); }
      .gh-card:hover::after { opacity:1; }
      .gh-card__title { font-size:14px; font-weight:700; color:var(--color-text-primary);
                        white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
      .gh-card__desc { flex:1 1 auto; margin:9px 0 0; font-size:12.5px; line-height:1.62;
                       color:var(--color-text-secondary);
                       display:-webkit-box; -webkit-line-clamp:3; -webkit-box-orient:vertical;
                       overflow:hidden; }
      .gh-card__nodesc { color:var(--color-text-muted); font-style:italic; }
      .gh-card__meta { display:flex; align-items:center; gap:16px; margin-top:14px;
                       padding-top:11px; border-top:1px solid var(--color-border-light);
                       font-size:12px; color:var(--color-text-muted); }
      .gh-card__stars { color:var(--color-accent); font-weight:600; }
      .gh-card__lang { display:inline-flex; align-items:center; gap:6px; }
      .gh-card__lang i { width:9px; height:9px; border-radius:50%; display:inline-block; }

      /* 资讯框：默认只露 5 条，超出上下滚动（高度由 JS 按实测量算了 5 条的高度）。
         所以这两个框不参与 resize，滚动条只做一层（在 .news-list 上）。 */
      .ai-box[data-box="domestic"], .ai-box[data-box="international"] { resize:none; overflow:hidden; }

      /* 资讯：一行一条，新闻体 */
      .news-list { display:flex; flex-direction:column; position:relative; overflow-y:auto; }
      .news-item { display:block; padding:11px 13px; text-decoration:none; border-radius:var(--radius-sm);
                   border-left:2px solid transparent;
                   transition:background var(--transition-fast), border-color var(--transition-fast); }
      .news-item + .news-item { border-top:1px solid var(--color-border-light); }
      .news-item:hover { background:var(--color-primary-bg); border-left-color:var(--color-primary); }
      .news-item__title { font-size:13.5px; font-weight:600; line-height:1.5;
                          color:var(--color-text-primary); transition:color var(--transition-fast);
                          display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical;
                          overflow:hidden; }
      .news-item:hover .news-item__title { color:var(--color-primary-light); }
      .news-item__desc { margin-top:6px; font-size:12px; line-height:1.58;
                         color:var(--color-text-secondary);
                         display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical;
                         overflow:hidden; }
      .news-item__foot { display:flex; align-items:center; gap:6px; margin-top:8px;
                         font-size:11px; color:var(--color-text-muted); }
      .news-item__src { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
      .news-item__arrow { margin-left:auto; opacity:0;
                          transition:opacity var(--transition-fast), transform var(--transition-fast); }
      .news-item:hover .news-item__arrow { opacity:1; transform:translate(2px,-2px); }

      /* 空态 / 提示 */
      .ai-box__empty { color:var(--color-text-muted); font-size:13px; padding:30px 0; text-align:center; }
      .ai-box__hint { font-size:12px; color:var(--color-accent-light); padding:9px 11px;
                      background:var(--color-accent-bg); border:1px solid rgba(212,154,62,.28);
                      border-radius:var(--radius-sm); margin-bottom:12px; }
      .ai-box__hint code { background:rgba(0,0,0,.3); padding:1px 5px; border-radius:4px; }

      /* ── AI 分析 ── */
      .aic__an { display:flex; flex-direction:column; gap:16px; }
      .aic__card { background:var(--color-bg-elevated); border:1px solid var(--color-border);
                   border-radius:var(--radius-lg); padding:16px 18px; box-shadow:var(--shadow-sm); }
      .aic__card-head { display:flex; align-items:center; gap:10px; margin-bottom:12px; }
      .aic__card-title { font-size:15px; font-weight:700; color:var(--color-text-primary);
                         display:flex; align-items:center; gap:9px; }
      .aic__card-title::before { content:''; width:3px; height:15px; border-radius:2px;
                                 background:linear-gradient(180deg,var(--color-primary),var(--color-accent)); }
      .aic__brief-date { margin-left:auto; font-size:12px; color:var(--color-text-muted); }

      .aic__nav { margin-left:auto; display:flex; align-items:center; gap:6px; }
      .aic__nav-btn { width:26px; height:26px; border-radius:50%; border:1px solid var(--color-border);
                      background:transparent; color:var(--color-text-secondary); cursor:pointer;
                      font-size:15px; line-height:1; padding:0; transition:var(--transition-fast); }
      .aic__nav-btn:hover:not(:disabled) { border-color:var(--color-primary); color:var(--color-primary-light); }
      .aic__nav-btn:disabled { opacity:.3; cursor:default; }
      .aic__nav-label { font-size:12.5px; color:var(--color-text-secondary); min-width:158px;
                        text-align:center; white-space:nowrap; }
      .aic__nav-input { width:128px; padding:3px 8px; border-radius:var(--radius-sm);
                        border:1px solid var(--color-border); background:var(--color-bg-surface);
                        color:var(--color-text-primary); font-size:12px; }

      .aic__brief-points { display:flex; flex-direction:column; gap:10px; margin:0; padding:0; list-style:none; }
      .aic__brief-points li { display:flex; gap:10px; font-size:13.5px; line-height:1.7;
                              color:var(--color-text-secondary); }
      .aic__brief-no { flex:0 0 auto; width:20px; height:20px; border-radius:50%; margin-top:3px;
                       background:var(--color-primary-bg); color:var(--color-primary-light);
                       font-size:11.5px; display:flex; align-items:center; justify-content:center; }
      .aic__brief-src { color:var(--color-primary-light); text-decoration:none; font-size:12px; margin-left:6px; }
      .aic__brief-trend { margin-top:14px; padding:10px 12px; border-radius:var(--radius-sm);
                          background:var(--color-accent-bg); border-left:2px solid var(--color-accent);
                          font-size:13px; line-height:1.7; color:var(--color-accent-light); }

      .aic__rank { display:flex; flex-direction:column; }
      .aic__rank-row { display:flex; gap:12px; align-items:flex-start; padding:11px 4px; }
      .aic__rank-row + .aic__rank-row { border-top:1px solid var(--color-border-light); }
      .aic__rank-no { flex:0 0 auto; width:22px; height:22px; border-radius:6px;
                      background:var(--color-bg-surface); color:var(--color-text-secondary);
                      font-size:12px; font-weight:600; display:flex; align-items:center; justify-content:center; }
      .aic__rank-row:first-child .aic__rank-no { background:var(--color-accent-bg); color:var(--color-accent-light); }
      .aic__rank-main { flex:1; min-width:0; }
      .aic__rank-name { font-size:13.5px; font-weight:600; color:var(--color-text-primary);
                        text-decoration:none; word-break:break-all; }
      a.aic__rank-name:hover { color:var(--color-primary-light); }
      .aic__rank-desc { margin-top:5px; font-size:12.5px; line-height:1.62; color:var(--color-text-secondary); }
      .aic__rank-meta { flex:0 0 auto; text-align:right; font-size:12px; color:var(--color-text-muted); }
      .aic__up { color:var(--color-primary-light); font-weight:600; }
      .aic__rank-date { display:block; margin-top:3px; font-size:11px; color:var(--color-text-muted); }
      .aic__src { font-size:11.5px; color:var(--color-text-muted); }

      .aic__gen { display:flex; align-items:center; justify-content:center; gap:10px;
                  padding:70px 20px; font-size:13px; color:var(--color-text-muted);
                  background:var(--color-bg-elevated); border:1px dashed var(--color-border);
                  border-radius:var(--radius-lg); }
      .aic__spin { width:14px; height:14px; border-radius:50%;
                   border:2px solid var(--color-border); border-top-color:var(--color-primary);
                   animation:aic-spin .8s linear infinite; }
      @keyframes aic-spin { to { transform:rotate(360deg); } }

      /* 响应式 */
      @media (max-width: 1100px) { .aic__body { grid-template-columns:1fr; } }
      @media (max-width: 720px)  { .gh-grid { grid-template-columns:1fr; } }
    </style>

    <div class="aic__wrap">
        <!-- 顶栏：标题 + 滑块（与「表达训练」同款） -->
        <div class="page-header page-header--with-icon" style="flex-shrink:0">
            <div class="page-header__icon" style="width:58px;height:58px">${AIC_HEADER_ICON}</div>
            <div style="flex:1;display:flex;justify-content:space-between;align-items:flex-start">
                <div>
                    <h1 class="page-header__title">AI资讯</h1>
                    <p class="page-header__subtitle">GitHub 趋势 · 国内 / 国际 AI 资讯 · AI 分析</p>
                </div>
                <div class="aic__tabs" id="aic-tabs" data-active="news">
                    <div class="aic__tab-slider"></div>
                    <div class="aic__tab aic__tab--active" data-view="news">资讯</div>
                    <div class="aic__tab" data-view="analysis">AI 分析</div>
                </div>
            </div>
        </div>

        <!-- 视图：资讯 -->
        <div class="aic__view aic__view--active" id="aic-view-news">
            <div class="aic__empty-all" id="aic-empty-all" style="display:none">
                ${AIC_EMPTY_ICON}
                <div class="aic__empty-all-title">还没有资讯数据</div>
                <div class="aic__empty-all-sub">点一下立即拉取，或等后端定时任务自动更新</div>
                <button class="aic__refresh" id="aic-refresh-btn" onclick="refreshAIConsult()">立即刷新</button>
            </div>

            <div class="aic__body" id="aic-grid">
                <!-- 左：GitHub（3/4） -->
                <section class="ai-box" data-box="github">
                    <div class="ai-box__head">
                        <span class="ai-box__title">GitHub 趋势</span>
                        <span class="ai-box__sub" id="github-time"></span>
                    </div>
                    <div class="ai-box__tabs">
                        <button class="ai-tab active" data-tab="weekly">本周最热</button>
                        <button class="ai-tab" data-tab="daily">今日新仓库</button>
                    </div>
                    <div class="gh-grid" id="github-body"></div>
                </section>

                <!-- 右：国内 / 国际（1/4） -->
                <div class="aic__side" id="aic-side">
                    <section class="ai-box" data-box="domestic" draggable="true">
                        <div class="ai-box__head">
                            <span class="ai-box__title">国内 AI 资讯</span>
                            <span class="ai-box__sub" id="domestic-time"></span>
                        </div>
                        <div class="news-list" id="domestic-body"></div>
                    </section>
                    <section class="ai-box" data-box="international" draggable="true">
                        <div class="ai-box__head">
                            <span class="ai-box__title">国际 AI 资讯</span>
                            <span class="ai-box__sub" id="international-time"></span>
                        </div>
                        <div class="news-list" id="international-body"></div>
                    </section>
                </div>
            </div>
        </div>

        <!-- 视图：AI 分析 -->
        <div class="aic__view" id="aic-view-analysis">
            <div class="aic__gen" id="aic-gen" style="display:none">
                <span class="aic__spin"></span>
                <span>AI 正在分析今天的情报…首次进入需要几十秒，好了会自动刷新</span>
            </div>

            <div class="aic__an" id="aic-analysis-body" style="display:none">
                <!-- 每日情报摘要 -->
                <section class="aic__card">
                    <div class="aic__card-head">
                        <span class="aic__card-title">每日情报摘要</span>
                        <span class="aic__brief-date" id="aic-brief-date"></span>
                    </div>
                    <div id="aic-brief"><div class="ai-box__empty">加载中…</div></div>
                </section>

                <!-- 本周新鲜榜（可切周） -->
                <section class="aic__card">
                    <div class="aic__card-head">
                        <span class="aic__card-title">本周新鲜榜</span>
                        <div class="aic__nav">
                            <button class="aic__nav-btn" onclick="aicNav('weekly',-1)">‹</button>
                            <span class="aic__nav-label" id="aic-navlabel-weekly"></span>
                            <button class="aic__nav-btn" onclick="aicNav('weekly',1)">›</button>
                            <input type="date" class="aic__nav-input" id="aic-navinput-weekly"
                                   onchange="aicJumpWeek(this.value)">
                        </div>
                    </div>
                    <div class="aic__rank" id="aic-rank-weekly"></div>
                </section>

                <!-- 本日新鲜榜（可切今天/昨天） -->
                <section class="aic__card">
                    <div class="aic__card-head">
                        <span class="aic__card-title">本日新鲜榜</span>
                        <div class="aic__nav">
                            <button class="aic__nav-btn" id="aic-prev-daily" onclick="aicNav('daily',-1)">‹</button>
                            <span class="aic__nav-label" id="aic-navlabel-daily"></span>
                            <button class="aic__nav-btn" id="aic-next-daily" onclick="aicNav('daily',1)">›</button>
                        </div>
                    </div>
                    <div class="aic__rank" id="aic-rank-daily"></div>
                </section>

                <!-- 资讯热度榜（可切今天/昨天） -->
                <section class="aic__card">
                    <div class="aic__card-head">
                        <span class="aic__card-title">资讯热度榜</span>
                        <div class="aic__nav">
                            <button class="aic__nav-btn" id="aic-prev-news_hot" onclick="aicNav('news_hot',-1)">‹</button>
                            <span class="aic__nav-label" id="aic-navlabel-news_hot"></span>
                            <button class="aic__nav-btn" id="aic-next-news_hot" onclick="aicNav('news_hot',1)">›</button>
                        </div>
                    </div>
                    <div class="aic__rank" id="aic-rank-news_hot"></div>
                </section>
            </div>
        </div>
    </div>`;
}

/* ── 视图切换（顶栏滑块） ─────────────────────────────────────── */

function switchAICView(view) {
    document.querySelectorAll('#aic-tabs .aic__tab').forEach(t => {
        t.classList.toggle('aic__tab--active', t.dataset.view === view);
    });
    const tabs = document.getElementById('aic-tabs');
    if (tabs) tabs.dataset.active = view;   // CSS 靠这个移动滑块
    document.querySelectorAll('.aic__view').forEach(v => {
        v.classList.toggle('aic__view--active', v.id === 'aic-view-' + view);
    });
    if (view === 'news') {
        // 切回来时重新量一次（之前可能处于隐藏状态，量不准）
        capNewsList(document.getElementById('domestic-body'));
        capNewsList(document.getElementById('international-body'));
    } else if (view === 'analysis') {
        loadAnalysis();          // 懒触发：今天没生成过 → 后端起生成任务，前端轮询
    }
}

/* ── 整页无数据时：显示空状态 + 刷新按钮 ─────────────────────── */

function updateAIConsultEmptyState() {
    const d = AICONSULT_DATA || {};
    const hasData = ['github_weekly', 'github_daily', 'domestic', 'international']
        .some(k => (d[k] || []).length > 0);
    const empty = document.getElementById('aic-empty-all');
    const grid = document.getElementById('aic-grid');
    if (empty) empty.style.display = hasData ? 'none' : '';
    if (grid) grid.style.display = hasData ? '' : 'none';
}

/* ── 右侧两个框的拖拽互换（**不持久化**：刷新 / 离开页面即回默认顺序） ── */

const NEWS_VISIBLE = 5;   // 每个资讯框默认露出几条，其余上下滚动

/** 把资讯列表的高度卡到「恰好 5 条」，多的部分靠滚动条查看。 */
function capNewsList(listEl) {
    if (!listEl) return;
    listEl.style.maxHeight = '';
    const items = listEl.querySelectorAll('.news-item');
    if (items.length <= NEWS_VISIBLE) return;   // 不够 5 条就不出滚动条
    const last = items[NEWS_VISIBLE - 1];
    const h = last.offsetTop + last.offsetHeight;
    if (h > 0) listEl.style.maxHeight = h + 'px';
}

/* ── 事件绑定 ─────────────────────────────────────────────────── */

function bindAIConsult() {
    // 顶栏滑块
    document.querySelectorAll('#aic-tabs .aic__tab').forEach(t => {
        t.addEventListener('click', () => switchAICView(t.dataset.view));
    });

    // 右侧两个资讯框：拖拽互换
    const side = document.getElementById('aic-side');
    if (side) {
        side.querySelectorAll('.ai-box').forEach(box => {
            box.addEventListener('dragstart', e => {
                e.dataTransfer.setData('text/plain', box.dataset.box);
                box.classList.add('ai-box--dragging');
            });
            box.addEventListener('dragend', () => box.classList.remove('ai-box--dragging'));
            box.addEventListener('dragover', e => e.preventDefault());
            box.addEventListener('drop', e => {
                e.preventDefault();
                const from = e.dataTransfer.getData('text/plain');
                if (!from || from === box.dataset.box) return;
                const dragged = side.querySelector('.ai-box[data-box="' + from + '"]');
                // 只挪 DOM，不写 localStorage —— 刷新或重新进入页面即回默认顺序
                if (dragged) side.insertBefore(dragged, box);
            });
        });
    }

    // GitHub 本周 / 今日
    document.querySelectorAll('#aic-view-news .ai-tab').forEach(t => {
        t.addEventListener('click', () => switchGHTab(t.dataset.tab));
    });
}

// 窗口变宽变窄会改变文字换行 → 重新量一次「5 条」的高度
// （本脚本只加载一次，这个监听也只绑一次）
window.addEventListener('resize', function () {
    capNewsList(document.getElementById('domestic-body'));
    capNewsList(document.getElementById('international-body'));
});

function switchGHTab(tab) {
    document.querySelectorAll('#aic-view-news .ai-tab')
        .forEach(t => t.classList.toggle('active', t.dataset.tab === tab));
    const list = (AICONSULT_DATA && (tab === 'weekly' ? AICONSULT_DATA.github_weekly : AICONSULT_DATA.github_daily)) || [];
    const body = document.getElementById('github-body');
    if (body) body.innerHTML = list.length ? list.map(ghCard).join('') : aiEmpty('暂无数据');
}

/* ── 数据加载 ─────────────────────────────────────────────────── */

function setBoxTime(id, list) {
    const el = document.getElementById(id);
    if (!el) return;
    const t = (list && list[0] && list[0].batch_time) || '';
    el.textContent = t ? '更新于 ' + fmtBatch(t) : '';
}

async function loadAIConsult() {
    let data;
    try {
        data = await aiApiGet('/api/aiconsult/all');
    } catch (e) {
        AICONSULT_DATA = null;
        updateAIConsultEmptyState();   // 加载失败 = 没数据 → 放出空状态 + 刷新按钮
        return;
    }
    AICONSULT_DATA = data;
    document.querySelectorAll('.ai-box__hint').forEach(h => h.remove());

    const cfg = data.configured || {};
    const hints = [];
    if (!cfg.github) hints.push('GitHub Token 未配置');
    if (!cfg.domestic) hints.push('国内资讯（Bocha）Key 未配置');
    if (!cfg.international) hints.push('国际资讯（Tavily）Key 未配置');
    if (hints.length) {
        const hintEl = document.createElement('div');
        hintEl.className = 'ai-box__hint';
        hintEl.innerHTML = '⚠️ ' + hints.join('；') + '（在 <code>backend/.env</code> 配置后重启）';
        const ghBox = document.querySelector('.ai-box[data-box="github"]');
        if (ghBox) ghBox.insertBefore(hintEl, ghBox.querySelector('.ai-box__tabs'));
    }

    setBoxTime('github-time', data.github_weekly);
    switchGHTab('weekly');

    const dom = data.domestic || [];
    const intl = data.international || [];
    document.getElementById('domestic-body').innerHTML = dom.length ? dom.map(newsCard).join('') : aiEmpty('暂无数据');
    document.getElementById('international-body').innerHTML = intl.length ? intl.map(newsCard).join('') : aiEmpty('暂无数据');
    setBoxTime('domestic-time', dom);
    setBoxTime('international-time', intl);

    updateAIConsultEmptyState();   // 先决定网格显不显示，再量高度
    capNewsList(document.getElementById('domestic-body'));
    capNewsList(document.getElementById('international-body'));
}

async function refreshAIConsult() {
    const btn = document.querySelector('.aic__refresh');
    if (btn) { btn.disabled = true; btn.textContent = '刷新中…'; }
    try {
        await aiApiPost('/api/aiconsult/refresh');
        await loadAIConsult();
        if (typeof showToast === 'function') showToast('已触发刷新', 'success');
    } catch (e) {
        if (typeof showToast === 'function') showToast('刷新失败：' + e.message, 'error');
    } finally {
        if (btn) { btn.disabled = false; btn.textContent = '立即刷新'; }
    }
}

/* ── AI 分析：加载 / 渲染 / 切换 ─────────────────────────────── */

const AIC_AN = { periods: { weekly: [], daily: [], news_hot: [] },
                 cur: { weekly: '', daily: '', news_hot: '' }, polling: null };

/** 本地日期 YYYY-MM-DD（**不要用 toISOString**，那是 UTC，会差 8 小时） */
function aicLocalDate(d) {
    const x = d || new Date();
    const p = n => String(n).padStart(2, '0');
    return `${x.getFullYear()}-${p(x.getMonth() + 1)}-${p(x.getDate())}`;
}

function fmtWeekRange(mondayStr) {
    if (!mondayStr) return '';
    const m = new Date(mondayStr + 'T00:00:00');
    if (isNaN(m)) return mondayStr;
    const e = new Date(m.getFullYear(), m.getMonth(), m.getDate() + 6);
    return `${m.getFullYear()}年${m.getMonth() + 1}月${m.getDate()}日 - ${e.getMonth() + 1}月${e.getDate()}日`;
}

function fmtDayLabel(dateStr) {
    if (!dateStr) return '';
    const today = aicLocalDate();
    const yest = aicLocalDate(new Date(Date.now() - 86400000));
    const tag = dateStr === today ? '今天' : (dateStr === yest ? '昨天' : '');
    const parts = String(dateStr).split('-');
    const md = parts.length === 3 ? `${parts[1]}/${parts[2]}` : dateStr;
    return (tag ? tag + ' · ' : '') + md;
}

function stopAnalysisPoll() {
    if (AIC_AN.polling) { clearInterval(AIC_AN.polling); AIC_AN.polling = null; }
}

async function loadAnalysis() {
    const gen = document.getElementById('aic-gen');
    const body = document.getElementById('aic-analysis-body');
    if (!gen || !body) return;
    let r;
    try {
        r = await aiApiGet('/api/aiconsult/analysis');
    } catch (e) {
        stopAnalysisPoll();
        gen.style.display = 'none';
        body.style.display = '';
        const br = document.getElementById('aic-brief');
        if (br) br.innerHTML = aiEmpty('加载失败：' + e.message);
        return;
    }
    if (r.status === 'generating') {
        gen.style.display = '';
        body.style.display = 'none';
        if (!AIC_AN.polling) AIC_AN.polling = setInterval(loadAnalysis, 5000);
        return;
    }
    stopAnalysisPoll();
    gen.style.display = 'none';
    body.style.display = '';
    renderAnalysis(r);
}

function renderAnalysis(r) {
    const b = r.boards || {};
    AIC_AN.periods = {
        weekly: (b.weekly && b.weekly.periods) || [],
        daily: (b.daily && b.daily.periods) || [],
        news_hot: (b.news_hot && b.news_hot.periods) || [],
    };
    AIC_AN.cur = {
        weekly: (b.weekly && b.weekly.default) || '',
        daily: (b.daily && b.daily.default) || '',
        news_hot: (b.news_hot && b.news_hot.default) || '',
    };
    const data = r.data || {};
    renderBriefing(r);
    renderBoard('weekly', data.weekly);
    renderBoard('daily', data.daily);
    renderBoard('news_hot', data.news_hot);
}

function renderBriefing(r) {
    const el = document.getElementById('aic-brief');
    const dt = document.getElementById('aic-brief-date');
    if (!el) return;
    if (dt) dt.textContent = r.updated_at ? ('生成于 ' + fmtBatch(r.updated_at)) : '';
    const b = r.briefing;
    if (!b || ((!b.points || !b.points.length) && !b.trend)) {
        el.innerHTML = aiEmpty('暂无摘要');
        return;
    }
    const pts = (b.points || []).map((p, i) => {
        const srcs = (p.sources || []).filter(s => s.url).map(s =>
            `<a class="aic__brief-src" href="${escapeHtml(s.url)}" target="_blank" rel="noopener">[${s.ref}]</a>`
        ).join('');
        return `<li><span class="aic__brief-no">${i + 1}</span><span>${escapeHtml(p.text)}${srcs}</span></li>`;
    }).join('');
    el.innerHTML = (pts ? `<ul class="aic__brief-points">${pts}</ul>` : '')
        + (b.trend ? `<div class="aic__brief-trend">趋势 · ${escapeHtml(b.trend)}</div>` : '');
}

function renderBoard(kind, board) {
    const el = document.getElementById('aic-rank-' + kind);
    if (!el) return;
    const items = ((board || {}).items) || [];
    if (!items.length) {
        el.innerHTML = aiEmpty('暂无数据');
    } else if (kind === 'weekly') {
        el.innerHTML = items.map(weeklyRow).join('');
    } else if (kind === 'daily') {
        el.innerHTML = items.map(dailyRow).join('');
    } else {
        el.innerHTML = items.map(newsRow).join('');
    }
    updateNav(kind);
}

function weeklyRow(it, i) {
    const meta = (it.meta && typeof it.meta === 'object') ? it.meta : {};
    const lang = meta.language
        ? `<span style="margin-left:8px;display:inline-flex;align-items:center;gap:5px;vertical-align:middle;font-size:11.5px;color:var(--color-text-muted)"><i style="width:9px;height:9px;border-radius:50%;display:inline-block;background:${langColor(meta.language)}"></i>${escapeHtml(meta.language)}</span>`
        : '';
    const desc = it.intro_zh
        ? escapeHtml(it.intro_zh)
        : escapeHtml(truncate(it.summary || '暂无简介', 130));
    const delta = Number(it.delta) || 0;
    return `<div class="aic__rank-row">
        <span class="aic__rank-no">${i + 1}</span>
        <div class="aic__rank-main">
            <a class="aic__rank-name" href="${escapeHtml(it.url || '#')}" target="_blank" rel="noopener">${escapeHtml(it.repo || '')}</a>${lang}
            <div class="aic__rank-desc">${desc}</div>
        </div>
        <div class="aic__rank-meta">
            <span class="aic__up">+${formatStars(delta)} ★</span>
            <span class="aic__rank-date">共 ${formatStars(it.stars)}</span>
        </div>
    </div>`;
}

function dailyRow(it, i) {
    const delta = Number(it.delta) || 0;
    const tag = (it.date === aicLocalDate()) ? '今日 ' : '';
    return `<div class="aic__rank-row">
        <span class="aic__rank-no">${i + 1}</span>
        <div class="aic__rank-main">
            <span class="aic__rank-name">${escapeHtml(it.repo || '')}</span>
        </div>
        <div class="aic__rank-meta">
            <span class="aic__up">${tag}+${formatStars(delta)} ★</span>
            <span class="aic__rank-date">${escapeHtml(it.date || '')}</span>
        </div>
    </div>`;
}

function newsRow(it, i) {
    return `<div class="aic__rank-row">
        <span class="aic__rank-no">${i + 1}</span>
        <div class="aic__rank-main">
            <a class="aic__rank-name" href="${escapeHtml(it.url || '#')}" target="_blank" rel="noopener">${escapeHtml(it.title || '')}</a>
            ${it.summary ? `<div class="aic__rank-desc">${escapeHtml(it.summary)}</div>` : ''}
        </div>
        <div class="aic__rank-meta">
            <span class="aic__up">热度 ${it.score != null ? it.score : '-'}</span>
            <span class="aic__rank-date">${escapeHtml(it.source || '')}</span>
        </div>
    </div>`;
}

function updateNav(kind) {
    const cur = AIC_AN.cur[kind] || '';
    const label = document.getElementById('aic-navlabel-' + kind);
    if (label) label.textContent = (kind === 'weekly') ? fmtWeekRange(cur) : fmtDayLabel(cur);

    if (kind === 'weekly') {
        const inp = document.getElementById('aic-navinput-weekly');
        if (inp && cur) inp.value = cur;
        return;
    }
    const list = AIC_AN.periods[kind] || [];
    const idx = list.indexOf(cur);
    const prev = document.getElementById('aic-prev-' + kind);
    const next = document.getElementById('aic-next-' + kind);
    if (prev) prev.disabled = (idx <= 0);
    if (next) next.disabled = (idx < 0 || idx >= list.length - 1);
}

function aicNav(kind, dir) {
    if (kind === 'weekly') {
        const cur = AIC_AN.cur.weekly;
        if (!cur) return;
        const d = new Date(cur + 'T00:00:00');
        if (isNaN(d)) return;
        d.setDate(d.getDate() + dir * 7);
        aicLoadBoard('weekly', aicLocalDate(d));
        return;
    }
    const list = AIC_AN.periods[kind] || [];
    const idx = list.indexOf(AIC_AN.cur[kind]);
    const ni = (idx < 0 ? 0 : idx) + dir;
    if (ni < 0 || ni >= list.length) return;
    aicLoadBoard(kind, list[ni]);
}

/** 周榜的日期输入：任意日期 → 它所在那一周的周一 */
function aicJumpWeek(v) {
    if (!v) return;
    const d = new Date(v + 'T00:00:00');
    if (isNaN(d)) return;
    const dow = (d.getDay() + 6) % 7;      // 周一 = 0
    d.setDate(d.getDate() - dow);
    aicLoadBoard('weekly', aicLocalDate(d));
}

async function aicLoadBoard(kind, period) {
    try {
        const r = await aiApiGet('/api/aiconsult/board?kind=' + encodeURIComponent(kind)
            + '&period=' + encodeURIComponent(period || ''));
        AIC_AN.cur[kind] = r.period;
        if (r.periods) AIC_AN.periods[kind] = r.periods;
        renderBoard(kind, r.board);
    } catch (e) {
        if (typeof showToast === 'function') showToast('加载失败：' + e.message, 'error');
    }
}

async function renderAIConsult() {
    const c = document.getElementById('page-extensions');
    c.innerHTML = getAIConsultLayout();   // 每次进页面都重建 → 拖拽/尺寸自动回默认
    bindAIConsult();
    await loadAIConsult();
}
