/**
 * 反问卡片「提交逻辑」的前端回归测试（Node + 极简假 DOM，无浏览器、无依赖）
 *
 * 跑法（任选）：
 *     node frontend/tests/interrupt-submit.test.mjs
 *     "C:/Users/18111/.workbuddy/binaries/node/versions/22.22.2/node.exe" frontend/tests/interrupt-submit.test.mjs
 *
 * 为什么需要它：反问（ask_user）的交互全在 `chat.js` 的 DOM 操作里 ——
 * 浏览器里不好自动化，但恰恰最容易出错。真实踩到的问题：
 *   · 一次消息路由到多个域 → **两个反问一同到达是常态**，
 *     改造前用单个 isLoading 全局开关挡住第二次提交，并且**静默吞掉**
 *     （用户点了没反应），或者绕过后端并发执行子图 → 写库型工具重复写入
 *   · 重渲染会把**另一张卡片里已输入的内容**清空
 *   · 跳过只删本地卡片，不告诉后端 → 该域永远完不成 → 这条记录的总结永远为空
 *
 * 覆盖场景见下方 ①~⑦。
 */
/**
 * 反问卡片「提交逻辑」的前端回归验证（Node + 极简假 DOM）
 *
 * 为什么要单独测前端：用户报的是"两个反问一同到达时提交逻辑出问题"，
 * 而这套逻辑全在 chat.js 的 DOM 操作里 —— 浏览器不好自动化，
 * 但它恰恰是最容易出错、又最难在单元测试里覆盖的部分。
 *
 * 这里用一个够用的假 DOM 跑真实 chat.js，重点验证：
 *   1. 两张卡片同时到达 → 快速分别提交 → **串行**发出（不会并发撞 409）
 *   2. 连点同一张卡片的发送 → 只发一次（状态锁，不靠定时器）
 *   3. 提交 A 的时候，B 卡片里已输入的内容**不能被清掉**
 *   4. 跳过 → 走 skip 接口（不能只在本地删卡片）
 *   5. 失败时卡片恢复可重试，且输入内容还回去
 *   6. 做完的卡片要退场，留在队列里的要正常渲染
 */

import { readFileSync } from 'node:fs';
import vm from 'node:vm';

// ================================================================
// 极简假 DOM（只实现 chat.js 真正用到的那些）
// ================================================================
class ClassList {
    constructor(el) { this.el = el; this.set = new Set(); }
    add(...cs) { cs.forEach((c) => c && this.set.add(c)); }
    remove(...cs) { cs.forEach((c) => this.set.delete(c)); }
    contains(c) { return this.set.has(c); }
    toggle(c, on) { if (on === undefined) on = !this.set.has(c); on ? this.set.add(c) : this.set.delete(c); return on; }
}

class El {
    constructor(tag) {
        this.tagName = String(tag).toUpperCase();
        this.children = [];
        this.parentNode = null;
        this._className = '';
        this._text = '';
        this.value = '';
        this.disabled = false;
        this.type = '';
        this.title = '';
        this.placeholder = '';
        this.style = {};
        this.dataset = {};
        this.listeners = {};
        this.scrollTop = 0;
        this.scrollHeight = 0;
        this.classList = new ClassList(this);
    }
    get isConnected() { return !!this.parentNode; }

    // className 与 classList 必须同步（真实 DOM 就是这样），
    // 代码里两种写法混着用（.className = '...' 与 .classList.add()）
    set className(v) {
        this._className = String(v || '');
        this.classList.set = new Set(this._className.split(/\s+/).filter(Boolean));
    }
    get className() { return this._className; }

    set textContent(v) { this._text = String(v); this.children = []; }
    get textContent() { return this._text; }

    set innerHTML(v) {
        if (v === '') { this.children = []; this._text = ''; return; }
        // 只用它写简单的状态行，当作纯文本处理足够
        this._text = String(v);
    }
    get innerHTML() { return this._text; }

    setAttribute(k, v) { this[k] = v; }

    appendChild(child) {
        if (child.parentNode) child.parentNode.children = child.parentNode.children.filter((c) => c !== child);
        child.parentNode = this;
        this.children.push(child);
        return child;
    }
    insertBefore(child, ref) {
        const i = ref ? this.children.indexOf(ref) : -1;
        if (i < 0) return this.appendChild(child);
        child.parentNode = this;
        this.children.splice(i, 0, child);
        return child;
    }
    remove() {
        if (this.parentNode) {
            this.parentNode.children = this.parentNode.children.filter((c) => c !== this);
            this.parentNode = null;
        }
        this.__decided = true;
    }
    _all(acc = []) {
        for (const c of this.children) { acc.push(c); c._all(acc); }
        return acc;
    }
    _match(sel) {
        if (sel.startsWith('.')) return this.classList.contains(sel.slice(1));
        return this.tagName === sel.toUpperCase();
    }
    querySelector(sel) { return this._all().find((e) => e._match(sel)) || null; }
    querySelectorAll(sel) { return this._all().filter((e) => e._match(sel)); }

    addEventListener(type, fn) { (this.listeners[type] ||= []).push(fn); }

    /** 测试里手动触发事件 */
    fire(type, ev = {}) {
        (this.listeners[type] || []).forEach((fn) => fn({ type, target: this, ...ev }));
    }
    click() { this.fire('click'); }
}

// ================================================================
// 装载 chat.js
// ================================================================
const src = readFileSync(new URL('../js/chat.js', import.meta.url), 'utf8');

const els = {
    'ai-float-ball': new El('div'),
    'ai-chat-dialog': new El('div'),
    'ai-messages': new El('div'),
    'ai-input': new El('input'),
    'ai-send-btn': new El('button'),
    'ai-tools-list': new El('div'),
    'ai-interrupt-area': new El('div'),
};

// 记录所有发出去的 /resume 请求
const sent = [];
let nextResolve = null;
let resolveDelayMs = 0;
let failNext = null;

const sandbox = {
    console,
    document: {
        getElementById: (id) => els[id] || null,
        createElement: (tag) => new El(tag),
        addEventListener: () => {},
    },
    sessionStorage: { getItem: () => null, setItem: () => {} },
    window: {},
    AppData: { user: { id: 1 }, profile: null },
    getCurrentUser: () => ({ id: 1 }),
    escapeHtml: (s) => String(s),
    // 用假的流式调用替掉真实网络：只关心「谁在什么时候发了什么」
    streamSSE: (url, body) => {
        sent.push({ url, body, at: Date.now() });
        if (failNext) {
            const e = failNext; failNext = null;
            return Promise.reject(e);
        }
        return new Promise((res) => {
            const finish = () => res(nextResolve ? nextResolve() : {
                thread_id: 't', reply: '', interrupts: [], results: [],
            });
            resolveDelayMs ? setTimeout(finish, resolveDelayMs) : finish();
        });
    },
};
sandbox.globalThis = sandbox;

vm.createContext(sandbox);
// 顶层 const 不会挂到 global，补一行导出
vm.runInContext(src + '\n;globalThis.AIChat = AIChat;', sandbox);
const AIChat = sandbox.AIChat;

// 初始化：假 DOM 撑不住拖拽/全局事件绑定，所以容错后再手动接管 DOM 引用
try {
    AIChat.init();
} catch (e) {
    console.log(`（init 在假 DOM 下部分失败，属预期：${e.message}）\n`);
}
AIChat.ball = els['ai-float-ball'];
AIChat.dialog = els['ai-chat-dialog'];
AIChat.messages = els['ai-messages'];
AIChat.input = els['ai-input'];
AIChat.sendBtn = els['ai-send-btn'];
AIChat.toolsList = els['ai-tools-list'];
AIChat.interruptArea = els['ai-interrupt-area'];
AIChat.threadId = 'th';

// ================================================================
// 断言
// ================================================================
let failed = 0;
function check(cond, msg) {
    console.log(`   ${cond ? '[OK]' : '[FAIL]'} ${msg}`);
    if (!cond) failed++;
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function mkInterrupt(id, domain, question = '请确认？') {
    return {
        id, domain, question,
        sub_thread_id: `th:${domain}`,
        domain_label: `标签-${domain}`,
        options: [],
    };
}

function cards() { return els['ai-interrupt-area'].querySelectorAll('.chat__interrupt-card'); }

// ================================================================
console.log('='.repeat(70));
console.log('① 两个反问一同到达 → 两张卡片都渲染出来，各自带进场动画');
console.log('='.repeat(70));
AIChat.threadId = 'th';
AIChat.interruptQueue = [mkInterrupt('i1', 'habit'), mkInterrupt('i2', 'task')];
AIChat._refreshInterruptArea();

const c = cards();
check(c.length === 2, `渲染出 2 张卡片（实际 ${c.length}）`);
check(c.every((x) => x.classList.contains('chat__interrupt-card--enter')),
    '两张卡片都带首次进场动画类');
check(c[0].querySelector('.chat__interrupt-input').value === '',
    '初始输入框为空');

// 重渲染一次：动画类**不应该**再出现（否则每次刷新都重播，很晃眼）
AIChat._refreshInterruptArea();
check(cards().every((x) => !x.classList.contains('chat__interrupt-card--enter')),
    '重渲染后不再加动画类（动画只在首次出现时播一次）');

// ================================================================
console.log();
console.log('='.repeat(70));
console.log('② 在 B 卡片里打字 → 提交 A 卡片 → B 的输入不能被清掉');
console.log('='.repeat(70));
{
    const cardB = cards()[1];
    const inputB = cardB.querySelector('.chat__interrupt-input');
    inputB.value = '我正在输入的内容';
    inputB.fire('input');

    // 在 A 卡片上提交
    cards()[0].querySelector('.chat__interrupt-input').value = 'A 的答案';
    cards()[0].querySelector('.chat__interrupt-send').click();

    check(cards().length === 2, '提交 A 后两张卡片都还在（A 变提交中，B 还在）');
    const inputB2 = cards()[1].querySelector('.chat__interrupt-input');
    check(inputB2.value === '我正在输入的内容',
        `B 卡片的输入被保留了（实际 ${JSON.stringify(inputB2.value)}）`);
}

// 等这一轮提交走完
await sleep(20);
check(sent.length === 1, `只发出了 1 个请求（实际 ${sent.length}）`);
check(sent[0].body.answer === 'A 的答案', '发出去的是 A 的答案');
check(sent[0].body.sub_thread_id === 'th:habit', '发到了 A 对应的子图');
check(cards().length === 1, `A 完成后卡片退场，只剩 B（实际 ${cards().length}）`);

// ================================================================
console.log();
console.log('='.repeat(70));
console.log('③ 连点同一张卡片的发送 → 只发一次（靠状态锁，不靠定时器）');
console.log('='.repeat(70));
{
    sent.length = 0;
    AIChat.interruptQueue = [mkInterrupt('j1', 'goal')];
    AIChat._refreshInterruptArea();

    const card = cards()[0];
    card.querySelector('.chat__interrupt-input').value = '连点';
    const btn = card.querySelector('.chat__interrupt-send');
    btn.click(); btn.click(); btn.click();     // 连点三次
    card.querySelector('.chat__interrupt-input').fire('keydown', { key: 'Enter' });  // 再加一次回车

    check(sent.length === 1, `连点 3 次 + 回车 1 次 → 只发 1 个请求（实际 ${sent.length}）`);
    await sleep(20);
    check(sent.length === 1, '整轮结束后仍然只有 1 个请求');
}

// ================================================================
console.log();
console.log('='.repeat(70));
console.log('④ 两张卡片快速依次提交 → 必须**串行**发（不能并发撞后端 409）');
console.log('='.repeat(70));
{
    sent.length = 0;
    AIChat.interruptQueue = [mkInterrupt('k1', 'habit'), mkInterrupt('k2', 'task')];
    AIChat._refreshInterruptArea();

    // 第一张填好并提交
    cards()[0].querySelector('.chat__interrupt-input').value = '第一';
    cards()[0].querySelector('.chat__interrupt-send').click();

    // 不等它结束，第二张也提交
    cards()[1].querySelector('.chat__interrupt-input').value = '第二';
    cards()[1].querySelector('.chat__interrupt-send').click();

    check(sent.length === 1,
        `此刻只发了 1 个请求（第二个进了队列，实际 ${sent.length}）`);

    await sleep(30);
    check(sent.length === 2, `串行发完 2 个请求（实际 ${sent.length}）`);
    check(sent[0].body.answer === '第一' && sent[1].body.answer === '第二',
        '顺序是「第一」→「第二」（FIFO）');
    check(sent[0].body.thread_id === sent[1].body.thread_id, '同一个会话');
    check(cards().length === 0, `两张卡片都退场（实际 ${cards().length}）`);
}

// ================================================================
console.log();
console.log('='.repeat(70));
console.log('⑤ 跳过 → 必须调后端 skip（不能只在本地删卡片）');
console.log('='.repeat(70));
{
    sent.length = 0;
    AIChat.interruptQueue = [mkInterrupt('m1', 'reward')];
    AIChat._refreshInterruptArea();
    cards()[0].querySelector('.chat__interrupt-skip').click();

    await sleep(20);
    check(sent.length === 1, '跳过也发出了请求（后端要靠它把该域标记为完成）');
    check(sent[0].body.skip === true, '`skip: true`');
    check(sent[0].body.answer === undefined, '跳过时不带 answer');
    check(cards().length === 0, '跳过的卡片退场');
}

// ================================================================
console.log();
console.log('='.repeat(70));
console.log('⑥ 提交失败 → 卡片恢复可重试，输入内容还回去');
console.log('='.repeat(70));
{
    sent.length = 0;
    failNext = Object.assign(new Error('上一条内容还在处理中，请等它结束再提交'), { status: 409 });
    AIChat.interruptQueue = [mkInterrupt('n1', 'goal')];
    AIChat._refreshInterruptArea();
    cards()[0].querySelector('.chat__interrupt-input').value = '要重试的内容';
    cards()[0].querySelector('.chat__interrupt-send').click();

    await sleep(20);
    const cs = cards();
    check(cs.length === 1, `失败的卡片留在队列里（实际 ${cs.length}）`);
    check(!cs[0].classList.contains('chat__interrupt-card--busy'),
        '恢复成可提交状态（不再是"排队中"）');
    check(cs[0].querySelector('.chat__interrupt-send').disabled === false,
        '发送按钮重新可用');
    check(cs[0].querySelector('.chat__interrupt-input').value === '要重试的内容',
        `输入内容被还回来了（实际 ${JSON.stringify(cs[0].querySelector('.chat__interrupt-input').value)}）`);
}

// ================================================================
console.log();
console.log('='.repeat(70));
console.log('⑦ 后端返回新反问 → 回到待答队列并渲染');
console.log('='.repeat(70));
{
    sent.length = 0;
    nextResolve = () => ({
        thread_id: 'th', reply: '', results: [],
        interrupts: [mkInterrupt('new1', 'habit', '还需要补充一点？')],
    });
    AIChat.interruptQueue = [mkInterrupt('p1', 'task')];
    AIChat._refreshInterruptArea();
    cards()[0].querySelector('.chat__interrupt-input').value = '回答';
    cards()[0].querySelector('.chat__interrupt-send').click();

    await sleep(20);
    nextResolve = null;
    check(cards().length === 1, `新反问渲染成卡片（实际 ${cards().length}）`);
    check(cards().length === 1 && cards()[0].dataset.id === 'new1', '就是后端新给的那张');
}

// ================================================================
console.log();
console.log('='.repeat(70));
console.log(failed ? `❌ ${failed} 项未通过` : '🎉 反问卡片提交逻辑全部通过');
console.log('='.repeat(70));
process.exit(failed ? 1 : 0);
