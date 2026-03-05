(function initReportingDashboardModule(globalScope) {
    function renderReportingWorkspace(payload, ctx) {
        const summary = payload.summary || {};
        ctx.setReportingLastPayload(payload);
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
        if (ctx.reportingVolumeChart) ctx.reportingVolumeChart.destroy();
        if (ctx.reportingCtrChart) ctx.reportingCtrChart.destroy();
        if (ctx.reportingScenarioOverlayChart) ctx.reportingScenarioOverlayChart.destroy();
        if (ctx.reportingFunnelChart) ctx.reportingFunnelChart.destroy();

        ctx.setReportingVolumeChart(new Chart(volumeCtx, {
            type: 'bar',
            data: {
                labels,
                datasets: [
                    { label: 'Impressions', data: impressions, backgroundColor: '#0d6efd' },
                    { label: 'Clicks', data: clicks, backgroundColor: '#198754' },
                ],
            },
            options: { responsive: true, maintainAspectRatio: false },
        }));
        ctx.setReportingCtrChart(new Chart(ctrCtx, {
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
                        fill: true,
                    },
                ],
            },
            options: { responsive: true, maintainAspectRatio: false },
        }));

        const palette = ['#6f42c1', '#0dcaf0', '#d63384', '#198754', '#ffc107', '#20c997'];
        const overlayDatasets = (payload.scenarios || []).slice(0, 6).map((scenario, idx) => ({
            label: scenario.name || scenario.scenario_id,
            data: (scenario.points || []).map(point => Number(point.ctr || 0) * 100),
            borderColor: palette[idx % palette.length],
            backgroundColor: 'transparent',
            tension: 0.25,
        }));
        ctx.setReportingScenarioOverlayChart(new Chart(overlayCtx, {
            type: 'line',
            data: { labels, datasets: overlayDatasets },
            options: { responsive: true, maintainAspectRatio: false },
        }));
        ctx.setReportingFunnelChart(new Chart(funnelCtx, {
            type: 'bar',
            data: {
                labels: ['Impressions', 'Clicks', 'Conversions'],
                datasets: [{
                    label: 'Funnel',
                    data: [summary.impressions || 0, summary.clicks || 0, summary.conversions || 0],
                    backgroundColor: ['#0d6efd', '#198754', '#fd7e14'],
                }],
            },
            options: {
                indexAxis: 'y',
                responsive: true,
                maintainAspectRatio: false,
            },
        }));
    }

    function renderReportingAttribution(payload, ctx) {
        ctx.setReportingLastAttribution(payload);
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

    globalScope.ReportingDashboardModule = {
        renderReportingWorkspace,
        renderReportingAttribution,
    };
})(window);
