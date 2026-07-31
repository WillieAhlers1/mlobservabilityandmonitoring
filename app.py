"""ML Monitoring Platform – Flask application."""

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, g
import mock_data
import data_source
from config_loader import config

app = Flask(__name__)
app.secret_key = config.flask_secret_key or os.urandom(24)

DB_PATH = config.db_path


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(exception):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = sqlite3.connect(DB_PATH)
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


init_db()


@app.route("/switch-industry/<industry_id>")
def switch_industry(industry_id):
    data_source.set_industry(industry_id)
    flash(f'Switched to {mock_data.INDUSTRY_META.get("name", industry_id)}', "success")
    return redirect(url_for("projects"))


@app.context_processor
def inject_industry():
    return {
        "current_industry": mock_data.INDUSTRY_META,
        "available_industries": mock_data.get_available_industries(),
    }


@app.route("/")
def cockpit():
    view = request.args.get("view", "all")
    models = data_source.get_models()
    agents = data_source.get_agents()
    stats = data_source.get_summary_stats_combined()
    return render_template("cockpit.html", models=models, agents=agents, stats=stats, view=view)


@app.route("/dashboard/<entity_id>")
def dashboard(entity_id):
    entity = data_source.get_entity(entity_id)
    if not entity:
        flash("Entity not found.", "danger")
        return redirect(url_for("cockpit"))
    if entity.get("entity_type") == "agent":
        metrics = data_source.get_agent_metrics(entity_id)
        fairness = data_source.get_fairness_metrics(entity_id)
        lineage_data = data_source.get_agent_lineage(entity_id)
        return render_template("agent_dashboard.html", agent=entity, metrics=metrics,
                               fairness=fairness, lineage=lineage_data)
    # Model dashboard
    model = entity
    metrics = data_source.get_model_metrics(entity_id)
    fairness = data_source.get_fairness_metrics(entity_id)
    lineage = data_source.get_model_lineage(entity_id)
    return render_template("dashboard.html", model=model, metrics=metrics,
                           fairness=fairness, lineage=lineage)


@app.route("/lineage/<entity_id>")
def lineage(entity_id):
    entity = data_source.get_entity(entity_id)
    if not entity:
        flash("Entity not found.", "danger")
        return redirect(url_for("cockpit"))
    if entity.get("entity_type") == "agent":
        lineage_data = data_source.get_agent_lineage(entity_id)
    else:
        lineage_data = data_source.get_model_lineage(entity_id)
    return render_template("lineage.html", model=entity, lineage=lineage_data)


@app.route("/projects", methods=["GET", "POST"])
def projects():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        owner = request.form.get("owner", "").strip()
        description = request.form.get("description", "").strip()
        team = request.form.get("team", "").strip()
        if name and owner:
            from datetime import date
            db = get_db()
            proj_id = "proj-custom-" + name.lower().replace(" ", "-")[:20]
            db.execute(
                "INSERT OR IGNORE INTO projects (id, name, description, owner, team, created_date) VALUES (?,?,?,?,?,?)",
                (proj_id, name, description, owner, team, date.today().isoformat()),
            )
            db.commit()
            flash(f'Project "{name}" created successfully!', "success")
        return redirect(url_for("projects"))
    db = get_db()
    custom_projects = [dict(r) for r in db.execute("SELECT * FROM projects").fetchall()]
    all_projects = data_source.get_projects()
    for cp in custom_projects:
        cp["model_count"] = 0
        cp["models"] = []
        cp["agent_count"] = 0
        cp["agents"] = []
        all_projects.append(cp)
    return render_template("projects.html", projects=all_projects)


@app.route("/onboard", methods=["GET", "POST"])
def onboard():
    if request.method == "POST":
        entity_type = request.form.get("entity_type", "model")
        from datetime import date
        db = get_db()
        now_iso = datetime.now(timezone.utc).isoformat()
        industry_id = data_source.get_current_industry()

        if entity_type == "agent":
            agent_name = request.form.get("agent_name", "").strip()
            if agent_name:
                entity_id = f"agent-{uuid.uuid4().hex[:8]}"
                project_id = request.form.get("project_id", "")
                endpoint = request.form.get("endpoint", "")

                db.execute(
                    """INSERT INTO onboarded_agents
                       (entity_id, agent_name, project_id, framework, llm_backbone, description,
                        version, endpoint, owner, environment,
                        task_completion_threshold, groundedness_threshold,
                        safety_threshold, cost_budget, latency_sla,
                        tools, linked_models,
                        hipaa_required, phi_handling, deid_method,
                        data_classification, retention_days, created_date)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        entity_id,
                        agent_name,
                        project_id,
                        request.form.get("framework", ""),
                        request.form.get("llm_backbone", ""),
                        request.form.get("description", ""),
                        request.form.get("version", ""),
                        endpoint,
                        request.form.get("owner", ""),
                        request.form.get("environment", "production"),
                        float(request.form.get("task_completion_threshold", 0.90)),
                        float(request.form.get("groundedness_threshold", 0.85)),
                        float(request.form.get("safety_threshold", 0.95)),
                        float(request.form.get("cost_budget", 0.10)),
                        int(request.form.get("latency_sla", 3000)),
                        request.form.get("tools", ""),
                        request.form.get("linked_models", ""),
                        1 if request.form.get("hipaa_required") else 0,
                        request.form.get("phi_handling", ""),
                        request.form.get("deid_method", ""),
                        request.form.get("data_classification", ""),
                        int(request.form.get("retention_days", 365)),
                        date.today().isoformat(),
                    ),
                )

                # Register in entity_registry
                metadata = json.dumps({
                    "framework": request.form.get("framework", ""),
                    "llm_backbone": request.form.get("llm_backbone", ""),
                    "version": request.form.get("version", ""),
                })
                db.execute(
                    """INSERT INTO entity_registry
                       (entity_id, entity_type, industry_id, project_id, name, status, metadata, created_at, updated_at)
                       VALUES (?,?,?,?,?,?,?,?,?)""",
                    (entity_id, "agent", industry_id, project_id, agent_name, "Unknown", metadata, now_iso, now_iso),
                )
                # Register aliases
                db.execute(
                    "INSERT INTO entity_aliases (entity_id, alias_type, alias_value) VALUES (?,?,?)",
                    (entity_id, "onboard_name", agent_name),
                )
                if endpoint:
                    db.execute(
                        "INSERT INTO entity_aliases (entity_id, alias_type, alias_value) VALUES (?,?,?)",
                        (entity_id, "endpoint", endpoint),
                    )

                db.commit()
                flash(f'Agent "{agent_name}" has been onboarded successfully!', "success")
        else:
            model_name = request.form.get("model_name", "").strip()
            if model_name:
                entity_id = f"model-{uuid.uuid4().hex[:8]}"
                project_id = request.form.get("project_id", "")
                endpoint = request.form.get("endpoint", "")

                db.execute(
                    """INSERT INTO onboarded_models
                       (entity_id, model_name, project_id, model_type, algorithm, description,
                        version, endpoint, owner, environment, primary_metric,
                        drift_method, perf_threshold, drift_threshold,
                        monitoring_frequency, features, created_date)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        entity_id,
                        model_name,
                        project_id,
                        request.form.get("model_type", ""),
                        request.form.get("algorithm", ""),
                        request.form.get("description", ""),
                        request.form.get("version", ""),
                        endpoint,
                        request.form.get("owner", ""),
                        request.form.get("environment", "production"),
                        request.form.get("primary_metric", "accuracy"),
                        request.form.get("drift_method", "psi"),
                        float(request.form.get("perf_threshold", 0.85)),
                        float(request.form.get("drift_threshold", 0.1)),
                        request.form.get("monitoring_frequency", "daily"),
                        request.form.get("features", ""),
                        date.today().isoformat(),
                    ),
                )

                # Register in entity_registry
                metadata = json.dumps({
                    "model_type": request.form.get("model_type", ""),
                    "algorithm": request.form.get("algorithm", ""),
                    "version": request.form.get("version", ""),
                })
                db.execute(
                    """INSERT INTO entity_registry
                       (entity_id, entity_type, industry_id, project_id, name, status, metadata, created_at, updated_at)
                       VALUES (?,?,?,?,?,?,?,?,?)""",
                    (entity_id, "model", industry_id, project_id, model_name, "Unknown", metadata, now_iso, now_iso),
                )
                # Register aliases
                db.execute(
                    "INSERT INTO entity_aliases (entity_id, alias_type, alias_value) VALUES (?,?,?)",
                    (entity_id, "onboard_name", model_name),
                )
                if endpoint:
                    db.execute(
                        "INSERT INTO entity_aliases (entity_id, alias_type, alias_value) VALUES (?,?,?)",
                        (entity_id, "endpoint", endpoint),
                    )

                db.commit()
                flash(f'Model "{model_name}" has been onboarded successfully!', "success")
        return redirect(url_for("onboard"))
    db = get_db()
    onboarded_models = [dict(r) for r in db.execute("SELECT * FROM onboarded_models ORDER BY created_date DESC").fetchall()]
    onboarded_agents = [dict(r) for r in db.execute("SELECT * FROM onboarded_agents ORDER BY created_date DESC").fetchall()]
    return render_template("onboard.html", projects=data_source.get_projects(),
                           onboarded_models=onboarded_models, onboarded_agents=onboarded_agents)


@app.route("/alerts")
def alerts():
    all_alerts = data_source.get_alerts()
    severity_filter = request.args.get("severity", "all")
    type_filter = request.args.get("type", "all")
    unfiltered = list(all_alerts)
    if severity_filter != "all":
        all_alerts = [a for a in all_alerts if a["severity"] == severity_filter]
    if type_filter != "all":
        all_alerts = [a for a in all_alerts if a["type"] == type_filter]
    stats = {
        "total": len(unfiltered),
        "critical": len([a for a in unfiltered if a["severity"] == "critical"]),
        "warning": len([a for a in unfiltered if a["severity"] == "warning"]),
        "acknowledged": len([a for a in unfiltered if a.get("acknowledged")]),
    }
    return render_template("alerts.html", alerts=all_alerts, stats=stats,
                           severity_filter=severity_filter, type_filter=type_filter)


@app.route("/compare")
def compare():
    model_a_id = request.args.get("model_a", "model-1")
    model_b_id = request.args.get("model_b", "model-2")
    model_a = data_source.get_model(model_a_id)
    model_b = data_source.get_model(model_b_id)
    metrics_a = data_source.get_model_metrics(model_a_id) if model_a else None
    metrics_b = data_source.get_model_metrics(model_b_id) if model_b else None
    return render_template("compare.html", models=data_source.get_models(), agents=data_source.get_agents(),
                           model_a=model_a, model_b=model_b,
                           metrics_a=metrics_a, metrics_b=metrics_b,
                           selected_a=model_a_id, selected_b=model_b_id)


@app.route("/api/model/<model_id>/metrics")
def api_model_metrics(model_id):
    metrics = data_source.get_model_metrics(model_id)
    if not metrics:
        return jsonify({"error": "Model not found"}), 404
    return jsonify(metrics)


if __name__ == "__main__":
    app.run(debug=True, port=5000)
