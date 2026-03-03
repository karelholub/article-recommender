from __future__ import annotations

import traceback
from datetime import datetime

from flask import Blueprint, current_app, jsonify, request

recommendations_blueprint = Blueprint('recommendations_blueprint', __name__)


def _store():
    return current_app.config.get('APP_STORE')


def _recommender():
    return current_app.config.get('APP_RECOMMENDER')


def _logger():
    return current_app.config['APP_LOGGER']


def _helpers():
    return current_app.config['APP_HELPERS']


@recommendations_blueprint.route('/api/recommendations/query', methods=['POST'])
def query_recommendations():
    if not _recommender() or not _store():
        return jsonify({'error': 'Recommender not initialized'}), 500

    try:
        payload = request.get_json() or {}
        if not isinstance(payload, dict):
            return _helpers()['validation_error']('Request body must be an object', code='invalid_payload_type')
        idempotency_key = _helpers()['read_idempotency_key'](payload)
        if idempotency_key:
            cached = _store().get_idempotency_record('recommendations_query', idempotency_key)
            if cached:
                response = jsonify(cached['response'])
                response.headers['X-Idempotent-Replay'] = 'true'
                response.headers['X-Cache-Hit'] = 'true' if cached['response'].get('cache_hit') else 'false'
                return response, int(cached['status_code'])
        result = _helpers()['execute_recommendation_query'](payload, api_surface='query')
        response = jsonify(result)
        response.headers['X-Cache-Hit'] = 'true' if result.get('cache_hit') else 'false'
        if idempotency_key:
            _store().save_idempotency_record(
                endpoint='recommendations_query',
                key=idempotency_key,
                status_code=200,
                response_payload=result,
            )
        return response
    except Exception as e:
        _logger().error(f'Error querying recommendations: {str(e)}')
        _logger().error(traceback.format_exc())
        return jsonify({'error': str(e)}), 400


@recommendations_blueprint.route('/api/recommendations/why-not', methods=['POST'])
def why_not_recommendation():
    if not _recommender() or not _store():
        return jsonify({'error': 'Recommender not initialized'}), 500
    try:
        payload = request.get_json() or {}
        target_article_id = str(payload.get('article_id', '')).strip() or None
        response = _helpers()['execute_recommendation_diagnostics'](payload)
        selected = {str(item.get('article_id')): idx + 1 for idx, item in enumerate(response.get('recommendations') or [])}
        pre_excluded = response.get('diagnostics', {}).get('excluded') or []
        scenario_decisions = (response.get('scenario_trace') or {}).get('decisions') or []

        reason_index = {}
        for item in pre_excluded:
            aid = str(item.get('article_id') or '').strip()
            if aid and aid not in reason_index:
                reason_index[aid] = {'stage': 'ranking', **item}
        for item in scenario_decisions:
            aid = str(item.get('article_id') or '').strip()
            if aid and item.get('status') == 'filtered':
                reason_index[aid] = {
                    'stage': 'scenario',
                    'reason_code': item.get('reason'),
                    'score_before': item.get('score_before'),
                }

        if target_article_id:
            shown_rank = selected.get(target_article_id)
            return jsonify(
                {
                    'api_version': 'v1',
                    'article_id': target_article_id,
                    'shown': bool(shown_rank),
                    'rank': shown_rank,
                    'reason': (None if shown_rank else reason_index.get(target_article_id, {'reason_code': 'not_in_candidate_pool'})),
                    'context': {
                        'config_id': response.get('config_id'),
                        'scenario_id': response.get('scenario_id'),
                        'selected_sources': response.get('selected_sources'),
                    },
                }
            )

        reason_counts = {}
        for item in reason_index.values():
            reason = str(item.get('reason_code') or 'unknown')
            reason_counts[reason] = reason_counts.get(reason, 0) + 1
        return jsonify(
            {
                'api_version': 'v1',
                'explainability_schema_version': 'v2',
                'reason_counts': reason_counts,
                'excluded_samples': [{'article_id': aid, **info} for aid, info in list(reason_index.items())[:50]],
                'selected_count': len(selected),
                'context': {
                    'config_id': response.get('config_id'),
                    'scenario_id': response.get('scenario_id'),
                    'selected_sources': response.get('selected_sources'),
                },
            }
        )
    except Exception as e:
        _logger().error(f'Error computing why-not recommendation: {str(e)}')
        _logger().error(traceback.format_exc())
        return jsonify({'error': str(e)}), 400


@recommendations_blueprint.route('/api/recommendations/explain-item', methods=['POST'])
def explain_recommendation_item():
    if not _recommender() or not _store():
        return jsonify({'error': 'Recommender not initialized'}), 500
    try:
        payload = request.get_json() or {}
        article_id = str(payload.get('article_id', '')).strip()
        if not article_id:
            return jsonify({'error': 'article_id is required'}), 400
        response = _helpers()['execute_recommendation_diagnostics'](payload)
        recommendations = response.get('recommendations') or []
        diagnostics = response.get('diagnostics') or {}
        scenario_trace = response.get('scenario_trace') or {}
        selected = {str(item.get('article_id')): idx + 1 for idx, item in enumerate(recommendations)}
        selected_item = next((item for item in recommendations if str(item.get('article_id')) == article_id), None)
        excluded_item = next(
            (item for item in (diagnostics.get('excluded') or []) if str(item.get('article_id') or '').strip() == article_id),
            None,
        )
        scenario_decision = next(
            (
                item
                for item in (scenario_trace.get('decisions') or [])
                if str(item.get('article_id') or '').strip() == article_id
            ),
            None,
        )

        ranking_status = 'pass'
        ranking_reason = 'candidate_in_ranked_list'
        if excluded_item:
            ranking_status = 'fail'
            ranking_reason = str(excluded_item.get('reason_code') or 'excluded_before_final_selection')
        scenario_status = 'pass'
        scenario_reason = 'kept_or_not_applicable'
        if scenario_decision and scenario_decision.get('status') == 'filtered':
            scenario_status = 'fail'
            scenario_reason = str(scenario_decision.get('reason') or 'scenario_filtered')
        final_status = 'pass' if selected_item else 'fail'
        final_reason = 'selected_in_top_n' if selected_item else 'not_selected_in_top_n'

        return jsonify(
            {
                'api_version': 'v1',
                'article_id': article_id,
                'shown': bool(selected_item),
                'rank': selected.get(article_id),
                'item': selected_item,
                'ranking_exclusion': excluded_item,
                'scenario_decision': scenario_decision,
                'pass_fail_trail': [
                    {'stage': 'ranking_eligibility', 'status': ranking_status, 'reason': ranking_reason},
                    {'stage': 'scenario_rules', 'status': scenario_status, 'reason': scenario_reason},
                    {'stage': 'final_selection', 'status': final_status, 'reason': final_reason},
                ],
                'context': {
                    'config_id': response.get('config_id'),
                    'scenario_id': response.get('scenario_id'),
                    'selected_sources': response.get('selected_sources'),
                    'inspect_count': response.get('inspect_count'),
                },
            }
        )
    except Exception as e:
        _logger().error(f'Error explaining recommendation item: {str(e)}')
        _logger().error(traceback.format_exc())
        return jsonify({'error': str(e)}), 400


@recommendations_blueprint.route('/api/explainability/schema', methods=['GET'])
def explainability_schema():
    return jsonify(
        {
            'api_version': 'v1',
            'schema_version': 'v2',
            'ranking_reason_codes': [
                'hard_max_age_days',
                'min_freshness',
                'dedup_title',
                'dedup_url',
                'cap_source',
                'cap_topic',
                'cap_section',
            ],
            'scenario_reason_codes': [
                'source_not_included',
                'source_excluded',
                'section_not_included',
                'section_excluded',
                'article_excluded',
                'keyword_not_included',
                'keyword_excluded',
                'too_old',
                'below_min_freshness',
                'below_min_score',
                'dedup_title',
                'dedup_url',
                'cap_source',
                'cap_topic',
                'cap_section',
            ],
            'recommendation_fields': [
                'features',
                'feature_contributions',
                'explanation',
                'explanation_details',
                'scenario_boost',
            ],
        }
    )


@recommendations_blueprint.route('/api/recommendations/batch', methods=['POST'])
def query_recommendations_batch():
    if not _recommender() or not _store():
        return jsonify({'error': 'Recommender not initialized'}), 500
    try:
        started_at = datetime.now()
        payload = request.get_json() or {}
        requests_payload = payload.get('requests') or []
        if not isinstance(requests_payload, list) or not requests_payload:
            return jsonify({'error': 'requests must be a non-empty array'}), 400
        if len(requests_payload) > 100:
            return jsonify({'error': 'Maximum batch size is 100'}), 400
        continue_on_error = bool(payload.get('continue_on_error', True))

        results = []
        success_count = 0
        for index, item in enumerate(requests_payload):
            if not isinstance(item, dict):
                error_payload = {
                    'index': index,
                    'request_id': None,
                    'status': 'error',
                    'error': 'Each request item must be an object',
                }
                results.append(error_payload)
                if not continue_on_error:
                    return jsonify(
                        {
                            'api_version': 'v1',
                            'count': len(requests_payload),
                            'success_count': success_count,
                            'error_count': len(results) - success_count,
                            'results': results,
                        }
                    ), 400
                continue

            request_id = str(item.get('request_id', '')).strip() or None
            try:
                result = _helpers()['execute_recommendation_query'](item, api_surface='batch')
                results.append(
                    {
                        'index': index,
                        'request_id': request_id,
                        'status': 'ok',
                        'result': result,
                    }
                )
                success_count += 1
            except Exception as exc:
                results.append(
                    {
                        'index': index,
                        'request_id': request_id,
                        'status': 'error',
                        'error': str(exc),
                    }
                )
                if not continue_on_error:
                    return jsonify(
                        {
                            'api_version': 'v1',
                            'count': len(requests_payload),
                            'success_count': success_count,
                            'error_count': len(results) - success_count,
                            'results': results,
                        }
                    ), 400

        return jsonify(
            {
                'api_version': 'v1',
                'count': len(requests_payload),
                'success_count': success_count,
                'error_count': len(results) - success_count,
                'duration_ms': int((datetime.now() - started_at).total_seconds() * 1000),
                'results': results,
            }
        )
    except Exception as e:
        _logger().error(f'Error running batch recommendations: {str(e)}')
        _logger().error(traceback.format_exc())
        return jsonify({'error': str(e)}), 400


@recommendations_blueprint.route('/api/recommendations/cms', methods=['POST'])
@recommendations_blueprint.route('/api/v1/recommendations/cms', methods=['POST'])
def recommendations_cms():
    if not _recommender() or not _store():
        return jsonify({'error': 'Recommender not initialized'}), 500

    try:
        started_at = datetime.now()
        payload = request.get_json() or {}
        if not isinstance(payload, dict):
            return _helpers()['validation_error']('Request body must be an object', code='invalid_payload_type')
        idempotency_key = _helpers()['read_idempotency_key'](payload)
        if idempotency_key:
            cached = _store().get_idempotency_record('recommendations_cms', idempotency_key)
            if cached:
                response = jsonify(cached['response'])
                response.headers['X-Idempotent-Replay'] = 'true'
                return response, int(cached['status_code'])
        data = payload.get('request') if isinstance(payload.get('request'), dict) else payload
        if not isinstance(data, dict):
            return _helpers()['validation_error']('request must be an object', code='invalid_request_object')
        user_id = str(data.get('user_id', 'anonymous')).strip() or 'anonymous'
        external_user_id = str(data.get('external_user_id', '')).strip() or None
        effective_user_id = _helpers()['resolve_effective_user_id'](user_id, external_user_id)
        top_n = max(1, min(20, int(data.get('limit', data.get('top_n', 5)))))
        user_reads = data.get('user_reads') or _recommender().user_profiles.get(effective_user_id, [])
        if not user_reads:
            user_reads = _recommender().user_profiles.get(user_id, [])
        requested_sources = data.get('sources') or []
        config_explicit = bool(str(data.get('config_id', '')).strip())
        config_id = str(data.get('config_id', 'balanced')).strip() or 'balanced'
        experiment = data.get('experiment')
        scenario_id = str(data.get('scenario_id', '')).strip() or None
        scenario_explicit = bool(scenario_id)
        cdp_context = _helpers()['resolve_cdp_personalization'](
            external_user_id=external_user_id,
            requested_sources=requested_sources,
            scenario_id=scenario_id,
            config_id=config_id,
            scenario_explicit=scenario_explicit,
            config_explicit=config_explicit,
        )
        requested_sources = cdp_context.get('requested_sources') or requested_sources
        if not scenario_explicit and cdp_context.get('selected_scenario_id'):
            scenario_id = cdp_context.get('selected_scenario_id')
        if not config_explicit and cdp_context.get('selected_config_id'):
            config_id = cdp_context.get('selected_config_id')
        scenario = _store().get_scenario(scenario_id) if scenario_id else None
        if scenario and scenario.get('rule_set', {}).get('include_sources') and not requested_sources:
            requested_sources = scenario['rule_set']['include_sources']
        if scenario and scenario.get('rule_set', {}).get('ranking_config_id'):
            config_id = scenario['rule_set']['ranking_config_id']

        experiment_assignment = _helpers()['resolve_experiment_assignment'](experiment, effective_user_id)
        if experiment_assignment:
            if experiment_assignment.get('selected_scenario_id'):
                scenario_id = experiment_assignment['selected_scenario_id']
                scenario = _store().get_scenario(scenario_id) if scenario_id else None
            if experiment_assignment.get('selected_config_id'):
                config_id = experiment_assignment['selected_config_id']
            if experiment_assignment.get('selected_sources'):
                requested_sources = experiment_assignment['selected_sources']

        decision_context = _helpers()['build_decision_context'](requested_sources, config_id, None)
        selected_sources = decision_context['selected_sources']
        effective_ranking_config = decision_context['effective_ranking_config']
        cdp_source_overrides = cdp_context.get('source_weight_overrides') or {}
        if cdp_source_overrides:
            source_weights = dict(effective_ranking_config.get('source_weights') or {})
            for source, weight in cdp_source_overrides.items():
                if source in selected_sources and weight > 0:
                    source_weights[source] = float(weight)
            effective_ranking_config['source_weights'] = source_weights
        cache_key = _helpers()['build_recommendation_cache_key'](
            'cms',
            {
                'user_id': user_id,
                'external_user_id': external_user_id,
                'user_reads': user_reads,
                'top_n': top_n,
                'sources': selected_sources,
                'config_id': decision_context['effective_config_id'],
                'scenario_id': scenario_id,
                'ranking_config': effective_ranking_config,
                'experiment': experiment_assignment or {},
            },
        )
        cached_recs = _helpers()['get_cached_recommendations'](cache_key)
        cache_hit = cached_recs is not None
        if cached_recs is not None:
            recs = cached_recs
        else:
            recs = (
                _recommender().recommend_for_user(
                    effective_user_id,
                    _recommender().article_vectors,
                    user_reads,
                    top_n=top_n,
                    sources=selected_sources,
                    config_id=decision_context['effective_config_id'],
                    ranking_config=effective_ranking_config,
                )
                if selected_sources
                else []
            )
            _helpers()['set_cached_recommendations'](cache_key, recs)
        recs, scenario_trace = _helpers()['apply_scenario_rules'](recs, scenario, include_decisions=True)
        recs = recs[:top_n]

        run_id = _store().persist_recommendation_run(
            user_id=effective_user_id,
            config_id=decision_context['effective_config_id'],
            config_version=decision_context['config_version'],
            request_payload={
                'user_id': user_id,
                'external_user_id': external_user_id,
                'effective_user_id': effective_user_id,
                'scenario_id': scenario_id,
                'sources': selected_sources,
                'top_n': top_n,
                'api_surface': 'cms',
                'scenario_trace': scenario_trace,
                'experiment_assignment': experiment_assignment,
                'cdp_context': cdp_context,
            },
            recommendations=recs,
            request_duration_ms=int((datetime.now() - started_at).total_seconds() * 1000),
        )

        _store().record_events(
            [
                {
                    'event_type': 'impression',
                    'run_id': run_id,
                    'article_id': rec.get('article_id'),
                    'scenario_id': scenario_id,
                    'user_id': effective_user_id,
                    'external_user_id': external_user_id,
                    'rank_position': idx,
                    'metadata': {'surface': 'cms', 'placement': data.get('placement')},
                }
                for idx, rec in enumerate(recs, start=1)
            ]
        )

        response_payload = {
            'api_version': 'v1',
            'request_id': run_id,
            'user': {
                'user_id': user_id,
                'external_user_id': external_user_id,
                'effective_user_id': effective_user_id,
            },
            'placement': data.get('placement'),
            'scenario_id': scenario_id,
            'config_id': decision_context['effective_config_id'],
            'config_version': decision_context['config_version'],
            'items': [
                {
                    'rank': idx,
                    'article_id': rec.get('article_id'),
                    'title': rec.get('title'),
                    'url': rec.get('url'),
                    'source': rec.get('source'),
                    'score': rec.get('score'),
                    'explanation': rec.get('explanation'),
                    'feature_contributions': rec.get('feature_contributions'),
                }
                for idx, rec in enumerate(recs, start=1)
            ],
            'trace': {
                'selected_sources': selected_sources,
                'source_defaults_applied': decision_context['source_defaults_applied'],
                'scenario_trace': scenario_trace,
                'experiment_assignment': experiment_assignment,
                'cdp_context': cdp_context,
                'cache_hit': cache_hit,
            },
        }
        if idempotency_key:
            _store().save_idempotency_record(
                endpoint='recommendations_cms',
                key=idempotency_key,
                status_code=200,
                response_payload=response_payload,
            )
        response = jsonify(response_payload)
        response.headers['X-Cache-Hit'] = 'true' if cache_hit else 'false'
        return response
    except Exception as e:
        _logger().error(f'Error in CMS recommendations endpoint: {str(e)}')
        _logger().error(traceback.format_exc())
        return jsonify({'error': str(e)}), 400


@recommendations_blueprint.route('/api/similar/<article_id>')
def get_similar_articles(article_id):
    if not _recommender():
        return jsonify({'error': 'Recommender not initialized'}), 500

    try:
        top_n = int(request.args.get('top_n', 5))
        config_id = request.args.get('config_id', 'balanced')
        requested_sources = _helpers()['parse_sources_param'](request.args.get('sources', ''))
        decision_context = _helpers()['build_decision_context'](requested_sources, config_id, None)
        effective_config_id = decision_context['effective_config_id']
        selected_sources = decision_context['selected_sources']
        effective_ranking_config = decision_context['effective_ranking_config']

        if selected_sources:
            similar_articles = _recommender().recommend_for_user(
                'demo_user',
                _recommender().article_vectors,
                [article_id],
                top_n=top_n,
                sources=selected_sources,
                config_id=effective_config_id,
                ranking_config=effective_ranking_config,
            )
        else:
            similar_articles = []

        for article in similar_articles:
            similar_id = article['article_id']
            if similar_id in _recommender().article_vectors:
                article['content'] = _recommender().article_vectors[similar_id]['metadata'].get('content', '')

        return jsonify(similar_articles)
    except Exception as e:
        _logger().error(f'Error getting similar articles: {str(e)}')
        _logger().error(traceback.format_exc())
        return jsonify({'error': str(e)}), 400


@recommendations_blueprint.route('/api/recommendation-context', methods=['POST'])
def recommendation_context():
    if not _recommender() or not _store():
        return jsonify({'error': 'Recommender not initialized'}), 500

    try:
        payload = request.get_json() or {}
        requested_sources = payload.get('sources') or []
        config_explicit = bool(str(payload.get('config_id', '')).strip())
        config_id = str(payload.get('config_id', 'balanced')).strip() or 'balanced'
        ranking_config = payload.get('ranking_config')
        external_user_id = str(payload.get('external_user_id', '')).strip() or None
        scenario_id = (payload.get('scenario_id') or '').strip() or None
        scenario_explicit = bool(scenario_id)
        cdp_context = _helpers()['resolve_cdp_personalization'](
            external_user_id=external_user_id,
            requested_sources=requested_sources,
            scenario_id=scenario_id,
            config_id=config_id,
            scenario_explicit=scenario_explicit,
            config_explicit=config_explicit,
        )
        requested_sources = cdp_context.get('requested_sources') or requested_sources
        if not scenario_explicit and cdp_context.get('selected_scenario_id'):
            scenario_id = cdp_context.get('selected_scenario_id')
        if not config_explicit and cdp_context.get('selected_config_id'):
            config_id = cdp_context.get('selected_config_id')
        scenario = _store().get_scenario(scenario_id) if scenario_id else None
        if scenario and scenario.get('rule_set', {}).get('include_sources') and not requested_sources:
            requested_sources = scenario['rule_set']['include_sources']
        if scenario and scenario.get('rule_set', {}).get('ranking_config_id') and not ranking_config:
            config_id = scenario['rule_set']['ranking_config_id']
        context = _helpers()['build_decision_context'](requested_sources, config_id, ranking_config)
        cdp_source_overrides = cdp_context.get('source_weight_overrides') or {}
        if cdp_source_overrides:
            source_weights = dict(context['effective_ranking_config'].get('source_weights') or {})
            for source, weight in cdp_source_overrides.items():
                if source in context['selected_sources'] and weight > 0:
                    source_weights[source] = float(weight)
            context['effective_ranking_config']['source_weights'] = source_weights
        context['scenario_id'] = scenario_id
        context['scenario'] = scenario
        context['cdp_context'] = cdp_context
        if scenario:
            context['scenario_rule_set'] = scenario.get('rule_set', {})
        return jsonify(context)
    except Exception as e:
        _logger().error(f'Error building recommendation context: {str(e)}')
        _logger().error(traceback.format_exc())
        return jsonify({'error': str(e)}), 400


@recommendations_blueprint.route('/api/recommendation-runs')
def list_recommendation_runs():
    store = _store()
    if not store:
        return jsonify({'error': 'Store unavailable'}), 500

    try:
        limit = max(1, min(200, int(request.args.get('limit', 20))))
        offset = max(0, int(request.args.get('offset', 0)))
        rows = store.list_runs(limit=limit + 1, offset=offset)
        has_more = len(rows) > limit
        runs = rows[:limit]
        return jsonify(
            {
                'runs': runs,
                'count': len(runs),
                'limit': limit,
                'offset': offset,
                'has_more': has_more,
                'next_offset': (offset + limit) if has_more else None,
            }
        )
    except Exception as e:
        _logger().error(f'Error listing runs: {str(e)}')
        _logger().error(traceback.format_exc())
        return jsonify({'error': str(e)}), 500


@recommendations_blueprint.route('/api/recommendation-runs/<run_id>')
def get_recommendation_run(run_id):
    store = _store()
    if not store:
        return jsonify({'error': 'Store unavailable'}), 500

    run = store.get_run(run_id)
    if not run:
        return jsonify({'error': 'Run not found'}), 404
    return jsonify(run)


@recommendations_blueprint.route('/api/recommendation-runs/<run_id>/decision-flow')
def get_recommendation_run_decision_flow(run_id):
    store = _store()
    if not store:
        return jsonify({'error': 'Store unavailable'}), 500

    run = store.get_run(run_id)
    if not run:
        return jsonify({'error': 'Run not found'}), 404
    return jsonify(_helpers()['build_run_decision_flow'](run))
