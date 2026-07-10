/* ================================================================
   history.js — 撤销/重做系统
   ================================================================ */

class HistoryManager {
  constructor(maxSize = 50) {
    this.stack = [];
    this.index = -1;
    this.maxSize = maxSize;
  }

  /**
   * 保存一个快照
   * @param {object} state - 可序列化的状态对象
   */
  push(state) {
    // 截断 redo 栈
    this.stack = this.stack.slice(0, this.index + 1);
    // 添加新快照
    this.stack.push(deepClone(state));
    // 限制栈大小
    if (this.stack.length > this.maxSize) {
      this.stack.shift();
    } else {
      this.index++;
    }
  }

  /**
   * 撤销
   * @returns {object|null} 上一个状态，或 null
   */
  undo() {
    if (!this.canUndo()) return null;
    this.index--;
    return deepClone(this.stack[this.index]);
  }

  /**
   * 重做
   * @returns {object|null} 下一个状态，或 null
   */
  redo() {
    if (!this.canRedo()) return null;
    this.index++;
    return deepClone(this.stack[this.index]);
  }

  canUndo() {
    return this.index > 0;
  }

  canRedo() {
    return this.index < this.stack.length - 1;
  }

  /**
   * 获取当前状态
   */
  current() {
    if (this.index >= 0 && this.index < this.stack.length) {
      return deepClone(this.stack[this.index]);
    }
    return null;
  }

  clear() {
    this.stack = [];
    this.index = -1;
  }
}
