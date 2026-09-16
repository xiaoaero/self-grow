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

    /** 回答反问 */
    async resumeInterrupt(interruptId, answer) {
        if (this.isLoading) return;

        // 从队列中找到并移除已回答的 interrupt
        const interrupt = this.interruptQueue.find(i => i.id === interruptId);
        if (!interrupt) return;
        this.interruptQueue = this.interruptQueue.filter(i => i.id !== interruptId);

        // 立即刷新反问区：当前卡片马上关闭，队列中下一个补上（不等 fetch 返回）
        this._refreshInterruptArea();

        this.isLoading = true;
        this.sendBtn.disabled = true;
        const bubble = this._showStream();

        try {
            const API_BASE = window.__SELF_GROW_API_BASE__ || 'http://localhost:3001';
            // JWT 改造：身份由 Authorization 头决定，user_id 仅作参考，不再兜底为 1
            const userId = AppData?.user?.id || getCurrentUser()?.id;

            const data = await this._streamCall(
                `${API_BASE}/api/coordinator/resume?user_id=${userId}`,
                {
                    thread_id: this.threadId,
                    sub_thread_id: interrupt.sub_thread_id,  // 指定恢复哪个子图
                    answer: answer,
                },
                bubble,
            );

            if (data.results && data.results.length > 0) {
                this._renderToolCalls(data.results);
            }

            // 如果有新的 interrupts，加入队列
            if (data.interrupts && data.interrupts.length > 0) {
                this.interruptQueue.push(...data.interrupts);
            }

            // 刷新显示（出队下一张卡片）
            this._refreshInterruptArea();

        } catch (err) {
            bubble.finish();
            this._appendMessage('assistant', `抱歉，出了点问题：${err.message}`);
        } finally {
            this.isLoading = false;
            this.sendBtn.disabled = false;
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

    /** 跳过（忽略）某个反问 */
    skipInterrupt(interruptId) {
        this.interruptQueue = this.interruptQueue.filter(i => i.id !== interruptId);
        this._refreshInterruptArea();
        this._appendMessage('assistant', '已跳过该提问');
    },

    /** 刷新反问区域（FIFO 队列渲染，最多 maxVisibleCards 张卡片） */
    _refreshInterruptArea() {
        this.interruptArea.innerHTML = '';

        const visible = this.interruptQueue.slice(0, this.maxVisibleCards);
        const remaining = this.interruptQueue.length - visible.length;

        for (const interrupt of visible) {
            const card = this._createInterruptCard(interrupt);
            this.interruptArea.appendChild(card);
        }

        // 超过 2 张时显示排队提示
        if (remaining > 0) {
            const queueHint = document.createElement('div');
            queueHint.className = 'chat__interrupt-queue-hint';
            queueHint.textContent = `还有 ${remaining} 个提问排队中，回答后自动显示`;
            this.interruptArea.appendChild(queueHint);
        }
    },

    /** 创建单张反问卡片 DOM */
    _createInterruptCard(interrupt) {
        const card = document.createElement('div');
        card.className = 'chat__interrupt-card';
        card.dataset.id = interrupt.id;

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
        skipBtn.addEventListener('click', () => this.skipInterrupt(interrupt.id));

        header.appendChild(domainLabel);
        header.appendChild(skipBtn);
        card.appendChild(header);

        // 问题文本
        const question = document.createElement('div');
        question.className = 'chat__interrupt-question';
        question.textContent = interrupt.question || '请补充信息';
        card.appendChild(question);

        // 输入框 + 发送按钮（自由文本回答）
        const inputRow = document.createElement('div');
        inputRow.className = 'chat__interrupt-input-row';

        const input = document.createElement('input');
        input.type = 'text';
        input.className = 'chat__interrupt-input';
        input.placeholder = '输入你的回答...';

        const sendBtn = document.createElement('button');
        sendBtn.className = 'chat__interrupt-send';
        sendBtn.textContent = '发送';
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
