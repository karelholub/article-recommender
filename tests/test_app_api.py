import uuid
import time

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
