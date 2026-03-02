import uuid
import time
import json
import hmac
import hashlib

from app import app, recommender
from connector_pipeline import IngestResult


def test_health_endpoints():
    client = app.test_client()

    live = client.get('/healthz')
    ready = client.get('/readyz')

    assert live.status_code == 200
    assert live.get_json()['status'] == 'ok'
    assert ready.status_code in (200, 503)


def test_sources_endpoint():
    client = app.test_client()
    response = client.get('/api/sources')

    assert response.status_code == 200
    payload = response.get_json()
    assert 'sources' in payload
    assert 'total_sources' in payload
    assert isinstance(payload['sources'], list)
    if payload['sources']:
        first = payload['sources'][0]
        assert 'enabled' in first
        assert 'default_weight' in first


def test_source_settings_update():
    client = app.test_client()
    sources_payload = client.get('/api/sources').get_json()
    assert sources_payload['sources']
    source = sources_payload['sources'][0]['source']

    update = client.put(
        f'/api/source-settings/{source}',
        json={'enabled': False, 'default_weight': 1.7},
    )
    assert update.status_code == 200

    refreshed = client.get('/api/source-settings').get_json()
    match = [entry for entry in refreshed['sources'] if entry['source'] == source][0]
    assert match['enabled'] is False
    assert abs(float(match['default_weight']) - 1.7) < 1e-9

    # Restore for other tests
    restore = client.put(
        f'/api/source-settings/{source}',
        json={'enabled': True, 'default_weight': 1.0},
    )
    assert restore.status_code == 200


def test_ranking_configs_endpoint():
    client = app.test_client()
    response = client.get('/api/ranking-configs')

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['default_config_id'] == 'balanced'
    assert 'balanced' in payload['configs']
    assert 'version' in payload['configs']['balanced']


def test_custom_ranking_config_crud_and_versioning():
    client = app.test_client()
    config_id = f"custom_{uuid.uuid4().hex[:8]}"

    create = client.post(
        '/api/ranking-configs',
        json={
            'config_id': config_id,
            'weights': {'semantic': 0.5, 'freshness': 0.2, 'topic': 0.2, 'source': 0.1},
            'time_decay_days': 21,
            'source_weights': {'www.e15.cz': 1.0},
        },
    )
    assert create.status_code == 201
    created_payload = create.get_json()
    assert created_payload['config_id'] == config_id
    assert created_payload['version'] >= 1

    update = client.put(
        f'/api/ranking-configs/{config_id}',
        json={
            'weights': {'semantic': 0.55, 'freshness': 0.15, 'topic': 0.2, 'source': 0.1},
            'time_decay_days': 28,
            'source_weights': {'www.e15.cz': 1.1},
        },
    )
    assert update.status_code == 200
    updated_payload = update.get_json()
    assert updated_payload['version'] == created_payload['version'] + 1

    all_configs = client.get('/api/ranking-configs').get_json()['configs']
    assert config_id in all_configs
    assert all_configs[config_id]['version'] == updated_payload['version']

    delete = client.delete(f'/api/ranking-configs/{config_id}')
    assert delete.status_code == 200


def test_similar_endpoint_with_filters_and_reasoning():
    client = app.test_client()

    article_id = next(iter(recommender.article_vectors.keys()))
    source = recommender.extract_source(
        recommender.article_vectors[article_id].get('metadata', {}).get('url', '')
    )

    response = client.get(f'/api/similar/{article_id}?config_id=balanced&sources={source}&top_n=3')

    assert response.status_code == 200
    payload = response.get_json()
    assert isinstance(payload, list)
    if payload:
        first = payload[0]
        assert 'feature_contributions' in first
        assert 'features' in first
        assert 'explanation' in first
        assert 'config_id' in first


def test_recommendation_query_persists_run_and_exposes_metrics():
    client = app.test_client()

    article_ids = list(recommender.article_vectors.keys())
    source = recommender.extract_source(
        recommender.article_vectors[article_ids[0]].get('metadata', {}).get('url', '')
    )

    response = client.post(
        '/api/recommendations/query',
        json={
            'user_id': 'demo_user',
            'user_reads': [article_ids[0]],
            'top_n': 2,
            'sources': [source],
            'config_id': 'balanced',
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['config_id'] == 'balanced'
    assert 'effective_ranking_config' in payload
    assert 'source_defaults_applied' in payload
    assert 'recommendations' in payload
    assert 'run_id' in payload
    assert isinstance(payload['recommendations'], list)

    run_detail_resp = client.get(f"/api/recommendation-runs/{payload['run_id']}")
    assert run_detail_resp.status_code == 200
    run_payload = run_detail_resp.get_json()
    assert run_payload['run_id'] == payload['run_id']
    assert 'items' in run_payload

    runs_list_resp = client.get('/api/recommendation-runs?limit=5')
    assert runs_list_resp.status_code == 200
    runs_list = runs_list_resp.get_json()
    assert 'runs' in runs_list

    metrics_resp = client.get('/api/metrics/offline?limit_runs=20')
    assert metrics_resp.status_code == 200
    metrics = metrics_resp.get_json()
    assert 'runs_analyzed' in metrics
    assert 'avg_score' in metrics


def test_recommendation_context_endpoint_reflects_source_defaults():
    client = app.test_client()
    sources_payload = client.get('/api/sources').get_json()
    assert sources_payload['sources']
    source = sources_payload['sources'][0]['source']

    update = client.put(
        f'/api/source-settings/{source}',
        json={'enabled': True, 'default_weight': 1.4},
    )
    assert update.status_code == 200

    context_resp = client.post(
        '/api/recommendation-context',
        json={
            'config_id': 'balanced',
            'sources': [source],
        },
    )
    assert context_resp.status_code == 200
    context = context_resp.get_json()
    assert context['effective_config_id'] == 'balanced'
    assert source in context['selected_sources']
    assert abs(float(context['source_defaults_applied'][source]) - 1.4) < 1e-9
    assert source in context['effective_ranking_config']['source_weights']

    # Restore for other tests
    restore = client.put(
        f'/api/source-settings/{source}',
        json={'enabled': True, 'default_weight': 1.0},
    )
    assert restore.status_code == 200


def test_disabled_source_not_used_by_default_query():
    client = app.test_client()
    sources_payload = client.get('/api/sources').get_json()
    assert sources_payload['sources']
    source = sources_payload['sources'][0]['source']

    disable = client.put(
        f'/api/source-settings/{source}',
        json={'enabled': False, 'default_weight': 1.0},
    )
    assert disable.status_code == 200

    article_id = next(iter(recommender.article_vectors.keys()))
    response = client.post(
        '/api/recommendations/query',
        json={
            'user_id': 'demo_user',
            'user_reads': [article_id],
            'top_n': 5,
            # Intentionally no "sources" filter => should use enabled defaults only.
            'config_id': 'balanced',
        },
    )
    assert response.status_code == 200
    payload = response.get_json()
    for rec in payload['recommendations']:
        assert rec['source'] != source

    # Restore for other tests
    restore = client.put(
        f'/api/source-settings/{source}',
        json={'enabled': True, 'default_weight': 1.0},
    )
    assert restore.status_code == 200


def test_connector_crud_and_sync_flow():
    client = app.test_client()
    name = f"test-connector-{uuid.uuid4().hex[:8]}"

    create = client.post(
        '/api/connectors',
        json={
            'name': name,
            'connector_type': 'rss',
            'config': {'feed_url': 'https://example.com/feed.xml'},
            'enabled': True,
        },
    )
    assert create.status_code == 201
    created = create.get_json()
    connector_id = created['connector_id']
    assert created['name'] == name
    assert created['connector_type'] == 'rss'
    assert created['enabled'] is True

    listed = client.get('/api/connectors')
    assert listed.status_code == 200
    listed_payload = listed.get_json()
    assert any(item['connector_id'] == connector_id for item in listed_payload['connectors'])

    updated = client.put(
        f'/api/connectors/{connector_id}',
        json={
            'name': f'{name}-updated',
            'connector_type': 'section_scraper',
            'config': {'base_url': 'https://example.com/news'},
            'enabled': True,
        },
    )
    assert updated.status_code == 200
    updated_payload = updated.get_json()
    assert updated_payload['name'] == f'{name}-updated'
    assert updated_payload['connector_type'] == 'section_scraper'
    assert updated_payload['config']['base_url'] == 'https://example.com/news'

    sync = client.post(f'/api/connectors/{connector_id}/sync')
    assert sync.status_code == 200
    sync_payload = sync.get_json()
    assert 'message' in sync_payload
    assert 'ingestion' in sync_payload
    assert 'run_id' in sync_payload
    assert 'run' in sync_payload
    assert sync_payload['ingestion']['connector_id'] == connector_id
    assert sync_payload['run']['status'] in ('completed', 'completed_with_errors')
    assert sync_payload['connector']['last_run_at'] is not None

    run_detail = client.get(f"/api/connector-runs/{sync_payload['run_id']}")
    assert run_detail.status_code == 200
    run_payload = run_detail.get_json()
    assert run_payload['run_id'] == sync_payload['run_id']
    assert run_payload['connector_id'] == connector_id

    run_list = client.get(f'/api/connectors/{connector_id}/runs?limit=5')
    assert run_list.status_code == 200
    run_list_payload = run_list.get_json()
    assert run_list_payload['connector_id'] == connector_id
    assert run_list_payload['count'] >= 1

    disabled = client.put(
        f'/api/connectors/{connector_id}',
        json={
            'name': f'{name}-updated',
            'connector_type': 'section_scraper',
            'config': {'base_url': 'https://example.com/news'},
            'enabled': False,
        },
    )
    assert disabled.status_code == 200
    sync_disabled = client.post(f'/api/connectors/{connector_id}/sync')
    assert sync_disabled.status_code == 400

    deleted = client.delete(f'/api/connectors/{connector_id}')
    assert deleted.status_code == 200
    missing_delete = client.delete(f'/api/connectors/{connector_id}')
    assert missing_delete.status_code == 404


def test_connector_validation():
    client = app.test_client()

    missing_name = client.post(
        '/api/connectors',
        json={
            'connector_type': 'rss',
            'config': {'feed_url': 'https://example.com/feed.xml'},
        },
    )
    assert missing_name.status_code == 400

    invalid_type_create = client.post(
        '/api/connectors',
        json={
            'name': 'bad-type',
            'connector_type': 'unsupported',
            'config': {},
        },
    )
    assert invalid_type_create.status_code == 400

    invalid_type_update = client.put(
        f'/api/connectors/{uuid.uuid4().hex}',
        json={'connector_type': 'unsupported'},
    )
    assert invalid_type_update.status_code == 400

    invalid_url = client.post(
        '/api/connectors',
        json={
            'name': 'bad-url',
            'connector_type': 'rss',
            'config': {'feed_url': 'notaurl'},
        },
    )
    assert invalid_url.status_code == 400

    created = client.post(
        '/api/connectors',
        json={
            'name': f'normalize-{uuid.uuid4().hex[:8]}',
            'connector_type': 'rss',
            'config': {
                'feed_url': 'https://example.com/feed.xml',
                'max_articles': 999,
                'sync_interval_minutes': 0,
                'auto_sync_enabled': 'yes',
            },
        },
    )
    assert created.status_code == 201
    payload = created.get_json()
    assert payload['config']['max_articles'] == 50
    assert payload['config']['sync_interval_minutes'] == 1
    assert payload['config']['auto_sync_enabled'] is True


def test_connector_sync_async_endpoint(monkeypatch):
    client = app.test_client()
    created = client.post(
        '/api/connectors',
        json={
            'name': f'async-{uuid.uuid4().hex[:8]}',
            'connector_type': 'rss',
            'config': {'feed_url': 'https://example.com/feed.xml'},
            'enabled': True,
        },
    ).get_json()
    connector_id = created['connector_id']

    monkeypatch.setattr(
        'app.ConnectorIngestionService.sync_connector',
        lambda self, connector: IngestResult(
            connector_id=connector['connector_id'],
            attempted=2,
            ingested=1,
            skipped_existing=1,
            errors=[],
        ),
    )

    response = client.post(f'/api/connectors/{connector_id}/sync-async')
    assert response.status_code == 202
    payload = response.get_json()
    assert payload['status'] == 'running'
    run_id = payload['run_id']

    run_payload = None
    for _ in range(30):
        run_resp = client.get(f'/api/connector-runs/{run_id}')
        assert run_resp.status_code == 200
        run_payload = run_resp.get_json()
        if run_payload['status'] in ('completed', 'completed_with_errors', 'failed'):
            break
        time.sleep(0.02)

    assert run_payload is not None
    assert run_payload['status'] in ('completed', 'completed_with_errors')
    assert run_payload['attempted'] == 2


def test_connector_sync_due_triggers_configured_connectors(monkeypatch):
    client = app.test_client()
    created = client.post(
        '/api/connectors',
        json={
            'name': f'scheduled-{uuid.uuid4().hex[:8]}',
            'connector_type': 'rss',
            'config': {
                'feed_url': 'https://example.com/feed.xml',
                'auto_sync_enabled': True,
                'sync_interval_minutes': 1,
            },
            'enabled': True,
        },
    ).get_json()
    connector_id = created['connector_id']

    monkeypatch.setattr(
        'app.ConnectorIngestionService.sync_connector',
        lambda self, connector: IngestResult(
            connector_id=connector['connector_id'],
            attempted=1,
            ingested=0,
            skipped_existing=1,
            errors=[],
        ),
    )

    trigger = client.post('/api/connectors/sync-due')
    assert trigger.status_code == 200
    trigger_payload = trigger.get_json()
    assert trigger_payload['triggered_count'] >= 1
    assert any(item['connector_id'] == connector_id for item in trigger_payload['triggered'])


def test_connector_scheduler_status_endpoint():
    client = app.test_client()
    response = client.get('/api/connectors/scheduler/status')
    assert response.status_code == 200
    payload = response.get_json()
    assert 'enabled' in payload
    assert 'interval_seconds' in payload
    assert 'runs_total' in payload


def test_connector_scheduler_run_now_endpoint(monkeypatch):
    client = app.test_client()
    monkeypatch.setattr(
        'app._enqueue_due_connector_syncs',
        lambda trigger_label='scheduled': {  # noqa: ARG005
            'triggered': [{'connector_id': 'c1', 'run_id': 'r1'}],
            'skipped': [],
            'triggered_count': 1,
            'skipped_count': 0,
        },
    )
    response = client.post('/api/connectors/scheduler/run-now')
    assert response.status_code == 200
    payload = response.get_json()
    assert 'scheduler_run' in payload
    assert payload['scheduler_run']['triggered_count'] == 1


def test_connector_metrics_endpoint():
    client = app.test_client()
    response = client.get('/api/connectors/metrics')
    assert response.status_code == 200
    payload = response.get_json()
    assert 'total_connectors' in payload
    assert 'total_runs' in payload
    assert 'overall_success_rate' in payload
    assert 'connectors' in payload


def test_scenario_crud_and_context_application():
    client = app.test_client()
    scenario_id = f"scenario_{uuid.uuid4().hex[:8]}"

    created = client.post(
        '/api/scenarios',
        json={
            'scenario_id': scenario_id,
            'name': 'Fresh Source Focus',
            'description': 'Prefer one source and recent content',
            'enabled': True,
            'rule_set': {
                'include_sources': ['www.e15.cz'],
                'max_age_days': 3650,
                'source_boosts': {'www.e15.cz': 1.2},
                'min_score': 0.0,
            },
        },
    )
    assert created.status_code == 201
    created_payload = created.get_json()
    assert created_payload['scenario_id'] == scenario_id
    assert created_payload['enabled'] is True

    listed = client.get('/api/scenarios')
    assert listed.status_code == 200
    listed_payload = listed.get_json()
    assert any(item['scenario_id'] == scenario_id for item in listed_payload['scenarios'])

    context = client.post(
        '/api/recommendation-context',
        json={'config_id': 'balanced', 'scenario_id': scenario_id},
    )
    assert context.status_code == 200
    context_payload = context.get_json()
    assert context_payload['scenario_id'] == scenario_id
    assert context_payload['scenario']['name'] == 'Fresh Source Focus'

    deleted = client.delete(f'/api/scenarios/{scenario_id}')
    assert deleted.status_code == 200


def test_external_user_id_and_event_metrics():
    client = app.test_client()
    article_id = next(iter(recommender.article_vectors.keys()))
    source = recommender.extract_source(
        recommender.article_vectors[article_id].get('metadata', {}).get('url', '')
    )

    scenario_id = f"scenario_{uuid.uuid4().hex[:8]}"
    create_scenario = client.post(
        '/api/scenarios',
        json={
            'scenario_id': scenario_id,
            'name': 'Event Tracking Scenario',
            'enabled': True,
            'rule_set': {'include_sources': [source]},
        },
    )
    assert create_scenario.status_code == 201

    rec_resp = client.post(
        '/api/recommendations/query',
        json={
            'user_id': 'registered_user',
            'external_user_id': 'customer-123',
            'user_reads': [article_id],
            'top_n': 3,
            'sources': [source],
            'config_id': 'balanced',
            'scenario_id': scenario_id,
            'track_impressions': True,
        },
    )
    assert rec_resp.status_code == 200
    rec_payload = rec_resp.get_json()
    assert rec_payload['external_user_id'] == 'customer-123'
    assert rec_payload['effective_user_id'] == 'ext:customer-123'
    assert rec_payload['scenario_trace']['applied'] is True
    assert rec_payload['run_id']

    if rec_payload['recommendations']:
        clicked_article = rec_payload['recommendations'][0]['article_id']
        event_resp = client.post(
            '/api/events',
            json={
                'events': [
                    {
                        'event_type': 'click',
                        'run_id': rec_payload['run_id'],
                        'article_id': clicked_article,
                        'scenario_id': scenario_id,
                        'external_user_id': 'customer-123',
                    },
                    {
                        'event_type': 'conversion',
                        'run_id': rec_payload['run_id'],
                        'article_id': clicked_article,
                        'scenario_id': scenario_id,
                        'external_user_id': 'customer-123',
                    },
                ]
            },
        )
        assert event_resp.status_code == 201
        assert event_resp.get_json()['inserted'] == 2

    events_resp = client.get(f'/api/events?scenario_id={scenario_id}&limit=20')
    assert events_resp.status_code == 200
    events_payload = events_resp.get_json()
    assert 'events' in events_payload

    metrics_resp = client.get('/api/metrics/scenarios?days=3650')
    assert metrics_resp.status_code == 200
    metrics_payload = metrics_resp.get_json()
    assert 'scenarios' in metrics_payload
    assert any(item['scenario_id'] == scenario_id for item in metrics_payload['scenarios'])


def test_cms_endpoint_and_scenario_simulation():
    client = app.test_client()
    article_id = next(iter(recommender.article_vectors.keys()))
    source = recommender.extract_source(
        recommender.article_vectors[article_id].get('metadata', {}).get('url', '')
    )

    scenario_id = f"scenario_{uuid.uuid4().hex[:8]}"
    created = client.post(
        '/api/scenarios',
        json={
            'scenario_id': scenario_id,
            'name': 'CMS Scenario',
            'enabled': True,
            'rule_set': {'include_sources': [source], 'source_boosts': {source: 1.1}},
        },
    )
    assert created.status_code == 201

    cms_resp = client.post(
        '/api/recommendations/cms',
        json={
            'request': {
                'user_id': 'u1',
                'external_user_id': 'ext-1',
                'user_reads': [article_id],
                'limit': 3,
                'scenario_id': scenario_id,
                'sources': [source],
                'placement': 'homepage_top',
            }
        },
    )
    assert cms_resp.status_code == 200
    cms_payload = cms_resp.get_json()
    assert 'request_id' in cms_payload
    assert cms_payload['user']['effective_user_id'] == 'ext:ext-1'
    assert cms_payload['scenario_id'] == scenario_id
    assert 'trace' in cms_payload

    sim_resp = client.post(
        f'/api/scenarios/{scenario_id}/simulate',
        json={
            'user_id': 'u1',
            'user_reads': [article_id],
            'top_n': 5,
            'sources': [source],
        },
    )
    assert sim_resp.status_code == 200
    sim_payload = sim_resp.get_json()
    assert sim_payload['scenario_id'] == scenario_id
    assert 'scenario_trace' in sim_payload
    assert 'decisions' in sim_payload['scenario_trace']

    source_metrics = client.get(f'/api/metrics/scenarios/{scenario_id}/sources?days=3650')
    assert source_metrics.status_code == 200
    source_metrics_payload = source_metrics.get_json()
    assert source_metrics_payload['scenario_id'] == scenario_id
    assert 'sources' in source_metrics_payload


def test_metrics_attribution_endpoint():
    client = app.test_client()
    article_id = next(iter(recommender.article_vectors.keys()))
    source = recommender.extract_source(
        recommender.article_vectors[article_id].get('metadata', {}).get('url', '')
    )
    scenario_id = f"scenario_{uuid.uuid4().hex[:8]}"

    created = client.post(
        '/api/scenarios',
        json={
            'scenario_id': scenario_id,
            'name': 'Attribution Scenario',
            'enabled': True,
            'rule_set': {'include_sources': [source]},
        },
    )
    assert created.status_code == 201

    rec_resp = client.post(
        '/api/recommendations/query',
        json={
            'user_id': 'attr_user',
            'external_user_id': 'attr-ext-1',
            'user_reads': [article_id],
            'top_n': 3,
            'sources': [source],
            'config_id': 'balanced',
            'scenario_id': scenario_id,
            'track_impressions': True,
        },
    )
    assert rec_resp.status_code == 200
    rec_payload = rec_resp.get_json()
    run_id = rec_payload['run_id']

    recs = rec_payload.get('recommendations') or []
    if recs:
        event_resp = client.post(
            '/api/events',
            json={
                'events': [
                    {
                        'event_type': 'click',
                        'run_id': run_id,
                        'article_id': recs[0]['article_id'],
                        'scenario_id': scenario_id,
                        'external_user_id': 'attr-ext-1',
                    },
                    {
                        'event_type': 'conversion',
                        'run_id': run_id,
                        'article_id': recs[0]['article_id'],
                        'scenario_id': scenario_id,
                        'external_user_id': 'attr-ext-1',
                    },
                ]
            },
        )
        assert event_resp.status_code == 201

    attribution_resp = client.get(
        f'/api/metrics/attribution?days=3650&scenario_ids={scenario_id}&top_runs=20'
    )
    assert attribution_resp.status_code == 200
    payload = attribution_resp.get_json()
    assert 'summary' in payload
    assert 'by_run' in payload
    assert 'by_source' in payload
    assert 'by_scenario' in payload

    assert any(item['scenario_id'] == scenario_id for item in payload['by_scenario'])
    matched_runs = [item for item in payload['by_run'] if item['run_id'] == run_id]
    assert matched_runs
    row = matched_runs[0]
    assert row['config_id'] == 'balanced'
    assert row['scenario_id'] == scenario_id
    assert isinstance(row['selected_sources'], list)


def test_identity_and_scenario_trace_metrics_endpoints():
    client = app.test_client()
    article_id = next(iter(recommender.article_vectors.keys()))
    source = recommender.extract_source(
        recommender.article_vectors[article_id].get('metadata', {}).get('url', '')
    )
    scenario_id = f"scenario_{uuid.uuid4().hex[:8]}"

    created = client.post(
        '/api/scenarios',
        json={
            'scenario_id': scenario_id,
            'name': 'Identity Trace Scenario',
            'enabled': True,
            'rule_set': {'include_sources': [source], 'max_age_days': 3650},
        },
    )
    assert created.status_code == 201

    rec_resp = client.post(
        '/api/recommendations/query',
        json={
            'user_id': 'identity_user',
            'external_user_id': 'identity-ext-1',
            'user_reads': [article_id],
            'top_n': 3,
            'sources': [source],
            'config_id': 'balanced',
            'scenario_id': scenario_id,
            'track_impressions': True,
        },
    )
    assert rec_resp.status_code == 200
    rec_payload = rec_resp.get_json()
    run_id = rec_payload['run_id']

    recs = rec_payload.get('recommendations') or []
    if recs:
        event_resp = client.post(
            '/api/events',
            json={
                'events': [
                    {
                        'event_type': 'click',
                        'run_id': run_id,
                        'article_id': recs[0]['article_id'],
                        'scenario_id': scenario_id,
                        'external_user_id': 'identity-ext-1',
                    }
                ]
            },
        )
        assert event_resp.status_code == 201

    identity_resp = client.get('/api/metrics/identity?days=3650&limit_events=50000&limit_runs=1000')
    assert identity_resp.status_code == 200
    identity_payload = identity_resp.get_json()
    assert 'summary' in identity_payload
    assert 'top_external_users' in identity_payload
    assert identity_payload['summary']['unique_external_users'] >= 1
    assert any(item['external_user_id'] == 'identity-ext-1' for item in identity_payload['top_external_users'])

    trace_resp = client.get(f'/api/metrics/scenario-traces?days=3650&limit_runs=1000&scenario_ids={scenario_id}')
    assert trace_resp.status_code == 200
    trace_payload = trace_resp.get_json()
    assert 'summary' in trace_payload
    assert 'scenarios' in trace_payload
    assert trace_payload['summary']['runs_with_trace'] >= 1
    assert any(item['scenario_id'] == scenario_id for item in trace_payload['scenarios'])


def test_engine_config_endpoint():
    client = app.test_client()
    response = client.get('/api/engine/config')
    assert response.status_code == 200
    payload = response.get_json()
    assert 'ranking_configs' in payload
    assert 'sources' in payload
    assert 'scenarios' in payload
    assert 'scheduler' in payload


def test_events_idempotency_and_pagination():
    client = app.test_client()
    idempotency_key = f"idemp_{uuid.uuid4().hex}"
    payload = {
        'event_type': 'impression',
        'scenario_id': None,
        'article_id': 'demo_article_1',
        'user_id': 'u1',
    }

    first = client.post('/api/events', json=payload, headers={'Idempotency-Key': idempotency_key})
    assert first.status_code == 201
    assert first.get_json()['inserted'] == 1

    second = client.post('/api/events', json=payload, headers={'Idempotency-Key': idempotency_key})
    assert second.status_code == 201
    assert second.headers.get('X-Idempotent-Replay') == 'true'
    assert second.get_json()['inserted'] == 1

    listed = client.get('/api/events?limit=1&offset=0')
    assert listed.status_code == 200
    listed_payload = listed.get_json()
    assert 'has_more' in listed_payload
    assert listed_payload['limit'] == 1


def test_cms_idempotency_and_observability():
    client = app.test_client()
    idempotency_key = f"cms_{uuid.uuid4().hex}"
    response = client.post(
        '/api/recommendations/cms',
        json={
            'request': {
                'user_id': 'demo_user',
                'external_user_id': 'customer-abc',
                'user_reads': ['demo_article_1'],
                'limit': 2,
            }
        },
        headers={'Idempotency-Key': idempotency_key},
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload['api_version'] == 'v1'
    request_id = payload['request_id']

    replay = client.post(
        '/api/recommendations/cms',
        json={
            'request': {
                'user_id': 'demo_user',
                'external_user_id': 'customer-abc',
                'user_reads': ['demo_article_1'],
                'limit': 2,
            }
        },
        headers={'Idempotency-Key': idempotency_key},
    )
    assert replay.status_code == 200
    assert replay.headers.get('X-Idempotent-Replay') == 'true'
    assert replay.get_json()['request_id'] == request_id

    observability = client.get('/api/observability/overview?days=30')
    assert observability.status_code == 200
    obs_payload = observability.get_json()
    assert obs_payload['api_version'] == 'v1'
    assert 'recommendation_api' in obs_payload


def test_audit_logs_endpoint_records_config_changes():
    client = app.test_client()
    scenario_id = f"audit_{uuid.uuid4().hex[:8]}"
    created = client.post(
        '/api/scenarios',
        json={
            'scenario_id': scenario_id,
            'name': 'Audit Scenario',
            'enabled': True,
            'rule_set': {},
            'actor_id': 'qa-user',
        },
        headers={'X-Actor-Id': 'qa-user'},
    )
    assert created.status_code == 201

    logs = client.get('/api/audit-logs?resource_type=scenario&actor_id=qa-user&limit=5')
    assert logs.status_code == 200
    payload = logs.get_json()
    assert payload['api_version'] == 'v1'
    assert any(item['resource_id'] == scenario_id for item in payload['events'])


def test_api_key_auth_toggle(monkeypatch):
    client = app.test_client()
    monkeypatch.setenv('API_AUTH_ENABLED', 'true')
    monkeypatch.setenv('API_AUTH_KEYS', 'secret123')

    no_key = client.get('/api/v1/engine/config')
    assert no_key.status_code == 401

    bad_key = client.get('/api/v1/engine/config', headers={'X-API-Key': 'bad'})
    assert bad_key.status_code == 403

    good_key = client.get('/api/v1/engine/config', headers={'X-API-Key': 'secret123'})
    assert good_key.status_code == 200

    monkeypatch.setenv('API_AUTH_ENABLED', 'false')
    monkeypatch.delenv('API_AUTH_KEYS', raising=False)


def test_rate_limit_toggle(monkeypatch):
    client = app.test_client()
    actor = f"rate-{uuid.uuid4().hex[:8]}"
    monkeypatch.setenv('API_AUTH_ENABLED', 'false')
    monkeypatch.setenv('API_RATE_LIMIT_ENABLED', 'true')
    monkeypatch.setenv('API_RATE_LIMIT_PER_MINUTE', '1')

    first = client.get('/api/v1/engine/config', headers={'X-Actor-Id': actor})
    assert first.status_code == 200

    second = client.get('/api/v1/engine/config', headers={'X-Actor-Id': actor})
    assert second.status_code == 429

    monkeypatch.setenv('API_RATE_LIMIT_ENABLED', 'false')


def test_hmac_signature_toggle(monkeypatch):
    client = app.test_client()
    monkeypatch.setenv('API_AUTH_ENABLED', 'false')
    monkeypatch.setenv('API_SIGNATURE_ENABLED', 'true')
    monkeypatch.setenv('API_SIGNATURE_SECRET', 'topsecret')
    monkeypatch.setenv('API_SIGNATURE_MAX_SKEW_SECONDS', '300')

    body = {'event_type': 'impression', 'article_id': 'demo_article_1', 'user_id': 'u1'}
    raw = json.dumps(body, separators=(',', ':'))

    missing = client.post('/api/events', data=raw, content_type='application/json')
    assert missing.status_code == 401

    ts = str(int(time.time()))
    payload = f"{ts}\n{raw}".encode()
    signature = hmac.new(b'topsecret', payload, hashlib.sha256).hexdigest()
    valid = client.post(
        '/api/events',
        data=raw,
        content_type='application/json',
        headers={'X-Timestamp': ts, 'X-Signature': signature},
    )
    assert valid.status_code == 201

    monkeypatch.setenv('API_SIGNATURE_ENABLED', 'false')
    monkeypatch.delenv('API_SIGNATURE_SECRET', raising=False)


def test_cleanup_endpoints():
    client = app.test_client()
    status = client.get('/api/maintenance/cleanup/status')
    assert status.status_code == 200
    status_payload = status.get_json()
    assert status_payload['api_version'] == 'v1'
    assert 'enabled' in status_payload

    run_now = client.post('/api/maintenance/cleanup/run-now')
    assert run_now.status_code == 200
    run_payload = run_now.get_json()
    assert run_payload['api_version'] == 'v1'
    assert 'cleanup' in run_payload


def test_alert_thresholds_and_sli_endpoints():
    client = app.test_client()
    get_resp = client.get('/api/alerts/thresholds')
    assert get_resp.status_code == 200
    get_payload = get_resp.get_json()
    assert get_payload['api_version'] == 'v1'
    assert 'thresholds' in get_payload

    put_resp = client.put(
        '/api/alerts/thresholds',
        json={
            'thresholds': {
                'recommendation_p95_ms': 600,
                'connector_failure_rate': 0.2,
                'min_ctr': 0.0,
            }
        },
    )
    assert put_resp.status_code == 200
    put_payload = put_resp.get_json()
    assert put_payload['thresholds']['recommendation_p95_ms'] == 600.0

    sli_resp = client.get('/api/v1/observability/sli?days=30')
    assert sli_resp.status_code == 200
    sli_payload = sli_resp.get_json()
    assert sli_payload['api_version'] == 'v1'
    assert 'overall_status' in sli_payload
    assert isinstance(sli_payload['checks'], list)


def test_alert_incidents_endpoints():
    client = app.test_client()
    evaluate = client.post('/api/alerts/incidents/evaluate', json={'days': 30, 'actor_id': 'ops-user'})
    assert evaluate.status_code == 200
    evaluate_payload = evaluate.get_json()
    assert evaluate_payload['api_version'] == 'v1'
    assert 'incident_sync' in evaluate_payload

    listed = client.get('/api/alerts/incidents?status=open&limit=20')
    assert listed.status_code == 200
    listed_payload = listed.get_json()
    assert listed_payload['api_version'] == 'v1'
    assert 'incidents' in listed_payload

    if listed_payload['incidents']:
        incident_id = listed_payload['incidents'][0]['incident_id']
        resolved = client.put(
            f'/api/alerts/incidents/{incident_id}/resolve',
            json={'actor_id': 'ops-user', 'note': 'handled'},
        )
        assert resolved.status_code == 200
        resolved_payload = resolved.get_json()
        assert resolved_payload['resolved'] is True
