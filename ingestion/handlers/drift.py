"""Drift event handler.

Processes CTEs with event_type='drift' and writes to the drift_snapshots table.
"""

import sqlite3
from ingestion.models import CanonicalTelemetryEvent


class DriftHandler:
    """Handles drift CTEs → drift_snapshots table."""

    target_table = "drift_snapshots"

    def write(self, db: sqlite3.Connection, cte: CanonicalTelemetryEvent,
              entity_id: str, value, mapping) -> None:
        """Write a drift event to drift_snapshots.

        Args:
            db: SQLite connection.
            cte: The canonical telemetry event.
            entity_id: Resolved entity ID.
            value: Transformed drift value.
            mapping: The MappingDefinition used.
        """
        drift_type = cte.payload.get("drift_type", "psi")
        scope = cte.payload.get("scope", "overall")
        status = cte.payload.get("status")

        # Derive status from value if not explicitly provided
        if status is None and value is not None:
            if value > 0.2:
                status = "Critical"
            elif value > 0.1:
                status = "Warning"
            else:
                status = "Normal"

        db.execute(
            """INSERT INTO drift_snapshots
               (entity_id, timestamp, drift_type, scope, value, status)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (entity_id, cte.timestamp, drift_type, scope, value, status),
        )
        db.commit()
