CREATE TABLE IF NOT EXISTS ranking_configs (
    config_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    config_json JSONB NOT NULL,
    is_system BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (config_id, version)
);

CREATE TABLE IF NOT EXISTS recommendation_runs (
    run_id UUID PRIMARY KEY,
    user_id TEXT NOT NULL,
    config_id TEXT NOT NULL,
    config_version INTEGER NOT NULL,
    request_json JSONB NOT NULL,
    summary_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS recommendation_items (
    run_id UUID NOT NULL,
    rank_position INTEGER NOT NULL,
    article_id TEXT NOT NULL,
    score DOUBLE PRECISION NOT NULL,
    source TEXT,
    features_json JSONB,
    contributions_json JSONB,
    explanation TEXT,
    PRIMARY KEY (run_id, rank_position),
    FOREIGN KEY (run_id) REFERENCES recommendation_runs(run_id)
);

CREATE INDEX IF NOT EXISTS idx_recommendation_runs_created_at
    ON recommendation_runs (created_at DESC);

CREATE INDEX IF NOT EXISTS idx_recommendation_items_run_id
    ON recommendation_items (run_id);
