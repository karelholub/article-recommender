(function initOperationsQueueModule(globalScope) {
    function escapeHtml(value) {
        return String(value ?? '')
            .replaceAll('&', '&amp;')
            .replaceAll('<', '&lt;')
            .replaceAll('>', '&gt;')
            .replaceAll('"', '&quot;')
            .replaceAll("'", '&#39;');
    }

    async function loadEventsQueueStatus(deps) {
        const { ApiClient } = deps;
        const container = document.getElementById('events-queue-status');
        if (!container) return;
        try {
            const payload = await ApiClient.get('/api/events/ingest-queue-status');
            const queue = payload.queue || {};
            container.innerHTML = `
                <div><strong>Enabled:</strong> ${queue.enabled ? 'yes' : 'no'}</div>
                <div><strong>Running:</strong> ${queue.running ? 'yes' : 'no'}</div>
                <div><strong>Queue size:</strong> ${queue.queue_size ?? 0}</div>
                <div><strong>Enqueued:</strong> ${queue.enqueued_total ?? 0} | <strong>Processed:</strong> ${queue.processed_total ?? 0} | <strong>Failed:</strong> ${queue.failed_total ?? 0}</div>
                <div><strong>Last processed:</strong> ${escapeHtml(queue.last_processed_at || 'n/a')}</div>
            `;
        } catch (error) {
            container.textContent = `Events queue unavailable: ${error.message}`;
        }
    }

    async function loadEventsQueueHealth(deps) {
        const { ApiClient } = deps;
        const container = document.getElementById('events-queue-health');
        if (!container) return;
        try {
            const payload = await ApiClient.get('/api/events/ingest-queue-health');
            const trend5m = payload.trend?.window_5m || {};
            const trend15m = payload.trend?.window_15m || {};
            const warnings = Array.isArray(payload.warnings) ? payload.warnings : [];
            const warningHtml = warnings.length
                ? warnings.map(item => `<div><strong>${escapeHtml(item.severity?.toUpperCase() || 'WARN')}:</strong> ${escapeHtml(item.message)} (${escapeHtml(item.recommendation || 'n/a')})</div>`).join('')
                : '<div>No queue warnings. Ingestion operating normally.</div>';
            container.innerHTML = `
                <div><strong>Advisory:</strong> ingest=${escapeHtml(payload.advisories?.ingest_async || 'normal')}, recommendations=${escapeHtml(payload.advisories?.recommendations || 'normal')}</div>
                <div><strong>5m:</strong> +enq ${trend5m.enqueued_delta ?? 0}, +proc ${trend5m.processed_delta ?? 0}, +fail ${trend5m.failed_delta ?? 0}, peak saturation ${Number(trend5m.peak_saturation || 0).toFixed(2)}</div>
                <div><strong>15m:</strong> +enq ${trend15m.enqueued_delta ?? 0}, +proc ${trend15m.processed_delta ?? 0}, +fail ${trend15m.failed_delta ?? 0}, peak saturation ${Number(trend15m.peak_saturation || 0).toFixed(2)}</div>
                <div class="mt-1">${warningHtml}</div>
            `;
        } catch (error) {
            container.textContent = `Queue health unavailable: ${error.message}`;
        }
    }

    async function enqueueEventsSample(deps) {
        const { getOperatorHeaders, getOperatorId } = deps;
        const countRaw = Number(document.getElementById('events-queue-sample-size')?.value || 5);
        const count = Number.isFinite(countRaw) ? Math.max(1, Math.min(5, Math.round(countRaw))) : 5;
        const now = Date.now();
        const runSuffix = String(now % 1000000000000).padStart(12, '0');
        const runId = `00000000-0000-0000-0000-${runSuffix}`;
        const events = Array.from({ length: count }).map((_, idx) => ({
            event_type: 'impression',
            run_id: runId,
            article_id: `sample_article_${idx + 1}`,
            scenario_id: 'default',
            user_id: `sample_user_${idx + 1}`,
            external_user_id: `sample_ext_${idx + 1}`,
            rank_position: idx + 1,
            event_value: 1.0,
            metadata: { source: 'sample.source.local', synthetic: true },
        }));
        const response = await fetch('/api/events/ingest-async', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', ...getOperatorHeaders() },
            body: JSON.stringify({ events, actor_id: getOperatorId() || undefined }),
        });
        const payload = await response.json();
        if (!response.ok) {
            throw new Error(payload.error || 'Failed to enqueue sample events');
        }
        await loadEventsQueueStatus(deps);
        await loadEventsQueueHealth(deps);
    }

    async function controlEventsQueue(action, deps) {
        const { getOperatorHeaders, getOperatorId } = deps;
        if (!['enable', 'disable', 'drain'].includes(action)) {
            throw new Error('Unsupported queue action');
        }
        const payload = { action, actor_id: getOperatorId() || undefined };
        const response = await fetch('/api/events/ingest-queue-control', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', ...getOperatorHeaders() },
            body: JSON.stringify(payload),
        });
        const body = await response.json();
        if (!response.ok) {
            throw new Error(body.error || 'Failed to control events queue');
        }
        await loadEventsQueueStatus(deps);
        await loadEventsQueueHealth(deps);
    }

    globalScope.OperationsQueueModule = {
        loadEventsQueueStatus,
        loadEventsQueueHealth,
        enqueueEventsSample,
        controlEventsQueue,
    };
})(window);
