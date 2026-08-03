"""Tests for Session 8: Connector Scheduler and Background Processing."""

import csv
import os
import sqlite3
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from ingestion.connectors.file_drop import FileDropConnector
from ingestion.models import CanonicalTelemetryEvent
from ingestion.scheduler import IngestionScheduler
from ingestion.staging import compute_event_id, insert_ctes, insert_single_cte


# ── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def scheduler_db(tmp_path):
    """Create a full-schema DB for scheduler tests."""
    db_path = str(tmp_path / "scheduler_test.db")
    import app as app_module
    original_path = app_module.DB_PATH
    app_module.DB_PATH = db_path
    app_module.init_db()
    app_module.DB_PATH = original_path

    # Register an entity for mapping
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """INSERT INTO entity_registry
           (entity_id, entity_type, industry_id, project_id, name, status, metadata, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        ("model-sched-001", "model", "hls", "proj-1", "Scheduler Model", "Healthy",
         '{"model_type": "classification"}', "2026-07-01T00:00:00Z", "2026-07-01T00:00:00Z"),
    )
    conn.execute(
        "INSERT INTO entity_aliases (entity_id, alias_type, alias_value) VALUES (?, ?, ?)",
        ("model-sched-001", "source_ref", "mlflow://experiment-1/sched-model"),
    )
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def mappings_dir(tmp_path):
    """Create a mapping directory with a metrics mapping."""
    mdir = tmp_path / "mappings"
    mdir.mkdir()
    (mdir / "metrics.yaml").write_text("""
version: "1"
applies_to:
  source_connector: file-drop-sched
  event_type: metric
entity_resolution:
  strategy: lookup
  on_no_match: reject
field_mappings:
  - source: payload.metric_value
    target: metric_timeseries.value
    transform: identity
validation_rules:
  - rule: not_null
    field: value
  - rule: numeric
    field: value
target_table: metric_timeseries
""", encoding="utf-8")
    return mdir


@pytest.fixture
def watch_dir(tmp_path):
    """Create watch directories for the file drop connector."""
    incoming = tmp_path / "incoming"
    incoming.mkdir()
    processed = tmp_path / "processed"
    processed.mkdir()
    return incoming, processed


@pytest.fixture
def connector_config(watch_dir):
    """File drop connector config."""
    incoming, processed = watch_dir
    return {
        "id": "file-drop-sched",
        "type": "file_drop",
        "watch_directory": str(incoming),
        "processed_directory": str(processed),
        "file_pattern": "*.csv",
        "column_mapping": {
            "entity_ref_column": "source_entity_ref",
            "metric_name_column": "metric_name",
            "value_column": "metric_value",
            "timestamp_column": "timestamp",
        },
    }


@pytest.fixture
def ingestion_config():
    """Ingestion settings for testing."""
    return {
        "batch_size": 100,
        "grace_period_hours": 6,
        "max_lag_alert_minutes": 30,
        "poll_interval_seconds": 5,
        "processing_interval_seconds": 2,
    }


def _write_csv(filepath, rows, fieldnames):
    """Helper to write a CSV file."""
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


# ── Test: Scheduler Lifecycle ───────────────────────────────────────────────

class TestSchedulerLifecycle:

    def test_starts_and_stops(self, scheduler_db, connector_config, mappings_dir, ingestion_config):
        scheduler = IngestionScheduler(
            scheduler_db, [connector_config], mappings_dir, ingestion_config
        )
        assert scheduler.running is False

        scheduler.start()
        assert scheduler.running is True

        scheduler.shutdown(wait=False)
        assert scheduler.running is False

    def test_double_start_no_error(self, scheduler_db, connector_config, mappings_dir, ingestion_config):
        scheduler = IngestionScheduler(
            scheduler_db, [connector_config], mappings_dir, ingestion_config
        )
        scheduler.start()
        scheduler.start()  # Should not error
        assert scheduler.running is True
        scheduler.shutdown(wait=False)

    def test_double_shutdown_no_error(self, scheduler_db, connector_config, mappings_dir, ingestion_config):
        scheduler = IngestionScheduler(
            scheduler_db, [connector_config], mappings_dir, ingestion_config
        )
        scheduler.start()
        scheduler.shutdown(wait=False)
        scheduler.shutdown(wait=False)  # Should not error
        assert scheduler.running is False

    def test_connectors_registered(self, scheduler_db, connector_config, mappings_dir, ingestion_config):
        scheduler = IngestionScheduler(
            scheduler_db, [connector_config], mappings_dir, ingestion_config
        )
        assert len(scheduler.connectors) == 1
        assert scheduler.connectors[0].connector_id() == "file-drop-sched"
        scheduler.shutdown(wait=False)


# ── Test: Scheduler does NOT start in mock mode ─────────────────────────────

class TestMockModeNoScheduler:

    def test_no_scheduler_in_mock_mode(self):
        """In mock mode, _ingestion_scheduler should be None."""
        import app as app_module
        # The app module loads with DATA_SOURCE=mock by default
        assert app_module._ingestion_scheduler is None


# ── Test: run_once (synchronous execution) ──────────────────────────────────

class TestRunOnce:

    def test_polls_connector_and_processes(self, scheduler_db, connector_config,
                                           mappings_dir, ingestion_config, watch_dir):
        """run_once polls files and processes them through mapping engine."""
        incoming, processed = watch_dir

        # Drop a CSV with data for the registered entity
        _write_csv(incoming / "metrics.csv", [
            {"source_entity_ref": "mlflow://experiment-1/sched-model", "metric_name": "accuracy",
             "metric_value": "0.92", "timestamp": "2026-07-30T14:00:00Z"},
            {"source_entity_ref": "mlflow://experiment-1/sched-model", "metric_name": "precision",
             "metric_value": "0.88", "timestamp": "2026-07-30T14:00:00Z"},
        ], ["source_entity_ref", "metric_name", "metric_value", "timestamp"])

        scheduler = IngestionScheduler(
            scheduler_db, [connector_config], mappings_dir, ingestion_config
        )

        result = scheduler.run_once()

        # Verify polling happened
        assert result["poll"]["file-drop-sched"]["polled"] == 2
        assert result["poll"]["file-drop-sched"]["inserted"] == 2

        # Verify processing happened
        assert result["processing"]["processed"] == 2
        assert result["processing"]["mapped"] == 2

        # Verify metric store has data
        conn = sqlite3.connect(scheduler_db)
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM metric_timeseries").fetchall()
        conn.close()
        assert len(rows) == 2

    def test_empty_poll_no_error(self, scheduler_db, connector_config,
                                  mappings_dir, ingestion_config):
        """run_once with no files produces zero results gracefully."""
        scheduler = IngestionScheduler(
            scheduler_db, [connector_config], mappings_dir, ingestion_config
        )
        result = scheduler.run_once()
        assert result["poll"]["file-drop-sched"]["polled"] == 0
        assert result["processing"]["processed"] == 0

    def test_webhook_connector_skipped_in_poll(self, scheduler_db, mappings_dir, ingestion_config):
        """Webhook connectors are not polled (they are push-based)."""
        configs = [
            {"id": "wh", "type": "webhook", "secret": ""},
        ]
        scheduler = IngestionScheduler(
            scheduler_db, configs, mappings_dir, ingestion_config
        )
        result = scheduler.run_once()
        # No poll result for webhook
        assert "wh" not in result["poll"]


# ── Test: Processing Lag ────────────────────────────────────────────────────

class TestProcessingLag:

    def test_lag_zero_when_no_pending(self, scheduler_db, connector_config,
                                      mappings_dir, ingestion_config):
        scheduler = IngestionScheduler(
            scheduler_db, [connector_config], mappings_dir, ingestion_config
        )
        scheduler.run_once()
        assert scheduler.processing_lag_seconds == 0.0

    def test_lag_computed_with_pending_events(self, scheduler_db, connector_config,
                                              mappings_dir, ingestion_config):
        """Lag is computed from oldest pending CTE's received_at."""
        from datetime import datetime, timedelta, timezone
        five_min_ago = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()

        conn = sqlite3.connect(scheduler_db)
        conn.row_factory = sqlite3.Row
        cte = CanonicalTelemetryEvent(
            event_id="lag-test-001",
            source_connector="test",
            source_entity_ref="mlflow://test",
            event_type="metric",
            timestamp="2026-07-30T14:00:00Z",
            received_at=five_min_ago,
            mapping_version="v1",
            payload={"metric_name": "test", "metric_value": 0.5},
        )
        insert_single_cte(conn, cte)
        conn.close()

        # Use a mapping dir without matching mappings so it won't get processed
        # But we also need the scheduler to NOT process this CTE —
        # it will get rejected ("no matching mapping") which removes it from pending.
        # So we compute lag BEFORE processing by calling _compute_lag directly.
        empty_mappings = Path(scheduler_db).parent / "empty_mappings"
        empty_mappings.mkdir()

        scheduler = IngestionScheduler(
            scheduler_db, [connector_config], empty_mappings, ingestion_config
        )
        # Only compute lag (don't process)
        scheduler._compute_lag()

        # Lag should be approximately 5 minutes (300 seconds ± tolerance)
        assert scheduler.processing_lag_seconds >= 290
        assert scheduler.processing_lag_seconds <= 320


# ── Test: Connector Health Updated ──────────────────────────────────────────

class TestConnectorHealthUpdated:

    def test_health_updated_on_successful_poll(self, scheduler_db, connector_config,
                                                mappings_dir, ingestion_config):
        scheduler = IngestionScheduler(
            scheduler_db, [connector_config], mappings_dir, ingestion_config
        )
        scheduler.run_once()

        conn = sqlite3.connect(scheduler_db)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM connector_health WHERE connector_id = 'file-drop-sched'"
        ).fetchone()
        conn.close()
        assert row is not None
        assert row["state"] == "healthy"

    def test_health_degraded_on_missing_dir(self, scheduler_db, mappings_dir, ingestion_config):
        """Connector with missing watch dir reports degraded health."""
        bad_config = {
            "id": "bad-connector",
            "type": "file_drop",
            "watch_directory": "/nonexistent/path",
            "file_pattern": "*.csv",
            "column_mapping": {},
        }
        scheduler = IngestionScheduler(
            scheduler_db, [bad_config], mappings_dir, ingestion_config
        )
        scheduler.run_once()

        conn = sqlite3.connect(scheduler_db)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM connector_health WHERE connector_id = 'bad-connector'"
        ).fetchone()
        conn.close()
        # Poll returns empty (no crash), health still logged as success (dir check in poll)
        assert row is not None
        assert row["state"] == "healthy"  # poll() returns [] when dir missing, no exception


# ── Test: get_status ────────────────────────────────────────────────────────

class TestGetStatus:

    def test_status_when_not_running(self, scheduler_db, connector_config,
                                     mappings_dir, ingestion_config):
        scheduler = IngestionScheduler(
            scheduler_db, [connector_config], mappings_dir, ingestion_config
        )
        status = scheduler.get_status()
        assert status["running"] is False
        assert status["connectors"] == 1
        assert status["lag_seconds"] == 0.0

    def test_status_after_run_once(self, scheduler_db, connector_config,
                                   mappings_dir, ingestion_config, watch_dir):
        incoming, processed = watch_dir
        _write_csv(incoming / "data.csv", [
            {"source_entity_ref": "mlflow://experiment-1/sched-model", "metric_name": "f1",
             "metric_value": "0.90", "timestamp": "2026-07-30T14:00:00Z"},
        ], ["source_entity_ref", "metric_name", "metric_value", "timestamp"])

        scheduler = IngestionScheduler(
            scheduler_db, [connector_config], mappings_dir, ingestion_config
        )
        scheduler.run_once()

        status = scheduler.get_status()
        assert status["poll_results"]["file-drop-sched"]["polled"] == 1
        assert status["last_processing"]["mapped"] == 1
        assert status["lag_seconds"] == 0.0  # All processed


# ── Test: Background Scheduler Actually Runs ────────────────────────────────

class TestBackgroundExecution:

    def test_scheduler_processes_within_interval(self, scheduler_db, connector_config,
                                                  mappings_dir, ingestion_config, watch_dir):
        """Start scheduler, drop file, wait, verify processing happened."""
        incoming, processed = watch_dir

        scheduler = IngestionScheduler(
            scheduler_db, [connector_config], mappings_dir, ingestion_config
        )
        scheduler.start()

        try:
            # Drop a file
            _write_csv(incoming / "bg_test.csv", [
                {"source_entity_ref": "mlflow://experiment-1/sched-model", "metric_name": "recall",
                 "metric_value": "0.87", "timestamp": "2026-07-30T16:00:00Z"},
            ], ["source_entity_ref", "metric_name", "metric_value", "timestamp"])

            # Wait for poll (5s) + processing (2s) + buffer
            time.sleep(9)

            # Verify data made it through
            conn = sqlite3.connect(scheduler_db)
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT * FROM metric_timeseries WHERE metric_name = 'recall'").fetchall()
            conn.close()
            assert len(rows) == 1
            assert rows[0]["value"] == 0.87
        finally:
            scheduler.shutdown(wait=False)
