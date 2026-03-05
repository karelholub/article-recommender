(function initCdpControllerModule(globalScope) {
    function setPreviewValidation(message, isError) {
        const input = document.getElementById('cdp-preview-payload');
        const hint = document.getElementById('cdp-preview-validation');
        if (input) {
            input.classList.toggle('is-invalid', Boolean(isError));
            input.classList.toggle('is-valid', !isError && Boolean(message));
        }
        if (hint) {
            hint.className = `small mb-2 ${isError ? 'text-danger' : 'text-muted'}`;
            hint.textContent = message || '';
        }
    }

    function validatePreviewPayloadInput() {
        const raw = document.getElementById('cdp-preview-payload')?.value || '';
        if (!raw.trim()) {
            setPreviewValidation('Provide valid JSON payload before preview.', false);
            return false;
        }
        try {
            JSON.parse(raw);
            setPreviewValidation('Payload JSON looks valid.', false);
            return true;
        } catch (_error) {
            setPreviewValidation('Sample payload is not valid JSON.', true);
            return false;
        }
    }

    function collectCdpMappingFromForm() {
        let scenarioMap = {};
        let configMap = {};
        try {
            scenarioMap = JSON.parse(document.getElementById('cdp-scenario-segment-map').value || '{}');
            configMap = JSON.parse(document.getElementById('cdp-config-segment-map').value || '{}');
        } catch (error) {
            throw new Error('Invalid JSON in mapping fields');
        }
        const weightRangeRaw = (document.getElementById('cdp-derivation-weight-range').value || '').trim();
        const weightRange = weightRangeRaw.split(':').map(item => Number(item.trim()));
        if (weightRange.length !== 2 || !Number.isFinite(weightRange[0]) || !Number.isFinite(weightRange[1])) {
            throw new Error('Invalid derivation weight range (expected min:max)');
        }
        return {
            external_id_path: (document.getElementById('cdp-external-id-path').value || '').trim(),
            traits_path: (document.getElementById('cdp-traits-path').value || '').trim(),
            segments_path: (document.getElementById('cdp-segments-path').value || '').trim(),
            fixed_segments: (document.getElementById('cdp-fixed-segments').value || '').split(',').map(item => item.trim()).filter(Boolean),
            preferred_sources_trait: (document.getElementById('cdp-preferred-sources-trait').value || '').trim(),
            excluded_sources_trait: (document.getElementById('cdp-excluded-sources-trait').value || '').trim(),
            source_weights_trait: (document.getElementById('cdp-source-weights-trait').value || '').trim(),
            source_weight_trait_prefix: (document.getElementById('cdp-source-weight-prefix').value || '').trim(),
            derivation_min_source_events: Number(document.getElementById('cdp-derivation-min-source-events').value || 3),
            derivation_min_category_events: Number(document.getElementById('cdp-derivation-min-category-events').value || 1),
            derivation_max_preferred_sources: Number(document.getElementById('cdp-derivation-max-sources').value || 5),
            derivation_min_source_weight: Number(weightRange[0]),
            derivation_max_source_weight: Number(weightRange[1]),
            derivation_allowed_sources: (document.getElementById('cdp-derivation-allowlist').value || '').split(',').map(item => item.trim()).filter(Boolean),
            derivation_blocked_sources: (document.getElementById('cdp-derivation-blocklist').value || '').split(',').map(item => item.trim()).filter(Boolean),
            scenario_segment_map: scenarioMap,
            config_segment_map: configMap,
            segment_priority: (document.getElementById('cdp-segment-priority').value || '').split(',').map(item => item.trim()).filter(Boolean),
            personalization_mode: (document.getElementById('cdp-personalization-mode').value || 'active').trim(),
            fallback_mode: (document.getElementById('cdp-fallback-mode').value || 'source_defaults').trim(),
            freshness_sla_hours: Number(document.getElementById('cdp-freshness-sla-hours').value || 24),
        };
    }

    function normalizeImportedCdpMapping(mapping) {
        const current = collectCdpMappingFromForm();
        return { ...current, ...(mapping || {}) };
    }

    function writeCdpMappingToForm(merged) {
        document.getElementById('cdp-external-id-path').value = merged.external_id_path || '';
        document.getElementById('cdp-traits-path').value = merged.traits_path || '';
        document.getElementById('cdp-segments-path').value = merged.segments_path || '';
        document.getElementById('cdp-fixed-segments').value = (merged.fixed_segments || []).join(', ');
        document.getElementById('cdp-preferred-sources-trait').value = merged.preferred_sources_trait || '';
        document.getElementById('cdp-excluded-sources-trait').value = merged.excluded_sources_trait || '';
        document.getElementById('cdp-source-weights-trait').value = merged.source_weights_trait || '';
        document.getElementById('cdp-source-weight-prefix').value = merged.source_weight_trait_prefix || '';
        document.getElementById('cdp-derivation-min-source-events').value = Number(merged.derivation_min_source_events ?? 3);
        document.getElementById('cdp-derivation-min-category-events').value = Number(merged.derivation_min_category_events ?? 1);
        document.getElementById('cdp-derivation-max-sources').value = Number(merged.derivation_max_preferred_sources ?? 5);
        document.getElementById('cdp-derivation-weight-range').value = `${Number(merged.derivation_min_source_weight ?? 1.05)}:${Number(merged.derivation_max_source_weight ?? 2.0)}`;
        document.getElementById('cdp-derivation-allowlist').value = (merged.derivation_allowed_sources || []).join(', ');
        document.getElementById('cdp-derivation-blocklist').value = (merged.derivation_blocked_sources || []).join(', ');
        document.getElementById('cdp-scenario-segment-map').value = JSON.stringify(merged.scenario_segment_map || {}, null, 2);
        document.getElementById('cdp-config-segment-map').value = JSON.stringify(merged.config_segment_map || {}, null, 2);
        document.getElementById('cdp-segment-priority').value = (merged.segment_priority || []).join(', ');
        document.getElementById('cdp-personalization-mode').value = merged.personalization_mode || 'active';
        document.getElementById('cdp-fallback-mode').value = merged.fallback_mode || 'source_defaults';
        document.getElementById('cdp-freshness-sla-hours').value = Number(merged.freshness_sla_hours ?? 24);
    }

    async function loadCdpConfig(ctx) {
        const statusEl = document.getElementById('cdp-config-status');
        try {
            const response = await fetch('/api/cdp/meiro');
            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.error || 'Failed to load CDP config');
            }
            const payload = await response.json();
            ctx.setCdpIntegration(payload);
            document.getElementById('cdp-enabled').checked = Boolean(payload.enabled);
            document.getElementById('cdp-base-url').value = payload.config?.base_url || '';
            document.getElementById('cdp-request-url-template').value = payload.config?.request_url_template || '';
            document.getElementById('cdp-profile-endpoint-template').value = payload.config?.profile_endpoint_template || '/profiles/{external_user_id}';
            document.getElementById('cdp-api-key').value = payload.config?.api_key || '';
            document.getElementById('cdp-timeout-seconds').value = Number(payload.config?.timeout_seconds ?? 5);
            document.getElementById('cdp-request-retries').value = Number(payload.config?.request_retries ?? 2);
            writeCdpMappingToForm(payload.mapping || {});
            const mappingJson = document.getElementById('cdp-mapping-json');
            if (mappingJson) mappingJson.value = JSON.stringify(payload.mapping || {}, null, 2);
            const previewInput = document.getElementById('cdp-preview-payload');
            if (previewInput && !previewInput.value.trim()) {
                previewInput.value = JSON.stringify(
                    {
                        customer_entity_id: 'external-user-id',
                        returned_attributes: {
                            web_all_products_viewed_3: [
                                '["2026-03-02T12:00:49","sku","name","200","tops","Brand","https://source.example/a","img"]',
                            ],
                        },
                    },
                    null,
                    2
                );
            }
            validatePreviewPayloadInput();
            if (statusEl) statusEl.textContent = `Loaded. Updated at ${payload.updated_at || 'n/a'}.`;
        } catch (error) {
            if (statusEl) statusEl.textContent = `CDP config unavailable: ${error.message}`;
        }
    }

    async function loadCdpMappingPresets(ctx) {
        const select = document.getElementById('cdp-mapping-preset');
        if (!select) return;
        try {
            const response = await fetch('/api/cdp/meiro/presets');
            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.error || 'Failed to load mapping presets');
            }
            const payload = await response.json();
            ctx.setCdpMappingPresets(payload.presets || []);
            const options = ['<option value="">Select preset</option>']
                .concat((ctx.cdpMappingPresets || []).map(item => `<option value="${item.preset_id}">${item.label} (${item.preset_id})</option>`));
            select.innerHTML = options.join('');
        } catch (error) {
            select.innerHTML = '<option value="">Presets unavailable</option>';
        }
    }

    function applyCdpPresetToForm(ctx) {
        const presetId = document.getElementById('cdp-mapping-preset')?.value || '';
        if (!presetId) throw new Error('Choose a mapping preset first.');
        const preset = (ctx.cdpMappingPresets || []).find(item => item.preset_id === presetId);
        if (!preset) throw new Error(`Unknown mapping preset: ${presetId}`);
        const merged = { ...collectCdpMappingFromForm(), ...(preset.mapping || {}) };
        writeCdpMappingToForm(merged);
        const mappingJson = document.getElementById('cdp-mapping-json');
        if (mappingJson) mappingJson.value = JSON.stringify(merged, null, 2);
        const statusEl = document.getElementById('cdp-config-status');
        if (statusEl) statusEl.textContent = `Applied preset ${preset.label} to form. Save to persist.`;
    }

    function exportCdpMappingJson() {
        const mapping = collectCdpMappingFromForm();
        const target = document.getElementById('cdp-mapping-json');
        if (!target) return;
        target.value = JSON.stringify(mapping, null, 2);
    }

    function importCdpMappingJson() {
        const target = document.getElementById('cdp-mapping-json');
        if (!target) return;
        let parsed = {};
        try {
            parsed = JSON.parse(target.value || '{}');
        } catch (_error) {
            throw new Error('Mapping JSON is invalid');
        }
        if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
            throw new Error('Mapping JSON must be an object');
        }
        const merged = normalizeImportedCdpMapping(parsed);
        writeCdpMappingToForm(merged);
    }

    async function saveCdpConfig(ctx) {
        const statusEl = document.getElementById('cdp-config-status');
        const payload = {
            enabled: document.getElementById('cdp-enabled').checked,
            config: {
                base_url: (document.getElementById('cdp-base-url').value || '').trim(),
                request_url_template: (document.getElementById('cdp-request-url-template').value || '').trim(),
                profile_endpoint_template: (document.getElementById('cdp-profile-endpoint-template').value || '').trim(),
                api_key: (document.getElementById('cdp-api-key').value || '').trim(),
                timeout_seconds: Number(document.getElementById('cdp-timeout-seconds').value || 5),
                request_retries: Number(document.getElementById('cdp-request-retries').value || 2),
            },
            mapping: collectCdpMappingFromForm(),
            actor_id: ctx.getOperatorId() || undefined,
        };
        if (statusEl) statusEl.textContent = 'Saving CDP config...';
        const response = await fetch('/api/cdp/meiro', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json', ...ctx.getOperatorHeaders() },
            body: JSON.stringify(payload),
        });
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Failed to save CDP config');
        }
        const saved = await response.json();
        ctx.setCdpIntegration(saved);
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

    async function syncCdpProfiles(ctx) {
        const statusEl = document.getElementById('cdp-sync-status');
        const raw = document.getElementById('cdp-sync-external-ids').value || '';
        const externalIds = raw.split(',').map(item => item.trim()).filter(Boolean);
        if (!externalIds.length) throw new Error('Enter at least one external ID');
        if (statusEl) statusEl.textContent = 'Sync in progress...';
        const response = await fetch('/api/cdp/meiro/sync', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', ...ctx.getOperatorHeaders() },
            body: JSON.stringify({ external_user_ids: externalIds, actor_id: ctx.getOperatorId() || undefined }),
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

    async function runCdpSchedulerNow(ctx) {
        const statusEl = document.getElementById('cdp-scheduler-status');
        if (statusEl) statusEl.textContent = 'Running CDP sync now...';
        const response = await fetch('/api/cdp/meiro/scheduler/run-now', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', ...ctx.getOperatorHeaders() },
            body: JSON.stringify({ actor_id: ctx.getOperatorId() || undefined }),
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

    async function deriveCdpProfile(persist = false, ctx) {
        const externalId = (document.getElementById('cdp-derive-external-id')?.value || '').trim();
        if (!externalId) throw new Error('Enter external user ID for derivation');
        const output = document.getElementById('cdp-derivation-output');
        if (output) output.textContent = 'Deriving...';
        const response = await fetch(`/api/cdp/meiro/profiles/${encodeURIComponent(externalId)}/derive`, {
            method: persist ? 'POST' : 'GET',
            headers: persist ? { 'Content-Type': 'application/json', ...ctx.getOperatorHeaders() } : undefined,
            body: persist ? JSON.stringify({
                persist: true,
                force: Boolean(document.getElementById('cdp-derive-force')?.checked),
                actor_id: ctx.getOperatorId() || undefined,
            }) : undefined,
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

    async function previewCdpMapping(ctx) {
        const output = document.getElementById('cdp-mapping-preview-output');
        if (!output) return;
        if (!validatePreviewPayloadInput()) {
            throw new Error('Fix sample payload JSON before preview');
        }
        let samplePayload = {};
        try {
            samplePayload = JSON.parse(document.getElementById('cdp-preview-payload')?.value || '{}');
        } catch (_error) {
            setPreviewValidation('Sample payload is not valid JSON.', true);
            throw new Error('Invalid JSON in sample payload');
        }
        setPreviewValidation('Payload JSON looks valid.', false);
        output.textContent = 'Previewing mapping...';
        const response = await fetch('/api/cdp/meiro/mapping/preview', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', ...ctx.getOperatorHeaders() },
            body: JSON.stringify({
                payload: samplePayload,
                fallback_external_user_id: (document.getElementById('cdp-preview-fallback-external-id')?.value || '').trim(),
                mapping: collectCdpMappingFromForm(),
                actor_id: ctx.getOperatorId() || undefined,
            }),
        });
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Failed to preview mapping');
        }
        const preview = await response.json();
        output.textContent = JSON.stringify(preview, null, 2);
    }

    async function previewCdpFallback(ctx) {
        const output = document.getElementById('cdp-mapping-preview-output');
        if (!output) return;
        const externalUserId = (document.getElementById('cdp-fallback-preview-external-id')?.value || '').trim();
        if (!externalUserId) throw new Error('Enter fallback preview external user ID');
        output.textContent = 'Previewing fallback behavior...';
        const response = await fetch('/api/cdp/meiro/fallback-preview', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', ...ctx.getOperatorHeaders() },
            body: JSON.stringify({
                external_user_id: externalUserId,
                sources: [],
                config_id: 'balanced',
                scenario_id: '',
                scenario_explicit: false,
                config_explicit: false,
            }),
        });
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Failed to preview CDP fallback');
        }
        const payload = await response.json();
        output.textContent = JSON.stringify(payload, null, 2);
    }

    globalScope.CdpControllerModule = {
        validatePreviewPayloadInput,
        collectCdpMappingFromForm,
        normalizeImportedCdpMapping,
        loadCdpConfig,
        loadCdpMappingPresets,
        applyCdpPresetToForm,
        exportCdpMappingJson,
        importCdpMappingJson,
        saveCdpConfig,
        loadCdpProfiles,
        syncCdpProfiles,
        loadCdpSchedulerStatus,
        runCdpSchedulerNow,
        loadCdpDiagnostics,
        deriveCdpProfile,
        previewCdpMapping,
        previewCdpFallback,
    };
})(window);
