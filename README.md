# Article Recommendation System

A Flask-based article recommendation system that uses text embeddings to provide article recommendations.

## Features

- Article scraping and processing
- Text embedding with Sentence Transformers
- Configurable recommendation algorithm with:
  - Semantic similarity
  - Freshness (time decay)
  - Topic clustering
  - Source priors
- Source-aware recommendation filtering
- Score explainability (feature values + weighted contributions)
- REST API + demo UI

## Requirements

- Python 3.8+
- Dependencies in `requirements.txt`

## Installation

```bash
git clone https://github.com/karelholub/article-recommender
cd article-recommender
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run Locally

Single command:

```bash
./run.sh
```

What it does:

- Activates `.venv` if present
- Ensures `embeddings/article_vectors.json` and `profiles/user_profiles.json` exist
- Starts Flask on `http://localhost:5001`

You can still run directly with:

```bash
python app.py
```

`app.py` now auto-creates minimal demo data on first run when data files are missing.

## Persistence Backends

Default backend is SQLite (`data/recommender.db`).

To use PostgreSQL:

```bash
export RECOMMENDER_DB_BACKEND=postgres
export DATABASE_URL='postgresql://user:password@localhost:5432/article_recommender'
python scripts/migrate_postgres.py
./run.sh
```

Optional SQLite override:

```bash
export RECOMMENDER_SQLITE_PATH=/path/to/recommender.db
```

## Docker Compose (App + Postgres)

One command:

```bash
./run-docker.sh
```

Or directly:

```bash
docker compose up --build
```

Services:
- App: `http://localhost:5001`
- Postgres: `localhost:5432` (`recommender/recommender`, db `article_recommender`)

Container startup flow:
1. Bootstraps demo article/profile data
2. Runs Postgres migrations (`scripts/migrate_postgres.py`)
3. Starts Flask API

Useful commands:

```bash
docker compose down
docker compose down -v  # remove postgres volume
```

## Production-Style Compose Profile

This profile separates schema migration from app startup and serves Flask via Gunicorn.

```bash
./run-docker-prod.sh
```

Equivalent:

```bash
docker compose -f docker-compose.prod.yml up --build
```

Services:
- `postgres`: persistent DB
- `migrate`: one-shot migration job
- `app`: Gunicorn server (`app:app`)

Health endpoints:
- `GET /healthz` (liveness)
- `GET /readyz` (readiness)

## Optional: Live Data Pipeline

To scrape real articles and regenerate vectors:

```bash
python scrape.py --url https://www.e15.cz/geopolitika
python embed.py
```

## API Endpoints

- `GET /`: Main page
- `GET /api/articles`: All available articles
- `GET /api/sources`: Available source domains and article counts
- `GET /api/source-settings`: Source defaults (`enabled`, `default_weight`)
- `PUT /api/source-settings/<source>`: Update source defaults
- `GET /api/connectors`: List connector definitions
- `POST /api/connectors`: Create connector (`section_scraper` or `rss`)
- `PUT /api/connectors/<connector_id>`: Update connector
- `DELETE /api/connectors/<connector_id>`: Delete connector
- `POST /api/connectors/<connector_id>/sync`: Execute connector ingestion, update embeddings, and record sync timestamp
- `GET /api/ranking-configs`: Latest ranking configs + versions
- `POST /api/ranking-configs`: Create custom ranking config (new version starts at 1)
- `PUT /api/ranking-configs/<config_id>`: Create a new version for an existing custom config
- `DELETE /api/ranking-configs/<config_id>`: Delete custom config versions (system configs are protected)
- `GET /api/similar/<article_id>?sources=...&config_id=...&top_n=...`: Similar articles with filters/config
- `POST /api/recommendations/query`: Structured recommendation query
- `POST /api/recommendation-context`: Resolve effective source/config context without executing ranking
- `GET /api/recommendation-runs?limit=20`: Recent recommendation runs
- `GET /api/recommendation-runs/<run_id>`: Full trace for one run
- `GET /api/metrics/offline?limit_runs=100`: Offline aggregate metrics from stored runs
- `GET /api/stats`: Dataset statistics

Example query endpoint payload:

```json
{
  "user_id": "demo_user",
  "user_reads": ["article_id_1"],
  "top_n": 5,
  "sources": ["www.e15.cz"],
  "config_id": "balanced"
}
```

The `POST /api/recommendations/query` response also includes:
- `source_defaults_applied`
- `effective_ranking_config`

These show exactly which source weights and ranking config were used during scoring.

Connector config fields:
- `rss`: `config.feed_url` (optional `max_articles`, default 10, max 50)
- `section_scraper`: `config.base_url` (optional `max_articles`, default 10, max 50)

`POST /api/connectors/<id>/sync` returns ingestion diagnostics:
- `attempted`
- `ingested`
- `skipped_existing`
- `errors`

## Development

```bash
pytest
black .
flake8
```
