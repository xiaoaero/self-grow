/**
 * 框选矩形回归测试（Node + 极简假 DOM，无浏览器、无依赖）
 *
 * 跑法：
 *     node frontend/tests/selection-box.test.mjs
 *
 * 为什么值得单独测：用户报「框选时的框呢？鼠标拖动我都不知道我拖了多大」。
 * 根因是 `#selection-box` 是 **SVG `<rect>`**，而代码用 `style.left/top/width/height`
 * 去定位 —— 这些 CSS 属性对 SVG 元素**完全无效**，所以那个框**从来没出现过**。
 *
 * 这类问题在浏览器里是"点了没反应"，但纯看代码很容易漏（CSS 里还有一条
 * 对 SVG 无效的 `#selection-box { border: … }` 在"证明"它存在）。
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));

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
  return {
    id,
    style: {},
    attrs: {},
    classList: { add() {}, remove() {}, contains() { return false; } },
    setAttribute(k, v) { this.attrs[k] = String(v); },
    getAttribute(k) { return this.attrs[k]; },
    addEventListener() {},
    removeEventListener() {},
    querySelector() { return null; },
    querySelectorAll() { return []; },
    contains() { return false; },
    appendChild() {},
    getBoundingClientRect() { return { left: 0, top: 0, width: 1000, height: 600 }; },
    clientWidth: 1000,
    clientHeight: 600,
  };
}

const els = {};
globalThis.document = {
  getElementById(id) { return (els[id] = els[id] || fakeEl(id)); },
  addEventListener() {},
  createElement() { return fakeEl('created'); },
};
globalThis.window = { addEventListener() {}, location: { search: '' } };
globalThis.showToast = () => {};

const srcPath = path.join(here, '..', 'skill-tree', 'js', 'interaction.js');
const src = fs.readFileSync(srcPath, 'utf8')
  // ES module 里 eval 声明的 class 不会挂到全局 —— 显式导出一下
  + '\nglobalThis.__InteractionManager = InteractionManager;';
// eslint-disable-next-line no-eval
eval(src);

const im = new globalThis.__InteractionManager({
  nodes: [],
  connections: [],
  selectedIds: new Set(),
  isUser: false,
  renderer: {
    nodeEls: new Map(),
    renderGrid() {},
    updateConnectionPaths() {},
    hideAlignLines() {},
    showAlignLines() {},
    hitTestNode() { return null; },
    hitTestRect() { return []; },
  },
  getSelectedNodes() { return []; },
  selectNode() {}, deselectNode() {}, selectNodes() {}, deselectAll() {},
  saveHistory() {},
});

/* ── 拖动 → 框应该跟着变大 ───────────────────────────── */

const box = els['selection-box'];

console.log('框选矩形（SVG rect 必须用 x/y/width/height 属性）');

im.isSelecting = true;
im.selectStart = { x: 100, y: 100 };
im.onMouseMove({ clientX: 300, clientY: 220 });

check('x', box.getAttribute('x'), '100');
check('y', box.getAttribute('y'), '100');
check('width', box.getAttribute('width'), '200');
check('height', box.getAttribute('height'), '120');

// 反向拖（右下 → 左上）：左上角要正确、宽高必须为正
im.selectStart = { x: 300, y: 220 };
im.onMouseMove({ clientX: 100, clientY: 100 });
check('反向拖：x 取左上角', box.getAttribute('x'), '100');
check('反向拖：y 取左上角', box.getAttribute('y'), '100');
check('反向拖：宽为正', box.getAttribute('width'), '200');
check('反向拖：高为正', box.getAttribute('height'), '120');

// 画布被平移/缩放过也要对（screenToCanvas 负责换算，这里只确认换算生效）
im.scale = 0.5;
im.panX = 40;
im.selectStart = { x: 0, y: 0 };
im.onMouseMove({ clientX: 400, clientY: 300 });
check('缩放 0.5 + 平移 40 → width = (400-40)/0.5', box.getAttribute('width'), '720');

/* ── 静态护栏：别再退回 style.left ────────────────────── */

console.log('\n静态护栏');

check('不再用 style.left/top 定位（对 SVG 无效）',
  /selectionBox\.style\.(left|top|width|height)/.test(src), false);

const cssText = fs.readFileSync(
  path.join(here, '..', 'skill-tree', 'css', 'style.css'), 'utf8');
check('CSS 里没有对 SVG 无效的 #selection-box 规则',
  /#selection-box\s*\{[^}]*border\s*:/.test(cssText), false);

const htmlText = fs.readFileSync(
  path.join(here, '..', 'skill-tree', 'index.html'), 'utf8');
check('框选层有 overflow: visible（否则拖出视口就被裁）',
  /#selection-box-layer[\s\S]{0,200}overflow:\s*visible/.test(cssText), true);
check('rect 用 vector-effect（线宽不随缩放变）',
  /id="selection-box"[\s\S]{0,300}vector-effect/.test(htmlText), true);

console.log(failures === 0 ? '\n全部通过' : `\n${failures} 项失败`);
process.exit(failures === 0 ? 0 : 1);
