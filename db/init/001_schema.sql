CREATE TABLE IF NOT EXISTS events (
    event_id BIGSERIAL PRIMARY KEY,
    ticket_id TEXT NOT NULL,
    ts TIMESTAMPTZ NOT NULL,
    event_type TEXT NOT NULL,
    actor_hash TEXT NOT NULL,
    team TEXT NOT NULL,
    from_state TEXT,
    to_state TEXT,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS events_ticket_ts_idx ON events (ticket_id, ts);
CREATE INDEX IF NOT EXISTS events_type_idx ON events (event_type);
CREATE INDEX IF NOT EXISTS events_team_idx ON events (team);

CREATE TABLE IF NOT EXISTS business_taxonomy (
    category_key TEXT PRIMARY KEY,
    label TEXT NOT NULL,
    strategic_criticality TEXT NOT NULL,
    core BOOLEAN NOT NULL
);

CREATE TABLE IF NOT EXISTS org_teams (
    team_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    product_line TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS org_members (
    actor_hash TEXT PRIMARY KEY,
    declared_team TEXT NOT NULL REFERENCES org_teams(team_id),
    role TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS dataset_metadata (
    metadata_key TEXT PRIMARY KEY,
    metadata_value JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
