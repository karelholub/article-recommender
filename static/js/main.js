// Global state
let currentArticle = null;
let articles = [];
let sourceOptions = [];
let rankingConfigs = {};
let connectors = [];

// Initialize the application
document.addEventListener('DOMContentLoaded', () => {
    loadArticles();
    loadStats();
    loadSources();
    loadRankingConfigs();
    loadOfflineMetrics();
    loadConnectors();
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
    } catch (error) {
        console.error('Error loading connectors:', error);
        document.getElementById('connector-list').innerHTML = '<span>Connectors unavailable</span>';
    }
}

function renderConnectors() {
    const container = document.getElementById('connector-list');
    if (!connectors.length) {
        container.innerHTML = '<span>No connectors configured.</span>';
        return;
    }

    container.innerHTML = connectors.map(connector => `
        <div class="border rounded p-2 mb-2">
            <div class="fw-semibold">${connector.name}</div>
            <div class="text-muted">${connector.connector_type}</div>
            <div class="text-muted small">${connector.config?.base_url || connector.config?.feed_url || 'n/a'}</div>
            <div class="d-flex gap-2 mt-2">
                <button class="btn btn-sm btn-outline-secondary connector-sync" data-id="${connector.connector_id}">Sync</button>
                <button class="btn btn-sm btn-outline-warning connector-toggle" data-id="${connector.connector_id}" data-enabled="${connector.enabled}">
                    ${connector.enabled ? 'Disable' : 'Enable'}
                </button>
                <button class="btn btn-sm btn-outline-danger connector-delete" data-id="${connector.connector_id}">Delete</button>
            </div>
            ${connector.last_run_at ? `<div class="small text-muted mt-1">Last sync: ${connector.last_run_at}</div>` : ''}
        </div>
    `).join('');
}

async function createConnector() {
    const name = document.getElementById('connector-name').value.trim();
    const connectorType = document.getElementById('connector-type').value;
    const url = document.getElementById('connector-url').value.trim();

    if (!name || !url) {
        showError('Connector name and URL are required');
        return;
    }

    const config = connectorType === 'rss' ? { feed_url: url } : { base_url: url };
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
    await loadConnectors();
}

async function handleConnectorAction(event) {
    const syncBtn = event.target.closest('.connector-sync');
    const toggleBtn = event.target.closest('.connector-toggle');
    const deleteBtn = event.target.closest('.connector-delete');

    if (!syncBtn && !toggleBtn && !deleteBtn) return;

    try {
        if (syncBtn) {
            const id = syncBtn.dataset.id;
            const response = await fetch(`/api/connectors/${encodeURIComponent(id)}/sync`, { method: 'POST' });
            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.error || 'Failed to sync connector');
            }
        }

        if (toggleBtn) {
            const id = toggleBtn.dataset.id;
            const currentlyEnabled = toggleBtn.dataset.enabled === 'true';
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
    } catch (error) {
        console.error('Error loading ranking configs:', error);
        document.getElementById('ranking-config').innerHTML = '<option value="balanced">balanced</option>';
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
                config_id: configId
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
            `<div class="alert alert-secondary py-2">Run ID: <code>${responsePayload.run_id}</code></div>`
        );
        loadOfflineMetrics();
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
    document.getElementById('save-source-settings').addEventListener('click', saveSourceSettings);
    document.getElementById('create-connector').addEventListener('click', async () => {
        try {
            await createConnector();
        } catch (error) {
            showError(error.message || 'Failed to create connector');
        }
    });
    document.getElementById('connector-list').addEventListener('click', handleConnectorAction);
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
