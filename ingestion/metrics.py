"""Ingestion pipeline metrics and health statistics.

Provides functions to compute throughput, lag, rejection rates, and
connector health summaries for the observability dashboard.
"""

import sqlite3
from datetime import datetime, timezone, timedelta


def get_pipeline_stats(db: sqlite3.Connection) -> dict:
    """Compute pipeline throughput and rejection stats.

    Returns:
        Dict with:
            total_events: Total events in staging store
            processed_1h: Events processed in last hour
            processed_24h: Events processed in last 24 hours
            pending: Currently pending events
            rejected: Total rejected events
            rejection_rate: rejected / total ratio (0.0 - 1.0)
            mapped: Total successfully mapped events
    """
    now = datetime.now(timezone.utc)
    one_hour_ago = (now - timedelta(hours=1)).isoformat()
    twenty_four_hours_ago = (now - timedelta(hours=24)).isoformat()

    total = db.execute("SELECT COUNT(*) as cnt FROM staging_events").fetchone()["cnt"]
    pending = db.execute(
        "SELECT COUNT(*) as cnt FROM staging_events WHERE processing_status = 'pending'"
    ).fetchone()["cnt"]
    rejected = db.execute(
        "SELECT COUNT(*) as cnt FROM staging_events WHERE processing_status = 'rejected'"
    ).fetchone()["cnt"]
    mapped = db.execute(
        "SELECT COUNT(*) as cnt FROM staging_events WHERE processing_status = 'mapped'"
    ).fetchone()["cnt"]

    processed_1h = db.execute(
        """SELECT COUNT(*) as cnt FROM staging_events
           WHERE processing_status IN ('mapped', 'rejected')
             AND processed_at >= ?""",
        (one_hour_ago,),
    ).fetchone()["cnt"]

    processed_24h = db.execute(
        """SELECT COUNT(*) as cnt FROM staging_events
           WHERE processing_status IN ('mapped', 'rejected')
             AND processed_at >= ?""",
        (twenty_four_hours_ago,),
    ).fetchone()["cnt"]

    rejection_rate = (rejected / total) if total > 0 else 0.0

    return {
        "total_events": total,
        "processed_1h": processed_1h,
        "processed_24h": processed_24h,
        "pending": pending,
        "rejected": rejected,
        "mapped": mapped,
        "rejection_rate": round(rejection_rate, 4),
    }


def get_processing_lag(db: sqlite3.Connection) -> dict:
    """Compute processing lag — time between newest pending event and now.

    Returns:
        Dict with:
            lag_seconds: Seconds since the oldest pending event was received (None if no pending)
            oldest_pending_at: ISO timestamp of oldest pending event
            newest_received_at: ISO timestamp of most recent event
    """
    oldest_pending = db.execute(
        """SELECT received_at FROM staging_events
           WHERE processing_status = 'pending'
           ORDER BY received_at ASC LIMIT 1"""
    ).fetchone()

    newest_received = db.execute(
        "SELECT received_at FROM staging_events ORDER BY received_at DESC LIMIT 1"
    ).fetchone()

    now = datetime.now(timezone.utc)
    lag_seconds = None
    oldest_pending_at = None

    if oldest_pending:
        oldest_pending_at = oldest_pending["received_at"]
        try:
            pending_time = datetime.fromisoformat(oldest_pending_at.replace("Z", "+00:00"))
            lag_seconds = int((now - pending_time).total_seconds())
        except (ValueError, TypeError):
            lag_seconds = None

    return {
        "lag_seconds": lag_seconds,
        "oldest_pending_at": oldest_pending_at,
        "newest_received_at": newest_received["received_at"] if newest_received else None,
    }


def get_connector_health(db: sqlite3.Connection) -> list[dict]:
    """Fetch connector health status from connector_health table.

    Returns:
        List of dicts with connector state info.
    """
    rows = db.execute(
        "SELECT * FROM connector_health ORDER BY connector_id"
    ).fetchall()

    connectors = []
    for row in rows:
        connectors.append({
            "connector_id": row["connector_id"],
            "connector_type": row["connector_type"],
            "state": row["state"],
            "last_success": row["last_success"],
            "last_failure": row["last_failure"],
            "consecutive_failures": row["consecutive_failures"],
            "error_message": row["error_message"],
        })
    return connectors


def get_rejected_events(db: sqlite3.Connection, limit: int = 100,
                        offset: int = 0) -> list[dict]:
    """Fetch rejected CTEs from staging for the dead-letter queue.

    Args:
        db: SQLite connection.
        limit: Max events to return.
        offset: Pagination offset.

    Returns:
        List of rejected event dicts with their rejection reasons.
    """
    rows = db.execute(
        """SELECT event_id, source_connector, source_entity_ref, event_type,
                  timestamp, received_at, rejection_reason, processed_at
           FROM staging_events
           WHERE processing_status = 'rejected'
           ORDER BY processed_at DESC
           LIMIT ? OFFSET ?""",
        (limit, offset),
    ).fetchall()

    return [
        {
            "event_id": row["event_id"],
            "source_connector": row["source_connector"],
            "source_entity_ref": row["source_entity_ref"],
            "event_type": row["event_type"],
            "timestamp": row["timestamp"],
            "received_at": row["received_at"],
            "rejection_reason": row["rejection_reason"],
            "processed_at": row["processed_at"],
        }
        for row in rows
    ]


def get_rejected_count(db: sqlite3.Connection) -> int:
    """Get total count of rejected events."""
    return db.execute(
        "SELECT COUNT(*) as cnt FROM staging_events WHERE processing_status = 'rejected'"
    ).fetchone()["cnt"]


def reprocess_event(db: sqlite3.Connection, event_id: str) -> bool:
    """Reset a rejected event back to pending for reprocessing.

    Args:
        db: SQLite connection.
        event_id: The event to reprocess.

    Returns:
        True if the event was found and reset, False otherwise.
    """
    cursor = db.execute(
        """UPDATE staging_events
           SET processing_status = 'pending', rejection_reason = NULL, processed_at = NULL
           WHERE event_id = ? AND processing_status = 'rejected'""",
        (event_id,),
    )
    db.commit()
    return cursor.rowcount > 0


def reprocess_all_rejected(db: sqlite3.Connection) -> int:
    """Reset all rejected events back to pending.

    Returns:
        Number of events reset.
    """
    cursor = db.execute(
        """UPDATE staging_events
           SET processing_status = 'pending', rejection_reason = NULL, processed_at = NULL
           WHERE processing_status = 'rejected'"""
    )
    db.commit()
    return cursor.rowcount


def get_late_event_count(db: sqlite3.Connection, grace_period_hours: int = 6) -> int:
    """Count events where received_at - timestamp > grace_period.

    Args:
        db: SQLite connection.
        grace_period_hours: Threshold for what constitutes a 'late' event.

    Returns:
        Count of late events.
    """
    # SQLite date arithmetic: compare the difference in hours
    rows = db.execute(
        """SELECT COUNT(*) as cnt FROM staging_events
           WHERE (julianday(received_at) - julianday(timestamp)) * 24 > ?""",
        (grace_period_hours,),
    ).fetchone()
    return rows["cnt"] if rows else 0
