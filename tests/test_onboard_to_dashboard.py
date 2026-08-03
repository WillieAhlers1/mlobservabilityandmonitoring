"""Tests for Session 9: Onboard-to-Live Pipeline Integration."""

import csv
import json
import os
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from ingestion.completeness import compute_completeness, has_any_telemetry
from ingestion.connectors.file_drop import FileDropConnector
from ingestion.mapping_engine import MappingEngine
from ingestion.staging import insert_ctes


# ── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def e2e_client(tmp_path):
    """Flask test client with full schema, ready for onboard → dashboard flow."""
    db_path = str(tmp_path / "e2e.db")
    import app as app_module
    import data_source as ds_module
    orig_app_db = app_module.DB_PATH
    orig_ds_db = ds_module.DB_PATH
    orig_source = ds_module.DATA_SOURCE
    app_module.DB_PATH = db_path
    ds_module.DB_PATH = db_path
    ds_module.DATA_SOURCE = "live"
    app_module.init_db()
    app_module.app.config["TESTING"] = True
    with app_module.app.test_client() as client:
        with app_module.app.app_context():
            yield client, db_path, tmp_path
    app_module.DB_PATH = orig_app_db
    ds_module.DB_PATH = orig_ds_db
    ds_module.DATA_SOURCE = orig_source


def _write_csv(filepath, rows, fieldnames):
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


# ── Test: Onboard with Source Reference ─────────────────────────────────────

class TestOnboardSourceRef:

    def test_model_onboard_creates_source_ref_alias(self, e2e_client):
        """Onboarding with source_ref creates the alias for connector matching."""
        client, db_path, tmp_path = e2e_client
        r = client.post("/onboard", data={
            "entity_type": "model",
            "model_name": "Pipeline Model",
            "project_id": "proj-hls-1",
            "model_type": "classification",
            "version": "v1.0.0",
            "endpoint": "/api/predict",
            "owner": "Team",
            "perf_threshold": "0.85",
            "drift_threshold": "0.1",
            "source_ref": "mlflow://experiment-9/pipeline-model",
        }, follow_redirects=True)
        assert r.status_code == 200

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM entity_aliases WHERE alias_type='source_ref' AND alias_value=?",
            ("mlflow://experiment-9/pipeline-model",)
        ).fetchone()
        conn.close()
        assert row is not None

    def test_agent_onboard_creates_source_ref_alias(self, e2e_client):
        """Agent onboarding with source_ref creates the alias."""
        client, db_path, tmp_path = e2e_client
        r = client.post("/onboard", data={
            "entity_type": "agent",
            "agent_name": "Pipeline Agent",
            "project_id": "proj-hls-1",
            "framework": "LangChain",
            "llm_backbone": "GPT-4",
            "version": "v1.0.0",
            "endpoint": "",
            "owner": "Team",
            "task_completion_threshold": "0.90",
            "groundedness_threshold": "0.85",
            "safety_threshold": "0.95",
            "cost_budget": "0.10",
            "latency_sla": "3000",
            "retention_days": "365",
            "source_ref": "agent://pipeline-agent",
        }, follow_redirects=True)
        assert r.status_code == 200

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM entity_aliases WHERE alias_type='source_ref' AND alias_value=?",
            ("agent://pipeline-agent",)
        ).fetchone()
        conn.close()
        assert row is not None

    def test_onboard_without_source_ref_no_alias(self, e2e_client):
        """No source_ref field → no source_ref alias created."""
        client, db_path, tmp_path = e2e_client
        client.post("/onboard", data={
            "entity_type": "model",
            "model_name": "No Source Model",
            "project_id": "proj-hls-1",
            "model_type": "classification",
            "version": "v1.0.0",
            "endpoint": "",
            "owner": "Team",
            "perf_threshold": "0.85",
            "drift_threshold": "0.1",
        }, follow_redirects=True)

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM entity_aliases WHERE alias_type='source_ref'"
        ).fetchall()
        conn.close()
        assert len(rows) == 0


# ── Test: Connector Matches Onboarded Entity ────────────────────────────────

class TestConnectorMatchesOnboarded:

    def test_cte_resolves_to_onboarded_entity(self, e2e_client):
        """CTE with source_ref matching onboarded entity resolves correctly."""
        client, db_path, tmp_path = e2e_client

        # Onboard with source_ref
        client.post("/onboard", data={
            "entity_type": "model",
            "model_name": "Resolvable Model",
            "project_id": "proj-hls-1",
            "model_type": "classification",
            "version": "v1.0.0",
            "endpoint": "",
            "owner": "Team",
            "perf_threshold": "0.85",
            "drift_threshold": "0.1",
            "source_ref": "mlflow://exp-resolve/model-x",
        }, follow_redirects=True)

        # Verify entity resolution works
        from ingestion.entity_resolution import resolve_entity
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        entity_id = resolve_entity(conn, "mlflow://exp-resolve/model-x")
        conn.close()
        assert entity_id is not None
        assert entity_id.startswith("model-")


# ── Test: Dashboard Graceful Degradation ────────────────────────────────────

class TestDashboardGracefulDegradation:

    def test_no_metrics_returns_empty_structure(self, e2e_client):
        """Live mode with onboarded entity but no data returns empty metrics."""
        client, db_path, tmp_path = e2e_client
        import data_source as ds

        # Onboard entity
        client.post("/onboard", data={
            "entity_type": "model",
            "model_name": "Empty Model",
            "project_id": "proj-hls-1",
            "model_type": "classification",
            "version": "v1.0.0",
            "endpoint": "",
            "owner": "Team",
            "perf_threshold": "0.85",
            "drift_threshold": "0.1",
        }, follow_redirects=True)

        # Get entity_id
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT entity_id FROM entity_registry WHERE name='Empty Model'").fetchone()
        entity_id = row["entity_id"]
        conn.close()

        # Query metrics — should return empty structure, not None
        result = ds.get_model_metrics(entity_id)
        assert result is not None
        assert result["dates"] == []
        assert result["metrics"] == {}

    def test_partial_metrics_returns_available(self, e2e_client):
        """Only some metrics present → returns what's available."""
        client, db_path, tmp_path = e2e_client
        import data_source as ds

        # Onboard entity
        client.post("/onboard", data={
            "entity_type": "model",
            "model_name": "Partial Model",
            "project_id": "proj-hls-1",
            "model_type": "classification",
            "version": "v1.0.0",
            "endpoint": "",
            "owner": "Team",
            "perf_threshold": "0.85",
            "drift_threshold": "0.1",
        }, follow_redirects=True)

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT entity_id FROM entity_registry WHERE name='Partial Model'").fetchone()
        entity_id = row["entity_id"]

        # Insert only accuracy metric
        conn.execute(
            "INSERT INTO metric_timeseries (entity_id, metric_name, timestamp, value) VALUES (?,?,?,?)",
            (entity_id, "accuracy", "2026-07-30T14:00:00Z", 0.92),
        )
        conn.commit()
        conn.close()

        result = ds.get_model_metrics(entity_id)
        assert result is not None
        assert "accuracy" in result["metrics"]
        assert result["metrics"]["accuracy"]["current"] == 0.92


# ── Test: Completeness Score ────────────────────────────────────────────────

class TestCompletenessScore:

    def test_no_metrics_score_zero(self, e2e_client):
        """Entity with no metrics → score = 0, status = none."""
        client, db_path, tmp_path = e2e_client

        client.post("/onboard", data={
            "entity_type": "model",
            "model_name": "Zero Score",
            "project_id": "proj-hls-1",
            "model_type": "classification",
            "version": "v1.0.0",
            "endpoint": "",
            "owner": "Team",
            "perf_threshold": "0.85",
            "drift_threshold": "0.1",
        }, follow_redirects=True)

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT entity_id FROM entity_registry WHERE name='Zero Score'").fetchone()
        entity_id = row["entity_id"]

        result = compute_completeness(conn, entity_id, "model", "classification")
        conn.close()
        assert result["score"] == 0.0
        assert result["status"] == "none"
        assert len(result["missing"]) == 5

    def test_partial_metrics_score(self, e2e_client):
        """3 of 5 expected metrics → score = 0.6, status = partial."""
        client, db_path, tmp_path = e2e_client

        client.post("/onboard", data={
            "entity_type": "model",
            "model_name": "Partial Score",
            "project_id": "proj-hls-1",
            "model_type": "classification",
            "version": "v1.0.0",
            "endpoint": "",
            "owner": "Team",
            "perf_threshold": "0.85",
            "drift_threshold": "0.1",
        }, follow_redirects=True)

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT entity_id FROM entity_registry WHERE name='Partial Score'").fetchone()
        entity_id = row["entity_id"]

        # Insert 3 metrics
        for metric in ["accuracy", "precision", "recall"]:
            conn.execute(
                "INSERT INTO metric_timeseries (entity_id, metric_name, timestamp, value) VALUES (?,?,?,?)",
                (entity_id, metric, "2026-07-30T14:00:00Z", 0.9),
            )
        conn.commit()

        result = compute_completeness(conn, entity_id, "model", "classification")
        conn.close()
        assert result["score"] == 0.6
        assert result["status"] == "partial"
        assert "accuracy" in result["present"]
        assert "f1_score" in result["missing"]

    def test_full_metrics_score(self, e2e_client):
        """All 5 expected metrics → score = 1.0, status = complete."""
        client, db_path, tmp_path = e2e_client

        client.post("/onboard", data={
            "entity_type": "model",
            "model_name": "Full Score",
            "project_id": "proj-hls-1",
            "model_type": "classification",
            "version": "v1.0.0",
            "endpoint": "",
            "owner": "Team",
            "perf_threshold": "0.85",
            "drift_threshold": "0.1",
        }, follow_redirects=True)

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT entity_id FROM entity_registry WHERE name='Full Score'").fetchone()
        entity_id = row["entity_id"]

        for metric in ["accuracy", "precision", "recall", "f1_score", "auc_roc"]:
            conn.execute(
                "INSERT INTO metric_timeseries (entity_id, metric_name, timestamp, value) VALUES (?,?,?,?)",
                (entity_id, metric, "2026-07-30T14:00:00Z", 0.9),
            )
        conn.commit()

        result = compute_completeness(conn, entity_id, "model", "classification")
        conn.close()
        assert result["score"] == 1.0
        assert result["status"] == "complete"

    def test_has_any_telemetry_false(self, e2e_client):
        """New entity with no data → False."""
        client, db_path, tmp_path = e2e_client

        client.post("/onboard", data={
            "entity_type": "model",
            "model_name": "No Telemetry",
            "project_id": "proj-hls-1",
            "model_type": "classification",
            "version": "v1.0.0",
            "endpoint": "",
            "owner": "Team",
            "perf_threshold": "0.85",
            "drift_threshold": "0.1",
        }, follow_redirects=True)

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT entity_id FROM entity_registry WHERE name='No Telemetry'").fetchone()
        entity_id = row["entity_id"]

        assert has_any_telemetry(conn, entity_id) is False
        conn.close()

    def test_has_any_telemetry_true(self, e2e_client):
        """Entity with one metric row → True."""
        client, db_path, tmp_path = e2e_client

        client.post("/onboard", data={
            "entity_type": "model",
            "model_name": "Has Telemetry",
            "project_id": "proj-hls-1",
            "model_type": "classification",
            "version": "v1.0.0",
            "endpoint": "",
            "owner": "Team",
            "perf_threshold": "0.85",
            "drift_threshold": "0.1",
        }, follow_redirects=True)

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT entity_id FROM entity_registry WHERE name='Has Telemetry'").fetchone()
        entity_id = row["entity_id"]
        conn.execute(
            "INSERT INTO metric_timeseries (entity_id, metric_name, timestamp, value) VALUES (?,?,?,?)",
            (entity_id, "accuracy", "2026-07-30T14:00:00Z", 0.9),
        )
        conn.commit()

        assert has_any_telemetry(conn, entity_id) is True
        conn.close()


# ── Test: End-to-End Onboard → File Drop → Dashboard ───────────────────────

class TestEndToEndOnboardToDashboard:

    def test_full_pipeline(self, e2e_client):
        """Onboard entity → drop CSV → process → dashboard returns data."""
        client, db_path, tmp_path = e2e_client
        import data_source as ds

        # Step 1: Onboard a model with source_ref
        client.post("/onboard", data={
            "entity_type": "model",
            "model_name": "E2E Pipeline Model",
            "project_id": "proj-hls-1",
            "model_type": "classification",
            "version": "v1.0.0",
            "endpoint": "/api/predict/e2e",
            "owner": "E2E Team",
            "perf_threshold": "0.85",
            "drift_threshold": "0.1",
            "source_ref": "mlflow://experiment-e2e/pipeline-model",
        }, follow_redirects=True)

        # Get the entity_id
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT entity_id FROM entity_registry WHERE name='E2E Pipeline Model'").fetchone()
        entity_id = row["entity_id"]
        conn.close()

        # Step 2: Drop a CSV file for this entity
        incoming = tmp_path / "incoming"
        incoming.mkdir()
        processed = tmp_path / "processed"
        processed.mkdir()

        _write_csv(incoming / "model_metrics.csv", [
            {"source_entity_ref": "mlflow://experiment-e2e/pipeline-model", "metric_name": "accuracy",
             "metric_value": "0.93", "timestamp": "2026-07-30T10:00:00Z"},
            {"source_entity_ref": "mlflow://experiment-e2e/pipeline-model", "metric_name": "precision",
             "metric_value": "0.91", "timestamp": "2026-07-30T10:00:00Z"},
            {"source_entity_ref": "mlflow://experiment-e2e/pipeline-model", "metric_name": "recall",
             "metric_value": "0.89", "timestamp": "2026-07-30T11:00:00Z"},
            {"source_entity_ref": "mlflow://experiment-e2e/pipeline-model", "metric_name": "accuracy",
             "metric_value": "0.94", "timestamp": "2026-07-30T12:00:00Z"},
        ], ["source_entity_ref", "metric_name", "metric_value", "timestamp"])

        # Step 3: Run the file drop connector
        connector = FileDropConnector({
            "id": "e2e-connector",
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
        })
        ctes = connector.poll()
        assert len(ctes) == 4

        # Step 4: Insert into staging and run mapping engine
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        inserted = insert_ctes(conn, ctes)
        assert inserted == 4

        # Create mapping definition
        mappings_dir = tmp_path / "mappings"
        mappings_dir.mkdir()
        (mappings_dir / "e2e.yaml").write_text("""
version: "1"
applies_to:
  source_connector: e2e-connector
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

        engine = MappingEngine(conn, mappings_dir)
        result = engine.process_batch()
        assert result["mapped"] == 4
        conn.close()

        # Step 5: Query dashboard — should return real metrics
        metrics = ds.get_model_metrics(entity_id)
        assert metrics is not None
        assert "accuracy" in metrics["metrics"]
        assert "precision" in metrics["metrics"]
        assert "recall" in metrics["metrics"]
        assert len(metrics["metrics"]["accuracy"]["values"]) == 2  # two accuracy points
        assert metrics["metrics"]["accuracy"]["current"] == 0.94

    def test_no_regressions_in_mock_mode(self, tmp_path):
        """Mock mode still works correctly alongside live pipeline."""
        db_path = str(tmp_path / "mock_test.db")
        import app as app_module
        import data_source as ds_module
        orig_app_db = app_module.DB_PATH
        orig_ds_db = ds_module.DB_PATH
        orig_source = ds_module.DATA_SOURCE
        app_module.DB_PATH = db_path
        ds_module.DB_PATH = db_path
        ds_module.DATA_SOURCE = "mock"
        app_module.init_db()
        app_module.app.config["TESTING"] = True

        try:
            with app_module.app.test_client() as client:
                with app_module.app.app_context():
                    r = client.get("/")
                    assert r.status_code == 200
                    r = client.get("/dashboard/model-1")
                    assert r.status_code == 200
                    r = client.get("/onboard")
                    assert r.status_code == 200

            # Mock data still returns full metrics
            result = ds_module.get_model_metrics("model-1")
            assert result is not None
            assert "accuracy" in result["metrics"]
        finally:
            app_module.DB_PATH = orig_app_db
            ds_module.DB_PATH = orig_ds_db
            ds_module.DATA_SOURCE = orig_source
