"""Staging store operations for the telemetry ingestion pipeline.

The staging store is an append-only event log. Each Canonical Telemetry Event (CTE)
is written with a deterministic event_id for deduplication. The processing_status
field is the only mutable column — it transitions from pending → mapped | rejected.

Usage:
    from ingestion.staging import compute_event_id, insert_ctes, fetch_pending_batch, mark_processed
"""

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from typing import Optional

from ingestion.models import CanonicalTelemetryEvent


def compute_event_id(source_connector: str, source_entity_ref: str,
                     event_type: str, timestamp: str,
                     metric_name: Optional[str] = None) -> str:
    """Compute a deterministic event_id for deduplication.

    The hash is derived from the tuple of identifying fields so that the same
    logical event always maps to the same ID regardless of when it arrives.

    Args:
        source_connector: Connector identifier (e.g., "mlflow", "file_drop").
        source_entity_ref: Source entity reference string.
        event_type: Event type (metric, drift, alert, trace, lifecycle).
        timestamp: ISO 8601 event timestamp.
        metric_name: Optional metric name for metric-type events.

    Returns:
        A 32-character hex string (SHA-256 truncated).
    """
    key = f"{source_connector}|{source_entity_ref}|{event_type}|{timestamp}|{metric_name or ''}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]


def insert_ctes(db: sqlite3.Connection, ctes: list[CanonicalTelemetryEvent]) -> int:
    """Insert CTEs into the staging store with deduplication.

    Uses INSERT OR IGNORE so duplicate event_ids are silently dropped.

    Args:
        db: SQLite connection with row_factory set.
        ctes: List of CTE objects to insert.

    Returns:
        Number of rows actually inserted (excludes duplicates).
    """
    if not ctes:
        return 0

    cursor = db.cursor()
    inserted = 0
    for cte in ctes:
        cursor.execute(
            """INSERT OR IGNORE INTO staging_events
               (event_id, source_connector, source_entity_ref, event_type,
                timestamp, received_at, mapping_version, payload, processing_status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                cte.event_id,
                cte.source_connector,
                cte.source_entity_ref,
                cte.event_type,
                cte.timestamp,
                cte.received_at,
                cte.mapping_version,
                json.dumps(cte.payload),
                cte.processing_status,
            ),
        )
        inserted += cursor.rowcount
    db.commit()
    return inserted


def insert_single_cte(db: sqlite3.Connection, cte: CanonicalTelemetryEvent) -> bool:
    """Insert a single CTE. Returns True if inserted, False if duplicate."""
    return insert_ctes(db, [cte]) == 1


def fetch_pending_batch(db: sqlite3.Connection, limit: int = 1000) -> list[CanonicalTelemetryEvent]:
    """Fetch the oldest pending CTEs from the staging store.

    Args:
        db: SQLite connection.
        limit: Maximum number of CTEs to return.

    Returns:
        List of CTE objects ordered by timestamp ascending.
    """
    rows = db.execute(
        """SELECT event_id, source_connector, source_entity_ref, event_type,
                  timestamp, received_at, mapping_version, payload, processing_status
           FROM staging_events
           WHERE processing_status = 'pending'
           ORDER BY timestamp ASC
           LIMIT ?""",
        (limit,),
    ).fetchall()

    result = []
    for row in rows:
        payload = json.loads(row["payload"]) if isinstance(row["payload"], str) else row["payload"]
        result.append(CanonicalTelemetryEvent(
            event_id=row["event_id"],
            source_connector=row["source_connector"],
            source_entity_ref=row["source_entity_ref"],
            event_type=row["event_type"],
            timestamp=row["timestamp"],
            received_at=row["received_at"],
            mapping_version=row["mapping_version"],
            payload=payload,
            processing_status=row["processing_status"],
        ))
    return result


def mark_processed(db: sqlite3.Connection, event_id: str, status: str,
                   reason: Optional[str] = None) -> None:
    """Transition a CTE's processing status.

    Args:
        db: SQLite connection.
        event_id: The event to update.
        status: New status ("mapped", "rejected", "duplicate").
        reason: Optional rejection reason (set when status="rejected").
    """
    now = datetime.now(timezone.utc).isoformat()
    db.execute(
        """UPDATE staging_events
           SET processing_status = ?, rejection_reason = ?, processed_at = ?
           WHERE event_id = ?""",
        (status, reason, now, event_id),
    )
    db.commit()


def mark_batch_processed(db: sqlite3.Connection,
                         updates: list[tuple[str, str, Optional[str]]]) -> None:
    """Batch update processing status for multiple CTEs.

    Args:
        db: SQLite connection.
        updates: List of (event_id, status, reason) tuples.
    """
    now = datetime.now(timezone.utc).isoformat()
    cursor = db.cursor()
    for event_id, status, reason in updates:
        cursor.execute(
            """UPDATE staging_events
               SET processing_status = ?, rejection_reason = ?, processed_at = ?
               WHERE event_id = ?""",
            (status, reason, now, event_id),
        )
    db.commit()


def count_by_status(db: sqlite3.Connection) -> dict[str, int]:
    """Return counts of events grouped by processing_status."""
    rows = db.execute(
        "SELECT processing_status, COUNT(*) as cnt FROM staging_events GROUP BY processing_status"
    ).fetchall()
    return {row["processing_status"]: row["cnt"] for row in rows}
