CREATE TABLE IF NOT EXISTS recommendation_scenarios (
    scenario_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    rule_set_json JSONB NOT NULL,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS recommendation_events (
    event_id UUID PRIMARY KEY,
    event_type TEXT NOT NULL,
    run_id UUID,
    article_id TEXT,
    scenario_id TEXT,
    user_id TEXT NOT NULL,
    external_user_id TEXT,
    rank_position INTEGER,
    event_value DOUBLE PRECISION NOT NULL DEFAULT 1.0,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_recommendation_events_created_at
    ON recommendation_events (created_at DESC);

CREATE INDEX IF NOT EXISTS idx_recommendation_events_scenario_type
    ON recommendation_events (scenario_id, event_type, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_recommendation_events_article
    ON recommendation_events (article_id, created_at DESC);
