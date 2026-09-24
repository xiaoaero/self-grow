/* ================================================================
   Agent — 表达训练系统（两视图完整实现）
   ================================================================ */

let currentAgentSubPage = 'agent';

// ================================================================
// 全局状态
// ================================================================

const STATE = {
    // 题型选择
    selectedTypes: [],
    // 当前题目
    currentQuestion: null,
    // 当前回答记录
    currentAnswerId: null,
    currentAttempt: 0,
    // 回答状态
    isAnswering: false,
    isPaused: false,
    answerText: '',
    fillerWords: {},
    // 分析结果
    evaluation: null,
    // 统计数据
    stats: null,
    // 自定义题目
    customQuestion: '',
    // AI 美化
    beautifyMode: 'raw',        // 'raw' | 'beautify'
    rawQuestion: '',            // 原始输入
    beautifiedQuestion: '',     // 美化后版本
    beautifyLoading: false,     // 美化请求中
    // 历史记录（旧-按回答记录）
    history: [],
    // 计时相关
    startTime: null,
    pausedTime: null,
    // ASR 相关（语音识别）
    asrStream: null,        // MediaStream 麦克风流
    audioContext: null,     // AudioContext 降采样
    audioNode: null,        // AudioWorkletNode 处理器
    audioGainNode: null,    // GainNode(0) 保持音频图活跃但不输出
    asrWs: null,            // WebSocket 连接
    asrText: '',            // 累积的 ASR 识别文本
    // 麦克风诊断测试状态
    micTestStream: null,    // 麦克风测试的 MediaStream
    micTestContext: null,   // 麦克风测试的 AudioContext
    micTestAnalyser: null,  // 麦克风测试的 AnalyserNode
    micTestSource: null,    // 麦克风测试的源节点
    micTestGain: null,      // 麦克风测试的监听 GainNode
    micTestRAF: null,       // 麦克风测试的 requestAnimationFrame id
    micTestMonitorOn: false,// 麦克风测试是否开启监听
    asrTestStream: null,    // ASR 测试的 MediaStream
    asrTestContext: null,   // ASR 测试的 AudioContext
    asrTestNode: null,      // ASR 测试的 AudioWorkletNode
    asrTestGain: null,      // ASR 测试的 GainNode(0)
    asrTestWs: null,        // ASR 测试的 WebSocket
    asrTestTimer: null,     // ASR 测试的倒计时 timer id
    asrTestCountdown: 10,   // ASR 测试倒计时剩余秒数
    // 草稿恢复标记
    _draftRestoredText: null, // 草稿恢复时已有的文本，新 ASR 文本将追加在其后
    // ========== 历史视图新状态 ==========
    // 筛选条件
    historyFilters: {
        type: '',
        timeStart: '',
        timeEnd: '',
        answerCount: '',
    },
    // 分页
    historyPage: 1,
    historyTotal: 0,
    historyPageSize: 10,
    // 历史问题列表（按题目分组）
    historyQuestions: [],
    // 已展开的题目ID
    expandedQuestionId: null,
    // 展开区域的回答缓存 { [questionId]: answers[] }
    expandedAnswers: {},
    // 详情模式
    detailMode: false,
    detailQuestionId: null,
    detailSelectedAttempt: null,
    detailSidebarQuestions: [],
    detailQuestionData: null,
    detailAnswers: [],
};

// ================================================================
// 填充词检测规则（新方案：密度 + 频率 + 句首 + 簇拥）
// ================================================================

const FILLER_RULES = {
    // 一级填充词：严重的口头禅，高频使用才标记
    level1: ['然后', '就是说', '所以说', '然后呢', '所以说呢'],
    // 二级填充词：有一定语义，但滥用时标记
    level2: ['就是', '反正', '基本上', '其实', '对吧', '这样的话'],
    // 三级语气词：极低语义，但少量出现完全正常
    level3: ['嗯', '呃', '啊', '额'],
    // 语境敏感词：需要上下文判断，多数情况下是正常用词
    contextual: ['这个', '那个', '一个'],
};

// 所有检测词的平铺列表
const ALL_FILLER_WORDS = [
    ...FILLER_RULES.level1,
    ...FILLER_RULES.level2,
    ...FILLER_RULES.level3,
    ...FILLER_RULES.contextual,
];

// 题型定义
const QUESTION_TYPES = [
    { id: 'hot_opinion', name: '热门事件观点', color: '#FF6B6B' },
    { id: 'emotional', name: '情感表达', color: '#F472B6' },
    { id: 'life_reflection', name: '生活感悟', color: '#34D399' },
    { id: 'career', name: '职场沟通', color: '#60A5FA' },
];

// ================================================================
// API 封装
// ================================================================

function getApiBase() {
    return window.__SELF_GROW_API_BASE__ || 'http://127.0.0.1:3001';
}

function getCurrentUserId() {
    // 优先从 AppData 取当前用户 ID
    const id = window.AppData && AppData.user && AppData.user.id;
    if (id) return id;
    // 降级到 localStorage 中保存的登录用户
    try {
        const raw = localStorage.getItem('sg_user');
        if (raw) {
            const user = JSON.parse(raw);
            if (user && user.id) return user.id;
        }
    } catch (e) {}
    // 最终兜底
    return 1;
}

function getUserIdParam() {
    return `user_id=${getCurrentUserId()}`;
}

async function apiPost(path, data) {
    const url = `${getApiBase()}${path}`;
    const options = {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
    };
    if (data !== undefined) {
        options.body = JSON.stringify(data);
    }
    const resp = await fetch(url, options);
    if (!resp.ok) {
        const err = await resp.text().catch(() => '请求失败');
        throw new Error(`API 错误 ${resp.status}: ${err}`);
    }
    return resp.json();
}

async function apiGet(path) {
    const url = `${getApiBase()}${path}`;
    const resp = await fetch(url);
    if (!resp.ok) {
        const err = await resp.text().catch(() => '请求失败');
        throw new Error(`API 错误 ${resp.status}: ${err}`);
    }
    return resp.json();
}

/**
 * 调表达训练的流式 AI 端点
 *
 * 这些端点产出的是 **JSON**（题目/提示/评分），逐字流式没有意义，
 * 所以后端推的是**阶段事件**（正在构思… / 第 2 轮调整… / 正在分析你的回答…）。
 * 这里把阶段提示转发给 onStage，最终从 done 事件里取结果。
 *
 * @param {string} path
 * @param {object} data
 * @param {function} [onStage] 收到阶段提示文本时调用（用于更新按钮/占位文案）
 * @returns {Promise<object>} done 事件的完整内容
 */
async function apiStream(path, data, onStage) {
    const url = `${getApiBase()}${path}`;
    return streamSSE(url, data, {
        onStage: (p) => { if (onStage && p.label) onStage(p.label); },
    });
}

// ================================================================
// 草稿管理（断网/刷新恢复）
// ================================================================

const DRAFT_KEY = 'expr_answering_draft';

function saveDraft() {
    if (!STATE.currentQuestion || !STATE.currentAnswerId) return;
    // 还没开始回答，不存草稿
    if (!STATE.isAnswering && !STATE.answerText && !STATE.asrText) return;

    // 语音模式下用 asrText，打字模式下用 answerText
    // 草稿恢复时：草稿文本 + ASR 新识别文本
    const text = STATE._draftRestoredText
        ? STATE._draftRestoredText + (STATE.asrText || '')
        : STATE.asrText || STATE.answerText || '';

    localStorage.setItem(DRAFT_KEY, JSON.stringify({
        question: STATE.currentQuestion,
        answerId: STATE.currentAnswerId,
        attempt: STATE.currentAttempt,
        answerText: text,
        fillerWords: STATE.fillerWords,
        startTime: STATE.startTime,
        pausedTime: STATE.pausedTime,
        isPaused: STATE.isPaused,
        timestamp: Date.now(),
    }));
}

function clearDraft() {
    localStorage.removeItem(DRAFT_KEY);
}

function getDraft() {
    try {
        const data = localStorage.getItem(DRAFT_KEY);
        return data ? JSON.parse(data) : null;
    } catch {
        return null;
    }
}

function handleResumeDraft() {
    const draft = getDraft();
    if (!draft) return;

    // 恢复状态
    STATE.currentQuestion = draft.question;
    STATE.currentAnswerId = draft.answerId;
    STATE.currentAttempt = draft.attempt;
    STATE.answerText = draft.answerText || '';
    STATE.fillerWords = draft.fillerWords || {};
    STATE.startTime = draft.startTime;
    STATE.pausedTime = draft.pausedTime;
    STATE.isPaused = draft.isPaused || false;
    STATE.isAnswering = true;
    STATE.evaluation = null;

    // 渲染答题视图
    renderAnswerView();
    bindAnswerEvents();

    // 恢复已有内容
    const content = document.getElementById('expr-answer-content');
    if (content && STATE.answerText) {
        content.style.display = 'block';
        content.innerHTML = STATE.answerText;
        const placeholder = document.getElementById('expr-answer-placeholder');
        if (placeholder) placeholder.style.display = 'none';
    }

    // 恢复按钮状态
    document.getElementById('expr-btn-start').disabled = true;
    document.getElementById('expr-btn-pause').disabled = false;
    document.getElementById('expr-btn-done').disabled = false;

    // 记录已恢复的草稿文本，后续 ASR 识别结果会追加在它后面
    STATE._draftRestoredText = STATE.answerText || null;

    // 重新建立音频连接
    (async () => {
        try {
            await startVoiceRecording();
            if (STATE.isPaused) {
                // 如果之前是暂停状态，立即暂停音频
                if (STATE.audioNode && STATE.audioContext) {
                    STATE.audioNode.disconnect();
                    if (STATE.audioGainNode) STATE.audioGainNode.disconnect();
                }
                // 更新按钮为"继续"
                const pauseBtn = document.getElementById('expr-btn-pause');
                if (pauseBtn) {
                    pauseBtn.innerHTML = `<svg viewBox="0 0 24 24" fill="currentColor" width="16" height="16"><path d="M8 5v14l11-7z"/></svg> 继续`;
                }
            }
            saveDraft();
        } catch (e) {
            showToast('重新连接麦克风失败: ' + e.message, 'error');
        }
    })();

    showToast('已恢复之前的回答', 'info');
}

function handleDiscardDraft() {
    clearDraft();
    // 重新渲染训练首页（去掉草稿提示）
    renderTrainView();
    bindEvents();
    showToast('已放弃未完成的回答', 'info');
}

// ================================================================
// 主渲染函数
// ================================================================

async function renderAgent(subPage) {
    currentAgentSubPage = subPage || 'agent';
    const container = document.getElementById('page-extensions');
    container.innerHTML = getAgentLayout();

    // 重置详情模式
    STATE.detailMode = false;
    STATE.detailQuestionId = null;
    STATE.detailSelectedAttempt = null;

    // 加载数据
    await Promise.all([
        loadStats(),
        loadHistory(),
        loadHistoryQuestions(),
    ]);

    // 渲染视图
    renderTrainView();
    bindEvents();
    // 检查 initialTab
    if (subPage === 'history') {
        switchTab('history');
        renderHistoryView();
    }
}

// ================================================================
// HTML 布局
// ================================================================

function getAgentLayout() {
    return `
    <div class="expr">
        <!-- 顶栏：标题 + 滑块 -->
        <div class="page-header page-header--with-icon" style="flex-shrink:0">
            <div class="page-header__icon" style="width:58px;height:58px">${HEADER_ICONS.expression}</div>
            <div style="flex:1;display:flex;justify-content:space-between;align-items:flex-start">
                <div>
                    <h1 class="page-header__title">表达训练</h1>
                    <p class="page-header__subtitle">AI 出题 · 实时反馈 · 提升表达能力</p>
                </div>
                <div class="expr__tabs" id="expr-tabs">
                    <div class="expr__tab-slider" id="expr-tab-slider"></div>
                    <div class="expr__tab expr__tab--active" data-tab="train">训练</div>
                    <div class="expr__tab" data-tab="history">历史</div>
                </div>
            </div>
        </div>

        <!-- 视图容器 -->
        <div class="expr__body" id="expr-body">
            <!-- 训练视图 -->
            <div class="expr__view expr__view--active" id="expr-view-train"></div>
            <!-- 历史视图 -->
            <div class="expr__view" id="expr-view-history"></div>
        </div>
    </div>
    `;
}

// ================================================================
// 视图 1：训练首页
// ================================================================

function renderTrainView() {
    const container = document.getElementById('expr-view-train');

    // 检查是否有草稿
    const draft = getDraft();

    container.innerHTML = `
        <div class="expr__train-layout">
            <!-- 左侧主区域 -->
            <div class="expr__train-main">
                ${draft ? `
                <!-- 草稿恢复提示 -->
                <div class="expr__card expr__draft-card">
                    <div class="expr__draft-header">
                        <span class="expr__draft-icon">📝</span>
                        <span class="expr__draft-text">有未完成的回答，是否继续？</span>
                    </div>
                    <div class="expr__draft-question">${escapeHtml(draft.question.question)}</div>
                    <div class="expr__draft-preview">${escapeHtml((draft.answerText || '').slice(0, 80))}${(draft.answerText || '').length > 80 ? '...' : ''}</div>
                    <div class="expr__draft-actions">
                        <button class="expr__draft-btn expr__draft-btn--resume" onclick="handleResumeDraft()">
                            <svg viewBox="0 0 24 24" fill="currentColor" width="14" height="14"><path d="M8 5v14l11-7z"/></svg>
                            继续回答
                        </button>
                        <button class="expr__draft-btn expr__draft-btn--discard" onclick="handleDiscardDraft()">
                            放弃
                        </button>
                    </div>
                </div>
                ` : ''}

                <!-- 生成问题区 -->
                <div class="expr__card">
                    <div class="expr__card-title">题型选择</div>
                    <div class="expr__type-selector" id="expr-type-selector">
                        ${QUESTION_TYPES.map(t => `
                            <button class="expr__type-btn"
                                    data-type="${t.id}"
                                    style="--type-color: ${t.color}">
                                <span class="expr__type-check">✓</span>
                                ${t.name}
                            </button>
                        `).join('')}
                    </div>
                    <!-- 自定义题目输入框 -->
                    <div class="expr__custom-question" style="margin-bottom:12px">
                        <div class="expr__custom-header">
                            <select class="expr__custom-select" id="expr-custom-mode">
                                <option value="raw">原问题</option>
                                <option value="beautify">AI 美化</option>
                            </select>
                            <div class="expr__beautify-actions" id="expr-beautify-actions" style="display:none">
                                <button class="expr__beautify-btn" id="expr-beautify-btn">美化</button>
                                <button class="expr__undo-btn" id="expr-undo-btn" style="display:none">撤回</button>
                            </div>
                        </div>
                        <input type="text" class="expr__custom-input" id="expr-custom-question"
                               placeholder="输入自定义题目（选填，留空则使用 AI 生成）"
                               value="${STATE.customQuestion || ''}"
                               oninput="STATE.customQuestion=this.value">
                    </div>
                    <button class="expr__gen-btn" id="expr-gen-btn">
                        <span class="expr__gen-btn-text">生成问题</span>
                        <span class="expr__gen-btn-loading" style="display:none">
                            <span class="expr__spinner"></span>
                            <span class="expr__gen-btn-tip">问题生成中</span>
                        </span>
                    </button>
                </div>

                <!-- 最近回答记录 -->
                <div class="expr__card">
                    <div class="expr__card-title">最近回答记录</div>
                    <div class="expr__history-list" id="expr-history-list">
                        ${renderHistoryList()}
                    </div>
                </div>
            </div>

            <!-- 右侧统计面板 -->
            <div class="expr__train-sidebar">
                <div class="expr__card">
                    <div class="expr__card-title">总训练记录</div>
                    <div class="expr__stats" id="expr-stats">
                        ${renderStats()}
                    </div>
                </div>
            </div>
        </div>
    `;
}

function renderStats() {
    const s = STATE.stats;
    if (!s) {
        return `<div class="expr__stats-loading">加载中...</div>`;
    }
    const typeNames = {
        hot_opinion: '热门事件观点',
        emotional: '情感表达',
        life_reflection: '生活感悟',
        career: '职场沟通',
    };
    const colors = {
        hot_opinion: '#FF6B6B',
        emotional: '#F472B6',
        life_reflection: '#34D399',
        career: '#60A5FA',
    };
    // 所有题型全部展示，无记录显示 0
    const allTypes = ['hot_opinion', 'emotional', 'life_reflection', 'career'];
    const typeSummary = s.type_summary || {};

    return `
        <div class="expr__stats-item">
            <div class="expr__stats-num">${s.total_answered}</div>
            <div class="expr__stats-label">累计回答</div>
        </div>
        <div class="expr__stats-item">
            <div class="expr__stats-num">${s.total_days}</div>
            <div class="expr__stats-label">训练天数</div>
        </div>
        ${s.avg_score != null ? `
        <div class="expr__stats-item">
            <div class="expr__stats-num">${s.avg_score}</div>
            <div class="expr__stats-label">近5次平均分</div>
        </div>
        ` : ''}
        <div class="expr__stats-divider"></div>
        <div class="expr__stats-types">
            ${allTypes.map(type => `
                <div class="expr__stats-type-item">
                    <span class="expr__stats-type-dot" style="background:${colors[type] || '#888'}"></span>
                    <span class="expr__stats-type-name">${typeNames[type] || type}</span>
                    <span class="expr__stats-type-count">${typeSummary[type] || 0}</span>
                </div>
            `).join('')}
        </div>
    `;
}

function renderHistoryList() {
    const records = STATE.history;
    if (!records || records.length === 0) {
        return `<div class="expr__history-empty">暂无回答记录</div>`;
    }
    return records.map(r => {
        const preview = (r.answer_full || r.answer_preview || '').slice(0, 100);
        const hasMore = (r.answer_full || '').length > 100;
        return `
            <div class="expr__history-item" data-id="${r.id}"
                 data-full="${encodeURIComponent(r.answer_full || '')}"
                 onclick="showHistoryDetail(this)">
                <div class="expr__history-question">${escapeHtml(r.question)}</div>
                <div class="expr__history-answer">${escapeHtml(preview)}${hasMore ? '...' : ''}</div>
                <div class="expr__history-meta">
                    <span class="expr__history-type ${r.question_type}">${getTypeName(r.question_type)}</span>
                    ${r.score_total != null ? `<span class="expr__history-score">${r.score_total}分</span>` : ''}
                    <span class="expr__history-date">${formatDateTime(r.created_at)}</span>
                </div>
            </div>
        `;
    }).join('');
}

// ================================================================
// 视图 2：答题训练
// ================================================================

function renderAnswerView() {
    const q = STATE.currentQuestion;
    if (!q) return;

    const container = document.getElementById('expr-view-train');
    container.innerHTML = `
        <div class="expr__answer-layout">
            <!-- 左侧答题区 -->
            <div class="expr__answer-main">
                <!-- 题目 -->
                <div class="expr__card expr__question-card">
                    <div class="expr__question-header">
                        <span class="expr__question-type ${q.question_type}">${getTypeName(q.question_type)}</span>
                        <span class="expr__question-attempt">第 ${STATE.currentAttempt} 次回答</span>
                    </div>
                    <div class="expr__question-text">${escapeHtml(q.question)}</div>
                </div>

                <!-- 控制按钮 -->
                <div class="expr__answer-controls">
                    <div class="expr__ctrl-group">
                        <button class="expr__ctrl-btn expr__ctrl-btn--start" id="expr-btn-start"
                                onclick="handleStartAnswer()">
                            <svg viewBox="0 0 24 24" fill="currentColor" width="16" height="16"><path d="M8 5v14l11-7z"/></svg>
                            开始回答
                        </button>
                        <button class="expr__ctrl-btn expr__ctrl-btn--pause" id="expr-btn-pause"
                                onclick="handlePauseAnswer()" disabled>
                            <svg viewBox="0 0 24 24" fill="currentColor" width="16" height="16"><path d="M6 4h4v16H6zM14 4h4v16h-4z"/></svg>
                            暂停
                        </button>
                        <button class="expr__ctrl-btn expr__ctrl-btn--done" id="expr-btn-done"
                                onclick="handleDoneAnswer()" disabled>
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16"><path d="M20 6L9 17l-5-5"/></svg>
                            完成回答
                        </button>
                    </div>
                    <button class="expr__ctrl-btn expr__ctrl-btn--mic-test" id="expr-btn-mic-test"
                            onclick="showMicDiagnosticModal()">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16"><path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><line x1="12" y1="19" x2="12" y2="23"/><line x1="8" y1="23" x2="16" y2="23"/></svg>
                        测试麦克风
                    </button>
                </div>

                <!-- 回答内容显示区 -->
                <div class="expr__answer-display" id="expr-answer-display">
                    <div class="expr__answer-placeholder" id="expr-answer-placeholder">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="48" height="48" opacity="0.3"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z"/></svg>
                        <p>点击「开始回答」后，对着麦克风说话，语音将实时转写为文字</p>
                    </div>
                    <div class="expr__answer-content" id="expr-answer-content" style="display:none"></div>
                </div>

                <!-- AI 分析按钮 + 返回按钮 -->
                <div class="expr__ai-section" id="expr-ai-section" style="display:none">
                    <button class="expr__ai-btn" id="expr-ai-btn" onclick="handleAIEvaluate()">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="18" height="18"><path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/></svg>
                        AI 分析
                    </button>
                    <button class="expr__back-btn" id="expr-back-btn" onclick="handleBackToTrain()">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="18" height="18"><path d="M19 12H5m7-7l-7 7 7 7"/></svg>
                        返回
                    </button>
                </div>

                <!-- AI 分析结果 -->
                <div class="expr__evaluation" id="expr-evaluation" style="display:none"></div>
            </div>

            <!-- 右侧提示面板 -->
            <div class="expr__answer-sidebar">
                <div class="expr__card">
                    <div class="expr__card-title">答题提示</div>
                    <div class="expr__hints" id="expr-hints">
                        ${renderHintsLoading()}
                    </div>
                </div>
            </div>
        </div>
    `;
}

function renderHintsLoading() {
    return ['提示一', '提示二', '提示三'].map(title => `
        <div class="expr__hint-group">
            <button class="expr__hint-toggle" onclick="toggleHintDirection(this)">
                <span class="expr__hint-toggle-label">${title}</span>
                <svg class="expr__hint-arrow" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><path d="M6 9l6 6 6-6"/></svg>
            </button>
            <div class="expr__hint-direction" style="display:none">
                <div class="expr__hint-loading">⏳ 提示生成中...</div>
            </div>
        </div>
    `).join('');
}

function renderHints(hints) {
    // 如果 hints 是数组且包含 direction 字段 → 新格式
    if (hints && Array.isArray(hints) && hints.length > 0 && hints[0].direction) {
        return hints.map((h, i) => {
            const title = h.title || `提示${'一二三'[i] || i + 1}`;
            const direction = h.direction || '';
            const examples = h.examples || [];
            return `
                <div class="expr__hint-group">
                    <button class="expr__hint-toggle" onclick="toggleHintDirection(this)">
                        <span class="expr__hint-toggle-label">${escapeHtml(title)}</span>
                        <svg class="expr__hint-arrow" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><path d="M6 9l6 6 6-6"/></svg>
                    </button>
                    <div class="expr__hint-direction" style="display:none">
                        <div class="expr__hint-direction-text">${escapeHtml(direction)}</div>
                        ${examples.length > 0 ? `
                            <button class="expr__hint-examples-toggle" onclick="toggleHintExamples(this)">
                                <span>查看例子</span>
                                <svg class="expr__hint-examples-arrow" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="12" height="12"><path d="M6 9l6 6 6-6"/></svg>
                            </button>
                            <div class="expr__hint-examples" style="display:none">
                                ${examples.map(ex => `<div class="expr__hint-example">• ${escapeHtml(ex)}</div>`).join('')}
                            </div>
                        ` : ''}
                    </div>
                </div>
            `;
        }).join('');
    }
    // 旧格式兼容（普通字符串提示）
    if (hints && Array.isArray(hints) && hints.length > 0) {
        return hints.map((h, i) => {
            const title = typeof h === 'string' ? `提示 ${i + 1}` : (h.title || `提示 ${i + 1}`);
            const content = typeof h === 'string' ? h : (h.content || '');
            return `
                <div class="expr__hint-group">
                    <button class="expr__hint-toggle" onclick="toggleHintDirection(this)">
                        <span class="expr__hint-toggle-label">${escapeHtml(title)}</span>
                        <svg class="expr__hint-arrow" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><path d="M6 9l6 6 6-6"/></svg>
                    </button>
                    <div class="expr__hint-direction" style="display:none">
                        <div class="expr__hint-direction-text">${escapeHtml(content)}</div>
                    </div>
                </div>
            `;
        }).join('');
    }
    return `<div class="expr__hints-empty">暂无提示</div>`;
}

function renderEvaluation() {
    const ev = STATE.evaluation;
    if (!ev) return '';

    const scores = ev.scores || {};
    const scoreItems = [
        { key: 'fluency', label: '流畅度', color: '#60A5FA' },
        { key: 'logic', label: '逻辑性', color: '#34D399' },
        { key: 'content', label: '内容质量', color: '#FBBF24' },
        { key: 'language', label: '语言表达', color: '#F472B6' },
    ];

    // 填充词统计
    const fillerHtml = renderFillerStats();

    return `
        <div class="expr__eval-header">
            <div class="expr__eval-total">
                <span class="expr__eval-score">${scores.total || '--'}</span>
                <span class="expr__eval-label">总分</span>
            </div>
            <div class="expr__eval-dims">
                ${scoreItems.map(s => `
                    <div class="expr__eval-dim">
                        <div class="expr__eval-dim-bar" style="background:${s.color}; width:${scores[s.key] || 0}%"></div>
                        <div class="expr__eval-dim-info">
                            <span>${s.label}</span>
                            <span>${scores[s.key] || '--'}</span>
                        </div>
                    </div>
                `).join('')}
            </div>
        </div>
        ${fillerHtml}
        <div class="expr__eval-body">
            ${ev.strengths && ev.strengths.length > 0 ? `
            <div class="expr__eval-section">
                <div class="expr__eval-section-title expr__eval-section-title--good">👍 优点</div>
                <ul class="expr__eval-list">
                    ${ev.strengths.map(s => `<li>${escapeHtml(s)}</li>`).join('')}
                </ul>
            </div>
            ` : ''}
            ${ev.improvements && ev.improvements.length > 0 ? `
            <div class="expr__eval-section">
                <div class="expr__eval-section-title expr__eval-section-title--warn">💪 有待改进</div>
                <ul class="expr__eval-list">
                    ${ev.improvements.map(s => `<li>${escapeHtml(s)}</li>`).join('')}
                </ul>
            </div>
            ` : ''}
            ${ev.suggestion ? `
            <div class="expr__eval-section">
                <div class="expr__eval-section-title expr__eval-section-title--tip">📝 综合建议</div>
                <p class="expr__eval-suggestion">${escapeHtml(ev.suggestion)}</p>
            </div>
            ` : ''}
        </div>
    `;
}

function renderFillerStats() {
    const fw = STATE.fillerWords;
    const entries = Object.entries(fw).filter(([, v]) => v > 0);
    if (entries.length === 0) return '';

    const total = entries.reduce((sum, [, v]) => sum + v, 0);
    return `
        <div class="expr__eval-filler">
            <div class="expr__eval-section-title expr__eval-section-title--warn">🔍 填充词分析</div>
            <div class="expr__eval-filler-tags">
                ${entries.map(([word, count]) => {
                    const level = count >= 5 ? 'high' : count >= 3 ? 'mid' : 'low';
                    return `<span class="expr__filler-tag expr__filler-tag--${level}">${escapeHtml(word)} ×${count}</span>`;
                }).join('')}
                <span class="expr__filler-total">共 ${total} 次</span>
            </div>
        </div>
    `;
}

// ================================================================
// 数据加载
// ================================================================

async function loadStats() {
    try {
        STATE.stats = await apiGet(`/api/expression/stats?${getUserIdParam()}`);
    } catch (e) {
        console.warn('加载统计数据失败:', e);
        STATE.stats = { total_answered: 0, total_days: 0, type_summary: {}, avg_score: null };
    }
}

async function loadHistory() {
    try {
        const data = await apiGet(`/api/expression/history?${getUserIdParam()}&limit=5`);
        STATE.history = data.records || [];
    } catch (e) {
        console.warn('加载历史记录失败:', e);
        STATE.history = [];
    }
}

// ================================================================
// 事件处理
// ================================================================

function bindEvents() {
    // 滑块切换
    const tabs = document.querySelectorAll('.expr__tab');
    tabs.forEach(tab => {
        tab.addEventListener('click', function () {
            const tabName = this.dataset.tab;
            switchTab(tabName);
        });
    });

    // 题型选择
    const typeBtns = document.querySelectorAll('.expr__type-btn');
    typeBtns.forEach(btn => {
        btn.addEventListener('click', function () {
            toggleType(this);
        });
    });

    // 生成问题
    const genBtn = document.getElementById('expr-gen-btn');
    if (genBtn) {
        genBtn.addEventListener('click', debounce(handleGenerate, 300));
    }

    // 模式切换：原问题 / AI 美化
    const modeSelect = document.getElementById('expr-custom-mode');
    if (modeSelect) {
        modeSelect.addEventListener('change', function () {
            const input = document.getElementById('expr-custom-question');
            const actions = document.getElementById('expr-beautify-actions');
            if (this.value === 'beautify') {
                actions.style.display = 'flex';
                // 如果有美化版本则显示美化版，否则显示原始
                if (STATE.beautifiedQuestion) {
                    input.value = STATE.beautifiedQuestion;
                    STATE.customQuestion = STATE.beautifiedQuestion;
                }
            } else {
                actions.style.display = 'none';
                // 切回原问题
                input.value = STATE.rawQuestion || input.value;
                STATE.customQuestion = STATE.rawQuestion || '';
            }
            STATE.beautifyMode = this.value;
        });
    }

    // 美化按钮
    const beautifyBtn = document.getElementById('expr-beautify-btn');
    if (beautifyBtn) {
        beautifyBtn.addEventListener('click', async function () {
            const input = document.getElementById('expr-custom-question');
            const rawText = input.value.trim();
            if (!rawText) {
                showToast('请先输入需要美化的题目', 'warning');
                return;
            }
            STATE.rawQuestion = rawText;
            this.disabled = true;
            this.textContent = '美化中...';
            try {
                const res = await apiPost(`/api/expression/beautify?${getUserIdParam()}`, { text: rawText });
                if (res && res.beautified) {
                    STATE.beautifiedQuestion = res.beautified;
                    input.value = res.beautified;
                    STATE.customQuestion = res.beautified;
                    document.getElementById('expr-undo-btn').style.display = 'inline-flex';
                    showToast('题目已美化', 'success');
                }
            } catch (e) {
                showToast('美化失败: ' + (e.message || '请稍后重试'), 'error');
            } finally {
                this.disabled = false;
                this.textContent = '美化';
            }
        });
    }

    // 撤回按钮
    const undoBtn = document.getElementById('expr-undo-btn');
    if (undoBtn) {
        undoBtn.addEventListener('click', function () {
            const input = document.getElementById('expr-custom-question');
            input.value = STATE.rawQuestion;
            STATE.customQuestion = STATE.rawQuestion;
            STATE.beautifiedQuestion = '';
            this.style.display = 'none';
            showToast('已撤回美化', 'info');
        });
    }
}

function switchTab(tabName) {
    const tabs = document.querySelectorAll('.expr__tab');
    const views = document.querySelectorAll('.expr__view');
    const slider = document.getElementById('expr-tab-slider');

    tabs.forEach((t, i) => {
        const isActive = t.dataset.tab === tabName;
        t.classList.toggle('expr__tab--active', isActive);
        // 移动滑块
        if (isActive && slider) {
            slider.style.transform = i === 0 ? 'translateX(0)' : 'translateX(100%)';
        }
    });
    views.forEach(v => v.classList.toggle('expr__view--active', v.id === `expr-view-${tabName}`));

    // 切换到历史视图时渲染
    if (tabName === 'history' && !STATE.detailMode) {
        renderHistoryView();
    } else if (tabName === 'history' && STATE.detailMode) {
        renderHistoryDetailView();
    }
}

function toggleType(btn) {
    const type = btn.dataset.type;
    const idx = STATE.selectedTypes.indexOf(type);

    if (idx === -1) {
        // 选中
        STATE.selectedTypes.push(type);
        btn.classList.add('expr__type-btn--active');
    } else {
        // 取消选中（允许全部取消）
        STATE.selectedTypes.splice(idx, 1);
        btn.classList.remove('expr__type-btn--active');
    }
}

async function handleGenerate() {
    const btn = document.getElementById('expr-gen-btn');
    const btnText = btn.querySelector('.expr__gen-btn-text');
    const btnLoading = btn.querySelector('.expr__gen-btn-loading');

    // 切换加载状态
    btnText.style.display = 'none';
    btnLoading.style.display = 'flex';
    btn.disabled = true;

    try {
        const customQuestion = (STATE.customQuestion || '').trim();

        if (customQuestion) {
            // 用户输入了自定义题目，调用后端保存到数据库
            const result = await apiStream(`/api/expression/generate?${getUserIdParam()}`, {
                custom_question: customQuestion,
                custom_type: 'custom',
            });
            STATE.currentQuestion = result;
            // 清空输入框 + 重置美化状态
            STATE.customQuestion = '';
            STATE.rawQuestion = '';
            STATE.beautifiedQuestion = '';
            document.getElementById('expr-undo-btn').style.display = 'none';
            const input = document.getElementById('expr-custom-question');
            if (input) input.value = '';
        } else {
            // 无自定义题目，调用 AI 生成
            let types = STATE.selectedTypes;
            // 如果未选择任何题型，随机挑选一个
            if (types.length === 0) {
                const allTypes = QUESTION_TYPES.map(t => t.id);
                types = [allTypes[Math.floor(Math.random() * allTypes.length)]];
            }
            // 流式：后端会推「正在构思…」「第 2 轮调整…」等阶段，直接显示在按钮上
            const result = await apiStream(`/api/expression/generate?${getUserIdParam()}`,
                { types },
                (label) => {
                    const tip = btnLoading && btnLoading.querySelector('.expr__gen-btn-tip');
                    if (tip) tip.textContent = label;
                });
            STATE.currentQuestion = result;
        }

        // 重置回答状态（不创建回答记录，等用户点击「开始回答」时再创建）
        STATE.currentAnswerId = null;
        STATE.currentAttempt = 0;
        STATE.answerText = '';
        STATE.fillerWords = {};
        STATE.evaluation = null;
        STATE.isAnswering = false;
        STATE.isPaused = false;

        // 切换到答题视图
        renderAnswerView();
        bindAnswerEvents();

        // 异步加载提示（不阻塞答题）
        if (!customQuestion && STATE.currentQuestion?.id) {
            loadHintsAsync(STATE.currentQuestion.id);
        }
    } catch (e) {
        showToast('生成问题失败: ' + e.message, 'error');
        btnText.style.display = 'block';
        btnLoading.style.display = 'none';
        btn.disabled = false;
    }
}

function bindAnswerEvents() {
    // 提示面板按钮由 onclick 处理，无需额外绑定
}

// 异步加载提示
async function loadHintsAsync(questionId) {
    try {
        // 流式：命中缓存时后端会立刻发 done，走的还是同一条解析路径
        const result = await apiStream(`/api/expression/generate-hints?${getUserIdParam()}`, {
            question_id: questionId,
        });
        const hints = result.hints || [];
        // 更新提示面板
        const hintsContainer = document.getElementById('expr-hints');
        if (hintsContainer) {
            hintsContainer.innerHTML = renderHints(hints);
        }
    } catch (e) {
        console.warn('加载提示失败:', e);
        // 保持显示"提示生成中"状态
    }
}

// 提示面板交互（双层展开）
function toggleHintDirection(btn) {
    const content = btn.nextElementSibling;
    const isHidden = content.style.display === 'none' || !content.style.display;
    content.style.display = isHidden ? 'block' : 'none';
    btn.classList.toggle('expr__hint-toggle--open', isHidden);
}

// 例子展开/收起（0.1s 防抖）
const toggleHintExamples = debounceClick(function _toggleHintExamples(btn) {
    const content = btn.nextElementSibling;
    const isHidden = content.style.display === 'none' || !content.style.display;
    content.style.display = isHidden ? 'block' : 'none';
    const arrow = btn.querySelector('.expr__hint-examples-arrow');
    if (arrow) {
        arrow.style.transform = isHidden ? 'rotate(180deg)' : 'rotate(0deg)';
    }
});

// ================================================================
// 答题控制
// ================================================================

// 0.1s 防抖包装
function debounceClick(fn) {
    let lastCall = 0;
    return function (...args) {
        const now = Date.now();
        if (now - lastCall < 100) return; // 0.1 秒内重复点击无响应
        lastCall = now;
        return fn.apply(this, args);
    };
}

// 带防抖的函数引用
const handleStartAnswer = debounceClick(async function _handleStartAnswer() {
    if (STATE.isAnswering) return;

    STATE.isAnswering = true;
    STATE.isPaused = false;
    STATE.startTime = Date.now();
    STATE.asrText = '';

    // 更新按钮状态
    document.getElementById('expr-btn-start').disabled = true;
    document.getElementById('expr-btn-pause').disabled = false;
    document.getElementById('expr-btn-done').disabled = false;

    // 显示回答区域
    const placeholder = document.getElementById('expr-answer-placeholder');
    const content = document.getElementById('expr-answer-content');
    if (placeholder) placeholder.style.display = 'none';
    if (content) {
        content.style.display = 'block';
        content.innerHTML = '';
        content.contentEditable = false; // 语音模式，只读
    }

    // 添加录音指示器
    const controls = document.querySelector('.expr__answer-controls');
    const indicator = document.createElement('div');
    indicator.className = 'expr__recording-indicator';
    indicator.id = 'expr-recording-indicator';
    indicator.innerHTML = `
        <span class="expr__recording-dot"></span>
        <span class="expr__recording-label">录音中...</span>
    `;
    if (controls) controls.after(indicator);

    try {
        // 如果还没有回答记录（首次点击「开始回答」），先创建
        if (!STATE.currentAnswerId) {
            const answerResult = await apiPost(`/api/expression/answer?${getUserIdParam()}`, {
                question_id: STATE.currentQuestion.id,
            });
            STATE.currentAnswerId = answerResult.answer_id;
            STATE.currentAttempt = answerResult.attempt;
        }
        // 如果已有回答记录（草稿恢复），直接使用已有值

        // 开始录音 + ASR
        await startVoiceRecording();
        // 存草稿
        saveDraft();
        showToast('开始回答，请对着麦克风表达你的观点', 'success');
    } catch (e) {
        showToast('启动麦克风失败: ' + e.message, 'error');
        STATE.isAnswering = false;
        document.getElementById('expr-btn-start').disabled = false;
        document.getElementById('expr-btn-pause').disabled = true;
        document.getElementById('expr-btn-done').disabled = true;
        const ind = document.getElementById('expr-recording-indicator');
        if (ind) ind.remove();
    }
});

const handlePauseAnswer = debounceClick(function _handlePauseAnswer() {
    if (!STATE.isAnswering) return;

    STATE.isPaused = !STATE.isPaused;
    const btn = document.getElementById('expr-btn-pause');
    const indicator = document.getElementById('expr-recording-indicator');

    if (STATE.isPaused) {
        // 暂停：断开音频图，暂停 ASR 发送
        if (STATE.audioNode && STATE.audioContext) {
            STATE.audioNode.disconnect();
            if (STATE.audioGainNode) STATE.audioGainNode.disconnect();
        }
        btn.innerHTML = `
            <svg viewBox="0 0 24 24" fill="currentColor" width="16" height="16"><path d="M8 5v14l11-7z"/></svg>
            继续
        `;
        if (indicator) {
            indicator.querySelector('.expr__recording-dot').style.animation = 'none';
            indicator.querySelector('.expr__recording-label').textContent = '已暂停';
        }
        showToast('已暂停', 'info');
    } else {
        // 继续：重新连接音频图
        if (STATE.audioNode && STATE.audioContext && STATE.asrStream) {
            const source = STATE.audioContext.createMediaStreamSource(STATE.asrStream);
            source.connect(STATE.audioNode);
            if (STATE.audioGainNode) {
                STATE.audioNode.connect(STATE.audioGainNode);
                STATE.audioGainNode.connect(STATE.audioContext.destination);
            } else {
                STATE.audioNode.connect(STATE.audioContext.destination);
            }
        }
        btn.innerHTML = `
            <svg viewBox="0 0 24 24" fill="currentColor" width="16" height="16"><path d="M6 4h4v16H6zM14 4h4v16h-4z"/></svg>
            暂停
        `;
        if (indicator) {
            indicator.querySelector('.expr__recording-dot').style.animation = '';
            indicator.querySelector('.expr__recording-label').textContent = '录音中...';
        }
        showToast('继续回答', 'info');
    }
});

const handleDoneAnswer = debounceClick(function _handleDoneAnswer() {
    if (!STATE.isAnswering) return;

    STATE.isAnswering = false;
    STATE.isPaused = false;

    // 禁用按钮
    document.getElementById('expr-btn-start').disabled = true;
    document.getElementById('expr-btn-pause').disabled = true;
    document.getElementById('expr-btn-done').disabled = true;

    // 移除录音指示器
    const indicator = document.getElementById('expr-recording-indicator');
    if (indicator) indicator.remove();

    // 保存当前 ASR 文本（先于 stopVoiceRecording，避免最后一条消息丢失）
    // 草稿恢复时：草稿文本 + 新 ASR 文本 = 完整回答
    STATE.answerText = STATE._draftRestoredText
        ? STATE._draftRestoredText + (STATE.asrText || '')
        : STATE.asrText || STATE.answerText;
    STATE._draftRestoredText = null;

    // 停止录音
    stopVoiceRecording();

    // 提交到后端
    saveAnswerText();

    // 清除草稿
    clearDraft();

    // 显示 AI 分析按钮
    document.getElementById('expr-ai-section').style.display = 'block';

    showToast('回答已保存，点击「AI 分析」获取评分建议', 'success');
});

// ================================================================
// 语音录制 + ASR WebSocket
// ================================================================

function getWsBase() {
    // 从 API_BASE 推导 WebSocket 地址
    const apiBase = window.__SELF_GROW_API_BASE__ || 'http://127.0.0.1:3001';
    return apiBase.replace(/^http/, 'ws');
}

async function startVoiceRecording() {
    try {
        // 请求麦克风权限
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        STATE.asrStream = stream;

        // 建立 WebSocket 连接
        STATE.asrWs = connectASRWebSocket();

        // 创建 AudioContext
        const audioContext = new (window.AudioContext || window.webkitAudioContext)();
        STATE.audioContext = audioContext;

        // 创建源节点
        const source = audioContext.createMediaStreamSource(stream);

        // 创建 AudioWorklet 处理器（内联注册，含降采样 48kHz→16kHz + 缓冲200ms）
        const workletCode = `
            class PCMProcessor extends AudioWorkletProcessor {
                constructor() {
                    super();
                    this.inputSampleRate = sampleRate;  // 浏览器实际采样率（通常48000）
                    this.targetRate = 16000;            // 后端期望采样率
                    this.ratio = this.inputSampleRate / this.targetRate;
                    this.buffer = [];                   // 降采样前的原始样本缓冲
                    this.pcmBuffer = [];                // 降采样后的PCM缓冲，攒够3200发送
                    this.TARGET_CHUNK = 3200;           // 每次发送3200个样本（200ms @ 16kHz）
                }
                process(inputs, outputs, parameters) {
                    const input = inputs[0];
                    if (input && input.length > 0) {
                        const channelData = input[0];
                        // 累积原始采样
                        for (let i = 0; i < channelData.length; i++) {
                            this.buffer.push(channelData[i]);
                        }
                        // 降采样：按比例取出目标样本
                        const needed = Math.floor(this.buffer.length / this.ratio);
                        if (needed > 0) {
                            for (let i = 0; i < needed; i++) {
                                const srcIdx = Math.round(i * this.ratio);
                                const s = Math.max(-1, Math.min(1, this.buffer[srcIdx]));
                                const pcm = s < 0 ? s * 0x8000 : s * 0x7FFF;
                                this.pcmBuffer.push(pcm);
                            }
                            // 移除已处理的原始样本
                            this.buffer.splice(0, Math.round(needed * this.ratio));
                        }
                        // 攒够3200个PCM样本（200ms）才发送
                        if (this.pcmBuffer.length >= this.TARGET_CHUNK) {
                            const chunk = new Int16Array(this.TARGET_CHUNK);
                            for (let i = 0; i < this.TARGET_CHUNK; i++) {
                                chunk[i] = this.pcmBuffer[i];
                            }
                            this.pcmBuffer.splice(0, this.TARGET_CHUNK);
                            this.port.postMessage(chunk.buffer, [chunk.buffer]);
                        }
                    }
                    return true;
                }
            }
            registerProcessor('pcm-processor', PCMProcessor);
        `;

        const blob = new Blob([workletCode], { type: 'application/javascript' });
        const blobUrl = URL.createObjectURL(blob);
        await audioContext.audioWorklet.addModule(blobUrl);
        URL.revokeObjectURL(blobUrl);

        const workletNode = new AudioWorkletNode(audioContext, 'pcm-processor');
        STATE.audioNode = workletNode;

        // GainNode(0) 保持音频图完整但不输出声音到扬声器
        const gainNode = audioContext.createGain();
        gainNode.gain.value = 0;
        STATE.audioGainNode = gainNode;

        workletNode.port.onmessage = function (event) {
            if (STATE.isPaused) return;
            if (!STATE.asrWs || STATE.asrWs.readyState !== WebSocket.OPEN) return;
            STATE.asrWs.send(event.data);
        };

        // 连接音频图：source → workletNode → gainNode(0) → destination
        source.connect(workletNode);
        workletNode.connect(gainNode);
        gainNode.connect(audioContext.destination);

        // 等待 WebSocket 就绪
        await new Promise((resolve, reject) => {
            const ws = STATE.asrWs;
            if (!ws) { reject(new Error('WebSocket 未创建')); return; }
            // 【修复】WebSocket 可能已经连接成功（AudioWorklet 初始化期间就连上了）
            if (ws.readyState === WebSocket.OPEN) { resolve(); return; }
            const timeout = setTimeout(() => reject(new Error('WebSocket 连接超时')), 10000);
            ws.onopen = function () {
                clearTimeout(timeout);
                resolve();
            };
            ws.onerror = function () {
                clearTimeout(timeout);
                reject(new Error('WebSocket 连接失败'));
            };
        });

    } catch (e) {
        // 出错了，清理资源
        stopVoiceRecording();
        throw e;
    }
}

/**
 * WebSocket 连接用的鉴权 query
 *
 * ⚠️ 浏览器原生 WebSocket **不支持自定义 header**，所以 token 只能挂在 URL 上
 * （与 EventSource 的 SSE 是同一个限制）。
 *
 * 之所以不能再像以前那样传 `?user_id=`：那等于让客户端「自己声明自己是谁」，
 * 谁都能填别人的 id —— 后端现已改为校验 `?token=<access_token>` 并拒绝无 token
 * 的连接（除非 TRUSTED_MODE）。
 */
function getWsAuthQuery() {
    const token = (window.Auth && Auth.getToken && Auth.getToken()) || '';
    return token ? `token=${encodeURIComponent(token)}` : '';
}

function connectASRWebSocket() {
    const ws = new WebSocket(`${getWsBase()}/ws/asr?${getWsAuthQuery()}`);
    ws.binaryType = 'arraybuffer';

    // 累积的完整文本
    let accumulatedFull = '';
    // 上一次收到的完整文本（用于去重：DashScope 可能重复回调同一句）
    let lastFullText = '';

    ws.onmessage = function (e) {
        try {
            const data = JSON.parse(e.data);
            if (data.type === 'transcript') {
                const text = data.text || '';
                if (!text) return;

                if (data.is_end) {
                    // 完整句子：只追加增量（去重）
                    if (text !== lastFullText) {
                        // 计算增量：新文本减去已累积的部分
                        if (text.startsWith(accumulatedFull)) {
                            accumulatedFull += text.slice(accumulatedFull.length);
                        } else {
                            // 兜底：直接追加
                            accumulatedFull += text;
                        }
                        lastFullText = text;
                    }
                } else {
                    // 部分结果：用累积文本 + 当前部分结果显示
                    // 不保存到 accumulatedFull
                }

                // 最终显示
                const fullText = data.is_end
                    ? accumulatedFull
                    : accumulatedFull + text;

                STATE.asrText = fullText;

                // 更新显示
                const content = document.getElementById('expr-answer-content');
                if (content) {
                    const displayText = STATE._draftRestoredText
                        ? STATE._draftRestoredText + fullText
                        : fullText;
                    const fillerWords = detectFillerWordsV2(displayText);
                    STATE.fillerWords = fillerWords;
                    highlightFillersV2(content, displayText, fillerWords);
                }
            } else if (data.type === 'error') {
                console.warn('ASR 错误:', data.message);
                showToast('语音识别出错: ' + data.message, 'error');
            }
        } catch (e) {
            console.warn('ASR 消息解析失败:', e);
        }
    };

    ws.onerror = function (e) {
        console.warn('ASR WebSocket 错误:', e);
    };

    ws.onclose = function () {
        console.log('ASR WebSocket 连接已关闭');
    };

    return ws;
}

function stopVoiceRecording() {
    // 关闭 WebSocket
    if (STATE.asrWs) {
        try {
            if (STATE.asrWs.readyState === WebSocket.OPEN || STATE.asrWs.readyState === WebSocket.CONNECTING) {
                STATE.asrWs.close();
            }
        } catch (e) {
            console.warn('关闭 WebSocket 异常:', e);
        }
        STATE.asrWs = null;
    }

    // 断开音频节点
    if (STATE.audioNode) {
        try {
            STATE.audioNode.disconnect();
        } catch (e) { /* ignore */ }
        STATE.audioNode = null;
    }

    // 断开 GainNode
    if (STATE.audioGainNode) {
        try {
            STATE.audioGainNode.disconnect();
        } catch (e) { /* ignore */ }
        STATE.audioGainNode = null;
    }

    // 关闭 AudioContext
    if (STATE.audioContext) {
        try {
            STATE.audioContext.close();
        } catch (e) { /* ignore */ }
        STATE.audioContext = null;
    }

    // 释放麦克风
    if (STATE.asrStream) {
        try {
            STATE.asrStream.getTracks().forEach(t => t.stop());
        } catch (e) { /* ignore */ }
        STATE.asrStream = null;
    }
}

/**
 * 麦克风诊断弹窗（双标签：麦克风测试 + 语音识别测试）
 * ================================================================ */

let _micTestActiveTab = 'mic'; // 'mic' | 'asr'

function showMicDiagnosticModal() {
    _micTestActiveTab = 'mic';
    const html = `
    <div class="expr__diag" id="expr-diag">
        <!-- 标签切换 -->
        <div class="expr__diag-tabs">
            <button class="expr__diag-tab expr__diag-tab--active" data-diag-tab="mic" onclick="switchMicTestTab('mic')">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><line x1="12" y1="19" x2="12" y2="23"/><line x1="8" y1="23" x2="16" y2="23"/></svg>
                麦克风测试
            </button>
            <button class="expr__diag-tab" data-diag-tab="asr" onclick="switchMicTestTab('asr')">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z"/></svg>
                语音识别测试
            </button>
        </div>
        <!-- 内容容器 -->
        <div class="expr__diag-body" id="expr-diag-body">
            ${renderMicTestTab()}
        </div>
    </div>
    `;
    openModal('🎤 麦克风诊断', html, false);
    // 弹窗关闭时清理资源
    const modal = document.getElementById('modal');
    if (modal) {
        const observer = new MutationObserver(() => {
            if (modal.style.display === 'none' || !modal.querySelector('.expr__diag')) {
                stopAllMicTests();
                observer.disconnect();
            }
        });
        observer.observe(modal, { attributes: true, attributeFilter: ['style'] });
    }
}

function switchMicTestTab(tab) {
    if (tab === _micTestActiveTab) return;
    // 停止当前测试
    stopAllMicTests();
    _micTestActiveTab = tab;
    // 切换标签高亮
    document.querySelectorAll('.expr__diag-tab').forEach(el => {
        el.classList.toggle('expr__diag-tab--active', el.dataset.diagTab === tab);
    });
    // 渲染对应内容
    const body = document.getElementById('expr-diag-body');
    if (body) {
        body.innerHTML = tab === 'mic' ? renderMicTestTab() : renderASRTestTab();
    }
}

// ================================================================
// 麦克风测试模式
// ================================================================

function renderMicTestTab() {
    return `
    <div class="expr__diag-panel" id="expr-diag-mic-panel">
        <div class="expr__diag-actions">
            <button class="expr__diag-btn expr__diag-btn--start" id="expr-diag-mic-start" onclick="startMicTest()">
                ▶ 开始测试
            </button>
            <button class="expr__diag-btn expr__diag-btn--stop" id="expr-diag-mic-stop" onclick="stopMicTest()" disabled>
                ⏹ 停止
            </button>
        </div>
        <!-- 音量电平 -->
        <div class="expr__diag-section">
            <div class="expr__diag-label">音量电平</div>
            <div class="expr__diag-volume" id="expr-diag-volume">
                ${Array(5).fill(0).map(() => `<div class="expr__diag-volume-bar"><div class="expr__diag-volume-fill" style="width:0%"></div></div>`).join('')}
            </div>
        </div>
        <!-- 实时监听开关 -->
        <div class="expr__diag-section">
            <div class="expr__diag-label">实时监听</div>
            <div class="expr__diag-monitor">
                <button class="expr__diag-toggle" id="expr-diag-monitor-btn" onclick="toggleMicTestMonitor()" disabled>
                    🔇 关闭监听
                </button>
                <span class="expr__diag-hint">⚠️ 建议佩戴耳机，避免啸叫</span>
            </div>
        </div>
        <!-- 状态信息 -->
        <div class="expr__diag-info" id="expr-diag-mic-info">
            <div class="expr__diag-status">状态: <span class="expr__diag-status-idle">等待开始</span></div>
            <div class="expr__diag-device" id="expr-diag-device">设备: --</div>
        </div>
    </div>`;
}

async function startMicTest() {
    try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        STATE.micTestStream = stream;

        const deviceLabel = stream.getAudioTracks()[0]?.label || '未知设备';
        document.getElementById('expr-diag-device').textContent = '设备: ' + deviceLabel;

        const audioContext = new (window.AudioContext || window.webkitAudioContext)();
        STATE.micTestContext = audioContext;

        const source = audioContext.createMediaStreamSource(stream);
        STATE.micTestSource = source;

        const analyser = audioContext.createAnalyser();
        analyser.fftSize = 256;
        STATE.micTestAnalyser = analyser;

        // 监听增益（默认关闭，仅连接但不输出）
        const gainNode = audioContext.createGain();
        gainNode.gain.value = 0;
        STATE.micTestGain = gainNode;

        source.connect(analyser);
        analyser.connect(gainNode);
        gainNode.connect(audioContext.destination);

        // 更新按钮状态
        document.getElementById('expr-diag-mic-start').disabled = true;
        document.getElementById('expr-diag-mic-stop').disabled = false;
        document.getElementById('expr-diag-monitor-btn').disabled = false;
        setMicTestStatus('● 监听中', 'listening');

        // 启动音量动画
        startVolumeAnimation();

    } catch (e) {
        setMicTestStatus('❌ 麦克风启动失败: ' + e.message, 'error');
    }
}

function startVolumeAnimation() {
    const bars = document.querySelectorAll('.expr__diag-volume-fill');
    if (!bars.length) return;

    let lastTimestamp = 0;
    const FPS_INTERVAL = 1000 / 30; // 30fps 刷新

    function animate(timestamp) {
        if (!STATE.micTestAnalyser || !STATE.micTestContext) return;

        if (timestamp - lastTimestamp >= FPS_INTERVAL) {
            lastTimestamp = timestamp;

            const dataArray = new Uint8Array(STATE.micTestAnalyser.frequencyBinCount);
            STATE.micTestAnalyser.getByteTimeDomainData(dataArray);

            // 计算 RMS 音量
            let sum = 0;
            for (let i = 0; i < dataArray.length; i++) {
                const value = (dataArray[i] - 128) / 128;
                sum += value * value;
            }
            const rms = Math.sqrt(sum / dataArray.length);
            // 转成百分比，加一点非线性映射让低音量更明显
            const pct = Math.min(100, Math.round(rms * 180));

            // 更新 5 条柱：模拟历史滚动效果
            if (!STATE._micVolumeHistory) STATE._micVolumeHistory = [];
            STATE._micVolumeHistory.push(pct);
            if (STATE._micVolumeHistory.length > 5) STATE._micVolumeHistory.shift();

            const history = STATE._micVolumeHistory;
            bars.forEach((bar, i) => {
                const idx = history.length - 5 + i;
                const val = idx >= 0 ? history[idx] : 0;
                bar.style.width = val + '%';
                // 颜色渐变：低音量绿色 → 中音量黄色 → 高音量红色
                if (val < 30) bar.style.background = '#34D399';
                else if (val < 60) bar.style.background = '#FBBF24';
                else bar.style.background = '#EF4444';
            });
        }

        STATE.micTestRAF = requestAnimationFrame(animate);
    }

    STATE.micTestRAF = requestAnimationFrame(animate);
}

function stopMicTest() {
    if (STATE.micTestRAF) {
        cancelAnimationFrame(STATE.micTestRAF);
        STATE.micTestRAF = null;
    }
    STATE._micVolumeHistory = null;

    if (STATE.micTestSource) {
        try { STATE.micTestSource.disconnect(); } catch (e) {}
        STATE.micTestSource = null;
    }
    if (STATE.micTestAnalyser) {
        try { STATE.micTestAnalyser.disconnect(); } catch (e) {}
        STATE.micTestAnalyser = null;
    }
    if (STATE.micTestGain) {
        try { STATE.micTestGain.disconnect(); } catch (e) {}
        STATE.micTestGain = null;
    }
    if (STATE.micTestContext) {
        try { STATE.micTestContext.close(); } catch (e) {}
        STATE.micTestContext = null;
    }
    if (STATE.micTestStream) {
        try { STATE.micTestStream.getTracks().forEach(t => t.stop()); } catch (e) {}
        STATE.micTestStream = null;
    }
    STATE.micTestMonitorOn = false;

    // 重置按钮
    const startBtn = document.getElementById('expr-diag-mic-start');
    const stopBtn = document.getElementById('expr-diag-mic-stop');
    const monitorBtn = document.getElementById('expr-diag-monitor-btn');
    if (startBtn) startBtn.disabled = false;
    if (stopBtn) stopBtn.disabled = true;
    if (monitorBtn) {
        monitorBtn.disabled = true;
        monitorBtn.innerHTML = '🔇 关闭监听';
    }

    // 重置音量条
    document.querySelectorAll('.expr__diag-volume-fill').forEach(el => {
        el.style.width = '0%';
        el.style.background = '';
    });

    setMicTestStatus('已停止', 'idle');
}

function toggleMicTestMonitor() {
    if (!STATE.micTestGain || !STATE.micTestContext) return;
    STATE.micTestMonitorOn = !STATE.micTestMonitorOn;
    STATE.micTestGain.gain.value = STATE.micTestMonitorOn ? 0.5 : 0;
    const btn = document.getElementById('expr-diag-monitor-btn');
    if (btn) {
        btn.innerHTML = STATE.micTestMonitorOn
            ? '🔊 开启监听'
            : '🔇 关闭监听';
    }
}

function setMicTestStatus(text, type) {
    const info = document.getElementById('expr-diag-mic-info');
    if (!info) return;
    const statusEl = info.querySelector('.expr__diag-status');
    if (statusEl) {
        statusEl.innerHTML = '状态: <span class="expr__diag-status-' + type + '">' + text + '</span>';
    }
}

// ================================================================
// 语音识别测试模式
// ================================================================

function renderASRTestTab() {
    return `
    <div class="expr__diag-panel" id="expr-diag-asr-panel">
        <div class="expr__diag-actions">
            <button class="expr__diag-btn expr__diag-btn--start" id="expr-diag-asr-start" onclick="startASRTest()">
                ▶ 开始测试
            </button>
            <button class="expr__diag-btn expr__diag-btn--stop" id="expr-diag-asr-stop" onclick="stopASRTest()" disabled>
                ⏹ 停止
            </button>
        </div>
        <!-- 倒计时 -->
        <div class="expr__diag-section">
            <div class="expr__diag-label">倒计时</div>
            <div class="expr__diag-countdown" id="expr-diag-countdown">
                <span class="expr__diag-countdown-num">--</span>
                <span class="expr__diag-countdown-unit">秒</span>
            </div>
        </div>
        <!-- 识别结果 -->
        <div class="expr__diag-section">
            <div class="expr__diag-label">识别结果</div>
            <div class="expr__diag-result" id="expr-diag-asr-result">
                <span class="expr__diag-result-placeholder">点击「开始测试」后，对着麦克风说话...</span>
            </div>
        </div>
        <!-- 状态信息 -->
        <div class="expr__diag-info" id="expr-diag-asr-info">
            <div class="expr__diag-status">状态: <span class="expr__diag-status-idle">等待开始</span></div>
        </div>
    </div>`;
}

async function startASRTest() {
    const countdownEl = document.getElementById('expr-diag-countdown-num');
    const resultEl = document.getElementById('expr-diag-asr-result');
    const startBtn = document.getElementById('expr-diag-asr-start');
    const stopBtn = document.getElementById('expr-diag-asr-stop');

    startBtn.disabled = true;
    stopBtn.disabled = false;
    // 【修复】连接前显示"连接中"，不显示倒计时数字
    if (countdownEl) {
        countdownEl.textContent = '--';
        countdownEl.style.fontSize = '28px';
    }
    if (resultEl) resultEl.innerHTML = '<span class="expr__diag-result-placeholder">正在连接麦克风和语音识别服务...</span>';
    setASRTestStatus('⏳ 正在连接...', 'connecting');
    // 清空累积文本
    STATE.asrTestFullText = '';

    // 总初始化超时（15秒）
    const CONNECT_TIMEOUT = 15000;
    let connectTimedOut = false;
    let connectTimeoutId = setTimeout(function () {
        connectTimedOut = true;
        stopASRTestInternal();
        setASRTestStatus('❌ 连接超时，请检查后端服务是否运行', 'error');
        if (resultEl) resultEl.innerHTML = '<span class="expr__diag-status-error">连接超时，请检查后端服务是否运行</span>';
        if (countdownEl) { countdownEl.textContent = '--'; countdownEl.style.fontSize = ''; }
        if (startBtn) startBtn.disabled = false;
        if (stopBtn) stopBtn.disabled = true;
    }, CONNECT_TIMEOUT);

    try {
        // 请求麦克风
        setASRTestStatus('⏳ 请求麦克风权限...', 'connecting');
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        if (connectTimedOut) { stream.getTracks().forEach(function (t) { t.stop(); }); return; }
        STATE.asrTestStream = stream;

        // 建立 WebSocket 连接（立即设置所有事件处理，避免丢失早期消息）
        setASRTestStatus('⏳ 连接语音识别服务...', 'connecting');
        const ws = new WebSocket(getWsBase() + '/ws/asr?' + getWsAuthQuery());
        ws.binaryType = 'arraybuffer';
        STATE.asrTestWs = ws;

        // 标记：倒计时是否已启动（收到第一条识别结果时启动）
        let countdownStarted = false;
        // 去重：上一次收到的完整句子文本
        let lastFullText = '';

        // 所有事件处理立即注册，不依赖 await 顺序
        ws.onmessage = function (e) {
            try {
                var data = JSON.parse(e.data);
                if (data.type === 'transcript') {
                    var text = data.text || '';
                    if (!text) return;

                    // 【修复】收到第一条识别结果时才开始倒计时
                    if (!countdownStarted) {
                        countdownStarted = true;
                        if (countdownEl) {
                            countdownEl.textContent = '10';
                            countdownEl.style.fontSize = '';
                        }
                        STATE.asrTestCountdown = 10;
                        var cdStartTime = Date.now();
                        STATE.asrTestTimer = setInterval(function () {
                            var elapsed = Math.floor((Date.now() - cdStartTime) / 1000);
                            var remaining = Math.max(0, 10 - elapsed);
                            STATE.asrTestCountdown = remaining;
                            if (countdownEl) countdownEl.textContent = String(remaining);
                            if (remaining <= 0) {
                                clearInterval(STATE.asrTestTimer);
                                STATE.asrTestTimer = null;
                                stopASRTestInternal();
                                var resultDiv = document.getElementById('expr-diag-asr-result');
                                if (resultDiv) {
                                    if (resultDiv.querySelector('.expr__diag-result-text')) {
                                        setASRTestStatus('✅ 测试完成', 'success');
                                    } else {
                                        resultDiv.innerHTML = '<span class="expr__diag-status-error">⏰ 未检测到语音输入，请靠近麦克风说话</span>';
                                        setASRTestStatus('测试结束', 'idle');
                                    }
                                }
                                var sBtn = document.getElementById('expr-diag-asr-start');
                                var stpBtn = document.getElementById('expr-diag-asr-stop');
                                if (sBtn) sBtn.disabled = false;
                                if (stpBtn) stpBtn.disabled = true;
                            }
                        }, 1000);
                    }
                    // 【修复】去重累积：is_end=true 时只追加增量，跳过重复
                    if (data.is_end) {
                        if (text !== lastFullText) {
                            if (STATE.asrTestFullText && text.startsWith(STATE.asrTestFullText)) {
                                STATE.asrTestFullText += text.slice(STATE.asrTestFullText.length);
                            } else {
                                STATE.asrTestFullText = (STATE.asrTestFullText || '') + text;
                            }
                            lastFullText = text;
                        }
                    } else {
                        // 部分结果：直接显示（最终会被完整句子替换）
                        // 不累积到 STATE.asrTestFullText
                    }
                    if (resultEl) {
                        var displayText = data.is_end
                            ? STATE.asrTestFullText
                            : (STATE.asrTestFullText || '') + text;
                        resultEl.innerHTML = '<div class="expr__diag-result-text">' + (displayText ? escapeHtml(displayText) : '（等待识别...）') + '</div>';
                        setASRTestStatus('✅ 识别正常', 'success');
                    }
                } else if (data.type === 'error') {
                    setASRTestStatus('❌ 识别错误: ' + data.message, 'error');
                }
            } catch (e) {}
        };
        ws.onerror = function () {
            setASRTestStatus('❌ WebSocket 连接异常', 'error');
        };
        ws.onclose = function () {
            // 如果状态还是 connecting/listening，说明意外断开
            var info = document.getElementById('expr-diag-asr-info');
            if (info) {
                var statusSpan = info.querySelector('.expr__diag-status span');
                if (statusSpan && statusSpan.className.indexOf('connecting') >= 0) {
                    setASRTestStatus('❌ 连接断开', 'error');
                }
            }
        };

        // 创建 AudioContext
        const audioContext = new (window.AudioContext || window.webkitAudioContext)();
        if (connectTimedOut) { stopASRTestInternal(); return; }
        STATE.asrTestContext = audioContext;

        const source = audioContext.createMediaStreamSource(stream);

        // 注册 AudioWorklet（含降采样 48kHz→16kHz）
        const workletCode = 'class PCMProcessor extends AudioWorkletProcessor { constructor() { super(); this.inputSampleRate = sampleRate; this.targetRate = 16000; this.ratio = this.inputSampleRate / this.targetRate; this.buffer = []; } process(inputs, outputs, parameters) { var input = inputs[0]; if (input && input.length > 0) { var channelData = input[0]; for (var i = 0; i < channelData.length; i++) { this.buffer.push(channelData[i]); } var needed = Math.floor(this.buffer.length / this.ratio); if (needed > 0) { var pcmData = new Int16Array(needed); for (var i = 0; i < needed; i++) { var srcIdx = Math.round(i * this.ratio); var s = Math.max(-1, Math.min(1, this.buffer[srcIdx])); pcmData[i] = s < 0 ? s * 0x8000 : s * 0x7FFF; } this.buffer.splice(0, Math.round(needed * this.ratio)); this.port.postMessage(pcmData.buffer, [pcmData.buffer]); } } return true; } } registerProcessor("pcm-processor", PCMProcessor);';
        const blob = new Blob([workletCode], { type: 'application/javascript' });
        const blobUrl = URL.createObjectURL(blob);
        await audioContext.audioWorklet.addModule(blobUrl);
        URL.revokeObjectURL(blobUrl);
        if (connectTimedOut) { stopASRTestInternal(); return; }

        const workletNode = new AudioWorkletNode(audioContext, 'pcm-processor');
        STATE.asrTestNode = workletNode;

        const gainNode = audioContext.createGain();
        gainNode.gain.value = 0;
        STATE.asrTestGain = gainNode;

        // PCM 数据发送
        workletNode.port.onmessage = function (event) {
            if (ws.readyState === WebSocket.OPEN) {
                ws.send(event.data);
            }
        };

        source.connect(workletNode);
        workletNode.connect(gainNode);
        gainNode.connect(audioContext.destination);

        // 等待 WebSocket 就绪
        await new Promise(function (resolve, reject) {
            if (ws.readyState === WebSocket.OPEN) { resolve(); return; }
            var timeout = setTimeout(function () { reject(new Error('WebSocket 连接超时')); }, 8000);
            ws.onopen = function () {
                clearTimeout(timeout);
                resolve();
            };
            ws.onerror = function () {
                clearTimeout(timeout);
                reject(new Error('WebSocket 连接失败'));
            };
        });
        if (connectTimedOut) { stopASRTestInternal(); return; }

        // 连接成功！取消总超时
        clearTimeout(connectTimeoutId);

        // 连接成功，但倒计时在收到第一条识别结果时才启动
        setASRTestStatus('● 识别中...', 'listening');
        if (resultEl) resultEl.innerHTML = '<span class="expr__diag-result-placeholder">请对着麦克风说话...</span>';

    } catch (e) {
        clearTimeout(connectTimeoutId);
        // 清理测试资源（停止倒计时）
        if (STATE.asrTestTimer) {
            clearInterval(STATE.asrTestTimer);
            STATE.asrTestTimer = null;
        }
        stopASRTestInternal();
        setASRTestStatus('❌ ' + e.message, 'error');
        if (resultEl) {
            resultEl.innerHTML = '<span class="expr__diag-status-error">启动失败: ' + escapeHtml(e.message) + '</span>';
        }
        if (countdownEl) { countdownEl.textContent = '--'; countdownEl.style.fontSize = ''; }
        if (startBtn) startBtn.disabled = false;
        if (stopBtn) stopBtn.disabled = true;
    }
}

function stopASRTest() {
    // 停止倒计时
    if (STATE.asrTestTimer) {
        clearInterval(STATE.asrTestTimer);
        STATE.asrTestTimer = null;
    }
    stopASRTestInternal();
    // 重置按钮
    var startBtn = document.getElementById('expr-diag-asr-start');
    var stopBtn = document.getElementById('expr-diag-asr-stop');
    if (startBtn) startBtn.disabled = false;
    if (stopBtn) stopBtn.disabled = true;
    setASRTestStatus('已停止', 'idle');
}

function stopASRTestInternal() {
    // 关闭 WebSocket
    if (STATE.asrTestWs) {
        try {
            if (STATE.asrTestWs.readyState === WebSocket.OPEN || STATE.asrTestWs.readyState === WebSocket.CONNECTING) {
                STATE.asrTestWs.close();
            }
        } catch (e) {}
        STATE.asrTestWs = null;
    }
    // 断开音频节点
    if (STATE.asrTestNode) {
        try { STATE.asrTestNode.disconnect(); } catch (e) {}
        STATE.asrTestNode = null;
    }
    if (STATE.asrTestGain) {
        try { STATE.asrTestGain.disconnect(); } catch (e) {}
        STATE.asrTestGain = null;
    }
    if (STATE.asrTestContext) {
        try { STATE.asrTestContext.close(); } catch (e) {}
        STATE.asrTestContext = null;
    }
    if (STATE.asrTestStream) {
        try { STATE.asrTestStream.getTracks().forEach(function (t) { t.stop(); }); } catch (e) {}
        STATE.asrTestStream = null;
    }
}

function setASRTestStatus(text, type) {
    var info = document.getElementById('expr-diag-asr-info');
    if (!info) return;
    var statusEl = info.querySelector('.expr__diag-status');
    if (statusEl) {
        statusEl.innerHTML = '状态: <span class="expr__diag-status-' + type + '">' + text + '</span>';
    }
}

// 清理所有测试资源
function stopAllMicTests() {
    stopMicTest();
    // 停止 ASR 测试
    if (STATE.asrTestTimer) {
        clearInterval(STATE.asrTestTimer);
        STATE.asrTestTimer = null;
    }
    stopASRTestInternal();
    // 重置 ASR 测试按钮
    var startBtn = document.getElementById('expr-diag-asr-start');
    var stopBtn = document.getElementById('expr-diag-asr-stop');
    if (startBtn) startBtn.disabled = false;
    if (stopBtn) stopBtn.disabled = true;
}

/**
 * 填充词检测 V2：基于密度 + 高频重复 + 句首 + 簇拥 四重规则
 * 只在"过度使用"时才标记，正常使用不标红
 */
function detectFillerWordsV2(text) {
    if (!text || text.length < 10) return {};

    // 1. 分句
    const sentences = text.split(/[。！？.!?\n]/).filter(s => s.trim().length > 0);
    const totalChars = text.length;

    // 2. 统计每句的原始命中
    const rawCounts = {};
    const sentenceHits = []; // 每句的命中情况 [{word: count, ...}]
    const sentenceStartHits = []; // 每句首词命中

    for (const s of sentences) {
        const trimmed = s.trim();
        const hits = {};
        for (const word of ALL_FILLER_WORDS) {
            const regex = new RegExp(escapeRegex(word), 'gi');
            const matches = trimmed.match(regex);
            if (matches) {
                hits[word] = matches.length;
                rawCounts[word] = (rawCounts[word] || 0) + matches.length;
            }
        }
        sentenceHits.push(hits);

        // 句首检测：句子开头的第一个词
        if (trimmed.length > 0) {
            let foundStart = false;
            for (const word of ALL_FILLER_WORDS) {
                if (trimmed.startsWith(word)) {
                    sentenceStartHits.push(word);
                    foundStart = true;
                    break;
                }
            }
            if (!foundStart) {
                sentenceStartHits.push(null);
            }
        }
    }

    // 3. 应用规则过滤
    const finalFlags = {};

    for (const [word, count] of Object.entries(rawCounts)) {
        if (count === 0) continue;

        // 密度检测：填充词字数 / 总字数 * 100
        const density = (word.length * count) / totalChars * 100;

        // 高频重复检测：连续句子中每句都出现
        let maxConsecutive = 0;
        let currentConsecutive = 0;
        for (const shits of sentenceHits) {
            if ((shits[word] || 0) >= 1) {
                currentConsecutive++;
                maxConsecutive = Math.max(maxConsecutive, currentConsecutive);
            } else {
                currentConsecutive = 0;
            }
        }

        // 句首检测
        let sentenceStartCount = 0;
        let consecutiveStart = 0;
        let maxConsecutiveStart = 0;
        for (const w of sentenceStartHits) {
            if (w === word) {
                sentenceStartCount++;
                consecutiveStart++;
                maxConsecutiveStart = Math.max(maxConsecutiveStart, consecutiveStart);
            } else {
                consecutiveStart = 0;
            }
        }

        // 判断是否标红
        let shouldFlag = false;

        // 规则A：密度超标
        if (density > 8 && count >= 3) {
            shouldFlag = true;
        }

        // 规则B：高频重复（连续3句以上每句都出现）
        if (maxConsecutive >= 3 && count >= 4) {
            shouldFlag = true;
        }

        // 规则C：句首堵词（连续3句以上以填充词开头）
        if (maxConsecutiveStart >= 3) {
            shouldFlag = true;
        }

        // 语境敏感词（contextual）更严格
        if (FILLER_RULES.contextual.includes(word)) {
            shouldFlag = false; // 先重置
            // 只有密度 > 12% 且次数 >= 5 才标记
            if (density > 12 && count >= 5) {
                shouldFlag = true;
            }
            // 或者簇拥模式（见下一步）
        }

        // 规则D：簇拥检测（在 highlight 函数中处理）
        // 这里只记录统计

        if (shouldFlag) {
            finalFlags[word] = count;
        }
    }

    // 4. 簇拥检测：检查是否有相邻填充词
    // 如果两个不同的填充词紧挨着出现，标记它们
    const clusterPattern = new RegExp(
        ALL_FILLER_WORDS.map(w => escapeRegex(w)).join('|') +
        '\\s*' +
        ALL_FILLER_WORDS.map(w => escapeRegex(w)).join('|'),
        'gi'
    );
    if (clusterPattern.test(text)) {
        // 找到了簇拥模式，确保这些词被标记
        const clusters = text.match(clusterPattern);
        if (clusters && clusters.length >= 1) {
            for (const word of ALL_FILLER_WORDS) {
                if (rawCounts[word] && rawCounts[word] >= 2) {
                    // 对于 contextual 类词，簇拥模式下也标记
                    finalFlags[word] = rawCounts[word];
                }
            }
        }
    }

    // 5. 三级语气词（嗯、呃、啊、额）额外宽松
    for (const word of FILLER_RULES.level3) {
        if (finalFlags[word]) {
            const count = rawCounts[word] || 0;
            // 语气词只有密度 > 15% 且次数 >= 5 才标记
            const density = (word.length * count) / totalChars * 100;
            if (density <= 15 || count < 5) {
                delete finalFlags[word];
            }
        }
    }

    return finalFlags;
}

function highlightFillersV2(container, text, fillerCounts) {
    const activeFillers = Object.keys(fillerCounts).filter(w => fillerCounts[w] > 0);
    if (activeFillers.length === 0) {
        // 没有需要标红的词，但如果有之前的标红需要清除
        const hasHighlight = container.querySelector('.expr__filler-highlight');
        if (!hasHighlight) {
            // 【修复】没有标红时也要更新内容，否则初次显示一直是空
            const escaped = escapeHtml(text);
            if (container.innerHTML !== escaped) {
                container.innerHTML = escaped;
            }
            return;
        }
        // 清除标红并恢复纯文本
        container.innerHTML = escapeHtml(text);
        return;
    }

    // 构建正则：匹配所有需要标红的填充词
    const pattern = activeFillers.map(w => escapeRegex(w)).join('|');
    const regex = new RegExp(`(${pattern})`, 'gi');

    // 替换文本为带高亮的 HTML
    const html = text.replace(regex, '<span class="expr__filler-highlight">$1</span>');

    // 只在内容变化时更新
    if (container.innerHTML !== html) {
        container.innerHTML = html;
    }
}

// ================================================================
// AI 分析
// ================================================================

async function handleAIEvaluate() {
    const btn = document.getElementById('expr-ai-btn');
    if (!btn) return;

    btn.disabled = true;
    btn.innerHTML = `<span class="expr__spinner"></span> <span class="expr__ai-tip">分析中...</span>`;

    try {
        // 流式：把后端推的阶段提示（正在分析你的回答…）显示在按钮上，
        // 免得用户对着一个不动的转圈等十几秒
        const result = await apiStream(
            `/api/expression/evaluate/${STATE.currentAnswerId}?${getUserIdParam()}`,
            undefined,
            (label) => {
                const tip = btn.querySelector('.expr__ai-tip');
                if (tip) tip.textContent = label;
            });
        STATE.evaluation = result;

        // 渲染分析结果
        const evalContainer = document.getElementById('expr-evaluation');
        evalContainer.innerHTML = renderEvaluation();
        evalContainer.style.display = 'block';

        // 隐藏 AI 分析按钮
        btn.style.display = 'none';

        // 刷新统计数据
        await loadStats();
        const statsContainer = document.querySelector('#expr-stats');
        if (statsContainer) statsContainer.innerHTML = renderStats();

        showToast('AI 分析完成', 'success');
    } catch (e) {
        showToast('AI 分析失败: ' + e.message, 'error');
        btn.disabled = false;
        btn.innerHTML = `
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="18" height="18"><path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/></svg>
            AI 分析
        `;
    }
}

// ================================================================
// 返回训练首页
// ================================================================

function handleBackToTrain() {
    // 如果正在回答，保存草稿以便恢复
    if (STATE.isAnswering) {
        // 停止录音
        stopVoiceRecording();
        // 保存当前文本到草稿（以便下次恢复）
        STATE.answerText = STATE._draftRestoredText
            ? STATE._draftRestoredText + (STATE.asrText || '')
            : STATE.asrText || STATE.answerText;
        STATE._draftRestoredText = null;
        saveDraft();
    } else {
        // 没有在回答，清除草稿
        clearDraft();
    }

    // 重置答题状态
    STATE.currentQuestion = null;
    STATE.currentAnswerId = null;
    STATE.currentAttempt = 0;
    STATE.isAnswering = false;
    STATE.isPaused = false;
    STATE.answerText = '';
    STATE.asrText = '';
    STATE.fillerWords = {};
    STATE.evaluation = null;

    // 重新加载最近回答记录，以确保新回答出现在列表中
    loadHistory().then(() => {
        // 重新渲染训练首页
        renderTrainView();
        bindEvents();
    });
}

// ================================================================
// 历史视图（筛选栏 + 问题列表 + 分页）
// ================================================================

function renderHistoryView() {
    const container = document.getElementById('expr-view-history');
    container.innerHTML = `
        <div class="expr__history-view" style="height:100%;overflow-y:auto;padding-right:4px">
            ${renderFilterBar()}
            <div id="expr-history-question-list" class="expr__history-question-list">
                <div class="expr__history-loading">
                    <span class="expr__spinner" style="border-color:rgba(255,255,255,0.15);border-top-color:var(--color-accent);width:16px;height:16px"></span>
                    加载中...
                </div>
            </div>
            <div id="expr-history-pagination" class="expr__pagination"></div>
        </div>
    `;
    bindHistoryEvents();
    // 渲染列表（无论有无数据，都会替换掉"加载中..."占位）
    renderHistoryQuestionList();
    if (STATE.historyQuestions.length > 0) {
        renderPagination();
    }
}

function renderFilterBar() {
    const f = STATE.historyFilters;
    return `
    <div class="expr__history-filter">
        <div class="expr__filter-group">
            <label class="expr__filter-label">分类</label>
            <select class="expr__filter-select" id="expr-filter-type">
                <option value="">全部题型</option>
                ${QUESTION_TYPES.map(t => `
                    <option value="${t.id}" ${f.type === t.id ? 'selected' : ''}>${t.name}</option>
                `).join('')}
                <option value="custom" ${f.type === 'custom' ? 'selected' : ''}>自定义题目</option>
            </select>
        </div>
        <div class="expr__filter-group">
            <label class="expr__filter-label">开始时间</label>
            <input type="date" class="expr__filter-select" id="expr-filter-time-start" value="${f.timeStart}">
        </div>
        <div class="expr__filter-group">
            <label class="expr__filter-label">结束时间</label>
            <input type="date" class="expr__filter-select" id="expr-filter-time-end" value="${f.timeEnd}">
        </div>
        <div class="expr__filter-group">
            <label class="expr__filter-label">回答次数</label>
            <select class="expr__filter-select" id="expr-filter-answer-count">
                <option value="">不限</option>
                <option value="1" ${f.answerCount === '1' ? 'selected' : ''}>1 次</option>
                <option value="2" ${f.answerCount === '2' ? 'selected' : ''}>2 次</option>
                <option value="3" ${f.answerCount === '3' ? 'selected' : ''}>3 次</option>
                <option value="gt3" ${f.answerCount === 'gt3' ? 'selected' : ''}>大于 3 次</option>
            </select>
        </div>
    </div>`;
}

function renderHistoryQuestionList() {
    const container = document.getElementById('expr-history-question-list');
    const items = STATE.historyQuestions;

    if (!items || items.length === 0) {
        container.innerHTML = `
            <div class="expr__empty-state">
                <div class="expr__empty-icon">📭</div>
                <div class="expr__empty-text">暂无历史记录，开始训练吧！</div>
            </div>`;
        return;
    }

    container.innerHTML = items.map(q => renderHistoryQuestionItem(q)).join('');
}

function renderHistoryQuestionItem(q) {
    const isExpanded = STATE.expandedQuestionId === q.question_id;
    const answers = STATE.expandedAnswers[q.question_id] || [];
    return `
    <div class="expr__history-question-item ${isExpanded ? 'expr__history-question-item--expanded' : ''}"
         data-question-id="${q.question_id}">
        <div class="expr__history-question-header" onclick="toggleQuestionExpand(${q.question_id})">
            <div class="expr__history-question-info">
                <div class="expr__history-question-text">${escapeHtml(q.question)}</div>
                <div class="expr__history-question-meta">
                    <span class="expr__history-question-type ${q.question_type}">${getTypeName(q.question_type)}</span>
                    <span class="expr__history-question-count">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="12" height="12"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z"/></svg>
                        ${q.answer_count} 次
                    </span>
                    <span class="expr__history-question-time">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="12" height="12"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg>
                        ${formatDateTime(q.last_answer_time)}
                    </span>
                </div>
            </div>
            <div class="expr__history-expand-icon ${isExpanded ? 'expr__history-expand-icon--open' : ''}">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16"><path d="M6 9l6 6 6-6"/></svg>
            </div>
        </div>
        <div class="expr__history-answers-container ${isExpanded ? 'expr__history-answers-container--open' : ''}">
            <div class="expr__history-answers-inner">
                ${isExpanded ? renderAnswerRows(answers) : ''}
            </div>
        </div>
    </div>`;
}

function renderAnswerRows(answers) {
    if (!answers || answers.length === 0) {
        return `<div class="expr__history-empty" style="padding:12px">暂无回答记录</div>`;
    }
    return answers.map(a => {
        const answerPreview = escapeHtml((a.answer || '').slice(0, 80));
        const hoverText = escapeHtml((a.answer || '').slice(0, 200));
        return `
        <div class="expr__history-answer-row" data-answer-id="${a.id}"
             data-hover-text="${hoverText}"
             onmouseenter="startHoverPopup(this)"
             onmouseleave="cancelHoverPopup(this)">
            <div class="expr__answer-attempt">${a.attempt}</div>
            <div class="expr__answer-info">
                <div class="expr__answer-time">${formatDateTime(a.created_at)}</div>
                <div class="expr__answer-text">${answerPreview}${(a.answer || '').length > 80 ? '...' : ''}</div>
            </div>
            <button class="expr__answer-detail-btn" onclick="event.stopPropagation();handleViewDetail(${STATE.expandedQuestionId}, ${a.attempt})">
                查看详情
            </button>
        </div>`;
    }).join('');
}

function renderPagination() {
    const container = document.getElementById('expr-history-pagination');
    if (!container) return;

    const total = STATE.historyTotal;
    const page = STATE.historyPage;
    const pageSize = STATE.historyPageSize;
    const totalPages = Math.ceil(total / pageSize) || 1;

    if (totalPages <= 1) {
        container.innerHTML = '';
        return;
    }

    let html = `<button class="expr__page-btn" onclick="changeHistoryPage(${page - 1})" ${page <= 1 ? 'disabled' : ''}>
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><path d="M15 18l-6-6 6-6"/></svg>
    </button>`;

    const maxVisible = 5;
    let startPage = Math.max(1, page - Math.floor(maxVisible / 2));
    let endPage = Math.min(totalPages, startPage + maxVisible - 1);
    if (endPage - startPage + 1 < maxVisible) {
        startPage = Math.max(1, endPage - maxVisible + 1);
    }

    for (let i = startPage; i <= endPage; i++) {
        html += `<button class="expr__page-btn ${i === page ? 'expr__page-btn--active' : ''}" onclick="changeHistoryPage(${i})">${i}</button>`;
    }

    html += `<button class="expr__page-btn" onclick="changeHistoryPage(${page + 1})" ${page >= totalPages ? 'disabled' : ''}>
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><path d="M9 18l6-6-6-6"/></svg>
    </button>`;
    html += `<span class="expr__page-info">${total} 条</span>`;

    container.innerHTML = html;
}

// 切页
async function changeHistoryPage(page) {
    STATE.historyPage = page;
    await loadHistoryQuestions();
    renderHistoryQuestionList();
    renderPagination();
    // 滚动到列表顶部
    const list = document.getElementById('expr-history-question-list');
    if (list) list.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

// 更新筛选条件后自动刷新
function bindHistoryEvents() {
    const filterIds = ['expr-filter-type', 'expr-filter-time-start', 'expr-filter-time-end', 'expr-filter-answer-count'];
    filterIds.forEach(id => {
        const el = document.getElementById(id);
        if (el) {
            el.addEventListener('change', function () {
                const key = id.replace('expr-filter-', '');
                STATE.historyFilters[key] = this.value;
                STATE.historyPage = 1;
                loadHistoryQuestions().then(() => {
                    renderHistoryQuestionList();
                    renderPagination();
                });
            });
        }
    });
}

async function loadHistoryQuestions() {
    const f = STATE.historyFilters;
    const params = new URLSearchParams();
    params.set('user_id', getCurrentUserId());
    params.set('page', STATE.historyPage);
    params.set('page_size', STATE.historyPageSize);
    if (f.type) params.set('question_type', f.type);
    if (f.timeStart) params.set('time_start', f.timeStart);
    if (f.timeEnd) params.set('time_end', f.timeEnd);
    if (f.answerCount) params.set('answer_count', f.answerCount);

    try {
        const data = await apiGet(`/api/expression/history/questions?${params.toString()}`);
        STATE.historyQuestions = data.items || [];
        STATE.historyTotal = data.total || 0;
    } catch (e) {
        console.warn('加载历史问题列表失败:', e);
        STATE.historyQuestions = [];
        STATE.historyTotal = 0;
    }
}

// 展开/收起（0.1s 防抖）
const toggleQuestionExpand = debounceClick(async function _toggleQuestionExpand(questionId) {
    if (STATE.expandedQuestionId === questionId) {
        // 收起
        STATE.expandedQuestionId = null;
    } else {
        // 展开
        STATE.expandedQuestionId = questionId;
        // 如果还没加载该题的答案，加载
        if (!STATE.expandedAnswers[questionId]) {
            try {
                const data = await apiGet(`/api/expression/history/questions/${questionId}/answers?${getUserIdParam()}&limit=5`);
                STATE.expandedAnswers[questionId] = data.answers || [];
            } catch (e) {
                console.warn('加载回答失败:', e);
                STATE.expandedAnswers[questionId] = [];
            }
        }
    }
    // 重新渲染
    renderHistoryQuestionList();
    renderPagination();
});

// 悬浮弹窗（1s 延迟）
let hoverTimers = {};

function startHoverPopup(el) {
    const aid = el.dataset.answerId;
    const text = el.dataset.hoverText;
    if (!aid || !text) return;
    // 清除旧的定时器
    if (hoverTimers[aid]) clearTimeout(hoverTimers[aid]);
    // 移除旧的弹窗
    const oldPopup = el.querySelector('.expr__hover-popup');
    if (oldPopup) oldPopup.remove();

    hoverTimers[aid] = setTimeout(() => {
        const popup = document.createElement('div');
        popup.className = 'expr__hover-popup expr__hover-popup--visible';
        popup.innerHTML = `<div class="expr__hover-popup-text">${text}</div>`;
        el.appendChild(popup);
    }, 1000);
}

function cancelHoverPopup(el) {
    const aid = el.dataset.answerId;
    if (aid && hoverTimers[aid]) {
        clearTimeout(hoverTimers[aid]);
        delete hoverTimers[aid];
    }
    const popup = el.querySelector('.expr__hover-popup');
    if (popup) popup.remove();
}

// ================================================================
// 历史详情页面
// ================================================================

function handleViewDetail(questionId, attempt) {
    STATE.detailMode = true;
    STATE.detailQuestionId = questionId;
    STATE.detailSelectedAttempt = attempt || null;
    STATE.detailAnswers = [];
    STATE.detailQuestionData = null;

    // 加载详情数据
    loadDetailData(questionId).then(() => {
        renderHistoryDetailView();
    });
}

async function loadDetailData(questionId) {
    try {
        // 加载题目详情及所有回答
        const data = await apiGet(`/api/expression/question/${questionId}?${getUserIdParam()}`);
        STATE.detailQuestionData = data;
        STATE.detailAnswers = data.answers || [];

        // 加载侧边栏列表（所有历史题目）
        const f = STATE.historyFilters;
        const params = new URLSearchParams();
        params.set('user_id', getCurrentUserId());
        params.set('page', 1);
        params.set('page_size', 50);
        if (f.type) params.set('question_type', f.type);
        const listData = await apiGet(`/api/expression/history/questions?${params.toString()}`);
        STATE.detailSidebarQuestions = listData.items || [];
    } catch (e) {
        console.warn('加载详情数据失败:', e);
        showToast('加载详情失败', 'error');
    }
}

function renderHistoryDetailView() {
    const container = document.getElementById('expr-view-history');
    const q = STATE.detailQuestionData;
    if (!q) {
        container.innerHTML = `<div class="expr__empty-state"><div class="expr__empty-icon">😵</div><div class="expr__empty-text">加载失败</div></div>`;
        return;
    }

    container.innerHTML = `
    <div class="expr__detail-layout">
        <!-- 左侧边栏 -->
        <div class="expr__detail-sidebar">
            <button class="expr__detail-back-btn" onclick="handleDetailBack()">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16"><path d="M19 12H5m7-7l-7 7 7 7"/></svg>
                返回列表
            </button>
            <div class="expr__detail-sidebar-list" id="expr-detail-sidebar-list">
                ${renderDetailSidebar()}
            </div>
        </div>
        <!-- 右侧主内容 -->
        <div class="expr__detail-main" id="expr-detail-main">
            ${renderDetailMain()}
        </div>
    </div>`;

    bindDetailEvents();
}

function renderDetailSidebar() {
    const items = STATE.detailSidebarQuestions;
    const currentId = STATE.detailQuestionId;
    if (!items || items.length === 0) {
        return `<div class="expr__detail-empty"><div class="expr__detail-empty-text">暂无其他历史记录</div></div>`;
    }
    return items.map(item => `
        <div class="expr__detail-sidebar-item ${item.question_id === currentId ? 'expr__detail-sidebar-item--active' : ''}"
             onclick="switchDetailQuestion(${item.question_id})">
            <div class="expr__detail-sidebar-q">${escapeHtml(item.question)}</div>
            <div class="expr__detail-sidebar-time">${formatDateTime(item.last_answer_time)}</div>
        </div>
    `).join('');
}

function renderDetailMain() {
    const q = STATE.detailQuestionData;
    if (!q) return '';

    const answers = STATE.detailAnswers;
    const totalAttempts = answers.length;
    const selectedAttempt = STATE.detailSelectedAttempt;

    // 找到选中的回答
    let selectedAnswer = null;
    if (selectedAttempt) {
        selectedAnswer = answers.find(a => a.attempt === selectedAttempt);
    }
    // 默认选中最后一次
    if (!selectedAnswer && answers.length > 0) {
        selectedAnswer = answers[answers.length - 1];
        STATE.detailSelectedAttempt = selectedAnswer.attempt;
    }

    return `
    <div class="expr__detail-question-card">
        <div class="expr__detail-question-header">
            <div>
                <span class="expr__detail-question-type ${q.question_type}">${getTypeName(q.question_type)}</span>
            </div>
            <button class="expr__detail-answer-again-btn" onclick="handleRetryQuestion()">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16"><path d="M1 4v6h6m16 10v-6h-6"/><path d="M3.51 15a9 9 0 102.13-9.36L1 10"/></svg>
                再次回答
            </button>
        </div>
        <div class="expr__detail-question-text">${escapeHtml(q.question)}</div>
    </div>

    ${totalAttempts > 0 ? `
    <div class="expr__detail-attempt-bar">
        ${answers.map((a, i) => `
            <button class="expr__detail-attempt-btn ${a.attempt === STATE.detailSelectedAttempt ? 'expr__detail-attempt-btn--active' : ''}"
                    onclick="switchDetailAttempt(${a.attempt})">
                第 ${a.attempt} 次回答
            </button>
        `).join('')}
    </div>
    ` : ''}

    ${selectedAnswer ? `
    <div class="expr__detail-content">
        <div class="expr__detail-content-title">📝 第 ${selectedAnswer.attempt} 次回答</div>
        <div class="expr__detail-answer-text">${escapeHtml(selectedAnswer.answer || '（无回答内容）')}</div>
        ${selectedAnswer.score_total != null ? `
        <div class="expr__detail-evaluation">
            <div class="expr__eval-header">
                <div class="expr__eval-total">
                    <span class="expr__eval-score">${selectedAnswer.score_total}</span>
                    <span class="expr__eval-label">总分</span>
                </div>
                <div class="expr__eval-dims">
                    ${[
                        { key: 'fluency', label: '流畅度', color: '#60A5FA' },
                        { key: 'logic', label: '逻辑性', color: '#34D399' },
                        { key: 'content', label: '内容质量', color: '#FBBF24' },
                        { key: 'language', label: '语言表达', color: '#F472B6' },
                    ].map(s => `
                        <div class="expr__eval-dim">
                            <div class="expr__eval-dim-bar" style="background:${s.color}; width:${selectedAnswer.scores[s.key] || 0}%"></div>
                            <div class="expr__eval-dim-info">
                                <span>${s.label}</span>
                                <span>${selectedAnswer.scores[s.key] || '--'}</span>
                            </div>
                        </div>
                    `).join('')}
                </div>
            </div>
            ${selectedAnswer.strengths && selectedAnswer.strengths.length > 0 ? `
            <div class="expr__eval-section">
                <div class="expr__eval-section-title expr__eval-section-title--good">👍 优点</div>
                <ul class="expr__eval-list">
                    ${selectedAnswer.strengths.map(s => `<li>${escapeHtml(s)}</li>`).join('')}
                </ul>
            </div>` : ''}
            ${selectedAnswer.improvements && selectedAnswer.improvements.length > 0 ? `
            <div class="expr__eval-section">
                <div class="expr__eval-section-title expr__eval-section-title--warn">💪 有待改进</div>
                <ul class="expr__eval-list">
                    ${selectedAnswer.improvements.map(s => `<li>${escapeHtml(s)}</li>`).join('')}
                </ul>
            </div>` : ''}
            ${selectedAnswer.suggestion ? `
            <div class="expr__eval-section">
                <div class="expr__eval-section-title expr__eval-section-title--tip">📝 综合建议</div>
                <p class="expr__eval-suggestion">${escapeHtml(selectedAnswer.suggestion)}</p>
            </div>` : ''}
        </div>
        ` : `
        <div class="expr__detail-empty">
            <div class="expr__detail-empty-text">该次回答尚未进行 AI 评分</div>
            <button class="expr__ai-btn expr__detail-ai-btn" onclick="handleDetailAIEvaluate(${selectedAnswer.id}, event)" style="margin-top:16px">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="18" height="18"><path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/></svg>
                AI 分析
            </button>
        </div>`}
    </div>
    ` : `
    <div class="expr__detail-empty">
        <div class="expr__detail-empty-icon">📭</div>
        <div class="expr__detail-empty-text">暂无回答记录</div>
    </div>`}`;
}

function bindDetailEvents() {
    // 详情页事件由 onclick 处理
}

// 切换详情页侧边栏题目
async function switchDetailQuestion(questionId) {
    if (questionId === STATE.detailQuestionId) return;
    STATE.detailQuestionId = questionId;
    STATE.detailSelectedAttempt = null;
    STATE.detailAnswers = [];
    STATE.detailQuestionData = null;

    // 加载新数据
    await loadDetailData(questionId);
    renderHistoryDetailView();
}

// 切换第X次回答
function switchDetailAttempt(attempt) {
    STATE.detailSelectedAttempt = attempt;
    renderHistoryDetailView();
}

/** 详情页 AI 分析某条回答 */
async function handleDetailAIEvaluate(answerId, evt) {
    const btn = (evt && evt.target) ? evt.target.closest('.expr__ai-btn') : null;
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = `<span class="expr__spinner"></span> <span class="expr__ai-tip">分析中...</span>`;
    }

    try {
        const result = await apiStream(
            `/api/expression/evaluate/${answerId}?${getUserIdParam()}`,
            undefined,
            (label) => {
                const tip = btn && btn.querySelector('.expr__ai-tip');
                if (tip) tip.textContent = label;
            });

        // 分析完成后重新加载详情数据，刷新界面
        await loadDetailData(STATE.detailQuestionId);
        renderHistoryDetailView();
        showToast('AI 分析完成', 'success');
    } catch (e) {
        showToast('AI 分析失败: ' + e.message, 'error');
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = `
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="18" height="18"><path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/></svg>
                AI 分析
            `;
        }
    }
}

// 返回历史列表
function handleDetailBack() {
    STATE.detailMode = false;
    STATE.detailQuestionId = null;
    STATE.detailSelectedAttempt = null;
    STATE.detailQuestionData = null;
    STATE.detailAnswers = [];
    STATE.detailSidebarQuestions = [];
    STATE.expandedQuestionId = null;
    STATE.expandedAnswers = {};

    renderHistoryView();
    // 重新加载列表
    loadHistoryQuestions().then(() => {
        renderHistoryQuestionList();
        renderPagination();
    });
}

// 再次回答
function handleRetryQuestion() {
    const q = STATE.detailQuestionData;
    if (!q) return;

    const nextAttempt = STATE.detailAnswers.length + 1;
    const modalHtml = `
        <div style="text-align:center;padding:8px 0 16px">
            <div style="font-size:48px;margin-bottom:12px">🔄</div>
            <div style="font-size:16px;font-weight:600;color:var(--color-text);margin-bottom:8px">确定要再次回答这道题吗？</div>
            <div style="font-size:14px;color:var(--color-text-muted)">将跳转到答题界面进行第 <strong>${nextAttempt}</strong> 次回答</div>
        </div>
        <div style="display:flex;gap:12px;margin-top:12px">
            <button class="btn" style="flex:1;padding:12px;font-size:15px;border-radius:10px" onclick="closeModal()">取消</button>
            <button class="btn btn--primary" style="flex:2;padding:12px;font-size:15px;font-weight:700;border-radius:10px" onclick="confirmRetryQuestion()">✅ 确定再次回答</button>
        </div>
    `;
    openModal('再次回答', modalHtml, false);
}

function confirmRetryQuestion() {
    closeModal();
    const q = STATE.detailQuestionData;
    if (!q) return;

    // 设置当前题目，跳转到训练视图（不创建回答记录，等用户点击「开始回答」时再创建）
    STATE.currentQuestion = {
        id: q.id,
        question: q.question,
        question_type: q.question_type,
        hints: q.hints || [],
    };
    STATE.currentAnswerId = null;
    STATE.currentAttempt = (STATE.detailAnswers?.length || 0) + 1;
    STATE.answerText = '';
    STATE.fillerWords = {};
    STATE.evaluation = null;
    STATE.isAnswering = false;
    STATE.isPaused = false;

    // 切换到训练视图
    switchTab('train');
    renderAnswerView();
    bindAnswerEvents();

    // 异步加载提示
    loadHintsAsync(q.id);
}

// ================================================================
// 保存回答
// ================================================================

async function saveAnswerText() {
    if (!STATE.currentAnswerId || !STATE.answerText) return;

    try {
        await apiPost(`/api/expression/answer/${STATE.currentAnswerId}/text?${getUserIdParam()}`, {
            answer: STATE.answerText,
            filler_words: STATE.fillerWords,
        });
    } catch (e) {
        console.warn('保存回答文本失败:', e);
    }
}

// ================================================================
// 历史记录交互
// ================================================================

function showHistoryDetail(el) {
    const fullText = decodeURIComponent(el.dataset.full || '');
    if (!fullText) return;

    // 创建悬浮弹窗
    const existing = document.querySelector('.expr__history-popup');
    if (existing) existing.remove();

    const popup = document.createElement('div');
    popup.className = 'expr__history-popup';
    popup.innerHTML = `
        <div class="expr__history-popup-content">
            <div class="expr__history-popup-close" onclick="this.parentElement.parentElement.remove()">✕</div>
            <div class="expr__history-popup-title">完整回答</div>
            <div class="expr__history-popup-text">${escapeHtml(fullText)}</div>
        </div>
    `;
    el.appendChild(popup);

    // 检查弹窗是否超出可视区域，如果超出则显示在上方
    requestAnimationFrame(() => {
        const rect = popup.getBoundingClientRect();
        const bodyRect = document.querySelector('.expr__body').getBoundingClientRect();
        if (rect.bottom > bodyRect.bottom - 8) {
            popup.style.top = 'auto';
            popup.style.bottom = '100%';
            popup.style.marginTop = '0';
            popup.style.marginBottom = '6px';
        }
    });

    // 鼠标离开时关闭
    el.addEventListener('mouseleave', function onLeave() {
        const p = el.querySelector('.expr__history-popup');
        if (p) p.remove();
        el.removeEventListener('mouseleave', onLeave);
    });
}

// ================================================================
// 工具函数
// ================================================================

function debounce(fn, delay) {
    let timer = null;
    return function (...args) {
        if (timer) clearTimeout(timer);
        timer = setTimeout(() => {
            fn.apply(this, args);
            timer = null;
        }, delay);
    };
}

/* 注：这里原来有个本地 `escapeHtml()`，已于 2026-09-17 删除。
   它与 `js/utils.js` 的实现等价（都是 createElement + textContent 转义），
   却因为本文件是 router 动态注入的、顶层 function 会挂到 window 上，
   **把 utils.js 的那份覆盖掉**（本文件只要被访问过，覆盖就是永久的）。
   留着纯属风险：删掉后这里的 29 处调用自动走 utils.js 那份。 */

function escapeRegex(str) {
    return str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function getTypeName(type) {
    const map = {
        hot_opinion: '热门事件观点',
        emotional: '情感表达',
        life_reflection: '生活感悟',
        career: '职场沟通',
        custom: '自定义题目',
    };
    return map[type] || type || '未知';
}

/**
 * 把时间格式化成「09-17 15:30」（表达训练页专用）
 *
 * ⚠️ 名字必须是 formatDateTime，**不能叫 formatDate**：
 * `js/utils.js` 已经有一个全局 `formatDate`，返回的是「9月17日」（只有月日）。
 * 之前这里同名覆盖，导致一个真实 bug ——
 * `tasks.js` 有 7 处用 `formatDate(new Date())` 生成任务时间戳，
 * 用户只要先访问过「表达训练」，再去「任务」页，
 * 时间戳就会从「9月17日」变成「09-17 15:30」。
 * 两个函数各有用途，所以是**改名**而不是删除。
 */
function formatDateTime(dateStr) {
    if (!dateStr) return '';
    try {
        const d = new Date(dateStr);
        const month = String(d.getMonth() + 1).padStart(2, '0');
        const day = String(d.getDate()).padStart(2, '0');
        const hour = String(d.getHours()).padStart(2, '0');
        const min = String(d.getMinutes()).padStart(2, '0');
        return `${month}-${day} ${hour}:${min}`;
    } catch (e) {
        return dateStr;
    }
}