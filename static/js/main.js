// Global state
let currentArticle = null;
let articles = [];
let sourceOptions = [];
let rankingConfigs = {};
let scenarios = [];
let connectors = [];
const connectorRunsCache = {};
const connectorMetricsById = {};
let connectorSearchTerm = '';
let connectorStatusFilter = 'all';

// Initialize the application
document.addEventListener('DOMContentLoaded', () => {
    loadArticles();
    loadStats();
    loadSources();
    loadRankingConfigs();
    loadScenarios();
    loadOfflineMetrics();
    loadScenarioMetrics();
    loadConnectors();
    loadConnectorMetrics();
    loadSchedulerStatus();
    loadDecisionContext();
    setupEventListeners();
    setInterval(loadSchedulerStatus, 15000);
});

async function loadArticles() {
    try {
        const articleList = document.getElementById('article-list');
        articleList.innerHTML = `
            <div class="text-center p-3">
                <div class="spinner-border text-primary" role="status">
                    <span class="visually-hidden">Loading...</span>
                </div>
                <p class="mt-2">Loading articles...</p>
            </div>
        `;

        const response = await fetch('/api/articles');
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Failed to load articles');
        }

        articles = await response.json();
        if (!Array.isArray(articles)) {
            throw new Error('Invalid response format');
        }

        displayArticles();
    } catch (error) {
        console.error('Error loading articles:', error);
        showError('Failed to load articles: ' + error.message);
        document.getElementById('article-list').innerHTML = `
            <div class="alert alert-warning">
                <i class="fas fa-exclamation-triangle me-2"></i>
                No articles available. Please try again later.
            </div>
        `;
    }
}

async function loadSources() {
    try {
        const response = await fetch('/api/sources');
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Failed to load sources');
        }

        const data = await response.json();
        sourceOptions = data.sources || [];
        renderSourceFilters();
        loadDecisionContext();
    } catch (error) {
        console.error('Error loading sources:', error);
        document.getElementById('source-filters').innerHTML = `<span>Failed to load sources</span>`;
    }
}

async function loadConnectors() {
    try {
        const response = await fetch('/api/connectors');
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Failed to load connectors');
        }
        const data = await response.json();
        connectors = data.connectors || [];
        renderConnectors();
        loadConnectorMetrics();
    } catch (error) {
        console.error('Error loading connectors:', error);
        document.getElementById('connector-list').innerHTML = '<span>Connectors unavailable</span>';
    }
}

async function loadConnectorMetrics() {
    const container = document.getElementById('connector-metrics');
    if (!container) return;
    try {
        const response = await fetch('/api/connectors/metrics');
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Failed to load connector metrics');
        }
        const payload = await response.json();
        Object.keys(connectorMetricsById).forEach(key => delete connectorMetricsById[key]);
        (payload.connectors || []).forEach(item => {
            connectorMetricsById[item.connector_id] = item;
        });
        container.innerHTML = `
            <div><strong>Connectors:</strong> ${payload.total_connectors}</div>
            <div><strong>Runs:</strong> ${payload.total_runs}</div>
            <div><strong>Success rate:</strong> ${(Number(payload.overall_success_rate || 0) * 100).toFixed(1)}%</div>
            <div><strong>Avg ingested/run:</strong> ${Number(payload.avg_ingested_per_run || 0).toFixed(2)}</div>
        `;
        renderConnectors();
    } catch (error) {
        container.textContent = `Metrics unavailable: ${error.message}`;
    }
}

function renderConnectors() {
    const container = document.getElementById('connector-list');
    if (!connectors.length) {
        container.innerHTML = '<span>No connectors configured.</span>';
        return;
    }

    const filtered = connectors.filter(connector => {
        const name = (connector.name || '').toLowerCase();
        const metric = connectorMetricsById[connector.connector_id] || {};
        const status = metric.last_status || 'none';
        const matchesName = !connectorSearchTerm || name.includes(connectorSearchTerm);
        const matchesStatus = connectorStatusFilter === 'all' || status === connectorStatusFilter;
        return matchesName && matchesStatus;
    });

    if (!filtered.length) {
        container.innerHTML = '<span>No connectors match current filters.</span>';
        return;
    }

    container.innerHTML = filtered.map(connector => {
        const metric = connectorMetricsById[connector.connector_id] || {};
        return `
            <div class="border rounded p-2 mb-2 connector-card" data-id="${connector.connector_id}">
                <div class="fw-semibold">${connector.name}</div>
                <div class="text-muted">${connector.connector_type}</div>
                <div class="text-muted small">${connector.config?.base_url || connector.config?.feed_url || 'n/a'}</div>
                <div class="text-muted small">
                    Auto-sync: ${connector.config?.auto_sync_enabled ? 'on' : 'off'}
                    (${Number(connector.config?.sync_interval_minutes || 60)} min)
                </div>
                <div class="text-muted small">
                    Last status: ${metric.last_status || 'none'}
                    ${typeof metric.success_rate === 'number' ? ` | Success ${(metric.success_rate * 100).toFixed(0)}%` : ''}
                </div>
                <div class="row g-2 mt-1">
                    <div class="col-4">
                        <input class="form-control form-control-sm connector-max-articles" type="number" min="1" max="50" value="${Number(connector.config?.max_articles || 10)}" title="max_articles">
                    </div>
                    <div class="col-4">
                        <input class="form-control form-control-sm connector-sync-interval" type="number" min="1" value="${Number(connector.config?.sync_interval_minutes || 60)}" title="sync_interval_minutes">
                    </div>
                    <div class="col-4 d-flex align-items-center">
                        <div class="form-check mb-0">
                            <input class="form-check-input connector-auto-sync" type="checkbox" ${connector.config?.auto_sync_enabled ? 'checked' : ''}>
                            <label class="form-check-label small">Auto</label>
                        </div>
                    </div>
                </div>
                <div class="d-flex gap-2 mt-2">
                    <button class="btn btn-sm btn-outline-secondary connector-sync" data-id="${connector.connector_id}">Sync</button>
                    <button class="btn btn-sm btn-outline-primary connector-sync-async" data-id="${connector.connector_id}">Sync Async</button>
                    <button class="btn btn-sm btn-outline-info connector-runs" data-id="${connector.connector_id}">Runs</button>
                    <button class="btn btn-sm btn-outline-success connector-save-config" data-id="${connector.connector_id}">Save Config</button>
                    <button class="btn btn-sm btn-outline-warning connector-toggle" data-id="${connector.connector_id}" data-enabled="${connector.enabled}">
                        ${connector.enabled ? 'Disable' : 'Enable'}
                    </button>
                    <button class="btn btn-sm btn-outline-danger connector-delete" data-id="${connector.connector_id}">Delete</button>
                </div>
                ${connector.last_run_at ? `<div class="small text-muted mt-1">Last sync: ${connector.last_run_at}</div>` : ''}
                <div id="connector-config-error-${connector.connector_id}" class="small text-danger mt-1" style="display:none;"></div>
                <div id="connector-runs-${connector.connector_id}" class="small mt-2"></div>
            </div>
        `;
    }).join('');
}

async function createConnector() {
    setConnectorFormError('');
    const name = document.getElementById('connector-name').value.trim();
    const connectorType = document.getElementById('connector-type').value;
    const url = document.getElementById('connector-url').value.trim();
    const maxArticles = Number(document.getElementById('connector-max-articles').value);
    const autoSyncEnabled = document.getElementById('connector-auto-sync').checked;
    const syncIntervalMinutes = Number(document.getElementById('connector-sync-interval').value);

    const validationError = validateConnectorInputs({
        name,
        url,
        maxArticles,
        syncIntervalMinutes
    });
    if (validationError) {
        setConnectorFormError(validationError);
        throw new Error(validationError);
    }

    const config = connectorType === 'rss' ? { feed_url: url } : { base_url: url };
    config.max_articles = Number.isFinite(maxArticles) && maxArticles > 0 ? maxArticles : 10;
    config.auto_sync_enabled = Boolean(autoSyncEnabled);
    config.sync_interval_minutes = Number.isFinite(syncIntervalMinutes) && syncIntervalMinutes > 0
        ? syncIntervalMinutes
        : 60;
    const response = await fetch('/api/connectors', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            name,
            connector_type: connectorType,
            config,
            enabled: true
        })
    });
    if (!response.ok) {
        const error = await response.json();
        throw new Error(error.error || 'Failed to create connector');
    }
    document.getElementById('connector-name').value = '';
    document.getElementById('connector-url').value = '';
    document.getElementById('connector-max-articles').value = '10';
    document.getElementById('connector-sync-interval').value = '60';
    document.getElementById('connector-auto-sync').checked = false;
    await loadConnectors();
}

async function handleConnectorAction(event) {
    const syncBtn = event.target.closest('.connector-sync');
    const syncAsyncBtn = event.target.closest('.connector-sync-async');
    const runsBtn = event.target.closest('.connector-runs');
    const saveConfigBtn = event.target.closest('.connector-save-config');
    const toggleBtn = event.target.closest('.connector-toggle');
    const deleteBtn = event.target.closest('.connector-delete');
    const card = event.target.closest('.connector-card');

    if (!syncBtn && !syncAsyncBtn && !runsBtn && !saveConfigBtn && !toggleBtn && !deleteBtn) return;

    try {
        if (syncBtn) {
            const id = syncBtn.dataset.id;
            const response = await fetch(`/api/connectors/${encodeURIComponent(id)}/sync`, { method: 'POST' });
            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.error || 'Failed to sync connector');
            }
            document.getElementById('connector-sync-summary').textContent = `Sync finished for ${id}`;
            await loadConnectorRuns(id);
        }

        if (syncAsyncBtn) {
            const id = syncAsyncBtn.dataset.id;
            const response = await fetch(`/api/connectors/${encodeURIComponent(id)}/sync-async`, { method: 'POST' });
            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.error || 'Failed to enqueue connector sync');
            }
            const payload = await response.json();
            document.getElementById('connector-sync-summary').textContent = `Queued run ${payload.run_id} for ${id}`;
            await pollConnectorRun(payload.run_id, id);
        }

        if (runsBtn) {
            const id = runsBtn.dataset.id;
            await loadConnectorRuns(id);
            return;
        }

        if (saveConfigBtn) {
            const id = saveConfigBtn.dataset.id;
            const target = connectors.find(connector => connector.connector_id === id);
            setConnectorCardError(id, '');
            const nextMaxArticles = Number(card?.querySelector('.connector-max-articles')?.value);
            const nextSyncInterval = Number(card?.querySelector('.connector-sync-interval')?.value);
            const nextAutoSync = Boolean(card?.querySelector('.connector-auto-sync')?.checked);
            const connectorUrl = target?.config?.feed_url || target?.config?.base_url || '';
            const validationError = validateConnectorInputs({
                name: target?.name || '',
                url: connectorUrl,
                maxArticles: nextMaxArticles,
                syncIntervalMinutes: nextSyncInterval
            });
            if (validationError) {
                setConnectorCardError(id, validationError);
                throw new Error(validationError);
            }
            const config = { ...(target?.config || {}) };
            config.max_articles = Number.isFinite(nextMaxArticles) && nextMaxArticles > 0 ? nextMaxArticles : 10;
            config.sync_interval_minutes = Number.isFinite(nextSyncInterval) && nextSyncInterval > 0
                ? nextSyncInterval
                : 60;
            config.auto_sync_enabled = nextAutoSync;

            const response = await fetch(`/api/connectors/${encodeURIComponent(id)}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    enabled: target?.enabled,
                    name: target?.name,
                    connector_type: target?.connector_type,
                    config
                })
            });
            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.error || 'Failed to save connector config');
            }
            document.getElementById('connector-sync-summary').textContent = `Saved config for ${id}`;
        }

        if (toggleBtn) {
            const id = toggleBtn.dataset.id;
            const currentlyEnabled = toggleBtn.dataset.enabled === 'true';
            if (currentlyEnabled) {
                const confirmed = window.confirm('Disable this connector? Scheduled and manual syncs will be blocked.');
                if (!confirmed) return;
            }
            const target = connectors.find(connector => connector.connector_id === id);
            const response = await fetch(`/api/connectors/${encodeURIComponent(id)}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    enabled: !currentlyEnabled,
                    name: target?.name,
                    connector_type: target?.connector_type,
                    config: target?.config || {}
                })
            });
            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.error || 'Failed to update connector');
            }
        }

        if (deleteBtn) {
            const id = deleteBtn.dataset.id;
            const confirmed = window.confirm('Delete this connector and its future sync ability?');
            if (!confirmed) return;
            const response = await fetch(`/api/connectors/${encodeURIComponent(id)}`, { method: 'DELETE' });
            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.error || 'Failed to delete connector');
            }
        }

        await loadConnectors();
    } catch (error) {
        console.error('Connector action failed:', error);
        showError(error.message || 'Connector operation failed');
    }
}

async function syncDueConnectors() {
    try {
        document.getElementById('connector-sync-summary').textContent = 'Scanning due connectors...';
        const response = await fetch('/api/connectors/sync-due', { method: 'POST' });
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Failed to trigger due connector sync');
        }
        const payload = await response.json();
        document.getElementById('connector-sync-summary').textContent =
            `Triggered ${payload.triggered_count}, skipped ${payload.skipped_count}`;

        const pollTasks = (payload.triggered || []).map(item => pollConnectorRun(item.run_id, item.connector_id));
        await Promise.all(pollTasks);
        await loadConnectors();
        await loadConnectorMetrics();
    } catch (error) {
        console.error('Error syncing due connectors:', error);
        showError(error.message || 'Failed to run due connector sync');
    }
}

async function loadSchedulerStatus() {
    const statusEl = document.getElementById('scheduler-status');
    if (!statusEl) return;
    try {
        const response = await fetch('/api/connectors/scheduler/status');
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Failed to load scheduler status');
        }
        const payload = await response.json();
        const lastRun = payload.last_run_at || 'never';
        const state = payload.running ? 'running' : (payload.enabled ? 'enabled' : 'disabled');
        statusEl.textContent = `${state}; runs ${payload.runs_total}; last ${lastRun}`;
    } catch (error) {
        statusEl.textContent = `Scheduler status error: ${error.message}`;
    }
}

async function runSchedulerNow() {
    try {
        const response = await fetch('/api/connectors/scheduler/run-now', { method: 'POST' });
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Failed to run scheduler now');
        }
        const payload = await response.json();
        const summary = payload.scheduler_run || {};
        document.getElementById('connector-sync-summary').textContent =
            `Scheduler run: triggered ${summary.triggered_count || 0}, skipped ${summary.skipped_count || 0}`;
        await loadSchedulerStatus();
        await loadConnectors();
        await loadConnectorMetrics();
    } catch (error) {
        showError(error.message || 'Scheduler run failed');
    }
}

async function pollConnectorRun(runId, connectorId) {
    for (let attempt = 0; attempt < 30; attempt += 1) {
        const response = await fetch(`/api/connector-runs/${encodeURIComponent(runId)}`);
        if (!response.ok) {
            break;
        }
        const run = await response.json();
        if (['completed', 'completed_with_errors', 'failed'].includes(run.status)) {
            await loadConnectorRuns(connectorId);
            return;
        }
        await new Promise(resolve => setTimeout(resolve, 800));
    }
}

function statusBadgeClass(status) {
    if (status === 'completed') return 'bg-success';
    if (status === 'completed_with_errors') return 'bg-warning text-dark';
    if (status === 'failed') return 'bg-danger';
    return 'bg-secondary';
}

async function loadConnectorRuns(connectorId) {
    try {
        const response = await fetch(`/api/connectors/${encodeURIComponent(connectorId)}/runs?limit=5`);
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Failed to load connector runs');
        }
        const payload = await response.json();
        connectorRunsCache[connectorId] = payload.runs || [];
        renderConnectorRuns(connectorId);
        await loadConnectorMetrics();
    } catch (error) {
        console.error('Error loading connector runs:', error);
        showError(error.message || 'Failed to load connector runs');
    }
}

function renderConnectorRuns(connectorId) {
    const target = document.getElementById(`connector-runs-${connectorId}`);
    if (!target) return;

    const runs = connectorRunsCache[connectorId] || [];
    if (!runs.length) {
        target.innerHTML = '<span class="text-muted">No run history.</span>';
        return;
    }

    target.innerHTML = runs.map(run => `
        <div class="border-top pt-1 mt-1">
            <span class="badge ${statusBadgeClass(run.status)}">${run.status}</span>
            <span class="ms-1">attempted ${run.attempted}, ingested ${run.ingested}</span>
            ${run.error_count ? `<div class="text-danger">errors: ${run.error_count}</div>` : ''}
            ${run.errors && run.errors.length ? `<div class="text-danger small">${run.errors[0]}</div>` : ''}
            <div class="text-muted">${run.created_at}</div>
        </div>
    `).join('');
}

function validateConnectorInputs({ name, url, maxArticles, syncIntervalMinutes }) {
    if (!name || !name.trim()) return 'Connector name is required.';
    if (!url || !url.trim()) return 'Connector URL is required.';
    try {
        const parsed = new URL(url);
        if (!['http:', 'https:'].includes(parsed.protocol)) {
            return 'URL must start with http:// or https://';
        }
    } catch (_error) {
        return 'Please enter a valid URL.';
    }
    if (!Number.isFinite(maxArticles) || maxArticles < 1 || maxArticles > 50) {
        return 'Max articles must be between 1 and 50.';
    }
    if (!Number.isFinite(syncIntervalMinutes) || syncIntervalMinutes < 1 || syncIntervalMinutes > 1440) {
        return 'Sync interval must be between 1 and 1440 minutes.';
    }
    return '';
}

function setConnectorFormError(message) {
    const el = document.getElementById('connector-form-error');
    if (!el) return;
    if (!message) {
        el.style.display = 'none';
        el.textContent = '';
        return;
    }
    el.style.display = 'block';
    el.textContent = message;
}

function setConnectorCardError(connectorId, message) {
    const el = document.getElementById(`connector-config-error-${connectorId}`);
    if (!el) return;
    if (!message) {
        el.style.display = 'none';
        el.textContent = '';
        return;
    }
    el.style.display = 'block';
    el.textContent = message;
}

function renderSourceFilters() {
    const sourceFilters = document.getElementById('source-filters');
    if (!sourceOptions.length) {
        sourceFilters.innerHTML = '<span>No source information available.</span>';
        return;
    }

    sourceFilters.innerHTML = sourceOptions.map(source => `
        <div class="border rounded p-2 mb-2">
            <div class="form-check mb-1">
                <input class="form-check-input source-filter" type="checkbox" value="${source.source}" id="query-${source.source.replace(/[^a-zA-Z0-9]/g, '_')}" ${source.enabled ? 'checked' : ''} ${source.enabled ? '' : 'disabled'}>
                <label class="form-check-label" for="query-${source.source.replace(/[^a-zA-Z0-9]/g, '_')}">
                    ${source.source} (${source.article_count})
                </label>
            </div>
            <div class="d-flex gap-2 align-items-center">
                <div class="form-check">
                    <input class="form-check-input source-enabled" type="checkbox" data-source="${source.source}" id="enabled-${source.source.replace(/[^a-zA-Z0-9]/g, '_')}" ${source.enabled ? 'checked' : ''}>
                    <label class="form-check-label small" for="enabled-${source.source.replace(/[^a-zA-Z0-9]/g, '_')}">Enabled</label>
                </div>
                <label class="small text-muted mb-0">Weight</label>
                <input class="form-control form-control-sm source-weight" style="max-width:90px" type="number" min="0.1" step="0.1" data-source="${source.source}" value="${Number(source.default_weight ?? 1).toFixed(1)}">
            </div>
        </div>
    `).join('');
}

function collectSourceSettingsFromUI() {
    const enabledMap = {};
    document.querySelectorAll('.source-enabled').forEach(el => {
        enabledMap[el.dataset.source] = el.checked;
    });

    const weightMap = {};
    document.querySelectorAll('.source-weight').forEach(el => {
        const parsed = Number(el.value);
        weightMap[el.dataset.source] = Number.isFinite(parsed) && parsed > 0 ? parsed : 1.0;
    });

    return sourceOptions.map(source => ({
        source: source.source,
        enabled: enabledMap[source.source] ?? true,
        default_weight: weightMap[source.source] ?? 1.0
    }));
}

async function saveSourceSettings() {
    try {
        const settings = collectSourceSettingsFromUI();
        await Promise.all(settings.map(async (item) => {
            const response = await fetch(`/api/source-settings/${encodeURIComponent(item.source)}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    enabled: item.enabled,
                    default_weight: item.default_weight
                })
            });
            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.error || `Failed for source ${item.source}`);
            }
        }));

        await loadSources();
    } catch (error) {
        console.error('Error saving source settings:', error);
        showError('Failed to save source settings');
    }
}

async function loadRankingConfigs() {
    try {
        const response = await fetch('/api/ranking-configs');
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Failed to load ranking configs');
        }

        const data = await response.json();
        rankingConfigs = data.configs || {};

        const select = document.getElementById('ranking-config');
        const configIds = Object.keys(rankingConfigs);
        select.innerHTML = configIds.map(id => `<option value="${id}">${id}</option>`).join('');

        if (data.default_config_id && rankingConfigs[data.default_config_id]) {
            select.value = data.default_config_id;
        }
        loadDecisionContext();
    } catch (error) {
        console.error('Error loading ranking configs:', error);
        document.getElementById('ranking-config').innerHTML = '<option value="balanced">balanced</option>';
    }
}

function getSelectedScenarioId() {
    return document.getElementById('scenario-select')?.value || '';
}

function getExternalUserId() {
    const raw = document.getElementById('external-user-id')?.value || '';
    return raw.trim();
}

function applyScenarioToEditor(scenario) {
    document.getElementById('scenario-id').value = scenario?.scenario_id || '';
    document.getElementById('scenario-name').value = scenario?.name || '';
    document.getElementById('scenario-enabled').checked = Boolean(scenario?.enabled ?? true);
    document.getElementById('scenario-rule-set').value = JSON.stringify(scenario?.rule_set || {}, null, 2);
}

async function loadScenarios() {
    try {
        const response = await fetch('/api/scenarios?include_disabled=true');
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Failed to load scenarios');
        }
        const data = await response.json();
        scenarios = data.scenarios || [];
        const select = document.getElementById('scenario-select');
        const current = select.value;
        select.innerHTML = '<option value="">No scenario</option>' + scenarios
            .map(item => `<option value="${item.scenario_id}">${item.name} (${item.scenario_id})${item.enabled ? '' : ' [disabled]'}</option>`)
            .join('');
        if (current && scenarios.some(item => item.scenario_id === current)) {
            select.value = current;
        }
        const selected = scenarios.find(item => item.scenario_id === select.value);
        applyScenarioToEditor(selected || null);
        loadDecisionContext();
    } catch (error) {
        console.error('Error loading scenarios:', error);
        showError(`Failed to load scenarios: ${error.message}`);
    }
}

async function saveScenario() {
    const scenarioId = (document.getElementById('scenario-id').value || '').trim();
    const name = (document.getElementById('scenario-name').value || '').trim();
    const enabled = document.getElementById('scenario-enabled').checked;
    const ruleSetRaw = document.getElementById('scenario-rule-set').value || '{}';
    if (!scenarioId) {
        throw new Error('Scenario ID is required');
    }
    if (!name) {
        throw new Error('Scenario name is required');
    }
    let ruleSet = {};
    try {
        ruleSet = JSON.parse(ruleSetRaw);
    } catch (_err) {
        throw new Error('Scenario rule set must be valid JSON');
    }

    const existing = scenarios.find(item => item.scenario_id === scenarioId);
    const method = existing ? 'PUT' : 'POST';
    const url = existing ? `/api/scenarios/${encodeURIComponent(scenarioId)}` : '/api/scenarios';
    const payload = {
        scenario_id: scenarioId,
        name,
        enabled,
        rule_set: ruleSet
    };
    const response = await fetch(url, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    });
    if (!response.ok) {
        const error = await response.json();
        throw new Error(error.error || 'Failed to save scenario');
    }
    await loadScenarios();
    document.getElementById('scenario-select').value = scenarioId;
    loadDecisionContext();
}

async function deleteScenario() {
    const scenarioId = (document.getElementById('scenario-id').value || '').trim();
    if (!scenarioId) {
        throw new Error('Select a scenario first');
    }
    const response = await fetch(`/api/scenarios/${encodeURIComponent(scenarioId)}`, { method: 'DELETE' });
    if (!response.ok) {
        const error = await response.json();
        throw new Error(error.error || 'Failed to delete scenario');
    }
    await loadScenarios();
    document.getElementById('scenario-select').value = '';
    applyScenarioToEditor(null);
    loadDecisionContext();
}

async function loadScenarioMetrics() {
    const container = document.getElementById('scenario-metrics');
    if (!container) return;
    try {
        const response = await fetch('/api/metrics/scenarios?days=30&top_articles=5');
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Failed to load scenario metrics');
        }
        const payload = await response.json();
        const scenariosRows = (payload.scenarios || []).map(item => `
            <tr>
                <td>${item.name || item.scenario_id}</td>
                <td>${item.impressions}</td>
                <td>${item.clicks}</td>
                <td>${(Number(item.ctr || 0) * 100).toFixed(1)}%</td>
                <td>${item.conversions}</td>
            </tr>
        `).join('');
        container.innerHTML = `
            <div><strong>Window:</strong> ${payload.window_days} days</div>
            <div><strong>Total impressions:</strong> ${payload.totals?.impressions ?? 0}</div>
            <div><strong>Total clicks:</strong> ${payload.totals?.clicks ?? 0}</div>
            <div><strong>Total CTR:</strong> ${(Number(payload.totals?.ctr || 0) * 100).toFixed(2)}%</div>
            <div class="table-responsive mt-2">
                <table class="table table-sm mb-0">
                    <thead><tr><th>Scenario</th><th>Impr.</th><th>Clicks</th><th>CTR</th><th>Conv.</th></tr></thead>
                    <tbody>${scenariosRows || '<tr><td colspan="5" class="text-muted">No scenario events yet.</td></tr>'}</tbody>
                </table>
            </div>
        `;
    } catch (error) {
        console.error('Error loading scenario metrics:', error);
        container.innerHTML = `Scenario metrics unavailable: ${error.message}`;
    }
}

async function loadDecisionContext() {
    const container = document.getElementById('decision-context');
    if (!container) return;
    try {
        const configId = document.getElementById('ranking-config')?.value || 'balanced';
        const selectedSources = getSelectedSources();
        const scenarioId = getSelectedScenarioId();
        const response = await fetch('/api/recommendation-context', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                config_id: configId,
                sources: selectedSources,
                scenario_id: scenarioId || undefined
            })
        });
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Failed to load decision context');
        }
        const context = await response.json();
        container.textContent = JSON.stringify(context, null, 2);
    } catch (error) {
        container.textContent = `Failed to load decision context: ${error.message}`;
    }
}

async function loadStats() {
    try {
        const response = await fetch('/api/stats');
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Failed to load statistics');
        }

        const stats = await response.json();
        displayStats(stats);
    } catch (error) {
        console.error('Error loading statistics:', error);
        showError('Failed to load statistics: ' + error.message);
    }
}

async function loadOfflineMetrics() {
    try {
        const response = await fetch('/api/metrics/offline?limit_runs=100');
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Failed to load offline metrics');
        }
        const metrics = await response.json();
        const container = document.getElementById('offline-metrics');
        container.innerHTML = `
            <div><strong>Runs analyzed:</strong> ${metrics.runs_analyzed ?? 0}</div>
            <div><strong>Avg score:</strong> ${Number(metrics.avg_score ?? 0).toFixed(4)}</div>
            <div><strong>Avg source diversity:</strong> ${Number(metrics.avg_source_diversity ?? 0).toFixed(4)}</div>
            <div><strong>Avg recommendations/run:</strong> ${Number(metrics.avg_recommendation_count ?? 0).toFixed(2)}</div>
        `;
    } catch (error) {
        console.error('Error loading offline metrics:', error);
        document.getElementById('offline-metrics').innerHTML = 'Metrics unavailable';
    }
}

function displayArticles() {
    const articleList = document.getElementById('article-list');
    if (!articles || articles.length === 0) {
        articleList.innerHTML = `
            <div class="alert alert-info">
                <i class="fas fa-info-circle me-2"></i>
                No articles available.
            </div>
        `;
        return;
    }

    articleList.innerHTML = articles.map(article => `
        <a href="#" class="list-group-item list-group-item-action" data-id="${article.article_id}">
            <div class="d-flex w-100 justify-content-between">
                <h6 class="mb-1">${article.title}</h6>
            </div>
            <small class="text-muted d-block">
                <i class="fas fa-rss me-1"></i>${article.source || 'unknown source'}
            </small>
            ${article.metadata.scraped_at ? `
                <small class="text-muted d-block">
                    <i class="fas fa-clock me-1"></i>
                    ${formatDate(article.metadata.scraped_at)}
                </small>
            ` : ''}
        </a>
    `).join('');
}

function displayArticle(article) {
    if (!article) return;

    currentArticle = article;

    document.getElementById('article-title').textContent = article.title || 'No Title';
    document.getElementById('article-content').textContent = article.content || 'No content available';

    const articleUrl = article.metadata?.url;
    const urlElement = document.getElementById('article-url');
    if (articleUrl) {
        urlElement.href = articleUrl;
        urlElement.style.display = 'inline-block';
    } else {
        urlElement.style.display = 'none';
    }

    document.getElementById('show-similar').style.display = 'inline-block';
}

function getSelectedSources() {
    return Array.from(document.querySelectorAll('.source-filter:checked')).map(cb => cb.value);
}

async function showSimilarArticles() {
    if (!currentArticle) {
        showError('Please select an article first');
        return;
    }

    try {
        const selectedSources = getSelectedSources();
        const configId = document.getElementById('ranking-config').value || 'balanced';
        const scenarioId = getSelectedScenarioId();
        const externalUserId = getExternalUserId();

        const similarList = document.getElementById('similar-list');
        similarList.innerHTML = `
            <div class="text-center p-3">
                <div class="spinner-border text-primary" role="status">
                    <span class="visually-hidden">Loading...</span>
                </div>
                <p class="mt-2">Finding similar articles...</p>
            </div>
        `;
        document.getElementById('similar-articles').style.display = 'block';

        const response = await fetch('/api/recommendations/query', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                user_id: 'demo_user',
                user_reads: [currentArticle.article_id],
                top_n: 5,
                sources: selectedSources,
                config_id: configId,
                scenario_id: scenarioId || undefined,
                external_user_id: externalUserId || undefined
            })
        });
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Failed to load similar articles');
        }

        const responsePayload = await response.json();
        const similarArticles = responsePayload.recommendations;
        if (!Array.isArray(similarArticles)) {
            throw new Error('Invalid response format');
        }

        if (similarArticles.length === 0) {
            similarList.innerHTML = `
                <div class="alert alert-info">
                    <i class="fas fa-info-circle me-2"></i>
                    No similar articles found for selected filters.
                </div>
            `;
            return;
        }

        similarList.innerHTML = similarArticles.map(article => {
            const contrib = article.feature_contributions || {};
            return `
                <div class="similar-article fade-in">
                    <h5>${article.title || 'No Title'}</h5>
                    <small class="text-muted d-block mb-2">
                        <i class="fas fa-rss me-1"></i>${article.source || 'unknown'}
                        <span class="ms-2">Config: ${article.config_id || 'n/a'}</span>
                    </small>
                    <p class="mb-2">${article.content ? article.content.substring(0, 150) + '...' : 'No content available'}</p>

                    <div class="similarity-indicators mb-2">
                        <div class="d-flex gap-2 flex-wrap">
                            <div class="similarity-indicator" title="Semantic Similarity">
                                <i class="fas fa-brain me-1"></i>
                                <span>${(article.similarity_components.semantic * 100).toFixed(1)}%</span>
                            </div>
                            <div class="similarity-indicator" title="Content Freshness">
                                <i class="fas fa-clock me-1"></i>
                                <span>${(article.similarity_components.freshness * 100).toFixed(1)}%</span>
                            </div>
                            <div class="similarity-indicator" title="Topic Clustering">
                                <i class="fas fa-layer-group me-1"></i>
                                <span>${(article.similarity_components.topic * 100).toFixed(1)}%</span>
                            </div>
                        </div>
                        <small class="text-muted d-block mt-1">
                            Weighted contributions: semantic ${formatContribution(contrib.semantic)}, freshness ${formatContribution(contrib.freshness)}, topic ${formatContribution(contrib.topic)}, source ${formatContribution(contrib.source)}
                        </small>
                        <small class="text-muted d-block mt-1">${article.explanation || ''}</small>
                        <small class="text-muted d-block mt-1">Overall Score: ${(article.score * 100).toFixed(1)}%</small>
                    </div>

                    ${article.url ? `
                        <a href="${article.url}" target="_blank" class="btn btn-sm btn-outline-primary">
                            <i class="fas fa-external-link-alt me-1"></i>
                            Read More
                        </a>
                    ` : ''}
                </div>
            `;
        }).join('');
        similarList.insertAdjacentHTML(
            'afterbegin',
            `<div class="alert alert-secondary py-2">
                Run ID: <code>${responsePayload.run_id}</code>
                ${responsePayload.external_user_id ? `<span class="ms-2">External User ID: <code>${responsePayload.external_user_id}</code></span>` : ''}
                ${responsePayload.scenario_id ? `<span class="ms-2">Scenario: <code>${responsePayload.scenario_id}</code></span>` : ''}
            </div>`
        );
        loadOfflineMetrics();
        loadScenarioMetrics();
    } catch (error) {
        console.error('Error loading similar articles:', error);
        showError('Failed to load similar articles: ' + error.message);
        document.getElementById('similar-list').innerHTML = `
            <div class="alert alert-danger">
                <i class="fas fa-exclamation-circle me-2"></i>
                Failed to load similar articles. Please try again.
            </div>
        `;
    }
}

function formatContribution(value) {
    if (typeof value !== 'number') return 'n/a';
    return value.toFixed(3);
}

function displayStats(stats) {
    const statsContainer = document.getElementById('article-stats');

    const freshnessData = {
        labels: ['Today', 'This Week', 'This Month', 'Older'],
        datasets: [{
            data: [
                stats.freshness_distribution.today,
                stats.freshness_distribution.this_week,
                stats.freshness_distribution.this_month,
                stats.freshness_distribution.older
            ],
            backgroundColor: ['#28a745', '#17a2b8', '#ffc107', '#6c757d']
        }]
    };

    const clusterData = {
        labels: Object.keys(stats.cluster_distribution).map(cluster => `Cluster ${cluster}`),
        datasets: [{
            data: Object.values(stats.cluster_distribution),
            backgroundColor: ['#007bff', '#6610f2', '#6f42c1', '#e83e8c', '#fd7e14']
        }]
    };

    statsContainer.innerHTML = `
        <div class="row">
            <div class="col-md-6">
                <h5 class="mb-3">Content Freshness</h5>
                <canvas id="freshnessChart"></canvas>
            </div>
            <div class="col-md-6">
                <h5 class="mb-3">Topic Clusters</h5>
                <canvas id="clusterChart"></canvas>
            </div>
        </div>
    `;

    new Chart(document.getElementById('freshnessChart'), {
        type: 'pie',
        data: freshnessData,
        options: { responsive: true, plugins: { legend: { position: 'bottom' } } }
    });

    new Chart(document.getElementById('clusterChart'), {
        type: 'pie',
        data: clusterData,
        options: { responsive: true, plugins: { legend: { position: 'bottom' } } }
    });
}

function setupEventListeners() {
    document.getElementById('article-list').addEventListener('click', (e) => {
        e.preventDefault();
        const articleItem = e.target.closest('.list-group-item');
        if (articleItem) {
            const articleId = articleItem.dataset.id;
            const article = articles.find(a => a.article_id === articleId);
            if (article) {
                document.querySelectorAll('.list-group-item').forEach(item => item.classList.remove('active'));
                articleItem.classList.add('active');
                displayArticle(article);
            }
        }
    });

    document.getElementById('show-similar').addEventListener('click', showSimilarArticles);
    document.getElementById('refresh-decision-context').addEventListener('click', loadDecisionContext);
    document.getElementById('ranking-config').addEventListener('change', loadDecisionContext);
    document.getElementById('scenario-select').addEventListener('change', (event) => {
        const selected = scenarios.find(item => item.scenario_id === event.target.value);
        applyScenarioToEditor(selected || null);
        loadDecisionContext();
    });
    document.getElementById('external-user-id').addEventListener('change', loadDecisionContext);
    document.getElementById('source-filters').addEventListener('change', (event) => {
        if (event.target.classList.contains('source-filter')) {
            loadDecisionContext();
        }
    });
    document.getElementById('save-source-settings').addEventListener('click', saveSourceSettings);
    document.getElementById('create-connector').addEventListener('click', async () => {
        try {
            await createConnector();
        } catch (error) {
            showError(error.message || 'Failed to create connector');
        }
    });
    document.getElementById('connector-search').addEventListener('input', (event) => {
        connectorSearchTerm = (event.target.value || '').trim().toLowerCase();
        renderConnectors();
    });
    document.getElementById('connector-status-filter').addEventListener('change', (event) => {
        connectorStatusFilter = event.target.value || 'all';
        renderConnectors();
    });
    document.getElementById('sync-due-connectors').addEventListener('click', syncDueConnectors);
    document.getElementById('run-scheduler-now').addEventListener('click', runSchedulerNow);
    document.getElementById('connector-list').addEventListener('click', handleConnectorAction);
    document.getElementById('save-scenario').addEventListener('click', async () => {
        try {
            await saveScenario();
            await loadScenarioMetrics();
        } catch (error) {
            showError(error.message || 'Failed to save scenario');
        }
    });
    document.getElementById('delete-scenario').addEventListener('click', async () => {
        try {
            await deleteScenario();
            await loadScenarioMetrics();
        } catch (error) {
            showError(error.message || 'Failed to delete scenario');
        }
    });
    document.getElementById('refresh-scenarios').addEventListener('click', loadScenarios);
    document.getElementById('refresh-scenario-metrics').addEventListener('click', loadScenarioMetrics);
}

function formatDate(dateString) {
    if (!dateString) return 'No date';
    try {
        const date = new Date(dateString);
        return date.toLocaleDateString('en-US', {
            year: 'numeric',
            month: 'short',
            day: 'numeric'
        });
    } catch (_e) {
        return 'Invalid date';
    }
}

function showError(message) {
    const toast = document.createElement('div');
    toast.className = 'toast show position-fixed bottom-0 end-0 m-3';
    toast.style.zIndex = '1050';
    toast.innerHTML = `
        <div class="toast-header bg-danger text-white">
            <i class="fas fa-exclamation-circle me-2"></i>
            <strong class="me-auto">Error</strong>
            <button type="button" class="btn-close btn-close-white" data-bs-dismiss="toast"></button>
        </div>
        <div class="toast-body">${message}</div>
    `;

    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 5000);
}
