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
