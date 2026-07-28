/* ================================================================
   Data — 初始数据（启动时由后端 API 加载覆盖）
   ================================================================ */

// SVG icon map — 8 attribute icons designed in 属性图标.svg
const AttrIcons = {
    health: `<svg viewBox="0 0 24 24" fill="none"><path d="M12 20C12 20 20 14.5 20 9.5C20 6.5 17.5 4 14.5 4C12.5 4 12 6 12 6C12 6 11.5 4 9.5 4C6.5 4 4 6.5 4 9.5C4 14.5 12 20 12 20Z" fill="url(#g-health)" stroke="none"/><path d="M8 10.5L10.5 13L16 7.5" stroke="rgba(255,255,255,0.5)" stroke-width="1.5" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg>`,
    study: `<svg viewBox="0 0 24 24" fill="none"><path d="M5 17V5.5C5 4.67 5.67 4 6.5 4H12L12 17L6.5 17C5.67 17 5 16.33 5 17Z" fill="url(#g-study)"/><path d="M19 17V5.5C19 4.67 18.33 4 17.5 4H12L12 17L17.5 17C18.33 17 19 16.33 19 17Z" fill="url(#g-study)" opacity="0.75"/><line x1="12" y1="4" x2="12" y2="17" stroke="rgba(255,255,255,0.3)" stroke-width="1"/></svg>`,
    relation: `<svg viewBox="0 0 24 24" fill="none"><circle cx="9" cy="8" r="3.5" fill="url(#g-relate)"/><circle cx="15" cy="8" r="3.5" fill="url(#g-relate)" opacity="0.8"/><path d="M2 20C2 16 6 14 9 14C12 14 16 16 16 20" stroke="url(#g-relate)" stroke-width="2.5" fill="none" stroke-linecap="round"/><path d="M8 20C8 16 12 14 15 14C18 14 22 16 22 20" stroke="url(#g-relate)" stroke-width="2.5" fill="none" stroke-linecap="round" opacity="0.8"/><path d="M12 12C11 10 9 10.5 9.5 12C10 13.5 12 15 12 15C12 15 14 13.5 14.5 12C15 10.5 13 10 12 12Z" fill="#FF91A8" opacity="0.9"/></svg>`,
    work: `<svg viewBox="0 0 24 24" fill="none"><rect x="4" y="8" width="16" height="12" rx="2" fill="url(#g-work)"/><path d="M8 8V5.5C8 4.67 8.67 4 9.5 4H14.5C15.33 4 16 4.67 16 5.5V8" stroke="url(#g-work)" stroke-width="2.5" fill="none" stroke-linecap="round"/><line x1="12" y1="12" x2="12" y2="16.5" stroke="rgba(0,0,0,0.15)" stroke-width="1.2"/></svg>`,
    create: `<svg viewBox="0 0 24 24" fill="none"><ellipse cx="10" cy="14" rx="9" ry="7" fill="url(#g-create)"/><ellipse cx="10" cy="14" rx="6.5" ry="5" fill="#2f3544" opacity="0.4"/><circle cx="6" cy="11" r="1.5" fill="#FFF" opacity="0.85"/><circle cx="9" cy="9" r="1.2" fill="#FFE066" opacity="0.85"/><circle cx="13" cy="9.5" r="1.1" fill="#6EE7B7" opacity="0.85"/><line x1="16" y1="8" x2="22" y2="2" stroke="#DDD" stroke-width="2" stroke-linecap="round"/></svg>`,
    finance: `<svg viewBox="0 0 24 24" fill="none"><ellipse cx="11" cy="18" rx="8" ry="3" fill="#1a7a4c"/><rect x="4" y="8" width="14" height="8" rx="2" fill="url(#g-money)"/><ellipse cx="11" cy="8" rx="7" ry="2.5" fill="url(#g-money)"/><text x="11" y="12" text-anchor="middle" fill="#166534" font-size="6" font-weight="700">¥</text></svg>`,
    hobby: `<svg viewBox="0 0 24 24" fill="none"><ellipse cx="8" cy="16" rx="5" ry="4" fill="url(#g-hobby)" transform="rotate(-15,8,16)"/><line x1="13" y1="15" x2="13" y2="4" stroke="#F472B6" stroke-width="2" stroke-linecap="round"/><ellipse cx="18" cy="13" rx="4" ry="3" fill="url(#g-hobby)" opacity="0.8" transform="rotate(-15,18,13)"/><line x1="18" y1="13" x2="18" y2="5" stroke="#F472B6" stroke-width="1.8" stroke-linecap="round" opacity="0.8"/><line x1="13" y1="4.5" x2="18" y2="5.5" stroke="#F472B6" stroke-width="2.5" stroke-linecap="round"/></svg>`,
    soul: `<svg viewBox="0 0 24 24" fill="none"><path d="M12 20C9 16 7 11 7.5 7C8 4 10 2 12 2C14 2 16 4 16.5 7C17 11 15 16 12 20Z" fill="url(#g-soul)"/><path d="M12 18C10.5 15 9.5 11 10 8C10.5 6 11.5 5 12 5C12.5 5 13.5 6 14 8C14.5 11 13.5 15 12 18Z" fill="#FCD34D" opacity="0.7"/><path d="M12 16C11 14 10.5 11.5 11 9.5C11.2 8.5 11.7 7.8 12 7.8C12.3 7.8 12.8 8.5 13 9.5C13.5 11.5 13 14 12 16Z" fill="#FEF3C7" opacity="0.6"/></svg>`,
};

const AppData = {
    user: {
        id: null,
        name: '冒险者',
        level: 1,
        exp: 0,
        totalExp: 0,
        streak: 0,
        joined: new Date().toISOString().slice(0, 10),
        get expToNext() { return expForLevel(this.level); },
        get title() { return getRankInfo(this.level).name; },
    },

    // 今日统计（启动时由后端加载覆盖）
    todayStats: { focusMinutes: 0, tasksDone: 0, habitsChecked: 0, expEarned: 0 },

    // 昨日对比（启动时由后端加载覆盖）
    yesterdayStats: { focusMinutes: 0, tasksDone: 0, habitsChecked: 0, expEarned: 0 },

    // 分类定义（8大属性维度）
    categories: [
        { id: 'health',    name: '健康',   color: '#FF7B72', expRate: 10, globalRate: 1.0  },
        { id: 'study',     name: '学习',   color: '#58D5C9', expRate: 10, globalRate: 1.0  },
        { id: 'relation',  name: '关系',   color: '#FF91A8', expRate: 8,  globalRate: 0.5  },
        { id: 'work',      name: '工作',   color: '#FFCA40', expRate: 12, globalRate: 1.0  },
        { id: 'create',    name: '创作',   color: '#B794F6', expRate: 8,  globalRate: 0.5  },
        { id: 'finance',   name: '财务',   color: '#4ADE80', expRate: 6,  globalRate: 0.5  },
        { id: 'hobby',     name: '爱好',   color: '#F472B6', expRate: 7,  globalRate: 0.75 },
        { id: 'soul',      name: '魅力',   color: '#FBBF24', expRate: 9,  globalRate: 0.5  },
    ],

    // 八维属性详情（启动时由后端加载覆盖）
    attributeDetails: [],

    // 近期活动（启动时由后端加载覆盖）
    recentActivities: [],

    // 习惯列表（启动时由后端加载覆盖）
    habits: [],

    // 上周习惯数据（启动时由后端加载覆盖）
    lastWeekHabits: [],

    // 目标（启动时由后端加载覆盖）
    goals: [],

    // 任务（启动时由后端加载覆盖）
    tasks: { todo: [], doing: [], done: [] },

    // 历史任务（启动时由后端加载覆盖）
    taskHistory: [],

    // 奖励（启动时由后端加载覆盖）
    rewards: [],

    // 个人主页 — 统计数据（启动时由后端加载覆盖）
    profile: {
        effortDays: 0,
        totalXP: 0,
        habitCheckins: 0,
        tasksCompleted: 0,
        goalsAchieved: 0,
        rewardsUnlocked: 0,
        yearlyActivity: [],
        dimensions: [],
    },
};

// 行动中心数据（启动时由各页面从后端 API 加载）
AppData.actionCenter = { dimensions: [], activities: [], weeklyTasks: [] };

// 历史记录（启动时由后端加载覆盖）
AppData.historyRecords = [];

// 定时任务模板（启动时由后端 API 加载覆盖）
AppData.scheduledTasks = [];

// 每周任务模板（启动时由后端 API 加载覆盖）
AppData.weeklyTaskTemplates = [];