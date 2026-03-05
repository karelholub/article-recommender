(function initConnectorsControllerModule(globalScope) {
    function statusBadgeClass(status) {
        if (status === 'completed') return 'bg-success';
        if (status === 'completed_with_errors') return 'bg-warning text-dark';
        if (status === 'failed') return 'bg-danger';
        return 'bg-secondary';
    }

    function renderConnectors(ctx) {
        const container = document.getElementById('connector-list');
        const connectors = ctx.connectors || [];
        if (!connectors.length) {
            container.innerHTML = '<span>No connectors configured.</span>';
            return;
        }

        const filtered = connectors.filter(connector => {
            const name = (connector.name || '').toLowerCase();
            const metric = (ctx.connectorMetricsById || {})[connector.connector_id] || {};
            const status = metric.last_status || 'none';
            const matchesName = !ctx.connectorSearchTerm || name.includes(ctx.connectorSearchTerm);
            const matchesStatus = ctx.connectorStatusFilter === 'all' || status === ctx.connectorStatusFilter;
            return matchesName && matchesStatus;
        });

        if (!filtered.length) {
            container.innerHTML = '<span>No connectors match current filters.</span>';
            return;
        }

        container.innerHTML = filtered.map(connector => {
            const metric = (ctx.connectorMetricsById || {})[connector.connector_id] || {};
            const rawUrl = connector.config?.base_url || connector.config?.feed_url || '';
            let sourceDomain = '';
            if (rawUrl) {
                try {
                    sourceDomain = new URL(rawUrl).hostname.replace(/^www\./, '');
                } catch (_error) {
                    sourceDomain = '';
                }
            }
            return `
                <div class="border rounded p-2 mb-2 connector-card" data-id="${connector.connector_id}">
                    <div class="fw-semibold">${connector.name}</div>
                    <div class="text-muted">${connector.connector_type}</div>
                    <div class="text-muted small">${rawUrl || 'n/a'}</div>
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
                    ${sourceDomain ? `<div class="small mt-1"><a class="text-decoration-none" href="/recommendations?source=${encodeURIComponent(sourceDomain)}">Open in Recommendations (source filter)</a></div>` : ''}
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

    async function createConnector(ctx) {
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
            syncIntervalMinutes,
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
                enabled: true,
            }),
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
        await ctx.loadConnectors();
    }

    async function loadConnectorRuns(connectorId, ctx) {
        try {
            const response = await fetch(`/api/connectors/${encodeURIComponent(connectorId)}/runs?limit=5`);
            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.error || 'Failed to load connector runs');
            }
            const payload = await response.json();
            ctx.connectorRunsCache[connectorId] = payload.runs || [];
            renderConnectorRuns(connectorId, ctx);
            await ctx.loadConnectorMetrics();
        } catch (error) {
            console.error('Error loading connector runs:', error);
            ctx.showError(error.message || 'Failed to load connector runs');
        }
    }

    function renderConnectorRuns(connectorId, ctx) {
        const target = document.getElementById(`connector-runs-${connectorId}`);
        if (!target) return;
        const runs = ctx.connectorRunsCache[connectorId] || [];
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

    async function pollConnectorRun(runId, connectorId, ctx) {
        for (let attempt = 0; attempt < 30; attempt += 1) {
            const response = await fetch(`/api/connector-runs/${encodeURIComponent(runId)}`);
            if (!response.ok) break;
            const run = await response.json();
            if (['completed', 'completed_with_errors', 'failed'].includes(run.status)) {
                await loadConnectorRuns(connectorId, ctx);
                return;
            }
            await new Promise(resolve => setTimeout(resolve, 800));
        }
    }

    async function handleConnectorAction(event, ctx) {
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
                await loadConnectorRuns(id, ctx);
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
                await pollConnectorRun(payload.run_id, id, ctx);
            }

            if (runsBtn) {
                const id = runsBtn.dataset.id;
                await loadConnectorRuns(id, ctx);
                return;
            }

            if (saveConfigBtn) {
                const id = saveConfigBtn.dataset.id;
                const target = (ctx.connectors || []).find(connector => connector.connector_id === id);
                setConnectorCardError(id, '');
                const nextMaxArticles = Number(card?.querySelector('.connector-max-articles')?.value);
                const nextSyncInterval = Number(card?.querySelector('.connector-sync-interval')?.value);
                const nextAutoSync = Boolean(card?.querySelector('.connector-auto-sync')?.checked);
                const connectorUrl = target?.config?.feed_url || target?.config?.base_url || '';
                const validationError = validateConnectorInputs({
                    name: target?.name || '',
                    url: connectorUrl,
                    maxArticles: nextMaxArticles,
                    syncIntervalMinutes: nextSyncInterval,
                });
                if (validationError) {
                    setConnectorCardError(id, validationError);
                    throw new Error(validationError);
                }
                const config = { ...(target?.config || {}) };
                config.max_articles = Number.isFinite(nextMaxArticles) && nextMaxArticles > 0 ? nextMaxArticles : 10;
                config.sync_interval_minutes = Number.isFinite(nextSyncInterval) && nextSyncInterval > 0 ? nextSyncInterval : 60;
                config.auto_sync_enabled = nextAutoSync;

                const response = await fetch(`/api/connectors/${encodeURIComponent(id)}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        enabled: target?.enabled,
                        name: target?.name,
                        connector_type: target?.connector_type,
                        config,
                    }),
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
                const target = (ctx.connectors || []).find(connector => connector.connector_id === id);
                const response = await fetch(`/api/connectors/${encodeURIComponent(id)}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        enabled: !currentlyEnabled,
                        name: target?.name,
                        connector_type: target?.connector_type,
                        config: target?.config || {},
                    }),
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

            await ctx.loadConnectors();
        } catch (error) {
            console.error('Connector action failed:', error);
            ctx.showError(error.message || 'Connector operation failed');
        }
    }

    async function syncDueConnectors(ctx) {
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

            const pollTasks = (payload.triggered || []).map(item => pollConnectorRun(item.run_id, item.connector_id, ctx));
            await Promise.all(pollTasks);
            await ctx.loadConnectors();
            await ctx.loadConnectorMetrics();
        } catch (error) {
            console.error('Error syncing due connectors:', error);
            ctx.showError(error.message || 'Failed to run due connector sync');
        }
    }

    async function loadSchedulerStatus(ctx) {
        const statusEl = document.getElementById('scheduler-status');
        if (!statusEl) return;
        try {
            const payload = await ctx.ApiClient.get('/api/connectors/scheduler/status');
            const lastRun = payload.last_run_at || 'never';
            const state = payload.running ? 'running' : (payload.enabled ? 'enabled' : 'disabled');
            statusEl.textContent = `${state}; runs ${payload.runs_total}; last ${lastRun}`;
        } catch (error) {
            statusEl.textContent = `Scheduler status error: ${error.message}`;
        }
    }

    async function runSchedulerNow(ctx) {
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
            await loadSchedulerStatus(ctx);
            await ctx.loadConnectors();
            await ctx.loadConnectorMetrics();
        } catch (error) {
            ctx.showError(error.message || 'Scheduler run failed');
        }
    }

    globalScope.ConnectorsControllerModule = {
        renderConnectors,
        createConnector,
        handleConnectorAction,
        syncDueConnectors,
        loadSchedulerStatus,
        runSchedulerNow,
        pollConnectorRun,
        loadConnectorRuns,
        renderConnectorRuns,
        validateConnectorInputs,
        setConnectorFormError,
        setConnectorCardError,
    };
})(window);
