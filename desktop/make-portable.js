/**
 * make-portable.js — 将 electron-builder --dir 输出打包为绿色版 zip
 *
 * 用法: node make-portable.js
 * 前提: 先运行 npm run build:dir 生成 dist/win-unpacked/
 */

const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

const DIST_DIR = path.join(__dirname, 'dist');
const UNPACKED_DIR = path.join(DIST_DIR, 'win-unpacked');
const APP_DIR = path.join(DIST_DIR, 'SelfGrow');
const VERSION = require('./package.json').version;

// Step 1: 检查 win-unpacked 是否存在
if (!fs.existsSync(UNPACKED_DIR)) {
  console.error('❌ dist/win-unpacked/ 不存在，请先运行 npm run build:dir');
  process.exit(1);
}

// Step 2: 重命名为 SelfGrow
if (fs.existsSync(APP_DIR)) {
  fs.rmSync(APP_DIR, { recursive: true, force: true });
}
fs.renameSync(UNPACKED_DIR, APP_DIR);
console.log('✅ 重命名 win-unpacked → SelfGrow');

// Step 3: 创建启动脚本
fs.writeFileSync(path.join(APP_DIR, '启动 Self Grow.bat'), [
  '@echo off',
  'chcp 65001 >nul',
  'title Self Grow - 个人成长系统',
  'echo 正在启动 Self Grow...',
  'start "" "%~dp0Self Grow.exe"',
  'exit',
].join('\r\n'));
console.log('✅ 创建 启动 Self Grow.bat');

// Step 4: 创建桌面快捷方式脚本
fs.writeFileSync(path.join(APP_DIR, '创建桌面快捷方式.bat'), [
  '@echo off',
  'chcp 65001 >nul',
  'echo 正在创建桌面快捷方式...',
  '',
  'set SCRIPT="%TEMP%\\%RANDOM%-%RANDOM%-%RANDOM%-%RANDOM%.vbs"',
  'echo Set oWS = WScript.CreateObject("WScript.Shell") >> %SCRIPT%',
  'echo sLinkFile = oWS.ExpandEnvironmentStrings("%%USERPROFILE%%\\Desktop\\Self Grow.lnk") >> %SCRIPT%',
  'echo Set oLink = oWS.CreateShortcut(sLinkFile) >> %SCRIPT%',
  'echo oLink.TargetPath = "%~dp0Self Grow.exe" >> %SCRIPT%',
  'echo oLink.WorkingDirectory = "%~dp0" >> %SCRIPT%',
  'echo oLink.Description = "Self Grow - 个人成长系统" >> %SCRIPT%',
  'echo oLink.Save >> %SCRIPT%',
  'cscript /nologo %SCRIPT%',
  'del %SCRIPT%',
  '',
  'echo 快捷方式已创建到桌面！',
  'pause',
].join('\r\n'));
console.log('✅ 创建 创建桌面快捷方式.bat');

// Step 5: 创建使用说明
fs.writeFileSync(path.join(APP_DIR, '使用说明.txt'), [
  '# Self Grow 个人成长系统 v' + VERSION,
  '',
  '## 使用方法',
  '',
  '1. 双击 "启动 Self Grow.bat" 或直接双击 "Self Grow.exe" 启动应用',
  '2. 首次启动会自动创建数据目录到 %APPDATA%\\SelfGrow\\',
  '3. 如需创建桌面快捷方式，双击 "创建桌面快捷方式.bat"',
  '',
  '## 数据存储',
  '',
  '- 数据库: %APPDATA%\\SelfGrow\\data.db',
  '- 上传文件: %APPDATA%\\SelfGrow\\uploads\\',
  '- AI配置: %APPDATA%\\SelfGrow\\.env',
  '',
  '## AI 功能配置',
  '',
  '编辑 %APPDATA%\\SelfGrow\\.env 文件，填入你的 API Key：',
  '  AI_API_BASE_URL=你的API地址',
  '  AI_API_KEY=你的API密钥',
  '  AI_MODEL=模型名称',
  '',
  '## 卸载',
  '',
  '直接删除此文件夹即可。用户数据在 %APPDATA%\\SelfGrow\\ 中，',
  '如需彻底删除，请同时删除该目录。',
  '',
  '## 注意事项',
  '',
  '- 首次启动可能被 Windows Defender 误报，请选择"仍要运行"',
  '- 关闭窗口即停止后端服务',
  '- 请勿同时运行多个实例',
].join('\r\n'));
console.log('✅ 创建 使用说明.txt');

// Step 6: 打包为 zip
const zipName = `SelfGrow-v${VERSION}-portable.zip`;
const zipPath = path.join(DIST_DIR, zipName);

// 使用 7za（electron-builder 自带）
const sevenZip = path.join(__dirname, 'node_modules', '7zip-bin', 'win', 'x64', '7za.exe');
if (fs.existsSync(sevenZip)) {
  try {
    execSync(`"${sevenZip}" a -tzip -mx5 "${zipPath}" "${APP_DIR}\\*"`, {
      cwd: DIST_DIR,
      stdio: 'inherit',
    });
    const size = fs.statSync(zipPath).size;
    console.log(`\n✅ 打包完成: ${zipName} (${(size / 1024 / 1024).toFixed(1)} MB)`);
  } catch (e) {
    console.error('❌ 7za 打包失败，请手动压缩 SelfGrow 目录');
  }
} else {
  console.log('⚠️ 7za.exe 未找到，请手动将 SelfGrow 目录压缩为 zip');
}

console.log('\n========================================');
console.log('  绿色版输出目录: dist/SelfGrow/');
console.log('  压缩包: dist/' + zipName);
console.log('========================================');
