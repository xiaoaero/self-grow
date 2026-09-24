/**
 * AI 对话「按树持久化」回归测试（Node + 极简假 DOM）
 *
 * 跑法：
 *     node frontend/tests/ai-session-persist.test.mjs
 *
 * 用户要求（2026-09-24）：**技能树编辑的 AI 对话，重进后也有原来的记录**。
 *
 * 实现要点：后端 checkpointer 是 **MemorySaver（内存）**，后端一重启服务端上下文就没了，
 * 所以"重进还有记录"只能靠前端 —— 每棵树的消息 + thread_id 各存一份 localStorage。
 * 这里验的是这套存/取/切/删的逻辑（真发请求的部分不测）。
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const TREE = path.join(here, '..', 'skill-tree', 'js');

let failures = 0;
function check(name, got, want) {
  const a = JSON.stringify(got);
  const b = JSON.stringify(want);
  if (a === b) {
    console.log('  ✓ ' + name);
  } else {
    failures++;
    console.log(`  ✗ ${name}\n      得到 ${a}\n      期望 ${b}`);
  }
}

/* ── 极简假 DOM ───────────────────────────────────────── */

function fakeEl(id) {
  const el = {
    id,
    style: {},
    children: [],
    className: '',
    textContent: '',
    disabled: false,
    classList: { add() {}, remove() {}, contains() { return false; } },
    addEventListener() {},
    removeEventListener() {},
    querySelector() { return null; },
    querySelectorAll() { return []; },
    appendChild(c) { el.children.push(c); return c; },
    insertBefore(c) { el.children.unshift(c); return c; },
    remove() {},
    // 清空消息区用的是 `el.innerHTML = ''` —— 假 DOM 必须实现它，
    // 否则 children 数组不会被清掉（这个测试就变成假的）
    get innerHTML() { return ''; },
    set innerHTML(v) { if (v === '') el.children.length = 0; },
    getBoundingClientRect() { return { left: 0, top: 0 }; },
    contains() { return false; },
    scrollTop: 0,
    scrollHeight: 0,
  };
  return el;
}

const els = {};
const store = {};                       // 假 localStorage
globalThis.localStorage = {
  getItem(k) { return Object.prototype.hasOwnProperty.call(store, k) ? store[k] : null; },
  setItem(k, v) { store[k] = String(v); },
  removeItem(k) { delete store[k]; },
};
globalThis.document = {
  getElementById(id) { return (els[id] = els[id] || fakeEl(id)); },
  createElement() { return fakeEl('new'); },
  addEventListener() {},
  querySelectorAll() { return []; },
};
globalThis.window = { addEventListener() {}, location: { search: '' } };
globalThis.showToast = () => {};
globalThis.showConfirm = () => {};

// utils.js 提供 loadFromStorage / saveToStorage —— 显式挂到全局，
// 否则 ai-bridge.js 在另一个 eval 作用域里看不见它们
// eslint-disable-next-line no-eval
eval(fs.readFileSync(path.join(TREE, 'utils.js'), 'utf8')
  + '\nglobalThis.loadFromStorage = loadFromStorage;'
  + '\nglobalThis.saveToStorage = saveToStorage;');

// eslint-disable-next-line no-eval
eval(fs.readFileSync(path.join(TREE, 'ai-bridge.js'), 'utf8')
  + '\nglobalThis.__AIBridge = AIBridge;');

function newBridge() {
  const ai = new globalThis.__AIBridge();
  ai.scrollToBottom = () => {};        // 没有真实滚动容器
  return ai;
}

function rendered(ai) {
  return ai.messagesEl.children.map(c => `${c.className}|${c.textContent}`);
}

/* ── ① 存：发过的消息要落盘 ──────────────────────────── */

console.log('对话记录按树持久化');

const ai = newBridge();
ai.useTree('tree_A');
ai.addMessage('user', '帮我加个节点');
ai.addMessage('assistant', '已添加');

check('localStorage 里存了这条对话',
  JSON.parse(store['skilltree_ai_msgs_tree_A']),
  [{ role: 'user', content: '帮我加个节点' }, { role: 'assistant', content: '已添加' }]);

/* ── ② 取：重进页面（新实例）能恢复 ──────────────────── */

const ai2 = newBridge();               // 模拟刷新页面后的新实例
ai2.useTree('tree_A');
check('重进后恢复出原来的记录', rendered(ai2),
  ['ai-message user|帮我加个节点', 'ai-message assistant|已添加']);

/* ── ③ 切树：各存各的，切回来还在 ────────────────────── */

ai2.syncTree('tree_B');
check('切到另一棵树 → 面板清空', rendered(ai2), []);

ai2.addMessage('user', 'B 树的问题');
ai2.syncTree('tree_A');
check('切回来 → A 树的记录还在', rendered(ai2),
  ['ai-message user|帮我加个节点', 'ai-message assistant|已添加']);

ai2.syncTree('tree_B');
check('再切到 B → B 的记录也在', rendered(ai2), ['ai-message user|B 树的问题']);

/* ── ④ thread_id 跟着树走 ────────────────────────────── */

ai2.threadId = 'thread-123';
ai2._persist();
check('thread_id 落盘', store['skilltree_ai_thread_tree_B'], JSON.stringify('thread-123'));

const ai3 = newBridge();
ai3.useTree('tree_B');
check('重进后 thread_id 也恢复', ai3.threadId, 'thread-123');
ai3.useTree('tree_A');
check('A 树没有那个 thread', ai3.threadId, null);

/* ── ⑤ 删树：连记录一起删 ────────────────────────────── */

ai3.forgetTree('tree_B');
check('删树后消息记录没了', store['skilltree_ai_msgs_tree_B'], undefined);
check('删树后 thread 也没了', store['skilltree_ai_thread_tree_B'], undefined);
check('A 树的记录不受影响', JSON.parse(store['skilltree_ai_msgs_tree_A']).length, 2);

/* ── ⑥ 清空对话：只清当前树 ──────────────────────────── */

ai3.useTree('tree_A');
ai3.resetSession();
check('清空后面板为空', rendered(ai3), []);
check('清空后存储为空', store['skilltree_ai_msgs_tree_A'], undefined);

/* ── ⑦ 历史条数有上限（别让 localStorage 无限涨）──────── */

const ai4 = newBridge();
ai4.useTree('tree_C');
for (let i = 0; i < 130; i++) ai4.addMessage('user', 'msg' + i);
check('最多留 100 条', JSON.parse(store['skilltree_ai_msgs_tree_C']).length, 100);
check('留的是最近的', JSON.parse(store['skilltree_ai_msgs_tree_C']).pop().content, 'msg129');

console.log(failures === 0 ? '\n全部通过' : `\n${failures} 项失败`);
process.exit(failures === 0 ? 0 : 1);
