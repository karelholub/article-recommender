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
