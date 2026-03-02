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
- Connector scraping hardened for cookie/consent overlays and noisy preference/navigation tabs
- Cluster diagnostics in UI (coverage, largest-cluster share, sample titles)
- Source-aware recommendation filtering
- Score explainability (feature values + weighted contributions)
- UI operators console for:
  - Source enable/weight controls
  - Ranking config CRUD
  - Scenario rule builder + simulation
  - Recommendation run explorer (run history + trace inspection)
  - SLI/alert thresholds + incidents
  - Scenario/source KPI drilldowns
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

Persistent app data volumes are configured for:
- `/app/embeddings`
- `/app/profiles`

This keeps scraped/embedded article data across container rebuilds/restarts.

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
- `GET /recommendations`: Recommendation workspace UI
- `GET /reporting`: Reporting workspace UI
- `GET /operations`: Operations/observability UI
- `GET /runs`: Recommendation run explorer UI
- `GET /api/articles`: All available articles
- `GET /api/sources`: Available source domains and article counts
- `GET /api/source-settings`: Source defaults (`enabled`, `default_weight`)
- `PUT /api/source-settings/<source>`: Update source defaults
- `GET /api/cdp/meiro`: Meiro CDP integration config (API key masked)
- `PUT /api/cdp/meiro`: Update Meiro integration settings + mapping rules
- `GET /api/cdp/meiro/profiles?limit=50`: List cached CDP profiles
- `GET /api/cdp/meiro/profiles/<external_user_id>`: Get one cached CDP profile
- `GET /api/cdp/meiro/profiles/<external_user_id>/derive`: Preview derived recommender traits from raw Meiro attributes
- `POST /api/cdp/meiro/profiles/<external_user_id>/derive`: Persist derived `preferred_sources`/`source_weights`/segments into cached profile
  - persistence is guardrailed; endpoint returns `409` when guardrails fail unless `force=true`
- `POST /api/cdp/meiro/mapping/preview`: Validate mapping paths and derivation against a sample payload before saving mapping
- `POST /api/cdp/meiro/profiles/upsert`: Upsert CDP profile payload (webhook/manual ingest)
- `POST /api/cdp/meiro/sync`: Pull profile(s) from Meiro API by external IDs
  - supports either `request_url_template` (e.g. `.../wbs?segment=107&attribute=stitching_meiro_id&value={external_user_id}`) or `base_url + profile_endpoint_template`
- `GET /api/cdp/meiro/sync-runs?limit=20`: CDP sync run history
- `GET /api/cdp/meiro/sync-runs/<run_id>`: CDP sync run detail
- `GET /api/cdp/meiro/scheduler/status`: CDP scheduler runtime state
- `POST /api/cdp/meiro/scheduler/run-now`: Trigger one CDP sync cycle immediately
- `GET /api/cdp/meiro/diagnostics`: CDP profile freshness, mapping hit-rate, sync reliability diagnostics

Meiro mapping also supports derivation guardrails:
- `derivation_min_source_events`
- `derivation_min_category_events`
- `derivation_allowed_sources`
- `derivation_blocked_sources`
- `derivation_max_preferred_sources`
- `derivation_min_source_weight`
- `derivation_max_source_weight`
- `GET /api/connectors`: List connector definitions
- `POST /api/connectors`: Create connector (`section_scraper` or `rss`)
- `PUT /api/connectors/<connector_id>`: Update connector
- `DELETE /api/connectors/<connector_id>`: Delete connector
- `POST /api/connectors/<connector_id>/sync`: Execute connector ingestion, update embeddings, and record sync timestamp
- `POST /api/connectors/<connector_id>/sync-async`: Enqueue connector sync run and return immediately
- `POST /api/connectors/sync-due`: Trigger async sync for connectors configured as auto-sync and currently due
- `GET /api/connectors/scheduler/status`: In-process scheduler state
- `POST /api/connectors/scheduler/run-now`: Force one scheduler due-scan cycle
- `GET /api/connectors/<connector_id>/runs?limit=20`: Connector sync run history
- `GET /api/connector-runs/<run_id>`: Connector sync run detail
- `GET /api/connectors/metrics`: Aggregated connector reliability and ingestion metrics
- `GET /api/ranking-configs`: Latest ranking configs + versions
- `POST /api/ranking-configs`: Create custom ranking config (new version starts at 1)
- `PUT /api/ranking-configs/<config_id>`: Create a new version for an existing custom config
- `DELETE /api/ranking-configs/<config_id>`: Delete custom config versions (system configs are protected)
- `GET /api/scenarios?include_disabled=true|false`: List recommendation scenarios/rule sets
- `POST /api/scenarios`: Create scenario rule configuration
- `GET /api/scenarios/<scenario_id>`: Get scenario detail
- `PUT /api/scenarios/<scenario_id>`: Update scenario rule configuration
- `DELETE /api/scenarios/<scenario_id>`: Delete scenario
- `GET /api/similar/<article_id>?sources=...&config_id=...&top_n=...`: Similar articles with filters/config
- `POST /api/recommendations/query`: Structured recommendation query
- `POST /api/recommendations/batch`: Execute multiple recommendation queries in one request (`requests[]`, per-item status)
- `POST /api/recommendation-context`: Resolve effective source/config context without executing ranking
  - if `external_user_id` is provided, engine applies CDP mapping and returns `cdp_context`
- `GET /api/recommendation-runs?limit=20`: Recent recommendation runs
- `GET /api/recommendation-runs/<run_id>`: Full trace for one run
- `GET /api/recommendation-runs/<run_id>/decision-flow`: Per-item scenario decision waterfall (kept/filtered, score before/after, boost, reason, final rank)
- `GET /api/metrics/offline?limit_runs=100`: Offline aggregate metrics from stored runs
- `GET /api/metrics/offline/config-compare?baseline_config_id=...&candidate_config_id=...`: Replay historical contexts and compare config quality metrics/lift
- `POST /api/metrics/offline/snapshots`: Persist a quality snapshot from offline metrics (label/window/limit metadata)
- `GET /api/metrics/offline/snapshots?snapshot_type=offline_quality&limit=30`: List persisted quality snapshots
- `GET /api/metrics/offline/snapshots/compare?baseline_id=<id>&candidate_id=<id>`: Compare two snapshots with metric deltas
- `POST /api/recommendations/cms`: CMS-style recommendation integration payload (external ID + placement + trace)
  - supports `Idempotency-Key` header
  - alias: `POST /api/v1/recommendations/cms`
- `POST /api/scenarios/<scenario_id>/simulate`: Preview scenario filtering/boosting over recommendations
- `POST /api/events`: Record impression/click/conversion events
- `GET /api/events?scenario_id=...&event_type=...&limit=...&offset=...&days=...`: Inspect event stream (paginated)
  - `POST /api/events` supports `Idempotency-Key`
  - alias: `/api/v1/events`
- `GET /api/metrics/scenarios?days=30&top_articles=5`: Scenario-level reporting (impressions, clicks, CTR, conversions, top articles)
- `GET /api/metrics/scenarios/<scenario_id>/sources?days=30`: Scenario KPI breakdown by source domain
- `GET /api/metrics/trends?days=30&scenario_ids=homepage&source=www.e15.cz`: Daily trends for impressions/clicks/conversions/CTR (supports filters)
- `GET /api/metrics/attribution?days=30&scenario_ids=homepage&source=www.e15.cz&top_runs=30`: Run/source/scenario attribution drilldown (includes config version + selected source traces)
- `GET /api/metrics/identity?days=30&limit_events=50000&limit_runs=1000&top_external=25`: External-ID analytics (cross-device coverage, top external users, scenario external-share)
- `GET /api/metrics/identity/diagnostics?days=30&limit_events=50000&limit_runs=5000`: External-ID data quality diagnostics (orphan events, run mismatches, ID drift)
- `GET /api/metrics/experiments?days=30&experiment_id=exp-homepage`: A/B experiment analytics by variant (runs, impressions, clicks, conversions, CTR/CVR)
- `GET /api/metrics/experiments/compare?days=30&experiment_id=exp-homepage&baseline_variant=control&candidate_variant=variant`: Variant-to-variant lift table (runs, impressions, clicks, conversions, CTR/CVR deltas)
- `GET /api/metrics/scenario-traces?days=30&limit_runs=1000&scenario_ids=homepage&top_rules=25`: Aggregated scenario trace/rule impact diagnostics from persisted recommendation runs
- `POST /api/metrics/rollups/rebuild`: Rebuild daily event rollups for reporting windows
- `GET /api/metrics/rollups/daily?days=30&scenario_ids=homepage&source=www.e15.cz`: Inspect persisted daily rollup rows
- `POST /api/ranking-configs/<config_id>/auto-tune`: Preview/apply feedback-driven source-weight tuning with guardrails
- `POST /api/ranking-configs/promote`: Promote one config payload into another config ID (e.g., candidate -> `balanced`)
- `POST /api/ranking-configs/promote-with-guard`: Promote candidate only when configured acceptance thresholds pass (NDCG/CTR lift + regression tolerances)
- `GET /api/engine/config`: Full runtime engine configuration snapshot (sources/configs/scenarios/scheduler)
  - alias: `/api/v1/engine/config`
- `GET /api/observability/overview?days=7`: SLA-oriented operational snapshot (recommendation latency stats, events throughput, connector failure rate)
- `GET /api/observability/sli?days=7`: SLI check status (`pass|warn`) against configured thresholds
- `GET /api/alerts/thresholds`: current alert/SLO threshold config
- `PUT /api/alerts/thresholds`: update alert/SLO thresholds
- `GET /api/alerts/incidents`: list alert incidents (`open|resolved`) with pagination/filters
- `POST /api/alerts/incidents/evaluate`: evaluate current SLI checks and open/resolve incidents
- `PUT /api/alerts/incidents/<incident_id>/resolve`: manually resolve incident
- `GET /api/recommendation-runs?limit=...&offset=...`: paginated run history
- `GET /api/audit-logs?limit=...&offset=...&actor_id=...&resource_type=...`: audit trail for config/scenario/source/connector changes
- `GET /api/maintenance/cleanup/status`: retention cleanup scheduler state
- `POST /api/maintenance/cleanup/run-now`: trigger retention cleanup job now
- `GET /api/stats`: Dataset statistics
  - includes `cluster_quality` diagnostics

Auth/rate-limit controls (disabled by default):
- `API_AUTH_ENABLED=true`
- `API_AUTH_KEYS=key1,key2` (header `X-API-Key`)
- `API_RATE_LIMIT_ENABLED=true`
- `API_RATE_LIMIT_PER_MINUTE=120` (keyed by `X-Actor-Id` + endpoint)
- `API_RATE_LIMIT_RULES='{\"/api/recommendations/cms\":60,\"/api/events\":120}'` (optional per-prefix overrides)
- `API_SIGNATURE_ENABLED=true`
- `API_SIGNATURE_SECRET=...` (headers: `X-Timestamp`, `X-Signature`)
- `API_SIGNATURE_MAX_SKEW_SECONDS=300`

Retention cleanup job:
- `CLEANUP_SCHEDULER_ENABLED=true`
- `CLEANUP_SCHEDULER_INTERVAL_SECONDS=3600`
- `IDEMPOTENCY_RETENTION_HOURS=72`
- `AUDIT_RETENTION_DAYS=90`

CDP sync scheduler:
- `CDP_SYNC_SCHEDULER_ENABLED=false`
- `CDP_SYNC_INTERVAL_SECONDS=900`
- `CDP_SYNC_LOOKBACK_DAYS=30`
- `CDP_SYNC_MAX_IDS_PER_RUN=200`

Alert/SLO thresholds are persisted and currently support:
- `recommendation_p95_ms`
- `connector_failure_rate`
- `connector_blocker_rate`
- `max_rollup_lag_hours`
- `min_ctr`

Example query endpoint payload:

```json
{
  "user_id": "demo_user",
  "external_user_id": "customer-123",
  "user_reads": ["article_id_1"],
  "top_n": 5,
  "sources": ["www.e15.cz"],
  "config_id": "balanced",
  "scenario_id": "homepage"
}
```

The `POST /api/recommendations/query` response also includes:
- `source_defaults_applied`
- `effective_ranking_config`
- `effective_user_id` (uses `external_user_id` when provided for cross-device identity)
- `scenario_trace` (rule-level filtering/boosting trace)

These show exactly which source weights and ranking config were used during scoring.

Connector config fields:
- `rss`: `config.feed_url` (optional `max_articles`, default 10, max 50)
- `section_scraper`: `config.base_url` (optional `max_articles`, default 10, max 50)
- Optional scheduling flags in `config`:
  - `auto_sync_enabled` (`true|false`)
  - `sync_interval_minutes` (default `60`)

Server-side normalization:
- `max_articles` is clamped to `[1, 50]`
- `sync_interval_minutes` is clamped to `[1, 1440]`
- URL fields must be valid `http(s)` URLs

Optional autonomous scheduler (in-process):
- `CONNECTOR_SCHEDULER_ENABLED=true`
- `CONNECTOR_SCHEDULER_INTERVAL_SECONDS=60`
- Process lock file (default): `/tmp/article_recommender_scheduler.lock`

`POST /api/connectors/<id>/sync` returns ingestion diagnostics:
- `attempted`
- `ingested`
- `skipped_existing`
- `errors`
- `run_id` and `run` (persistent execution trace with status `completed`, `completed_with_errors`, or `failed`)

## Development

```bash
pytest
black .
flake8
```
