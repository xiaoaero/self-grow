/* ================================================================
   App — 应用入口初始化
   ================================================================ */

document.addEventListener('DOMContentLoaded', async () => {
    // 验证登录
    if (!requireLogin()) return;

    // 从后端并行加载用户数据
    const user = getCurrentUser();
    const [profile, habitsData, lastWeekData, profileStats, recentActivities, rewardsData, goalsData, scheduledTasksData, taskHistoryData] = await Promise.all([
        fetchUserProfile(user.id).catch(() => null),
        fetchHabits(user.id).catch(() => null),
        fetchLastWeekHabits(user.id).catch(() => null),
        fetchProfileStats(user.id).catch(() => null),
        fetchRecentActivities(user.id).catch(() => null),
        fetchRewards(user.id).catch(() => null),
        fetchGoals(user.id).catch(() => null),
        fetchScheduledTasks(user.id).catch(() => null),
        fetchTaskHistory(user.id, { page_size: 500 }).catch(() => null),
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

    if (taskHistoryData && taskHistoryData.records) {
        AppData.taskHistory = taskHistoryData.records;
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
});
