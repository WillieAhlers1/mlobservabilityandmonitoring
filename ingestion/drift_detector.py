"""Schema drift detection for the ingestion pipeline.

Monitors parse failure rates and field-level anomalies to detect when
upstream data sources change schema without notice.
"""

import sqlite3
from datetime import datetime, timezone, timedelta


def detect_schema_drift(db: sqlite3.Connection,
                        window_hours: int = 24,
                        failure_threshold: float = 0.05) -> list[dict]:
    """Detect potential schema drift by analyzing rejection patterns.

    Schema drift is suspected when:
    - More than `failure_threshold` (default 5%) of events are rejected
      with transform/validation errors in the given time window.
    - A specific connector+event_type combo shows elevated rejections.

    Args:
        db: SQLite connection.
        window_hours: How far back to look (default 24h).
        failure_threshold: Rejection rate threshold to trigger alert (default 5%).

    Returns:
        List of drift alert dicts, each with:
            connector: source_connector with drift
            event_type: event_type with drift
            total_events: total events in window
            rejected_events: rejected count in window
            rejection_rate: ratio
            common_reasons: list of (reason, count)
            detected_at: ISO timestamp
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=window_hours)).isoformat()

    # Group by connector + event_type
    rows = db.execute(
        """SELECT source_connector, event_type,
                  COUNT(*) as total,
                  SUM(CASE WHEN processing_status = 'rejected' THEN 1 ELSE 0 END) as rejected
           FROM staging_events
           WHERE received_at >= ?
           GROUP BY source_connector, event_type""",
        (cutoff,),
    ).fetchall()

    alerts = []
    now = datetime.now(timezone.utc).isoformat()

    for row in rows:
        total = row["total"]
        rejected = row["rejected"]
        if total == 0:
            continue

        rate = rejected / total
        if rate >= failure_threshold:
            # Get common rejection reasons
            reasons = db.execute(
                """SELECT rejection_reason, COUNT(*) as cnt
                   FROM staging_events
                   WHERE source_connector = ? AND event_type = ?
                     AND processing_status = 'rejected'
                     AND received_at >= ?
                   GROUP BY rejection_reason
                   ORDER BY cnt DESC
                   LIMIT 5""",
                (row["source_connector"], row["event_type"], cutoff),
            ).fetchall()

            common_reasons = [
                {"reason": r["rejection_reason"] or "Unknown", "count": r["cnt"]}
                for r in reasons
            ]

            alerts.append({
                "connector": row["source_connector"],
                "event_type": row["event_type"],
                "total_events": total,
                "rejected_events": rejected,
                "rejection_rate": round(rate, 4),
                "common_reasons": common_reasons,
                "detected_at": now,
            })

    return alerts


def generate_schema_drift_alerts(db: sqlite3.Connection,
                                 window_hours: int = 24,
                                 failure_threshold: float = 0.05) -> int:
    """Detect schema drift and write alerts to the alerts table.

    Only generates alerts if a matching unresolved alert doesn't already exist.

    Args:
        db: SQLite connection.
        window_hours: Lookback window.
        failure_threshold: Rejection threshold.

    Returns:
        Number of new alerts generated.
    """
    drift_alerts = detect_schema_drift(db, window_hours, failure_threshold)
    generated = 0

    for alert in drift_alerts:
        # Check if we already have an unresolved schema drift alert for this connector
        existing = db.execute(
            """SELECT id FROM alerts
               WHERE alert_type = 'schema_drift'
                 AND resolved = 0
                 AND description LIKE ?""",
            (f"%{alert['connector']}%{alert['event_type']}%",),
        ).fetchone()

        if existing:
            continue

        # Need an entity to attach alert to — use first entity from rejected events
        entity_row = db.execute(
            """SELECT er.entity_id
               FROM staging_events se
               JOIN entity_aliases ea ON ea.alias_value = se.source_entity_ref
               JOIN entity_registry er ON er.entity_id = ea.entity_id
               WHERE se.source_connector = ? AND se.event_type = ?
               LIMIT 1""",
            (alert["connector"], alert["event_type"]),
        ).fetchone()

        # If no entity found, use a sentinel
        entity_id = entity_row["entity_id"] if entity_row else "system"

        # Determine severity
        severity = "high" if alert["rejection_rate"] > 0.2 else "medium"

        reasons_text = "; ".join(
            f"{r['reason']} ({r['count']}x)" for r in alert["common_reasons"][:3]
        )
        description = (
            f"Schema drift detected for {alert['connector']}/{alert['event_type']}: "
            f"{alert['rejection_rate']*100:.1f}% rejection rate "
            f"({alert['rejected_events']}/{alert['total_events']} events). "
            f"Top reasons: {reasons_text}"
        )

        db.execute(
            """INSERT INTO alerts
               (entity_id, timestamp, severity, alert_type, title, description, resolved)
               VALUES (?, ?, ?, ?, ?, ?, 0)""",
            (entity_id, alert["detected_at"], severity, "schema_drift",
             f"Schema drift: {alert['connector']}/{alert['event_type']}", description),
        )
        generated += 1

    db.commit()
    return generated
