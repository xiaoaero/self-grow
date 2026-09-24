/**
 * 技能树「id 契约」的前端回归测试（Node，无依赖、无浏览器）
 *
 * 跑法：
 *     node frontend/tests/tree-id-normalize.test.mjs
 *
 * 为什么需要它（2026-09-24 实测事故）
 *
 * 后端列表接口一度把**数据库自增主键**当 `id` 返回，而两个前端到处都用 `t.id`
 * 当树的标识：侧边栏选中项、localStorage key、API 路径 `/api/skill-trees/{id}/...`。
 * 于是服务器上第一次有数据之后：`currentId` 变成 `3` →
 * `POST /api/skill-trees/3/chat` → 404「技能树不存在」——
 * 症状和「树根本没存上」一模一样，但树明明在库里，很容易又查错方向。
 *
 * 后端已改成对外只给 tree_id（自增主键改名 db_id），
 * 但**已经被写进用户 localStorage 的坏条目**要靠 `normalizeTreeEntry` 兜住：
 *   · 带 tree_id 的 → 用 tree_id 当 id（保住这棵树）
 *   · 只有纯数字 id 的 → 丢弃（它对应的是死键 `tree_<数字>`，
 *     不丢的话同步逻辑会往服务器上建一棵叫 "3" 的垃圾树）
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

// ⚠️ ES module 里直接 `eval(源码)` 声明的函数**留在 eval 自己的作用域里**，
//    外部取不到 —— 所以在源码末尾追加一句显式导出到 globalThis。
// eslint-disable-next-line no-eval
eval(fs.readFileSync(utilsPath, 'utf8')
  + String.fromCharCode(10)
  + 'globalThis.__treeIdUtils = { normalizeTreeEntry, normalizeTreeEntries };');
const { normalizeTreeEntries } = globalThis.__treeIdUtils;

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

console.log('技能树的 id 规整');

// ① 后端列表里带的冗余字段（tree_id）+ 自增主键（id）→ 用 tree_id 当 id
check('陈旧条目 {id:3, tree_id} → id 取 tree_id',
  normalizeTreeEntries([{ id: 3, tree_id: 'tree_ms35mznq_d9bk', name: '后端' }]),
  [{ id: 'tree_ms35mznq_d9bk', tree_id: 'tree_ms35mznq_d9bk', name: '后端' }]);

// ② 正常的本地条目（id 本来就是 tree_xxx）→ 原样保留
check('正常条目原样保留',
  normalizeTreeEntries([{ id: 'tree_abc', name: 'A' }]),
  [{ id: 'tree_abc', name: 'A' }]);

// ③ 只有纯数字 id 的陈旧条目 → 丢弃（不能当成一棵树去同步）
check('纯数字 id 无 tree_id → 丢弃',
  normalizeTreeEntries([{ id: '3' }, { id: 7, name: 'x' }]),
  []);

// ④ 同一棵树出现两次（一次本地、一次服务器）→ 去重
check('重复 id 去重',
  normalizeTreeEntries([
    { id: 3, tree_id: 'tree_x' },
    { id: 'tree_x', name: '本地那份' },
  ]).length,
  1);

// ⑤ 脏数据不能让它抛异常
check('null / 字符串 / 缺 id → 安全丢弃',
  normalizeTreeEntries([null, 'abc', {}, 42]),
  []);

// ⑥ 真实混合场景：坏的 + 好的 + 重复的
check('混合场景',
  normalizeTreeEntries([
    { id: 3, tree_id: 'tree_keep' },
    { id: 9 },
    { id: 'tree_new', name: 'B' },
  ]).map(t => t.id),
  ['tree_keep', 'tree_new']);

console.log(failures === 0 ? '\n全部通过' : `\n${failures} 项失败`);
process.exit(failures === 0 ? 0 : 1);
