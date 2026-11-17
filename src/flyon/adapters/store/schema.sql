-- flyon schema, version 1. DDL only: tables, indexes, pragmas. No queries, no seed data.
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS session (
    session_id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    ended_at   TEXT,
    title      TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS line (
    line_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES session (session_id) ON DELETE CASCADE,
    stream     TEXT NOT NULL,
    start_ms   INTEGER NOT NULL,
    end_ms     INTEGER NOT NULL,
    text       TEXT NOT NULL,
    engine     TEXT NOT NULL DEFAULT 'unknown',
    model      TEXT NOT NULL DEFAULT 'unknown'
);

CREATE INDEX IF NOT EXISTS line_session_start ON line (session_id, start_ms, line_id);
