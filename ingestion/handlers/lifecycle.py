"""Lifecycle event handler.

Processes CTEs with event_type='lifecycle' and writes to the lineage_events table.
"""

import json
import sqlite3
from ingestion.models import CanonicalTelemetryEvent


class LifecycleHandler:
    """Handles lifecycle CTEs → lineage_events table."""

    target_table = "lineage_events"

    def write(self, db: sqlite3.Connection, cte: CanonicalTelemetryEvent,
              entity_id: str, value, mapping) -> None:
        """Write a lifecycle event to lineage_events.

        Args:
            db: SQLite connection.
            cte: The canonical telemetry event.
            entity_id: Resolved entity ID.
            value: Not used (payload carries structured data).
            mapping: The MappingDefinition used.
        """
        event_type = cte.payload.get("lifecycle_type", cte.payload.get("event_type", "deployment"))
        version = cte.payload.get("version")
        trigger = cte.payload.get("trigger")

        # Everything else goes into metadata JSON
        metadata_keys = {"lifecycle_type", "event_type", "version", "trigger"}
        metadata = {k: v for k, v in cte.payload.items() if k not in metadata_keys}

        db.execute(
            """INSERT INTO lineage_events
               (entity_id, timestamp, event_type, version, trigger, metadata)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (entity_id, cte.timestamp, event_type, version, trigger,
             json.dumps(metadata) if metadata else None),
        )
        db.commit()
