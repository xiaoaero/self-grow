/**
 * Self Grow — AI 助手对话组件
 *
 * 悬浮球 + 对话框 + 反问卡片交互（FIFO 队列，最多 2 张可见）。
 */

// 会话钥匙：用 sessionStorage 持久化 thread_id
// 语义：切换页面/刷新不丢，关闭标签页才丢
const THREAD_KEY = 'self_grow_coordinator_thread_id';

const AIChat = {
    isOpen: false,
    threadId: null,
    isLoading: false,

    // 反问队列管理
    interruptQueue: [],       // 完整队列（所有待处理的 interrupt）
    maxVisibleCards: 2,        // 最多同时显示 2 张卡片

    // 反问卡片的运行时状态（不放进 interruptQueue，因为它是后端数据）
    //
    // 为什么需要它：一次消息可能路由到多个域，两边同时缺信息 →
    // **两个反问一同到达是常态**。而回答一个反问要写后端编排 state，
    // 后端对同一会话加了锁（并发提交第二个会拿到 409），所以前端必须
    // 把多个回答**串起来**逐个发。这个 map 记录每张卡片当前处于
    // 待发 / 发送中，用来①防重复点击 ②在卡片上给出"排队中/提交中"的反馈。
    _interruptStatus: {},     // interrupt.id → 'queued' | 'sending'
    _answerJobs: [],          // 待提交的回答（FIFO）
    _answerRunning: false,    // 是否正在串行提交
    _interruptDrafts: {},     // interrupt.id → 输入框草稿（重渲染不能丢）
    _interruptAnimated: {},   // 已播过进场动画的卡片（避免每次重渲染都重播）

    // DOM 引用
    ball: null,
    dialog: null,
    messages: null,
    input: null,
    sendBtn: null,
    toolsPanel: null,
    toolsList: null,
    interruptArea: null,

    // 域名 → emoji 标签映射
    DOMAIN_LABELS: {
        action: '🏃 行动记录',
        query: '📊 统计查询',
        goal: '🎯 目标管理',
        task: '📋 任务管理',
        habit: '✅ 习惯管理',
        reward: '🎁 奖励管理',
    },

    /** 初始化 */
    init() {
        // 从 sessionStorage 恢复会话钥匙（刷新不丢，关闭才丢）
        this.threadId = sessionStorage.getItem(THREAD_KEY) || null;

        this.ball = document.getElementById('ai-float-ball');
        this.dialog = document.getElementById('ai-chat-dialog');
        this.messages = document.getElementById('ai-messages');
        this.input = document.getElementById('ai-input');
        this.sendBtn = document.getElementById('ai-send-btn');
        this.toolsList = document.getElementById('ai-tools-list');
        this.interruptArea = document.getElementById('ai-interrupt-area');

        this._initDraggable();
        this._bindEvents();
    },

    /** 悬浮球拖拽 */
    _initDraggable() {
        let isDragging = false;
        let startX, startY, startLeft, startBottom;

        const onStart = (e) => {
            isDragging = false;
            const touch = e.touches ? e.touches[0] : e;
            startX = touch.clientX;
            startY = touch.clientY;
            const rect = this.ball.getBoundingClientRect();
            startBottom = window.innerHeight - rect.top - rect.height / 2;
            startLeft = rect.left + rect.width / 2;

            document.addEventListener('mousemove', onMove);
            document.addEventListener('mouseup', onEnd);
            document.addEventListener('touchmove', onMove, { passive: false });
            document.addEventListener('touchend', onEnd);
        };

        const onMove = (e) => {
            e.preventDefault();
            const touch = e.touches ? e.touches[0] : e;
            const dx = touch.clientX - startX;
            const dy = touch.clientY - startY;
            if (Math.abs(dx) > 3 || Math.abs(dy) > 3) isDragging = true;

            const newBottom = Math.max(20, Math.min(window.innerHeight - 40, startBottom - dy));
            const newLeft = Math.max(40, Math.min(window.innerWidth - 40, startLeft + dx));
            this.ball.style.bottom = 'auto';
            this.ball.style.right = 'auto';
            this.ball.style.bottom = (newBottom - 28) + 'px';
            this.ball.style.left = (newLeft - 28) + 'px';
        };

        const onEnd = () => {
            document.removeEventListener('mousemove', onMove);
            document.removeEventListener('mouseup', onEnd);
            document.removeEventListener('touchmove', onMove);
            document.removeEventListener('touchend', onEnd);
            if (!isDragging) this.toggle();
        };

        this.ball.addEventListener('mousedown', onStart);
        this.ball.addEventListener('touchstart', onStart, { passive: false });
    },

    /** 绑定事件 */
    _bindEvents() {
        // 关闭按钮
        const closeBtn = this.dialog.querySelector('.chat__close-btn');
        if (closeBtn) closeBtn.addEventListener('click', () => this.close());

        // 发送按钮
        this.sendBtn.addEventListener('click', () => this.sendMessage());

        // Enter 发送，Shift+Enter 换行
        this.input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.sendMessage();
            }
        });

        // 自动调整输入框高度
        this.input.addEventListener('input', () => {
            this.input.style.height = 'auto';
            this.input.style.height = Math.min(this.input.scrollHeight, 120) + 'px';
        });
    },

    /** 切换对话框 */
    toggle() {
        this.isOpen ? this.close() : this.open();
    },

    /** 打开对话框 */
    open() {
        this.isOpen = true;
        this.dialog.classList.remove('chat__dialog--hidden');
        this.dialog.classList.add('chat__dialog--visible');
        this.input.focus();
    },

    /** 关闭对话框 */
    close() {
        this.isOpen = false;
        this.dialog.classList.remove('chat__dialog--visible');
        this.dialog.classList.add('chat__dialog--hidden');
    },

    /** 发送消息 */
    async sendMessage() {
        const text = this.input.value.trim();
        if (!text || this.isLoading) return;

        // 清空输入框
        this.input.value = '';
        this.input.style.height = 'auto';

        // 显示用户消息
        this._appendMessage('user', text);

        // 显示加载状态
        this.isLoading = true;
        this.sendBtn.disabled = true;
        const bubble = this._showStream();

        try {
            const API_BASE = window.__SELF_GROW_API_BASE__ || 'http://localhost:3001';
            // JWT 改造：身份由 Authorization 头决定，user_id 仅作参考，不再兜底为 1
            const userId = AppData?.user?.id || getCurrentUser()?.id;

            // 流式请求：阶段进度 + 逐 token（见 utils/chat 里的 _streamCall 注释）
            const data = await this._streamCall(
                `${API_BASE}/api/coordinator/chat?user_id=${userId}`,
                { message: text, thread_id: this.threadId },
                bubble,
            );

            this.threadId = data.thread_id;
            sessionStorage.setItem(THREAD_KEY, data.thread_id);

            // 显示工具调用
            if (data.results && data.results.length > 0) {
                this._renderToolCalls(data.results);
            }

            // 处理反问 — 加入 FIFO 队列
            if (data.interrupts && data.interrupts.length > 0) {
                this.interruptQueue.push(...data.interrupts);
                this._refreshInterruptArea();
            }

        } catch (err) {
            // 已经流出来的内容保留着（用户能看到部分结果），下面再补一条错误说明
            bubble.finish();
            this._appendMessage('assistant', `抱歉，出了点问题：${err.message}`);
        } finally {
            this.isLoading = false;
            this.sendBtn.disabled = false;
        }
    },

    /**
     * 回答一个反问（进入串行队列，不直接发请求）
     *
     * 为什么不在这里直接发：一次消息可能路由到多个域，**两个反问一同到达是常态**。
     * 后端 /resume 对同一会话加了锁（并发写会重复执行子图 → 写库型工具重复写入），
     * 第二个并发请求会拿到 409。所以前端必须把多个回答排队逐个发。
     *
     * 防抖靠 `_interruptStatus`：第一次点击就同步把它置为 queued，
     * 后续点击（连点、Enter 连按）在状态检查处直接被忽略 ——
     * 比用定时器防抖更可靠（定时器窗口之外仍可能漏）。
     */
    resumeInterrupt(interruptId, answer) {
        const interrupt = this.interruptQueue.find(i => i.id === interruptId);
        if (!interrupt) return;
        if (this._interruptStatus[interruptId]) return;   // 已排队/发送中 → 忽略重复点击

        const text = (answer || '').trim();
        if (!text) return;

        delete this._interruptDrafts[interruptId];
        this._interruptStatus[interruptId] = 'queued';
        this._answerJobs.push({
            interruptId: interruptId,
            domain: interrupt.domain,
            sub_thread_id: interrupt.sub_thread_id,
            text: text,
            skip: false,
        });
        this._refreshInterruptArea();
        this._drainAnswers();
    },

    /**
     * 串行提交排队中的回答（一次只发一个）
     *
     * 用一个 while 循环 + `_answerRunning` 标志实现「单飞」：
     * 先到的调用负责把队列清空，后来的调用看到标志就直接返回。
     */
    async _drainAnswers() {
        if (this._answerRunning) return;
        this._answerRunning = true;
        this.isLoading = true;
        this.sendBtn.disabled = true;
        this._refreshInterruptArea();   // 立即把还在排队的卡片标成"排队中"

        try {
            while (this._answerJobs.length) {
                const job = this._answerJobs[0];
                this._interruptStatus[job.interruptId] = 'sending';
                this._refreshInterruptArea();

                const ok = await this._submitAnswer(job);

                this._answerJobs.shift();
                if (ok) {
                    // 后端已消费这次回答 → 卡片退场
                    this.interruptQueue = this.interruptQueue
                        .filter(i => i.id !== job.interruptId);
                    delete this._interruptStatus[job.interruptId];
                } else {
                    // 失败 → 恢复成可提交，并把输入内容还回去让用户重试。
                    // ⚠️ 必须 **delete** 而不是赋 'idle'：卡片渲染用的是
                    // `busy = !!status`，任何真值（包括字符串 'idle'）都会被当成忙
                    delete this._interruptStatus[job.interruptId];
                    if (job.text) this._interruptDrafts[job.interruptId] = job.text;
                }
                this._refreshInterruptArea();
            }
        } finally {
            this._answerRunning = false;
            this.isLoading = false;
            this.sendBtn.disabled = false;
            this._refreshInterruptArea();
        }
    },

    /**
     * 真正发出一次 /resume 请求
     *
     * @returns {Promise<boolean>} 是否成功（失败时调用方会把卡片恢复成可重试）
     */
    async _submitAnswer(job) {
        const bubble = this._showStream();
        try {
            const API_BASE = window.__SELF_GROW_API_BASE__ || 'http://localhost:3001';
            // JWT 改造：身份由 Authorization 头决定，user_id 仅作参考，不再兜底为 1
            const userId = AppData?.user?.id || getCurrentUser()?.id;

            const body = {
                thread_id: this.threadId,
                sub_thread_id: job.sub_thread_id,   // 指定恢复哪个子图
            };
            if (job.skip) {
                // 跳过必须显式告诉后端：否则这个域永远完不成 →
                // 这条记录的总结**永远不会生成**
                body.skip = true;
            } else {
                body.answer = job.text;
            }

            const data = await this._streamCall(
                `${API_BASE}/api/coordinator/resume?user_id=${userId}`,
                body,
                bubble,
            );

            if (data.results && data.results.length > 0) {
                this._renderToolCalls(data.results);
            }
            // 该子图可能又反问一次 → 回到待答队列
            if (data.interrupts && data.interrupts.length > 0) {
                this.interruptQueue.push(...data.interrupts);
            }
            return true;
        } catch (err) {
            // 已经流出来的内容保留着（用户能看到部分结果），下面再补一条错误说明
            bubble.finish();
            // 409 = 后端说"上一条还在处理中"。理论上排队后不该出现，
            // 出现了说明有另一个标签页 / 别的客户端在同时操作 —— 提示得具体点
            const hint = (err && err.status === 409)
                ? '（可能在另一个标签页或窗口提交过，请刷新页面后重试）'
                : '';
            this._appendMessage('assistant', `抱歉，出了点问题：${err.message}${hint}`);
            return false;
        }
    },

    /** 追加消息到消息列表 */
    _appendMessage(role, content) {
        const wrapper = document.createElement('div');
        wrapper.className = `chat__msg chat__msg--${role}`;

        const avatar = document.createElement('div');
        avatar.className = 'chat__msg-avatar';
        avatar.textContent = role === 'user' ? '👤' : '🤖';

        const bubble = document.createElement('div');
        bubble.className = 'chat__msg-bubble';
        bubble.textContent = content;

        wrapper.appendChild(avatar);
        wrapper.appendChild(bubble);
        this.messages.appendChild(wrapper);

        // 滚动到底部
        this.messages.scrollTop = this.messages.scrollHeight;
    },

    /* 说明：原来的 `_showTyping()`（三点跳动动画）已被 `_showStream()` 取代 ——
       流式气泡内部自带同样的三点动画，等第一个 token 到达时自动移除。
       两者并存会导致「loading 和流式文本同时出现」，所以删掉了。 */

    /** 滚动到底部（流式追加文本时每来一段都要调） */
    _scrollToBottom() {
        this.messages.scrollTop = this.messages.scrollHeight;
    },

    /** 创建一个「流式回复」气泡：上方阶段进度条，下方逐字文本
     *
     * 返回控制器（不要直接操作 DOM）：
     *   setStage(label)  追加一条阶段提示（连续重复的会去重）
     *   appendToken(t)   追加文本增量
     *   setText(t)       用权威文本覆盖（done 事件里的 reply）
     *   finish()         收尾：去掉光标与加载动画
     *   remove()         整条移除
     */
    _showStream() {
        const wrapper = document.createElement('div');
        wrapper.className = 'chat__msg chat__msg--assistant';

        const avatar = document.createElement('div');
        avatar.className = 'chat__msg-avatar';
        avatar.textContent = '🤖';

        const bubble = document.createElement('div');
        bubble.className = 'chat__msg-bubble chat__msg-bubble--stream';

        const stages = document.createElement('div');
        stages.className = 'chat__stages';
        stages.style.display = 'none';

        const text = document.createElement('div');
        text.className = 'chat__stream-text';

        const typing = document.createElement('div');
        typing.className = 'chat__typing';
        for (let i = 0; i < 3; i++) {
            const dot = document.createElement('div');
            dot.className = 'chat__typing-dot';
            typing.appendChild(dot);
        }

        bubble.appendChild(stages);
        bubble.appendChild(typing);
        bubble.appendChild(text);
        wrapper.appendChild(avatar);
        wrapper.appendChild(bubble);
        this.messages.appendChild(wrapper);
        this._scrollToBottom();

        const self = this;
        // 阶段日志最多保留最近几条：协调 Agent 一次请求可能推十几条
        // （每个工具一条），全留着会把气泡撑得很长
        const MAX_STAGES = 5;
        let stageList = [];
        let hasText = false;

        const dropTyping = () => { if (typing.parentNode) typing.remove(); };

        return {
            setStage(label) {
                if (!label) return;
                if (stageList[stageList.length - 1] === label) return;
                stageList.push(label);
                if (stageList.length > MAX_STAGES) stageList = stageList.slice(-MAX_STAGES);
                stages.style.display = '';
                const last = stageList.length - 1;
                stages.innerHTML = stageList.map(function (l, i) {
                    const cls = i === last
                        ? 'chat__stage chat__stage--active'
                        : 'chat__stage';
                    return '<div class="' + cls + '">' + escapeHtml(l) + '</div>';
                }).join('');
                self._scrollToBottom();
            },
            appendToken(t) {
                if (!t) return;
                if (!hasText) { hasText = true; dropTyping(); }
                text.textContent += t;
                self._scrollToBottom();
            },
            setText(t) {
                if (t === undefined || t === null) return;
                hasText = true;
                dropTyping();
                text.textContent = t;
                bubble.classList.add('chat__msg-bubble--done');
                stages.querySelectorAll('.chat__stage--active').forEach(function (el) {
                    el.classList.remove('chat__stage--active');
                });
                self._scrollToBottom();
            },
            finish() {
                dropTyping();
                bubble.classList.add('chat__msg-bubble--done');
                stages.querySelectorAll('.chat__stage--active').forEach(function (el) {
                    el.classList.remove('chat__stage--active');
                });
            },
            remove() { wrapper.remove(); },
            hasText() { return hasText; },
        };
    },

    /**
     * 调一个流式 AI 端点，把过程渲染进气泡
     *
     * 约定（与后端 services/sse.py 一致）：
     *   · stage 事件 → 阶段进度
     *   · token 事件 → 逐字追加
     *   · done 事件  → **用其中的 reply 覆盖已逐字输出的文本**
     *     （服务端在中途出错时会降级成规则拼接，已输出的半截内容不再权威）
     *
     * @returns {Promise<object>} done 事件的完整内容
     */
    async _streamCall(url, body, bubble) {
        const result = await streamSSE(url, body, {
            onStage: (p) => bubble.setStage(p.label),
            onToken: (t) => bubble.appendToken(t),
        });
        if (result.reply) bubble.setText(result.reply);
        else bubble.finish();
        return result;
    },

    /** 渲染工具调用结果 */
    _renderToolCalls(results) {
        this.toolsList.innerHTML = '';
        for (const r of results) {
            const card = document.createElement('div');
            card.className = 'chat__tool-card';

            const name = document.createElement('div');
            name.className = 'chat__tool-card-name';
            name.textContent = this.DOMAIN_LABELS[r.domain] || r.domain || '操作';

            const args = document.createElement('div');
            args.className = 'chat__tool-card-args';
            args.textContent = r.message || '';

            card.appendChild(name);
            card.appendChild(args);

            // 有明确成功/失败标记时展示状态
            if (r.success !== undefined && r.success !== null) {
                const status = document.createElement('div');
                status.className = 'chat__tool-card-status';
                if (r.success !== false) {
                    status.classList.add('chat__tool-card-status--success');
                    status.textContent = '✅ 成功';
                } else {
                    status.classList.add('chat__tool-card-status--error');
                    status.textContent = '❌ 失败';
                }
                card.appendChild(status);
            }

            this.toolsList.appendChild(card);
        }
    },

    /**
     * 跳过某个反问
     *
     * ⚠️ 必须**调用后端**（`skip: true`），不能只在本地把卡片删掉：
     * 后端要靠这次调用把这个域标记成"已完成"，否则 `pending_domains` 永远
     * 不是 `completed_domains` 的子集 → 这条记录的总结**永远不会生成**。
     *
     * 与回答共用同一条串行队列：跳过同样会写后端编排 state，不能并发。
     */
    skipInterrupt(interruptId) {
        const interrupt = this.interruptQueue.find(i => i.id === interruptId);
        if (!interrupt) return;
        if (this._interruptStatus[interruptId]) return;   // 已排队/发送中 → 忽略

        delete this._interruptDrafts[interruptId];
        this._interruptStatus[interruptId] = 'queued';
        this._answerJobs.push({
            interruptId: interruptId,
            domain: interrupt.domain,
            sub_thread_id: interrupt.sub_thread_id,
            text: '',
            skip: true,
        });
        this._refreshInterruptArea();
        this._drainAnswers();
    },

    /** 重渲染前把卡片里已输入的内容存起来（否则 innerHTML='' 会把另一个卡片的输入清掉） */
    _captureInterruptDrafts() {
        if (!this.interruptArea) return;
        this.interruptArea.querySelectorAll('.chat__interrupt-card').forEach((card) => {
            const id = card.dataset.id;
            const input = card.querySelector('.chat__interrupt-input');
            if (id && input) this._interruptDrafts[id] = input.value;
        });
    },

    /** 刷新反问区域（FIFO 队列渲染，最多 maxVisibleCards 张卡片） */
    _refreshInterruptArea() {
        if (!this.interruptArea) return;

        // ⚠️ 必须在清空之前抓草稿：用户在 A 卡片里打了半句，然后去提交 B 卡片，
        // 重渲染会把 A 的输入一起清掉 —— 这是改造前丢答案的原因之一
        this._captureInterruptDrafts();
        this.interruptArea.innerHTML = '';

        const visible = this.interruptQueue.slice(0, this.maxVisibleCards);
        const remaining = this.interruptQueue.length - visible.length;

        for (const interrupt of visible) {
            const card = this._createInterruptCard(interrupt);
            this.interruptArea.appendChild(card);
        }

        // 超过 maxVisibleCards 时显示排队提示
        if (remaining > 0) {
            const queueHint = document.createElement('div');
            queueHint.className = 'chat__interrupt-queue-hint';
            queueHint.textContent = `还有 ${remaining} 个提问排队中，回答后自动显示`;
            this.interruptArea.appendChild(queueHint);
        }

        // 说明性提示放在**最后**（appendChild 会把提示压到队列提示下面）
        if (this._answerRunning) {
            const busyHint = document.createElement('div');
            busyHint.className = 'chat__interrupt-busy-hint';
            busyHint.textContent = '之前的回答还在处理中，这一条会在它完成后自动发送…';
            this.interruptArea.appendChild(busyHint);
        }
    },

    /** 创建单张反问卡片 DOM */
    _createInterruptCard(interrupt) {
        const status = this._interruptStatus[interrupt.id];   // undefined | 'queued' | 'sending'
        const busy = !!status;

        const card = document.createElement('div');
        card.className = 'chat__interrupt-card';
        card.dataset.id = interrupt.id;
        if (busy) card.classList.add('chat__interrupt-card--busy');

        // 进场动画只在**首次**创建时加：每次重渲染都重播会很晃眼
        if (!this._interruptAnimated[interrupt.id]) {
            this._interruptAnimated[interrupt.id] = true;
            card.classList.add('chat__interrupt-card--enter');
        }

        // 头部：域名标签 + 关闭按钮
        const header = document.createElement('div');
        header.className = 'chat__interrupt-header';

        const domainLabel = document.createElement('span');
        domainLabel.className = 'chat__interrupt-domain';
        domainLabel.textContent = interrupt.domain_label || this.DOMAIN_LABELS[interrupt.domain] || '🤖 AI 助手';

        const skipBtn = document.createElement('button');
        skipBtn.className = 'chat__interrupt-skip';
        skipBtn.textContent = '×';
        skipBtn.title = '跳过此提问';
        skipBtn.disabled = busy;
        skipBtn.addEventListener('click', () => this.skipInterrupt(interrupt.id));

        header.appendChild(domainLabel);
        header.appendChild(skipBtn);
        card.appendChild(header);

        // 问题文本
        const question = document.createElement('div');
        question.className = 'chat__interrupt-question';
        question.textContent = interrupt.question || '请补充信息';
        card.appendChild(question);

        // 状态行：给排队/提交中的卡片一个明确的反馈
        //（改造前是静默吞掉第二次提交，用户点了没反应，只能反复点）
        if (busy) {
            const statusEl = document.createElement('div');
            statusEl.className = 'chat__interrupt-status';
            statusEl.innerHTML = '<span class="chat__interrupt-status-dot"></span>'
                + (status === 'sending' ? '正在提交…' : '排队中，等待上一条完成…');
            card.appendChild(statusEl);
        }

        // 输入框 + 发送按钮（自由文本回答）
        const inputRow = document.createElement('div');
        inputRow.className = 'chat__interrupt-input-row';

        const input = document.createElement('input');
        input.type = 'text';
        input.className = 'chat__interrupt-input';
        input.placeholder = busy ? '上一条处理完后可继续' : '输入你的回答...';
        input.value = this._interruptDrafts[interrupt.id] || '';
        input.disabled = busy;
        input.addEventListener('input', () => {
            this._interruptDrafts[interrupt.id] = input.value;
        });

        const sendBtn = document.createElement('button');
        sendBtn.className = 'chat__interrupt-send';
        sendBtn.textContent = busy ? '…' : '发送';
        sendBtn.disabled = busy;
        sendBtn.addEventListener('click', () => {
            const val = input.value.trim();
            if (val) {
                this.resumeInterrupt(interrupt.id, val);
            }
        });

        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                const val = input.value.trim();
                if (val) {
                    this.resumeInterrupt(interrupt.id, val);
                }
            }
        });

        inputRow.appendChild(input);
        inputRow.appendChild(sendBtn);
        card.appendChild(inputRow);

        // 选项按钮（如果有）
        if (interrupt.options && interrupt.options.length > 0) {
            const optionsWrap = document.createElement('div');
            optionsWrap.className = 'chat__interrupt-options';
            for (const opt of interrupt.options) {
                const btn = document.createElement('button');
                btn.className = 'chat__interrupt-option';
                btn.textContent = opt;
                btn.disabled = busy;
                btn.addEventListener('click', () => {
                    this.resumeInterrupt(interrupt.id, opt);
                });
                optionsWrap.appendChild(btn);
            }
            card.appendChild(optionsWrap);
        }

        return card;
    },

    /** 渲染反问卡片（兼容旧接口，实际走队列） */
    _renderInterrupts(interrupts) {
        this.interruptQueue.push(...interrupts);
        this._refreshInterruptArea();
    },
};

// 全局初始化（在 app.js 之后）
document.addEventListener('DOMContentLoaded', () => {
    AIChat.init();
});
