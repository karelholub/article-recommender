import os

import pytest

from store import RecommenderStore, SQLiteRecommenderStore


def test_store_defaults_to_sqlite(monkeypatch, tmp_path):
    monkeypatch.delenv('RECOMMENDER_DB_BACKEND', raising=False)
    monkeypatch.setenv('RECOMMENDER_SQLITE_PATH', str(tmp_path / 'recommender.db'))

    store = RecommenderStore()
    assert isinstance(store, SQLiteRecommenderStore)


def test_store_postgres_requires_database_url(monkeypatch):
    monkeypatch.setenv('RECOMMENDER_DB_BACKEND', 'postgres')
    monkeypatch.delenv('DATABASE_URL', raising=False)

    with pytest.raises(ValueError):
        RecommenderStore()

    monkeypatch.setenv('RECOMMENDER_DB_BACKEND', 'sqlite')


def test_connector_run_lifecycle_sqlite(tmp_path):
    store = SQLiteRecommenderStore(db_path=str(tmp_path / 'recommender.db'))
    connector = store.create_connector(
        name='test',
        connector_type='rss',
        config={'feed_url': 'https://example.com/feed.xml'},
        enabled=True,
    )
    connector_id = connector['connector_id']

    run_id = store.start_connector_run(connector_id, trigger='manual')
    finished = store.finish_connector_run(
        run_id=run_id,
        status='completed',
        attempted=3,
        ingested=2,
        skipped_existing=1,
        errors=['minor'],
    )
    assert finished is not None
    assert finished['status'] == 'completed'
    assert finished['attempted'] == 3
    assert finished['error_count'] == 1

    detail = store.get_connector_run(run_id)
    assert detail is not None
    assert detail['run_id'] == run_id
    assert detail['connector_id'] == connector_id

    runs = store.list_connector_runs(connector_id, limit=5)
    assert runs
    assert runs[0]['run_id'] == run_id


def test_scenario_and_event_metrics_sqlite(tmp_path):
    store = SQLiteRecommenderStore(db_path=str(tmp_path / 'recommender.db'))
    scenario = store.upsert_scenario(
        scenario_id='homepage',
        name='Homepage',
        rule_set={'include_sources': ['example.com']},
        enabled=True,
    )
    assert scenario['scenario_id'] == 'homepage'

    scenarios = store.list_scenarios()
    assert any(item['scenario_id'] == 'homepage' for item in scenarios)

    inserted = store.record_events(
        [
            {
                'event_type': 'impression',
                'run_id': None,
                'article_id': 'a1',
                'scenario_id': 'homepage',
                'user_id': 'u1',
            },
            {
                'event_type': 'click',
                'run_id': None,
                'article_id': 'a1',
                'scenario_id': 'homepage',
                'user_id': 'u1',
            },
        ]
    )
    assert inserted == 2

    events = store.list_events(limit=10, scenario_id='homepage')
    assert len(events) == 2

    metrics = store.compute_scenario_metrics(days=30, top_articles=3)
    assert metrics['totals']['impressions'] == 1
    assert metrics['totals']['clicks'] == 1
    assert any(item['scenario_id'] == 'homepage' for item in metrics['scenarios'])


def test_idempotency_record_sqlite(tmp_path):
    store = SQLiteRecommenderStore(db_path=str(tmp_path / 'recommender.db'))
    store.save_idempotency_record(
        endpoint='events_ingest',
        key='key-1',
        status_code=201,
        response_payload={'inserted': 2},
    )
    loaded = store.get_idempotency_record(endpoint='events_ingest', key='key-1')
    assert loaded is not None
    assert loaded['status_code'] == 201
    assert loaded['response']['inserted'] == 2


def test_audit_events_sqlite(tmp_path):
    store = SQLiteRecommenderStore(db_path=str(tmp_path / 'recommender.db'))
    event_id = store.record_audit_event(
        actor_id='tester',
        action='update',
        resource_type='scenario',
        resource_id='homepage',
        metadata={'field': 'value'},
    )
    assert event_id
    events = store.list_audit_events(limit=10, offset=0, actor_id='tester', resource_type='scenario')
    assert len(events) == 1
    assert events[0]['resource_id'] == 'homepage'
    assert events[0]['metadata']['field'] == 'value'


def test_purge_retention_sqlite(tmp_path):
    store = SQLiteRecommenderStore(db_path=str(tmp_path / 'recommender.db'))
    store.save_idempotency_record(
        endpoint='events_ingest',
        key='purge-key',
        status_code=201,
        response_payload={'inserted': 1},
    )
    store.record_audit_event(
        actor_id='tester',
        action='update',
        resource_type='scenario',
        resource_id='cleanup',
    )
    removed_idem = store.purge_idempotency_records(older_than_hours=0)
    removed_audit = store.purge_audit_events(older_than_days=0)
    assert removed_idem >= 1
    assert removed_audit >= 1


def test_alert_thresholds_sqlite(tmp_path):
    store = SQLiteRecommenderStore(db_path=str(tmp_path / 'recommender.db'))
    defaults = store.get_alert_thresholds()
    assert 'recommendation_p95_ms' in defaults
    updated = store.upsert_alert_thresholds(
        {
            'recommendation_p95_ms': 420,
            'connector_failure_rate': 0.08,
            'min_ctr': 0.02,
        }
    )
    assert updated['recommendation_p95_ms'] == 420.0
    assert updated['connector_failure_rate'] == 0.08
    assert updated['min_ctr'] == 0.02


def test_alert_incident_lifecycle_sqlite(tmp_path):
    store = SQLiteRecommenderStore(db_path=str(tmp_path / 'recommender.db'))
    incident = store.upsert_alert_incident(
        metric='ctr',
        current_value=0.0,
        threshold_value=0.01,
        details={'status': 'warn'},
    )
    assert incident['status'] == 'open'
    listed = store.list_alert_incidents(limit=10, offset=0, status='open', metric='ctr')
    assert len(listed) == 1
    resolved = store.resolve_alert_incident(incident['incident_id'], resolved_by='tester', note='ack')
    assert resolved is True
    listed_resolved = store.list_alert_incidents(limit=10, offset=0, status='resolved', metric='ctr')
    assert listed_resolved


def test_list_runs_with_request_sqlite(tmp_path):
    store = SQLiteRecommenderStore(db_path=str(tmp_path / 'recommender.db'))
    run_id = store.persist_recommendation_run(
        user_id='u1',
        config_id='balanced',
        config_version=1,
        request_payload={
            'user_id': 'u1',
            'external_user_id': 'ext-1',
            'scenario_id': 'homepage',
            'scenario_trace': {'filtered_out': 1, 'remaining': 2, 'reasons': {'max_age_days': 1}},
        },
        recommendations=[
            {'article_id': 'a1', 'score': 0.9, 'source': 'example.com', 'features': {}, 'feature_contributions': {}, 'explanation': 'x'}
        ],
        request_duration_ms=10,
    )
    rows = store.list_runs_with_request(limit=10, offset=0, days=30)
    assert rows
    assert rows[0]['run_id'] == run_id
    assert rows[0]['request']['external_user_id'] == 'ext-1'
    assert rows[0]['request']['scenario_id'] == 'homepage'
    assert 'items' not in rows[0]


def test_event_rollups_sqlite(tmp_path):
    store = SQLiteRecommenderStore(db_path=str(tmp_path / 'recommender.db'))
    store.record_events(
        [
            {
                'event_type': 'impression',
                'run_id': None,
                'article_id': 'a1',
                'scenario_id': 'homepage',
                'user_id': 'u1',
                'metadata': {'source': 'example.com'},
            },
            {
                'event_type': 'click',
                'run_id': None,
                'article_id': 'a1',
                'scenario_id': 'homepage',
                'user_id': 'u1',
                'metadata': {'source': 'example.com'},
            },
        ]
    )
    rebuilt = store.rebuild_event_rollups(days=30)
    assert rebuilt['rows_upserted'] >= 1
    rows = store.list_event_rollups(days=30, scenario_ids=['homepage'], source='example.com')
    assert rows
    assert rows[0]['impressions'] >= 1
    assert rows[0]['clicks'] >= 1
