/* ================================================================
   Auth — 登录态管理与 fetch 拦截（2026-09-13 JWT 改造）

   设计要点：
   1. **一处改动覆盖全部调用**：包装 window.fetch，自动给本站 API 请求
      带上 Authorization 头。主应用 52 处、技能树若干处 fetch 全部无需修改。
      （这是零框架项目里比逐个改调用点更安全的做法，将来迁移 Vue 也能原样保留。）
   2. **401 自动续期**：access 过期时用 refresh 换一对新 token 并重放原请求；
      刷新失败才清登录态并跳登录页。
   3. **并发去重**：多个请求同时 401 时只发一次 refresh。
   4. **不拦截登录/刷新端点自身**，避免递归。

   注意：本文件必须在 utils.js / ai-bridge.js 之前加载。
   主应用路径 js/auth.js，技能树路径 ../js/auth.js。
   ================================================================ */

(function () {
  'use strict';

  var TOKEN_KEY = 'sg_access_token';
  var REFRESH_KEY = 'sg_refresh_token';
  var USER_KEY = 'sg_user';

  // 后端 /api/config.js 注入（同源部署时为空 → 回落到 localhost:3001）
  var API_BASE = window.__SELF_GROW_API_BASE__ || 'http://localhost:3001';

  var rawFetch = window.fetch.bind(window);

  /* ── 令牌存取 ───────────────────────────────────────────── */

  function getToken() {
    try { return localStorage.getItem(TOKEN_KEY) || ''; } catch (e) { return ''; }
  }

  function getRefreshToken() {
    try { return localStorage.getItem(REFRESH_KEY) || ''; } catch (e) { return ''; }
  }

  /** 保存登录结果（login / refresh 响应） */
  function setSession(data) {
    if (!data || !data.access_token) return;
    try {
      localStorage.setItem(TOKEN_KEY, data.access_token);
      if (data.refresh_token) localStorage.setItem(REFRESH_KEY, data.refresh_token);
      if (data.user) localStorage.setItem(USER_KEY, JSON.stringify(data.user));
      clearTrustedFlag();   // 走真实登录后，免鉴权模式标记失效
    } catch (e) {
      console.warn('[auth] 保存登录态失败：', e);
    }
  }

  function clear() {
    try {
      localStorage.removeItem(TOKEN_KEY);
      localStorage.removeItem(REFRESH_KEY);
      localStorage.removeItem(USER_KEY);
    } catch (e) { /* ignore */ }
  }

  /** 退出免鉴权模式标记（正常登录成功后调用） */
  function clearTrustedFlag() {
    try { localStorage.removeItem('sg_trusted'); } catch (e) { /* ignore */ }
  }

  /** 供各处 fetch 直接使用的请求头 */
  function getAuthHeaders() {
    var t = getToken();
    return t ? { Authorization: 'Bearer ' + t } : {};
  }

  function isAuthenticated() {
    return !!getToken();
  }

  /**
   * 是否处于"本地免鉴权模式"（SELF_GROW_TRUSTED_MODE=1）。
   * 该模式下后端不校验凭证，前端也不应把用户踢回登录页。
   * 来自后端 /api/config.js 注入；跨域开发时 config.js 取不到，
   * 退而读 login.html 在免密登录时写入的 localStorage 标记。
   */
  function isTrustedMode() {
    if (window.__SELF_GROW_TRUSTED_MODE__ === true) return true;
    try { return localStorage.getItem('sg_trusted') === '1'; } catch (e) { return false; }
  }

  /* ── 跳登录页 ───────────────────────────────────────────── */

  function loginUrl() {
    // 页面都在 /frontend/ 下，登录页在项目根
    var p = location.pathname || '';
    var idx = p.indexOf('/frontend/');
    if (idx >= 0) return p.slice(0, idx) + '/login.html';
    return 'login.html';
  }

  function redirectToLogin() {
    if (window.__authRedirecting) return;
    window.__authRedirecting = true;
    clear();
    // 通知页面（如技能树编辑器的角色校验）登录态已失效
    window.dispatchEvent(new CustomEvent('auth:expired'));
    var url = loginUrl();
    if (location.pathname.indexOf('login.html') === -1) {
      location.href = url;
    }
  }

  /* ── 判断是否需要拦截 ───────────────────────────────────── */

  function toUrlString(input) {
    if (typeof input === 'string') return input;
    if (input && input.url) return input.url;
    return '';
  }

  /** 只处理本站后端 API，避免把 token 发给第三方 */
  function isApiRequest(url) {
    if (!url) return false;
    if (url.indexOf(API_BASE) === 0) return true;
    // 同源相对路径（/api/... ）
    if (/^\/api\//.test(url)) return true;
    if (url.indexOf('/api/') !== -1 && url.indexOf('http') !== 0) return true;
    return false;
  }

  /** 这些端点由本模块自己调用，不能走拦截（否则递归） */
  function isExcluded(url) {
    return /\/api\/auth\/(login|refresh)(\?|$)/.test(url);
  }

  /* ── refresh（并发只发一次） ─────────────────────────────── */

  var refreshPromise = null;

  function doRefresh() {
    if (refreshPromise) return refreshPromise;

    refreshPromise = (async function () {
      try {
        var rt = getRefreshToken();
        if (!rt) throw new Error('no-refresh-token');

        var resp = await rawFetch(API_BASE + '/api/auth/refresh', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ refresh_token: rt }),
          credentials: 'include',
        });
        if (!resp.ok) throw new Error('refresh-failed:' + resp.status);

        var data = await resp.json();
        setSession(data);
        return data.access_token;
      } finally {
        refreshPromise = null;
      }
    })();

    return refreshPromise;
  }

  /* ── fetch 包装 ─────────────────────────────────────────── */

  async function authFetch(input, init) {
    init = init || {};
    var url = toUrlString(input);

    if (!isApiRequest(url) || isExcluded(url)) {
      return rawFetch(input, init);
    }

    var headers = new Headers(init.headers || {});
    var token = getToken();
    if (token) headers.set('Authorization', 'Bearer ' + token);
    // 同源部署时让 refresh cookie 能带上（跨域且未开 CORS credentials 时浏览器会自动忽略）
    if (init.credentials === undefined) init.credentials = 'include';

    var newInit = Object.assign({}, init, { headers: headers });
    var resp = await rawFetch(input, newInit);

    if (resp.status !== 401) return resp;

    // 401：只有"本来带着 token"才值得尝试续期；带 refresh 失败一次的也要给回原响应
    if (!token || !getRefreshToken()) {
      redirectToLogin();
      return resp;
    }

    try {
      var newToken = await doRefresh();
      if (!newToken) throw new Error('refresh-empty');

      // 重放原请求（body 需要重新构造，stream 不能复用）
      var retryHeaders = new Headers(init.headers || {});
      retryHeaders.set('Authorization', 'Bearer ' + newToken);
      return await rawFetch(input, Object.assign({}, init, { headers: retryHeaders }));
    } catch (e) {
      console.warn('[auth] 自动续期失败，跳转登录页：', e);
      redirectToLogin();
      return resp;
    }
  }

  window.fetch = authFetch;
  window.__rawFetch = rawFetch;   // 需要绕过拦截时使用

  /* ── 对外 API ───────────────────────────────────────────── */

  /**
   * 主动登录（供 login.html 使用）
   * @returns {Promise<{ok:boolean, detail?:string, data?:object}>}
   */
  async function login(username, password) {
    var resp = await rawFetch(API_BASE + '/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: username, password: password }),
      credentials: 'include',
    });
    var data = null;
    try { data = await resp.json(); } catch (e) { data = null; }

    if (!resp.ok) {
      return { ok: false, detail: (data && data.detail) || ('登录失败（' + resp.status + '）') };
    }
    setSession(data);
    return { ok: true, data: data };
  }

  /** 登出：撤销服务端 refresh 并清理本地 */
  async function logout() {
    try {
      await rawFetch(API_BASE + '/api/auth/logout', {
        method: 'POST',
        headers: Object.assign({ 'Content-Type': 'application/json' }, getAuthHeaders()),
        body: JSON.stringify({ refresh_token: getRefreshToken() }),
        credentials: 'include',
      });
    } catch (e) { /* 网络失败也要清本地 */ }
    clear();
  }

  window.Auth = {
    API_BASE: API_BASE,
    getToken: getToken,
    getRefreshToken: getRefreshToken,
    getAuthHeaders: getAuthHeaders,
    setSession: setSession,
    clear: clear,
    isAuthenticated: isAuthenticated,
    isTrustedMode: isTrustedMode,
    login: login,
    logout: logout,
    clearTrustedFlag: clearTrustedFlag,
    redirectToLogin: redirectToLogin,
    /** 测试/调试用：原始 fetch */
    raw: rawFetch,
  };
})();
