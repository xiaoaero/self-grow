/**
 * Self Grow — Electron preload 脚本
 *
 * 在渲染进程中安全地暴露 Electron API。
 * 当前主要用于标记 Electron 环境。
 */

const { contextBridge } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
  isElectron: true,
  platform: process.platform,
});
