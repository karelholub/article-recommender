CREATE TABLE IF NOT EXISTS source_settings (
    source TEXT PRIMARY KEY,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    default_weight DOUBLE PRECISION NOT NULL DEFAULT 1.0,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_source_settings_enabled
    ON source_settings (enabled);
