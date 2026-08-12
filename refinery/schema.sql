-- swarm-refinery canonical schema
-- Postgres + pgvector. Idempotent: safe to run repeatedly.

CREATE EXTENSION IF NOT EXISTS vector;

-- ── Layer 0: raw ingested rows + Layer 1: refined signals ────────────────────
-- Both live in `signals`, discriminated by `kind`. Raw kinds are prefixed raw_*,
-- refined kinds are *_signal. `embedding` dim must match EMBED_DIM (default 384,
-- sentence-transformers all-MiniLM-L6-v2).
CREATE TABLE IF NOT EXISTS signals (
    id          TEXT PRIMARY KEY,
    source      TEXT NOT NULL,           -- redis | smolting_facts | lore | orchestrator | market | refine
    kind        TEXT NOT NULL,           -- raw_msg | raw_fact | raw_lore | raw_orchestrator | market_snapshot_ref | content_signal | market_signal | governance_signal | meta_signal
    text        TEXT NOT NULL,
    ts          TIMESTAMPTZ NOT NULL DEFAULT now(),
    provenance  JSONB NOT NULL DEFAULT '{}'::jsonb,
    confidence  REAL NOT NULL DEFAULT 1.0,
    private     BOOLEAN NOT NULL DEFAULT false,  -- private-source rows never leave the box
    embedding   vector(384)
);
CREATE INDEX IF NOT EXISTS idx_signals_kind   ON signals (kind);
CREATE INDEX IF NOT EXISTS idx_signals_source ON signals (source);
CREATE INDEX IF NOT EXISTS idx_signals_ts     ON signals (ts DESC);

CREATE TABLE IF NOT EXISTS entities (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    kind        TEXT NOT NULL,
    first_seen  TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen   TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata    JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_entities_name_kind ON entities (name, kind);

CREATE TABLE IF NOT EXISTS engagements (
    id          TEXT PRIMARY KEY,
    platform    TEXT NOT NULL,           -- moltbook | x
    post_ref    TEXT NOT NULL,
    metric      TEXT NOT NULL,           -- likes | replies | reposts | views ...
    value       REAL NOT NULL,
    ts          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_engagements_post ON engagements (platform, post_ref);
CREATE INDEX IF NOT EXISTS idx_engagements_ts   ON engagements (ts DESC);

CREATE TABLE IF NOT EXISTS market_snapshots (
    id          TEXT PRIMARY KEY,
    ts          TIMESTAMPTZ NOT NULL DEFAULT now(),
    token_mint  TEXT NOT NULL,
    price       DOUBLE PRECISION,
    volume      DOUBLE PRECISION,
    liquidity   DOUBLE PRECISION,
    holders     INTEGER,
    source      TEXT NOT NULL            -- dexscreener | birdeye
);
CREATE INDEX IF NOT EXISTS idx_market_mint_ts ON market_snapshots (token_mint, ts DESC);

-- Per-ingester cursor so every ingest run is idempotent / resumable.
CREATE TABLE IF NOT EXISTS ingest_cursors (
    ingester    TEXT PRIMARY KEY,
    cursor      TEXT NOT NULL DEFAULT '',
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    stats       JSONB NOT NULL DEFAULT '{}'::jsonb
);
