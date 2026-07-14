/**
 * Self Grow — Electron 主进程
 *
 * 职责：
 * 1. 启动 Python 后端 (self-grow-backend.exe)
 * 2. 等待后端就绪 (轮询 /api/health)
 * 3. 创建 BrowserWindow 加载前端页面
 * 4. 窗口关闭时终止后端进程
 */

const { app, BrowserWindow } = require('electron');
const path = require('path');
const { spawn } = require('child_process');
const http = require('http');
const net = require('net');

// ========================================
// 路径配置
// ========================================

const isDev = !app.isPackaged;

// 后端可执行文件路径
const BACKEND_EXE = isDev
  ? path.join(__dirname, '..', 'backend', '.pixi', 'envs', 'default', 'python.exe')
  : path.join(process.resourcesPath, 'backend', 'self-grow-backend.exe');

// 后端 main.py 路径（开发模式用）
const BACKEND_MAIN = isDev
  ? path.join(__dirname, '..', 'backend', 'self_grow_server.py')
  : null;

// 前端目录
const FRONTEND_DIR = isDev
  ? path.join(__dirname, '..', 'frontend')
  : path.join(process.resourcesPath, 'frontend');

// login.html
const LOGIN_HTML = isDev
  ? path.join(__dirname, '..', 'login.html')
  : path.join(process.resourcesPath, 'login.html');

// ========================================
// 端口查找
// ========================================

function findFreePort(startPort) {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.listen(startPort, '127.0.0.1', () => {
      const port = server.address().port;
      server.close(() => resolve(port));
    });
    server.on('error', () => {
      findFreePort(startPort + 1).then(resolve, reject);
    });
  });
}

// ========================================
// 后端管理
// ========================================

let backendProcess = null;
let backendPort = 3001;

async function startBackend() {
  backendPort = await findFreePort(3001);

  const args = isDev
    ? [BACKEND_MAIN, '--port', String(backendPort), '--frontend-dir', FRONTEND_DIR]
    : ['--port', String(backendPort), '--frontend-dir', FRONTEND_DIR];

  const env = {
    ...process.env,
    SELF_GROW_PACKAGED: isDev ? '0' : '1',
    PORT: String(backendPort),
    SELF_GROW_FRONTEND_DIR: FRONTEND_DIR,
  };

  console.log(`[Self Grow] 启动后端: port=${backendPort}`);
  console.log(`[Self Grow] 后端路径: ${BACKEND_EXE}`);

  backendProcess = spawn(BACKEND_EXE, args, {
    cwd: path.dirname(BACKEND_EXE),
    env,
    stdio: ['ignore', 'pipe', 'pipe'],
  });

  backendProcess.stdout.on('data', (data) => {
    console.log(`[Backend] ${data.toString().trim()}`);
  });

  backendProcess.stderr.on('data', (data) => {
    console.error(`[Backend] ${data.toString().trim()}`);
  });

  backendProcess.on('exit', (code) => {
    console.log(`[Backend] 进程退出，code=${code}`);
  });

  // 等待后端就绪
  await waitForBackend(backendPort);
  console.log(`[Self Grow] 后端就绪: http://127.0.0.1:${backendPort}`);
}

async function waitForBackend(port, maxRetries = 30, interval = 1000) {
  for (let i = 0; i < maxRetries; i++) {
    try {
      await new Promise((resolve, reject) => {
        const req = http.get(`http://127.0.0.1:${port}/api/health`, (res) => {
          if (res.statusCode === 200) resolve();
          else reject(new Error(`Status ${res.statusCode}`));
        });
        req.on('error', reject);
        req.setTimeout(2000, () => {
          req.destroy();
          reject(new Error('Timeout'));
        });
      });
      return;
    } catch (e) {
      if (i === 0) console.log('[Self Grow] 等待后端启动...');
      await new Promise(r => setTimeout(r, interval));
    }
  }
  throw new Error('后端启动超时');
}

function stopBackend() {
  if (backendProcess) {
    console.log('[Self Grow] 停止后端...');
    if (process.platform === 'win32') {
      // Windows: 用 taskkill 终止进程树
      spawn('taskkill', ['/pid', String(backendProcess.pid), '/T', '/F'], { stdio: 'ignore' });
    } else {
      backendProcess.kill('SIGTERM');
    }
    backendProcess = null;
  }
}

// ========================================
// 窗口管理
// ========================================

let mainWindow = null;

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 800,
    minWidth: 960,
    minHeight: 600,
    icon: path.join(__dirname, 'build', 'icon.ico'),
    title: 'Self Grow - 个人成长系统',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      nodeIntegration: false,
      contextIsolation: true,
    },
    show: false, // 加载完成后再显示
  });

  // 加载登录页（由后端 serve）
  mainWindow.loadURL(`http://127.0.0.1:${backendPort}/`);

  mainWindow.once('ready-to-show', () => {
    mainWindow.show();
    console.log('[Self Grow] 窗口已显示');
  });

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

// ========================================
// 应用生命周期
// ========================================

// 单实例锁
const gotTheLock = app.requestSingleInstanceLock();
if (!gotTheLock) {
  app.quit();
} else {
  app.on('second-instance', () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.focus();
    }
  });

  app.on('ready', async () => {
    try {
      await startBackend();
      createWindow();
    } catch (e) {
      console.error('[Self Grow] 启动失败:', e);
      app.quit();
    }
  });

  app.on('window-all-closed', () => {
    stopBackend();
    app.quit();
  });

  app.on('before-quit', () => {
    stopBackend();
  });
}
