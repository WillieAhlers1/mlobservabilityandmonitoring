"""Background scheduler for the ingestion pipeline.

Runs connector polling and mapping engine batch processing on configured
intervals. Only activates when DATA_SOURCE == "live".

Usage:
    from ingestion.scheduler import IngestionScheduler
    scheduler = IngestionScheduler(db_path, connectors, mappings_dir, config)
    scheduler.start()
    # ... app runs ...
    scheduler.shutdown()
"""

import logging
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler

from ingestion.connector_registry import create_all_connectors
from ingestion.connectors.base import BaseConnector
from ingestion.mapping_engine import MappingEngine
from ingestion.staging import count_by_status, fetch_pending_batch, insert_ctes

logger = logging.getLogger(__name__)


class IngestionScheduler:
    """Manages background jobs for the ingestion pipeline."""

    def __init__(self, db_path: str, connectors_config: list[dict],
                 mappings_dir: Path, ingestion_config: dict):
        """Initialize the scheduler.

        Args:
            db_path: Path to the SQLite database.
            connectors_config: List of connector config dicts from app.yaml.
            mappings_dir: Directory containing mapping YAML files.
            ingestion_config: Ingestion settings dict (batch_size, poll_interval, etc.).
        """
        self._db_path = db_path
        self._mappings_dir = mappings_dir
        self._ingestion_config = ingestion_config
        self._poll_interval = ingestion_config.get("poll_interval_seconds", 60)
        self._batch_size = ingestion_config.get("batch_size", 1000)
        self._processing_interval = ingestion_config.get("processing_interval_seconds", 10)

        # Create connector instances
        self._connectors = create_all_connectors(connectors_config)

        # APScheduler instance
        self._scheduler = BackgroundScheduler(
            job_defaults={"coalesce": True, "max_instances": 1}
        )
        self._running = False

        # Metrics
        self._last_poll_results: dict[str, dict] = {}
        self._last_processing_result: Optional[dict] = None
        self._processing_lag_seconds: float = 0.0

    @property
    def running(self) -> bool:
        """Whether the scheduler is currently running."""
        return self._running

    @property
    def connectors(self) -> list[BaseConnector]:
        """Registered connector instances."""
        return self._connectors

    @property
    def processing_lag_seconds(self) -> float:
        """Time lag between oldest pending CTE and now, in seconds."""
        return self._processing_lag_seconds

    @property
    def last_processing_result(self) -> Optional[dict]:
        """Result dict from the most recent mapping engine run."""
        return self._last_processing_result

    def start(self) -> None:
        """Start the background scheduler with all jobs."""
        if self._running:
            return

        # Register connector poll jobs
        for connector in self._connectors:
            # Skip webhook connectors (they are push-based)
            if connector.connector_type() == "webhook":
                continue

            interval = self._poll_interval
            self._scheduler.add_job(
                self._poll_connector,
                "interval",
                seconds=interval,
                args=[connector],
                id=f"poll_{connector.connector_id()}",
                name=f"Poll {connector.connector_id()}",
            )

        # Register mapping engine processing job
        self._scheduler.add_job(
            self._process_pending,
            "interval",
            seconds=self._processing_interval,
            id="process_pending",
            name="Process pending CTEs",
        )

        # Register lag computation job
        self._scheduler.add_job(
            self._compute_lag,
            "interval",
            seconds=30,
            id="compute_lag",
            name="Compute processing lag",
        )

        self._scheduler.start()
        self._running = True
        logger.info("Ingestion scheduler started with %d connectors", len(self._connectors))

    def shutdown(self, wait: bool = True) -> None:
        """Shut down the scheduler gracefully."""
        if not self._running:
            return
        self._scheduler.shutdown(wait=wait)
        self._running = False
        logger.info("Ingestion scheduler stopped")

    def run_once(self) -> dict:
        """Execute one poll + process cycle synchronously (for testing).

        Returns:
            Dict with poll and processing results.
        """
        poll_results = {}
        for connector in self._connectors:
            if connector.connector_type() == "webhook":
                continue
            result = self._poll_connector(connector)
            poll_results[connector.connector_id()] = result

        process_result = self._process_pending()
        self._compute_lag()

        return {
            "poll": poll_results,
            "processing": process_result,
            "lag_seconds": self._processing_lag_seconds,
        }

    def _get_db(self) -> sqlite3.Connection:
        """Open a new DB connection for this thread."""
        conn = sqlite3.connect(self._db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _poll_connector(self, connector: BaseConnector) -> dict:
        """Poll a single connector and insert CTEs into staging."""
        db = self._get_db()
        try:
            ctes = connector.poll()
            inserted = 0
            if ctes:
                inserted = insert_ctes(db, ctes)
            connector.update_health(db, success=True)
            result = {"polled": len(ctes), "inserted": inserted}
            self._last_poll_results[connector.connector_id()] = result
            return result
        except Exception as e:
            connector.update_health(db, success=False, error_message=str(e))
            result = {"polled": 0, "inserted": 0, "error": str(e)}
            self._last_poll_results[connector.connector_id()] = result
            logger.error("Connector %s poll failed: %s", connector.connector_id(), e)
            return result
        finally:
            db.close()

    def _process_pending(self) -> dict:
        """Process a batch of pending CTEs through the mapping engine."""
        db = self._get_db()
        try:
            engine = MappingEngine(db, self._mappings_dir)
            result = engine.process_batch(batch_size=self._batch_size)
            self._last_processing_result = result
            return result
        except Exception as e:
            logger.error("Mapping engine error: %s", e)
            self._last_processing_result = {"error": str(e)}
            return {"processed": 0, "mapped": 0, "rejected": 0, "no_mapping": 0, "error": str(e)}
        finally:
            db.close()

    def _compute_lag(self) -> None:
        """Compute processing lag from oldest pending CTE."""
        db = self._get_db()
        try:
            row = db.execute(
                """SELECT MIN(received_at) as oldest
                   FROM staging_events
                   WHERE processing_status = 'pending'"""
            ).fetchone()
            if row and row["oldest"]:
                oldest_str = row["oldest"].replace("Z", "+00:00")
                try:
                    oldest = datetime.fromisoformat(oldest_str)
                    now = datetime.now(timezone.utc)
                    self._processing_lag_seconds = max(0, (now - oldest).total_seconds())
                except ValueError:
                    self._processing_lag_seconds = 0.0
            else:
                self._processing_lag_seconds = 0.0
        finally:
            db.close()

    def get_status(self) -> dict:
        """Return current scheduler status for health monitoring."""
        return {
            "running": self._running,
            "connectors": len(self._connectors),
            "poll_results": dict(self._last_poll_results),
            "last_processing": self._last_processing_result,
            "lag_seconds": self._processing_lag_seconds,
        }
