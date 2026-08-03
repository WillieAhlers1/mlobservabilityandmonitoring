"""Alerts event handler.

Processes CTEs with event_type='alert' and writes to the alerts table.
"""

import sqlite3
from ingestion.models import CanonicalTelemetryEvent


class AlertsHandler:
    """Handles alert CTEs → alerts table."""

    target_table = "alerts"

    def write(self, db: sqlite3.Connection, cte: CanonicalTelemetryEvent,
              entity_id: str, value, mapping) -> None:
        """Write an alert event to the alerts table.

        Args:
            db: SQLite connection.
            cte: The canonical telemetry event.
            entity_id: Resolved entity ID.
            value: Not used for alerts (payload carries all fields).
            mapping: The MappingDefinition used.
        """
        severity = cte.payload.get("severity", "medium")
        alert_type = cte.payload.get("alert_type", "unknown")
        title = cte.payload.get("title", "Untitled Alert")
        description = cte.payload.get("description", "")
        resolved = cte.payload.get("resolved", False)
        resolved_at = cte.payload.get("resolved_at")

        db.execute(
            """INSERT INTO alerts
               (entity_id, timestamp, severity, alert_type, title, description, resolved, resolved_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (entity_id, cte.timestamp, severity, alert_type, title, description,
             1 if resolved else 0, resolved_at),
        )
        db.commit()
