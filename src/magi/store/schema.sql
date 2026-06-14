-- MAGI deliberation store schema.
-- Reference schema from build spec section 3.4, with agent_name and ord
-- added to the position table for faithful Record round-trip.

CREATE TABLE IF NOT EXISTS deliberation (
    id          TEXT    PRIMARY KEY,
    created_at  TEXT    NOT NULL,
    question    TEXT    NOT NULL,
    tier        TEXT    NOT NULL,
    outcome     TEXT    NOT NULL,
    crux        TEXT,
    concurrence INTEGER NOT NULL DEFAULT 0
);

-- One row per agent per deliberation.
-- ord preserves Position ordering in the tuple; agent_name enables round-trip.
CREATE TABLE IF NOT EXISTS position (
    deliberation_id  TEXT    NOT NULL REFERENCES deliberation(id),
    ord              INTEGER NOT NULL,
    agent_name       TEXT    NOT NULL,
    agent_mandate    TEXT    NOT NULL,
    rationale        TEXT    NOT NULL,
    vote             TEXT    NOT NULL
);

-- FTS5 index for similarity retrieval (spec section 3.4, Retrieval and Compounding Precedent).
CREATE VIRTUAL TABLE IF NOT EXISTS deliberation_fts
USING fts5(deliberation_id UNINDEXED, question);
