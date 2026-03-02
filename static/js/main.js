// Global state
let currentArticle = null;
let articles = [];
let sourceOptions = [];
let rankingConfigs = {};
let scenarios = [];
let connectors = [];
let alertThresholds = {};
const connectorRunsCache = {};
const connectorMetricsById = {};
let connectorSearchTerm = '';
let connectorStatusFilter = 'all';
let reportingVolumeChart = null;
let reportingCtrChart = null;
let reportingScenarioOverlayChart = null;
let reportingFunnelChart = null;
let reportingLastPayload = null;
let reportingLastAttribution = null;
let reportingLastIdentity = null;
let reportingLastScenarioTraces = null;
let reportingLastIdentityDiagnostics = null;
let reportingLastExperiments = null;
let reportingLastExperimentComparison = null;
let reportingQualitySnapshots = [];
let reportingLastQualityCompare = null;
let cdpIntegration = null;
let recommendationRuns = [];

function hasElement(id) {
    return Boolean(document.getElementById(id));
}

// Initialize the application
document.addEventListener('DOMContentLoaded', () => {
    if (hasElement('article-list')) loadArticles();
    if (hasElement('article-stats')) loadStats();
    if (hasElement('source-filters') || hasElement('reporting-source-filter')) loadSources();
    if (hasElement('ranking-config')) loadRankingConfigs();
    if (hasElement('scenario-select') || hasElement('reporting-scenario-filter') || hasElement('scenario-id')) loadScenarios();
    if (hasElement('offline-metrics')) loadOfflineMetrics();
    if (hasElement('scenario-metrics')) loadScenarioMetrics();
    if (hasElement('scenario-source-metrics')) loadScenarioSourceMetrics();
    if (hasElement('threshold-p95-ms')) loadAlertThresholds();
    if (hasElement('sli-overview')) loadSliOverview();
    if (hasElement('alert-incidents')) loadAlertIncidents();
    if (hasElement('cleanup-status')) loadCleanupStatus();
    if (hasElement('rollups-status')) loadRollupsStatus();
    if (hasElement('engine-config-snapshot')) loadEngineConfigSnapshot();
    if (hasElement('audit-logs-list')) loadAuditLogs();
    if (hasElement('run-list')) loadRecommendationRuns();
    if (hasElement('connector-list')) {
        loadConnectors();
        loadConnectorMetrics();
    }
    if (hasElement('scheduler-status')) {
        loadSchedulerStatus();
        setInterval(loadSchedulerStatus, 15000);
    }
    if (hasElement('cdp-base-url')) {
        loadCdpConfig();
        loadCdpProfiles();
        loadCdpSchedulerStatus();
        loadCdpDiagnostics();
    }
    if (hasElement('decision-context')) loadDecisionContext();
    if (hasElement('reporting-summary')) {
        loadReportingWorkspace();
        loadQualitySnapshotHistory();
    }
    setupEventListeners();
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
        renderReportingSourceFilterOptions();
        if (hasElement('decision-context')) loadDecisionContext();
        if (hasElement('reporting-summary')) loadReportingWorkspace();
    } catch (error) {
        console.error('Error loading sources:', error);
        const sourceFilters = document.getElementById('source-filters');
        if (sourceFilters) sourceFilters.innerHTML = `<span>Failed to load sources</span>`;
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
                <div class="text-muted small">
                    Health: ${metric.health_state || 'unknown'}
                    ${metric.last_error_code ? ` | Last error: ${metric.last_error_code}` : ''}
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
    if (!sourceFilters) return;
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

function renderReportingSourceFilterOptions() {
    const select = document.getElementById('reporting-source-filter');
    if (!select) return;
    const previous = select.value;
    const options = ['<option value="">All sources</option>']
        .concat(sourceOptions.map(item => `<option value="${item.source}">${item.source} (${item.article_count})</option>`));
    select.innerHTML = options.join('');
    if (previous && sourceOptions.some(item => item.source === previous)) {
        select.value = previous;
    }
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
        renderRuleBuilderConfigOptions();
        populateRankingConfigEditor(select.value);
        loadDecisionContext();
    } catch (error) {
        console.error('Error loading ranking configs:', error);
        document.getElementById('ranking-config').innerHTML = '<option value="balanced">balanced</option>';
        rankingConfigs = {};
        renderRuleBuilderConfigOptions();
        populateRankingConfigEditor('balanced');
    }
}

function renderRuleBuilderConfigOptions() {
    const select = document.getElementById('rule-ranking-config-id');
    if (!select) return;
    const options = ['<option value="">None</option>'];
    Object.keys(rankingConfigs).forEach(id => {
        options.push(`<option value="${id}">${id}</option>`);
    });
    select.innerHTML = options.join('');
}

function populateRankingConfigEditor(configId) {
    const record = rankingConfigs[configId];
    const config = record?.config || {};
    const weights = config.weights || {};
    document.getElementById('ranking-config-id').value = configId || '';
    document.getElementById('weight-semantic').value = Number(weights.semantic ?? 0.5);
    document.getElementById('weight-freshness').value = Number(weights.freshness ?? 0.3);
    document.getElementById('weight-topic').value = Number(weights.topic ?? 0.2);
    document.getElementById('weight-source').value = Number(weights.source ?? 0.1);
    document.getElementById('ranking-time-decay-days').value = Number(config.time_decay_days ?? 30);
    document.getElementById('ranking-source-weights-json').value = JSON.stringify(config.source_weights || {}, null, 2);
    if (record) {
        const systemLabel = record.is_system ? 'system' : 'custom';
        setRankingConfigStatus(`Editing ${systemLabel} config ${configId} (v${record.version}).`);
    } else {
        setRankingConfigStatus('Drafting a new custom ranking config.');
    }
}

function collectRankingConfigPayloadFromEditor() {
    const configId = (document.getElementById('ranking-config-id').value || '').trim();
    if (!configId) {
        throw new Error('Ranking config ID is required.');
    }
    const semantic = Number(document.getElementById('weight-semantic').value);
    const freshness = Number(document.getElementById('weight-freshness').value);
    const topic = Number(document.getElementById('weight-topic').value);
    const source = Number(document.getElementById('weight-source').value);
    const timeDecayDays = Number(document.getElementById('ranking-time-decay-days').value);
    const sourceWeights = parseJsonObjectInput(
        document.getElementById('ranking-source-weights-json').value,
        'Source weights'
    );

    const weights = { semantic, freshness, topic, source };
    Object.entries(weights).forEach(([name, value]) => {
        if (!Number.isFinite(value) || value < 0) {
            throw new Error(`Weight ${name} must be a number >= 0.`);
        }
    });
    if (!Number.isFinite(timeDecayDays) || timeDecayDays < 1) {
        throw new Error('Time decay days must be >= 1.');
    }
    return {
        configId,
        payload: {
            config_id: configId,
            weights,
            time_decay_days: Math.round(timeDecayDays),
            source_weights: sourceWeights
        }
    };
}

async function saveRankingConfig() {
    const { configId, payload } = collectRankingConfigPayloadFromEditor();
    const existing = rankingConfigs[configId];
    setRankingConfigStatus(existing ? `Updating ${configId}...` : `Creating ${configId}...`);
    const endpoint = existing ? `/api/ranking-configs/${encodeURIComponent(configId)}` : '/api/ranking-configs';
    const method = existing ? 'PUT' : 'POST';
    const response = await fetch(endpoint, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    });
    if (!response.ok) {
        const error = await response.json();
        throw new Error(error.error || 'Failed to save ranking config');
    }
    const result = await response.json();
    await loadRankingConfigs();
    document.getElementById('ranking-config').value = configId;
    populateRankingConfigEditor(configId);
    loadDecisionContext();
    setRankingConfigStatus(`Saved ${configId} (version ${result.version}).`);
}

async function deleteRankingConfig() {
    const configId = (document.getElementById('ranking-config-id').value || '').trim();
    if (!configId) {
        throw new Error('Ranking config ID is required.');
    }
    if (!window.confirm(`Delete ranking config "${configId}"?`)) {
        return;
    }
    const response = await fetch(`/api/ranking-configs/${encodeURIComponent(configId)}`, { method: 'DELETE' });
    if (!response.ok) {
        const error = await response.json();
        throw new Error(error.error || 'Failed to delete ranking config');
    }
    await loadRankingConfigs();
    const selected = document.getElementById('ranking-config').value || 'balanced';
    populateRankingConfigEditor(selected);
    setRankingConfigStatus(`Deleted config ${configId}.`);
}

function getSelectedScenarioId() {
    return document.getElementById('scenario-select')?.value || '';
}

function getExternalUserId() {
    const raw = document.getElementById('external-user-id')?.value || '';
    return raw.trim();
}

function getOperatorId() {
    const raw = document.getElementById('operator-id')?.value || '';
    return raw.trim();
}

function getOperatorHeaders() {
    const operatorId = getOperatorId();
    return operatorId ? { 'X-Actor-Id': operatorId } : {};
}

function parseCsvInput(value) {
    return String(value || '')
        .split(',')
        .map(item => item.trim())
        .filter(Boolean);
}

function formatCsv(values) {
    return (Array.isArray(values) ? values : []).join(', ');
}

function parseJsonObjectInput(raw, fieldLabel) {
    const text = String(raw || '').trim();
    if (!text) return {};
    let parsed = {};
    try {
        parsed = JSON.parse(text);
    } catch (_error) {
        throw new Error(`${fieldLabel} must be valid JSON`);
    }
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
        throw new Error(`${fieldLabel} must be a JSON object`);
    }
    return parsed;
}

function setRuleBuilderStatus(message, isError = false) {
    const el = document.getElementById('rule-builder-status');
    if (!el) return;
    el.className = `small ${isError ? 'text-danger' : 'text-muted'}`;
    el.textContent = message;
}

function setRankingConfigStatus(message, isError = false) {
    const el = document.getElementById('ranking-config-status');
    if (!el) return;
    el.className = `small mt-2 ${isError ? 'text-danger' : 'text-muted'}`;
    el.textContent = message;
}

function applyScenarioToEditor(scenario) {
    const scenarioId = document.getElementById('scenario-id');
    const scenarioName = document.getElementById('scenario-name');
    const scenarioDescription = document.getElementById('scenario-description');
    const scenarioEnabled = document.getElementById('scenario-enabled');
    const scenarioRuleSet = document.getElementById('scenario-rule-set');
    if (scenarioId) scenarioId.value = scenario?.scenario_id || '';
    if (scenarioName) scenarioName.value = scenario?.name || '';
    if (scenarioDescription) scenarioDescription.value = scenario?.description || '';
    if (scenarioEnabled) scenarioEnabled.checked = Boolean(scenario?.enabled ?? true);
    if (scenarioRuleSet) scenarioRuleSet.value = JSON.stringify(scenario?.rule_set || {}, null, 2);
    if (hasElement('rule-include-sources')) {
        populateRuleBuilderFromRuleSet(scenario?.rule_set || {});
    }
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
        if (select) {
            const current = select.value;
            select.innerHTML = '<option value="">No scenario</option>' + scenarios
                .map(item => `<option value="${item.scenario_id}">${item.name} (${item.scenario_id})${item.enabled ? '' : ' [disabled]'}</option>`)
                .join('');
            if (current && scenarios.some(item => item.scenario_id === current)) {
                select.value = current;
            }
            const selected = scenarios.find(item => item.scenario_id === select.value);
            applyScenarioToEditor(selected || null);
        }
        renderReportingScenarioOptions();
        loadDecisionContext();
        loadScenarioSourceMetrics();
    } catch (error) {
        console.error('Error loading scenarios:', error);
        showError(`Failed to load scenarios: ${error.message}`);
    }
}

async function saveScenario() {
    const scenarioId = (document.getElementById('scenario-id').value || '').trim();
    const name = (document.getElementById('scenario-name').value || '').trim();
    const description = (document.getElementById('scenario-description').value || '').trim();
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
        description,
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

function populateRuleBuilderFromRuleSet(ruleSet) {
    const rules = ruleSet || {};
    document.getElementById('rule-include-sources').value = formatCsv(rules.include_sources);
    document.getElementById('rule-exclude-sources').value = formatCsv(rules.exclude_sources);
    document.getElementById('rule-include-sections').value = formatCsv(rules.include_sections);
    document.getElementById('rule-exclude-sections').value = formatCsv(rules.exclude_sections);
    document.getElementById('rule-include-keywords').value = formatCsv(rules.include_keywords);
    document.getElementById('rule-exclude-keywords').value = formatCsv(rules.exclude_keywords);
    document.getElementById('rule-exclude-article-ids').value = formatCsv(rules.exclude_article_ids);
    document.getElementById('rule-max-age-days').value =
        rules.max_age_days === null || rules.max_age_days === undefined ? '' : Number(rules.max_age_days);
    document.getElementById('rule-min-score').value =
        rules.min_score === null || rules.min_score === undefined ? '' : Number(rules.min_score);
    document.getElementById('rule-ranking-config-id').value = rules.ranking_config_id || '';
    document.getElementById('rule-source-boosts-json').value = JSON.stringify(rules.source_boosts || {}, null, 2);
}

function collectRuleBuilderRuleSet() {
    const maxAgeRaw = document.getElementById('rule-max-age-days').value;
    const minScoreRaw = document.getElementById('rule-min-score').value;
    const sourceBoosts = parseJsonObjectInput(
        document.getElementById('rule-source-boosts-json').value,
        'Rule source boosts'
    );
    Object.entries(sourceBoosts).forEach(([source, value]) => {
        const parsed = Number(value);
        if (!Number.isFinite(parsed) || parsed <= 0) {
            throw new Error(`Rule source boost for "${source}" must be > 0.`);
        }
        sourceBoosts[source] = parsed;
    });
    const maxAgeDays = maxAgeRaw === '' ? null : Number(maxAgeRaw);
    if (maxAgeDays !== null && (!Number.isFinite(maxAgeDays) || maxAgeDays < 0)) {
        throw new Error('Rule max age days must be >= 0.');
    }
    const minScore = minScoreRaw === '' ? null : Number(minScoreRaw);
    if (minScore !== null && (!Number.isFinite(minScore) || minScore < 0)) {
        throw new Error('Rule min score must be >= 0.');
    }
    return {
        include_sources: parseCsvInput(document.getElementById('rule-include-sources').value),
        exclude_sources: parseCsvInput(document.getElementById('rule-exclude-sources').value),
        include_sections: parseCsvInput(document.getElementById('rule-include-sections').value).map(v => v.toLowerCase()),
        exclude_sections: parseCsvInput(document.getElementById('rule-exclude-sections').value).map(v => v.toLowerCase()),
        include_keywords: parseCsvInput(document.getElementById('rule-include-keywords').value).map(v => v.toLowerCase()),
        exclude_keywords: parseCsvInput(document.getElementById('rule-exclude-keywords').value).map(v => v.toLowerCase()),
        exclude_article_ids: parseCsvInput(document.getElementById('rule-exclude-article-ids').value),
        max_age_days: maxAgeDays === null ? null : Math.round(maxAgeDays),
        min_score: minScore,
        source_boosts: sourceBoosts,
        ranking_config_id: (document.getElementById('rule-ranking-config-id').value || '').trim() || null
    };
}

function applyRuleBuilderToJson() {
    const ruleSet = collectRuleBuilderRuleSet();
    document.getElementById('scenario-rule-set').value = JSON.stringify(ruleSet, null, 2);
    setRuleBuilderStatus('Rule builder applied to JSON.');
}

function loadRuleBuilderFromJson() {
    const raw = document.getElementById('scenario-rule-set').value || '{}';
    let parsed = {};
    try {
        parsed = JSON.parse(raw);
    } catch (_error) {
        throw new Error('Scenario rule set JSON is invalid.');
    }
    populateRuleBuilderFromRuleSet(parsed);
    setRuleBuilderStatus('Rule builder loaded from JSON.');
}

async function simulateSelectedScenario() {
    const scenarioId = (document.getElementById('scenario-id').value || '').trim();
    if (!scenarioId) {
        throw new Error('Scenario ID is required to run simulation.');
    }
    const output = document.getElementById('scenario-simulation');
    output.textContent = 'Running simulation...';
    const response = await fetch(`/api/scenarios/${encodeURIComponent(scenarioId)}/simulate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            user_id: 'demo_user',
            top_n: 10,
            sources: getSelectedSources()
        })
    });
    if (!response.ok) {
        const error = await response.json();
        throw new Error(error.error || 'Scenario simulation failed');
    }
    const payload = await response.json();
    const trace = payload.scenario_trace || {};
    output.innerHTML = `
        <div><strong>Base:</strong> ${payload.base_count} | <strong>After scenario:</strong> ${payload.scenario_count}</div>
        <div><strong>Filtered out:</strong> ${trace.filtered_out ?? 0}</div>
        <div><strong>Reasons:</strong> <code>${JSON.stringify(trace.reasons || {})}</code></div>
    `;
}

async function loadScenarioSourceMetrics() {
    const container = document.getElementById('scenario-source-metrics');
    if (!container) return;
    const reportingSelection = getSelectedReportingScenarioIds();
    const scenarioId = getSelectedScenarioId()
        || (document.getElementById('scenario-id')?.value || '').trim()
        || (reportingSelection[0] || '');
    if (!scenarioId) {
        container.textContent = 'Select a scenario to view source KPI breakdown.';
        return;
    }
    try {
        const response = await fetch(`/api/metrics/scenarios/${encodeURIComponent(scenarioId)}/sources?days=30`);
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Failed to load scenario source metrics');
        }
        const payload = await response.json();
        const rows = (payload.sources || []).map(item => `
            <tr>
                <td>${item.source}</td>
                <td>${item.impressions}</td>
                <td>${item.clicks}</td>
                <td>${(Number(item.ctr || 0) * 100).toFixed(2)}%</td>
                <td>${item.conversions}</td>
            </tr>
        `).join('');
        container.innerHTML = `
            <div class="table-responsive">
                <table class="table table-sm mb-0">
                    <thead><tr><th>Source</th><th>Impr.</th><th>Clicks</th><th>CTR</th><th>Conv.</th></tr></thead>
                    <tbody>${rows || '<tr><td colspan="5" class="text-muted">No source metrics yet.</td></tr>'}</tbody>
                </table>
            </div>
        `;
    } catch (error) {
        console.error('Error loading scenario source metrics:', error);
        container.textContent = `Scenario source metrics unavailable: ${error.message}`;
    }
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

async function loadAlertThresholds() {
    try {
        const response = await fetch('/api/alerts/thresholds');
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Failed to load alert thresholds');
        }
        const payload = await response.json();
        alertThresholds = payload.thresholds || {};
        document.getElementById('threshold-p95-ms').value = Number(alertThresholds.recommendation_p95_ms ?? 500);
        document.getElementById('threshold-failure-rate').value = Number(alertThresholds.connector_failure_rate ?? 0.05);
        document.getElementById('threshold-blocker-rate').value = Number(alertThresholds.connector_blocker_rate ?? 0.2);
        document.getElementById('threshold-rollup-lag-hours').value = Number(alertThresholds.max_rollup_lag_hours ?? 24);
        document.getElementById('threshold-min-ctr').value = Number(alertThresholds.min_ctr ?? 0.01);
    } catch (error) {
        console.error('Error loading alert thresholds:', error);
        document.getElementById('alert-thresholds-status').textContent = `Threshold load failed: ${error.message}`;
    }
}

async function saveAlertThresholds() {
    const recommendationP95 = Number(document.getElementById('threshold-p95-ms').value);
    const connectorFailureRate = Number(document.getElementById('threshold-failure-rate').value);
    const connectorBlockerRate = Number(document.getElementById('threshold-blocker-rate').value);
    const maxRollupLagHours = Number(document.getElementById('threshold-rollup-lag-hours').value);
    const minCtr = Number(document.getElementById('threshold-min-ctr').value);
    const statusEl = document.getElementById('alert-thresholds-status');
    statusEl.textContent = 'Saving thresholds...';
    const response = await fetch('/api/alerts/thresholds', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', ...getOperatorHeaders() },
        body: JSON.stringify({
            thresholds: {
                recommendation_p95_ms: recommendationP95,
                connector_failure_rate: connectorFailureRate,
                connector_blocker_rate: connectorBlockerRate,
                max_rollup_lag_hours: maxRollupLagHours,
                min_ctr: minCtr
            }
        })
    });
    if (!response.ok) {
        const error = await response.json();
        throw new Error(error.error || 'Failed to save thresholds');
    }
    const payload = await response.json();
    alertThresholds = payload.thresholds || {};
    statusEl.textContent = 'Thresholds updated.';
}

function renderSliOverview(payload) {
    const container = document.getElementById('sli-overview');
    if (!container) return;
    const checks = payload.checks || [];
    const rows = checks.map(check => {
        const metric = check.metric;
        const value = check.value === null || check.value === undefined ? 'n/a' : Number(check.value).toFixed(4);
        const target = check.target_max !== undefined
            ? `<= ${Number(check.target_max).toFixed(4)}`
            : `>= ${Number(check.target_min ?? 0).toFixed(4)}`;
        const statusClass = check.status === 'pass' ? 'text-success' : 'text-danger';
        return `<tr><td>${metric}</td><td>${value}</td><td>${target}</td><td class="${statusClass}">${check.status}</td></tr>`;
    }).join('');
    container.innerHTML = `
        <div><strong>Overall:</strong> <span class="${payload.overall_status === 'pass' ? 'text-success' : 'text-danger'}">${payload.overall_status}</span></div>
        <div><strong>Window:</strong> ${payload.window_days} days</div>
        <div class="table-responsive mt-2">
            <table class="table table-sm mb-0">
                <thead><tr><th>Metric</th><th>Value</th><th>Target</th><th>Status</th></tr></thead>
                <tbody>${rows || '<tr><td colspan="4" class="text-muted">No checks available.</td></tr>'}</tbody>
            </table>
        </div>
    `;
}

async function loadSliOverview() {
    try {
        const persist = document.getElementById('persist-incidents-on-sli')?.checked;
        const suffix = persist ? '&persist_incidents=true' : '';
        const response = await fetch(`/api/observability/sli?days=30${suffix}`);
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Failed to load SLI');
        }
        const payload = await response.json();
        renderSliOverview(payload);
        if (persist) {
            await loadAlertIncidents();
        }
    } catch (error) {
        console.error('Error loading SLI:', error);
        document.getElementById('sli-overview').textContent = `SLI unavailable: ${error.message}`;
    }
}

function renderAlertIncidents(payload) {
    const container = document.getElementById('alert-incidents');
    const incidents = payload.incidents || [];
    if (!incidents.length) {
        container.innerHTML = '<span>No incidents found.</span>';
        return;
    }
    container.innerHTML = incidents.map(incident => `
        <div class="border rounded p-2 mb-2">
            <div class="d-flex justify-content-between align-items-center">
                <strong>${incident.metric}</strong>
                <span class="${incident.status === 'open' ? 'text-danger' : 'text-success'}">${incident.status}</span>
            </div>
            <div class="small text-muted">Current: ${incident.current_value ?? 'n/a'} | Threshold: ${incident.threshold_value ?? 'n/a'}</div>
            <div class="small text-muted">Occurrences: ${incident.occurrences} | Last seen: ${incident.last_seen_at}</div>
            ${incident.status === 'open' ? `<button class="btn btn-sm btn-outline-success mt-1 resolve-incident" data-id="${incident.incident_id}">Resolve</button>` : ''}
        </div>
    `).join('');
}

async function loadAlertIncidents() {
    try {
        const status = document.getElementById('incident-status-filter')?.value || '';
        const metric = (document.getElementById('incident-metric-filter')?.value || '').trim();
        const params = new URLSearchParams({ limit: '20' });
        if (status) params.set('status', status);
        if (metric) params.set('metric', metric);
        const response = await fetch(`/api/alerts/incidents?${params.toString()}`);
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Failed to load incidents');
        }
        const payload = await response.json();
        renderAlertIncidents(payload);
    } catch (error) {
        console.error('Error loading alert incidents:', error);
        document.getElementById('alert-incidents').textContent = `Incidents unavailable: ${error.message}`;
    }
}

async function evaluateAlertIncidents() {
    const statusEl = document.getElementById('alert-thresholds-status');
    statusEl.textContent = 'Evaluating incidents...';
    const response = await fetch('/api/alerts/incidents/evaluate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...getOperatorHeaders() },
        body: JSON.stringify({ days: 30, actor_id: getOperatorId() || undefined })
    });
    if (!response.ok) {
        const error = await response.json();
        throw new Error(error.error || 'Failed to evaluate incidents');
    }
    const payload = await response.json();
    statusEl.textContent = `Incidents evaluated. Opened/updated: ${payload.incident_sync?.opened_or_updated ?? 0}, resolved: ${payload.incident_sync?.resolved ?? 0}.`;
    await loadAlertIncidents();
    await loadSliOverview();
}

async function resolveIncident(incidentId) {
    const response = await fetch(`/api/alerts/incidents/${encodeURIComponent(incidentId)}/resolve`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', ...getOperatorHeaders() },
        body: JSON.stringify({
            actor_id: getOperatorId() || undefined,
            note: 'Resolved from UI'
        })
    });
    if (!response.ok) {
        const error = await response.json();
        throw new Error(error.error || 'Failed to resolve incident');
    }
    await loadAlertIncidents();
    await loadSliOverview();
}

async function loadCleanupStatus() {
    const container = document.getElementById('cleanup-status');
    if (!container) return;
    try {
        const response = await fetch('/api/maintenance/cleanup/status');
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Failed to load cleanup status');
        }
        const payload = await response.json();
        container.innerHTML = `
            <div><strong>Enabled:</strong> ${payload.enabled ? 'yes' : 'no'}</div>
            <div><strong>Running:</strong> ${payload.running ? 'yes' : 'no'}</div>
            <div><strong>Runs:</strong> ${payload.runs_total ?? 0}</div>
            <div><strong>Errors:</strong> ${payload.errors_total ?? 0}</div>
            <div><strong>Last run:</strong> ${payload.last_run_at || 'n/a'}</div>
        `;
    } catch (error) {
        console.error('Error loading cleanup status:', error);
        container.textContent = `Cleanup status unavailable: ${error.message}`;
    }
}

async function loadCdpConfig() {
    const statusEl = document.getElementById('cdp-config-status');
    try {
        const response = await fetch('/api/cdp/meiro');
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Failed to load CDP config');
        }
        const payload = await response.json();
        cdpIntegration = payload;
        document.getElementById('cdp-enabled').checked = Boolean(payload.enabled);
        document.getElementById('cdp-base-url').value = payload.config?.base_url || '';
        document.getElementById('cdp-request-url-template').value = payload.config?.request_url_template || '';
        document.getElementById('cdp-profile-endpoint-template').value = payload.config?.profile_endpoint_template || '/profiles/{external_user_id}';
        document.getElementById('cdp-api-key').value = payload.config?.api_key || '';
        document.getElementById('cdp-timeout-seconds').value = Number(payload.config?.timeout_seconds ?? 5);
        document.getElementById('cdp-request-retries').value = Number(payload.config?.request_retries ?? 2);
        document.getElementById('cdp-external-id-path').value = payload.mapping?.external_id_path || 'customer_entity_id';
        document.getElementById('cdp-traits-path').value = payload.mapping?.traits_path || 'returned_attributes';
        document.getElementById('cdp-segments-path').value = payload.mapping?.segments_path || '';
        document.getElementById('cdp-fixed-segments').value = (payload.mapping?.fixed_segments || []).join(', ');
        document.getElementById('cdp-preferred-sources-trait').value = payload.mapping?.preferred_sources_trait || 'preferred_sources';
        document.getElementById('cdp-excluded-sources-trait').value = payload.mapping?.excluded_sources_trait || 'excluded_sources';
        document.getElementById('cdp-source-weights-trait').value = payload.mapping?.source_weights_trait || 'source_weights';
        document.getElementById('cdp-source-weight-prefix').value = payload.mapping?.source_weight_trait_prefix || 'source_weight_';
        document.getElementById('cdp-scenario-segment-map').value = JSON.stringify(payload.mapping?.scenario_segment_map || {}, null, 2);
        document.getElementById('cdp-config-segment-map').value = JSON.stringify(payload.mapping?.config_segment_map || {}, null, 2);
        document.getElementById('cdp-segment-priority').value = (payload.mapping?.segment_priority || []).join(', ');
        if (statusEl) statusEl.textContent = `Loaded. Updated at ${payload.updated_at || 'n/a'}.`;
    } catch (error) {
        if (statusEl) statusEl.textContent = `CDP config unavailable: ${error.message}`;
    }
}

async function saveCdpConfig() {
    const statusEl = document.getElementById('cdp-config-status');
    let scenarioMap = {};
    let configMap = {};
    try {
        scenarioMap = JSON.parse(document.getElementById('cdp-scenario-segment-map').value || '{}');
        configMap = JSON.parse(document.getElementById('cdp-config-segment-map').value || '{}');
    } catch (error) {
        throw new Error('Invalid JSON in mapping fields');
    }
    const payload = {
        enabled: document.getElementById('cdp-enabled').checked,
        config: {
            base_url: (document.getElementById('cdp-base-url').value || '').trim(),
            request_url_template: (document.getElementById('cdp-request-url-template').value || '').trim(),
            profile_endpoint_template: (document.getElementById('cdp-profile-endpoint-template').value || '').trim(),
            api_key: (document.getElementById('cdp-api-key').value || '').trim(),
            timeout_seconds: Number(document.getElementById('cdp-timeout-seconds').value || 5),
            request_retries: Number(document.getElementById('cdp-request-retries').value || 2)
        },
        mapping: {
            external_id_path: (document.getElementById('cdp-external-id-path').value || '').trim(),
            traits_path: (document.getElementById('cdp-traits-path').value || '').trim(),
            segments_path: (document.getElementById('cdp-segments-path').value || '').trim(),
            fixed_segments: (document.getElementById('cdp-fixed-segments').value || '').split(',').map(item => item.trim()).filter(Boolean),
            preferred_sources_trait: (document.getElementById('cdp-preferred-sources-trait').value || '').trim(),
            excluded_sources_trait: (document.getElementById('cdp-excluded-sources-trait').value || '').trim(),
            source_weights_trait: (document.getElementById('cdp-source-weights-trait').value || '').trim(),
            source_weight_trait_prefix: (document.getElementById('cdp-source-weight-prefix').value || '').trim(),
            scenario_segment_map: scenarioMap,
            config_segment_map: configMap,
            segment_priority: (document.getElementById('cdp-segment-priority').value || '').split(',').map(item => item.trim()).filter(Boolean)
        },
        actor_id: getOperatorId() || undefined
    };
    if (statusEl) statusEl.textContent = 'Saving CDP config...';
    const response = await fetch('/api/cdp/meiro', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', ...getOperatorHeaders() },
        body: JSON.stringify(payload)
    });
    if (!response.ok) {
        const error = await response.json();
        throw new Error(error.error || 'Failed to save CDP config');
    }
    const saved = await response.json();
    cdpIntegration = saved;
    if (statusEl) statusEl.textContent = 'CDP config saved.';
}

async function loadCdpProfiles() {
    const table = document.getElementById('cdp-profiles-table');
    if (!table) return;
    try {
        const response = await fetch('/api/cdp/meiro/profiles?limit=50');
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Failed to load CDP profiles');
        }
        const payload = await response.json();
        const rows = (payload.profiles || []).map(item => `
            <tr>
                <td><code>${item.external_user_id}</code></td>
                <td class="small">${(item.segments || []).join(', ') || 'n/a'}</td>
                <td class="small">${Object.keys(item.traits || {}).slice(0, 6).join(', ') || 'n/a'}</td>
                <td>${item.synced_at || 'n/a'}</td>
            </tr>
        `).join('');
        table.innerHTML = rows || '<tr><td colspan="4" class="text-muted">No CDP profiles ingested yet.</td></tr>';
    } catch (error) {
        table.innerHTML = `<tr><td colspan="4" class="text-danger">CDP profiles unavailable: ${error.message}</td></tr>`;
    }
}

async function syncCdpProfiles() {
    const statusEl = document.getElementById('cdp-sync-status');
    const raw = document.getElementById('cdp-sync-external-ids').value || '';
    const externalIds = raw.split(',').map(item => item.trim()).filter(Boolean);
    if (!externalIds.length) {
        throw new Error('Enter at least one external ID');
    }
    if (statusEl) statusEl.textContent = 'Sync in progress...';
    const response = await fetch('/api/cdp/meiro/sync', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...getOperatorHeaders() },
        body: JSON.stringify({ external_user_ids: externalIds, actor_id: getOperatorId() || undefined })
    });
    if (!response.ok) {
        const error = await response.json();
        throw new Error(error.error || 'Failed to sync profiles');
    }
    const payload = await response.json();
    if (statusEl) statusEl.textContent = `Sync finished. Synced: ${payload.synced_count || 0}, errors: ${payload.error_count || 0}.`;
    await loadCdpProfiles();
    await loadCdpDiagnostics();
}

async function loadCdpSchedulerStatus() {
    const container = document.getElementById('cdp-scheduler-status');
    if (!container) return;
    try {
        const response = await fetch('/api/cdp/meiro/scheduler/status');
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Failed to load scheduler status');
        }
        const payload = await response.json();
        container.innerHTML = `
            <div><strong>Enabled:</strong> ${payload.enabled ? 'yes' : 'no'}</div>
            <div><strong>Running:</strong> ${payload.running ? 'yes' : 'no'}</div>
            <div><strong>Runs total:</strong> ${payload.runs_total || 0}</div>
            <div><strong>Errors total:</strong> ${payload.errors_total || 0}</div>
            <div><strong>Last run:</strong> ${payload.last_run_at || 'n/a'}</div>
            <div><strong>Last result:</strong> ${payload.last_result ? JSON.stringify(payload.last_result) : 'n/a'}</div>
        `;
    } catch (error) {
        container.textContent = `Scheduler status unavailable: ${error.message}`;
    }
}

async function runCdpSchedulerNow() {
    const statusEl = document.getElementById('cdp-scheduler-status');
    if (statusEl) statusEl.textContent = 'Running CDP sync now...';
    const response = await fetch('/api/cdp/meiro/scheduler/run-now', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...getOperatorHeaders() },
        body: JSON.stringify({ actor_id: getOperatorId() || undefined })
    });
    if (!response.ok) {
        const error = await response.json();
        throw new Error(error.error || 'Failed to run scheduler now');
    }
    await loadCdpSchedulerStatus();
    await loadCdpDiagnostics();
    await loadCdpProfiles();
}

async function loadCdpDiagnostics() {
    const summary = document.getElementById('cdp-diagnostics-summary');
    const table = document.getElementById('cdp-sync-runs-table');
    if (!summary || !table) return;
    try {
        const response = await fetch('/api/cdp/meiro/diagnostics?freshness_hours=24');
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Failed to load diagnostics');
        }
        const payload = await response.json();
        const p = payload.profiles || {};
        const m = payload.mapping_coverage || {};
        const s = payload.sync_runs || {};
        summary.innerHTML = `
            <strong>Profiles:</strong> ${p.count || 0} (fresh ${(Number(p.fresh_ratio || 0) * 100).toFixed(1)}%, stale ${(Number(p.stale_ratio || 0) * 100).toFixed(1)}%)
            | <strong>Mapping hit:</strong> ${(Number(m.profile_found_ratio || 0) * 100).toFixed(1)}%
            | <strong>Applied:</strong> ${(Number(m.applied_ratio || 0) * 100).toFixed(1)}%
            | <strong>Sync success:</strong> ${(Number(s.success_ratio || 0) * 100).toFixed(1)}%
        `;
        const rows = (s.recent || []).map(item => `
            <tr>
                <td><code>${(item.run_id || '').slice(0, 8)}</code></td>
                <td>${item.status || 'n/a'}</td>
                <td>${item.attempted || 0}</td>
                <td>${item.synced || 0}</td>
                <td>${item.error_count || 0}</td>
            </tr>
        `).join('');
        table.innerHTML = rows || '<tr><td colspan="5" class="text-muted">No sync runs yet.</td></tr>';
    } catch (error) {
        summary.textContent = `CDP diagnostics unavailable: ${error.message}`;
        table.innerHTML = '<tr><td colspan="5" class="text-danger">Failed to load diagnostics.</td></tr>';
    }
}

async function deriveCdpProfile(persist = false) {
    const externalId = (document.getElementById('cdp-derive-external-id')?.value || '').trim();
    if (!externalId) {
        throw new Error('Enter external user ID for derivation');
    }
    const output = document.getElementById('cdp-derivation-output');
    if (output) output.textContent = 'Deriving...';
    const response = await fetch(`/api/cdp/meiro/profiles/${encodeURIComponent(externalId)}/derive`, {
        method: persist ? 'POST' : 'GET',
        headers: persist ? { 'Content-Type': 'application/json', ...getOperatorHeaders() } : undefined,
        body: persist ? JSON.stringify({ persist: true, actor_id: getOperatorId() || undefined }) : undefined
    });
    if (!response.ok) {
        const error = await response.json();
        throw new Error(error.error || 'Failed to derive profile traits');
    }
    const payload = await response.json();
    if (output) output.textContent = JSON.stringify(payload, null, 2);
    if (persist) {
        await loadCdpProfiles();
        await loadCdpDiagnostics();
    }
}

async function runCleanupNow() {
    const container = document.getElementById('cleanup-status');
    container.textContent = 'Running cleanup...';
    const response = await fetch('/api/maintenance/cleanup/run-now', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...getOperatorHeaders() },
        body: JSON.stringify({ actor_id: getOperatorId() || undefined })
    });
    if (!response.ok) {
        const error = await response.json();
        throw new Error(error.error || 'Failed to run cleanup');
    }
    const payload = await response.json();
    container.innerHTML = `
        <div><strong>Cleanup done.</strong></div>
        <div>Removed idempotency: ${payload.cleanup?.removed_idempotency ?? 0}</div>
        <div>Removed audit events: ${payload.cleanup?.removed_audit_events ?? 0}</div>
    `;
}

async function loadRollupsStatus() {
    const container = document.getElementById('rollups-status');
    if (!container) return;
    try {
        const daysRaw = Number(document.getElementById('rollups-days')?.value || 30);
        const days = Number.isFinite(daysRaw) ? Math.max(1, Math.min(365, Math.round(daysRaw))) : 30;
        const response = await fetch(`/api/metrics/rollups/daily?days=${days}`);
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Failed to load rollups');
        }
        const payload = await response.json();
        const totals = (payload.rows || []).reduce((acc, row) => {
            acc.impressions += Number(row.impressions || 0);
            acc.clicks += Number(row.clicks || 0);
            acc.conversions += Number(row.conversions || 0);
            return acc;
        }, { impressions: 0, clicks: 0, conversions: 0 });
        container.innerHTML = `
            <div><strong>Rows:</strong> ${payload.count ?? 0}</div>
            <div><strong>Window:</strong> ${payload.window_days} days</div>
            <div><strong>Aggregated events:</strong> impressions ${totals.impressions}, clicks ${totals.clicks}, conversions ${totals.conversions}</div>
        `;
    } catch (error) {
        container.textContent = `Rollup status unavailable: ${error.message}`;
    }
}

async function rebuildRollups() {
    const container = document.getElementById('rollups-status');
    if (container) container.textContent = 'Rebuilding rollups...';
    const daysRaw = Number(document.getElementById('rollups-days')?.value || 30);
    const days = Number.isFinite(daysRaw) ? Math.max(1, Math.min(365, Math.round(daysRaw))) : 30;
    const response = await fetch('/api/metrics/rollups/rebuild', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...getOperatorHeaders() },
        body: JSON.stringify({ days, actor_id: getOperatorId() || undefined })
    });
    if (!response.ok) {
        const error = await response.json();
        throw new Error(error.error || 'Failed to rebuild rollups');
    }
    const payload = await response.json();
    if (container) {
        container.innerHTML = `
            <div><strong>Rebuild done.</strong></div>
            <div>Rows: ${payload.rows_upserted ?? 0}</div>
            <div>Window start day: ${payload.window_start_day || 'n/a'}</div>
            <div>Rebuilt at: ${payload.rebuilt_at || 'n/a'}</div>
        `;
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

async function loadEngineConfigSnapshot() {
    const container = document.getElementById('engine-config-snapshot');
    if (!container) return;
    try {
        const response = await fetch('/api/engine/config');
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Failed to load engine config');
        }
        const payload = await response.json();
        container.textContent = JSON.stringify(payload, null, 2);
    } catch (error) {
        container.textContent = `Failed to load engine snapshot: ${error.message}`;
    }
}

function renderAuditLogs(payload) {
    const container = document.getElementById('audit-logs-list');
    const events = payload.events || [];
    if (!events.length) {
        container.innerHTML = '<span>No audit events found.</span>';
        return;
    }
    container.innerHTML = events.map(event => `
        <div class="border rounded p-2 mb-2">
            <div class="d-flex justify-content-between">
                <strong>${event.action}</strong>
                <span class="text-muted">${event.created_at}</span>
            </div>
            <div class="small text-muted">${event.resource_type}:${event.resource_id} | actor: ${event.actor_id}</div>
            <div class="small"><code>${JSON.stringify(event.extra || {})}</code></div>
        </div>
    `).join('');
}

async function loadAuditLogs() {
    try {
        const actorId = (document.getElementById('audit-actor-filter')?.value || '').trim();
        const resourceType = (document.getElementById('audit-resource-filter')?.value || '').trim();
        const params = new URLSearchParams({ limit: '25', offset: '0' });
        if (actorId) params.set('actor_id', actorId);
        if (resourceType) params.set('resource_type', resourceType);
        const response = await fetch(`/api/audit-logs?${params.toString()}`);
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Failed to load audit logs');
        }
        const payload = await response.json();
        renderAuditLogs(payload);
    } catch (error) {
        document.getElementById('audit-logs-list').textContent = `Audit logs unavailable: ${error.message}`;
    }
}

function renderReportingScenarioOptions() {
    const select = document.getElementById('reporting-scenario-filter');
    if (!select) return;
    const previous = new Set(Array.from(select.selectedOptions).map(option => option.value));
    const options = ['<option value="default">default</option>']
        .concat(
            scenarios.map(item => `<option value="${item.scenario_id}">${item.name} (${item.scenario_id})</option>`)
        );
    select.innerHTML = options.join('');
    Array.from(select.options).forEach(option => {
        option.selected = previous.has(option.value);
    });
}

function getSelectedReportingScenarioIds() {
    const select = document.getElementById('reporting-scenario-filter');
    if (!select) return [];
    return Array.from(select.selectedOptions)
        .map(option => option.value)
        .filter(Boolean);
}

function toCsvCell(value) {
    const raw = String(value ?? '');
    if (raw.includes(',') || raw.includes('"') || raw.includes('\n')) {
        return `"${raw.replace(/"/g, '""')}"`;
    }
    return raw;
}

function renderReportingWorkspace(payload) {
    reportingLastPayload = payload;
    const summary = payload.summary || {};
    const summaryEl = document.getElementById('reporting-summary');
    const selectedCount = (payload.filters?.scenario_ids || []).length;
    const scopeLabel = selectedCount ? ` | filtered scenarios ${selectedCount}` : ' | all scenarios';
    summaryEl.innerHTML = `
        <strong>Totals (${payload.window_days} days):</strong>
        impressions ${summary.impressions ?? 0},
        clicks ${summary.clicks ?? 0},
        conversions ${summary.conversions ?? 0},
        CTR ${(Number(summary.ctr || 0) * 100).toFixed(2)}%
        ${scopeLabel}
    `;

    const tableBody = document.getElementById('reporting-scenario-table');
    const scenarioRows = (payload.scenarios || []).map(item => `
        <tr>
            <td>${item.name || item.scenario_id}</td>
            <td>${item.impressions}</td>
            <td>${item.clicks}</td>
            <td>${item.conversions}</td>
            <td>${(Number(item.ctr || 0) * 100).toFixed(2)}%</td>
        </tr>
    `).join('');
    tableBody.innerHTML = scenarioRows || '<tr><td colspan="5" class="text-muted">No scenario activity in selected window.</td></tr>';

    const labels = (payload.totals_by_day || []).map(item => item.date);
    const impressions = (payload.totals_by_day || []).map(item => item.impressions);
    const clicks = (payload.totals_by_day || []).map(item => item.clicks);
    const ctr = (payload.totals_by_day || []).map(item => Number(item.ctr || 0) * 100);

    const volumeCtx = document.getElementById('reporting-volume-chart');
    const ctrCtx = document.getElementById('reporting-ctr-chart');
    const overlayCtx = document.getElementById('reporting-scenario-overlay-chart');
    const funnelCtx = document.getElementById('reporting-funnel-chart');
    if (reportingVolumeChart) reportingVolumeChart.destroy();
    if (reportingCtrChart) reportingCtrChart.destroy();
    if (reportingScenarioOverlayChart) reportingScenarioOverlayChart.destroy();
    if (reportingFunnelChart) reportingFunnelChart.destroy();

    reportingVolumeChart = new Chart(volumeCtx, {
        type: 'bar',
        data: {
            labels,
            datasets: [
                { label: 'Impressions', data: impressions, backgroundColor: '#0d6efd' },
                { label: 'Clicks', data: clicks, backgroundColor: '#198754' }
            ]
        },
        options: { responsive: true, maintainAspectRatio: false }
    });
    reportingCtrChart = new Chart(ctrCtx, {
        type: 'line',
        data: {
            labels,
            datasets: [
                {
                    label: 'CTR %',
                    data: ctr,
                    borderColor: '#fd7e14',
                    backgroundColor: 'rgba(253,126,20,0.2)',
                    tension: 0.25,
                    fill: true
                }
            ]
        },
        options: { responsive: true, maintainAspectRatio: false }
    });

    const palette = ['#6f42c1', '#0dcaf0', '#d63384', '#198754', '#ffc107', '#20c997'];
    const overlayDatasets = (payload.scenarios || []).slice(0, 6).map((scenario, idx) => ({
        label: scenario.name || scenario.scenario_id,
        data: (scenario.points || []).map(point => Number(point.ctr || 0) * 100),
        borderColor: palette[idx % palette.length],
        backgroundColor: 'transparent',
        tension: 0.25
    }));
    reportingScenarioOverlayChart = new Chart(overlayCtx, {
        type: 'line',
        data: { labels, datasets: overlayDatasets },
        options: { responsive: true, maintainAspectRatio: false }
    });
    reportingFunnelChart = new Chart(funnelCtx, {
        type: 'bar',
        data: {
            labels: ['Impressions', 'Clicks', 'Conversions'],
            datasets: [{
                label: 'Funnel',
                data: [summary.impressions || 0, summary.clicks || 0, summary.conversions || 0],
                backgroundColor: ['#0d6efd', '#198754', '#fd7e14']
            }]
        },
        options: {
            indexAxis: 'y',
            responsive: true,
            maintainAspectRatio: false
        }
    });
}

function renderReportingAttribution(payload) {
    reportingLastAttribution = payload;
    const attributionTable = document.getElementById('reporting-attribution-table');
    if (attributionTable) {
        const runRows = (payload.by_run || []).map(item => `
            <tr>
                <td><code>${item.run_id === 'untracked' ? 'untracked' : item.run_id.slice(0, 8)}</code></td>
                <td>${item.config_id ? `${item.config_id} v${item.config_version}` : 'n/a'}</td>
                <td>${item.scenario_name || item.scenario_id || 'default'}</td>
                <td class="small">${(item.selected_sources || []).slice(0, 4).join(', ') || 'n/a'}</td>
                <td>${item.impressions || 0}</td>
                <td>${item.clicks || 0}</td>
                <td>${item.conversions || 0}</td>
                <td>${(Number(item.ctr || 0) * 100).toFixed(2)}%</td>
                <td>${(Number(item.conversion_rate || 0) * 100).toFixed(2)}%</td>
            </tr>
        `).join('');
        attributionTable.innerHTML = runRows || '<tr><td colspan="9" class="text-muted">No run attribution in selected window.</td></tr>';
    }

    const sourceTable = document.getElementById('reporting-source-table');
    if (sourceTable) {
        const sourceRows = (payload.by_source || []).map(item => `
            <tr>
                <td>${item.source || 'unknown'}</td>
                <td>${item.impressions || 0}</td>
                <td>${item.clicks || 0}</td>
                <td>${item.conversions || 0}</td>
                <td>${(Number(item.ctr || 0) * 100).toFixed(2)}%</td>
                <td>${(Number(item.conversion_rate || 0) * 100).toFixed(2)}%</td>
            </tr>
        `).join('');
        sourceTable.innerHTML = sourceRows || '<tr><td colspan="6" class="text-muted">No source attribution in selected window.</td></tr>';
    }
}

function renderIdentityMetrics(payload) {
    reportingLastIdentity = payload;
    const summary = payload.summary || {};
    const summaryEl = document.getElementById('reporting-identity-summary');
    if (summaryEl) {
        summaryEl.innerHTML = `
            <strong>Identity coverage:</strong>
            external events ${(Number(summary.external_event_share || 0) * 100).toFixed(2)}%,
            runs with external ID ${(Number(summary.run_external_share || 0) * 100).toFixed(2)}%
            | unique external users ${summary.unique_external_users ?? 0}
            | unique users ${summary.unique_users ?? 0}
        `;
    }
    const table = document.getElementById('reporting-identity-table');
    if (table) {
        const rows = (payload.top_external_users || []).map(item => `
            <tr>
                <td><code>${item.external_user_id}</code></td>
                <td>${item.events || 0}</td>
                <td>${item.impressions || 0}</td>
                <td>${item.clicks || 0}</td>
                <td>${item.conversions || 0}</td>
                <td>${(Number(item.ctr || 0) * 100).toFixed(2)}%</td>
                <td>${item.scenario_count || 0}</td>
            </tr>
        `).join('');
        table.innerHTML = rows || '<tr><td colspan="7" class="text-muted">No external ID events in selected window.</td></tr>';
    }
}

function renderIdentityDiagnostics(payload) {
    reportingLastIdentityDiagnostics = payload;
    const summary = payload.summary || {};
    const summaryEl = document.getElementById('reporting-identity-diagnostics-summary');
    if (summaryEl) {
        summaryEl.innerHTML = `
            <strong>Identity diagnostics:</strong>
            orphan external events ${summary.orphan_external_events ?? 0},
            unknown-run external events ${summary.unknown_run_external_events ?? 0},
            mismatch events ${summary.run_external_mismatch_events ?? 0}
        `;
    }
    const table = document.getElementById('reporting-identity-diagnostics-table');
    if (table) {
        const rows = (payload.mismatch_samples || []).map(item => `
            <tr>
                <td><code>${item.run_id}</code></td>
                <td><code>${item.event_external_user_id}</code></td>
                <td><code>${item.run_external_user_id}</code></td>
            </tr>
        `).join('');
        table.innerHTML = rows || '<tr><td colspan="3" class="text-muted">No mismatch samples in selected window.</td></tr>';
    }
}

function renderExperimentMetrics(payload) {
    reportingLastExperiments = payload;
    const summaryEl = document.getElementById('reporting-experiment-summary');
    if (summaryEl) {
        summaryEl.innerHTML = `
            <strong>Experiments:</strong>
            ${payload.experiment_id || 'multiple/none'} | assignments ${payload.runs_with_assignment ?? 0}
        `;
    }
    const table = document.getElementById('reporting-experiment-table');
    if (table) {
        const rows = (payload.variants || []).map(item => `
            <tr>
                <td>${item.variant_id}</td>
                <td>${item.runs || 0}</td>
                <td>${item.impressions || 0}</td>
                <td>${item.clicks || 0}</td>
                <td>${item.conversions || 0}</td>
                <td>${(Number(item.ctr || 0) * 100).toFixed(2)}%</td>
                <td>${(Number(item.conversion_rate || 0) * 100).toFixed(2)}%</td>
            </tr>
        `).join('');
        table.innerHTML = rows || '<tr><td colspan="7" class="text-muted">No experiment assignments in selected window.</td></tr>';
    }
    const baseline = document.getElementById('experiment-baseline');
    const candidate = document.getElementById('experiment-candidate');
    if (baseline && candidate) {
        const options = (payload.variants || []).map(item => (
            `<option value="${item.variant_id}">${item.variant_id} (runs ${item.runs || 0}, CTR ${(Number(item.ctr || 0) * 100).toFixed(2)}%)</option>`
        )).join('');
        baseline.innerHTML = options || '<option value="">No variants</option>';
        candidate.innerHTML = options || '<option value="">No variants</option>';
        if ((payload.variants || []).length >= 2) {
            baseline.value = payload.variants[0].variant_id;
            candidate.value = payload.variants[1].variant_id;
        } else if ((payload.variants || []).length === 1) {
            baseline.value = payload.variants[0].variant_id;
            candidate.value = payload.variants[0].variant_id;
        }
    }
}

function renderExperimentComparison(payload) {
    reportingLastExperimentComparison = payload;
    const summary = document.getElementById('reporting-experiment-compare-summary');
    const table = document.getElementById('reporting-experiment-compare-table');
    if (summary) {
        summary.innerHTML = `
            <strong>Experiment comparison:</strong>
            baseline ${payload.baseline_variant}, candidate ${payload.candidate_variant},
            window ${payload.window_days} days
        `;
    }
    if (table) {
        const rows = (payload.comparison || []).map(item => `
            <tr>
                <td>${item.metric}</td>
                <td>${item.baseline ?? 'n/a'}</td>
                <td>${item.candidate ?? 'n/a'}</td>
                <td>${item.delta === null || item.delta === undefined ? 'n/a' : Number(item.delta).toFixed(6)}</td>
                <td>${item.delta_pct === null || item.delta_pct === undefined ? 'n/a' : `${(Number(item.delta_pct) * 100).toFixed(2)}%`}</td>
            </tr>
        `).join('');
        table.innerHTML = rows || '<tr><td colspan="5" class="text-muted">No comparison data.</td></tr>';
    }
}

async function compareExperimentVariants() {
    const days = Number(document.getElementById('reporting-days')?.value || 30);
    const baseline = document.getElementById('experiment-baseline')?.value || '';
    const candidate = document.getElementById('experiment-candidate')?.value || '';
    const experimentId = reportingLastExperiments?.experiment_id || '';
    if (!baseline || !candidate) {
        throw new Error('Select baseline and candidate variants');
    }
    const params = new URLSearchParams({
        days: String(Number.isFinite(days) ? Math.max(1, Math.min(365, Math.round(days))) : 30),
        baseline_variant: baseline,
        candidate_variant: candidate,
        limit_runs: '5000',
        limit_events: '100000'
    });
    if (experimentId) params.set('experiment_id', experimentId);
    const response = await fetch(`/api/metrics/experiments/compare?${params.toString()}`);
    if (!response.ok) {
        const error = await response.json();
        throw new Error(error.error || 'Failed to compare variants');
    }
    const payload = await response.json();
    renderExperimentComparison(payload);
}

function renderScenarioTraceMetrics(payload) {
    reportingLastScenarioTraces = payload;
    const table = document.getElementById('reporting-scenario-trace-table');
    if (!table) return;
    const rows = (payload.scenarios || []).map(item => `
        <tr>
            <td>${item.name || item.scenario_id}</td>
            <td>${item.runs || 0}</td>
            <td>${item.filtered_out || 0}</td>
            <td>${item.remaining || 0}</td>
            <td>${(Number(item.drop_rate || 0) * 100).toFixed(2)}%</td>
            <td class="small">${(item.top_rules || []).map(rule => `${rule.rule}:${rule.count}`).join(' | ') || 'n/a'}</td>
        </tr>
    `).join('');
    table.innerHTML = rows || '<tr><td colspan="6" class="text-muted">No scenario trace data in selected window.</td></tr>';
}

function formatSnapshotOption(snapshot) {
    const label = (snapshot.metadata || {}).label ? ` | ${(snapshot.metadata || {}).label}` : '';
    return `${snapshot.created_at} | ${snapshot.snapshot_id.slice(0, 8)} | avg_score ${Number((snapshot.metrics || {}).avg_score || 0).toFixed(4)}${label}`;
}

function renderQualitySnapshotSelectors() {
    const baseline = document.getElementById('quality-baseline');
    const candidate = document.getElementById('quality-candidate');
    if (!baseline || !candidate) return;
    const options = reportingQualitySnapshots.map(snapshot => (
        `<option value="${snapshot.snapshot_id}">${formatSnapshotOption(snapshot)}</option>`
    )).join('');
    baseline.innerHTML = options || '<option value="">No snapshots</option>';
    candidate.innerHTML = options || '<option value="">No snapshots</option>';
    if (reportingQualitySnapshots.length >= 2) {
        baseline.value = reportingQualitySnapshots[1].snapshot_id;
        candidate.value = reportingQualitySnapshots[0].snapshot_id;
    } else if (reportingQualitySnapshots.length === 1) {
        baseline.value = reportingQualitySnapshots[0].snapshot_id;
        candidate.value = reportingQualitySnapshots[0].snapshot_id;
    }
}

function renderQualitySnapshotCompare(payload) {
    reportingLastQualityCompare = payload;
    const summary = document.getElementById('reporting-quality-summary');
    const table = document.getElementById('reporting-quality-compare-table');
    if (summary) {
        summary.innerHTML = `
            <strong>Quality snapshots:</strong>
            baseline ${payload.baseline.snapshot_id.slice(0, 8)} (${payload.baseline.created_at}),
            candidate ${payload.candidate.snapshot_id.slice(0, 8)} (${payload.candidate.created_at})
        `;
    }
    if (table) {
        const rows = (payload.deltas || []).map(item => `
            <tr>
                <td>${item.metric}</td>
                <td>${item.baseline ?? 'n/a'}</td>
                <td>${item.candidate ?? 'n/a'}</td>
                <td>${item.delta === null || item.delta === undefined ? 'n/a' : Number(item.delta).toFixed(6)}</td>
                <td>${item.delta_pct === null || item.delta_pct === undefined ? 'n/a' : `${(Number(item.delta_pct) * 100).toFixed(2)}%`}</td>
            </tr>
        `).join('');
        table.innerHTML = rows || '<tr><td colspan="5" class="text-muted">No comparable numeric metrics.</td></tr>';
    }
}

async function loadQualitySnapshotHistory() {
    const summary = document.getElementById('reporting-quality-summary');
    try {
        const response = await fetch('/api/metrics/offline/snapshots?snapshot_type=offline_quality&limit=30');
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Failed to load quality snapshots');
        }
        const payload = await response.json();
        reportingQualitySnapshots = payload.snapshots || [];
        renderQualitySnapshotSelectors();
        if (summary) {
            summary.textContent = `Loaded ${reportingQualitySnapshots.length} quality snapshots.`;
        }
        const table = document.getElementById('reporting-quality-compare-table');
        if (table && !reportingQualitySnapshots.length) {
            table.innerHTML = '<tr><td colspan="5" class="text-muted">No quality snapshots yet.</td></tr>';
        }
    } catch (error) {
        if (summary) summary.textContent = `Quality snapshots unavailable: ${error.message}`;
    }
}

async function captureQualitySnapshot() {
    const days = Number(document.getElementById('reporting-days')?.value || 30);
    const response = await fetch('/api/metrics/offline/snapshots', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...getOperatorHeaders() },
        body: JSON.stringify({
            snapshot_type: 'offline_quality',
            window_days: Number.isFinite(days) ? Math.max(1, Math.min(365, Math.round(days))) : 30,
            limit_runs: 200,
            actor_id: getOperatorId() || undefined
        })
    });
    if (!response.ok) {
        const error = await response.json();
        throw new Error(error.error || 'Failed to capture quality snapshot');
    }
    await loadQualitySnapshotHistory();
}

async function compareQualitySnapshots() {
    const baselineId = document.getElementById('quality-baseline')?.value || '';
    const candidateId = document.getElementById('quality-candidate')?.value || '';
    if (!baselineId || !candidateId) {
        throw new Error('Select baseline and candidate snapshots');
    }
    const response = await fetch(`/api/metrics/offline/snapshots/compare?baseline_id=${encodeURIComponent(baselineId)}&candidate_id=${encodeURIComponent(candidateId)}`);
    if (!response.ok) {
        const error = await response.json();
        throw new Error(error.error || 'Failed to compare quality snapshots');
    }
    const payload = await response.json();
    renderQualitySnapshotCompare(payload);
}

async function loadReportingWorkspace() {
    try {
        const days = Number(document.getElementById('reporting-days')?.value || 30);
        const scenarioIds = getSelectedReportingScenarioIds();
        const source = (document.getElementById('reporting-source-filter')?.value || '').trim();
        const topRunsRaw = Number(document.getElementById('reporting-top-runs')?.value || 30);
        const topRuns = Number.isFinite(topRunsRaw) ? Math.max(5, Math.min(200, Math.round(topRunsRaw))) : 30;
        const params = new URLSearchParams({
            days: String(Number.isFinite(days) && days > 0 ? Math.round(days) : 30),
            limit: '50000'
        });
        if (scenarioIds.length) params.set('scenario_ids', scenarioIds.join(','));
        if (source) params.set('source', source);
        const attributionParams = new URLSearchParams(params);
        attributionParams.set('top_runs', String(topRuns));

        const [trendsResponse, attributionResponse, identityResponse, identityDiagnosticsResponse, experimentsResponse, traceResponse] = await Promise.all([
            fetch(`/api/metrics/trends?${params.toString()}`),
            fetch(`/api/metrics/attribution?${attributionParams.toString()}`),
            fetch(`/api/metrics/identity?days=${params.get('days')}&limit_events=50000&limit_runs=1000&top_external=25`),
            fetch(`/api/metrics/identity/diagnostics?days=${params.get('days')}&limit_events=50000&limit_runs=5000`),
            fetch(`/api/metrics/experiments?days=${params.get('days')}&limit_runs=5000&limit_events=100000`),
            fetch(`/api/metrics/scenario-traces?days=${params.get('days')}&limit_runs=1000${scenarioIds.length ? `&scenario_ids=${encodeURIComponent(scenarioIds.join(','))}` : ''}`)
        ]);
        if (!trendsResponse.ok) {
            const error = await trendsResponse.json();
            throw new Error(error.error || 'Failed to load reporting trends');
        }
        if (!attributionResponse.ok) {
            const error = await attributionResponse.json();
            throw new Error(error.error || 'Failed to load attribution trends');
        }
        if (!identityResponse.ok) {
            const error = await identityResponse.json();
            throw new Error(error.error || 'Failed to load identity analytics');
        }
        if (!identityDiagnosticsResponse.ok) {
            const error = await identityDiagnosticsResponse.json();
            throw new Error(error.error || 'Failed to load identity diagnostics');
        }
        if (!experimentsResponse.ok) {
            const error = await experimentsResponse.json();
            throw new Error(error.error || 'Failed to load experiment analytics');
        }
        if (!traceResponse.ok) {
            const error = await traceResponse.json();
            throw new Error(error.error || 'Failed to load scenario trace analytics');
        }
        const trendsPayload = await trendsResponse.json();
        const attributionPayload = await attributionResponse.json();
        const identityPayload = await identityResponse.json();
        const identityDiagnosticsPayload = await identityDiagnosticsResponse.json();
        const experimentsPayload = await experimentsResponse.json();
        const tracePayload = await traceResponse.json();
        renderReportingWorkspace(trendsPayload);
        renderReportingAttribution(attributionPayload);
        renderIdentityMetrics(identityPayload);
        renderIdentityDiagnostics(identityDiagnosticsPayload);
        renderExperimentMetrics(experimentsPayload);
        if ((experimentsPayload.variants || []).length >= 1) {
            try {
                await compareExperimentVariants();
            } catch (error) {
                const summary = document.getElementById('reporting-experiment-compare-summary');
                const table = document.getElementById('reporting-experiment-compare-table');
                if (summary) summary.textContent = `Experiment comparison unavailable: ${error.message}`;
                if (table) table.innerHTML = '<tr><td colspan="5" class="text-muted">Select variants to compare.</td></tr>';
            }
        }
        renderScenarioTraceMetrics(tracePayload);
    } catch (error) {
        document.getElementById('reporting-summary').textContent = `Reporting unavailable: ${error.message}`;
        document.getElementById('reporting-scenario-table').innerHTML = '<tr><td colspan="5" class="text-danger">Failed to load reporting data.</td></tr>';
        const attributionTable = document.getElementById('reporting-attribution-table');
        const sourceTable = document.getElementById('reporting-source-table');
        const identitySummary = document.getElementById('reporting-identity-summary');
        const identityTable = document.getElementById('reporting-identity-table');
        const identityDiagSummary = document.getElementById('reporting-identity-diagnostics-summary');
        const identityDiagTable = document.getElementById('reporting-identity-diagnostics-table');
        const experimentSummary = document.getElementById('reporting-experiment-summary');
        const experimentTable = document.getElementById('reporting-experiment-table');
        const experimentCompareSummary = document.getElementById('reporting-experiment-compare-summary');
        const experimentCompareTable = document.getElementById('reporting-experiment-compare-table');
        const traceTable = document.getElementById('reporting-scenario-trace-table');
        if (attributionTable) attributionTable.innerHTML = '<tr><td colspan="9" class="text-danger">Failed to load attribution data.</td></tr>';
        if (sourceTable) sourceTable.innerHTML = '<tr><td colspan="6" class="text-danger">Failed to load attribution data.</td></tr>';
        if (identitySummary) identitySummary.textContent = `Identity analytics unavailable: ${error.message}`;
        if (identityTable) identityTable.innerHTML = '<tr><td colspan="7" class="text-danger">Failed to load identity analytics.</td></tr>';
        if (identityDiagSummary) identityDiagSummary.textContent = `Identity diagnostics unavailable: ${error.message}`;
        if (identityDiagTable) identityDiagTable.innerHTML = '<tr><td colspan="3" class="text-danger">Failed to load identity diagnostics.</td></tr>';
        if (experimentSummary) experimentSummary.textContent = `Experiment analytics unavailable: ${error.message}`;
        if (experimentTable) experimentTable.innerHTML = '<tr><td colspan="7" class="text-danger">Failed to load experiment analytics.</td></tr>';
        if (experimentCompareSummary) experimentCompareSummary.textContent = `Experiment comparison unavailable: ${error.message}`;
        if (experimentCompareTable) experimentCompareTable.innerHTML = '<tr><td colspan="5" class="text-danger">Failed to load experiment comparison.</td></tr>';
        if (traceTable) traceTable.innerHTML = '<tr><td colspan="6" class="text-danger">Failed to load scenario trace analytics.</td></tr>';
    }
}

function exportReportingCsv() {
    if (!reportingLastPayload) {
        showError('No reporting data loaded yet.');
        return;
    }
    const rows = [['date', 'impressions', 'clicks', 'conversions', 'ctr']];
    (reportingLastPayload.totals_by_day || []).forEach(item => {
        rows.push([item.date, item.impressions, item.clicks, item.conversions, item.ctr]);
    });
    rows.push([]);
    rows.push(['scenario_id', 'scenario_name', 'impressions', 'clicks', 'conversions', 'ctr']);
    (reportingLastPayload.scenarios || []).forEach(item => {
        rows.push([item.scenario_id, item.name, item.impressions, item.clicks, item.conversions, item.ctr]);
    });
    if (reportingLastAttribution) {
        rows.push([]);
        rows.push(['run_id', 'config_id', 'config_version', 'scenario_id', 'selected_sources', 'impressions', 'clicks', 'conversions', 'ctr', 'conversion_rate']);
        (reportingLastAttribution.by_run || []).forEach(item => {
            rows.push([
                item.run_id,
                item.config_id,
                item.config_version,
                item.scenario_id,
                (item.selected_sources || []).join('|'),
                item.impressions,
                item.clicks,
                item.conversions,
                item.ctr,
                item.conversion_rate
            ]);
        });
    }
    if (reportingLastExperimentComparison) {
        rows.push([]);
        rows.push(['experiment_metric', 'baseline', 'candidate', 'delta', 'delta_pct']);
        (reportingLastExperimentComparison.comparison || []).forEach(item => {
            rows.push([item.metric, item.baseline, item.candidate, item.delta, item.delta_pct]);
        });
    }
    if (reportingLastQualityCompare) {
        rows.push([]);
        rows.push(['quality_metric', 'baseline', 'candidate', 'delta', 'delta_pct']);
        (reportingLastQualityCompare.deltas || []).forEach(item => {
            rows.push([item.metric, item.baseline, item.candidate, item.delta, item.delta_pct]);
        });
    }
    if (reportingLastIdentity) {
        rows.push([]);
        rows.push(['external_user_id', 'events', 'impressions', 'clicks', 'conversions', 'ctr', 'scenario_count']);
        (reportingLastIdentity.top_external_users || []).forEach(item => {
            rows.push([
                item.external_user_id,
                item.events,
                item.impressions,
                item.clicks,
                item.conversions,
                item.ctr,
                item.scenario_count
            ]);
        });
    }
    if (reportingLastScenarioTraces) {
        rows.push([]);
        rows.push(['scenario_id', 'scenario_name', 'runs', 'filtered_out', 'remaining', 'drop_rate', 'top_rules']);
        (reportingLastScenarioTraces.scenarios || []).forEach(item => {
            rows.push([
                item.scenario_id,
                item.name,
                item.runs,
                item.filtered_out,
                item.remaining,
                item.drop_rate,
                (item.top_rules || []).map(rule => `${rule.rule}:${rule.count}`).join('|')
            ]);
        });
    }
    if (reportingLastIdentityDiagnostics) {
        rows.push([]);
        rows.push(['orphan_external_events', 'unknown_run_external_events', 'run_external_mismatch_events', 'external_ids_only_in_events', 'external_ids_only_in_runs']);
        const summary = reportingLastIdentityDiagnostics.summary || {};
        rows.push([
            summary.orphan_external_events ?? 0,
            summary.unknown_run_external_events ?? 0,
            summary.run_external_mismatch_events ?? 0,
            summary.external_ids_only_in_events ?? 0,
            summary.external_ids_only_in_runs ?? 0
        ]);
    }
    if (reportingLastExperiments) {
        rows.push([]);
        rows.push(['variant_id', 'runs', 'impressions', 'clicks', 'conversions', 'ctr', 'conversion_rate']);
        (reportingLastExperiments.variants || []).forEach(item => {
            rows.push([
                item.variant_id,
                item.runs,
                item.impressions,
                item.clicks,
                item.conversions,
                item.ctr,
                item.conversion_rate
            ]);
        });
    }
    const csv = rows.map(row => row.map(toCsvCell).join(',')).join('\n');
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `reporting_trends_${new Date().toISOString().slice(0, 10)}.csv`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
}

function renderRecommendationRunList() {
    const container = document.getElementById('run-list');
    if (!container) return;
    if (!recommendationRuns.length) {
        container.innerHTML = '<span>No recommendation runs available.</span>';
        return;
    }
    container.innerHTML = recommendationRuns.map(run => `
        <button class="btn btn-sm btn-outline-secondary w-100 text-start mb-1 run-item" data-id="${run.run_id}">
            <div><strong>${run.run_id.slice(0, 8)}</strong> | ${run.config_id} v${run.config_version}</div>
            <div class="small text-muted">${run.created_at} | items ${run.summary?.count ?? 0}</div>
        </button>
    `).join('');
}

async function loadRecommendationRuns() {
    try {
        const limitRaw = Number(document.getElementById('run-limit')?.value || 20);
        const limit = Number.isFinite(limitRaw) ? Math.max(5, Math.min(100, Math.round(limitRaw))) : 20;
        const response = await fetch(`/api/recommendation-runs?limit=${limit}&offset=0`);
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Failed to load recommendation runs');
        }
        const payload = await response.json();
        recommendationRuns = payload.runs || [];
        renderRecommendationRunList();
    } catch (error) {
        document.getElementById('run-list').textContent = `Run list unavailable: ${error.message}`;
    }
}

function summarizeRunItemReasoning(item) {
    const contrib = item.feature_contributions || {};
    const entries = Object.entries(contrib)
        .filter(([, value]) => typeof value === 'number')
        .sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]))
        .slice(0, 2)
        .map(([name, value]) => `${name}:${value.toFixed(3)}`);
    return entries.join(', ') || (item.explanation || '').slice(0, 80) || 'n/a';
}

function renderRecommendationRunDetail(run) {
    const summary = document.getElementById('run-detail-summary');
    const request = document.getElementById('run-detail-request');
    const items = document.getElementById('run-detail-items');
    summary.innerHTML = `
        <div><strong>Run:</strong> ${run.run_id}</div>
        <div><strong>User:</strong> ${run.user_id}</div>
        <div><strong>Config:</strong> ${run.config_id} v${run.config_version}</div>
        <div><strong>Created:</strong> ${run.created_at}</div>
        <div><strong>Duration:</strong> ${run.summary?.duration_ms ?? 'n/a'} ms | <strong>Avg score:</strong> ${Number(run.summary?.avg_score || 0).toFixed(4)}</div>
    `;
    request.textContent = JSON.stringify(run.request || {}, null, 2);
    items.innerHTML = (run.items || []).map(item => `
        <tr>
            <td>${item.rank}</td>
            <td><code>${item.article_id}</code><div class="small text-muted">${item.source || 'unknown'}</div></td>
            <td>${Number(item.score || 0).toFixed(4)}</td>
            <td>${summarizeRunItemReasoning(item)}</td>
        </tr>
    `).join('') || '<tr><td colspan="4" class="text-muted">No items.</td></tr>';
}

function renderRunDecisionFlow(flow) {
    const summary = document.getElementById('run-decision-flow-summary');
    const table = document.getElementById('run-decision-flow-table');
    if (!summary || !table) return;
    const trace = flow.scenario_trace_summary || {};
    summary.innerHTML = `
        <strong>Scenario:</strong> ${flow.scenario_id || 'none'}
        | <strong>Applied:</strong> ${trace.applied ? 'yes' : 'no'}
        | <strong>Filtered out:</strong> ${trace.filtered_out ?? 0}
        | <strong>Remaining:</strong> ${trace.remaining ?? 0}
    `;
    const rows = (flow.decisions || []).map(item => `
        <tr>
            <td>${item.position ?? ''}</td>
            <td><code>${item.article_id || 'n/a'}</code><div class="small text-muted">${item.source || 'unknown'}</div></td>
            <td>${item.status || 'n/a'}</td>
            <td>${item.score_before == null ? 'n/a' : Number(item.score_before).toFixed(4)}</td>
            <td>${item.boost == null ? 'n/a' : Number(item.boost).toFixed(3)}</td>
            <td>${item.score_after == null ? 'n/a' : Number(item.score_after).toFixed(4)}</td>
            <td>${item.reason || 'n/a'}</td>
            <td>${item.final_rank ?? 'n/a'}</td>
        </tr>
    `).join('');
    table.innerHTML = rows || '<tr><td colspan="8" class="text-muted">No scenario decisions for this run.</td></tr>';
}

async function loadRecommendationRunDetail(runId) {
    const summary = document.getElementById('run-detail-summary');
    summary.textContent = `Loading run ${runId}...`;
    const [runResponse, flowResponse] = await Promise.all([
        fetch(`/api/recommendation-runs/${encodeURIComponent(runId)}`),
        fetch(`/api/recommendation-runs/${encodeURIComponent(runId)}/decision-flow`)
    ]);
    if (!runResponse.ok) {
        const error = await runResponse.json();
        throw new Error(error.error || 'Failed to load run detail');
    }
    if (!flowResponse.ok) {
        const error = await flowResponse.json();
        throw new Error(error.error || 'Failed to load run decision flow');
    }
    const [runPayload, flowPayload] = await Promise.all([runResponse.json(), flowResponse.json()]);
    renderRecommendationRunDetail(runPayload);
    renderRunDecisionFlow(flowPayload);
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

    const clusterTopics = stats.cluster_topics || {};
    const topicRows = Object.entries(clusterTopics).map(([cluster, titles]) => `
        <tr>
            <td>${cluster}</td>
            <td>${Array.isArray(titles) && titles.length ? titles.join(' | ') : 'n/a'}</td>
        </tr>
    `).join('');
    const quality = stats.cluster_quality || {};

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
        <div class="mt-3 small text-muted">
            <strong>Cluster coverage:</strong> ${(Number(quality.coverage_ratio || 0) * 100).toFixed(1)}%
            | <strong>Largest cluster share:</strong> ${(Number(quality.largest_cluster_share || 0) * 100).toFixed(1)}%
            | <strong>Cluster count:</strong> ${quality.cluster_count ?? 0}
        </div>
        <div class="table-responsive mt-2">
            <table class="table table-sm mb-0">
                <thead><tr><th>Cluster</th><th>Top sample titles</th></tr></thead>
                <tbody>${topicRows || '<tr><td colspan="2" class="text-muted">No cluster topic data.</td></tr>'}</tbody>
            </table>
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
    const on = (id, event, handler) => {
        const el = document.getElementById(id);
        if (el) el.addEventListener(event, handler);
    };
    const articleList = document.getElementById('article-list');
    if (articleList) {
        articleList.addEventListener('click', (e) => {
            e.preventDefault();
            const articleItem = e.target.closest('.list-group-item');
            if (!articleItem) return;
            const articleId = articleItem.dataset.id;
            const article = articles.find(a => a.article_id === articleId);
            if (!article) return;
            document.querySelectorAll('.list-group-item').forEach(item => item.classList.remove('active'));
            articleItem.classList.add('active');
            displayArticle(article);
        });
    }

    on('show-similar', 'click', showSimilarArticles);
    on('refresh-decision-context', 'click', loadDecisionContext);
    on('refresh-engine-snapshot', 'click', loadEngineConfigSnapshot);
    on('refresh-reporting-workspace', 'click', loadReportingWorkspace);
    on('export-reporting-csv', 'click', exportReportingCsv);
    on('reporting-days', 'change', loadReportingWorkspace);
    on('reporting-scenario-filter', 'change', loadReportingWorkspace);
    on('reporting-source-filter', 'change', loadReportingWorkspace);
    on('reporting-top-runs', 'change', loadReportingWorkspace);
    on('capture-quality-snapshot', 'click', async () => {
        try {
            await captureQualitySnapshot();
        } catch (error) {
            showError(error.message || 'Failed to capture quality snapshot');
        }
    });
    on('compare-quality-snapshots', 'click', async () => {
        try {
            await compareQualitySnapshots();
        } catch (error) {
            showError(error.message || 'Failed to compare snapshots');
        }
    });
    on('compare-experiment-variants', 'click', async () => {
        try {
            await compareExperimentVariants();
        } catch (error) {
            showError(error.message || 'Failed to compare experiment variants');
        }
    });
    on('refresh-run-explorer', 'click', loadRecommendationRuns);
    on('run-limit', 'change', loadRecommendationRuns);
    on('run-list', 'click', async (event) => {
        const button = event.target.closest('.run-item');
        if (!button) return;
        try {
            await loadRecommendationRunDetail(button.dataset.id);
        } catch (error) {
            showError(error.message || 'Failed to load run detail');
        }
    });
    on('ranking-config', 'change', (event) => {
        populateRankingConfigEditor(event.target.value);
        loadDecisionContext();
    });
    on('scenario-select', 'change', (event) => {
        const selected = scenarios.find(item => item.scenario_id === event.target.value);
        applyScenarioToEditor(selected || null);
        loadDecisionContext();
        loadScenarioSourceMetrics();
    });
    on('external-user-id', 'change', loadDecisionContext);
    on('source-filters', 'change', (event) => {
        if (event.target.classList.contains('source-filter')) loadDecisionContext();
    });
    on('save-source-settings', 'click', saveSourceSettings);
    on('save-ranking-config', 'click', async () => {
        try {
            await saveRankingConfig();
        } catch (error) {
            setRankingConfigStatus(error.message || 'Failed to save ranking config', true);
            showError(error.message || 'Failed to save ranking config');
        }
    });
    on('delete-ranking-config', 'click', async () => {
        try {
            await deleteRankingConfig();
        } catch (error) {
            setRankingConfigStatus(error.message || 'Failed to delete ranking config', true);
            showError(error.message || 'Failed to delete ranking config');
        }
    });
    on('create-connector', 'click', async () => {
        try {
            await createConnector();
        } catch (error) {
            showError(error.message || 'Failed to create connector');
        }
    });
    on('connector-search', 'input', (event) => {
        connectorSearchTerm = (event.target.value || '').trim().toLowerCase();
        renderConnectors();
    });
    on('connector-status-filter', 'change', (event) => {
        connectorStatusFilter = event.target.value || 'all';
        renderConnectors();
    });
    on('sync-due-connectors', 'click', syncDueConnectors);
    on('run-scheduler-now', 'click', runSchedulerNow);
    on('connector-list', 'click', handleConnectorAction);
    on('save-scenario', 'click', async () => {
        try {
            applyRuleBuilderToJson();
            await saveScenario();
            await loadScenarioMetrics();
            await loadScenarioSourceMetrics();
        } catch (error) {
            showError(error.message || 'Failed to save scenario');
        }
    });
    on('delete-scenario', 'click', async () => {
        try {
            await deleteScenario();
            await loadScenarioMetrics();
            await loadScenarioSourceMetrics();
        } catch (error) {
            showError(error.message || 'Failed to delete scenario');
        }
    });
    on('refresh-scenarios', 'click', loadScenarios);
    on('refresh-scenario-metrics', 'click', loadScenarioMetrics);
    on('refresh-scenario-source-metrics', 'click', loadScenarioSourceMetrics);
    on('apply-rule-builder', 'click', () => {
        try {
            applyRuleBuilderToJson();
        } catch (error) {
            setRuleBuilderStatus(error.message || 'Failed to apply builder', true);
            showError(error.message || 'Failed to apply rule builder');
        }
    });
    on('load-rule-builder', 'click', () => {
        try {
            loadRuleBuilderFromJson();
        } catch (error) {
            setRuleBuilderStatus(error.message || 'Failed to load builder', true);
            showError(error.message || 'Failed to load rule builder');
        }
    });
    on('simulate-scenario', 'click', async () => {
        try {
            await simulateSelectedScenario();
        } catch (error) {
            showError(error.message || 'Failed to simulate scenario');
            const simulation = document.getElementById('scenario-simulation');
            if (simulation) simulation.textContent = error.message || 'Failed to simulate scenario';
        }
    });
    on('refresh-sli', 'click', loadSliOverview);
    on('persist-incidents-on-sli', 'change', loadSliOverview);
    on('save-alert-thresholds', 'click', async () => {
        try {
            await saveAlertThresholds();
            await loadSliOverview();
        } catch (error) {
            showError(error.message || 'Failed to save alert thresholds');
        }
    });
    on('evaluate-alert-incidents', 'click', async () => {
        try {
            await evaluateAlertIncidents();
        } catch (error) {
            showError(error.message || 'Failed to evaluate alert incidents');
        }
    });
    on('refresh-alert-incidents', 'click', loadAlertIncidents);
    on('incident-status-filter', 'change', loadAlertIncidents);
    on('incident-metric-filter', 'change', loadAlertIncidents);
    on('alert-incidents', 'click', async (event) => {
        const button = event.target.closest('.resolve-incident');
        if (!button) return;
        try {
            await resolveIncident(button.dataset.id);
        } catch (error) {
            showError(error.message || 'Failed to resolve incident');
        }
    });
    on('refresh-cleanup-status', 'click', loadCleanupStatus);
    on('refresh-rollups-status', 'click', loadRollupsStatus);
    on('rollups-days', 'change', loadRollupsStatus);
    on('rebuild-rollups', 'click', async () => {
        try {
            await rebuildRollups();
            if (hasElement('reporting-summary')) await loadReportingWorkspace();
        } catch (error) {
            showError(error.message || 'Failed to rebuild rollups');
        }
    });
    on('run-cleanup-now', 'click', async () => {
        try {
            await runCleanupNow();
        } catch (error) {
            showError(error.message || 'Failed to run cleanup');
        }
    });
    on('refresh-cdp-config', 'click', loadCdpConfig);
    on('save-cdp-config', 'click', async () => {
        try {
            await saveCdpConfig();
        } catch (error) {
            showError(error.message || 'Failed to save CDP config');
        }
    });
    on('save-cdp-mapping', 'click', async () => {
        try {
            await saveCdpConfig();
        } catch (error) {
            showError(error.message || 'Failed to save CDP mapping');
        }
    });
    on('refresh-cdp-profiles', 'click', loadCdpProfiles);
    on('sync-cdp-profiles', 'click', async () => {
        try {
            await syncCdpProfiles();
        } catch (error) {
            showError(error.message || 'Failed to sync CDP profiles');
        }
    });
    on('refresh-cdp-scheduler', 'click', loadCdpSchedulerStatus);
    on('run-cdp-scheduler-now', 'click', async () => {
        try {
            await runCdpSchedulerNow();
        } catch (error) {
            showError(error.message || 'Failed to run CDP scheduler now');
        }
    });
    on('refresh-cdp-diagnostics', 'click', loadCdpDiagnostics);
    on('preview-cdp-derivation', 'click', async () => {
        try {
            await deriveCdpProfile(false);
        } catch (error) {
            showError(error.message || 'Failed to preview derivation');
        }
    });
    on('persist-cdp-derivation', 'click', async () => {
        try {
            await deriveCdpProfile(true);
        } catch (error) {
            showError(error.message || 'Failed to persist derivation');
        }
    });
    on('refresh-audit-logs', 'click', loadAuditLogs);
    on('audit-actor-filter', 'change', loadAuditLogs);
    on('audit-resource-filter', 'change', loadAuditLogs);
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
