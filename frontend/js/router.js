/* ================================================================
   Router — 页面导航 + 动态 JS 加载
   ================================================================ */

let currentPage = 'dashboard';
let currentSubPage = 'quick';
let currentTasksSubPage = 'today';
let currentSkillSubPage = 'mine';
let currentExtSubPage = 'agent';

/** 已加载的页面 JS 模块名集合 */
const loadedPages = new Set();

/** 渲染版本号，用于防止快速切换页面时旧渲染覆盖新页面 */
navigateTo._version = 0;

/** 页面名 → JS 文件路径 映射 */
const PAGE_JS_MAP = {
    dashboard: 'js/pages/dashboard.js',
    action: 'js/pages/action.js',
    history: 'js/pages/history.js',
    attributes: 'js/pages/attributes.js',
    goals: 'js/pages/goals.js',
    tasks: 'js/pages/tasks.js',
    habits: 'js/pages/habits.js',
    skill: 'js/pages/skills.js',
    rewards: 'js/pages/rewards.js',
    extensions: 'js/pages/agent.js',
};

/** 动态加载页面 JS */
function loadPageJS(pageName) {
    if (loadedPages.has(pageName)) return Promise.resolve();
    const src = PAGE_JS_MAP[pageName];
    if (!src) return Promise.resolve();

    return new Promise((resolve, reject) => {
        const script = document.createElement('script');
        script.src = src;
        script.onload = () => {
            loadedPages.add(pageName);
            resolve();
        };
        script.onerror = () => {
            console.warn(`页面 JS 加载失败: ${src}`);
            reject(new Error(`Failed to load ${src}`));
        };
        document.body.appendChild(script);
    });
}

/** 子导航栏切换防抖（100ms） */
let _lastSubnavToggle = 0;
function _debounceSubnavToggle() {
    const now = Date.now();
    if (now - _lastSubnavToggle < 100) return false;
    _lastSubnavToggle = now;
    return true;
}

function navigateTo(pageName, subPage) {
    // If same page AND same subpage, skip
    if (currentPage === pageName && subPage && currentSubPage === subPage) return;
    if (currentPage === pageName && pageName === 'tasks' && subPage && currentTasksSubPage === subPage) return;
    if (currentPage === pageName && pageName === 'skill' && subPage && currentSkillSubPage === subPage) return;
    if (currentPage === pageName && pageName === 'extensions' && subPage && currentExtSubPage === subPage) return;
    // If clicking parent "行动" while already on it, toggle subnav visibility only
    if (currentPage === pageName && pageName === 'action' && !subPage) {
        if (!_debounceSubnavToggle()) return;
        const subnavAction = document.getElementById('subnav-action');
        if (subnavAction) {
            subnavAction.classList.toggle('sidebar__subnav--open');
        }
        return;
    }
    // If clicking parent "任务" while already on it, toggle subnav visibility only
    if (currentPage === pageName && pageName === 'tasks' && !subPage) {
        if (!_debounceSubnavToggle()) return;
        const subnavTasks = document.getElementById('subnav-tasks');
        if (subnavTasks) {
            subnavTasks.classList.toggle('sidebar__subnav--open');
        }
        return;
    }
    // If clicking parent "技能" while already on it, toggle subnav visibility only
    if (currentPage === pageName && pageName === 'skill' && !subPage) {
        if (!_debounceSubnavToggle()) return;
        const subnavSkill = document.getElementById('subnav-skill');
        if (subnavSkill) {
            subnavSkill.classList.toggle('sidebar__subnav--open');
        }
        return;
    }
    // If clicking parent "扩展" while already on it, toggle subnav visibility only
    if (currentPage === pageName && pageName === 'extensions' && !subPage) {
        if (!_debounceSubnavToggle()) return;
        const subnavExt = document.getElementById('subnav-ext');
        if (subnavExt) {
            subnavExt.classList.toggle('sidebar__subnav--open');
        }
        return;
    }

    // Update sidebar nav items
    document.querySelectorAll('.sidebar__nav-item').forEach(item => {
        item.classList.toggle('active', item.dataset.page === pageName);
    });

    // Handle subnav for "行动" page
    const subnavAction = document.getElementById('subnav-action');
    if (subnavAction) {
        if (pageName === 'action') {
            subnavAction.classList.add('sidebar__subnav--open');
            const targetSub = subPage || 'quick';
            subnavAction.querySelectorAll('.sidebar__subnav-item').forEach(sub => {
                sub.classList.toggle('active', sub.dataset.subpage === 'action.' + targetSub);
            });
            currentSubPage = targetSub;
        } else {
            subnavAction.classList.remove('sidebar__subnav--open');
            currentSubPage = null;
        }
    }

    // Handle subnav for "任务" page
    const subnavTasks = document.getElementById('subnav-tasks');
    if (subnavTasks) {
        if (pageName === 'tasks') {
            subnavTasks.classList.add('sidebar__subnav--open');
            const targetSub = subPage || 'today';
            subnavTasks.querySelectorAll('.sidebar__subnav-item').forEach(sub => {
                sub.classList.toggle('active', sub.dataset.subpage === 'tasks.' + targetSub);
            });
            currentTasksSubPage = targetSub;
        } else {
            subnavTasks.classList.remove('sidebar__subnav--open');
            currentTasksSubPage = null;
        }
    }

    // Handle subnav for "技能" page
    const subnavSkill = document.getElementById('subnav-skill');
    if (subnavSkill) {
        if (pageName === 'skill') {
            subnavSkill.classList.add('sidebar__subnav--open');
            const targetSub = subPage || 'mine';
            subnavSkill.querySelectorAll('.sidebar__subnav-item').forEach(sub => {
                sub.classList.toggle('active', sub.dataset.subpage === 'skill.' + targetSub);
            });
            currentSkillSubPage = targetSub;
        } else {
            subnavSkill.classList.remove('sidebar__subnav--open');
            currentSkillSubPage = null;
        }
    }

    // Handle subnav for "扩展" page
    const subnavExt = document.getElementById('subnav-ext');
    if (subnavExt) {
        if (pageName === 'extensions') {
            subnavExt.classList.add('sidebar__subnav--open');
            const targetSub = subPage || 'agent';
            subnavExt.querySelectorAll('.sidebar__subnav-item').forEach(sub => {
                sub.classList.toggle('active', sub.dataset.subpage === 'ext.' + targetSub);
            });
            currentExtSubPage = targetSub;
        } else {
            subnavExt.classList.remove('sidebar__subnav--open');
            currentExtSubPage = null;
        }
    }

    // Update pages
    document.querySelectorAll('.page').forEach(page => {
        page.classList.remove('page--active');
    });

    const target = document.getElementById('page-' + pageName);
    if (target) {
        target.classList.add('page--active');
        currentPage = pageName;

        // 渲染版本号守卫：防止快速切换页面时旧渲染覆盖新页面
        const renderVersion = ++navigateTo._version;

        // 动态加载并渲染
        loadPageJS(pageName).then(async () => {
            // 如果用户已切换到其他页面，跳过渲染
            if (renderVersion !== navigateTo._version) return;

            const renderers = {
                dashboard: typeof renderDashboard !== 'undefined' ? renderDashboard : null,
                action: typeof renderAction !== 'undefined' ? () => renderAction(currentSubPage) : null,
                history: typeof renderHistory !== 'undefined' ? renderHistory : null,
                attributes: typeof renderAttributes !== 'undefined' ? renderAttributes : null,
                goals: typeof renderGoals !== 'undefined' ? renderGoals : null,
                tasks: typeof renderTasks !== 'undefined' ? () => renderTasks(currentTasksSubPage) : null,
                habits: typeof renderHabits !== 'undefined' ? renderHabits : null,
                skill: typeof renderSkills !== 'undefined' ? () => renderSkills(currentSkillSubPage) : null,
                rewards: typeof renderRewards !== 'undefined' ? renderRewards : null,
                extensions: typeof renderAgent !== 'undefined' ? () => renderAgent(currentExtSubPage) : null,
            };

            const renderFn = renderers[pageName];
            if (renderFn) {
                await renderFn();
            }
        }).catch(() => {
            // 加载失败时显示提示
            target.innerHTML = `<div class="card" style="padding:40px;text-align:center;color:var(--color-text-muted)">
                <div style="font-size:48px;margin-bottom:12px">😵</div>
                <div>页面加载失败，请刷新重试</div>
            </div>`;
        });
    }

    // Scroll to top
    document.querySelector('.main-content').scrollTop = 0;

    // 保存当前页面到 sessionStorage（刷新后恢复，关闭重进则回到仪表盘）
    sessionStorage.setItem('lastPage', pageName);
    if (subPage) {
        sessionStorage.setItem('lastSubPage', subPage);
    } else {
        sessionStorage.removeItem('lastSubPage');
    }
}