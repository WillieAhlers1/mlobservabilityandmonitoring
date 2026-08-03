"""Data quality handler.

Processes CTEs with event_type='data_quality' and writes to the data_quality table.
"""

import sqlite3
from ingestion.models import CanonicalTelemetryEvent


class DataQualityHandler:
    """Handles data_quality CTEs → data_quality table."""

    target_table = "data_quality"

    def write(self, db: sqlite3.Connection, cte: CanonicalTelemetryEvent,
              entity_id: str, value, mapping) -> None:
        """Write data quality metrics to the data_quality table.

        Supports two formats:
          1. Single: {feature, missing_rate, outlier_rate, schema_valid, row_count}
          2. Batch: {features: [{feature, missing_rate, outlier_rate, schema_valid, row_count}]}

        Args:
            db: SQLite connection.
            cte: The canonical telemetry event.
            entity_id: Resolved entity ID.
            value: Not used (payload carries structured data).
            mapping: The MappingDefinition used.
        """
        features = cte.payload.get("features")

        if features and isinstance(features, list):
            # Batch format
            for feat in features:
                self._insert_row(db, entity_id, cte.timestamp, feat)
        else:
            # Single format — payload is the row itself
            self._insert_row(db, entity_id, cte.timestamp, cte.payload)

    def _insert_row(self, db, entity_id, timestamp, data):
        """Insert a single data quality row."""
        feature = data.get("feature", "unknown")
        missing_rate = data.get("missing_rate")
        outlier_rate = data.get("outlier_rate")
        schema_valid = data.get("schema_valid", True)
        row_count = data.get("row_count")

        db.execute(
            """INSERT INTO data_quality
               (entity_id, timestamp, feature, missing_rate, outlier_rate, schema_valid, row_count)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (entity_id, timestamp, feature, missing_rate, outlier_rate,
             1 if schema_valid else 0, row_count),
        )
        db.commit()
