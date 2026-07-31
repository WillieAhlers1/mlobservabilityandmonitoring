"""Aggregation engine for time-bucketing metric data.

Rolls raw metric_timeseries rows into time-bucketed aggregate rows in
metric_timeseries_agg. Dashboards query the agg table for efficient rendering.

Bucket sizes: "1h" (1 hour), "1d" (1 day)
Aggregation methods: last, mean, max, min, sum
"""

import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Optional


def compute_bucket_start(timestamp: str, bucket_size: str) -> str:
    """Compute the start of the time bucket for a given timestamp.

    Args:
        timestamp: ISO 8601 timestamp (e.g., "2026-07-30T14:35:00Z").
        bucket_size: "1h" or "1d".

    Returns:
        ISO 8601 bucket start (e.g., "2026-07-30T14:00:00Z" for 1h bucket).
    """
    ts = _parse_timestamp(timestamp)

    if bucket_size == "1d":
        bucket = ts.replace(hour=0, minute=0, second=0, microsecond=0)
    else:  # default "1h"
        bucket = ts.replace(minute=0, second=0, microsecond=0)

    return bucket.strftime("%Y-%m-%dT%H:%M:%SZ")


def aggregate_bucket(db: sqlite3.Connection, entity_id: str, metric_name: str,
                     bucket_start: str, bucket_size: str,
                     agg_method: str = "last") -> Optional[dict]:
    """Compute the aggregate value for a single bucket.

    Reads raw rows from metric_timeseries within the bucket window and computes
    the aggregate value.

    Args:
        db: SQLite connection.
        entity_id: Entity to aggregate for.
        metric_name: Metric name to aggregate.
        bucket_start: ISO 8601 start of the bucket.
        bucket_size: "1h" or "1d".
        agg_method: One of "last", "mean", "max", "min", "sum".

    Returns:
        Dict with {value, sample_count} or None if no data in bucket.
    """
    bucket_end = _compute_bucket_end(bucket_start, bucket_size)

    rows = db.execute(
        """SELECT value FROM metric_timeseries
           WHERE entity_id = ? AND metric_name = ?
             AND timestamp >= ? AND timestamp < ?
           ORDER BY timestamp ASC""",
        (entity_id, metric_name, bucket_start, bucket_end),
    ).fetchall()

    if not rows:
        return None

    values = [r["value"] for r in rows]
    agg_value = _compute_agg(values, agg_method)

    return {"value": agg_value, "sample_count": len(values)}


def upsert_aggregate(db: sqlite3.Connection, entity_id: str, metric_name: str,
                     bucket_start: str, bucket_size: str, agg_method: str,
                     value: float, sample_count: int,
                     semantic_tag: Optional[str] = None) -> None:
    """Insert or update an aggregate row.

    Uses INSERT OR REPLACE on the UNIQUE constraint.
    """
    db.execute(
        """INSERT OR REPLACE INTO metric_timeseries_agg
           (entity_id, metric_name, semantic_tag, bucket_start, bucket_size, agg_method, value, sample_count)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (entity_id, metric_name, semantic_tag, bucket_start, bucket_size, agg_method, value, sample_count),
    )
    db.commit()


def aggregate_entity_metric(db: sqlite3.Connection, entity_id: str, metric_name: str,
                            bucket_size: str = "1h", agg_method: str = "last",
                            since: Optional[str] = None) -> int:
    """Aggregate all buckets for an entity/metric from raw data.

    Args:
        db: SQLite connection.
        entity_id: Entity to aggregate.
        metric_name: Metric to aggregate.
        bucket_size: Bucket size ("1h" or "1d").
        agg_method: Aggregation method.
        since: Optional ISO timestamp — only aggregate buckets after this time.

    Returns:
        Number of buckets written.
    """
    query = """SELECT DISTINCT timestamp FROM metric_timeseries
               WHERE entity_id = ? AND metric_name = ?"""
    params = [entity_id, metric_name]
    if since:
        query += " AND timestamp >= ?"
        params.append(since)
    query += " ORDER BY timestamp"

    rows = db.execute(query, params).fetchall()
    if not rows:
        return 0

    # Find unique bucket starts
    bucket_starts = set()
    for row in rows:
        bs = compute_bucket_start(row["timestamp"], bucket_size)
        bucket_starts.add(bs)

    buckets_written = 0
    for bs in sorted(bucket_starts):
        result = aggregate_bucket(db, entity_id, metric_name, bs, bucket_size, agg_method)
        if result:
            upsert_aggregate(db, entity_id, metric_name, bs, bucket_size,
                             agg_method, result["value"], result["sample_count"])
            buckets_written += 1

    return buckets_written


def reaggregate_bucket(db: sqlite3.Connection, entity_id: str, metric_name: str,
                       timestamp: str, bucket_size: str = "1h",
                       agg_method: str = "last") -> bool:
    """Re-aggregate the bucket containing the given timestamp.

    Called when a new event arrives that falls into an existing bucket.

    Returns:
        True if bucket was updated, False if no data found.
    """
    bucket_start = compute_bucket_start(timestamp, bucket_size)
    result = aggregate_bucket(db, entity_id, metric_name, bucket_start, bucket_size, agg_method)
    if result:
        upsert_aggregate(db, entity_id, metric_name, bucket_start, bucket_size,
                         agg_method, result["value"], result["sample_count"])
        return True
    return False


def is_within_grace_period(event_timestamp: str, grace_period_hours: int = 6) -> bool:
    """Check if an event timestamp is within the grace period for re-aggregation.

    Events within the grace period trigger re-aggregation of their bucket.
    Events outside the grace period are accepted into staging but do NOT
    update the aggregation table.

    Args:
        event_timestamp: ISO 8601 timestamp of the event.
        grace_period_hours: How many hours back is acceptable.

    Returns:
        True if the event is within grace period (should trigger re-agg).
    """
    now = datetime.now(timezone.utc)
    ts = _parse_timestamp(event_timestamp)
    cutoff = now - timedelta(hours=grace_period_hours)
    return ts >= cutoff


def aggregate_after_mapping(db: sqlite3.Connection, entity_id: str, metric_name: str,
                            timestamp: str, bucket_size: str = "1h",
                            agg_method: str = "last",
                            grace_period_hours: int = 6) -> bool:
    """Called after a CTE is mapped to trigger aggregation if appropriate.

    Only re-aggregates if the event is within the grace period.

    Returns:
        True if aggregation was performed, False if skipped (outside grace).
    """
    if not is_within_grace_period(timestamp, grace_period_hours):
        return False
    return reaggregate_bucket(db, entity_id, metric_name, timestamp, bucket_size, agg_method)


# ── Internal helpers ────────────────────────────────────────────────────────

def _parse_timestamp(timestamp: str) -> datetime:
    """Parse ISO 8601 timestamp to datetime."""
    # Handle both "Z" suffix and "+00:00"
    ts_str = timestamp.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(ts_str)
    except ValueError:
        # Fallback: try without timezone
        return datetime.strptime(timestamp[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)


def _compute_bucket_end(bucket_start: str, bucket_size: str) -> str:
    """Compute the exclusive end of a bucket."""
    ts = _parse_timestamp(bucket_start)
    if bucket_size == "1d":
        end = ts + timedelta(days=1)
    else:  # "1h"
        end = ts + timedelta(hours=1)
    return end.strftime("%Y-%m-%dT%H:%M:%SZ")


def _compute_agg(values: list[float], method: str) -> float:
    """Compute aggregate value from a list of floats."""
    if not values:
        return 0.0

    if method == "last":
        return values[-1]
    elif method == "mean":
        return sum(values) / len(values)
    elif method == "max":
        return max(values)
    elif method == "min":
        return min(values)
    elif method == "sum":
        return sum(values)
    else:
        return values[-1]  # default to last
