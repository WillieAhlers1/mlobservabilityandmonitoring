"""Base connector interface for telemetry source plugins.

All connectors implement this ABC to provide a uniform poll/health interface.
"""

import sqlite3
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Iterator, Optional

from ingestion.models import CanonicalTelemetryEvent


class BaseConnector(ABC):
    """Plugin interface for telemetry source connectors."""

    @abstractmethod
    def connector_id(self) -> str:
        """Unique identifier for this connector instance."""

    @abstractmethod
    def connector_type(self) -> str:
        """Type identifier (e.g., 'file_drop', 'webhook', 'mlflow')."""

    @abstractmethod
    def poll(self) -> list[CanonicalTelemetryEvent]:
        """Fetch new events. Returns list of CTEs."""

    @abstractmethod
    def health_check(self) -> bool:
        """Return True if the source is reachable and ready."""

    def update_health(self, db: sqlite3.Connection, success: bool,
                      error_message: Optional[str] = None) -> None:
        """Update connector_health table after a poll attempt."""
        now = datetime.now(timezone.utc).isoformat()

        existing = db.execute(
            "SELECT * FROM connector_health WHERE connector_id = ?",
            (self.connector_id(),),
        ).fetchone()

        if success:
            if existing:
                db.execute(
                    """UPDATE connector_health
                       SET last_success = ?, consecutive_failures = 0,
                           state = 'healthy', error_message = NULL
                       WHERE connector_id = ?""",
                    (now, self.connector_id()),
                )
            else:
                db.execute(
                    """INSERT INTO connector_health
                       (connector_id, connector_type, last_success, consecutive_failures, state)
                       VALUES (?, ?, ?, 0, 'healthy')""",
                    (self.connector_id(), self.connector_type(), now),
                )
        else:
            if existing:
                failures = (existing["consecutive_failures"] or 0) + 1
                state = "degraded" if failures < 3 else "down"
                db.execute(
                    """UPDATE connector_health
                       SET last_failure = ?, consecutive_failures = ?,
                           state = ?, error_message = ?
                       WHERE connector_id = ?""",
                    (now, failures, state, error_message, self.connector_id()),
                )
            else:
                db.execute(
                    """INSERT INTO connector_health
                       (connector_id, connector_type, last_failure, consecutive_failures, state, error_message)
                       VALUES (?, ?, ?, 1, 'degraded', ?)""",
                    (self.connector_id(), self.connector_type(), now, error_message),
                )
        db.commit()
