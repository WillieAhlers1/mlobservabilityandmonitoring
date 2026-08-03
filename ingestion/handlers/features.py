"""Feature importance handler.

Processes CTEs with event_type='feature_importance' and writes to the feature_importance table.
"""

import sqlite3
from ingestion.models import CanonicalTelemetryEvent


class FeaturesHandler:
    """Handles feature_importance CTEs → feature_importance table."""

    target_table = "feature_importance"

    def write(self, db: sqlite3.Connection, cte: CanonicalTelemetryEvent,
              entity_id: str, value, mapping) -> None:
        """Write feature importance data to feature_importance table.

        Supports two formats:
          1. Single: {feature, importance, method}
          2. Batch: {features: [{feature, importance}], method}

        Args:
            db: SQLite connection.
            cte: The canonical telemetry event.
            entity_id: Resolved entity ID.
            value: Not used (payload carries structured data).
            mapping: The MappingDefinition used.
        """
        method = cte.payload.get("method", "shap")
        features = cte.payload.get("features")

        if features and isinstance(features, list):
            # Batch format
            for feat in features:
                feature_name = feat.get("feature", "unknown")
                importance = feat.get("importance", 0.0)
                db.execute(
                    """INSERT INTO feature_importance
                       (entity_id, timestamp, feature, importance, method)
                       VALUES (?, ?, ?, ?, ?)""",
                    (entity_id, cte.timestamp, feature_name, importance, method),
                )
        else:
            # Single format
            feature_name = cte.payload.get("feature", "unknown")
            importance = cte.payload.get("importance", value or 0.0)
            db.execute(
                """INSERT INTO feature_importance
                   (entity_id, timestamp, feature, importance, method)
                   VALUES (?, ?, ?, ?, ?)""",
                (entity_id, cte.timestamp, feature_name, importance, method),
            )
        db.commit()
