/* ================================================================
   App — 应用入口初始化
   ================================================================ */

document.addEventListener('DOMContentLoaded', async () => {
    // 验证登录
    if (!requireLogin()) return;

    // 侧边栏收起/展开（尽早初始化，别等数据加载完才能收起）
    initSidebarCollapse();

    // 从后端并行加载用户数据
    const user = getCurrentUser();
    const [profile, habitsData, lastWeekData, profileStats, recentActivities, rewardsData, goalsData, scheduledTasksData] = await Promise.all([
        fetchUserProfile(user.id).catch(() => null),
        fetchHabits(user.id).catch(() => null),
        fetchLastWeekHabits(user.id).catch(() => null),
        fetchProfileStats(user.id).catch(() => null),
        fetchRecentActivities(user.id).catch(() => null),
        fetchRewards(user.id).catch(() => null),
        fetchGoals(user.id).catch(() => null),
        fetchScheduledTasks(user.id).catch(() => null),
    ]);

    if (profile) {
        // 成功后端数据覆盖 AppData
        AppData.user = {
            ...AppData.user,
            ...profile.user,
            get expToNext() { return expForLevel(this.level); },
            get title() { return getRankInfo(this.level).name; },
        };
        AppData.todayStats = profile.todayStats;
        AppData.yesterdayStats = profile.yesterdayStats;
    }

    if (profileStats) {
        AppData.profile = profileStats;
    }

    if (recentActivities) {
        AppData.recentActivities = recentActivities.activities || recentActivities;
    }

    if (habitsData) {
        AppData.habits = habitsData;
    }
    if (lastWeekData) {
        AppData.lastWeekHabits = lastWeekData;
    }

    if (rewardsData && rewardsData.rewards) {
        AppData.rewards = rewardsData.rewards;
    }

    if (goalsData && goalsData.goals) {
        AppData.goals = goalsData.goals;
    }

    if (scheduledTasksData) {
        const allTasks = [
            ...(scheduledTasksData.daily || []).map(t => ({ ...t, type: 'daily' })),
            ...(scheduledTasksData.weekly || []).map(t => ({ ...t, type: 'weekly' })),
        ];
        AppData.scheduledTasks = allTasks;
        AppData.weeklyTaskTemplates = allTasks.filter(t => t.type === 'weekly');
    }

    // Render sidebar footer (level / rank / EXP bar)
    renderSidebarFooter();

    // Task refresh — 已由后端定时任务（每日 03:00）替代
    await loadPageJS('tasks');

    // 从 sessionStorage 恢复上次页面（刷新保留，关闭重进则回到仪表盘）
    const lastPage = sessionStorage.getItem('lastPage');
    if (lastPage) {
        const lastSubPage = sessionStorage.getItem('lastSubPage');
        navigateTo(lastPage, lastSubPage || undefined);
    } else {
        navigateTo('dashboard');
    }

    // Keyboard shortcuts
    document.addEventListener('keydown', (e) => {
        // Escape to close modal
        if (e.key === 'Escape') {
            closeModal();
        }

        // Ctrl+1-8 to navigate pages
        if (e.ctrlKey && e.key >= '1' && e.key <= '8') {
            e.preventDefault();
            const pages = ['dashboard', 'action', 'history', 'attributes', 'goals', 'tasks', 'habits', 'rewards'];
            navigateTo(pages[parseInt(e.key) - 1]);
        }
    });

    // Close modal on overlay click (respect clickOutsideToClose flag)
    document.getElementById('modal-overlay').addEventListener('click', function(e) {
        if (e.target === document.getElementById('modal-overlay')) {
            closeModalIfNotActive();
        }
    });

    console.log('🌱 个人成长系统 - Self Grow System 已就绪');
    console.log('💡 使用 Ctrl+1~8 快速切换页面');

    // 拉取全局版本号（右下角）
    fetchGlobalVersion();
});

/** 拉取并显示系统版本号（右下角，跟随 git 记录） */
async function fetchGlobalVersion() {
    const API_BASE = window.__SELF_GROW_API_BASE__ || 'http://localhost:3001';
    try {
        const resp = await fetch(`${API_BASE}/api/health`);
        if (resp.ok) {
            const data = await resp.json();
            const el = document.getElementById('global-version');
            if (el && data.version) el.textContent = data.version;
        }
    } catch (e) {
        // 版本号获取失败，保持默认 "--"
    }
}

/* ================================================================
   Sidebar — 收起 / 展开
   ----------------------------------------------------------------
   收起后只留图标（宽度 260px → 76px），主内容区随 --sidebar-width 变宽并
   在剩余空间里重新居中 —— 见 css/sidebar.css 的「收起态」一节。

   状态记在 <html> 的 is-collapsed 上。head 里那段内联脚本会在首屏渲染前
   按 localStorage 预置这个类，否则刷新时会先展开再收起、闪一下。
   ================================================================ */

const SIDEBAR_COLLAPSE_KEY = 'selfgrow.sidebarCollapsed';

function isSidebarCollapsed() {
    return document.documentElement.classList.contains('is-collapsed');
}

/** 把每个导航项的文字写进 data-tip —— 收起态只剩图标时靠它做悬停提示。
 *  这样 index.html 里 11 个导航项一个属性都不用加。 */
function initSidebarTips() {
    document.querySelectorAll('.sidebar__nav-item').forEach(item => {
        if (item.dataset.tip) return;
        const label = item.querySelector('span');
        if (label) item.dataset.tip = label.textContent.trim();
    });
}

/** 同步按钮的 aria 状态与文案（收起后用同一个按钮展开） */
function syncSidebarToggle() {
    const btn = document.getElementById('sidebar-toggle');
    if (!btn) return;
    const collapsed = isSidebarCollapsed();
    const label = collapsed ? '展开侧边栏' : '收起侧边栏';
    btn.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
    btn.setAttribute('aria-label', label);
    btn.title = label;
}

function toggleSidebar() {
    const collapsed = !isSidebarCollapsed();
    document.documentElement.classList.toggle('is-collapsed', collapsed);
    try {
        localStorage.setItem(SIDEBAR_COLLAPSE_KEY, collapsed ? '1' : '0');
    } catch (e) {
        // localStorage 不可用（隐私模式等）：只是记不住状态，功能不受影响
    }
    syncSidebarToggle();
    hideSidebarTip();
}

/* --- 收起态的悬停提示 ---
   为什么不用 CSS ::after：`.sidebar__nav` 上有 overflow-y: auto，
   而一个轴设成 auto 时另一个轴的计算值也会变成 auto，浮层会被裁掉。
   所以往 body 挂一个 fixed 定位的浮层，由这里负责定位。 */

let _sidebarTipEl = null;

function showSidebarTip(item) {
    if (!isSidebarCollapsed()) return;
    const text = item.dataset.tip;
    if (!text) return;

    if (!_sidebarTipEl) {
        _sidebarTipEl = document.createElement('div');
        _sidebarTipEl.className = 'sidebar__tip';
        document.body.appendChild(_sidebarTipEl);
    }
    _sidebarTipEl.textContent = text;
    const rect = item.getBoundingClientRect();
    _sidebarTipEl.style.top = (rect.top + rect.height / 2) + 'px';
    _sidebarTipEl.style.left = (rect.right + 14) + 'px';
    _sidebarTipEl.classList.add('sidebar__tip--show');
}

function hideSidebarTip() {
    if (_sidebarTipEl) _sidebarTipEl.classList.remove('sidebar__tip--show');
}

function initSidebarCollapse() {
    const btn = document.getElementById('sidebar-toggle');
    if (btn) btn.addEventListener('click', toggleSidebar);

    syncSidebarToggle();
    initSidebarTips();

    const sidebar = document.getElementById('sidebar');
    if (!sidebar) return;

    sidebar.addEventListener('mouseover', (e) => {
        const item = e.target.closest('.sidebar__nav-item');
        if (item) showSidebarTip(item);
    });
    sidebar.addEventListener('mouseleave', hideSidebarTip);

    // 收起态点带子菜单的板块（行动 / 任务 / 技能 / 扩展）：
    // 先展开侧栏 —— 收起时子菜单是隐藏的，不展开就选不了子板块。
    // 用捕获阶段，抢在那句 inline onclick 的 navigateTo 之前执行，
    // 这样子菜单能跟着一起展开。
    sidebar.addEventListener('click', (e) => {
        if (!isSidebarCollapsed()) return;
        const item = e.target.closest('.sidebar__nav-item');
        if (!item) return;
        if (!item.querySelector('.sidebar__nav-arrow')) return;   // 没有子菜单的项不展开
        toggleSidebar();   // 此刻必然是「收起 → 展开」
    }, true);
}
