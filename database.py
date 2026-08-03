"""Database initialization, connection management, and migrations."""

import sqlite3

from flask import g

from config_loader import config

DB_PATH = config.db_path


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH, timeout=30)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA journal_mode=WAL")
    return g.db


def close_db(exception):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = sqlite3.connect(DB_PATH, timeout=30)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("""CREATE TABLE IF NOT EXISTS projects (
        id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT,
        owner TEXT NOT NULL, team TEXT, created_date TEXT, status TEXT DEFAULT 'Active'
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS onboarded_models (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        entity_id TEXT,
        model_name TEXT NOT NULL, project_id TEXT, model_type TEXT,
        algorithm TEXT, description TEXT, version TEXT, endpoint TEXT,
        owner TEXT, environment TEXT, primary_metric TEXT,
        drift_method TEXT, perf_threshold REAL, drift_threshold REAL,
        monitoring_frequency TEXT, features TEXT, created_date TEXT,
        FOREIGN KEY (project_id) REFERENCES projects(id)
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS onboarded_agents (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        entity_id TEXT,
        agent_name TEXT NOT NULL, project_id TEXT, framework TEXT,
        llm_backbone TEXT, description TEXT, version TEXT, endpoint TEXT,
        owner TEXT, environment TEXT,
        task_completion_threshold REAL, groundedness_threshold REAL,
        safety_threshold REAL, cost_budget REAL, latency_sla INTEGER,
        tools TEXT, linked_models TEXT,
        hipaa_required INTEGER DEFAULT 0, phi_handling TEXT,
        deid_method TEXT, data_classification TEXT, retention_days INTEGER,
        created_date TEXT,
        FOREIGN KEY (project_id) REFERENCES projects(id)
    )""")

    # ── Entity Registry (telemetry ingestion) ───────────────────────────────
    db.execute("""CREATE TABLE IF NOT EXISTS entity_registry (
        entity_id   TEXT PRIMARY KEY,
        entity_type TEXT NOT NULL CHECK(entity_type IN ('model', 'agent')),
        industry_id TEXT NOT NULL,
        project_id  TEXT NOT NULL,
        name        TEXT NOT NULL,
        status      TEXT DEFAULT 'Unknown',
        metadata    JSON,
        created_at  TEXT NOT NULL,
        updated_at  TEXT NOT NULL,
        FOREIGN KEY (project_id) REFERENCES projects(id)
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS entity_aliases (
        entity_id   TEXT NOT NULL,
        alias_type  TEXT NOT NULL,
        alias_value TEXT NOT NULL,
        PRIMARY KEY (entity_id, alias_type, alias_value),
        FOREIGN KEY (entity_id) REFERENCES entity_registry(entity_id)
    )""")

    # ── Metric Store ────────────────────────────────────────────────────────
    db.execute("""CREATE TABLE IF NOT EXISTS metric_timeseries (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        entity_id       TEXT NOT NULL,
        metric_name     TEXT NOT NULL,
        semantic_tag    TEXT,
        timestamp       TEXT NOT NULL,
        value           REAL NOT NULL,
        dimensions      JSON,
        source_event_id TEXT,
        FOREIGN KEY (entity_id) REFERENCES entity_registry(entity_id)
    )""")
    db.execute("""CREATE INDEX IF NOT EXISTS idx_metric_ts_entity_time
        ON metric_timeseries(entity_id, metric_name, timestamp)""")

    db.execute("""CREATE TABLE IF NOT EXISTS metric_timeseries_agg (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        entity_id    TEXT NOT NULL,
        metric_name  TEXT NOT NULL,
        semantic_tag TEXT,
        bucket_start TEXT NOT NULL,
        bucket_size  TEXT NOT NULL,
        agg_method   TEXT NOT NULL,
        value        REAL NOT NULL,
        sample_count INTEGER NOT NULL,
        UNIQUE(entity_id, metric_name, bucket_start, bucket_size)
    )""")
    db.execute("""CREATE INDEX IF NOT EXISTS idx_agg_entity_metric
        ON metric_timeseries_agg(entity_id, metric_name, bucket_start)""")

    db.execute("""CREATE TABLE IF NOT EXISTS drift_snapshots (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        entity_id   TEXT NOT NULL,
        timestamp   TEXT NOT NULL,
        drift_type  TEXT NOT NULL,
        scope       TEXT NOT NULL,
        value       REAL NOT NULL,
        status      TEXT,
        FOREIGN KEY (entity_id) REFERENCES entity_registry(entity_id)
    )""")

    db.execute("""CREATE TABLE IF NOT EXISTS cohort_metrics (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        entity_id   TEXT NOT NULL,
        timestamp   TEXT NOT NULL,
        cohort_name TEXT NOT NULL,
        cohort_dim  TEXT NOT NULL,
        metric_name TEXT NOT NULL,
        value       REAL NOT NULL,
        sample_size INTEGER,
        FOREIGN KEY (entity_id) REFERENCES entity_registry(entity_id)
    )""")

    db.execute("""CREATE TABLE IF NOT EXISTS feature_importance (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        entity_id   TEXT NOT NULL,
        timestamp   TEXT NOT NULL,
        feature     TEXT NOT NULL,
        importance  REAL NOT NULL,
        method      TEXT,
        FOREIGN KEY (entity_id) REFERENCES entity_registry(entity_id)
    )""")

    db.execute("""CREATE TABLE IF NOT EXISTS data_quality (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        entity_id       TEXT NOT NULL,
        timestamp       TEXT NOT NULL,
        feature         TEXT NOT NULL,
        missing_rate    REAL,
        outlier_rate    REAL,
        schema_valid    BOOLEAN,
        row_count       INTEGER,
        FOREIGN KEY (entity_id) REFERENCES entity_registry(entity_id)
    )""")

    db.execute("""CREATE TABLE IF NOT EXISTS agent_traces (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        entity_id       TEXT NOT NULL,
        trace_id        TEXT NOT NULL UNIQUE,
        timestamp       TEXT NOT NULL,
        query           TEXT,
        response        TEXT,
        total_latency   INTEGER,
        token_count     INTEGER,
        voice_score     REAL,
        policy_pass     BOOLEAN,
        policy_note     TEXT,
        FOREIGN KEY (entity_id) REFERENCES entity_registry(entity_id)
    )""")

    db.execute("""CREATE TABLE IF NOT EXISTS agent_trace_steps (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        trace_id    TEXT NOT NULL,
        step_order  INTEGER NOT NULL,
        tool        TEXT NOT NULL,
        action      TEXT,
        latency_ms  INTEGER,
        status      TEXT,
        FOREIGN KEY (trace_id) REFERENCES agent_traces(trace_id)
    )""")

    db.execute("""CREATE TABLE IF NOT EXISTS alerts (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        entity_id   TEXT NOT NULL,
        timestamp   TEXT NOT NULL,
        severity    TEXT NOT NULL CHECK(severity IN ('critical', 'high', 'medium', 'low', 'warning', 'info')),
        alert_type  TEXT NOT NULL,
        title       TEXT NOT NULL,
        description TEXT,
        resolved    BOOLEAN DEFAULT FALSE,
        resolved_at TEXT,
        FOREIGN KEY (entity_id) REFERENCES entity_registry(entity_id)
    )""")

    db.execute("""CREATE TABLE IF NOT EXISTS lineage_events (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        entity_id   TEXT NOT NULL,
        timestamp   TEXT NOT NULL,
        event_type  TEXT NOT NULL,
        version     TEXT,
        trigger     TEXT,
        metadata    JSON,
        FOREIGN KEY (entity_id) REFERENCES entity_registry(entity_id)
    )""")

    # ── Staging Store ───────────────────────────────────────────────────────
    db.execute("""CREATE TABLE IF NOT EXISTS staging_events (
        event_id            TEXT PRIMARY KEY,
        source_connector    TEXT NOT NULL,
        source_entity_ref   TEXT NOT NULL,
        event_type          TEXT NOT NULL,
        timestamp           TEXT NOT NULL,
        received_at         TEXT NOT NULL,
        mapping_version     TEXT,
        payload             JSON NOT NULL,
        processing_status   TEXT DEFAULT 'pending',
        rejection_reason    TEXT,
        processed_at        TEXT
    )""")
    db.execute("""CREATE INDEX IF NOT EXISTS idx_staging_status
        ON staging_events(processing_status, received_at)""")
    db.execute("""CREATE INDEX IF NOT EXISTS idx_staging_entity
        ON staging_events(source_entity_ref, timestamp)""")

    # ── Connector Health ────────────────────────────────────────────────────
    db.execute("""CREATE TABLE IF NOT EXISTS connector_health (
        connector_id        TEXT PRIMARY KEY,
        connector_type      TEXT NOT NULL,
        config_hash         TEXT,
        cursor_value        TEXT,
        last_success        TEXT,
        last_failure        TEXT,
        consecutive_failures INTEGER DEFAULT 0,
        state               TEXT DEFAULT 'healthy',
        error_message       TEXT
    )""")

    # ── Schema Version ──────────────────────────────────────────────────────
    db.execute("""CREATE TABLE IF NOT EXISTS schema_version (
        version     INTEGER PRIMARY KEY,
        applied_at  TEXT NOT NULL
    )""")

    db.commit()
    db.close()

    # Add entity_id column to existing tables if missing (migration-safe)
    _migrate_add_entity_id_column()


def _migrate_add_entity_id_column():
    """Add entity_id column to onboarded_models/agents if upgrading from old schema."""
    db = sqlite3.connect(DB_PATH)
    for table in ("onboarded_models", "onboarded_agents"):
        columns = [row[1] for row in db.execute(f"PRAGMA table_info({table})").fetchall()]
        if "entity_id" not in columns:
            db.execute(f"ALTER TABLE {table} ADD COLUMN entity_id TEXT")
    db.commit()
    db.close()
