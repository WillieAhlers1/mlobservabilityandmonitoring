"""Cohort metrics handler.

Processes CTEs with event_type='cohort' and writes to the cohort_metrics table.
"""

import sqlite3
from ingestion.models import CanonicalTelemetryEvent


class CohortsHandler:
    """Handles cohort CTEs → cohort_metrics table."""

    target_table = "cohort_metrics"

    def write(self, db: sqlite3.Connection, cte: CanonicalTelemetryEvent,
              entity_id: str, value, mapping) -> None:
        """Write cohort metric(s) to cohort_metrics.

        The payload may contain a single metric or multiple metrics per cohort.
        Supports two formats:
          1. Single: {cohort_name, cohort_dim, metric_name, value, sample_size}
          2. Batch: {cohorts: [{cohort_name, cohort_dim, metrics: {name: val}, sample_size}]}

        Args:
            db: SQLite connection.
            cte: The canonical telemetry event.
            entity_id: Resolved entity ID.
            value: Not used (payload carries structured data).
            mapping: The MappingDefinition used.
        """
        cohorts = cte.payload.get("cohorts")
        if cohorts and isinstance(cohorts, list):
            # Batch format
            for cohort in cohorts:
                cohort_name = cohort.get("cohort_name", "unknown")
                cohort_dim = cohort.get("cohort_dim", "segment")
                sample_size = cohort.get("sample_size")
                metrics = cohort.get("metrics", {})
                for metric_name, metric_value in metrics.items():
                    self._insert_row(db, entity_id, cte.timestamp,
                                     cohort_name, cohort_dim, metric_name,
                                     metric_value, sample_size)
        else:
            # Single format
            cohort_name = cte.payload.get("cohort_name", "unknown")
            cohort_dim = cte.payload.get("cohort_dim", "segment")
            metric_name = cte.payload.get("metric_name", "unknown")
            metric_value = cte.payload.get("value", value)
            sample_size = cte.payload.get("sample_size")
            self._insert_row(db, entity_id, cte.timestamp,
                             cohort_name, cohort_dim, metric_name,
                             metric_value, sample_size)

    def _insert_row(self, db, entity_id, timestamp, cohort_name, cohort_dim,
                    metric_name, value, sample_size):
        """Insert a single cohort metric row."""
        db.execute(
            """INSERT INTO cohort_metrics
               (entity_id, timestamp, cohort_name, cohort_dim, metric_name, value, sample_size)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (entity_id, timestamp, cohort_name, cohort_dim, metric_name, value, sample_size),
        )
        db.commit()
