/**
 * 技能树编辑器的交互逻辑回归测试（Node，无依赖、无浏览器）
 *
 * 跑法：
 *     node frontend/tests/tree-editor-features.test.mjs
 *
 * 上面这些功能是 2026-09-24 用户提的：
 *   ① 网格按「单位区域」扩展（原来只在中间画一小块）
 *   ② 拖节点（含框选整组）必须 **Ctrl/Cmd + 左键**；左键只选中，不拖
 *   ③ 多选右键菜单：移动 / 删除边 / 删除结点
 *   ④ Ctrl+Z 撤销
 *
 * 这里只测**纯逻辑部分**（区域计算、选边），DOM/事件那部分在浏览器里点两下就知道了；
 * 但纯函数最容易在"顺手改一下"的时候坏掉，所以钉住。
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const utilsPath = path.join(here, '..', 'skill-tree', 'js', 'utils.js');

// ── 极简环境：utils.js 顶层会用到 window / localStorage / document ──
globalThis.window = { location: { search: '' } };
globalThis.localStorage = {
  _d: {},
  getItem(k) { return Object.prototype.hasOwnProperty.call(this._d, k) ? this._d[k] : null; },
  setItem(k, v) { this._d[k] = String(v); },
  removeItem(k) { delete this._d[k]; },
};
globalThis.document = { getElementById: () => null };

// eslint-disable-next-line no-eval
eval(fs.readFileSync(utilsPath, 'utf8')
  + String.fromCharCode(10)
  + 'globalThis.__utils = { gridRegionFor, edgesAmong, normalizeTreeEntries };');
const { gridRegionFor, edgesAmong, normalizeTreeEntries } = globalThis.__utils;

let failures = 0;
function check(name, actual, expected) {
  const a = JSON.stringify(actual);
  const e = JSON.stringify(expected);
  if (a === e) {
    console.log(`  ✓ ${name}`);
  } else {
    failures++;
    console.log(`  ✗ ${name}\n      期望 ${e}\n      实际 ${a}`);
  }
}

const UNIT = 300;

console.log('网格区域（单位区域扩展）');

// ① 空树：给视口中心那一格（"一开始只有一个单位区域，就是中间"）
check('空树 → 视口中心那一格',
  gridRegionFor([], UNIT, { w: 1000, h: 600, panX: 0, panY: 0, scale: 1 }),
  { x0: 300, y0: 300, x1: 600, y1: 600 });

// ② 一个节点在第一格 → 就一格
check('节点在 (80,80) → 0..300',
  gridRegionFor([{ x: 80, y: 80, size: 70 }], UNIT, null),
  { x0: 0, y0: 0, x1: 300, y1: 300 });

// ③ 节点往右跑到第二格 → 右边多一格
check('节点跑到 x=350 → 右边补一格',
  gridRegionFor([{ x: 350, y: 80, size: 70 }], UNIT, null),
  { x0: 300, y0: 0, x1: 600, y1: 300 });

// ④ 往左上跑 → 负方向也要补
check('节点跑到负方向 → 左上补一格',
  gridRegionFor([{ x: -50, y: -20, size: 70 }], UNIT, null),
  { x0: -300, y0: -300, x1: 300, y1: 300 });

// ⑤ 两个方向都有 → 区域应该是连续的若干格
check('横跨多格 → 顺延到整格',
  gridRegionFor([{ x: 80, y: 80, size: 70 }, { x: 1250, y: 900, size: 70 }], UNIT, null),
  { x0: 0, y0: 0, x1: 1500, y1: 1200 });

// ⑥ 节点尺寸要算进包围盒（跨格时要占两格，不能把节点压在边界线上）
check('节点尺寸计入包围盒（290+70 → 跨两格）',
  gridRegionFor([{ x: 290, y: 290, size: 70 }], UNIT, null),
  { x0: 0, y0: 0, x1: 600, y1: 600 });

// ⑦ 缩放不参与区域计算（区域只跟内容走）
check('scale 不影响区域',
  gridRegionFor([{ x: 80, y: 80, size: 70 }], UNIT, { w: 1000, h: 600, panX: 0, panY: 0, scale: 0.5 }),
  { x0: 0, y0: 0, x1: 300, y1: 300 });

console.log('\n列表字段对齐（修「进去都是 0 节点 / 日期空白」）');

// 后端行是 snake_case，前端渲染用 camelCase —— 不映射就全空
{
  const one = normalizeTreeEntries([{
    id: 7, tree_id: 'tree_x', name: '后端',
    node_count: 21, completed_count: 3,
    created_at: '2026-09-24 10:00:00', updated_at: '2026-09-24 12:00:00',
  }])[0];
  check('snake_case → camelCase',
    [one.nodeCount, one.completedCount, one.createdAt, one.updatedAt],
    [21, 3, '2026-09-24 10:00:00', '2026-09-24 12:00:00']);
}

// 本地索引用的是 camelCase，不能被覆盖成 undefined
check('本地条目（camelCase）保持原值', (function () {
  const one = normalizeTreeEntries([{
    id: 'tree_y', name: '前端', nodeCount: 5, completedCount: 1,
    createdAt: '2026-09-20 09:00:00', updatedAt: '2026-09-21 09:00:00',
  }])[0];
  return [one.nodeCount, one.completedCount, one.createdAt, one.updatedAt];
})(), [5, 1, '2026-09-20 09:00:00', '2026-09-21 09:00:00']);

console.log('\n删除边（只删选中节点之间的）');

const conns = [
  { id: 'c1', from: 'a', to: 'b' },   // 两端都选中 → 删
  { id: 'c2', from: 'b', to: 'c' },   // c 没选中 → 留
  { id: 'c3', from: 'a', to: 'd' },   // d 没选中 → 留
  { id: 'c4', from: 'a', to: 'b' },   // 两端都选中（重复边）→ 删
];

check('只留两端都在集合里的边',
  edgesAmong(conns, new Set(['a', 'b'])).map(c => c.id),
  ['c1', 'c4']);

check('传数组也行',
  edgesAmong(conns, ['a', 'b']).length,
  2);

check('只选一个 → 没有边可删',
  edgesAmong(conns, ['a']),
  []);

check('空输入不炸',
  [edgesAmong([], ['a']), edgesAmong(conns, []), edgesAmong(null, ['a'])],
  [[], [], []]);

console.log('\n手势约定（拖节点必须 Ctrl+左键）');

// 这个约定来回改过两次（直接拖 -> Ctrl 平移 -> 回到 Ctrl 拖），
// 所以钉一条静态断言：以后再被顺手改掉会立刻红。
{
  const src = fs.readFileSync(
    path.join(here, '..', 'skill-tree', 'js', 'interaction.js'), 'utf8');

  // 1) 节点拖动必须挂在 ctrlKey/metaKey 上
  const i = src.indexOf('--- 拖拽 ---');
  const dragBlock = src.slice(i, i + 900);
  check('拖节点需要 Ctrl/Cmd',
    /wantDrag\s*=\s*e\.ctrlKey\s*\|\|\s*e\.metaKey/.test(dragBlock), true);
  check('只有按住 Ctrl 才进 isDragging',
    /wantDrag\s*&&\s*!multi[\s\S]{0,300}this\.isDragging\s*=\s*true/.test(dragBlock), true);

  // 2) Ctrl 不能拿去平移画布（用户明确说不要）
  const j = src.indexOf('空格 / 中键');
  const panBlock = src.slice(j, src.indexOf('连线模式完成'));
  check('Ctrl+左键不用于平移画布', /ctrlKey/.test(panBlock), false);
  check('平移仍然是空格/中键',
    /spaceDown\s*\|\|\s*e\.button\s*===\s*1/.test(panBlock), true);
}

console.log('\n单位区域接缝（多格不能像拼接）');

{
  const rsrc = fs.readFileSync(
    path.join(here, '..', 'skill-tree', 'js', 'tree-renderer.js'), 'utf8');
  const css = fs.readFileSync(
    path.join(here, '..', 'skill-tree', 'css', 'style.css'), 'utf8');

  // 接缝只画**内部**的（从 x0+unit 起）；边界由外框 rect 负责，
  // 否则多格区域看着像几块板子拼起来（用户明确要求变浅）
  check('接缝从内部开始，不画外框那几条',
    /x = x0 \+ unit/.test(rsrc) && /y = y0 \+ unit/.test(rsrc), true);
  check('接缝用了单独的弱化 class',
    /class=\"grid-unit-seam\"/.test(rsrc), true);
  const m = css.match(/\.grid-unit-seam[\s\S]*?opacity:\s*([0-9.]+)/);
  check('接缝透明度很低（<=0.3）', m ? parseFloat(m[1]) <= 0.3 : false, true);
}

console.log(failures === 0 ? '\n全部通过' : `\n${failures} 项失败`);
process.exit(failures === 0 ? 0 : 1);
