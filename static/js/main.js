// Global state
let currentArticle = null;
let articles = [];
let sourceOptions = [];
let rankingConfigs = {};
let scenarios = [];
let cdpMappingPresets = [];
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
let reportingOnlineKpi = null;
let reportingOnlineKpiSelectedConfig = '';
let reportingLastIdentityDiagnostics = null;
let reportingLastExperiments = null;
let reportingLastExperimentComparison = null;
let reportingQualitySnapshots = [];
let reportingLastQualityCompare = null;
let reportingLastConfigCompare = null;
let rolloutItems = [];
let selectedRolloutId = '';
let cdpIntegration = null;
let recommendationRuns = [];
let rankingLabContexts = [];
let rankingLabLastComparison = null;
let rankingLabEvaluationsById = {};
let articleSearchTerm = '';
let articleSourceFilter = 'all';
let articleSortMode = 'newest';
let articlePageSize = 20;
let articleCurrentPage = 1;
const preferredSourceFromQuery = new URLSearchParams(window.location.search).get('source');
const GUARD_PRESET_STORAGE_KEY = 'reporting_guard_preset_v1';
const RANKING_LAB_BOOKMARKS_STORAGE_KEY = 'ranking_lab_context_sets_v1';
const GUARD_PRESETS = {
    conservative: {
        min_ndcg_lift: 0.01,
        min_ctr_lift: 0.002,
        max_precision_drop: 0.005,
        max_recall_drop: 0.005,
        max_mrr_drop: 0.005,
        min_source_coverage_at_k: 0.45,
        min_section_coverage_at_k: 0.30,
        min_avg_freshness: 0.20,
        max_top_source_share_at_k: 0.60,
        max_stale_ratio_at_k: 0.30
    },
    balanced: {
        min_ndcg_lift: 0.0,
        min_ctr_lift: 0.0,
        max_precision_drop: 0.02,
        max_recall_drop: 0.02,
        max_mrr_drop: 0.02,
        min_source_coverage_at_k: 0.30,
        min_section_coverage_at_k: 0.20,
        min_avg_freshness: 0.15,
        max_top_source_share_at_k: 0.70,
        max_stale_ratio_at_k: 0.45
    },
    aggressive: {
        min_ndcg_lift: -0.005,
        min_ctr_lift: -0.001,
        max_precision_drop: 0.05,
        max_recall_drop: 0.05,
        max_mrr_drop: 0.05,
        min_source_coverage_at_k: 0.15,
        min_section_coverage_at_k: 0.10,
        min_avg_freshness: 0.10,
        max_top_source_share_at_k: 0.85,
        max_stale_ratio_at_k: 0.60
    }
};

function hasElement(id) {
    return Boolean(document.getElementById(id));
}

function getOperationsQueueModule() {
    if (!window.OperationsQueueModule) {
        throw new Error('Operations queue module is not loaded');
    }
    return window.OperationsQueueModule;
}

function getReportingRolloutsModule() {
    if (!window.ReportingRolloutsModule) {
        throw new Error('Reporting rollouts module is not loaded');
    }
    return window.ReportingRolloutsModule;
}

function getRecommendationsArticlesModule() {
    if (!window.RecommendationsArticlesModule) {
        throw new Error('Recommendations articles module is not loaded');
    }
    return window.RecommendationsArticlesModule;
}

function getReportingDashboardModule() {
    if (!window.ReportingDashboardModule) {
        throw new Error('Reporting dashboard module is not loaded');
    }
    return window.ReportingDashboardModule;
}

function getConnectorsControllerModule() {
    if (!window.ConnectorsControllerModule) {
        throw new Error('Connectors controller module is not loaded');
    }
    return window.ConnectorsControllerModule;
}

function getCdpControllerModule() {
    if (!window.CdpControllerModule) {
        throw new Error('CDP controller module is not loaded');
    }
    return window.CdpControllerModule;
}

function buildRecommendationsArticlesContext() {
    return {
        get articles() {
            return articles;
        },
        get currentArticle() {
            return currentArticle;
        },
        get articleSearchTerm() {
            return articleSearchTerm;
        },
        get articleSourceFilter() {
            return articleSourceFilter;
        },
        get articleSortMode() {
            return articleSortMode;
        },
        get articlePageSize() {
            return articlePageSize;
        },
        get articleCurrentPage() {
            return articleCurrentPage;
        },
        setCurrentArticle: (value) => {
            currentArticle = value;
        },
        setArticleSourceFilter: (value) => {
            articleSourceFilter = value;
        },
        setArticleCurrentPage: (value) => {
            articleCurrentPage = value;
        },
    };
}

function buildConnectorsControllerContext() {
    return {
        ApiClient,
        get connectors() {
            return connectors;
        },
        get connectorMetricsById() {
            return connectorMetricsById;
        },
        get connectorSearchTerm() {
            return connectorSearchTerm;
        },
        get connectorStatusFilter() {
            return connectorStatusFilter;
        },
        connectorRunsCache,
        loadConnectors,
        loadConnectorMetrics,
        showError,
    };
}

function buildCdpControllerContext() {
    return {
        get cdpMappingPresets() {
            return cdpMappingPresets;
        },
        setCdpMappingPresets: (value) => {
            cdpMappingPresets = value;
        },
        setCdpIntegration: (value) => {
            cdpIntegration = value;
        },
        getOperatorId,
        getOperatorHeaders,
    };
}

function buildReportingDashboardContext() {
    return {
        get reportingVolumeChart() {
            return reportingVolumeChart;
        },
        get reportingCtrChart() {
            return reportingCtrChart;
        },
        get reportingScenarioOverlayChart() {
            return reportingScenarioOverlayChart;
        },
        get reportingFunnelChart() {
            return reportingFunnelChart;
        },
        setReportingVolumeChart: (value) => {
            reportingVolumeChart = value;
        },
        setReportingCtrChart: (value) => {
            reportingCtrChart = value;
        },
        setReportingScenarioOverlayChart: (value) => {
            reportingScenarioOverlayChart = value;
        },
        setReportingFunnelChart: (value) => {
            reportingFunnelChart = value;
        },
        setReportingLastPayload: (value) => {
            reportingLastPayload = value;
        },
        setReportingLastAttribution: (value) => {
            reportingLastAttribution = value;
        },
    };
}

function buildRolloutsModuleContext() {
    return {
        ApiClient,
        rolloutItems,
        selectedRolloutId,
        rankingConfigs,
        setRolloutItems: (items) => {
            rolloutItems = items;
        },
        setSelectedRolloutId: (rolloutId) => {
            selectedRolloutId = rolloutId;
        },
        getOperatorId,
        getOperatorHeaders,
        renderRolloutControls,
        loadRollouts,
    };
}

// Initialize the application
document.addEventListener('DOMContentLoaded', () => {
    if (hasElement('article-list')) loadArticles();
    if (hasElement('article-stats')) loadStats();
    if (hasElement('source-filters') || hasElement('reporting-source-filter')) loadSources();
    if (hasElement('ranking-config') || hasElement('config-compare-baseline') || hasElement('lab-baseline-config')) loadRankingConfigs();
    if (hasElement('scenario-select') || hasElement('reporting-scenario-filter') || hasElement('scenario-id')) loadScenarios();
    if (hasElement('offline-metrics')) loadOfflineMetrics();
    if (hasElement('scenario-metrics')) loadScenarioMetrics();
    if (hasElement('scenario-source-metrics')) loadScenarioSourceMetrics();
    if (hasElement('threshold-p95-ms')) loadAlertThresholds();
    if (hasElement('sli-overview')) loadSliOverview();
    if (hasElement('surface-metrics-summary')) loadRecommendationSurfaceMetrics();
    if (hasElement('alert-incidents')) loadAlertIncidents();
    if (hasElement('cleanup-status')) loadCleanupStatus();
    if (hasElement('rollups-status')) loadRollupsStatus();
    if (hasElement('events-queue-status')) loadEventsQueueStatus();
    if (hasElement('events-queue-health')) loadEventsQueueHealth();
    if (hasElement('api-protection-status')) loadApiProtectionStatus();
    if (hasElement('events-queue-status')) setInterval(loadEventsQueueStatus, 5000);
    if (hasElement('events-queue-health')) setInterval(loadEventsQueueHealth, 10000);
    setInterval(() => {
        if (rollupAsyncJobId) {
            loadRollupAsyncStatus().catch(() => {});
        }
    }, 3000);
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
        loadCdpMappingPresets();
        loadCdpConfig();
        loadCdpProfiles();
        loadCdpSchedulerStatus();
        loadCdpDiagnostics();
    }
    if (hasElement('embedding-model-name')) {
        loadEmbeddingConfig();
        loadEmbeddingStatus();
        setInterval(loadEmbeddingStatus, 5000);
    }
    if (hasElement('decision-context')) loadDecisionContext();
    if (hasElement('external-user-id')) loadExternalUserIdSuggestions();
    if (hasElement('reporting-summary')) {
        loadReportingWorkspace();
        loadQualitySnapshotHistory();
    }
    if (hasElement('rollout-select') || hasElement('active-rollout-hint')) loadRollouts();
    if (hasElement('online-kpi-summary')) {
        loadOnlineKpis();
    }
    if (hasElement('guard-preset')) {
        loadGuardPresetFromStorage();
    }
    if (hasElement('lab-contexts')) {
        renderRankingLabBookmarks();
        loadRankingLabContexts();
        loadRankingLabHistory();
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

        articles = await ApiClient.get('/api/articles');
        if (!Array.isArray(articles)) {
            throw new Error('Invalid response format');
        }

        refreshArticleSourceFilterOptions();
        displayArticles();
        if (!currentArticle && articles.length) {
            selectArticleById(articles[0].article_id);
        }
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
        const data = await ApiClient.get('/api/sources');
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

async function loadExternalUserIdSuggestions() {
    const input = document.getElementById('external-user-id');
    const datalist = document.getElementById('external-user-id-options');
    const hint = document.getElementById('external-user-id-hint');
    if (!input || !datalist) return;
    try {
        const response = await fetch('/api/cdp/meiro/profiles?limit=100');
        if (!response.ok) {
            throw new Error('not available');
        }
        const payload = await response.json();
        const ids = Array.from(new Set((payload.profiles || []).map(item => item.external_user_id).filter(Boolean)));
        datalist.innerHTML = ids.map(id => `<option value="${id}"></option>`).join('');
        if (hint) {
            hint.textContent = ids.length
                ? `Loaded ${ids.length} recent external IDs from CDP sync.`
                : 'No synced external IDs yet. Add one in CDP > Profile Sync.';
        }
    } catch (_error) {
        datalist.innerHTML = '';
        if (hint) hint.textContent = 'CDP profile suggestions unavailable. You can still enter an external ID manually.';
    }
}

async function loadConnectors() {
    try {
        const data = await ApiClient.get('/api/connectors');
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
        const payload = await ApiClient.get('/api/connectors/metrics');
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
    getConnectorsControllerModule().renderConnectors(buildConnectorsControllerContext());
}

async function createConnector() {
    await getConnectorsControllerModule().createConnector(buildConnectorsControllerContext());
}

async function handleConnectorAction(event) {
    await getConnectorsControllerModule().handleConnectorAction(event, buildConnectorsControllerContext());
}

async function syncDueConnectors() {
    await getConnectorsControllerModule().syncDueConnectors(buildConnectorsControllerContext());
}

async function loadSchedulerStatus() {
    await getConnectorsControllerModule().loadSchedulerStatus(buildConnectorsControllerContext());
}

async function runSchedulerNow() {
    await getConnectorsControllerModule().runSchedulerNow(buildConnectorsControllerContext());
}

async function pollConnectorRun(runId, connectorId) {
    await getConnectorsControllerModule().pollConnectorRun(runId, connectorId, buildConnectorsControllerContext());
}

async function loadConnectorRuns(connectorId) {
    await getConnectorsControllerModule().loadConnectorRuns(connectorId, buildConnectorsControllerContext());
}

function renderConnectorRuns(connectorId) {
    getConnectorsControllerModule().renderConnectorRuns(connectorId, buildConnectorsControllerContext());
}

function validateConnectorInputs({ name, url, maxArticles, syncIntervalMinutes }) {
    return getConnectorsControllerModule().validateConnectorInputs({ name, url, maxArticles, syncIntervalMinutes });
}

function setConnectorFormError(message) {
    getConnectorsControllerModule().setConnectorFormError(message);
}

function setConnectorCardError(connectorId, message) {
    getConnectorsControllerModule().setConnectorCardError(connectorId, message);
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
    const hint = document.getElementById('active-rollout-hint');
    if (preferredSourceFromQuery) {
        document.querySelectorAll('.source-filter').forEach(el => {
            el.checked = el.value === preferredSourceFromQuery;
        });
        if (hint) {
            hint.textContent = `Source preselected from Operations: ${preferredSourceFromQuery}`;
        }
    }
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
        if (select) {
            const configIds = Object.keys(rankingConfigs);
            select.innerHTML = configIds.map(id => `<option value="${id}">${id}</option>`).join('');

            if (data.default_config_id && rankingConfigs[data.default_config_id]) {
                select.value = data.default_config_id;
            }
            populateRankingConfigEditor(select.value);
        }
        renderConfigCompareSelectors();
        renderOnlineKpiSelectors();
        renderRankingLabConfigSelectors();
        renderRuleBuilderConfigOptions();
        renderRolloutControls();
        loadDecisionContext();
    } catch (error) {
        console.error('Error loading ranking configs:', error);
        const select = document.getElementById('ranking-config');
        if (select) select.innerHTML = '<option value="balanced">balanced</option>';
        rankingConfigs = {};
        renderRuleBuilderConfigOptions();
        renderConfigCompareSelectors();
        renderOnlineKpiSelectors();
        renderRankingLabConfigSelectors();
        renderRolloutControls();
        if (select) populateRankingConfigEditor('balanced');
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

function renderRankingLabConfigSelectors() {
    const baseline = document.getElementById('lab-baseline-config');
    const candidate = document.getElementById('lab-candidate-config');
    if (!baseline || !candidate) return;
    const configIds = Object.keys(rankingConfigs);
    const options = configIds.map(id => `<option value="${id}">${id}</option>`).join('');
    baseline.innerHTML = options || '<option value="balanced">balanced</option>';
    candidate.innerHTML = options || '<option value="balanced">balanced</option>';
    if (baseline.value && candidate.value === baseline.value && configIds.length > 1) {
        const alt = configIds.find(id => id !== baseline.value);
        if (alt) candidate.value = alt;
    }
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
    document.getElementById('ranking-hard-max-age-days').value =
        config.hard_max_age_days == null ? '' : Number(config.hard_max_age_days);
    document.getElementById('ranking-min-freshness').value =
        config.min_freshness == null ? '' : Number(config.min_freshness);
    document.getElementById('ranking-max-per-source').value =
        config.max_per_source == null ? '' : Number(config.max_per_source);
    document.getElementById('ranking-max-per-topic').value =
        config.max_per_topic == null ? '' : Number(config.max_per_topic);
    document.getElementById('ranking-max-per-section').value =
        config.max_per_section == null ? '' : Number(config.max_per_section);
    document.getElementById('ranking-recent-boost-days').value = Number(config.recent_boost_days ?? 0);
    document.getElementById('ranking-recent-boost-factor').value = Number(config.recent_boost_factor ?? 1.0);
    document.getElementById('ranking-dedup-by-title').checked = Boolean(config.dedup_by_title);
    document.getElementById('ranking-dedup-by-url').checked = Boolean(config.dedup_by_url);
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
    const hardMaxAgeRaw = (document.getElementById('ranking-hard-max-age-days').value || '').trim();
    const minFreshnessRaw = (document.getElementById('ranking-min-freshness').value || '').trim();
    const maxPerSourceRaw = (document.getElementById('ranking-max-per-source').value || '').trim();
    const maxPerTopicRaw = (document.getElementById('ranking-max-per-topic').value || '').trim();
    const maxPerSectionRaw = (document.getElementById('ranking-max-per-section').value || '').trim();
    const recentBoostDaysRaw = (document.getElementById('ranking-recent-boost-days').value || '').trim();
    const recentBoostFactorRaw = (document.getElementById('ranking-recent-boost-factor').value || '').trim();
    const dedupByTitle = Boolean(document.getElementById('ranking-dedup-by-title').checked);
    const dedupByUrl = Boolean(document.getElementById('ranking-dedup-by-url').checked);
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
    const parseOptionalInt = (raw, label, min) => {
        if (!raw) return null;
        const parsed = Number(raw);
        if (!Number.isFinite(parsed) || parsed < min) {
            throw new Error(`${label} must be >= ${min}.`);
        }
        return Math.round(parsed);
    };
    const parseOptionalFloat = (raw, label, min, max = null) => {
        if (!raw) return null;
        const parsed = Number(raw);
        if (!Number.isFinite(parsed) || parsed < min || (max != null && parsed > max)) {
            throw new Error(`${label} must be between ${min}${max != null ? ` and ${max}` : ''}.`);
        }
        return parsed;
    };
    return {
        configId,
        payload: {
            config_id: configId,
            weights,
            time_decay_days: Math.round(timeDecayDays),
            source_weights: sourceWeights,
            hard_max_age_days: parseOptionalInt(hardMaxAgeRaw, 'Hard max age days', 0),
            min_freshness: parseOptionalFloat(minFreshnessRaw, 'Min freshness', 0, 1),
            max_per_source: parseOptionalInt(maxPerSourceRaw, 'Max per source', 1),
            max_per_topic: parseOptionalInt(maxPerTopicRaw, 'Max per topic', 1),
            max_per_section: parseOptionalInt(maxPerSectionRaw, 'Max per section', 1),
            recent_boost_days: parseOptionalInt(recentBoostDaysRaw, 'Recent boost window', 0) ?? 0,
            recent_boost_factor: parseOptionalFloat(recentBoostFactorRaw, 'Recent boost factor', 0.5, 5) ?? 1.0,
            dedup_by_title: dedupByTitle,
            dedup_by_url: dedupByUrl
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
    renderScenarioLifecycleStatus(scenario || null);
    loadScenarioVersions(scenario?.scenario_id || '').catch(() => {});
}

function renderScenarioLifecycleStatus(scenario) {
    const el = document.getElementById('scenario-lifecycle-status');
    if (!el) return;
    if (!scenario) {
        el.textContent = 'Lifecycle status unavailable.';
        return;
    }
    const lifecycle = scenario.lifecycle || {};
    const draftVersion = Number(lifecycle.draft_version || 1);
    const publishedVersion = Number(lifecycle.published_version || 1);
    const pending = Boolean(lifecycle.pending_changes);
    const publishedAt = lifecycle.published_at || 'n/a';
    const publishedBy = lifecycle.published_by || 'n/a';
    el.innerHTML = `
        Draft v${draftVersion} | Published v${publishedVersion}
        ${pending ? '<span class="text-warning">| Pending draft changes</span>' : '<span class="text-success">| In sync</span>'}
        <br><span class="text-muted">Last publish: ${publishedAt} by ${publishedBy}</span>
    `;
}

async function loadScenarioVersions(scenarioId) {
    const select = document.getElementById('scenario-version-select');
    if (!select) return;
    if (!scenarioId) {
        select.innerHTML = '<option value="">Latest previous version</option>';
        return;
    }
    try {
        const payload = await ApiClient.get(`/api/scenarios/${encodeURIComponent(scenarioId)}/versions`);
        const versions = payload.versions || [];
        const options = ['<option value="">Latest previous version</option>'].concat(
            versions.map(item => `<option value="${item.version}">v${item.version} (${item.published_at || 'n/a'})</option>`)
        );
        select.innerHTML = options.join('');
    } catch (_error) {
        select.innerHTML = '<option value="">Versions unavailable</option>';
    }
}

async function loadScenarios() {
    try {
        const data = await ApiClient.get('/api/scenarios', { query: { include_disabled: true } });
        scenarios = data.scenarios || [];
        const select = document.getElementById('scenario-select');
        if (select) {
            const current = select.value;
            select.innerHTML = '<option value="">No scenario</option>' + scenarios
                .map(item => {
                    const lifecycle = item.lifecycle || {};
                    const pending = lifecycle.pending_changes ? ' *draft' : '';
                    return `<option value="${item.scenario_id}">${item.name} (${item.scenario_id})${item.enabled ? '' : ' [disabled]'}${pending}</option>`;
                })
                .join('');
            if (current && scenarios.some(item => item.scenario_id === current)) {
                select.value = current;
            }
            const selected = scenarios.find(item => item.scenario_id === select.value);
            applyScenarioToEditor(selected || null);
        }
        renderReportingScenarioOptions();
        renderOnlineKpiSelectors();
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
    await ApiClient.request(url, { method, headers: { 'Content-Type': 'application/json', ...getOperatorHeaders() }, body: JSON.stringify(payload) });
    await loadScenarios();
    document.getElementById('scenario-select').value = scenarioId;
    loadDecisionContext();
}

async function deleteScenario() {
    const scenarioId = (document.getElementById('scenario-id').value || '').trim();
    if (!scenarioId) {
        throw new Error('Select a scenario first');
    }
    await ApiClient.del(`/api/scenarios/${encodeURIComponent(scenarioId)}`);
    await loadScenarios();
    document.getElementById('scenario-select').value = '';
    applyScenarioToEditor(null);
    loadDecisionContext();
}

async function publishScenario() {
    const scenarioId = (document.getElementById('scenario-id').value || '').trim();
    if (!scenarioId) {
        throw new Error('Select a scenario first');
    }
    const response = await fetch(`/api/scenarios/${encodeURIComponent(scenarioId)}/publish`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...getOperatorHeaders() },
        body: JSON.stringify({ actor_id: getOperatorId() || undefined })
    });
    const payload = await response.json();
    if (!response.ok) {
        if (response.status === 409 && payload.guard_evaluation) {
            const failed = (payload.guard_evaluation.checks || []).filter(item => !item.pass);
            const details = failed.map(item => `${item.name}: ${item.detail}`).join(' | ');
            throw new Error(`Publish blocked by guardrails. ${details || 'Fix scenario constraints.'}`);
        }
        throw new Error(payload.error || 'Failed to publish scenario');
    }
    await loadScenarios();
    document.getElementById('scenario-select').value = scenarioId;
    const selected = scenarios.find(item => item.scenario_id === scenarioId) || null;
    applyScenarioToEditor(selected);
    loadDecisionContext();
    setRuleBuilderStatus(`Published scenario ${scenarioId} (v${payload.published_version}).`);
}

async function rollbackScenario() {
    const scenarioId = (document.getElementById('scenario-id').value || '').trim();
    if (!scenarioId) {
        throw new Error('Select a scenario first');
    }
    const targetVersionRaw = (document.getElementById('scenario-version-select')?.value || '').trim();
    const targetVersion = targetVersionRaw ? Number(targetVersionRaw) : undefined;
    const response = await fetch(`/api/scenarios/${encodeURIComponent(scenarioId)}/rollback`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...getOperatorHeaders() },
        body: JSON.stringify({
            actor_id: getOperatorId() || undefined,
            target_version: Number.isFinite(targetVersion) ? targetVersion : undefined
        })
    });
    const payload = await response.json();
    if (!response.ok) {
        throw new Error(payload.error || 'Failed to rollback scenario');
    }
    await loadScenarios();
    document.getElementById('scenario-select').value = scenarioId;
    const selected = scenarios.find(item => item.scenario_id === scenarioId) || null;
    applyScenarioToEditor(selected);
    loadDecisionContext();
    setRuleBuilderStatus(`Rolled back scenario ${scenarioId} to published v${payload.rolled_back_to_version}.`);
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
    document.getElementById('rule-min-freshness').value =
        rules.min_freshness === null || rules.min_freshness === undefined ? '' : Number(rules.min_freshness);
    document.getElementById('rule-max-per-source').value =
        rules.max_per_source === null || rules.max_per_source === undefined ? '' : Number(rules.max_per_source);
    document.getElementById('rule-max-per-topic').value =
        rules.max_per_topic === null || rules.max_per_topic === undefined ? '' : Number(rules.max_per_topic);
    document.getElementById('rule-max-per-section').value =
        rules.max_per_section === null || rules.max_per_section === undefined ? '' : Number(rules.max_per_section);
    document.getElementById('rule-recent-boost-days').value = Number(rules.recent_boost_days ?? 0);
    document.getElementById('rule-recent-boost-factor').value = Number(rules.recent_boost_factor ?? 1.0);
    document.getElementById('rule-dedup-by-title').checked = Boolean(rules.dedup_by_title);
    document.getElementById('rule-dedup-by-url').checked = Boolean(rules.dedup_by_url);
    document.getElementById('rule-ranking-config-id').value = rules.ranking_config_id || '';
    document.getElementById('rule-source-boosts-json').value = JSON.stringify(rules.source_boosts || {}, null, 2);
}

function collectRuleBuilderRuleSet() {
    const maxAgeRaw = document.getElementById('rule-max-age-days').value;
    const minScoreRaw = document.getElementById('rule-min-score').value;
    const minFreshnessRaw = document.getElementById('rule-min-freshness').value;
    const maxPerSourceRaw = document.getElementById('rule-max-per-source').value;
    const maxPerTopicRaw = document.getElementById('rule-max-per-topic').value;
    const maxPerSectionRaw = document.getElementById('rule-max-per-section').value;
    const recentBoostDaysRaw = document.getElementById('rule-recent-boost-days').value;
    const recentBoostFactorRaw = document.getElementById('rule-recent-boost-factor').value;
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
    const minFreshness = minFreshnessRaw === '' ? null : Number(minFreshnessRaw);
    if (minFreshness !== null && (!Number.isFinite(minFreshness) || minFreshness < 0 || minFreshness > 1)) {
        throw new Error('Rule min freshness must be between 0 and 1.');
    }
    const parseOptionalCap = (raw, label) => {
        if (raw === '') return null;
        const parsed = Number(raw);
        if (!Number.isFinite(parsed) || parsed < 1) {
            throw new Error(`${label} must be >= 1.`);
        }
        return Math.round(parsed);
    };
    const maxPerSource = parseOptionalCap(maxPerSourceRaw, 'Rule max per source');
    const maxPerTopic = parseOptionalCap(maxPerTopicRaw, 'Rule max per topic');
    const maxPerSection = parseOptionalCap(maxPerSectionRaw, 'Rule max per section');
    const recentBoostDays = recentBoostDaysRaw === '' ? 0 : Number(recentBoostDaysRaw);
    if (!Number.isFinite(recentBoostDays) || recentBoostDays < 0) {
        throw new Error('Rule recent boost days must be >= 0.');
    }
    const recentBoostFactor = recentBoostFactorRaw === '' ? 1.0 : Number(recentBoostFactorRaw);
    if (!Number.isFinite(recentBoostFactor) || recentBoostFactor < 0.5 || recentBoostFactor > 5) {
        throw new Error('Rule recent boost factor must be between 0.5 and 5.');
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
        min_freshness: minFreshness,
        max_per_source: maxPerSource,
        max_per_topic: maxPerTopic,
        max_per_section: maxPerSection,
        recent_boost_days: Math.round(recentBoostDays),
        recent_boost_factor: recentBoostFactor,
        dedup_by_title: Boolean(document.getElementById('rule-dedup-by-title').checked),
        dedup_by_url: Boolean(document.getElementById('rule-dedup-by-url').checked),
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
    const baseRows = (payload.base_top || []).map((item, idx) => `
        <tr>
            <td>${idx + 1}</td>
            <td>${item.article_id || 'n/a'}</td>
            <td>${item.source || 'n/a'}</td>
            <td>${Number(item.score || 0).toFixed(4)}</td>
        </tr>
    `).join('');
    const scenarioRows = (payload.scenario_top || []).map((item, idx) => `
        <tr>
            <td>${idx + 1}</td>
            <td>${item.article_id || 'n/a'}</td>
            <td>${item.source || 'n/a'}</td>
            <td>${Number(item.score || 0).toFixed(4)}</td>
        </tr>
    `).join('');
    output.innerHTML = `
        <div><strong>Base:</strong> ${payload.base_count} | <strong>After scenario:</strong> ${payload.scenario_count}</div>
        <div><strong>Filtered out:</strong> ${trace.filtered_out ?? 0}</div>
        <div><strong>Reasons:</strong> <code>${JSON.stringify(trace.reasons || {})}</code></div>
        <div class="row g-2 mt-2">
            <div class="col-md-6">
                <div class="small fw-semibold mb-1">Before Scenario</div>
                <div class="table-responsive">
                    <table class="table table-sm mb-0">
                        <thead><tr><th>#</th><th>Article</th><th>Source</th><th>Score</th></tr></thead>
                        <tbody>${baseRows || '<tr><td colspan="4" class="text-muted">No base items.</td></tr>'}</tbody>
                    </table>
                </div>
            </div>
            <div class="col-md-6">
                <div class="small fw-semibold mb-1">After Scenario</div>
                <div class="table-responsive">
                    <table class="table table-sm mb-0">
                        <thead><tr><th>#</th><th>Article</th><th>Source</th><th>Score</th></tr></thead>
                        <tbody>${scenarioRows || '<tr><td colspan="4" class="text-muted">No scenario items.</td></tr>'}</tbody>
                    </table>
                </div>
            </div>
        </div>
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
        document.getElementById('threshold-max-source-top-share').value = Number(alertThresholds.max_source_top_share ?? 0.85);
        document.getElementById('threshold-max-stale-ratio').value = Number(alertThresholds.max_stale_ratio ?? 0.4);
        document.getElementById('threshold-min-ctr-lift').value = Number(alertThresholds.min_ctr_lift_vs_baseline ?? -0.05);
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
    const maxSourceTopShare = Number(document.getElementById('threshold-max-source-top-share').value);
    const maxStaleRatio = Number(document.getElementById('threshold-max-stale-ratio').value);
    const minCtrLiftVsBaseline = Number(document.getElementById('threshold-min-ctr-lift').value);
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
                min_ctr: minCtr,
                max_source_top_share: maxSourceTopShare,
                max_stale_ratio: maxStaleRatio,
                min_ctr_lift_vs_baseline: minCtrLiftVsBaseline
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

function renderRecommendationSurfaceMetrics(payload) {
    const summary = document.getElementById('surface-metrics-summary');
    const table = document.getElementById('surface-metrics-table');
    if (!summary || !table) return;
    const rec = payload.recommendation_api || {};
    const surfaces = rec.surfaces || [];
    summary.innerHTML = `
        <strong>Window:</strong> ${payload.window_days} days
        | <strong>Total runs:</strong> ${rec.runs ?? 0}
        | <strong>P95:</strong> ${rec.p95_duration_ms ?? 'n/a'} ms
        | <strong>Avg:</strong> ${rec.avg_duration_ms ?? 'n/a'} ms
    `;
    const rows = surfaces.map(item => `
        <tr>
            <td>${item.surface}</td>
            <td>${item.runs ?? 0}</td>
            <td>${(Number(item.share || 0) * 100).toFixed(1)}%</td>
            <td>${item.avg_duration_ms == null ? 'n/a' : Number(item.avg_duration_ms).toFixed(2)}</td>
            <td>${(Number(item.external_id_share || 0) * 100).toFixed(1)}%</td>
        </tr>
    `).join('');
    table.innerHTML = rows || '<tr><td colspan="5" class="text-muted">No recommendation runs in selected window.</td></tr>';
}

async function loadRecommendationSurfaceMetrics() {
    const summary = document.getElementById('surface-metrics-summary');
    const table = document.getElementById('surface-metrics-table');
    if (!summary || !table) return;
    try {
        const response = await fetch('/api/observability/overview?days=30');
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Failed to load observability overview');
        }
        const payload = await response.json();
        renderRecommendationSurfaceMetrics(payload);
    } catch (error) {
        summary.textContent = `Surface metrics unavailable: ${error.message}`;
        table.innerHTML = '<tr><td colspan="5" class="text-danger">Failed to load surface metrics.</td></tr>';
    }
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
        const payload = await ApiClient.get('/api/maintenance/cleanup/status');
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

async function loadApiProtectionStatus() {
    const container = document.getElementById('api-protection-status');
    if (!container) return;
    try {
        const payload = await ApiClient.get('/api/operations/api-protection-status');
        container.innerHTML = `
            <div>API key auth: <strong>${payload.api_auth_enabled ? 'enabled' : 'disabled'}</strong> (keys: ${payload.configured_api_key_count || 0})</div>
            <div>Request signature: <strong>${payload.api_signature_enabled ? 'enabled' : 'disabled'}</strong></div>
            <div>Rate limit: <strong>${payload.rate_limit_enabled ? 'enabled' : 'disabled'}</strong> (default ${payload.rate_limit_default_per_minute || 0}/min)</div>
            <div>Active buckets: ${payload.active_rate_limit_buckets || 0}</div>
            <div class="mt-1">Effective limits: CMS ${payload.effective_limits_preview?.recommendations_cms ?? 'n/a'}/min, events ${payload.effective_limits_preview?.events ?? 'n/a'}/min, configs ${payload.effective_limits_preview?.ranking_configs ?? 'n/a'}/min</div>
        `;
    } catch (error) {
        container.textContent = `API protection status unavailable: ${error.message}`;
    }
}

async function loadCdpConfig() {
    await getCdpControllerModule().loadCdpConfig(buildCdpControllerContext());
}

async function loadCdpMappingPresets() {
    await getCdpControllerModule().loadCdpMappingPresets(buildCdpControllerContext());
}

function applyCdpPresetToForm() {
    getCdpControllerModule().applyCdpPresetToForm(buildCdpControllerContext());
}

function exportCdpMappingJson() {
    getCdpControllerModule().exportCdpMappingJson();
}

function importCdpMappingJson() {
    getCdpControllerModule().importCdpMappingJson();
}

function _normalizeImportedCdpMapping(mapping) {
    return getCdpControllerModule().normalizeImportedCdpMapping(mapping);
}

function collectCdpMappingFromForm() {
    return getCdpControllerModule().collectCdpMappingFromForm();
}

async function saveCdpConfig() {
    await getCdpControllerModule().saveCdpConfig(buildCdpControllerContext());
}

async function loadCdpProfiles() {
    await getCdpControllerModule().loadCdpProfiles();
}

async function syncCdpProfiles() {
    await getCdpControllerModule().syncCdpProfiles(buildCdpControllerContext());
}

async function loadCdpSchedulerStatus() {
    await getCdpControllerModule().loadCdpSchedulerStatus();
}

async function runCdpSchedulerNow() {
    await getCdpControllerModule().runCdpSchedulerNow(buildCdpControllerContext());
}

async function loadCdpDiagnostics() {
    await getCdpControllerModule().loadCdpDiagnostics();
}

async function deriveCdpProfile(persist = false) {
    await getCdpControllerModule().deriveCdpProfile(persist, buildCdpControllerContext());
}

async function previewCdpMapping() {
    await getCdpControllerModule().previewCdpMapping(buildCdpControllerContext());
}

async function previewCdpFallback() {
    await getCdpControllerModule().previewCdpFallback(buildCdpControllerContext());
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
        const payload = await ApiClient.get('/api/metrics/rollups/daily', { query: { days } });
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

let rollupAsyncJobId = null;

async function loadEventsQueueStatus() {
    await getOperationsQueueModule().loadEventsQueueStatus({ ApiClient });
}

async function loadEventsQueueHealth() {
    await getOperationsQueueModule().loadEventsQueueHealth({ ApiClient });
}

async function enqueueEventsSample() {
    await getOperationsQueueModule().enqueueEventsSample({
        ApiClient,
        getOperatorHeaders,
        getOperatorId,
    });
}

async function controlEventsQueue(action) {
    await getOperationsQueueModule().controlEventsQueue(action, {
        ApiClient,
        getOperatorHeaders,
        getOperatorId,
    });
}

async function rebuildRollupsAsync() {
    const statusEl = document.getElementById('rollups-async-status');
    if (statusEl) statusEl.textContent = 'Queueing async rollup rebuild...';
    const daysRaw = Number(document.getElementById('rollups-days')?.value || 30);
    const days = Number.isFinite(daysRaw) ? Math.max(1, Math.min(365, Math.round(daysRaw))) : 30;
    const response = await fetch('/api/metrics/rollups/rebuild-async', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...getOperatorHeaders() },
        body: JSON.stringify({ days, actor_id: getOperatorId() || undefined })
    });
    const payload = await response.json();
    if (!response.ok) {
        throw new Error(payload.error || 'Failed to queue async rebuild');
    }
    rollupAsyncJobId = payload.job?.job_id || null;
    await loadRollupAsyncStatus();
}

async function loadRollupAsyncStatus() {
    const statusEl = document.getElementById('rollups-async-status');
    if (!statusEl || !rollupAsyncJobId) return;
    const response = await fetch(`/api/metrics/rollups/rebuild-async/${encodeURIComponent(rollupAsyncJobId)}`);
    const payload = await response.json();
    if (!response.ok) {
        throw new Error(payload.error || 'Failed to load async rollup status');
    }
    const job = payload.job || {};
    statusEl.innerHTML = `
        <div><strong>Job:</strong> <code>${job.job_id || 'n/a'}</code></div>
        <div><strong>Status:</strong> ${job.status || 'unknown'} | <strong>Days:</strong> ${job.days ?? 'n/a'}</div>
        <div><strong>Created:</strong> ${job.created_at || 'n/a'} | <strong>Updated:</strong> ${job.updated_at || 'n/a'}</div>
        ${job.error ? `<div class="text-danger"><strong>Error:</strong> ${job.error}</div>` : ''}
    `;
    if (job.status === 'completed' || job.status === 'failed') {
        if (job.status === 'completed') {
            await loadRollupsStatus();
        }
        rollupAsyncJobId = null;
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
    const summary = document.getElementById('decision-context-summary');
    const details = document.getElementById('decision-context-details');
    if (!container) return;
    try {
        const configId = document.getElementById('ranking-config')?.value || 'balanced';
        const selectedSources = getSelectedSources();
        const scenarioId = getSelectedScenarioId();
        const context = await ApiClient.post('/api/recommendation-context', {
            config_id: configId,
            sources: selectedSources,
            scenario_id: scenarioId || undefined
        });
        container.textContent = JSON.stringify(context, null, 2);
        const effectiveConfig = context.effective_config || {};
        const sourceWeights = effectiveConfig.source_weights || {};
        const sourceWeightEntries = Object.entries(sourceWeights);
        const scenario = context.scenario || {};
        const scenarioRuleSet = scenario.rule_set || {};
        const includeSources = scenarioRuleSet.include_sources || [];
        const excludeSources = scenarioRuleSet.exclude_sources || [];
        const includeSections = scenarioRuleSet.include_sections || [];
        const excludeSections = scenarioRuleSet.exclude_sections || [];
        const includeKeywords = scenarioRuleSet.include_keywords || [];
        const excludeKeywords = scenarioRuleSet.exclude_keywords || [];
        const scenarioEnabled = scenario && (scenario.enabled === true);
        const effectiveSources = context.effective_sources || selectedSources || [];
        const appliedConfigId = context.config_id || configId;
        if (summary) {
            summary.innerHTML = `
                Config <strong>${appliedConfigId}</strong>
                | Scenario <strong>${scenarioId || 'none'}</strong> (${scenarioEnabled ? 'enabled' : 'disabled/none'})
                | Sources <strong>${effectiveSources.length}</strong>
                | Source weights <strong>${sourceWeightEntries.length}</strong>
                | Max age <strong>${effectiveConfig.hard_max_age_days ?? 'n/a'}</strong> days
                | Min freshness <strong>${effectiveConfig.min_freshness ?? 'n/a'}</strong>
            `;
        }
        if (details) {
            const sourceBadges = effectiveSources.slice(0, 12).map(source => `<span class="badge text-bg-light border me-1 mb-1">${source}</span>`).join('');
            const weightsBadges = sourceWeightEntries
                .sort((a, b) => Number(b[1]) - Number(a[1]))
                .slice(0, 12)
                .map(([source, weight]) => `<span class="badge text-bg-light border me-1 mb-1">${source}: ${Number(weight).toFixed(2)}</span>`)
                .join('');
            details.innerHTML = `
                <div class="row g-2 mb-2">
                    <div class="col-md-6"><strong>Time decay (days):</strong> ${effectiveConfig.time_decay_days ?? 'n/a'}</div>
                    <div class="col-md-6"><strong>Recent boost:</strong> ${effectiveConfig.recent_boost_factor ?? 'n/a'} (${effectiveConfig.recent_boost_days ?? 'n/a'}d)</div>
                    <div class="col-md-6"><strong>Dedup title/URL:</strong> ${(effectiveConfig.dedup_by_title ? 'yes' : 'no')} / ${(effectiveConfig.dedup_by_url ? 'yes' : 'no')}</div>
                    <div class="col-md-6"><strong>Caps (source/topic/section):</strong> ${effectiveConfig.max_per_source ?? '-'} / ${effectiveConfig.max_per_topic ?? '-'} / ${effectiveConfig.max_per_section ?? '-'}</div>
                </div>
                <details class="mb-2">
                    <summary class="small">Effective sources</summary>
                    <div class="mt-1">${sourceBadges || '<span class="text-muted">No effective sources.</span>'}</div>
                </details>
                <details class="mb-2">
                    <summary class="small">Top source weights</summary>
                    <div class="mt-1">${weightsBadges || '<span class="text-muted">No source weights.</span>'}</div>
                </details>
                <details>
                    <summary class="small">Scenario rule summary</summary>
                    <div class="mt-1">
                        include sources ${includeSources.length}, exclude sources ${excludeSources.length},
                        include sections ${includeSections.length}, exclude sections ${excludeSections.length},
                        include keywords ${includeKeywords.length}, exclude keywords ${excludeKeywords.length}
                    </div>
                </details>
            `;
        }
    } catch (error) {
        if (summary) summary.textContent = `Failed to load decision context summary: ${error.message}`;
        if (details) details.textContent = `Failed to load decision context details: ${error.message}`;
        container.textContent = `Failed to load decision context: ${error.message}`;
    }
}

async function runBatchRecommendations() {
    const input = document.getElementById('batch-recommendation-requests');
    const output = document.getElementById('batch-recommendation-output');
    if (!input || !output) return;
    let requestsPayload = [];
    try {
        requestsPayload = JSON.parse(input.value || '[]');
    } catch (_error) {
        throw new Error('Invalid batch JSON payload');
    }
    if (!Array.isArray(requestsPayload) || !requestsPayload.length) {
        throw new Error('Batch payload must be a non-empty array');
    }
    output.textContent = 'Running batch...';
    const payload = await ApiClient.post('/api/recommendations/batch', {
        continue_on_error: Boolean(document.getElementById('batch-continue-on-error')?.checked),
        requests: requestsPayload
    });
    output.textContent = JSON.stringify(payload, null, 2);
}

function renderEmbeddingJobStatus(payload) {
    const status = document.getElementById('embedding-job-status');
    const result = document.getElementById('embedding-job-result');
    if (!status || !result) return;
    const state = payload.state || {};
    const statusLabel = state.running ? 'running' : (state.last_status || 'idle');
    status.innerHTML = `
        <strong>Status:</strong> ${statusLabel}
        | <strong>Current job:</strong> ${state.current_job_id || 'n/a'}
        | <strong>Last completed:</strong> ${state.last_completed_at || 'n/a'}
        | <strong>Duration:</strong> ${state.last_duration_ms ?? 'n/a'} ms
    `;
    const output = {
        state,
        config: payload.config || {}
    };
    result.textContent = JSON.stringify(output, null, 2);
}

async function loadEmbeddingConfig() {
    const status = document.getElementById('embedding-config-status');
    const modelSelect = document.getElementById('embedding-model-name');
    if (!status || !modelSelect) return;
    try {
        const response = await fetch('/api/embeddings/config');
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Failed to load embedding config');
        }
        const payload = await response.json();
        const allowed = payload.allowed_models || [];
        modelSelect.innerHTML = allowed.map(name => `<option value="${name}">${name}</option>`).join('');
        const cfg = payload.config || {};
        modelSelect.value = cfg.model_name || allowed[0] || '';
        document.getElementById('embedding-batch-size').value = Number(cfg.batch_size ?? 16);
        document.getElementById('embedding-max-length').value = Number(cfg.max_length ?? 512);
        document.getElementById('embedding-normalize').checked = Boolean(cfg.normalize_embeddings);
        document.getElementById('embedding-show-progress').checked = Boolean(cfg.show_progress_bar);
        status.textContent = `Loaded from ${payload.config_path || 'config file'}.`;
    } catch (error) {
        status.textContent = `Embedding config unavailable: ${error.message}`;
    }
}

async function saveEmbeddingConfig() {
    const status = document.getElementById('embedding-config-status');
    if (!status) return;
    status.textContent = 'Saving...';
    const response = await fetch('/api/embeddings/config', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', ...getOperatorHeaders() },
        body: JSON.stringify({
            config: {
                model_name: (document.getElementById('embedding-model-name')?.value || '').trim(),
                batch_size: Number(document.getElementById('embedding-batch-size')?.value || 16),
                max_length: Number(document.getElementById('embedding-max-length')?.value || 512),
                normalize_embeddings: Boolean(document.getElementById('embedding-normalize')?.checked),
                show_progress_bar: Boolean(document.getElementById('embedding-show-progress')?.checked)
            },
            actor_id: getOperatorId() || undefined
        })
    });
    if (!response.ok) {
        const error = await response.json();
        throw new Error(error.error || 'Failed to save embedding config');
    }
    await loadEmbeddingConfig();
    status.textContent = 'Embedding config saved.';
}

async function loadEmbeddingStatus() {
    const status = document.getElementById('embedding-job-status');
    if (!status) return;
    try {
        const response = await fetch('/api/embeddings/status');
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Failed to load embedding status');
        }
        const payload = await response.json();
        renderEmbeddingJobStatus(payload);
    } catch (error) {
        status.textContent = `Embedding status unavailable: ${error.message}`;
    }
}

async function runEmbeddingJob(forceUpdate = false) {
    const status = document.getElementById('embedding-job-status');
    if (status) status.textContent = forceUpdate ? 'Starting full re-embed...' : 'Starting incremental re-embed...';
    const response = await fetch('/api/embeddings/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...getOperatorHeaders() },
        body: JSON.stringify({ force_update: forceUpdate, actor_id: getOperatorId() || undefined })
    });
    if (!response.ok) {
        const error = await response.json();
        throw new Error(error.error || 'Failed to start embedding run');
    }
    await loadEmbeddingStatus();
}

async function loadEngineConfigSnapshot() {
    if (window.OperationsWorkspace && typeof window.OperationsWorkspace.loadEngineConfigSnapshot === 'function') {
        await window.OperationsWorkspace.loadEngineConfigSnapshot();
        return;
    }
    const container = document.getElementById('engine-config-snapshot');
    if (container) container.textContent = 'Engine snapshot module unavailable.';
}

function renderAuditLogs(payload) {
    // Backward compatible wrapper: delegate to Operations module.
    if (window.OperationsWorkspace && typeof window.OperationsWorkspace.loadAuditLogs === 'function') {
        window.OperationsWorkspace.loadAuditLogs().catch(() => {});
    }
}

async function loadAuditLogs() {
    if (window.OperationsWorkspace && typeof window.OperationsWorkspace.loadAuditLogs === 'function') {
        await window.OperationsWorkspace.loadAuditLogs();
        return;
    }
    const container = document.getElementById('audit-logs-list');
    if (container) container.textContent = 'Audit logs module unavailable.';
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
    getReportingDashboardModule().renderReportingWorkspace(payload, buildReportingDashboardContext());
}

function renderReportingAttribution(payload) {
    getReportingDashboardModule().renderReportingAttribution(payload, buildReportingDashboardContext());
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
                <td>${item.variant_id}${item.top_config_id ? `<div class="small text-muted">cfg: ${item.top_config_id}</div>` : ''}</td>
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

async function promoteExperimentCandidateVariant() {
    const variantId = document.getElementById('experiment-candidate')?.value || '';
    if (!variantId) {
        throw new Error('Select candidate variant first');
    }
    const days = Math.max(1, Math.min(365, Number(document.getElementById('reporting-days')?.value || 30)));
    const experimentId = reportingLastExperiments?.experiment_id || '';
    const response = await fetch('/api/metrics/experiments/promote-variant', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...getOperatorHeaders() },
        body: JSON.stringify({
            experiment_id: experimentId || undefined,
            variant_id: variantId,
            target_config_id: 'balanced',
            days,
            limit_runs: 5000,
            limit_events: 100000,
            actor_id: getOperatorId() || undefined
        })
    });
    const payload = await response.json();
    if (!response.ok) {
        throw new Error(payload.error || 'Failed to promote experiment variant');
    }
    const summary = document.getElementById('reporting-experiment-compare-summary');
    if (summary) {
        summary.textContent = `Promoted variant ${payload.variant_id} config ${payload.source_config_id} to ${payload.target_config_id} v${payload.target_version}.`;
    }
    await loadRankingConfigs();
    await loadReportingWorkspace();
}

function rolloutConfigOptionsHtml(selectedValue = '') {
    return getReportingRolloutsModule().rolloutConfigOptionsHtml(rankingConfigs, selectedValue);
}

function renderRolloutControls() {
    getReportingRolloutsModule().renderRolloutControls(buildRolloutsModuleContext());
}

async function loadRollouts() {
    await getReportingRolloutsModule().loadRollouts(buildRolloutsModuleContext());
}

function collectRolloutPayloadFromUi() {
    return getReportingRolloutsModule().collectRolloutPayloadFromUi(getOperatorId);
}

async function saveRollout() {
    await getReportingRolloutsModule().saveRollout(buildRolloutsModuleContext());
}

async function startSelectedRollout() {
    await getReportingRolloutsModule().startSelectedRollout(buildRolloutsModuleContext());
}

async function stopSelectedRollout() {
    await getReportingRolloutsModule().stopSelectedRollout(buildRolloutsModuleContext());
}

async function evaluateSelectedRollout() {
    await getReportingRolloutsModule().evaluateSelectedRollout(buildRolloutsModuleContext());
}

async function evaluateActiveRollouts() {
    await getReportingRolloutsModule().evaluateActiveRollouts(buildRolloutsModuleContext());
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

function renderConfigCompareSelectors() {
    const baseline = document.getElementById('config-compare-baseline');
    const candidate = document.getElementById('config-compare-candidate');
    if (!baseline || !candidate) return;
    const configs = Object.values(rankingConfigs || {});
    const options = configs.map(item => {
        const configId = item?.config?.config_id || '';
        const version = item?.version ?? 0;
        return `<option value="${configId}">${configId} (v${version})</option>`;
    }).join('');
    baseline.innerHTML = options || '<option value="">No configs</option>';
    candidate.innerHTML = options || '<option value="">No configs</option>';
    if (configs.length) {
        if (!baseline.value) baseline.value = 'balanced';
        if (!baseline.value) baseline.value = configs[0]?.config?.config_id || '';
        if (!candidate.value || candidate.value === baseline.value) {
            const alternative = configs.find(item => (item?.config?.config_id || '') !== baseline.value);
            candidate.value = alternative?.config?.config_id || baseline.value;
        }
    }
}

function renderOnlineKpiSelectors() {
    const baselineConfig = document.getElementById('online-kpi-baseline-config');
    if (baselineConfig) {
        const configs = Object.values(rankingConfigs || {});
        const options = configs.map(item => {
            const configId = item?.config?.config_id || '';
            const version = item?.version ?? 0;
            return `<option value="${configId}">${configId} (v${version})</option>`;
        }).join('');
        baselineConfig.innerHTML = options || '<option value="balanced">balanced</option>';
        if (!baselineConfig.value) baselineConfig.value = 'balanced';
        if (!baselineConfig.value && configs.length) baselineConfig.value = configs[0]?.config?.config_id || 'balanced';
    }

    const baselineScenario = document.getElementById('online-kpi-baseline-scenario');
    if (baselineScenario) {
        const current = baselineScenario.value || 'default';
        const scenarioOptions = ['<option value="default">default</option>']
            .concat((scenarios || []).map(item => `<option value="${item.scenario_id}">${item.name} (${item.scenario_id})</option>`));
        baselineScenario.innerHTML = scenarioOptions.join('');
        baselineScenario.value = current;
    }
}

function renderConfigCompareResult(payload) {
    reportingLastConfigCompare = payload;
    const summary = document.getElementById('reporting-config-compare-summary');
    const table = document.getElementById('reporting-config-compare-table');
    if (summary) {
        summary.innerHTML = `
            <strong>Runs:</strong> considered ${payload.runs_considered ?? 0}, evaluated ${payload.runs_evaluated ?? 0}
            | <strong>Skipped no relevant:</strong> ${payload.skipped_no_relevant ?? 0}
            | <strong>Baseline:</strong> ${payload.baseline_config_id}
            | <strong>Candidate:</strong> ${payload.candidate_config_id}
        `;
    }
    if (table) {
        const rows = (payload.deltas || []).map(item => `
            <tr>
                <td>${item.metric}</td>
                <td>${Number(item.baseline || 0).toFixed(6)}</td>
                <td>${Number(item.candidate || 0).toFixed(6)}</td>
                <td>${Number(item.delta || 0).toFixed(6)}</td>
                <td>${item.delta_pct == null ? 'n/a' : `${(Number(item.delta_pct) * 100).toFixed(2)}%`}</td>
            </tr>
        `).join('');
        table.innerHTML = rows || '<tr><td colspan="5" class="text-muted">No config comparison data.</td></tr>';
    }
}

function renderPromotionGuardResult(guardEvaluation) {
    const panel = document.getElementById('promotion-guard-result');
    if (!panel) return;
    if (!guardEvaluation || !Array.isArray(guardEvaluation.checks) || !guardEvaluation.checks.length) {
        panel.className = 'small mb-2 text-muted';
        panel.textContent = 'No guard evaluation yet.';
        return;
    }
    const failedCount = guardEvaluation.checks.filter(item => !item.pass).length;
    const toneClass = failedCount ? 'small mb-2 text-danger' : 'small mb-2 text-success';
    const title = failedCount
        ? `Guard checks failed (${failedCount}/${guardEvaluation.checks.length}).`
        : `All guard checks passed (${guardEvaluation.checks.length}/${guardEvaluation.checks.length}).`;
    const rows = guardEvaluation.checks.map((item) => {
        const status = item.pass ? 'PASS' : 'FAIL';
        const value = Number(item.value || 0).toFixed(4);
        const target = Number(item.target || 0).toFixed(4);
        return `<tr><td>${status}</td><td>${item.metric}</td><td>${value}</td><td>${item.operator}</td><td>${target}</td></tr>`;
    }).join('');
    panel.className = toneClass;
    const recommendations = Array.isArray(guardEvaluation.recommendations) ? guardEvaluation.recommendations : [];
    const recommendationsHtml = recommendations.length
        ? `<div class="mt-2"><strong>Recommended next steps:</strong><ul class="mb-0">${recommendations.map((item) => `<li>${item}</li>`).join('')}</ul></div>`
        : '';
    panel.innerHTML = `
        <div class="mb-1">${title}</div>
        <div class="table-responsive">
            <table class="table table-sm mb-0">
                <thead><tr><th>Status</th><th>Metric</th><th>Value</th><th>Rule</th><th>Target</th></tr></thead>
                <tbody>${rows}</tbody>
            </table>
        </div>
        ${recommendationsHtml}
    `;
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

async function runOfflineConfigCompare() {
    const baselineId = document.getElementById('config-compare-baseline')?.value || '';
    const candidateId = document.getElementById('config-compare-candidate')?.value || '';
    if (!baselineId || !candidateId) {
        throw new Error('Select baseline and candidate configs');
    }
    const days = Math.max(1, Math.min(365, Number(document.getElementById('reporting-days')?.value || 30)));
    const topN = Math.max(1, Math.min(20, Number(document.getElementById('config-compare-top-n')?.value || 5)));
    const limitRuns = Math.max(10, Math.min(5000, Number(document.getElementById('config-compare-limit-runs')?.value || 300)));
    const requireRelevant = Boolean(document.getElementById('config-compare-require-relevant')?.checked);
    const summary = document.getElementById('reporting-config-compare-summary');
    if (summary) summary.textContent = 'Running config comparison...';

    const params = new URLSearchParams({
        days: String(days),
        baseline_config_id: baselineId,
        candidate_config_id: candidateId,
        top_n: String(topN),
        limit_runs: String(limitRuns),
        require_relevant: requireRelevant ? 'true' : 'false'
    });
    const response = await fetch(`/api/metrics/offline/config-compare?${params.toString()}`);
    if (!response.ok) {
        const error = await response.json();
        throw new Error(error.error || 'Failed to compare ranking configs');
    }
    const payload = await response.json();
    renderConfigCompareResult(payload);
    renderPromotionGuardResult(null);
}

async function promoteCandidateConfig() {
    const sourceConfigId = document.getElementById('config-compare-candidate')?.value || '';
    if (!sourceConfigId) {
        throw new Error('Select candidate config to promote');
    }
    const response = await fetch('/api/ranking-configs/promote', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...getOperatorHeaders() },
        body: JSON.stringify({
            source_config_id: sourceConfigId,
            target_config_id: 'balanced',
            actor_id: getOperatorId() || undefined
        })
    });
    if (!response.ok) {
        const error = await response.json();
        throw new Error(error.error || 'Failed to promote config');
    }
    const payload = await response.json();
    const summary = document.getElementById('reporting-config-compare-summary');
    if (summary) summary.textContent = `Promoted ${payload.source_config_id} to ${payload.target_config_id} v${payload.target_version}.`;
    await loadRankingConfigs();
}

async function rollbackDefaultConfig() {
    const summary = document.getElementById('reporting-config-compare-summary');
    if (summary) summary.textContent = 'Rolling back default config...';
    const response = await fetch('/api/ranking-configs/rollback', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...getOperatorHeaders() },
        body: JSON.stringify({
            target_config_id: 'balanced',
            actor_id: getOperatorId() || undefined
        })
    });
    const payload = await response.json();
    if (!response.ok) {
        throw new Error(payload.error || 'Failed to rollback config');
    }
    if (summary) {
        summary.textContent = `Rolled back ${payload.target_config_id} to ${payload.source_config_id} (v${payload.target_version}).`;
    }
    await loadRankingConfigs();
    await loadOnlineKpis();
}

function renderOnlineKpiTables(payload) {
    reportingOnlineKpi = payload;
    const summary = document.getElementById('online-kpi-summary');
    const configTable = document.getElementById('online-kpi-config-table');
    const scenarioTable = document.getElementById('online-kpi-scenario-table');
    const alerts = document.getElementById('online-kpi-alerts');
    if (!summary || !configTable || !scenarioTable || !alerts) return;
    if (!reportingOnlineKpiSelectedConfig && (payload.by_config || []).length) {
        reportingOnlineKpiSelectedConfig = payload.by_config[0].key || '';
    }

    const s = payload.summary || {};
    summary.innerHTML = `
        <strong>Window:</strong> ${payload.window_days} days
        | <strong>Runs:</strong> ${s.runs_with_events ?? 0}/${s.runs ?? 0}
        | <strong>Impr:</strong> ${s.impressions ?? 0}
        | <strong>CTR:</strong> ${(Number(s.ctr || 0) * 100).toFixed(2)}%
        | <strong>CVR:</strong> ${(Number(s.conversion_rate || 0) * 100).toFixed(2)}%
        | <strong>Top source share:</strong> ${(Number(s.top_source_share || 0) * 100).toFixed(1)}%
        | <strong>Stale ratio:</strong> ${(Number(s.stale_ratio || 0) * 100).toFixed(1)}%
    `;

    const configRows = (payload.by_config || []).map(item => `
        <tr class="${reportingOnlineKpiSelectedConfig === item.key ? 'table-warning' : ''}">
            <td>
                <button class="btn btn-sm btn-link p-0 select-online-kpi-config" data-config="${item.key}">${item.key}</button>
            </td>
            <td>${item.impressions}</td>
            <td>${(Number(item.ctr || 0) * 100).toFixed(2)}%</td>
            <td>${item.ctr_lift_vs_baseline == null ? 'n/a' : `${(Number(item.ctr_lift_vs_baseline) * 100).toFixed(2)}%`}</td>
            <td>${item.ctr_confidence == null ? 'n/a' : `${(Number(item.ctr_confidence) * 100).toFixed(1)}%`}</td>
            <td>${(Number(item.conversion_rate || 0) * 100).toFixed(2)}%</td>
            <td>${(Number(item.top_source_share || 0) * 100).toFixed(1)}%</td>
            <td>${(Number(item.stale_ratio || 0) * 100).toFixed(1)}%</td>
        </tr>
    `).join('');
    configTable.innerHTML = configRows || '<tr><td colspan="8" class="text-muted">No config KPI rows.</td></tr>';

    const scenarioRows = (payload.by_scenario || []).map(item => `
        <tr>
            <td>${item.key}</td>
            <td>${item.impressions}</td>
            <td>${(Number(item.ctr || 0) * 100).toFixed(2)}%</td>
            <td>${item.ctr_lift_vs_baseline == null ? 'n/a' : `${(Number(item.ctr_lift_vs_baseline) * 100).toFixed(2)}%`}</td>
            <td>${item.ctr_confidence == null ? 'n/a' : `${(Number(item.ctr_confidence) * 100).toFixed(1)}%`}</td>
            <td>${(Number(item.top_source_share || 0) * 100).toFixed(1)}%</td>
            <td>${(Number(item.stale_ratio || 0) * 100).toFixed(1)}%</td>
        </tr>
    `).join('');
    scenarioTable.innerHTML = scenarioRows || '<tr><td colspan="7" class="text-muted">No scenario KPI rows.</td></tr>';

    const alertRows = (payload.alerts || []).map(item => `
        <span class="badge bg-danger me-2">${item.metric}: value ${Number(item.value || 0).toFixed(4)} vs threshold ${Number(item.threshold || 0).toFixed(4)}</span>
    `).join('');
    alerts.innerHTML = alertRows || '<span class="text-success">No KPI alerts in this window.</span>';
}

async function loadOnlineKpis() {
    const summary = document.getElementById('online-kpi-summary');
    if (!summary) return;
    const days = Math.max(1, Math.min(365, Number(document.getElementById('reporting-days')?.value || 30)));
    const baselineConfig = document.getElementById('online-kpi-baseline-config')?.value || 'balanced';
    const baselineScenario = document.getElementById('online-kpi-baseline-scenario')?.value || 'default';
    const staleFloor = Math.max(0, Math.min(1, Number(document.getElementById('online-kpi-stale-floor')?.value || 0.2)));
    summary.textContent = 'Loading online KPI metrics...';
    const params = new URLSearchParams({
        days: String(days),
        baseline_config_id: baselineConfig,
        baseline_scenario_id: baselineScenario,
        stale_freshness_floor: String(staleFloor),
        limit_runs: '1200',
        limit_events: '100000'
    });
    const response = await fetch(`/api/metrics/online-kpis?${params.toString()}`);
    if (!response.ok) {
        const error = await response.json();
        throw new Error(error.error || 'Failed to load online KPIs');
    }
    const payload = await response.json();
    renderOnlineKpiTables(payload);
}

async function promoteOnlineKpiCandidate() {
    if (!reportingOnlineKpiSelectedConfig) {
        throw new Error('Select a config row in Online KPI table first');
    }
    const summary = document.getElementById('reporting-config-compare-summary');
    if (summary) summary.textContent = `Promoting ${reportingOnlineKpiSelectedConfig} based on online KPI selection...`;
    const response = await fetch('/api/ranking-configs/promote', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...getOperatorHeaders() },
        body: JSON.stringify({
            source_config_id: reportingOnlineKpiSelectedConfig,
            target_config_id: 'balanced',
            actor_id: getOperatorId() || undefined
        })
    });
    const payload = await response.json();
    if (!response.ok) {
        throw new Error(payload.error || 'Failed to promote config from online KPI');
    }
    if (summary) summary.textContent = `Promoted ${payload.source_config_id} to ${payload.target_config_id} v${payload.target_version}.`;
    await loadRankingConfigs();
    await loadOnlineKpis();
}

function collectPromotionGuardFromUi() {
    return {
        min_ndcg_lift: Number(document.getElementById('guard-min-ndcg-lift')?.value || 0),
        min_ctr_lift: Number(document.getElementById('guard-min-ctr-lift')?.value || 0),
        max_precision_drop: Number(document.getElementById('guard-max-precision-drop')?.value || 0),
        max_recall_drop: Number(document.getElementById('guard-max-recall-drop')?.value || 0),
        max_mrr_drop: Number(document.getElementById('guard-max-mrr-drop')?.value || 0),
        min_source_coverage_at_k: Number(document.getElementById('guard-min-source-coverage')?.value || 0),
        min_section_coverage_at_k: Number(document.getElementById('guard-min-section-coverage')?.value || 0),
        min_avg_freshness: Number(document.getElementById('guard-min-avg-freshness')?.value || 0),
        max_top_source_share_at_k: Number(document.getElementById('guard-max-top-source-share')?.value || 1),
        max_stale_ratio_at_k: Number(document.getElementById('guard-max-stale-ratio')?.value || 1)
    };
}

function applyGuardPreset(presetName, persist = true) {
    const preset = GUARD_PRESETS[presetName];
    const select = document.getElementById('guard-preset');
    if (!preset || !select) return;
    select.value = presetName;
    const pairs = [
        ['guard-min-ndcg-lift', preset.min_ndcg_lift],
        ['guard-min-ctr-lift', preset.min_ctr_lift],
        ['guard-max-precision-drop', preset.max_precision_drop],
        ['guard-max-recall-drop', preset.max_recall_drop],
        ['guard-max-mrr-drop', preset.max_mrr_drop],
        ['guard-min-source-coverage', preset.min_source_coverage_at_k],
        ['guard-min-section-coverage', preset.min_section_coverage_at_k],
        ['guard-min-avg-freshness', preset.min_avg_freshness],
        ['guard-max-top-source-share', preset.max_top_source_share_at_k],
        ['guard-max-stale-ratio', preset.max_stale_ratio_at_k]
    ];
    pairs.forEach(([id, value]) => {
        const el = document.getElementById(id);
        if (el) el.value = Number(value).toFixed(3);
    });
    if (persist) localStorage.setItem(GUARD_PRESET_STORAGE_KEY, presetName);
}

function loadGuardPresetFromStorage() {
    const select = document.getElementById('guard-preset');
    if (!select) return;
    const stored = localStorage.getItem(GUARD_PRESET_STORAGE_KEY);
    const preset = GUARD_PRESETS[stored] ? stored : 'balanced';
    applyGuardPreset(preset, false);
    select.value = preset;
}

function markGuardPresetCustom() {
    const select = document.getElementById('guard-preset');
    if (!select) return;
    select.value = 'custom';
    localStorage.setItem(GUARD_PRESET_STORAGE_KEY, 'custom');
}

async function promoteWithGuard() {
    const baselineId = document.getElementById('config-compare-baseline')?.value || '';
    const candidateId = document.getElementById('config-compare-candidate')?.value || '';
    if (!baselineId || !candidateId) {
        throw new Error('Select baseline and candidate configs');
    }
    const days = Math.max(1, Math.min(365, Number(document.getElementById('reporting-days')?.value || 30)));
    const topN = Math.max(1, Math.min(20, Number(document.getElementById('config-compare-top-n')?.value || 5)));
    const limitRuns = Math.max(10, Math.min(5000, Number(document.getElementById('config-compare-limit-runs')?.value || 300)));
    const requireRelevant = Boolean(document.getElementById('config-compare-require-relevant')?.checked);
    const summary = document.getElementById('reporting-config-compare-summary');
    if (summary) summary.textContent = 'Evaluating promotion guard...';

    const response = await fetch('/api/ranking-configs/promote-with-guard', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...getOperatorHeaders() },
        body: JSON.stringify({
            baseline_config_id: baselineId,
            candidate_config_id: candidateId,
            target_config_id: 'balanced',
            days,
            top_n: topN,
            limit_runs: limitRuns,
            require_relevant: requireRelevant,
            guard: collectPromotionGuardFromUi(),
            actor_id: getOperatorId() || undefined
        })
    });
    const payload = await response.json();
    if (!response.ok) {
        if (response.status === 409) {
            renderConfigCompareResult(payload.comparison || {});
            renderPromotionGuardResult(payload.guard_evaluation || null);
            const failedChecks = (payload.guard_evaluation?.checks || []).filter(item => !item.pass);
            const msg = failedChecks
                .slice(0, 3)
                .map(item => `${item.metric}: ${item.value} ${item.operator} ${item.target}`)
                .join(' | ');
            if (summary) summary.textContent = `Guard blocked promotion: ${msg || 'threshold not met'}`;
            return;
        }
        throw new Error(payload.error || 'Failed guarded promotion');
    }
    renderConfigCompareResult(payload.comparison || {});
    renderPromotionGuardResult(payload.guard_evaluation || null);
    if (summary) summary.textContent = `Guard passed. Promoted ${payload.source_config_id} to ${payload.target_config_id} v${payload.target_version}.`;
    await loadRankingConfigs();
}

async function evaluatePromotionGuard() {
    const baselineId = document.getElementById('config-compare-baseline')?.value || '';
    const candidateId = document.getElementById('config-compare-candidate')?.value || '';
    if (!baselineId || !candidateId) {
        throw new Error('Select baseline and candidate configs');
    }
    const days = Math.max(1, Math.min(365, Number(document.getElementById('reporting-days')?.value || 30)));
    const topN = Math.max(1, Math.min(20, Number(document.getElementById('config-compare-top-n')?.value || 5)));
    const limitRuns = Math.max(10, Math.min(5000, Number(document.getElementById('config-compare-limit-runs')?.value || 300)));
    const requireRelevant = Boolean(document.getElementById('config-compare-require-relevant')?.checked);
    const summary = document.getElementById('reporting-config-compare-summary');
    if (summary) summary.textContent = 'Evaluating promotion guard (no promotion)...';

    const response = await fetch('/api/ranking-configs/guard-evaluate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...getOperatorHeaders() },
        body: JSON.stringify({
            baseline_config_id: baselineId,
            candidate_config_id: candidateId,
            days,
            top_n: topN,
            limit_runs: limitRuns,
            require_relevant: requireRelevant,
            guard: collectPromotionGuardFromUi(),
            actor_id: getOperatorId() || undefined
        })
    });
    const payload = await response.json();
    if (!response.ok) {
        throw new Error(payload.error || 'Failed to evaluate promotion guard');
    }
    renderConfigCompareResult(payload.comparison || {});
    renderPromotionGuardResult(payload.guard_evaluation || null);
    if (summary) {
        summary.textContent = payload.guard_evaluation?.passed
            ? 'Guard evaluation passed. Candidate is eligible for guarded promotion.'
            : 'Guard evaluation failed. Review failed checks and recommendations below.';
    }
}

async function autoTuneRankingConfig(apply = false) {
    const output = document.getElementById('autotune-output');
    if (!output) return;
    const configId = document.getElementById('ranking-config')?.value || '';
    if (!configId) {
        throw new Error('Select a ranking config first');
    }
    output.textContent = apply ? 'Applying auto-tune...' : 'Calculating auto-tune preview...';
    const response = await fetch(`/api/ranking-configs/${encodeURIComponent(configId)}/auto-tune`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...getOperatorHeaders() },
        body: JSON.stringify({
            days: Number(document.getElementById('autotune-days')?.value || 30),
            min_impressions: Number(document.getElementById('autotune-min-impressions')?.value || 50),
            learning_rate: Number(document.getElementById('autotune-learning-rate')?.value || 0.5),
            max_weight_delta: Number(document.getElementById('autotune-max-delta')?.value || 0.25),
            min_source_weight: Number(document.getElementById('autotune-min-weight')?.value || 0.5),
            max_source_weight: Number(document.getElementById('autotune-max-weight')?.value || 3.0),
            apply,
            actor_id: getOperatorId() || undefined
        })
    });
    if (!response.ok) {
        const error = await response.json();
        throw new Error(error.error || 'Failed to auto-tune config');
    }
    const result = await response.json();
    output.textContent = JSON.stringify(result, null, 2);
    if (result.applied) {
        await loadRankingConfigs();
    }
}

function selectedRankingLabContextIds() {
    const select = document.getElementById('lab-contexts');
    if (!select) return [];
    return Array.from(select.selectedOptions || []).map(option => option.value).filter(Boolean);
}

function renderRankingLabContexts() {
    const select = document.getElementById('lab-contexts');
    const countEl = document.getElementById('lab-context-count');
    if (!select) return;
    select.innerHTML = rankingLabContexts.map(ctx => {
        const sourceCount = (ctx.sources || []).length;
        const scenario = ctx.scenario_id ? ` | ${ctx.scenario_id}` : '';
        const createdAt = ctx.created_at || '';
        const label = `${ctx.label || ctx.effective_user_id || ctx.context_id} | sources:${sourceCount}${scenario} | ${createdAt}`;
        return `<option value="${ctx.context_id}">${label}</option>`;
    }).join('');
    if (countEl) countEl.textContent = `${rankingLabContexts.length} loaded`;
    if (rankingLabContexts.length) {
        const maxContexts = Math.max(1, Math.min(20, Number(document.getElementById('lab-context-limit')?.value || 10)));
        Array.from(select.options).forEach((option, idx) => {
            option.selected = idx < maxContexts;
        });
    }
}

async function loadRankingLabContexts() {
    const days = Math.max(1, Math.min(365, Number(document.getElementById('lab-window-days')?.value || 30)));
    const limit = Math.max(1, Math.min(50, Number(document.getElementById('lab-context-limit')?.value || 10)));
    const status = document.getElementById('lab-status');
    if (status) status.textContent = 'Loading sample contexts...';
    const response = await fetch(`/api/ranking-lab/contexts?days=${days}&limit=${limit}`);
    const payload = await response.json();
    if (!response.ok) {
        throw new Error(payload.error || 'Failed to load ranking lab contexts');
    }
    rankingLabContexts = payload.contexts || [];
    renderRankingLabContexts();
    if (status) status.textContent = `Loaded ${rankingLabContexts.length} contexts.`;
}

function formatLabItemDetails(item) {
    const contrib = item.feature_contributions || {};
    return `
        <div><strong>${item.title || item.article_id || 'n/a'}</strong></div>
        <div class="text-muted">Score ${Number(item.score || 0).toFixed(4)} | Source ${item.source || 'n/a'}</div>
        <div class="text-muted">Contrib: semantic ${formatContribution(contrib.semantic)}, freshness ${formatContribution(contrib.freshness)}, topic ${formatContribution(contrib.topic)}, source ${formatContribution(contrib.source)}</div>
        <div class="text-muted">${item.explanation || ''}</div>
    `;
}

function renderRankingLabComparison(payload) {
    rankingLabLastComparison = payload;
    const summary = document.getElementById('lab-summary');
    const deltas = document.getElementById('lab-deltas-table');
    const coverage = document.getElementById('lab-coverage-summary');
    const sideBySide = document.getElementById('lab-side-by-side');
    if (!payload || !deltas || !sideBySide) return;

    const overall = payload.overall || {};
    const deltaRows = (overall.deltas || []).map(row => `
        <tr>
            <td>${row.metric}</td>
            <td>${Number(row.baseline || 0).toFixed(6)}</td>
            <td>${Number(row.candidate || 0).toFixed(6)}</td>
            <td>${Number(row.delta || 0).toFixed(6)}</td>
            <td>${row.delta_pct == null ? 'n/a' : `${(Number(row.delta_pct) * 100).toFixed(2)}%`}</td>
        </tr>
    `).join('');
    deltas.innerHTML = deltaRows || '<tr><td colspan="5" class="text-muted">No metrics returned.</td></tr>';

    const contexts = payload.contexts || [];
    const coverageSummary = payload.coverage_summary || {};
    if (summary) {
        summary.innerHTML = `
            <strong>Baseline:</strong> ${payload.baseline_config_id}
            | <strong>Candidate:</strong> ${payload.candidate_config_id}
            | <strong>Runs evaluated:</strong> ${overall.runs_evaluated || 0}/${overall.runs_considered || 0}
            | <strong>Contexts shown:</strong> ${contexts.length}
        `;
    }
    if (coverage) {
        coverage.innerHTML = `
            <strong>Avg overlap@k:</strong> ${(Number(coverageSummary.avg_overlap_at_k || 0) * 100).toFixed(2)}%
            | <strong>Unique top articles:</strong> ${coverageSummary.unique_top_articles || 0}
        `;
    }

    sideBySide.innerHTML = contexts.map(ctx => {
        const baselineRows = (ctx.baseline?.recommendations || []).slice(0, 3).map(item => `<div class="mb-2">${formatLabItemDetails(item)}</div>`).join('');
        const candidateRows = (ctx.candidate?.recommendations || []).slice(0, 3).map(item => `<div class="mb-2">${formatLabItemDetails(item)}</div>`).join('');
        const baselineTrace = ctx.baseline?.scenario_trace || {};
        const candidateTrace = ctx.candidate?.scenario_trace || {};
        return `
            <div class="border rounded p-2 mb-2">
                <div class="small mb-2">
                    <strong>${ctx.label || ctx.context_id}</strong>
                    | overlap@k ${(Number(ctx.overlap_at_k || 0) * 100).toFixed(2)}%
                    ${ctx.seed_article_title ? `| seed ${ctx.seed_article_title}` : ''}
                </div>
                <div class="row g-2">
                    <div class="col-md-6">
                        <div class="small fw-semibold mb-1">Baseline (${ctx.baseline?.config_id || payload.baseline_config_id})</div>
                        <div class="small text-muted mb-1">Scenario filtered ${baselineTrace.filtered_out || 0} | remaining ${baselineTrace.remaining || 0}</div>
                        ${baselineRows || '<div class="text-muted small">No recommendations.</div>'}
                    </div>
                    <div class="col-md-6">
                        <div class="small fw-semibold mb-1">Candidate (${ctx.candidate?.config_id || payload.candidate_config_id})</div>
                        <div class="small text-muted mb-1">Scenario filtered ${candidateTrace.filtered_out || 0} | remaining ${candidateTrace.remaining || 0}</div>
                        ${candidateRows || '<div class="text-muted small">No recommendations.</div>'}
                    </div>
                </div>
            </div>
        `;
    }).join('') || '<div class="text-muted">No context rows.</div>';
}

async function runRankingLabCompare() {
    const status = document.getElementById('lab-status');
    if (status) status.textContent = 'Running comparison...';
    const payload = {
        baseline_config_id: document.getElementById('lab-baseline-config')?.value || 'balanced',
        candidate_config_id: document.getElementById('lab-candidate-config')?.value || '',
        days: Math.max(1, Math.min(365, Number(document.getElementById('lab-window-days')?.value || 30))),
        top_n: Math.max(1, Math.min(20, Number(document.getElementById('lab-top-n')?.value || 5))),
        limit_runs: Math.max(10, Math.min(5000, Number(document.getElementById('lab-limit-runs')?.value || 300))),
        max_contexts: Math.max(1, Math.min(20, Number(document.getElementById('lab-context-limit')?.value || 10))),
        require_relevant: Boolean(document.getElementById('lab-require-relevant')?.checked),
        context_ids: selectedRankingLabContextIds()
    };
    const response = await fetch('/api/ranking-lab/compare', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    });
    const result = await response.json();
    if (!response.ok) {
        throw new Error(result.error || 'Failed to run ranking lab compare');
    }
    renderRankingLabComparison(result);
    if (status) status.textContent = 'Comparison finished.';
}

async function loadRankingLabHistory() {
    const table = document.getElementById('lab-history-table');
    if (!table) return;
    const response = await fetch('/api/ranking-lab/evaluations?limit=30');
    const payload = await response.json();
    if (!response.ok) {
        table.innerHTML = `<tr><td colspan="8" class="text-danger">${payload.error || 'Failed to load history'}</td></tr>`;
        return;
    }
    rankingLabEvaluationsById = {};
    table.innerHTML = (payload.evaluations || []).map(item => {
        const meta = item.metadata || {};
        const metrics = item.metrics || {};
        rankingLabEvaluationsById[item.snapshot_id] = item;
        return `
            <tr>
                <td>${item.created_at || ''}</td>
                <td>${meta.label || '-'}</td>
                <td>${meta.baseline_config_id || '-'}</td>
                <td>${meta.candidate_config_id || '-'}</td>
                <td>${metrics.contexts_selected ?? '-'}</td>
                <td>${Number(metrics.delta_ndcg_at_k || 0).toFixed(6)}</td>
                <td>${Number(metrics.delta_historical_ctr || 0).toFixed(6)}</td>
                <td><button class="btn btn-sm btn-outline-secondary lab-load-evaluation" data-id="${item.snapshot_id}">Load</button></td>
            </tr>
        `;
    }).join('') || '<tr><td colspan="8" class="text-muted">No evaluations yet.</td></tr>';
}

async function saveRankingLabEvaluation() {
    const status = document.getElementById('lab-status');
    if (status) status.textContent = 'Saving evaluation...';
    const payload = {
        baseline_config_id: document.getElementById('lab-baseline-config')?.value || 'balanced',
        candidate_config_id: document.getElementById('lab-candidate-config')?.value || '',
        days: Math.max(1, Math.min(365, Number(document.getElementById('lab-window-days')?.value || 30))),
        top_n: Math.max(1, Math.min(20, Number(document.getElementById('lab-top-n')?.value || 5))),
        limit_runs: Math.max(10, Math.min(5000, Number(document.getElementById('lab-limit-runs')?.value || 300))),
        max_contexts: Math.max(1, Math.min(20, Number(document.getElementById('lab-context-limit')?.value || 10))),
        require_relevant: Boolean(document.getElementById('lab-require-relevant')?.checked),
        context_ids: selectedRankingLabContextIds(),
        label: (document.getElementById('lab-evaluation-label')?.value || '').trim(),
        actor_id: getOperatorId() || undefined
    };
    const response = await fetch('/api/ranking-lab/evaluations', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...getOperatorHeaders() },
        body: JSON.stringify(payload)
    });
    const result = await response.json();
    if (!response.ok) {
        throw new Error(result.error || 'Failed to save ranking lab evaluation');
    }
    if (result.comparison) renderRankingLabComparison(result.comparison);
    await loadRankingLabHistory();
    if (status) status.textContent = `Evaluation saved (${result.evaluation?.snapshot_id?.slice(0, 8) || 'ok'}).`;
}

function getRankingLabBookmarks() {
    try {
        const raw = localStorage.getItem(RANKING_LAB_BOOKMARKS_STORAGE_KEY);
        const parsed = raw ? JSON.parse(raw) : [];
        return Array.isArray(parsed) ? parsed : [];
    } catch (_error) {
        return [];
    }
}

function setRankingLabBookmarks(bookmarks) {
    localStorage.setItem(RANKING_LAB_BOOKMARKS_STORAGE_KEY, JSON.stringify(bookmarks || []));
}

function renderRankingLabBookmarks() {
    const select = document.getElementById('lab-bookmark-select');
    if (!select) return;
    const bookmarks = getRankingLabBookmarks();
    select.innerHTML = '<option value="">Saved sets</option>' + bookmarks.map((item) => (
        `<option value="${item.id}">${item.name} (${(item.context_ids || []).length})</option>`
    )).join('');
}

function saveRankingLabBookmark() {
    const nameInput = document.getElementById('lab-bookmark-name');
    const name = (nameInput?.value || '').trim();
    const contextIds = selectedRankingLabContextIds();
    if (!name) throw new Error('Bookmark name is required');
    if (!contextIds.length) throw new Error('Select at least one context');
    const bookmarks = getRankingLabBookmarks();
    const existingIdx = bookmarks.findIndex(item => item.name === name);
    const payload = {
        id: existingIdx >= 0 ? bookmarks[existingIdx].id : `set_${Date.now()}`,
        name,
        context_ids: contextIds,
        updated_at: new Date().toISOString()
    };
    if (existingIdx >= 0) {
        bookmarks[existingIdx] = payload;
    } else {
        bookmarks.unshift(payload);
    }
    setRankingLabBookmarks(bookmarks.slice(0, 20));
    renderRankingLabBookmarks();
}

function loadRankingLabBookmark() {
    const select = document.getElementById('lab-bookmark-select');
    const contextsEl = document.getElementById('lab-contexts');
    if (!select || !contextsEl) return;
    const bookmarkId = select.value;
    if (!bookmarkId) throw new Error('Choose a saved set');
    const bookmark = getRankingLabBookmarks().find(item => item.id === bookmarkId);
    if (!bookmark) throw new Error('Saved set not found');
    const ids = new Set(bookmark.context_ids || []);
    Array.from(contextsEl.options).forEach(option => {
        option.selected = ids.has(option.value);
    });
}

function deleteRankingLabBookmark() {
    const select = document.getElementById('lab-bookmark-select');
    if (!select) return;
    const bookmarkId = select.value;
    if (!bookmarkId) throw new Error('Choose a saved set');
    const bookmarks = getRankingLabBookmarks().filter(item => item.id !== bookmarkId);
    setRankingLabBookmarks(bookmarks);
    renderRankingLabBookmarks();
}

function collectRankingLabGuard() {
    return {
        min_ndcg_lift: Number(document.getElementById('lab-guard-min-ndcg')?.value || 0),
        min_ctr_lift: Number(document.getElementById('lab-guard-min-ctr')?.value || 0),
        max_precision_drop: Number(document.getElementById('lab-guard-max-precision-drop')?.value || 0),
        max_recall_drop: Number(document.getElementById('lab-guard-max-recall-drop')?.value || 0),
        max_mrr_drop: Number(document.getElementById('lab-guard-max-mrr-drop')?.value || 0)
    };
}

async function promoteRankingLabCandidate(guarded = false) {
    const status = document.getElementById('lab-status');
    const baselineId = document.getElementById('lab-baseline-config')?.value || '';
    const candidateId = document.getElementById('lab-candidate-config')?.value || '';
    if (!baselineId || !candidateId) throw new Error('Select baseline and candidate configs');
    if (status) status.textContent = guarded ? 'Running guarded promotion...' : 'Promoting candidate...';

    const body = {
        source_config_id: candidateId,
        target_config_id: 'balanced',
        actor_id: getOperatorId() || undefined
    };
    let endpoint = '/api/ranking-configs/promote';
    if (guarded) {
        endpoint = '/api/ranking-configs/promote-with-guard';
        body.baseline_config_id = baselineId;
        body.candidate_config_id = candidateId;
        body.days = Math.max(1, Math.min(365, Number(document.getElementById('lab-window-days')?.value || 30)));
        body.top_n = Math.max(1, Math.min(20, Number(document.getElementById('lab-top-n')?.value || 5)));
        body.limit_runs = Math.max(10, Math.min(5000, Number(document.getElementById('lab-limit-runs')?.value || 300)));
        body.require_relevant = Boolean(document.getElementById('lab-require-relevant')?.checked);
        body.guard = collectRankingLabGuard();
    }

    const response = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...getOperatorHeaders() },
        body: JSON.stringify(body)
    });
    const payload = await response.json();
    if (!response.ok) {
        if (response.status === 409 && guarded) {
            const failedChecks = (payload.guard_evaluation?.checks || []).filter(item => !item.pass);
            const failed = failedChecks.map(item => `${item.metric}: ${item.value} ${item.operator} ${item.target}`).join(' | ');
            throw new Error(`Guard blocked promotion. ${failed || 'thresholds not met'}`);
        }
        throw new Error(payload.error || 'Failed to promote candidate');
    }
    await loadRankingConfigs();
    if (status) status.textContent = `Promoted ${candidateId} to balanced v${payload.target_version || payload.version || 'n/a'}.`;
}

function exportRankingLabJson() {
    if (!rankingLabLastComparison) {
        throw new Error('Run comparison before export');
    }
    const blob = new Blob([JSON.stringify(rankingLabLastComparison, null, 2)], { type: 'application/json;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `ranking_lab_compare_${new Date().toISOString().slice(0, 10)}.json`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
}

function exportRankingLabCsv() {
    if (!rankingLabLastComparison) {
        throw new Error('Run comparison before export');
    }
    const rows = [['metric', 'baseline', 'candidate', 'delta', 'delta_pct']];
    ((rankingLabLastComparison.overall || {}).deltas || []).forEach(item => {
        rows.push([item.metric, item.baseline, item.candidate, item.delta, item.delta_pct]);
    });
    rows.push([]);
    rows.push(['context_id', 'label', 'overlap_at_k', 'baseline_top_article', 'candidate_top_article']);
    (rankingLabLastComparison.contexts || []).forEach(ctx => {
        const baselineTop = (ctx.baseline?.recommendations || [])[0]?.article_id || '';
        const candidateTop = (ctx.candidate?.recommendations || [])[0]?.article_id || '';
        rows.push([ctx.context_id, ctx.label, ctx.overlap_at_k, baselineTop, candidateTop]);
    });
    const csv = rows.map(row => row.map(toCsvCell).join(',')).join('\n');
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `ranking_lab_compare_${new Date().toISOString().slice(0, 10)}.csv`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
}

async function loadRankingLabEvaluation(snapshotId) {
    const status = document.getElementById('lab-status');
    if (status) status.textContent = 'Loading evaluation...';
    const response = await fetch(`/api/ranking-lab/evaluations/${encodeURIComponent(snapshotId)}`);
    const payload = await response.json();
    if (!response.ok) {
        throw new Error(payload.error || 'Failed to load evaluation');
    }
    const rehydrate = payload.rehydrate || {};
    const baseline = document.getElementById('lab-baseline-config');
    const candidate = document.getElementById('lab-candidate-config');
    if (baseline) baseline.value = rehydrate.baseline_config_id || baseline.value;
    if (candidate) candidate.value = rehydrate.candidate_config_id || candidate.value;
    const daysInput = document.getElementById('lab-window-days');
    const topNInput = document.getElementById('lab-top-n');
    const limitRunsInput = document.getElementById('lab-limit-runs');
    const requireInput = document.getElementById('lab-require-relevant');
    const labelInput = document.getElementById('lab-evaluation-label');
    if (daysInput) daysInput.value = Number(rehydrate.days || daysInput.value || 30);
    if (topNInput) topNInput.value = Number(rehydrate.top_n || topNInput.value || 5);
    if (limitRunsInput) limitRunsInput.value = Number(rehydrate.limit_runs || limitRunsInput.value || 300);
    if (requireInput) requireInput.checked = Boolean(rehydrate.require_relevant);
    if (labelInput) labelInput.value = rehydrate.label || '';

    await loadRankingLabContexts();
    const contextIds = new Set(rehydrate.context_ids || []);
    const contextsEl = document.getElementById('lab-contexts');
    if (contextsEl && contextIds.size) {
        Array.from(contextsEl.options).forEach(option => {
            option.selected = contextIds.has(option.value);
        });
    }
    await runRankingLabCompare();
    if (status) status.textContent = `Evaluation ${snapshotId.slice(0, 8)} loaded.`;
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
        if (hasElement('online-kpi-summary')) {
            try {
                await loadOnlineKpis();
            } catch (error) {
                const el = document.getElementById('online-kpi-summary');
                if (el) el.textContent = `Online KPI unavailable: ${error.message}`;
            }
        }
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
        const [stats, articleItems] = await Promise.all([
            ApiClient.get('/api/stats'),
            ApiClient.get('/api/articles').catch(() => [])
        ]);
        displayStats(stats, Array.isArray(articleItems) ? articleItems : []);
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
    getRecommendationsArticlesModule().displayArticles(buildRecommendationsArticlesContext());
}

function displayArticle(article) {
    getRecommendationsArticlesModule().displayArticle(article, buildRecommendationsArticlesContext());
}

function getSelectedSources() {
    return Array.from(document.querySelectorAll('.source-filter:checked')).map(cb => cb.value);
}

function buildCurrentRecommendationPayload() {
    return {
        user_id: 'demo_user',
        external_user_id: getExternalUserId() || undefined,
        user_reads: currentArticle?.article_id ? [currentArticle.article_id] : [],
        top_n: 5,
        config_id: document.getElementById('ranking-config')?.value || 'balanced',
        scenario_id: getSelectedScenarioId() || undefined,
        sources: getSelectedSources()
    };
}

async function copyCurrentRecommendationPayload() {
    const status = document.getElementById('query-payload-copy-status');
    const payload = buildCurrentRecommendationPayload();
    const serialized = JSON.stringify(payload, null, 2);
    try {
        await navigator.clipboard.writeText(serialized);
        if (status) status.textContent = 'Copied current query payload to clipboard.';
    } catch (_error) {
        if (status) status.textContent = 'Clipboard unavailable. Open browser permissions and retry.';
    }
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

        const responsePayload = await ApiClient.post('/api/recommendations/query', {
            user_id: 'demo_user',
            user_reads: [currentArticle.article_id],
            top_n: 5,
            sources: selectedSources,
            config_id: configId,
            scenario_id: scenarioId || undefined,
            external_user_id: externalUserId || undefined
        });
        const similarArticles = responsePayload.recommendations;
        if (!Array.isArray(similarArticles)) {
            throw new Error('Invalid response format');
        }
        const whyThisInput = document.getElementById('why-this-article-id');
        if (whyThisInput && !whyThisInput.value && similarArticles.length) {
            whyThisInput.value = similarArticles[0].article_id || '';
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
            const components = article.similarity_components || {};
            const details = article.explanation_details || {};
            const reasons = Array.isArray(details.reasons) ? details.reasons.join(', ') : '';
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
                        <small class="text-muted d-block mt-1">
                            Age: ${article.age_days == null ? 'n/a' : `${article.age_days}d`} | Topic cluster: ${article.topic_cluster ?? 'n/a'} | Section: ${article.section ?? 'n/a'}
                        </small>
                        <small class="text-muted d-block mt-1">${article.explanation || ''}</small>
                        <small class="text-muted d-block mt-1">Overall Score: ${(article.score * 100).toFixed(1)}%</small>
                        <details class="mt-2">
                            <summary class="small">Explainability details</summary>
                            <div class="small text-muted mt-1">
                                <div>Similarity components:</div>
                                <code>semantic=${formatContribution(components.semantic)} freshness=${formatContribution(components.freshness)} topic=${formatContribution(components.topic)} source=${formatContribution(components.source)}</code>
                                ${article.score_before_scenario != null ? `<div class="mt-1">Scenario score: ${formatContribution(article.score_before_scenario)} -> ${formatContribution(article.score)} (boost ${formatContribution(article.scenario_boost)})</div>` : ''}
                                ${reasons ? `<div class="mt-1">Reason tags: <code>${reasons}</code></div>` : ''}
                                <div class="mt-1">Config: <code>${article.config_id || 'n/a'}</code> | Scenario: <code>${article.scenario_id || 'none'}</code></div>
                            </div>
                        </details>
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

async function runWhyNotAnalysis() {
    const output = document.getElementById('why-not-output');
    if (!output) return;
    const articleId = (document.getElementById('why-not-article-id')?.value || '').trim();
    const configId = document.getElementById('ranking-config')?.value || 'balanced';
    const scenarioId = getSelectedScenarioId();
    const externalUserId = getExternalUserId();
    const userReads = currentArticle?.article_id ? [currentArticle.article_id] : [];
    output.textContent = 'Running why-not analysis...';
    const payload = await ApiClient.post('/api/recommendations/why-not', {
        user_id: 'demo_user',
        user_reads: userReads,
        top_n: 5,
        inspect_count: 60,
        sources: getSelectedSources(),
        config_id: configId,
        scenario_id: scenarioId || undefined,
        external_user_id: externalUserId || undefined,
        article_id: articleId || undefined,
    });
    output.textContent = JSON.stringify(payload, null, 2);
}

async function runWhyThisAnalysis() {
    const output = document.getElementById('why-this-output');
    if (!output) return;
    const articleId = (document.getElementById('why-this-article-id')?.value || '').trim();
    if (!articleId) {
        throw new Error('Article ID is required');
    }
    const configId = document.getElementById('ranking-config')?.value || 'balanced';
    const scenarioId = getSelectedScenarioId();
    const externalUserId = getExternalUserId();
    const userReads = currentArticle?.article_id ? [currentArticle.article_id] : [];
    output.textContent = 'Running why-this analysis...';
    const payload = await ApiClient.post('/api/recommendations/explain-item', {
        user_id: 'demo_user',
        user_reads: userReads,
        top_n: 5,
        inspect_count: 80,
        sources: getSelectedSources(),
        config_id: configId,
        scenario_id: scenarioId || undefined,
        external_user_id: externalUserId || undefined,
        article_id: articleId
    });
    output.textContent = JSON.stringify(payload, null, 2);
}

function formatContribution(value) {
    if (typeof value !== 'number') return 'n/a';
    return value.toFixed(3);
}

function displayStats(stats, articleItems = []) {
    if (window.RecommendationStatsView && typeof window.RecommendationStatsView.render === 'function') {
        window.RecommendationStatsView.render(stats, articleItems);
        return;
    }
    const statsContainer = document.getElementById('article-stats');
    if (statsContainer) statsContainer.textContent = 'Statistics view unavailable.';
}

function setupEventListeners() {
    const on = (id, event, handler) => {
        const el = document.getElementById(id);
        if (el) el.addEventListener(event, handler);
    };
    const articleList = document.getElementById('article-list');
    if (articleList) {
        articleList.addEventListener('click', (e) => {
            const selectButton = e.target.closest('.select-article-btn');
            if (!selectButton) return;
            e.preventDefault();
            selectArticleById(selectButton.dataset.id);
        });
    }
    on('article-search-input', 'input', (event) => {
        articleSearchTerm = (event.target.value || '').trim().toLowerCase();
        articleCurrentPage = 1;
        displayArticles();
    });
    on('article-source-select', 'change', (event) => {
        articleSourceFilter = event.target.value || 'all';
        articleCurrentPage = 1;
        displayArticles();
    });
    on('article-sort-select', 'change', (event) => {
        articleSortMode = event.target.value || 'newest';
        articleCurrentPage = 1;
        displayArticles();
    });
    on('article-page-size', 'change', (event) => {
        const parsed = Number(event.target.value || 20);
        articlePageSize = Number.isFinite(parsed) && parsed > 0 ? parsed : 20;
        articleCurrentPage = 1;
        displayArticles();
    });
    on('article-reset-filters', 'click', () => {
        articleSearchTerm = '';
        articleSourceFilter = 'all';
        articleSortMode = 'newest';
        articlePageSize = 20;
        articleCurrentPage = 1;
        const searchInput = document.getElementById('article-search-input');
        const sourceSelect = document.getElementById('article-source-select');
        const sortSelect = document.getElementById('article-sort-select');
        const sizeSelect = document.getElementById('article-page-size');
        if (searchInput) searchInput.value = '';
        if (sourceSelect) sourceSelect.value = 'all';
        if (sortSelect) sortSelect.value = 'newest';
        if (sizeSelect) sizeSelect.value = '20';
        displayArticles();
    });
    on('article-page-prev', 'click', () => {
        articleCurrentPage = Math.max(1, articleCurrentPage - 1);
        displayArticles();
    });
    on('article-page-next', 'click', () => {
        articleCurrentPage += 1;
        displayArticles();
    });

    on('show-similar', 'click', showSimilarArticles);
    on('copy-current-query-payload', 'click', async () => {
        try {
            await copyCurrentRecommendationPayload();
        } catch (error) {
            showError(error.message || 'Failed to copy current query payload');
        }
    });
    on('refresh-decision-context', 'click', loadDecisionContext);
    on('refresh-engine-snapshot', 'click', loadEngineConfigSnapshot);
    on('refresh-reporting-workspace', 'click', loadReportingWorkspace);
    on('export-reporting-csv', 'click', exportReportingCsv);
    on('reporting-days', 'change', loadReportingWorkspace);
    on('reporting-scenario-filter', 'change', loadReportingWorkspace);
    on('reporting-source-filter', 'change', loadReportingWorkspace);
    on('reporting-top-runs', 'change', loadReportingWorkspace);
    on('load-lab-contexts', 'click', async () => {
        try {
            await loadRankingLabContexts();
        } catch (error) {
            showError(error.message || 'Failed to load ranking lab contexts');
        }
    });
    on('run-lab-compare', 'click', async () => {
        try {
            await runRankingLabCompare();
        } catch (error) {
            showError(error.message || 'Failed to run ranking lab comparison');
        }
    });
    on('save-lab-evaluation', 'click', async () => {
        try {
            await saveRankingLabEvaluation();
        } catch (error) {
            showError(error.message || 'Failed to save ranking lab evaluation');
        }
    });
    on('refresh-lab-history', 'click', async () => {
        try {
            await loadRankingLabHistory();
        } catch (error) {
            showError(error.message || 'Failed to load ranking lab history');
        }
    });
    on('lab-history-table', 'click', async (event) => {
        const button = event.target.closest('.lab-load-evaluation');
        if (!button) return;
        try {
            await loadRankingLabEvaluation(button.dataset.id);
        } catch (error) {
            showError(error.message || 'Failed to load evaluation');
        }
    });
    on('save-lab-bookmark', 'click', () => {
        try {
            saveRankingLabBookmark();
        } catch (error) {
            showError(error.message || 'Failed to save context set');
        }
    });
    on('load-lab-bookmark', 'click', () => {
        try {
            loadRankingLabBookmark();
        } catch (error) {
            showError(error.message || 'Failed to load context set');
        }
    });
    on('delete-lab-bookmark', 'click', () => {
        try {
            deleteRankingLabBookmark();
        } catch (error) {
            showError(error.message || 'Failed to delete context set');
        }
    });
    on('lab-promote-candidate', 'click', async () => {
        try {
            await promoteRankingLabCandidate(false);
        } catch (error) {
            showError(error.message || 'Failed to promote candidate');
        }
    });
    on('lab-promote-guarded', 'click', async () => {
        try {
            await promoteRankingLabCandidate(true);
        } catch (error) {
            showError(error.message || 'Failed guarded promotion');
        }
    });
    on('export-lab-json', 'click', () => {
        try {
            exportRankingLabJson();
        } catch (error) {
            showError(error.message || 'Failed to export ranking lab JSON');
        }
    });
    on('export-lab-csv', 'click', () => {
        try {
            exportRankingLabCsv();
        } catch (error) {
            showError(error.message || 'Failed to export ranking lab CSV');
        }
    });
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
    on('run-config-compare', 'click', async () => {
        try {
            await runOfflineConfigCompare();
        } catch (error) {
            showError(error.message || 'Failed to compare ranking configs');
        }
    });
    on('rollout-select', 'change', (event) => {
        selectedRolloutId = event.target.value || '';
        renderRolloutControls();
    });
    on('rollout-table', 'click', (event) => {
        const row = event.target.closest('.rollout-row');
        if (!row) return;
        selectedRolloutId = row.dataset.rolloutId || '';
        const select = document.getElementById('rollout-select');
        if (select) select.value = selectedRolloutId;
        renderRolloutControls();
    });
    on('new-rollout', 'click', () => {
        selectedRolloutId = '';
        const select = document.getElementById('rollout-select');
        if (select) select.value = '';
        renderRolloutControls();
    });
    on('save-rollout', 'click', async () => {
        try {
            await saveRollout();
        } catch (error) {
            showError(error.message || 'Failed to save rollout');
        }
    });
    on('start-rollout', 'click', async () => {
        try {
            await startSelectedRollout();
        } catch (error) {
            showError(error.message || 'Failed to start rollout');
        }
    });
    on('stop-rollout', 'click', async () => {
        try {
            await stopSelectedRollout();
        } catch (error) {
            showError(error.message || 'Failed to stop rollout');
        }
    });
    on('evaluate-rollout', 'click', async () => {
        try {
            await evaluateSelectedRollout();
        } catch (error) {
            showError(error.message || 'Failed to evaluate rollout');
        }
    });
    on('evaluate-active-rollouts', 'click', async () => {
        try {
            await evaluateActiveRollouts();
        } catch (error) {
            showError(error.message || 'Failed to evaluate active rollouts');
        }
    });
    on('evaluate-promotion-guard', 'click', async () => {
        try {
            await evaluatePromotionGuard();
        } catch (error) {
            showError(error.message || 'Failed to evaluate guard');
        }
    });
    on('promote-candidate-config', 'click', async () => {
        try {
            await promoteCandidateConfig();
        } catch (error) {
            showError(error.message || 'Failed to promote config');
        }
    });
    on('promote-with-guard', 'click', async () => {
        try {
            await promoteWithGuard();
        } catch (error) {
            showError(error.message || 'Failed guarded promotion');
        }
    });
    on('rollback-default-config', 'click', async () => {
        try {
            await rollbackDefaultConfig();
        } catch (error) {
            showError(error.message || 'Failed to rollback config');
        }
    });
    on('refresh-online-kpis', 'click', async () => {
        try {
            await loadOnlineKpis();
        } catch (error) {
            showError(error.message || 'Failed to load online KPIs');
        }
    });
    on('promote-online-kpi-candidate', 'click', async () => {
        try {
            await promoteOnlineKpiCandidate();
        } catch (error) {
            showError(error.message || 'Failed to promote from online KPI');
        }
    });
    on('online-kpi-baseline-config', 'change', loadOnlineKpis);
    on('online-kpi-baseline-scenario', 'change', loadOnlineKpis);
    on('online-kpi-stale-floor', 'change', loadOnlineKpis);
    on('online-kpi-config-table', 'click', (event) => {
        const button = event.target.closest('.select-online-kpi-config');
        if (!button) return;
        reportingOnlineKpiSelectedConfig = button.dataset.config || '';
        renderOnlineKpiTables(reportingOnlineKpi || { by_config: [], by_scenario: [], summary: {}, alerts: [] });
    });
    on('apply-guard-preset', 'click', () => {
        const preset = document.getElementById('guard-preset')?.value || 'balanced';
        if (preset === 'custom') return;
        applyGuardPreset(preset, true);
    });
    on('guard-preset', 'change', (event) => {
        const preset = event.target.value || 'balanced';
        if (preset === 'custom') {
            localStorage.setItem(GUARD_PRESET_STORAGE_KEY, 'custom');
            return;
        }
        applyGuardPreset(preset, true);
    });
    [
        'guard-min-ndcg-lift',
        'guard-min-ctr-lift',
        'guard-max-precision-drop',
        'guard-max-recall-drop',
        'guard-max-mrr-drop',
        'guard-min-source-coverage',
        'guard-min-section-coverage',
        'guard-min-avg-freshness',
        'guard-max-top-source-share',
        'guard-max-stale-ratio'
    ].forEach((id) => on(id, 'input', markGuardPresetCustom));
    on('compare-experiment-variants', 'click', async () => {
        try {
            await compareExperimentVariants();
        } catch (error) {
            showError(error.message || 'Failed to compare experiment variants');
        }
    });
    on('promote-experiment-candidate', 'click', async () => {
        try {
            await promoteExperimentCandidateVariant();
        } catch (error) {
            showError(error.message || 'Failed to promote experiment candidate');
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
    on('preview-autotune', 'click', async () => {
        try {
            await autoTuneRankingConfig(false);
        } catch (error) {
            showError(error.message || 'Failed to preview auto-tune');
        }
    });
    on('apply-autotune', 'click', async () => {
        try {
            await autoTuneRankingConfig(true);
        } catch (error) {
            showError(error.message || 'Failed to apply auto-tune');
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
    on('refresh-api-protection', 'click', loadApiProtectionStatus);
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
    on('publish-scenario', 'click', async () => {
        try {
            await publishScenario();
            await loadScenarioMetrics();
            await loadScenarioSourceMetrics();
        } catch (error) {
            showError(error.message || 'Failed to publish scenario');
        }
    });
    on('rollback-scenario', 'click', async () => {
        try {
            await rollbackScenario();
            await loadScenarioMetrics();
            await loadScenarioSourceMetrics();
        } catch (error) {
            showError(error.message || 'Failed to rollback scenario');
        }
    });
    on('refresh-scenarios', 'click', loadScenarios);
    on('refresh-scenario-versions', 'click', async () => {
        try {
            const scenarioId = (document.getElementById('scenario-id')?.value || '').trim();
            await loadScenarioVersions(scenarioId);
        } catch (error) {
            showError(error.message || 'Failed to refresh scenario versions');
        }
    });
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
    on('refresh-surface-metrics', 'click', loadRecommendationSurfaceMetrics);
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
    on('refresh-events-queue', 'click', async () => {
        await loadEventsQueueStatus();
        await loadEventsQueueHealth();
    });
    on('rollups-days', 'change', loadRollupsStatus);
    on('rebuild-rollups', 'click', async () => {
        try {
            await rebuildRollups();
            if (hasElement('reporting-summary')) await loadReportingWorkspace();
        } catch (error) {
            showError(error.message || 'Failed to rebuild rollups');
        }
    });
    on('rebuild-rollups-async', 'click', async () => {
        try {
            await rebuildRollupsAsync();
        } catch (error) {
            showError(error.message || 'Failed to queue async rollup rebuild');
        }
    });
    on('enqueue-events-sample', 'click', async () => {
        try {
            await enqueueEventsSample();
        } catch (error) {
            showError(error.message || 'Failed to enqueue sample events');
        }
    });
    on('enable-events-queue', 'click', async () => {
        try {
            await controlEventsQueue('enable');
        } catch (error) {
            showError(error.message || 'Failed to enable events queue');
        }
    });
    on('disable-events-queue', 'click', async () => {
        try {
            await controlEventsQueue('disable');
        } catch (error) {
            showError(error.message || 'Failed to disable events queue');
        }
    });
    on('drain-events-queue', 'click', async () => {
        try {
            await controlEventsQueue('drain');
        } catch (error) {
            showError(error.message || 'Failed to drain events queue');
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
    on('apply-cdp-preset', 'click', () => {
        try {
            applyCdpPresetToForm();
        } catch (error) {
            showError(error.message || 'Failed to apply CDP preset');
        }
    });
    on('export-cdp-mapping', 'click', () => {
        try {
            exportCdpMappingJson();
        } catch (error) {
            showError(error.message || 'Failed to export CDP mapping');
        }
    });
    on('import-cdp-mapping', 'click', () => {
        try {
            importCdpMappingJson();
        } catch (error) {
            showError(error.message || 'Failed to import CDP mapping');
        }
    });
    on('preview-cdp-mapping', 'click', async () => {
        try {
            await previewCdpMapping();
        } catch (error) {
            showError(error.message || 'Failed to preview CDP mapping');
        }
    });
    on('cdp-preview-payload', 'input', () => {
        try {
            getCdpControllerModule().validatePreviewPayloadInput();
        } catch (_error) {}
    });
    on('preview-cdp-fallback', 'click', async () => {
        try {
            await previewCdpFallback();
        } catch (error) {
            showError(error.message || 'Failed to preview CDP fallback');
        }
    });
    on('run-why-not', 'click', async () => {
        try {
            await runWhyNotAnalysis();
        } catch (error) {
            showError(error.message || 'Failed to run why-not analysis');
            const output = document.getElementById('why-not-output');
            if (output) output.textContent = error.message || 'Why-not analysis failed';
        }
    });
    on('run-why-this', 'click', async () => {
        try {
            await runWhyThisAnalysis();
        } catch (error) {
            showError(error.message || 'Failed to run why-this analysis');
            const output = document.getElementById('why-this-output');
            if (output) output.textContent = error.message || 'Why-this analysis failed';
        }
    });
    on('run-batch-recommendations', 'click', async () => {
        try {
            await runBatchRecommendations();
        } catch (error) {
            showError(error.message || 'Failed to run batch recommendations');
        }
    });
    on('refresh-embedding-config', 'click', loadEmbeddingConfig);
    on('save-embedding-config', 'click', async () => {
        try {
            await saveEmbeddingConfig();
        } catch (error) {
            showError(error.message || 'Failed to save embedding config');
        }
    });
    on('refresh-embedding-status', 'click', loadEmbeddingStatus);
    on('run-embedding-incremental', 'click', async () => {
        try {
            await runEmbeddingJob(false);
        } catch (error) {
            showError(error.message || 'Failed to run incremental embedding');
        }
    });
    on('run-embedding-full', 'click', async () => {
        try {
            await runEmbeddingJob(true);
        } catch (error) {
            showError(error.message || 'Failed to run full embedding');
        }
    });
    on('refresh-audit-logs', 'click', loadAuditLogs);
    on('audit-actor-filter', 'change', loadAuditLogs);
    on('audit-resource-filter', 'change', loadAuditLogs);
}

function refreshArticleSourceFilterOptions() {
    getRecommendationsArticlesModule().refreshArticleSourceFilterOptions(buildRecommendationsArticlesContext());
}

function selectArticleById(articleId) {
    getRecommendationsArticlesModule().selectArticleById(articleId, buildRecommendationsArticlesContext());
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
