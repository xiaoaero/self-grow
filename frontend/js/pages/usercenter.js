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
                <span class="usercenter-card__header-icon">🤖</span> 模型信息
            </div>
            <div id="usercenter-models" class="usercenter-models">
                <div class="usercenter-loading">加载模型配置中…</div>
            </div>
        </div>
    `;

    loadModelInfo();
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

/** 打开模型编辑弹窗（configId 为 null 时新增，type 由「添加」按钮决定） */
function openModelModal(configId, type) {
    const isEdit = configId != null;
    const userId = getCurrentUser()?.id || AppData.user.id || 1;
    const API_BASE = window.__SELF_GROW_API_BASE__ || 'http://localhost:3001';

    const buildForm = (cfg) => {
        const c = cfg || { type: type || 'llm', name: '', model: '', base_url: '', api_key: '' };
        const typeLabel = c.type === 'llm' ? '文本模型 (LLM)' : '语音模型 (ASR)';
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
                    <input class="input" id="mc-api-key" type="password" placeholder="${isEdit ? '留空则不修改' : 'sk-...'}" value="">
                </div>
                <div class="usercenter-modal-test">
                    <button class="btn btn--ghost" onclick="testModelConnection('${c.type}')">测试连通性</button>
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

/** 测试模型连通性 */
async function testModelConnection(type) {
    const userId = getCurrentUser()?.id || AppData.user.id || 1;
    const API_BASE = window.__SELF_GROW_API_BASE__ || 'http://localhost:3001';

    const model = document.getElementById('mc-model').value.trim();
    const base_url = document.getElementById('mc-base-url').value.trim();
    const api_key = document.getElementById('mc-api-key').value.trim();
    const resultEl = document.getElementById('mc-test-result');

    if (!model) { showToast('请先填写模型标识', 'error'); return; }
    if (!api_key) { showToast('请填写 API Key 以测试连通性', 'error'); return; }

    if (resultEl) { resultEl.textContent = '测试中…'; resultEl.className = 'usercenter-modal-test-result'; }

    try {
        const resp = await fetch(`${API_BASE}/api/model-configs/test?user_id=${userId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ type, model, base_url, api_key }),
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
