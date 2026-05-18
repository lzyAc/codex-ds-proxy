/**
 * Codex DeepSeek Proxy - Web 管理面板逻辑
 */

// ===== 状态 =====
let currentPanel = 'dashboard';
let config = {};
let statusRefreshTimer = null;

// ===== 初始化 =====
document.addEventListener('DOMContentLoaded', () => {
    initNavigation();
    loadConfig();
    refreshAll();
    statusRefreshTimer = setInterval(refreshAll, 5000);
});

// ===== 导航 =====
function initNavigation() {
    document.querySelectorAll('.nav-item').forEach(item => {
        item.addEventListener('click', (e) => {
            e.preventDefault();
            const panel = item.dataset.panel;
            switchPanel(panel);
        });
    });
}

function switchPanel(panel) {
    currentPanel = panel;

    document.querySelectorAll('.nav-item').forEach(i => i.classList.remove('active'));
    document.querySelector(`[data-panel="${panel}"]`).classList.add('active');

    document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
    document.getElementById(`panel-${panel}`).classList.add('active');

    if (panel === 'logs') refreshLogs();
    if (panel === 'env') loadEnvInstructions();
    if (panel === 'config') loadConfigToForm();
    if (panel === 'models') loadMappingsToForm();
}

// ===== API 调用 =====
async function apiGet(path) {
    try {
        const resp = await fetch(`/api${path}`);
        return await resp.json();
    } catch (e) {
        console.error('API error:', e);
        return null;
    }
}

async function apiPost(path, data) {
    try {
        const resp = await fetch(`/api${path}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data),
        });
        return await resp.json();
    } catch (e) {
        console.error('API error:', e);
        return { ok: false, error: e.message };
    }
}

// ===== 刷新所有状态 =====
async function refreshAll() {
    await refreshProxyStatus();
    if (currentPanel === 'dashboard') {
        await refreshDashboardStats();
    }
    if (currentPanel === 'logs') {
        await refreshLogs();
    }
}

async function refreshProxyStatus() {
    const status = await apiGet('/proxy/status');
    const dot = document.getElementById('statusDot');
    const text = document.getElementById('statusText');

    if (status && status.running) {
        dot.className = 'status-dot online';
        text.textContent = `代理运行中 :${status.port}`;

        document.getElementById('statStatus').textContent = '运行中';
        document.getElementById('statStatus').style.color = 'var(--green)';
        document.getElementById('infoProxyUrl').textContent = `http://127.0.0.1:${status.port}/v1`;

        if (status.start_time) {
            const start = new Date(status.start_time);
            const now = new Date();
            const diff = Math.floor((now - start) / 1000);
            const h = Math.floor(diff / 3600);
            const m = Math.floor((diff % 3600) / 60);
            const s = diff % 60;
            document.getElementById('infoUptime').textContent =
                `${h}时${m}分${s}秒`;
        }

        document.getElementById('statRequests').textContent = status.total_requests || 0;
        document.getElementById('statTokens').textContent = formatTokens(status.total_tokens || 0);
    } else {
        dot.className = 'status-dot offline';
        text.textContent = '代理未运行';

        document.getElementById('statStatus').textContent = '已停止';
        document.getElementById('statStatus').style.color = 'var(--red)';
        document.getElementById('infoUptime').textContent = '--';
    }
}

async function refreshDashboardStats() {
    const configResp = await apiGet('/config');
    if (configResp) {
        document.getElementById('statModel').textContent = configResp.deepseek_model || '--';
    }
}

// ===== 配置管理 =====
async function loadConfig() {
    config = await apiGet('/config') || {};
}

async function loadConfigToForm() {
    await loadConfig();
    if (config.deepseek_api_key) {
        document.getElementById('cfgApiKey').value = config.deepseek_api_key;
    }
    document.getElementById('cfgBaseUrl').value = config.deepseek_base_url || 'https://api.deepseek.com';
    document.getElementById('cfgModel').value = config.deepseek_model || 'deepseek-v4-pro';
    document.getElementById('cfgProxyPort').value = config.proxy_port || 8787;
    document.getElementById('cfgAutoStart').checked = config.auto_start || false;
}

async function saveConfig(e) {
    e.preventDefault();
    const data = {
        deepseek_api_key: document.getElementById('cfgApiKey').value,
        deepseek_base_url: document.getElementById('cfgBaseUrl').value,
        deepseek_model: document.getElementById('cfgModel').value,
        proxy_port: parseInt(document.getElementById('cfgProxyPort').value),
        auto_start: document.getElementById('cfgAutoStart').checked,
    };

    const result = await apiPost('/config', data);
    if (result.ok) {
        showToast('配置已保存', 'success');
        await loadConfig();
        refreshAll();
    } else {
        showToast('保存失败: ' + (result.error || '未知错误'), 'error');
    }
}

// ===== 连接测试 =====
async function testConnection() {
    const resultDiv = document.getElementById('testResult');
    resultDiv.className = 'test-result';
    resultDiv.textContent = '⏳ 正在测试连接...';
    resultDiv.classList.remove('hidden');
    // 滚动到可见
    resultDiv.scrollIntoView({ behavior: 'smooth', block: 'center' });

    const result = await apiPost('/config/test', {});
    resultDiv.classList.remove('hidden');

    if (result.ok) {
        resultDiv.className = 'test-result success';
        resultDiv.textContent = '✅ ' + result.message;
    } else {
        resultDiv.className = 'test-result error';
        resultDiv.textContent = '❌ ' + (result.error || '连接失败');
    }
}

// ===== 模型映射 =====
async function loadMappingsToForm() {
    await loadConfig();
    const mapping = config.model_mapping || {};
    const tbody = document.getElementById('mappingBody');
    tbody.innerHTML = '';

    Object.entries(mapping).forEach(([openai, deepseek]) => {
        addMappingRowInternal(openai, deepseek);
    });
}

function addMappingRowInternal(openai = '', deepseek = '') {
    const tbody = document.getElementById('mappingBody');
    const tr = document.createElement('tr');
    tr.innerHTML = `
        <td><input type="text" class="map-openai" value="${escapeHtml(openai)}" placeholder="gpt-4"></td>
        <td class="mapping-arrow">→</td>
        <td><input type="text" class="map-deepseek" value="${escapeHtml(deepseek)}" placeholder="deepseek-v4-pro"></td>
        <td><button class="btn btn-sm btn-danger" onclick="this.closest('tr').remove()">删除</button></td>
    `;
    tbody.appendChild(tr);
}

function addMappingRow() {
    addMappingRowInternal();
}

async function saveMappings() {
    const mapping = {};
    document.querySelectorAll('#mappingBody tr').forEach(tr => {
        const openai = tr.querySelector('.map-openai').value.trim();
        const deepseek = tr.querySelector('.map-deepseek').value.trim();
        if (openai && deepseek) {
            mapping[openai] = deepseek;
        }
    });

    const result = await apiPost('/config', { model_mapping: mapping });
    if (result.ok) {
        showToast('模型映射已保存', 'success');
        await loadConfig();
    } else {
        showToast('保存失败: ' + (result.error || '未知错误'), 'error');
    }
}

// ===== 请求日志 =====
async function refreshLogs() {
    const resp = await apiGet('/logs?limit=50');
    const list = document.getElementById('logList');
    const logs = resp && resp.logs ? resp.logs : [];
    if (logs.length === 0) {
        list.innerHTML = '<div class="log-empty">暂无请求记录 — 启动代理后，通过 Codex CLI 发出的请求会显示在这里</div>';
        return;
    }

    const reversed = [...logs].reverse();
    list.innerHTML = reversed.map(entry => {
        const time = entry.time ? entry.time.slice(11, 19) : '--:--:--';
        const statusClass = entry.status === 'success' ? 'success' : 'error';
        return `
            <div class="log-entry">
                <span class="log-time">${escapeHtml(time)}</span>
                <span class="log-status ${statusClass}"></span>
                <span class="log-model">${escapeHtml(entry.model_original || '?')}</span>
                <span class="log-model-arrow">→</span>
                <span class="log-model">${escapeHtml(entry.model_mapped || '?')}</span>
                <span class="log-tokens">${formatTokens(entry.tokens || 0)} tk</span>
                <span class="log-duration">${entry.duration_ms || 0}ms</span>
                ${entry.error ? `<span class="log-error">${escapeHtml(entry.error)}</span>` : ''}
            </div>
        `;
    }).join('');
}

async function clearLogs() {
    // 日志在内存中，通过刷新获取空状态
    // 由于日志存储在代理进程中，这里通过重新请求来确认清空
    document.getElementById('logList').innerHTML = '<div class="log-empty">请求日志已刷新</div>';
    showToast('日志显示已刷新（新请求将在代理重启后从零开始计数）', 'info');
}

// ===== 环境变量 =====
async function loadEnvInstructions() {
    const resp = await apiGet('/env');
    if (resp && resp.instructions) {
        document.getElementById('envCode').textContent = resp.instructions;
    }
}

async function copyEnv() {
    const resp = await apiGet('/env');
    if (resp && resp.instructions) {
        try {
            await navigator.clipboard.writeText(resp.instructions);
            showToast('已复制到剪贴板！', 'success');
        } catch (e) {
            // fallback
            const textarea = document.createElement('textarea');
            textarea.value = resp.instructions;
            document.body.appendChild(textarea);
            textarea.select();
            document.execCommand('copy');
            document.body.removeChild(textarea);
            showToast('已复制到剪贴板！', 'success');
        }
    }
}

async function copyUnset() {
    const cmd = 'unset OPENAI_BASE_URL\nunset OPENAI_API_KEY';
    try {
        await navigator.clipboard.writeText(cmd);
        showToast('清空命令已复制！在终端粘贴执行即可', 'success');
    } catch (e) {
        const textarea = document.createElement('textarea');
        textarea.value = cmd;
        document.body.appendChild(textarea);
        textarea.select();
        document.execCommand('copy');
        document.body.removeChild(textarea);
        showToast('清空命令已复制！', 'success');
    }
}

// ===== 工具函数 =====
function formatTokens(n) {
    if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M';
    if (n >= 1000) return (n / 1000).toFixed(1) + 'K';
    return n.toString();
}

function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

function showToast(message, type = 'info') {
    const existing = document.querySelector('.toast');
    if (existing) existing.remove();

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    document.body.appendChild(toast);

    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transition = 'opacity 0.3s';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}
