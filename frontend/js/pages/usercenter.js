/**
 * Self Grow — 用户中心页面
 *
 * 两部分：基础信息 + 模型信息（系统版本 + 多模型管理 + 语音模型）
 */

// 模型类型映射
const MODEL_TYPE_LABEL = {
    llm: '文本模型 (LLM)',
    asr: '语音模型 (ASR)',
};

/** 渲染用户中心页面 */
function renderUserCenter() {
    const page = document.getElementById('page-usercenter');
    if (!page) return;

    const user = AppData.user;
    const curUser = getCurrentUser();
    const theme = getLevelTheme(user.level);
    const roleLabel = user.role === 'admin' ? '管理员' : '普通用户';
    const uid = (curUser && curUser.id) || user.id || '-';

    page.innerHTML = `
        <div class="page-header">
            <h1 class="page-header__title">用户中心</h1>
            <p class="page-header__subtitle">管理账户信息与 AI 模型配置</p>
        </div>

        <div class="card usercenter-card">
            <div class="usercenter-card__header">
                <span class="usercenter-card__header-icon">👤</span> 基础信息
            </div>
            <div class="usercenter-profile">
                <div class="usercenter-profile__badge" style="background:${theme.block}">Lv.${user.level}</div>
                <div class="usercenter-profile__body">
                    <div class="usercenter-profile__name-row">
                        <span class="usercenter-profile__name">${user.name || '冒险者'}</span>
                        <span class="usercenter-profile__role ${user.role === 'admin' ? 'usercenter-profile__role--admin' : ''}">${roleLabel}</span>
                    </div>
                    <div class="usercenter-info-list">
                        <div class="usercenter-info-row">
                            <span class="usercenter-info-row__label">等级</span>
                            <span class="usercenter-info-row__value" style="color:${theme.accent}">Lv.${user.level} · ${user.rank || getRankInfo(user.level).name}</span>
                        </div>
                        <div class="usercenter-info-row">
                            <span class="usercenter-info-row__label">总经验</span>
                            <span class="usercenter-info-row__value">${(user.totalExp || 0).toLocaleString()} EXP</span>
                        </div>
                        <div class="usercenter-info-row">
                            <span class="usercenter-info-row__label">注册时间</span>
                            <span class="usercenter-info-row__value">${user.joined || '-'}</span>
                        </div>
                        <div class="usercenter-info-row">
                            <span class="usercenter-info-row__label">用户 ID</span>
                            <span class="usercenter-info-row__value">#${uid}</span>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <div class="card usercenter-card">
            <div class="usercenter-card__header">
                <span class="usercenter-card__header-icon">🔐</span> 账户安全
            </div>
            <div class="usercenter-info-list" style="padding:0 4px">
                <div class="usercenter-info-row">
                    <span class="usercenter-info-row__label">登录凭证</span>
                    <span class="usercenter-info-row__value">JWT · Access 2 小时 / Refresh 30 天</span>
                </div>
                <div class="usercenter-info-row">
                    <span class="usercenter-info-row__label">登录状态</span>
                    <span class="usercenter-info-row__value" id="uc-auth-status">—</span>
                </div>
            </div>
            <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:14px">
                <button class="btn btn--sm" onclick="openChangePasswordModal()">修改密码</button>
                <button class="btn btn--sm" onclick="openApiKeysModal()">API Key（MCP）</button>
                <button class="btn btn--sm" onclick="doLogout()">退出登录</button>
            </div>
        </div>

        <div class="card usercenter-card">
            <div class="usercenter-card__header">
                <span class="usercenter-card__header-icon">🤖</span> 模型信息
            </div>
            <div id="usercenter-models" class="usercenter-models">
                <div class="usercenter-loading">加载模型配置中…</div>
            </div>
        </div>
    `;

    refreshAuthStatus();
    loadModelInfo();
}

/* ================================================================
   账户安全：登录状态 / 修改密码 / API Key / 退出登录
   （2026-09-13 JWT 改造）
   ================================================================ */

async function refreshAuthStatus() {
    const el = document.getElementById('uc-auth-status');
    if (!el) return;
    if (!window.Auth || !window.Auth.isAuthenticated()) {
        el.textContent = '未登录';
        el.style.color = '#ef5350';
        return;
    }
    try {
        const resp = await fetch(`${API_BASE}/api/auth/me`);
        if (!resp.ok) throw new Error('401');
        const me = await resp.json();
        el.textContent = `已登录 · ${me.name}（${me.is_admin ? '管理员' : '普通用户'}）`;
        el.style.color = '#66bb6a';
    } catch (e) {
        el.textContent = '凭证已失效';
        el.style.color = '#ef5350';
    }
}

function doLogout() {
    showConfirm('确定要退出登录吗？', async () => {
        await window.Auth.logout();
        window.location.href = '../../login.html';
    });
}

function openChangePasswordModal() {
    const content = `
        <div style="display:flex;flex-direction:column;gap:14px">
            <div>
                <label class="action-form__label">当前密码</label>
                <input class="input" type="password" id="pw-old" autocomplete="current-password">
            </div>
            <div>
                <label class="action-form__label">新密码（至少 8 位）</label>
                <input class="input" type="password" id="pw-new" autocomplete="new-password">
            </div>
            <div>
                <label class="action-form__label">确认新密码</label>
                <input class="input" type="password" id="pw-new2" autocomplete="new-password">
            </div>
            <p style="font-size:12px;color:var(--text-muted);margin:0">
                修改成功后所有设备的登录状态都会失效，需要重新登录。
            </p>
        </div>
        <div class="modal__actions">
            <button class="btn btn--ghost" onclick="closeModal()">取消</button>
            <button class="btn btn--primary" onclick="submitChangePassword()">确认修改</button>
        </div>
    `;
    openModal('修改密码', content, false);
}

async function submitChangePassword() {
    const oldPw = document.getElementById('pw-old').value;
    const newPw = document.getElementById('pw-new').value;
    const newPw2 = document.getElementById('pw-new2').value;

    if (!oldPw || !newPw) { showToast('请填写完整', 'error'); return; }
    if (newPw.length < 8) { showToast('新密码至少 8 位', 'error'); return; }
    if (newPw !== newPw2) { showToast('两次输入的新密码不一致', 'error'); return; }

    try {
        const resp = await fetch(`${API_BASE}/api/auth/password`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ old_password: oldPw, new_password: newPw }),
        });
        const data = await resp.json().catch(() => ({}));
        if (!resp.ok) { showToast(data.detail || '修改失败', 'error'); return; }

        showToast('密码已修改，请重新登录', 'success');
        await window.Auth.logout();
        setTimeout(() => { window.location.href = '../../login.html'; }, 800);
    } catch (e) {
        showToast('网络错误：' + e.message, 'error');
    }
}

async function openApiKeysModal() {
    let keys = [];
    try {
        const resp = await fetch(`${API_BASE}/api/auth/api-keys`);
        if (resp.ok) keys = (await resp.json()).keys || [];
    } catch (e) { /* 忽略，按空列表渲染 */ }

    const listHtml = keys.length
        ? keys.map(k => `
            <div class="usercenter-info-row">
                <span class="usercenter-info-row__label">${escapeHtml(k.name)}</span>
                <span class="usercenter-info-row__value">
                    ${k.revoked
                        ? '<span style="color:#ef5350">已撤销</span>'
                        : (k.last_used_at ? '最近使用 ' + k.last_used_at : '未使用')}
                    ${k.revoked ? '' : `<button class="usercenter-model-btn usercenter-model-btn--danger" onclick="revokeApiKey(${k.id})">撤销</button>`}
                </span>
            </div>`).join('')
        : '<p style="font-size:13px;color:var(--text-muted)">暂无 API Key</p>';

    const content = `
        <div style="display:flex;flex-direction:column;gap:14px">
            <p style="font-size:13px;color:var(--text-muted);margin:0">
                用于 MCP 插件 / 脚本以非交互方式访问本系统。请求头：<code>X-API-Key: sgk_...</code>
            </p>
            <div>
                <label class="action-form__label">用途备注</label>
                <input class="input" id="ak-name" placeholder="例如：Claude Desktop">
            </div>
            <div id="ak-list">${listHtml}</div>
            <div id="ak-result"></div>
        </div>
        <div class="modal__actions">
            <button class="btn btn--ghost" onclick="closeModal()">关闭</button>
            <button class="btn btn--primary" onclick="createApiKey()">创建</button>
        </div>
    `;
    openModal('API Key 管理', content, false);
}

async function createApiKey() {
    const name = (document.getElementById('ak-name').value || 'default').trim();
    try {
        const resp = await fetch(`${API_BASE}/api/auth/api-keys`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name }),
        });
        const data = await resp.json().catch(() => ({}));
        if (!resp.ok) { showToast(data.detail || '创建失败', 'error'); return; }

        const box = document.getElementById('ak-result');
        if (box) {
            box.innerHTML = `
                <p style="font-size:12px;color:#f0a020;margin:0 0 6px">⚠️ 明文仅此一次显示，请立即复制保存</p>
                <code style="display:block;word-break:break-all;background:var(--bg-tertiary);padding:8px;border-radius:6px;font-size:12px">${data.api_key}</code>
            `;
        }
        showToast('已创建 API Key', 'success');
    } catch (e) {
        showToast('网络错误：' + e.message, 'error');
    }
}

async function revokeApiKey(keyId) {
    try {
        const resp = await fetch(`${API_BASE}/api/auth/api-keys/${keyId}`, { method: 'DELETE' });
        if (!resp.ok) { showToast('撤销失败', 'error'); return; }
        showToast('已撤销', 'success');
        closeModal();
        openApiKeysModal();
    } catch (e) {
        showToast('网络错误：' + e.message, 'error');
    }
}

/** 加载模型配置列表 */
async function loadModelInfo() {
    const userId = getCurrentUser()?.id || AppData.user.id || 1;
    const API_BASE = window.__SELF_GROW_API_BASE__ || 'http://localhost:3001';

    const configs = await fetch(`${API_BASE}/api/model-configs?user_id=${userId}`)
        .then(r => r.ok ? r.json() : [])
        .catch(() => []);

    renderModelList(configs || []);
}

/** 渲染模型列表（llm / asr 分组） */
function renderModelList(configs) {
    const container = document.getElementById('usercenter-models');
    if (!container) return;

    const llmConfigs = configs.filter(c => c.type === 'llm');
    const asrConfigs = configs.filter(c => c.type === 'asr');

    container.innerHTML = `
        ${renderModelGroup('llm', '文本模型 (LLM)', llmConfigs)}
        ${renderModelGroup('asr', '语音模型 (ASR)', asrConfigs)}
    `;
}

/** 渲染一组模型 */
function renderModelGroup(type, title, configs) {
    const cards = configs.length
        ? configs.map(c => renderModelCard(c)).join('')
        : `<div class="usercenter-model-empty">暂无配置，点击右上角「添加」创建</div>`;

    return `
        <div class="usercenter-model-group">
            <div class="usercenter-model-group__head">
                <span class="usercenter-model-group__title">${title}</span>
                <button class="usercenter-model-add" onclick="openModelModal(null, '${type}')">+ 添加</button>
            </div>
            <div class="usercenter-model-list">
                ${cards}
            </div>
        </div>
    `;
}

/** 渲染单个模型卡片 */
function renderModelCard(cfg) {
    const active = cfg.is_active === 1;
    return `
        <div class="usercenter-model-card ${active ? 'usercenter-model-card--active' : ''}">
            <div class="usercenter-model-card__main" onclick="activateModel(${cfg.id})" title="点击切换启用">
                <div class="usercenter-model-card__name">${cfg.name || cfg.model}</div>
                <div class="usercenter-model-card__meta">
                    <span class="usercenter-model-card__model">${cfg.model}</span>
                    ${cfg.base_url ? `<span class="usercenter-model-card__url">${cfg.base_url}</span>` : ''}
                </div>
                ${active
                    ? '<span class="usercenter-model-card__badge">● 启用中</span>'
                    : '<span class="usercenter-model-card__badge usercenter-model-card__badge--off">○ 未启用</span>'}
            </div>
            <div class="usercenter-model-card__actions">
                <button class="usercenter-model-btn" onclick="openModelModal(${cfg.id})">编辑</button>
                <button class="usercenter-model-btn usercenter-model-btn--danger" onclick="deleteModel(${cfg.id})">删除</button>
            </div>
        </div>
    `;
}

/* 弹窗里当前配置已保存 Key 的**脱敏形式**（后端只返回 sk-****abcd）。
   非空即表示"已保存过 Key"，此时输入框留空也允许测试连通性 —— 后端会用已保存的那把。 */
let _mcSavedKeyMasked = '';

/** 打开模型编辑弹窗（configId 为 null 时新增，type 由「添加」按钮决定） */
function openModelModal(configId, type) {
    const isEdit = configId != null;
    const userId = getCurrentUser()?.id || AppData.user.id || 1;
    const API_BASE = window.__SELF_GROW_API_BASE__ || 'http://localhost:3001';

    const buildForm = (cfg) => {
        const c = cfg || { type: type || 'llm', name: '', model: '', base_url: '', api_key: '' };
        const typeLabel = c.type === 'llm' ? '文本模型 (LLM)' : '语音模型 (ASR)';
        // 记录"是否已有保存的 Key"（c.api_key 是脱敏值，非空即已保存）
        _mcSavedKeyMasked = c.api_key || '';
        // 编辑时把脱敏值显示在 placeholder 里，提示用户留空即可
        const keyPlaceholder = isEdit
            ? (_mcSavedKeyMasked
                ? `已保存 ${_mcSavedKeyMasked}，留空即用它测试`
                : '留空则不修改')
            : 'sk-...';
        const content = `
            <div style="display:flex;flex-direction:column;gap:14px">
                <div class="usercenter-modal-type">${typeLabel}</div>
                <div>
                    <label class="action-form__label">配置名称</label>
                    <input class="input" id="mc-name" placeholder="例如：主力模型" value="${escapeHtml(c.name || '')}">
                </div>
                <div>
                    <label class="action-form__label">模型标识</label>
                    <input class="input" id="mc-model" placeholder="例如：qwen3.7-plus-2026-05-26" value="${escapeHtml(c.model || '')}">
                </div>
                <div>
                    <label class="action-form__label">API 地址</label>
                    <input class="input" id="mc-base-url" placeholder="https://... 或 wss://..." value="${escapeHtml(c.base_url || '')}">
                </div>
                <div>
                    <label class="action-form__label">API Key</label>
                    <input class="input" id="mc-api-key" type="password" placeholder="${escapeHtml(keyPlaceholder)}" value="">
                </div>
                <div class="usercenter-modal-test">
                    <button class="btn btn--ghost" onclick="testModelConnection('${c.type}', ${configId || 0})">测试连通性</button>
                    <span id="mc-test-result" class="usercenter-modal-test-result"></span>
                </div>
            </div>
            <div class="modal__actions">
                <button class="btn btn--ghost" onclick="closeModal()">取消</button>
                <button class="btn btn--primary" onclick="saveModel(${configId || 0}, ${isEdit ? 'true' : 'false'}, '${c.type}')">${isEdit ? '保存' : '创建'}</button>
            </div>
        `;
        openModal(isEdit ? '编辑模型' : '添加模型', content, false);
    };

    if (isEdit) {
        fetch(`${API_BASE}/api/model-configs?user_id=${userId}`)
            .then(r => r.json())
            .then(list => {
                const cfg = (list || []).find(x => x.id === configId);
                buildForm(cfg);
            })
            .catch(() => buildForm(null));
    } else {
        buildForm(null);
    }
}

/** 保存模型（创建或编辑）。type 由添加按钮决定，编辑时不变更 */
async function saveModel(configId, isEdit, type) {
    const userId = getCurrentUser()?.id || AppData.user.id || 1;
    const API_BASE = window.__SELF_GROW_API_BASE__ || 'http://localhost:3001';

    const name = document.getElementById('mc-name').value.trim();
    const model = document.getElementById('mc-model').value.trim();
    const base_url = document.getElementById('mc-base-url').value.trim();
    const api_key = document.getElementById('mc-api-key').value.trim();

    if (!name || !model) {
        showToast('请填写配置名称和模型标识', 'error');
        return;
    }

    try {
        let resp;
        if (isEdit) {
            const body = { name, model, base_url };
            if (api_key) body.api_key = api_key;  // 编辑时留空不改密钥
            resp = await fetch(`${API_BASE}/api/model-configs/${configId}?user_id=${userId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
        } else {
            resp = await fetch(`${API_BASE}/api/model-configs?user_id=${userId}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ type, name, model, base_url, api_key }),
            });
        }
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        closeModal();
        showToast(isEdit ? '模型已更新' : '模型已添加', 'success');
        loadModelInfo();
    } catch (e) {
        showToast(`保存失败：${e.message}`, 'error');
    }
}

/**
 * 测试模型连通性
 *
 * api_key 留空是允许的：后端会回落到这条配置**已保存**的 Key
 * （前端本来就拿不到明文，只有脱敏值，所以不该强迫用户重新粘贴）。
 */
async function testModelConnection(type, configId) {
    const userId = getCurrentUser()?.id || AppData.user.id || 1;
    const API_BASE = window.__SELF_GROW_API_BASE__ || 'http://localhost:3001';

    const model = document.getElementById('mc-model').value.trim();
    const base_url = document.getElementById('mc-base-url').value.trim();
    const api_key = document.getElementById('mc-api-key').value.trim();
    const resultEl = document.getElementById('mc-test-result');

    if (!model) { showToast('请先填写模型标识', 'error'); return; }
    // 没填、且这条配置也没有已保存的 Key → 才拦
    if (!api_key && !_mcSavedKeyMasked) {
        showToast('请填写 API Key（这条配置还没有已保存的 Key）', 'error');
        return;
    }

    if (resultEl) { resultEl.textContent = '测试中…'; resultEl.className = 'usercenter-modal-test-result'; }

    try {
        const resp = await fetch(`${API_BASE}/api/model-configs/test?user_id=${userId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ type, model, base_url, api_key,
                                   config_id: (configId || 0) || null }),
        });
        const data = await resp.json();
        if (resultEl) {
            resultEl.textContent = data.success ? '✓ ' + (data.message || '连接成功') : '✗ ' + (data.message || '连接失败');
            resultEl.className = 'usercenter-modal-test-result ' + (data.success ? 'usercenter-modal-test-result--ok' : 'usercenter-modal-test-result--fail');
        }
    } catch (e) {
        if (resultEl) {
            resultEl.textContent = '✗ ' + e.message;
            resultEl.className = 'usercenter-modal-test-result usercenter-modal-test-result--fail';
        }
    }
}

/** 删除模型 */
async function deleteModel(configId) {
    if (!confirm('确定删除这个模型配置吗？')) return;
    const userId = getCurrentUser()?.id || AppData.user.id || 1;
    const API_BASE = window.__SELF_GROW_API_BASE__ || 'http://localhost:3001';
    try {
        const resp = await fetch(`${API_BASE}/api/model-configs/${configId}?user_id=${userId}`, { method: 'DELETE' });
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        showToast('模型已删除', 'success');
        loadModelInfo();
    } catch (e) {
        showToast(`删除失败：${e.message}`, 'error');
    }
}

/** 切换启用 */
async function activateModel(configId) {
    const userId = getCurrentUser()?.id || AppData.user.id || 1;
    const API_BASE = window.__SELF_GROW_API_BASE__ || 'http://localhost:3001';
    try {
        const resp = await fetch(`${API_BASE}/api/model-configs/${configId}/activate?user_id=${userId}`, { method: 'POST' });
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        showToast('已切换启用模型', 'success');
        loadModelInfo();
    } catch (e) {
        showToast(`切换失败：${e.message}`, 'error');
    }
}
