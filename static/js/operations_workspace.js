(function initOperationsWorkspace(globalScope) {
    function renderEngineConfigSnapshot(payload) {
        const container = document.getElementById('engine-config-snapshot');
        const summary = document.getElementById('engine-config-summary');
        const kpis = document.getElementById('engine-config-kpis');
        const details = document.getElementById('engine-config-details');
        if (!container || !summary || !kpis || !details) return;

        container.textContent = JSON.stringify(payload, null, 2);
        const rankingConfigs = payload.ranking_configs || {};
        const configIds = Object.keys(rankingConfigs);
        const scenarios = payload.scenarios || [];
        const enabledScenarios = scenarios.filter(item => item && item.enabled).length;
        const disabledScenarios = Math.max(0, scenarios.length - enabledScenarios);
        const sources = payload.sources || [];
        const scheduler = payload.scheduler || {};
        const cdpScheduler = payload.cdp_scheduler || {};
        const cdp = payload.cdp || {};
        const topConfigs = configIds.slice(0, 8).map(id => `<span class="badge text-bg-light border me-1 mb-1">${id}</span>`).join('');
        const topScenarios = scenarios.slice(0, 8).map(item => (
            `<span class="badge ${item.enabled ? 'text-bg-success' : 'text-bg-secondary'} me-1 mb-1">${item.scenario_id || 'n/a'}</span>`
        )).join('');
        kpis.innerHTML = [
            `<span class="badge text-bg-light border">Sources ${sources.length}</span>`,
            `<span class="badge text-bg-light border">Ranking configs ${configIds.length}</span>`,
            `<span class="badge text-bg-success">Enabled scenarios ${enabledScenarios}</span>`,
            `<span class="badge text-bg-secondary">Disabled scenarios ${disabledScenarios}</span>`,
            `<span class="badge ${cdp.enabled ? 'text-bg-primary' : 'text-bg-light border'}">CDP ${cdp.enabled ? 'on' : 'off'}</span>`
        ].join('');
        summary.innerHTML = `
            Updated <strong>${payload.generated_at || 'n/a'}</strong> | API ${payload.api_version || 'n/a'}<br>
            Connector scheduler: ${scheduler.running ? '<span class="text-success">running</span>' : '<span class="text-muted">idle</span>'}
            (runs ${scheduler.runs_total ?? 0}, errors ${scheduler.errors_total ?? 0}) |
            CDP scheduler: ${cdpScheduler.running ? '<span class="text-success">running</span>' : '<span class="text-muted">idle</span>'}
            (runs ${cdpScheduler.runs_total ?? 0}, errors ${cdpScheduler.errors_total ?? 0})
        `;
        details.innerHTML = `
            <div class="mb-2">
                <strong>Top ranking configs</strong>
                <div class="mt-1">${topConfigs || '<span class="text-muted">No configs.</span>'}</div>
            </div>
            <div>
                <strong>Top scenarios</strong>
                <div class="mt-1">${topScenarios || '<span class="text-muted">No scenarios.</span>'}</div>
            </div>
        `;
    }

    function renderAuditLogs(payload) {
        const container = document.getElementById('audit-logs-list');
        if (!container) return;
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

    async function loadEngineConfigSnapshot() {
        const container = document.getElementById('engine-config-snapshot');
        const summary = document.getElementById('engine-config-summary');
        const kpis = document.getElementById('engine-config-kpis');
        const details = document.getElementById('engine-config-details');
        if (!container || !summary || !kpis || !details) return;
        try {
            const payload = await ApiClient.get('/api/engine/config');
            renderEngineConfigSnapshot(payload);
        } catch (error) {
            kpis.innerHTML = '';
            summary.textContent = `Failed to load engine snapshot summary: ${error.message}`;
            details.textContent = `Failed to load details: ${error.message}`;
            container.textContent = `Failed to load engine snapshot: ${error.message}`;
        }
    }

    async function loadAuditLogs() {
        const container = document.getElementById('audit-logs-list');
        if (!container) return;
        try {
            const actorId = (document.getElementById('audit-actor-filter')?.value || '').trim();
            const resourceType = (document.getElementById('audit-resource-filter')?.value || '').trim();
            const payload = await ApiClient.get('/api/audit-logs', {
                query: {
                    limit: 25,
                    offset: 0,
                    actor_id: actorId || undefined,
                    resource_type: resourceType || undefined
                }
            });
            renderAuditLogs(payload);
        } catch (error) {
            container.textContent = `Audit logs unavailable: ${error.message}`;
        }
    }

    globalScope.OperationsWorkspace = {
        loadEngineConfigSnapshot,
        loadAuditLogs
    };
})(window);
