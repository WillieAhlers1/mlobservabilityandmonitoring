"""Metric completeness scoring for monitored entities.

Computes what percentage of expected metrics are populated for an entity,
enabling the dashboard to show "awaiting telemetry" vs partial vs full states.
"""

import sqlite3
from typing import Optional


# Expected metrics by entity/model type
EXPECTED_METRICS = {
    "classification": ["accuracy", "precision", "recall", "f1_score", "auc_roc"],
    "regression": ["r2_score", "mae", "rmse", "mape"],
    "agent": ["task_completion", "groundedness", "safety"],
}


def compute_completeness(db: sqlite3.Connection, entity_id: str,
                         entity_type: str = "model",
                         model_type: str = "classification") -> dict:
    """Compute metric completeness score for an entity.

    Args:
        db: SQLite connection.
        entity_id: Entity to check.
        entity_type: "model" or "agent".
        model_type: "classification" or "regression" (for models).

    Returns:
        Dict with:
            score: float 0.0-1.0 (percentage of expected metrics present)
            present: list of metric names found
            missing: list of metric names not found
            expected: list of all expected metric names
            status: "none" | "partial" | "complete"
    """
    if entity_type == "agent":
        expected = EXPECTED_METRICS["agent"]
    else:
        expected = EXPECTED_METRICS.get(model_type, EXPECTED_METRICS["classification"])

    # Query distinct metric names for this entity
    rows = db.execute(
        "SELECT DISTINCT metric_name FROM metric_timeseries WHERE entity_id = ?",
        (entity_id,),
    ).fetchall()
    present_metrics = {r["metric_name"] for r in rows}

    # Also check aggregated table
    agg_rows = db.execute(
        "SELECT DISTINCT metric_name FROM metric_timeseries_agg WHERE entity_id = ?",
        (entity_id,),
    ).fetchall()
    present_metrics.update(r["metric_name"] for r in agg_rows)

    present = [m for m in expected if m in present_metrics]
    missing = [m for m in expected if m not in present_metrics]

    if not expected:
        score = 1.0
    else:
        score = len(present) / len(expected)

    if score == 0:
        status = "none"
    elif score < 1.0:
        status = "partial"
    else:
        status = "complete"

    return {
        "score": round(score, 2),
        "present": present,
        "missing": missing,
        "expected": expected,
        "status": status,
    }


def has_any_telemetry(db: sqlite3.Connection, entity_id: str) -> bool:
    """Check if an entity has received any telemetry data at all.

    Checks metric_timeseries, drift_snapshots, and agent_traces.
    """
    row = db.execute(
        "SELECT COUNT(*) as cnt FROM metric_timeseries WHERE entity_id = ? LIMIT 1",
        (entity_id,),
    ).fetchone()
    if row["cnt"] > 0:
        return True

    row = db.execute(
        "SELECT COUNT(*) as cnt FROM drift_snapshots WHERE entity_id = ? LIMIT 1",
        (entity_id,),
    ).fetchone()
    if row["cnt"] > 0:
        return True

    row = db.execute(
        "SELECT COUNT(*) as cnt FROM agent_traces WHERE entity_id = ? LIMIT 1",
        (entity_id,),
    ).fetchone()
    if row["cnt"] > 0:
        return True

    return False
