"""Tests for Session 6: Connector Framework and FileDropConnector."""

import csv
import json
import os
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from ingestion.connector_registry import create_all_connectors, create_connector
from ingestion.connectors.base import BaseConnector
from ingestion.connectors.file_drop import FileDropConnector
from ingestion.mapping_engine import MappingEngine
from ingestion.staging import fetch_pending_batch, insert_ctes


# ── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def watch_dir(tmp_path):
    """Create watch and processed directories."""
    incoming = tmp_path / "incoming"
    incoming.mkdir()
    processed = tmp_path / "processed"
    processed.mkdir()
    return incoming, processed


@pytest.fixture
def connector_config(watch_dir):
    """Return a valid connector config dict."""
    incoming, processed = watch_dir
    return {
        "id": "test-file-drop",
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
def connector(connector_config):
    """Create a FileDropConnector instance."""
    return FileDropConnector(connector_config)


@pytest.fixture
def e2e_db(tmp_path):
    """Full DB with entity registered for E2E testing."""
    db_path = str(tmp_path / "e2e_test.db")
    import app as app_module
    original_path = app_module.DB_PATH
    app_module.DB_PATH = db_path
    app_module.init_db()
    app_module.DB_PATH = original_path

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Register entity with alias matching synthetic data ref
    conn.execute(
        """INSERT INTO entity_registry
           (entity_id, entity_type, industry_id, project_id, name, status, metadata, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        ("model-e2e-001", "model", "hls", "proj-1", "E2E Model", "Healthy",
         '{"model_type": "classification"}', "2026-07-01T00:00:00Z", "2026-07-01T00:00:00Z"),
    )
    conn.execute(
        "INSERT INTO entity_aliases (entity_id, alias_type, alias_value) VALUES (?, ?, ?)",
        ("model-e2e-001", "source_ref", "mlflow://experiment-1/e2e-model"),
    )
    conn.commit()
    yield conn
    conn.close()


def _write_csv(filepath, rows, fieldnames):
    """Helper to write a CSV file."""
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _write_json(filepath, records):
    """Helper to write a JSON file."""
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(records, f)


# ── Test: FileDropConnector reads CSV ───────────────────────────────────────

class TestFileDropCSV:

    def test_reads_csv_produces_ctes(self, connector, watch_dir):
        incoming, processed = watch_dir
        _write_csv(incoming / "metrics.csv", [
            {"source_entity_ref": "mlflow://exp/model-a", "metric_name": "accuracy",
             "metric_value": "0.934", "timestamp": "2026-07-30T14:00:00Z"},
            {"source_entity_ref": "mlflow://exp/model-a", "metric_name": "precision",
             "metric_value": "0.91", "timestamp": "2026-07-30T14:00:00Z"},
        ], ["source_entity_ref", "metric_name", "metric_value", "timestamp"])

        ctes = connector.poll()
        assert len(ctes) == 2
        assert ctes[0].source_entity_ref == "mlflow://exp/model-a"
        assert ctes[0].event_type == "metric"
        assert ctes[0].source_connector == "test-file-drop"

    def test_file_moved_after_processing(self, connector, watch_dir):
        incoming, processed = watch_dir
        _write_csv(incoming / "test.csv", [
            {"source_entity_ref": "ref", "metric_name": "acc", "metric_value": "0.9",
             "timestamp": "2026-07-30T14:00:00Z"},
        ], ["source_entity_ref", "metric_name", "metric_value", "timestamp"])

        connector.poll()
        assert not (incoming / "test.csv").exists()
        assert (processed / "test.csv").exists()

    def test_already_processed_file_ignored(self, connector, watch_dir):
        incoming, processed = watch_dir
        _write_csv(incoming / "data.csv", [
            {"source_entity_ref": "ref", "metric_name": "acc", "metric_value": "0.9",
             "timestamp": "2026-07-30T14:00:00Z"},
        ], ["source_entity_ref", "metric_name", "metric_value", "timestamp"])

        ctes1 = connector.poll()
        assert len(ctes1) == 1

        # File is moved, so second poll finds nothing
        ctes2 = connector.poll()
        assert len(ctes2) == 0

    def test_infers_drift_event_type_from_filename(self, connector, watch_dir):
        incoming, processed = watch_dir
        _write_csv(incoming / "drift_events.csv", [
            {"source_entity_ref": "ref", "drift_type": "psi", "scope": "overall",
             "value": "0.12", "timestamp": "2026-07-30T14:00:00Z"},
        ], ["source_entity_ref", "drift_type", "scope", "value", "timestamp"])

        ctes = connector.poll()
        assert len(ctes) == 1
        assert ctes[0].event_type == "drift"

    def test_empty_entity_ref_skipped(self, connector, watch_dir):
        incoming, processed = watch_dir
        _write_csv(incoming / "data.csv", [
            {"source_entity_ref": "", "metric_name": "acc", "metric_value": "0.9",
             "timestamp": "2026-07-30T14:00:00Z"},
            {"source_entity_ref": "valid-ref", "metric_name": "acc", "metric_value": "0.85",
             "timestamp": "2026-07-30T14:00:00Z"},
        ], ["source_entity_ref", "metric_name", "metric_value", "timestamp"])

        ctes = connector.poll()
        assert len(ctes) == 1
        assert ctes[0].source_entity_ref == "valid-ref"

    def test_value_converted_to_float(self, connector, watch_dir):
        incoming, processed = watch_dir
        _write_csv(incoming / "data.csv", [
            {"source_entity_ref": "ref", "metric_name": "acc", "metric_value": "0.934",
             "timestamp": "2026-07-30T14:00:00Z"},
        ], ["source_entity_ref", "metric_name", "metric_value", "timestamp"])

        ctes = connector.poll()
        assert ctes[0].payload["metric_value"] == 0.934


# ── Test: FileDropConnector reads JSON ──────────────────────────────────────

class TestFileDropJSON:

    def test_reads_json_array(self, watch_dir):
        incoming, processed = watch_dir
        config = {
            "id": "json-connector",
            "type": "file_drop",
            "watch_directory": str(incoming),
            "processed_directory": str(processed),
            "file_pattern": "*.json",
            "column_mapping": {
                "entity_ref_column": "source_entity_ref",
                "timestamp_column": "timestamp",
                "metric_name_column": "metric_name",
            },
        }
        conn = FileDropConnector(config)

        _write_json(incoming / "data.json", [
            {"source_entity_ref": "ref-1", "event_type": "metric",
             "metric_name": "accuracy", "metric_value": 0.93,
             "timestamp": "2026-07-30T14:00:00Z"},
            {"source_entity_ref": "ref-2", "event_type": "drift",
             "metric_name": "psi", "metric_value": 0.15,
             "timestamp": "2026-07-30T14:00:00Z"},
        ])

        ctes = conn.poll()
        assert len(ctes) == 2
        assert ctes[0].event_type == "metric"
        assert ctes[1].event_type == "drift"

    def test_json_file_moved(self, watch_dir):
        incoming, processed = watch_dir
        config = {
            "id": "json-conn",
            "type": "file_drop",
            "watch_directory": str(incoming),
            "processed_directory": str(processed),
            "file_pattern": "*.json",
            "column_mapping": {},
        }
        conn = FileDropConnector(config)
        _write_json(incoming / "test.json", [
            {"source_entity_ref": "ref", "timestamp": "2026-07-30T14:00:00Z"},
        ])

        conn.poll()
        assert not (incoming / "test.json").exists()
        assert (processed / "test.json").exists()


# ── Test: Connector Health ──────────────────────────────────────────────────

class TestConnectorHealth:

    def test_health_check_valid_dir(self, connector, watch_dir):
        assert connector.health_check() is True

    def test_health_check_missing_dir(self, tmp_path):
        config = {
            "id": "bad-conn",
            "type": "file_drop",
            "watch_directory": str(tmp_path / "nonexistent"),
            "column_mapping": {},
        }
        conn = FileDropConnector(config)
        assert conn.health_check() is False

    def test_update_health_success(self, connector, e2e_db):
        connector.update_health(e2e_db, success=True)
        row = e2e_db.execute(
            "SELECT * FROM connector_health WHERE connector_id = 'test-file-drop'"
        ).fetchone()
        assert row is not None
        assert row["state"] == "healthy"
        assert row["consecutive_failures"] == 0

    def test_update_health_failure(self, connector, e2e_db):
        connector.update_health(e2e_db, success=False, error_message="Dir not found")
        row = e2e_db.execute(
            "SELECT * FROM connector_health WHERE connector_id = 'test-file-drop'"
        ).fetchone()
        assert row["state"] == "degraded"
        assert row["consecutive_failures"] == 1
        assert row["error_message"] == "Dir not found"

    def test_consecutive_failures_escalate(self, connector, e2e_db):
        for _ in range(3):
            connector.update_health(e2e_db, success=False, error_message="fail")
        row = e2e_db.execute(
            "SELECT * FROM connector_health WHERE connector_id = 'test-file-drop'"
        ).fetchone()
        assert row["state"] == "down"
        assert row["consecutive_failures"] == 3

    def test_success_resets_failures(self, connector, e2e_db):
        connector.update_health(e2e_db, success=False, error_message="fail")
        connector.update_health(e2e_db, success=True)
        row = e2e_db.execute(
            "SELECT * FROM connector_health WHERE connector_id = 'test-file-drop'"
        ).fetchone()
        assert row["state"] == "healthy"
        assert row["consecutive_failures"] == 0


# ── Test: Connector Registry ────────────────────────────────────────────────

class TestConnectorRegistry:

    def test_create_file_drop(self, connector_config):
        conn = create_connector(connector_config)
        assert isinstance(conn, FileDropConnector)
        assert conn.connector_id() == "test-file-drop"
        assert conn.connector_type() == "file_drop"

    def test_create_all_connectors(self, connector_config):
        connectors = create_all_connectors([connector_config])
        assert len(connectors) == 1
        assert isinstance(connectors[0], BaseConnector)

    def test_unknown_type_raises(self):
        with pytest.raises(ValueError, match="Unknown connector type"):
            create_connector({"id": "x", "type": "unknown_type"})

    def test_missing_id_raises(self):
        with pytest.raises(ValueError, match="missing 'id'"):
            create_connector({"type": "file_drop", "watch_directory": "/tmp"})

    def test_missing_type_raises(self):
        with pytest.raises(ValueError, match="missing 'type'"):
            create_connector({"id": "x"})


# ── Test: End-to-End Pipeline ───────────────────────────────────────────────

class TestEndToEndPipeline:

    def test_file_drop_to_metric_store(self, e2e_db, watch_dir, tmp_path):
        """E2E: drop CSV → connector → staging → mapping engine → metric store."""
        incoming, processed = watch_dir

        # Write a CSV with metrics for the registered entity
        _write_csv(incoming / "model_metrics.csv", [
            {"source_entity_ref": "mlflow://experiment-1/e2e-model", "metric_name": "accuracy",
             "metric_value": "0.934", "timestamp": "2026-07-30T14:00:00Z"},
            {"source_entity_ref": "mlflow://experiment-1/e2e-model", "metric_name": "precision",
             "metric_value": "0.91", "timestamp": "2026-07-30T14:00:00Z"},
            {"source_entity_ref": "mlflow://experiment-1/e2e-model", "metric_name": "recall",
             "metric_value": "0.89", "timestamp": "2026-07-30T15:00:00Z"},
        ], ["source_entity_ref", "metric_name", "metric_value", "timestamp"])

        # Step 1: Connector polls and produces CTEs
        config = {
            "id": "e2e-file-drop",
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
        connector = FileDropConnector(config)
        ctes = connector.poll()
        assert len(ctes) == 3

        # Step 2: Insert CTEs into staging
        inserted = insert_ctes(e2e_db, ctes)
        assert inserted == 3

        # Step 3: Create mapping YAML for this connector
        mappings_dir = tmp_path / "mappings"
        mappings_dir.mkdir()
        (mappings_dir / "e2e_metrics.yaml").write_text("""
version: "1"
applies_to:
  source_connector: e2e-file-drop
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

        # Step 4: Run mapping engine
        engine = MappingEngine(e2e_db, mappings_dir)
        result = engine.process_batch()
        assert result["processed"] == 3
        assert result["mapped"] == 3

        # Step 5: Verify metric store
        rows = e2e_db.execute(
            "SELECT * FROM metric_timeseries WHERE entity_id = 'model-e2e-001' ORDER BY metric_name"
        ).fetchall()
        assert len(rows) == 3
        names = [r["metric_name"] for r in rows]
        assert "accuracy" in names
        assert "precision" in names
        assert "recall" in names

        # Step 6: File was moved
        assert not (incoming / "model_metrics.csv").exists()
        assert (processed / "model_metrics.csv").exists()

    def test_unknown_entity_rejected_in_pipeline(self, e2e_db, watch_dir, tmp_path):
        """Files with unknown entity refs result in rejected CTEs."""
        incoming, processed = watch_dir

        _write_csv(incoming / "unknown.csv", [
            {"source_entity_ref": "mlflow://unknown/model", "metric_name": "accuracy",
             "metric_value": "0.8", "timestamp": "2026-07-30T14:00:00Z"},
        ], ["source_entity_ref", "metric_name", "metric_value", "timestamp"])

        config = {
            "id": "e2e-file-drop",
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
        connector = FileDropConnector(config)
        ctes = connector.poll()
        insert_ctes(e2e_db, ctes)

        mappings_dir = tmp_path / "mappings"
        mappings_dir.mkdir()
        (mappings_dir / "metrics.yaml").write_text("""
version: "1"
applies_to:
  source_connector: e2e-file-drop
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
target_table: metric_timeseries
""", encoding="utf-8")

        engine = MappingEngine(e2e_db, mappings_dir)
        result = engine.process_batch()
        assert result["rejected"] == 1

        row = e2e_db.execute(
            "SELECT processing_status, rejection_reason FROM staging_events"
        ).fetchone()
        assert row["processing_status"] == "rejected"
        assert "not found" in row["rejection_reason"].lower()

    def test_connector_health_tracked(self, e2e_db, connector):
        """Connector health updates after poll."""
        connector.update_health(e2e_db, success=True)
        row = e2e_db.execute(
            "SELECT state FROM connector_health WHERE connector_id = ?",
            (connector.connector_id(),)
        ).fetchone()
        assert row["state"] == "healthy"
