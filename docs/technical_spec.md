# Article Recommender: Technical Spec (Milestone 1)

## 1. Scope

This milestone introduces a transparent, configurable ranking engine and source selection for recommendations while keeping the current Flask architecture.

## 2. Architecture (Current + Milestone 1)

- `app.py`
  - API and UI routes
  - source discovery endpoints
  - ranking configuration endpoints
  - recommendation query endpoint with source filters and explanation payload
- `recommend.py`
  - recommender abstraction
  - `AdvancedRecommender` upgraded to feature-based ranking with score decomposition
- `bootstrap_data.py`
  - first-run demo dataset bootstrap

## 3. Data Model (Current File-backed)

### 3.1 Article Vector Record

Stored in `embeddings/article_vectors.json`:

```json
{
  "article_id": {
    "vector": [0.1, 0.2],
    "cluster": 1,
    "metadata": {
      "title": "...",
      "content": "...",
      "url": "https://...",
      "scraped_at": "YYYY-MM-DD HH:MM:SS"
    }
  }
}
```

### 3.2 User Profiles

Stored in `profiles/user_profiles.json`:

```json
{
  "user_id": ["article_id_1", "article_id_2"]
}
```

### 3.3 Ranking Config Schema (Milestone 1)

Runtime schema (JSON-compatible):

```json
{
  "config_id": "balanced",
  "weights": {
    "semantic": 0.5,
    "freshness": 0.2,
    "topic": 0.2,
    "source": 0.1
  },
  "time_decay_days": 30,
  "source_weights": {
    "www.e15.cz": 1.0,
    "example.com": 0.8
  }
}
```

Constraints:
- feature weights must sum to 1.0
- every weight in `[0, 1]`
- `time_decay_days > 0`

## 4. Ranking Logic

### 4.1 Features

For each candidate article:
- `semantic`: cosine similarity(user profile vector, candidate vector)
- `freshness`: exponential time decay from `scraped_at`
- `topic`: candidate cluster match ratio against user read clusters
- `source`: source prior from `source_weights` by URL domain (default `1.0`)

### 4.2 Final Score

`score = semantic*w_semantic + freshness*w_freshness + topic*w_topic + source*w_source`

### 4.3 Explanation Payload

Each recommendation returns:
- `score`
- raw feature values (`features`)
- weighted contributions (`contributions`)
- `explanation`: compact human-readable summary
- `config_id` used for ranking

## 5. API Contract (Milestone 1)

### 5.1 `GET /api/sources`

Returns available source domains and article counts.

```json
{
  "sources": [
    {"source": "www.e15.cz", "article_count": 12}
  ],
  "total_sources": 1
}
```

Includes persisted source settings fields:
- `enabled`: whether source participates in default recommendation queries
- `default_weight`: multiplicative source prior

### 5.1b `PUT /api/source-settings/<source>`

Update default source behavior:

```json
{
  "enabled": true,
  "default_weight": 1.2
}
```

### 5.1c Connector Management APIs

- `GET /api/connectors`
- `POST /api/connectors`
- `PUT /api/connectors/<connector_id>`
- `DELETE /api/connectors/<connector_id>`
- `POST /api/connectors/<connector_id>/sync`
- `POST /api/connectors/<connector_id>/sync-async`
- `POST /api/connectors/sync-due`
- `GET /api/connectors/scheduler/status`
- `POST /api/connectors/scheduler/run-now`
- `GET /api/connectors/metrics`
- `GET /api/connectors/<connector_id>/runs`
- `GET /api/connector-runs/<run_id>`

Connector types:
- `section_scraper`
- `rss`

Sync behavior:
- Executes source ingestion for the connector type.
- Supports synchronous and asynchronous execution modes.
- Deduplicates by URL against stored article vectors.
- Generates deterministic embeddings for newly ingested articles.
- Persists article vectors and refreshes in-process recommender state.
- Persists connector run records with status and counters.
- Returns ingestion diagnostics (`attempted`, `ingested`, `skipped_existing`, `errors`) and run metadata.
- Scheduler hook:
  - `sync-due` evaluates connector config flags `auto_sync_enabled` + `sync_interval_minutes`
  - enqueues due connectors as `scheduled` runs
  - optional in-process scheduler loop executes due scans on a fixed interval

Connector config validation:
- `feed_url` / `base_url` must be valid `http(s)` URLs
- `max_articles` normalized to `1..50`
- `sync_interval_minutes` normalized to `1..1440`

### 5.2 `GET /api/ranking-configs`

Returns supported preset configs and default config id.

### 5.3 `POST /api/recommendations/query`

Body:

```json
{
  "user_id": "demo_user",
  "user_reads": ["article_id_1"],
  "top_n": 5,
  "sources": ["www.e15.cz"],
  "config_id": "balanced"
}
```

Response: ranked recommendations with explanation payload.

The response includes transparent scoring context:
- `source_defaults_applied`
- `effective_ranking_config`

### 5.3b `POST /api/recommendation-context`

Resolves recommendation decision context without executing recommendation ranking.

Input:
- `config_id` and optional inline `ranking_config`
- optional source filter list

Output:
- `requested_sources`
- `selected_sources`
- `source_defaults_applied`
- `effective_config_id`
- `config_version`
- `effective_ranking_config`

### 5.4 `GET /api/similar/<article_id>?sources=...&config_id=...&top_n=...`

Backwards-compatible route with added filtering/configuration.

## 6. UI Behavior (Milestone 1)

- User can select one or more sources.
- User can choose ranking config preset.
- Recommendation cards display:
  - final score
  - feature contributions
  - explanation text

## 7. Next Milestones

- Move configs and recommendation traces to PostgreSQL
- Add admin CRUD for ranking configs
- Add experiment tracking and offline evaluation metrics
- Add source connector interface and scheduler

## 8. Implemented Extension (Current)

- SQLite persistence (`data/recommender.db`) now stores:
  - versioned ranking configs
  - recommendation run metadata
  - per-item recommendation trace with features/contributions
- Added config CRUD/versioning endpoints and run/metrics endpoints:
  - `POST/PUT/DELETE /api/ranking-configs`
  - `GET /api/recommendation-runs`
  - `GET /api/recommendation-runs/<run_id>`
  - `GET /api/metrics/offline`
- Added pluggable persistence backend:
  - `RECOMMENDER_DB_BACKEND=sqlite|postgres`
  - `DATABASE_URL` for Postgres
  - Postgres migrations in `db/migrations/postgres/*.sql`
  - Migration runner: `scripts/migrate_postgres.py`
- Added containerized local stack:
  - `docker-compose.yml` (Flask app + Postgres 16)
  - `docker-entrypoint.sh` (bootstrap + migrate + run)
- Added production-style container profile:
  - `docker-compose.prod.yml` with separate `migrate` service
  - Gunicorn app process (`app:app`) with container healthcheck
  - API health endpoints: `/healthz`, `/readyz`
