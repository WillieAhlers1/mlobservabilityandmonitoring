"""Data source router for ML Monitoring Platform.

Routes data requests to either mock data (default) or live metric store
based on the configuration in config/app.yaml (overridable via ML_WORKS_DATA_SOURCE env var).

Usage:
    import data_source
    metrics = data_source.get_model_metrics("model-1")

Configuration (config/app.yaml):
    data_source: mock   — use mock_data generators (default)
    data_source: live   — query the metric store tables
"""

import json
import os
import sqlite3

import mock_data
from config_loader import config


def _get_data_source():
    """Return current data source mode (always up-to-date).

    Reads the module-level DATA_SOURCE variable which is:
    - Set from config at import time
    - Updated by the settings route on save
    - Patchable by tests
    """
    return DATA_SOURCE


# Module-level variables kept for backward compatibility and test patching.
DATA_SOURCE = config.data_source
DB_PATH = config.db_path


def _get_live_db():
    """Open a read-only connection to the metric store."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ── Industry / global state (always delegate to mock_data) ──────────────────
# Industry switching is a UI concept tied to mock data modules.
# In live mode, entities have industry_id in entity_registry.

def set_industry(industry_id):
    mock_data.set_industry(industry_id)


def get_current_industry():
    return mock_data.get_current_industry()


def get_available_industries():
    return mock_data.get_available_industries()


@property
def INDUSTRY_META():
    return mock_data.INDUSTRY_META


# ── Entity lists ────────────────────────────────────────────────────────────

def get_models():
    """Return the list of all models."""
    if _get_data_source() == "live":
        return _live_entity_list("model")
    return list(mock_data.MODELS)


def get_agents():
    """Return the list of all agents."""
    if _get_data_source() == "live":
        return _live_entity_list("agent")
    return list(mock_data.AGENTS)


def get_entity(entity_id):
    """Look up any entity by ID."""
    if _get_data_source() == "live":
        return _live_get_entity(entity_id)
    return mock_data.get_entity(entity_id)


def get_model(model_id):
    """Look up a single model by ID."""
    if _get_data_source() == "live":
        entity = _live_get_entity(model_id)
        if entity and entity.get("entity_type") == "model":
            return entity
        return None
    return mock_data.get_model(model_id)


# ── Metrics ─────────────────────────────────────────────────────────────────

def get_model_metrics(entity_id):
    if _get_data_source() == "live":
        return _live_model_metrics(entity_id)
    return mock_data.get_model_metrics(entity_id)


def get_agent_metrics(entity_id):
    if _get_data_source() == "live":
        return _live_agent_metrics(entity_id)
    return mock_data.get_agent_metrics(entity_id)


def get_fairness_metrics(entity_id):
    if _get_data_source() == "live":
        return _live_fairness_metrics(entity_id)
    return mock_data.get_fairness_metrics(entity_id)


# ── Lineage ─────────────────────────────────────────────────────────────────

def get_model_lineage(entity_id):
    if _get_data_source() == "live":
        return _live_model_lineage(entity_id)
    return mock_data.get_model_lineage(entity_id)


def get_agent_lineage(entity_id):
    if _get_data_source() == "live":
        return _live_agent_lineage(entity_id)
    return mock_data.get_agent_lineage(entity_id)


# ── Alerts ──────────────────────────────────────────────────────────────────

def get_alerts():
    if _get_data_source() == "live":
        return _live_alerts()
    return mock_data.get_alerts()


# ── Summary / Projects ─────────────────────────────────────────────────────

def get_summary_stats_combined():
    if _get_data_source() == "live":
        return _live_summary_stats()
    return mock_data.get_summary_stats_combined()


def get_projects():
    if _get_data_source() == "live":
        return _live_projects()
    return mock_data.get_projects()


# ═════════════════════════════════════════════════════════════════════════════
# Live-mode implementations (query metric store)
# ═════════════════════════════════════════════════════════════════════════════

def _live_entity_list(entity_type):
    """Return entities from entity_registry as dicts matching mock shape."""
    db = _get_live_db()
    try:
        rows = db.execute(
            "SELECT * FROM entity_registry WHERE entity_type = ? ORDER BY name",
            (entity_type,),
        ).fetchall()
        entities = []
        for row in rows:
            meta = json.loads(row["metadata"]) if row["metadata"] else {}

            # Look up project name
            proj = db.execute(
                "SELECT name FROM projects WHERE id = ?", (row["project_id"],)
            ).fetchone()
            project_name = proj["name"] if proj else row["project_id"]

            entity = {
                "id": row["entity_id"],
                "name": row["name"],
                "entity_type": row["entity_type"],
                "status": row["status"],
                "project_id": row["project_id"],
                "project_name": project_name,
                "industry_id": row["industry_id"],
                **meta,
            }

            # Add defaults for cockpit template fields
            if entity_type == "model":
                entity.setdefault("algorithm", "")
                entity.setdefault("version", "")
                entity.setdefault("owner", "")
                entity.setdefault("drift_score", 0.0)
                entity.setdefault("performance_score", 0.0)
                entity.setdefault("dqm_score", 0.0)
                entity.setdefault("hipaa", {"compliant": False, "phi_handling": ""})

                # Compute live drift/perf scores from DB if available
                latest_drift = db.execute(
                    """SELECT value FROM drift_snapshots
                       WHERE entity_id = ? AND scope = 'overall'
                       ORDER BY timestamp DESC LIMIT 1""",
                    (row["entity_id"],),
                ).fetchone()
                if latest_drift:
                    entity["drift_score"] = latest_drift["value"]

                latest_perf = db.execute(
                    """SELECT value FROM metric_timeseries
                       WHERE entity_id = ? AND metric_name IN ('accuracy', 'r2_score')
                       ORDER BY timestamp DESC LIMIT 1""",
                    (row["entity_id"],),
                ).fetchone()
                if latest_perf:
                    entity["performance_score"] = latest_perf["value"]

            elif entity_type == "agent":
                entity.setdefault("framework", "")
                entity.setdefault("llm_backbone", "")
                entity.setdefault("version", "")
                entity.setdefault("owner", "")
                entity.setdefault("safety_score", 0.0)
                entity.setdefault("task_completion_rate", 0.0)
                entity.setdefault("groundedness_score", 0.0)
                entity.setdefault("avg_cost_per_interaction", 0.0)

                # Compute live scores from DB if available
                latest_safety = db.execute(
                    """SELECT value FROM metric_timeseries
                       WHERE entity_id = ? AND metric_name = 'safety'
                       ORDER BY timestamp DESC LIMIT 1""",
                    (row["entity_id"],),
                ).fetchone()
                if latest_safety:
                    entity["safety_score"] = latest_safety["value"]

                latest_tc = db.execute(
                    """SELECT value FROM metric_timeseries
                       WHERE entity_id = ? AND metric_name = 'task_completion'
                       ORDER BY timestamp DESC LIMIT 1""",
                    (row["entity_id"],),
                ).fetchone()
                if latest_tc:
                    entity["task_completion_rate"] = latest_tc["value"]

            entities.append(entity)
        return entities
    finally:
        db.close()


def _live_get_entity(entity_id):
    """Look up a single entity from entity_registry."""
    db = _get_live_db()
    try:
        row = db.execute(
            "SELECT * FROM entity_registry WHERE entity_id = ?",
            (entity_id,),
        ).fetchone()
        if not row:
            return None
        meta = json.loads(row["metadata"]) if row["metadata"] else {}

        # Look up project name
        proj = db.execute(
            "SELECT name FROM projects WHERE id = ?", (row["project_id"],)
        ).fetchone()
        project_name = proj["name"] if proj else row["project_id"]

        entity = {
            "id": row["entity_id"],
            "name": row["name"],
            "entity_type": row["entity_type"],
            "status": row["status"],
            "project_id": row["project_id"],
            "project_name": project_name,
            "industry_id": row["industry_id"],
            **meta,
        }

        # Defaults for templates
        if row["entity_type"] == "model":
            entity.setdefault("algorithm", "")
            entity.setdefault("version", "")
            entity.setdefault("owner", "")
            entity.setdefault("description", "")
            entity.setdefault("features", "")
            entity.setdefault("last_updated", row["updated_at"])
            entity.setdefault("predictions_today", 0)
            entity.setdefault("avg_latency_ms", 0)
            entity.setdefault("drift_score", 0.0)
            entity.setdefault("performance_score", 0.0)
            entity.setdefault("dqm_score", 0.0)
            entity.setdefault("hipaa", {
                "compliant": False, "phi_handling": "",
                "encryption_at_rest": False, "encryption_in_transit": False,
                "audit_logging": False, "min_necessary": False,
                "baa_signed": False, "access_control": "",
                "data_classification": "", "deid_method": "",
                "retention_days": 0, "last_risk_assessment": "",
            })
        elif row["entity_type"] == "agent":
            entity.setdefault("framework", "")
            entity.setdefault("llm_backbone", "")
            entity.setdefault("version", "")
            entity.setdefault("owner", "")
            entity.setdefault("description", "")
            entity.setdefault("last_updated", row["updated_at"])
            entity.setdefault("sessions_today", 0)
            entity.setdefault("avg_latency_ms", 0)
            entity.setdefault("safety_score", 0.0)
            entity.setdefault("task_completion_rate", 0.0)
            entity.setdefault("groundedness_score", 0.0)
            entity.setdefault("avg_cost_per_interaction", 0.0)
            entity.setdefault("hipaa", {
                "compliant": False, "phi_handling": "",
                "encryption_at_rest": False, "encryption_in_transit": False,
                "audit_logging": False, "min_necessary": False,
                "baa_signed": False, "access_control": "",
                "data_classification": "", "deid_method": "",
                "retention_days": 0, "last_risk_assessment": "",
            })

        return entity
    finally:
        db.close()


def _live_model_metrics(entity_id):
    """Query metric store for a model. Prefers agg table, falls back to raw."""
    entity = _live_get_entity(entity_id)
    if not entity:
        return None

    db = _get_live_db()
    try:
        # Prefer aggregated data if available
        agg_rows = db.execute(
            """SELECT metric_name, bucket_start as timestamp, value
               FROM metric_timeseries_agg
               WHERE entity_id = ?
               ORDER BY bucket_start""",
            (entity_id,),
        ).fetchall()

        # Fall back to raw metric_timeseries if no agg data
        if agg_rows:
            rows = agg_rows
        else:
            rows = db.execute(
                """SELECT metric_name, timestamp, value
                   FROM metric_timeseries
                   WHERE entity_id = ?
                   ORDER BY timestamp""",
                (entity_id,),
            ).fetchall()

        if not rows:
            # Return empty structure matching mock shape
            return {
                "model": entity,
                "metric_type": entity.get("model_type", "classification"),
                "dates": [],
                "metrics": {},
                "drift": {"dates": [], "values": [], "current": 0.0},
                "cohorts": {"category_name": "Segment", "segments": []},
                "feature_importance": [],
                "feature_drift": [],
                "feature_accuracy_drop": [],
                "data_quality": {
                    "overall_score": 0.0,
                    "total_records_today": 0,
                    "freshness_minutes": 0,
                    "schema_violations": 0,
                    "features": [],
                },
                "confusion_matrix": None,
            }

        # Group metrics by name
        metrics_by_name = {}
        all_dates = []
        seen_dates = set()
        for r in rows:
            name = r["metric_name"]
            if name not in metrics_by_name:
                metrics_by_name[name] = {"dates": [], "values": []}
            # Use date portion for daily data, full timestamp for hourly agg data
            ts = r["timestamp"]
            date_key = ts[:10] if ts[10:] in ("", "T00:00:00Z", "T00:00:00+00:00") else ts
            metrics_by_name[name]["dates"].append(date_key)
            metrics_by_name[name]["values"].append(r["value"])
            if date_key not in seen_dates:
                all_dates.append(date_key)
                seen_dates.add(date_key)

        dates = sorted(all_dates)

        # Build metrics dict matching mock shape
        formatted_metrics = {}
        for name, data in metrics_by_name.items():
            formatted_metrics[name] = {
                "values": data["values"],
                "current": data["values"][-1] if data["values"] else 0.0,
                "label": name.replace("_", " ").title(),
            }

        # Fetch drift data
        drift_rows = db.execute(
            """SELECT timestamp, value
               FROM drift_snapshots
               WHERE entity_id = ? AND scope = 'overall'
               ORDER BY timestamp""",
            (entity_id,),
        ).fetchall()
        drift_dates = [r["timestamp"][:10] for r in drift_rows]
        drift_values = [r["value"] for r in drift_rows]

        # Fetch cohort metrics
        cohort_rows = db.execute(
            """SELECT cohort_name, cohort_dim, metric_name, value, sample_size
               FROM cohort_metrics
               WHERE entity_id = ?
               ORDER BY cohort_name""",
            (entity_id,),
        ).fetchall()
        cohorts_by_name = {}
        cohort_dim_name = "Segment"
        for cr in cohort_rows:
            cname = cr["cohort_name"]
            cohort_dim_name = cr["cohort_dim"]
            if cname not in cohorts_by_name:
                cohorts_by_name[cname] = {"name": cname, "sample_size": cr["sample_size"] or 0}
            cohorts_by_name[cname][cr["metric_name"]] = cr["value"]

        # Fetch feature importance
        fi_rows = db.execute(
            """SELECT feature, importance
               FROM feature_importance
               WHERE entity_id = ?
               ORDER BY importance DESC""",
            (entity_id,),
        ).fetchall()

        # Fetch feature drift
        fd_rows = db.execute(
            """SELECT scope, value, status
               FROM drift_snapshots
               WHERE entity_id = ? AND scope LIKE 'feature:%'
               ORDER BY value DESC""",
            (entity_id,),
        ).fetchall()

        # Fetch data quality
        dq_rows = db.execute(
            """SELECT feature, missing_rate, outlier_rate, schema_valid, row_count
               FROM data_quality
               WHERE entity_id = ?""",
            (entity_id,),
        ).fetchall()

        return {
            "model": entity,
            "metric_type": entity.get("model_type", "classification"),
            "dates": dates,
            "metrics": formatted_metrics,
            "drift": {
                "dates": drift_dates,
                "values": drift_values,
                "current": drift_values[-1] if drift_values else None,
            },
            "cohorts": {
                "category_name": cohort_dim_name,
                "segments": list(cohorts_by_name.values()),
            },
            "feature_importance": [
                {"feature": r["feature"], "importance": r["importance"]}
                for r in fi_rows
            ],
            "feature_drift": [
                {
                    "feature": r["scope"].replace("feature:", ""),
                    "psi": r["value"],
                    "status": r["status"] or "Normal",
                }
                for r in fd_rows
            ],
            "feature_accuracy_drop": [],  # Populated in later sessions
            "data_quality": {
                "overall_score": round(1.0 - sum((r["missing_rate"] or 0) for r in dq_rows) / max(len(dq_rows), 1), 2) if dq_rows else 0.0,
                "total_records_today": sum(r["row_count"] or 0 for r in dq_rows),
                "freshness_minutes": 0,
                "schema_violations": 0,
                "features": [
                    {
                        "feature": r["feature"],
                        "missing_rate": (r["missing_rate"] or 0) * 100,
                        "outlier_rate": (r["outlier_rate"] or 0) * 100,
                        "distribution_shift": 0,
                        "schema_valid": bool(r["schema_valid"]),
                    }
                    for r in dq_rows
                ],
            },
            "confusion_matrix": None,
        }
    finally:
        db.close()


def _live_agent_metrics(entity_id):
    """Query agent_traces and metric_timeseries for an agent."""
    entity = _live_get_entity(entity_id)
    if not entity:
        return None

    db = _get_live_db()
    try:
        # Fetch time-series metrics
        rows = db.execute(
            """SELECT metric_name, timestamp, value
               FROM metric_timeseries
               WHERE entity_id = ?
               ORDER BY timestamp""",
            (entity_id,),
        ).fetchall()

        dates = sorted(set(r["timestamp"][:10] for r in rows)) if rows else []

        # Extract specific metric series
        def _extract_series(metric_name):
            vals = [r["value"] for r in rows if r["metric_name"] == metric_name]
            return {"values": vals, "current": vals[-1] if vals else 0.0}

        # Fetch traces
        traces = db.execute(
            """SELECT * FROM agent_traces
               WHERE entity_id = ?
               ORDER BY timestamp DESC LIMIT 20""",
            (entity_id,),
        ).fetchall()

        trace_list = []
        for t in traces:
            steps = db.execute(
                "SELECT * FROM agent_trace_steps WHERE trace_id = ? ORDER BY step_order",
                (t["trace_id"],),
            ).fetchall()
            trace_list.append({
                "trace_id": t["trace_id"],
                "timestamp": t["timestamp"],
                "query": t["query"],
                "response": t["response"],
                "total_latency_ms": t["total_latency"],
                "tool_count": len(steps),
                "voice_score": t["voice_score"],
                "policy_pass": bool(t["policy_pass"]),
                "steps": [
                    {
                        "tool": s["tool"],
                        "action": s["action"],
                        "latency_ms": s["latency_ms"],
                        "status": s["status"],
                    }
                    for s in steps
                ],
            })

        if not rows and not traces:
            # Return empty structure
            return {
                "agent": entity,
                "dates": [],
                "task_completion": {"values": [], "current": 0.0},
                "groundedness": {"values": [], "current": 0.0},
                "safety": {"values": [], "current": 0.0},
                "tokens": {
                    "dates": [],
                    "input_tokens": [],
                    "output_tokens": [],
                    "cost_per_day": [],
                    "total_cost_30d": 0,
                    "avg_cost_per_interaction": 0,
                },
                "tool_usage": [],
                "safety_events": [],
                "task_breakdown": [],
                "linked_model_health": [],
                "policy_violations": {"violations": [], "summary": {}, "total": 0},
                "voice_scores": {"dimensions": {}, "dates": [], "overall": 0.0},
                "traces": [],
            }

        return {
            "agent": entity,
            "dates": dates,
            "task_completion": _extract_series("task_completion"),
            "groundedness": _extract_series("groundedness"),
            "safety": _extract_series("safety"),
            "tokens": {
                "dates": dates,
                "input_tokens": [r["value"] for r in rows if r["metric_name"] == "input_tokens"],
                "output_tokens": [r["value"] for r in rows if r["metric_name"] == "output_tokens"],
                "cost_per_day": [r["value"] for r in rows if r["metric_name"] == "cost_per_day"],
                "total_cost_30d": 0,
                "avg_cost_per_interaction": 0,
            },
            "tool_usage": [],        # Populated from agent_traces in later sessions
            "safety_events": [],     # Populated in later sessions
            "task_breakdown": [],    # Populated in later sessions
            "linked_model_health": [],
            "policy_violations": {"violations": [], "summary": {}, "total": 0},
            "voice_scores": {"dimensions": {}, "dates": dates, "overall": 0.0},
            "traces": trace_list,
        }
    finally:
        db.close()


def _live_fairness_metrics(entity_id):
    """Query cohort_metrics for fairness/equity data."""
    entity = _live_get_entity(entity_id)
    if not entity:
        return None

    db = _get_live_db()
    try:
        rows = db.execute(
            """SELECT cohort_dim, cohort_name, metric_name, value, sample_size
               FROM cohort_metrics
               WHERE entity_id = ?""",
            (entity_id,),
        ).fetchall()

        if not rows:
            return {"demographics": {}, "overall_disparity": 0.0, "overall_fairness": 0.0}

        demographics = {}
        for r in rows:
            dim = r["cohort_dim"]
            if dim not in demographics:
                demographics[dim] = {"label": dim.replace("_", " ").title(), "groups": []}
            # Find or create group entry
            group = next((g for g in demographics[dim]["groups"] if g["name"] == r["cohort_name"]), None)
            if not group:
                group = {
                    "name": r["cohort_name"],
                    "size": r["sample_size"] or 0,
                    "accuracy": 0.0,
                    "precision": 0.0,
                    "recall": 0.0,
                    "f1_score": 0.0,
                    "fpr": 0.0,
                    "selection_rate": 0.0,
                    "disparate_impact": 1.0,
                }
                demographics[dim]["groups"].append(group)
            group[r["metric_name"]] = r["value"]

        return {"demographics": demographics, "overall_disparity": 0.0, "overall_fairness": 0.85}
    finally:
        db.close()


def _live_model_lineage(entity_id):
    """Query lineage_events for version history."""
    entity = _live_get_entity(entity_id)
    if not entity:
        return None

    db = _get_live_db()
    try:
        rows = db.execute(
            """SELECT * FROM lineage_events
               WHERE entity_id = ?
               ORDER BY timestamp DESC""",
            (entity_id,),
        ).fetchall()

        versions = []
        for r in rows:
            meta = json.loads(r["metadata"]) if r["metadata"] else {}
            versions.append({
                "version": r["version"] or "unknown",
                "status": meta.get("status", "Unknown"),
                "deployed_date": r["timestamp"][:10],
                "retired_date": meta.get("retired_date"),
                "trigger": r["trigger"] or "Manual",
                "performance_at_deploy": meta.get("performance_at_deploy"),
                "performance_at_retire": meta.get("performance_at_retire"),
                "training_records": meta.get("training_records"),
                "training_duration_min": meta.get("training_duration_min"),
                "champion_challenger": meta.get("champion_challenger", "Unknown"),
                "notes": meta.get("notes", ""),
            })

        return {
            "model": entity,
            "current_version": entity.get("version", "unknown"),
            "total_versions": len(versions),
            "versions": versions,
            "total_retrains": max(0, len(versions) - 1),
            "avg_version_lifespan_days": None,
        }
    finally:
        db.close()


def _live_agent_lineage(entity_id):
    """Agent lineage — same structure as model lineage."""
    return _live_model_lineage(entity_id)


def _live_alerts():
    """Query alerts table."""
    db = _get_live_db()
    try:
        rows = db.execute(
            "SELECT * FROM alerts ORDER BY timestamp DESC"
        ).fetchall()
        result = []
        for r in rows:
            # Look up entity name
            entity = db.execute(
                "SELECT name, entity_type, project_id FROM entity_registry WHERE entity_id = ?",
                (r["entity_id"],),
            ).fetchone()
            result.append({
                "id": f"alert-{r['id']}",
                "timestamp": r["timestamp"],
                "timestamp_relative": "",
                "model_id": r["entity_id"],
                "model_name": entity["name"] if entity else "Unknown",
                "entity_type": entity["entity_type"] if entity else "model",
                "project_name": "",
                "type": r["alert_type"],
                "icon": "exclamation-triangle",
                "severity": r["severity"],
                "message": r["description"] or r["title"],
                "acknowledged": bool(r["resolved"]),
            })
        return result
    finally:
        db.close()


def _live_summary_stats():
    """Compute summary stats from entity_registry."""
    db = _get_live_db()
    try:
        models = db.execute(
            "SELECT status, COUNT(*) as cnt FROM entity_registry WHERE entity_type='model' GROUP BY status"
        ).fetchall()
        agents = db.execute(
            "SELECT status, COUNT(*) as cnt FROM entity_registry WHERE entity_type='agent' GROUP BY status"
        ).fetchall()

        model_counts = {r["status"]: r["cnt"] for r in models}
        agent_counts = {r["status"]: r["cnt"] for r in agents}

        return {
            "total_models": sum(model_counts.values()),
            "healthy_models": model_counts.get("Healthy", 0),
            "warning_models": model_counts.get("Warning", 0),
            "critical_models": model_counts.get("Critical", 0) + model_counts.get("Degraded", 0),
            "total_agents": sum(agent_counts.values()),
            "operational_agents": agent_counts.get("Operational", 0),
            "warning_agents": agent_counts.get("Warning", 0),
            "degraded_agents": agent_counts.get("Degraded", 0),
        }
    finally:
        db.close()


def _live_projects():
    """Query projects from DB plus entity counts from entity_registry."""
    db = _get_live_db()
    try:
        proj_rows = db.execute("SELECT * FROM projects").fetchall()
        projects = []
        for p in proj_rows:
            pid = p["id"]
            model_count = db.execute(
                "SELECT COUNT(*) as cnt FROM entity_registry WHERE project_id=? AND entity_type='model'",
                (pid,),
            ).fetchone()["cnt"]
            agent_count = db.execute(
                "SELECT COUNT(*) as cnt FROM entity_registry WHERE project_id=? AND entity_type='agent'",
                (pid,),
            ).fetchone()["cnt"]

            # Fetch entity lists for this project
            model_rows = db.execute(
                "SELECT * FROM entity_registry WHERE project_id=? AND entity_type='model'",
                (pid,),
            ).fetchall()
            agent_rows = db.execute(
                "SELECT * FROM entity_registry WHERE project_id=? AND entity_type='agent'",
                (pid,),
            ).fetchall()

            projects.append({
                "id": pid,
                "name": p["name"],
                "description": p["description"],
                "owner": p["owner"],
                "team": p["team"],
                "created_date": p["created_date"],
                "status": p["status"],
                "model_count": model_count,
                "models": [
                    {"id": r["entity_id"], "name": r["name"], "status": r["status"]}
                    for r in model_rows
                ],
                "agent_count": agent_count,
                "agents": [
                    {"id": r["entity_id"], "name": r["name"], "status": r["status"]}
                    for r in agent_rows
                ],
            })
        return projects
    finally:
        db.close()
