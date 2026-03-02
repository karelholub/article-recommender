CREATE TABLE IF NOT EXISTS alert_thresholds (
    threshold_id TEXT PRIMARY KEY,
    thresholds_json JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);
