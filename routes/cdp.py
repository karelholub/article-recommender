from __future__ import annotations

import traceback
from datetime import datetime, timedelta
from typing import Any, Dict

from flask import Blueprint, current_app, jsonify, request

from meiro_adapter import MeiroAdapter, _get_by_path

cdp_blueprint = Blueprint('cdp_blueprint', __name__)


def _helpers() -> Dict[str, Any]:
    return current_app.config['APP_HELPERS']


def _store():
    return current_app.config.get('APP_STORE')


def _provider() -> str:
    return current_app.config.get('CDP_PROVIDER', 'meiro')


def _state_lock():
    return current_app.config['CDP_STATE_LOCK']


def _state() -> Dict[str, Any]:
    return current_app.config['CDP_STATE']


def _logger():
    return current_app.config['APP_LOGGER']


@cdp_blueprint.route('/api/cdp/meiro', methods=['GET', 'PUT'])
def cdp_meiro_config():
    store = _store()
    if not store:
        return jsonify({'error': 'Store unavailable'}), 500
    h = _helpers()
    try:
        if request.method == 'GET':
            integration = store.get_cdp_integration(_provider())
            config = dict(integration.get('config') or {})
            if config.get('api_key'):
                config['api_key'] = '***'
            return jsonify(
                {
                    'provider': _provider(),
                    'enabled': bool(integration.get('enabled')),
                    'config': config,
                    'mapping': h['normalize_meiro_mapping'](integration.get('mapping')),
                    'updated_at': integration.get('updated_at'),
                }
            )

        payload = request.get_json() or {}
        integration = store.get_cdp_integration(_provider())
        current_config = dict(integration.get('config') or {})
        current_mapping = h['normalize_meiro_mapping'](integration.get('mapping'))
        next_enabled = payload.get('enabled')
        next_config = dict(current_config)
        if isinstance(payload.get('config'), dict):
            next_config.update(payload.get('config') or {})
        next_mapping = dict(current_mapping)
        if isinstance(payload.get('mapping'), dict):
            next_mapping.update(payload.get('mapping') or {})
        if str(next_config.get('api_key', '')).strip() == '***':
            next_config['api_key'] = current_config.get('api_key', '')
        stored = store.upsert_cdp_integration(
            provider=_provider(),
            config=next_config,
            mapping=h['normalize_meiro_mapping'](next_mapping),
            enabled=(bool(next_enabled) if next_enabled is not None else None),
        )
        h['record_audit'](
            action='update',
            resource_type='cdp_integration',
            resource_id=_provider(),
            payload=payload,
            extra={'enabled': stored.get('enabled')},
        )
        safe_config = dict(stored.get('config') or {})
        if safe_config.get('api_key'):
            safe_config['api_key'] = '***'
        return jsonify(
            {
                'provider': _provider(),
                'enabled': bool(stored.get('enabled')),
                'config': safe_config,
                'mapping': h['normalize_meiro_mapping'](stored.get('mapping')),
                'updated_at': stored.get('updated_at'),
            }
        )
    except Exception as e:
        _logger().error(f'Error handling CDP config: {str(e)}')
        _logger().error(traceback.format_exc())
        return jsonify({'error': str(e)}), 400


@cdp_blueprint.route('/api/cdp/meiro/presets', methods=['GET'])
def cdp_meiro_mapping_presets():
    h = _helpers()
    presets = []
    for preset_id, preset in current_app.config.get('MEIRO_MAPPING_PRESETS', {}).items():
        presets.append(
            {
                'preset_id': preset_id,
                'label': str(preset.get('label') or preset_id),
                'mapping': h['normalize_meiro_mapping'](preset.get('mapping') or {}),
            }
        )
    presets.sort(key=lambda item: item['preset_id'])
    return jsonify({'provider': _provider(), 'presets': presets, 'count': len(presets)})


@cdp_blueprint.route('/api/cdp/meiro/fallback-preview', methods=['POST'])
def cdp_meiro_fallback_preview():
    store = _store()
    if not store:
        return jsonify({'error': 'Store unavailable'}), 500
    h = _helpers()
    try:
        payload = request.get_json(silent=True) or {}
        external_user_id = str(payload.get('external_user_id', '')).strip() or None
        requested_sources = h['normalize_string_list'](payload.get('sources'))
        scenario_id = str(payload.get('scenario_id', '')).strip() or None
        config_id = str(payload.get('config_id', 'balanced')).strip() or 'balanced'
        scenario_explicit = bool(payload.get('scenario_explicit', bool(scenario_id)))
        config_explicit = bool(payload.get('config_explicit', bool(str(payload.get('config_id', '')).strip())))
        context = h['resolve_cdp_personalization'](
            external_user_id=external_user_id,
            requested_sources=requested_sources,
            scenario_id=scenario_id,
            config_id=config_id,
            scenario_explicit=scenario_explicit,
            config_explicit=config_explicit,
        )
        integration = store.get_cdp_integration(_provider())
        mapping = h['normalize_meiro_mapping'](integration.get('mapping'))
        return jsonify(
            {
                'provider': _provider(),
                'external_user_id': external_user_id,
                'requested_sources': requested_sources,
                'context': context,
                'mapping': {
                    'personalization_mode': mapping.get('personalization_mode'),
                    'fallback_mode': mapping.get('fallback_mode'),
                    'freshness_sla_hours': mapping.get('freshness_sla_hours'),
                },
            }
        )
    except Exception as e:
        _logger().error(f'Error previewing CDP fallback behavior: {str(e)}')
        _logger().error(traceback.format_exc())
        return jsonify({'error': str(e)}), 400


@cdp_blueprint.route('/api/cdp/meiro/profiles', methods=['GET'])
def cdp_meiro_profiles():
    store = _store()
    if not store:
        return jsonify({'error': 'Store unavailable'}), 500
    try:
        limit = max(1, min(200, int(request.args.get('limit', 50))))
        offset = max(0, int(request.args.get('offset', 0)))
        rows = store.list_cdp_profiles(_provider(), limit=limit + 1, offset=offset)
        has_more = len(rows) > limit
        profiles = rows[:limit]
        return jsonify(
            {
                'provider': _provider(),
                'profiles': profiles,
                'count': len(profiles),
                'limit': limit,
                'offset': offset,
                'has_more': has_more,
                'next_offset': (offset + limit) if has_more else None,
            }
        )
    except Exception as e:
        _logger().error(f'Error listing CDP profiles: {str(e)}')
        _logger().error(traceback.format_exc())
        return jsonify({'error': str(e)}), 400


@cdp_blueprint.route('/api/cdp/meiro/profiles/<external_user_id>', methods=['GET'])
def cdp_meiro_profile_detail(external_user_id):
    store = _store()
    if not store:
        return jsonify({'error': 'Store unavailable'}), 500
    profile = store.get_cdp_profile(_provider(), external_user_id)
    if not profile:
        return jsonify({'error': 'Profile not found'}), 404
    return jsonify(profile)


@cdp_blueprint.route('/api/cdp/meiro/profiles/<external_user_id>/derive', methods=['GET', 'POST'])
def cdp_meiro_profile_derive(external_user_id):
    store = _store()
    if not store:
        return jsonify({'error': 'Store unavailable'}), 500
    h = _helpers()
    profile = store.get_cdp_profile(_provider(), external_user_id)
    if not profile:
        return jsonify({'error': 'Profile not found'}), 404
    integration = store.get_cdp_integration(_provider())
    mapping = h['normalize_meiro_mapping'](integration.get('mapping'))
    derived = h['derive_reco_fields_from_meiro_traits'](profile.get('traits') or {})
    guardrail = h['apply_derivation_guardrails'](derived, mapping)
    diff = h['build_derivation_diff'](profile, guardrail)
    if request.method == 'GET':
        return jsonify(
            {
                'provider': _provider(),
                'external_user_id': external_user_id,
                'derived': derived,
                'guardrail': guardrail,
                'diff': diff,
                'persisted': False,
            }
        )
    try:
        payload = request.get_json(silent=True) or {}
        persist = bool(payload.get('persist', True))
        force = bool(payload.get('force', False))
        if not persist:
            return jsonify(
                {
                    'provider': _provider(),
                    'external_user_id': external_user_id,
                    'derived': derived,
                    'guardrail': guardrail,
                    'diff': diff,
                    'persisted': False,
                }
            )
        if not guardrail.get('pass') and not force:
            return jsonify(
                {
                    'error': 'Derivation blocked by guardrails',
                    'provider': _provider(),
                    'external_user_id': external_user_id,
                    'derived': derived,
                    'guardrail': guardrail,
                    'diff': diff,
                    'persisted': False,
                }
            ), 409
        result = guardrail.get('result') or {}
        traits = dict(profile.get('traits') or {})
        traits['preferred_sources'] = result.get('preferred_sources') or []
        traits['source_weights'] = result.get('source_weights') or {}
        segments = sorted(set((profile.get('segments') or []) + (result.get('derived_segments') or [])))
        stored = store.upsert_cdp_profile(
            provider=_provider(),
            external_user_id=external_user_id,
            traits=traits,
            segments=segments,
            raw_payload=profile.get('raw') or {},
        )
        h['record_audit'](
            action='derive',
            resource_type='cdp_profile',
            resource_id=external_user_id,
            payload=payload,
            extra={'provider': _provider(), 'persisted': True, 'guardrail_pass': bool(guardrail.get('pass')), 'forced': force},
        )
        return jsonify(
            {
                'provider': _provider(),
                'external_user_id': external_user_id,
                'derived': derived,
                'guardrail': guardrail,
                'diff': diff,
                'persisted': True,
                'forced': force,
                'profile': stored,
            }
        )
    except Exception as e:
        _logger().error(f'Error deriving CDP profile fields: {str(e)}')
        _logger().error(traceback.format_exc())
        return jsonify({'error': str(e)}), 400


@cdp_blueprint.route('/api/cdp/meiro/mapping/preview', methods=['POST'])
def cdp_meiro_mapping_preview():
    store = _store()
    if not store:
        return jsonify({'error': 'Store unavailable'}), 500
    h = _helpers()
    try:
        payload = request.get_json() or {}
        sample_payload = payload.get('payload')
        if not isinstance(sample_payload, dict):
            return jsonify({'error': 'payload must be a JSON object'}), 400

        integration = store.get_cdp_integration(_provider())
        mapping = h['normalize_meiro_mapping'](integration.get('mapping'))
        override = payload.get('mapping')
        if isinstance(override, dict):
            merged = dict(mapping)
            merged.update(override)
            mapping = h['normalize_meiro_mapping'](merged)

        adapter = MeiroAdapter(integration.get('config') or {})
        profile = adapter.normalize_profile(
            sample_payload,
            mapping=mapping,
            fallback_external_user_id=str(payload.get('fallback_external_user_id', '')).strip(),
        )
        derived = h['derive_reco_fields_from_meiro_traits'](profile.traits or {})
        guardrail = h['apply_derivation_guardrails'](derived, mapping)
        existing_profile = store.get_cdp_profile(_provider(), profile.external_user_id) or {
            'traits': {},
            'segments': [],
        }
        diff = h['build_derivation_diff'](existing_profile, guardrail)

        return jsonify(
            {
                'provider': _provider(),
                'external_user_id': profile.external_user_id,
                'segments': profile.segments,
                'trait_keys_count': len(profile.traits.keys()),
                'trait_keys_sample': sorted(list(profile.traits.keys()))[:25],
                'path_resolution': {
                    'external_id_path': {
                        'path': mapping.get('external_id_path'),
                        'value': _get_by_path(sample_payload, mapping.get('external_id_path', ''), None),
                    },
                    'traits_path': {
                        'path': mapping.get('traits_path'),
                        'is_object': isinstance(_get_by_path(sample_payload, mapping.get('traits_path', ''), {}), dict),
                    },
                    'segments_path': {
                        'path': mapping.get('segments_path'),
                        'value': _get_by_path(sample_payload, mapping.get('segments_path', ''), []),
                    },
                },
                'derived': derived,
                'guardrail': guardrail,
                'diff': diff,
            }
        )
    except Exception as e:
        _logger().error(f'Error previewing CDP mapping: {str(e)}')
        _logger().error(traceback.format_exc())
        return jsonify({'error': str(e)}), 400


@cdp_blueprint.route('/api/cdp/meiro/profiles/upsert', methods=['POST'])
def cdp_meiro_profile_upsert():
    store = _store()
    if not store:
        return jsonify({'error': 'Store unavailable'}), 500
    h = _helpers()
    try:
        payload = request.get_json() or {}
        integration = store.get_cdp_integration(_provider())
        mapping = h['normalize_meiro_mapping'](integration.get('mapping'))
        adapter = MeiroAdapter(integration.get('config') or {})

        if isinstance(payload.get('payload'), dict):
            profile = adapter.normalize_profile(
                payload['payload'],
                mapping=mapping,
                fallback_external_user_id=str(payload.get('external_id', '')).strip(),
            )
            external_id = profile.external_user_id
            traits = profile.traits
            segments = profile.segments
            raw_payload = payload.get('payload')
        else:
            external_id = str(payload.get('external_id', '')).strip()
            if not external_id:
                return jsonify({'error': 'external_id is required'}), 400
            traits = payload.get('traits') or {}
            segments = payload.get('segments') or []
            raw_payload = payload.get('raw_payload') or payload

        stored = store.upsert_cdp_profile(
            provider=_provider(),
            external_user_id=external_id,
            traits=traits,
            segments=segments,
            raw_payload=raw_payload,
        )
        h['record_audit'](
            action='upsert',
            resource_type='cdp_profile',
            resource_id=external_id,
            payload=payload,
            extra={'provider': _provider()},
        )
        return jsonify(stored), 201
    except Exception as e:
        _logger().error(f'Error upserting CDP profile: {str(e)}')
        _logger().error(traceback.format_exc())
        return jsonify({'error': str(e)}), 400


@cdp_blueprint.route('/api/cdp/meiro/sync', methods=['POST'])
def cdp_meiro_sync_profiles():
    store = _store()
    if not store:
        return jsonify({'error': 'Store unavailable'}), 500
    h = _helpers()
    try:
        payload = request.get_json() or {}
        requested_ids = [str(item).strip() for item in (payload.get('external_user_ids') or []) if str(item).strip()]
        result = h['execute_cdp_sync_run'](
            trigger='manual',
            external_user_ids=(requested_ids if requested_ids else None),
        )
        h['record_audit'](
            action='sync',
            resource_type='cdp_sync',
            resource_id=result.get('run_id', ''),
            payload=payload,
            extra={
                'run_id': result.get('run_id'),
                'attempted': result.get('attempted', 0),
                'synced': result.get('synced_count', 0),
                'errors': result.get('error_count', 0),
            },
        )
        return jsonify(result)
    except Exception as e:
        _logger().error(f'Error syncing CDP profiles: {str(e)}')
        _logger().error(traceback.format_exc())
        return jsonify({'error': str(e)}), 400


@cdp_blueprint.route('/api/cdp/meiro/sync-runs', methods=['GET'])
def cdp_meiro_sync_runs():
    store = _store()
    if not store:
        return jsonify({'error': 'Store unavailable'}), 500
    try:
        limit = max(1, min(100, int(request.args.get('limit', 20))))
        rows = store.list_cdp_sync_runs(_provider(), limit=limit)
        return jsonify({'provider': _provider(), 'runs': rows, 'count': len(rows)})
    except Exception as e:
        _logger().error(f'Error listing CDP sync runs: {str(e)}')
        _logger().error(traceback.format_exc())
        return jsonify({'error': str(e)}), 400


@cdp_blueprint.route('/api/cdp/meiro/sync-runs/<run_id>', methods=['GET'])
def cdp_meiro_sync_run_detail(run_id):
    store = _store()
    if not store:
        return jsonify({'error': 'Store unavailable'}), 500
    run = store.get_cdp_sync_run(run_id)
    if not run:
        return jsonify({'error': 'Sync run not found'}), 404
    return jsonify(run)


@cdp_blueprint.route('/api/cdp/meiro/scheduler/status', methods=['GET'])
def cdp_meiro_scheduler_status():
    with _state_lock():
        snapshot = dict(_state())
    snapshot['provider'] = _provider()
    return jsonify(snapshot)


@cdp_blueprint.route('/api/cdp/meiro/scheduler/run-now', methods=['POST'])
def cdp_meiro_scheduler_run_now():
    store = _store()
    if not store:
        return jsonify({'error': 'Store unavailable'}), 500
    h = _helpers()
    try:
        payload = request.get_json(silent=True) or {}
        requested_ids = [str(item).strip() for item in (payload.get('external_user_ids') or []) if str(item).strip()]
        result = h['execute_cdp_sync_run'](
            trigger='run_now',
            external_user_ids=(requested_ids if requested_ids else None),
        )
        with _state_lock():
            state = _state()
            state['runs_total'] += 1
            state['last_run_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            state['last_result'] = {
                'status': result.get('run', {}).get('status', result.get('status')),
                'attempted': result.get('attempted', 0),
                'synced_count': result.get('synced_count', 0),
                'error_count': result.get('error_count', 0),
            }
            if result.get('error_count', 0) > 0:
                state['errors_total'] += 1
                state['last_error'] = f"{result.get('error_count')} errors"
            else:
                state['last_error'] = None
        return jsonify(result)
    except Exception as e:
        _logger().error(f'Error executing CDP run-now: {str(e)}')
        _logger().error(traceback.format_exc())
        return jsonify({'error': str(e)}), 400


@cdp_blueprint.route('/api/cdp/meiro/diagnostics', methods=['GET'])
def cdp_meiro_diagnostics():
    store = _store()
    if not store:
        return jsonify({'error': 'Store unavailable'}), 500
    h = _helpers()
    try:
        freshness_hours = max(1, min(24 * 30, int(request.args.get('freshness_hours', 24))))
        profile_limit = max(1, min(10000, int(request.args.get('profile_limit', 2000))))
        run_limit = max(1, min(10000, int(request.args.get('run_limit', 2000))))
        sync_run_limit = max(1, min(200, int(request.args.get('sync_run_limit', 50))))

        integration = store.get_cdp_integration(_provider())
        profiles = store.list_cdp_profiles(_provider(), limit=profile_limit, offset=0)
        now = datetime.now()
        stale_cutoff = now - timedelta(hours=freshness_hours)
        freshness = {'fresh': 0, 'stale': 0, 'unknown': 0}
        for item in profiles:
            synced_at = h['safe_parse_timestamp'](str(item.get('synced_at', '')))
            if synced_at is None:
                freshness['unknown'] += 1
            elif synced_at >= stale_cutoff:
                freshness['fresh'] += 1
            else:
                freshness['stale'] += 1

        recent_runs = store.list_runs_with_request(limit=run_limit, offset=0, days=30)
        runs_with_external = 0
        cdp_profile_found = 0
        cdp_applied = 0
        for run in recent_runs:
            req = run.get('request') or {}
            external = str(req.get('external_user_id') or '').strip()
            if not external:
                continue
            runs_with_external += 1
            cdp_ctx = req.get('cdp_context') or {}
            if cdp_ctx.get('profile_found'):
                cdp_profile_found += 1
            if cdp_ctx.get('applied'):
                cdp_applied += 1

        sync_runs = store.list_cdp_sync_runs(_provider(), limit=sync_run_limit)
        sync_attempted = sum(int(item.get('attempted') or 0) for item in sync_runs)
        sync_synced = sum(int(item.get('synced') or 0) for item in sync_runs)
        sync_errors = sum(int(item.get('error_count') or 0) for item in sync_runs)

        return jsonify(
            {
                'provider': _provider(),
                'generated_at': now.strftime('%Y-%m-%d %H:%M:%S'),
                'integration_enabled': bool(integration.get('enabled')),
                'profiles': {
                    'count': len(profiles),
                    'freshness_hours': freshness_hours,
                    'freshness': freshness,
                    'fresh_ratio': round((freshness['fresh'] / len(profiles)), 4) if profiles else 0.0,
                    'stale_ratio': round((freshness['stale'] / len(profiles)), 4) if profiles else 0.0,
                },
                'mapping_coverage': {
                    'runs_with_external_id': runs_with_external,
                    'runs_with_cdp_profile_found': cdp_profile_found,
                    'runs_with_cdp_applied': cdp_applied,
                    'profile_found_ratio': round((cdp_profile_found / runs_with_external), 4) if runs_with_external else 0.0,
                    'applied_ratio': round((cdp_applied / runs_with_external), 4) if runs_with_external else 0.0,
                },
                'sync_runs': {
                    'count': len(sync_runs),
                    'attempted_total': sync_attempted,
                    'synced_total': sync_synced,
                    'errors_total': sync_errors,
                    'success_ratio': round((sync_synced / sync_attempted), 4) if sync_attempted else 0.0,
                    'recent': sync_runs[:10],
                },
            }
        )
    except Exception as e:
        _logger().error(f'Error building CDP diagnostics: {str(e)}')
        _logger().error(traceback.format_exc())
        return jsonify({'error': str(e)}), 400
