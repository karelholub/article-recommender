# API Hardening + Scale Additions

This document describes the implemented MVP for points 3 and 4.

## 1) API hardening

### OpenAPI contract
- Endpoint: `GET /api/openapi.json` (also `/api/v1/openapi.json`)
- Includes core public paths for recommendations, events, online KPIs, thresholds, promote/rollback and async jobs.

### Validation/error envelope
- New helper-based validation envelope for new/updated routes:
  - fields: `error`, `message`, `error_code`, `status`, optional `details`
- Existing routes continue to return backward-compatible `error` messages.

### Idempotency semantics
- Added idempotent replay support for `POST /api/recommendations/query`
  - header/body key supported through existing `Idempotency-Key` and `idempotency_key`
  - replay returns `X-Idempotent-Replay: true`

## 2) Scale path

### Recommendation response cache
- In-memory cache for recommendation candidates with TTL (`RECOMMENDATION_CACHE_TTL_SECONDS`, default 60s).
- Applied to:
  - internal query pipeline
  - CMS recommendation endpoint
- Responses expose `X-Cache-Hit: true|false`.

### Async event ingestion queue
- New endpoints:
  - `POST /api/events/ingest-async`
  - `GET /api/events/ingest-status/{job_id}`
  - `GET /api/events/ingest-queue-status`
  - and `/api/v1/...` aliases
- Background worker persists queued batches into the same events store.
- Controlled by env:
  - `EVENTS_INGEST_ASYNC_ENABLED` (default `true`)
  - `EVENTS_INGEST_QUEUE_MAXSIZE` (default `10000`)

### Async rollup rebuild jobs
- New endpoints:
  - `POST /api/metrics/rollups/rebuild-async`
  - `GET /api/metrics/rollups/rebuild-async/{job_id}`
  - and `/api/v1/...` aliases
- Uses a single background executor to avoid concurrent rebuild contention.

## 3) Suggested production tuning

- Set cache TTL by endpoint profile:
  - homepage placements: 30-120s
  - highly dynamic contexts: 10-30s
- Ensure event queue has backpressure monitoring and queue depth alerts.
- Keep async rollup rebuild as the default for larger windows.
