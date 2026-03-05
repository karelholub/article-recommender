(function initReportingRolloutsModule(globalScope) {
    function rolloutConfigOptionsHtml(configsMap, selectedValue = '') {
        const configs = Object.values(configsMap || {});
        const options = configs.map((item) => {
            const configId = item?.config?.config_id || '';
            const version = item?.version ?? 0;
            return `<option value="${configId}" ${selectedValue === configId ? 'selected' : ''}>${configId} (v${version})</option>`;
        }).join('');
        return options || '<option value="balanced">balanced</option>';
    }

    function renderRolloutControls(ctx) {
        const {
            rolloutItems,
            selectedRolloutId,
            setSelectedRolloutId,
            rankingConfigs,
        } = ctx;
        const summary = document.getElementById('rollout-summary');
        const table = document.getElementById('rollout-table');
        const select = document.getElementById('rollout-select');
        const activeHint = document.getElementById('active-rollout-hint');
        if (!select && !activeHint) return;

        const active = (rolloutItems || []).find(item => item.enabled && item.status === 'running') || null;
        if (activeHint) {
            activeHint.textContent = active
                ? `Active canary rollout: ${active.name} (${Number(active.traffic_percentage || 0).toFixed(1)}% candidate traffic).`
                : 'No active canary rollout detected.';
        }
        if (!select || !table || !summary) return;

        const previous = selectedRolloutId || select.value || '';
        const options = ['<option value="">New rollout</option>']
            .concat((rolloutItems || []).map(item => `<option value="${item.rollout_id}">${item.name} (${item.status})</option>`));
        select.innerHTML = options.join('');
        select.value = (rolloutItems || []).some(item => item.rollout_id === previous) ? previous : '';
        setSelectedRolloutId(select.value);

        const activeCount = (rolloutItems || []).filter(item => item.enabled && item.status === 'running').length;
        summary.textContent = `Rollouts: ${(rolloutItems || []).length} total | Active: ${activeCount}`;
        table.innerHTML = (rolloutItems || []).map(item => {
            const lastGuard = item.last_evaluation?.passed == null
                ? 'n/a'
                : (item.last_evaluation.passed ? 'PASS' : 'FAIL');
            return `
                <tr data-rollout-id="${item.rollout_id}" class="rollout-row">
                    <td>${item.name}</td>
                    <td>${item.status}${item.enabled ? ' / enabled' : ''}</td>
                    <td>${Number(item.traffic_percentage || 0).toFixed(1)}%</td>
                    <td>${item.baseline_config_id || 'n/a'}</td>
                    <td>${item.candidate_config_id || 'n/a'}</td>
                    <td>${lastGuard}</td>
                    <td>${item.updated_at || 'n/a'}</td>
                </tr>
            `;
        }).join('') || '<tr><td colspan="7" class="text-muted">No rollout definitions yet.</td></tr>';

        const selected = (rolloutItems || []).find(item => item.rollout_id === select.value) || null;
        document.getElementById('rollout-name').value = selected?.name || '';
        document.getElementById('rollout-baseline-config').innerHTML = rolloutConfigOptionsHtml(rankingConfigs, selected?.baseline_config_id || 'balanced');
        document.getElementById('rollout-candidate-config').innerHTML = rolloutConfigOptionsHtml(rankingConfigs, selected?.candidate_config_id || 'balanced');
        if (!document.getElementById('rollout-baseline-config').value) document.getElementById('rollout-baseline-config').value = 'balanced';
        if (!document.getElementById('rollout-candidate-config').value) document.getElementById('rollout-candidate-config').value = 'balanced';
        document.getElementById('rollout-traffic-percentage').value = Number(selected?.traffic_percentage ?? 10).toFixed(1);
        document.getElementById('rollout-auto-rollback-enabled').checked = Boolean(selected?.auto_rollback?.enabled ?? true);
        document.getElementById('rollout-evaluation-days').value = Number(selected?.auto_rollback?.evaluation_days ?? 7);
        document.getElementById('rollout-min-candidate-runs').value = Number(selected?.auto_rollback?.min_candidate_runs ?? 200);
        document.getElementById('rollout-min-ctr-lift').value = Number(selected?.auto_rollback?.min_ctr_lift ?? -0.01).toFixed(3);
        document.getElementById('rollout-max-ctr-drop').value = Number(selected?.auto_rollback?.max_ctr_drop ?? 0.02).toFixed(3);
    }

    function collectRolloutPayloadFromUi(getOperatorId) {
        return {
            name: document.getElementById('rollout-name')?.value?.trim() || '',
            baseline_config_id: document.getElementById('rollout-baseline-config')?.value || 'balanced',
            candidate_config_id: document.getElementById('rollout-candidate-config')?.value || '',
            traffic_percentage: Number(document.getElementById('rollout-traffic-percentage')?.value || 10),
            auto_rollback: {
                enabled: Boolean(document.getElementById('rollout-auto-rollback-enabled')?.checked),
                evaluation_days: Number(document.getElementById('rollout-evaluation-days')?.value || 7),
                min_candidate_runs: Number(document.getElementById('rollout-min-candidate-runs')?.value || 200),
                min_ctr_lift: Number(document.getElementById('rollout-min-ctr-lift')?.value || -0.01),
                max_ctr_drop: Number(document.getElementById('rollout-max-ctr-drop')?.value || 0.02),
            },
            actor_id: getOperatorId() || undefined,
        };
    }

    async function loadRollouts(ctx) {
        const { ApiClient, setRolloutItems, renderRolloutControls } = ctx;
        try {
            const payload = await ApiClient.get('/api/rollouts');
            setRolloutItems(payload.rollouts || []);
            renderRolloutControls();
        } catch (error) {
            const summary = document.getElementById('rollout-summary');
            const table = document.getElementById('rollout-table');
            if (summary) summary.textContent = `Rollout loading failed: ${error.message}`;
            if (table) table.innerHTML = '<tr><td colspan="7" class="text-danger">Failed to load rollouts.</td></tr>';
        }
    }

    async function saveRollout(ctx) {
        const { ApiClient, selectedRolloutId, setSelectedRolloutId, getOperatorId, getOperatorHeaders, loadRollouts } = ctx;
        const payload = collectRolloutPayloadFromUi(getOperatorId);
        if (!payload.candidate_config_id) {
            throw new Error('Candidate config is required');
        }
        if (selectedRolloutId) {
            await ApiClient.put(`/api/rollouts/${encodeURIComponent(selectedRolloutId)}`, payload, { headers: getOperatorHeaders() });
        } else {
            const created = await ApiClient.post('/api/rollouts', payload, { headers: getOperatorHeaders() });
            setSelectedRolloutId(created.rollout?.rollout_id || '');
        }
        await loadRollouts();
    }

    async function startSelectedRollout(ctx) {
        const { ApiClient, selectedRolloutId, getOperatorId, getOperatorHeaders, loadRollouts } = ctx;
        if (!selectedRolloutId) throw new Error('Select rollout first');
        await ApiClient.post(`/api/rollouts/${encodeURIComponent(selectedRolloutId)}/start`, { actor_id: getOperatorId() || undefined }, { headers: getOperatorHeaders() });
        await loadRollouts();
    }

    async function stopSelectedRollout(ctx) {
        const { ApiClient, selectedRolloutId, getOperatorId, getOperatorHeaders, loadRollouts } = ctx;
        if (!selectedRolloutId) throw new Error('Select rollout first');
        await ApiClient.post(`/api/rollouts/${encodeURIComponent(selectedRolloutId)}/stop`, { actor_id: getOperatorId() || undefined }, { headers: getOperatorHeaders() });
        await loadRollouts();
    }

    async function evaluateSelectedRollout(ctx) {
        const { ApiClient, selectedRolloutId, getOperatorId, getOperatorHeaders, loadRollouts } = ctx;
        if (!selectedRolloutId) throw new Error('Select rollout first');
        const response = await ApiClient.post(
            `/api/rollouts/${encodeURIComponent(selectedRolloutId)}/evaluate`,
            { apply_auto_rollback: true, actor_id: getOperatorId() || undefined },
            { headers: getOperatorHeaders() }
        );
        const summary = document.getElementById('rollout-summary');
        if (summary) {
            summary.textContent = response.evaluation?.passed
                ? 'Selected rollout guard passed.'
                : `Selected rollout guard failed${response.evaluation?.auto_rollback_applied ? ' and rollout was auto-paused.' : '.'}`;
        }
        await loadRollouts();
    }

    async function evaluateActiveRollouts(ctx) {
        const { ApiClient, getOperatorId, getOperatorHeaders, loadRollouts } = ctx;
        const response = await ApiClient.post('/api/rollouts/evaluate-active', { apply_auto_rollback: true, actor_id: getOperatorId() || undefined }, { headers: getOperatorHeaders() });
        const summary = document.getElementById('rollout-summary');
        if (summary) summary.textContent = `Evaluated ${response.count || 0} active rollouts.`;
        await loadRollouts();
    }

    globalScope.ReportingRolloutsModule = {
        rolloutConfigOptionsHtml,
        renderRolloutControls,
        collectRolloutPayloadFromUi,
        loadRollouts,
        saveRollout,
        startSelectedRollout,
        stopSelectedRollout,
        evaluateSelectedRollout,
        evaluateActiveRollouts,
    };
})(window);
