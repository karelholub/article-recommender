CREATE TABLE IF NOT EXISTS api_idempotency_keys (
    endpoint TEXT NOT NULL,
    key TEXT NOT NULL,
    status_code INTEGER NOT NULL,
    response_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (endpoint, key)
);

CREATE INDEX IF NOT EXISTS idx_api_idempotency_created_at
    ON api_idempotency_keys (created_at DESC);
