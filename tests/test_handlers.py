"""Tests for ingestion handler modules (Session 10).

Tests each handler for correct CTE → table routing and data integrity.
"""

import json
import os
import sqlite3
import sys
import uuid
from datetime import datetime, timezone

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from ingestion.handlers.drift import DriftHandler
from ingestion.handlers.alerts import AlertsHandler
from ingestion.handlers.cohorts import CohortsHandler
from ingestion.handlers.features import FeaturesHandler
from ingestion.handlers.data_quality import DataQualityHandler
from ingestion.handlers.lifecycle import LifecycleHandler
from ingestion.handlers.traces import TracesHandler
from ingestion.handlers import HANDLER_REGISTRY
from ingestion.models import CanonicalTelemetryEvent
from ingestion.staging import compute_event_id


@pytest.fixture
def handler_db(tmp_db):
    """DB connection with a registered entity for handler tests."""
    conn = sqlite3.connect(tmp_db)
    conn.row_factory = sqlite3.Row
    # Create a project and entity
    conn.execute(
        "INSERT INTO projects (id, name, description, owner, team, created_date, status) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("proj-1", "Test Project", "Desc", "owner", "team", "2026-01-01", "Active"),
    )
    conn.execute(
        "INSERT INTO entity_registry (entity_id, entity_type, industry_id, project_id, name, status, metadata, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("model-abc123", "model", "retail", "proj-1", "Test Model", "Healthy",
         json.dumps({"model_type": "classification"}),
         "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z"),
    )
    conn.execute(
        "INSERT INTO entity_registry (entity_id, entity_type, industry_id, project_id, name, status, metadata, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("agent-xyz789", "agent", "retail", "proj-1", "Test Agent", "Operational",
         json.dumps({"framework": "langchain"}),
         "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z"),
    )
    conn.execute(
        "INSERT INTO entity_aliases (entity_id, alias_type, alias_value) VALUES (?, ?, ?)",
        ("model-abc123", "source_ref", "file_drop://model_metrics/Test Model"),
    )
    conn.execute(
        "INSERT INTO entity_aliases (entity_id, alias_type, alias_value) VALUES (?, ?, ?)",
        ("agent-xyz789", "source_ref", "file_drop://agent_traces/Test Agent"),
    )
    conn.commit()
    yield conn
    conn.close()


def _make_cte(event_type, payload, entity_ref="file_drop://model_metrics/Test Model",
              timestamp="2026-07-15T10:00:00Z"):
    """Helper to create a CTE for testing."""
    event_id = compute_event_id("file_drop", entity_ref, event_type, timestamp)
    return CanonicalTelemetryEvent(
        event_id=event_id,
        source_connector="file_drop",
        source_entity_ref=entity_ref,
        event_type=event_type,
        timestamp=timestamp,
        received_at="2026-07-15T10:01:00Z",
        mapping_version="1",
        payload=payload,
    )


# ═══════════════════════════════════════════════════════════════════════════
# HANDLER REGISTRY TESTS
# ═══════════════════════════════════════════════════════════════════════════

class TestHandlerRegistry:
    """Test the handler registry configuration."""

    def test_all_event_types_registered(self):
        expected = {"drift", "alert", "cohort", "feature_importance", "data_quality", "lifecycle", "trace"}
        assert expected == set(HANDLER_REGISTRY.keys())

    def test_each_handler_has_target_table(self):
        for event_type, handler_cls in HANDLER_REGISTRY.items():
            assert hasattr(handler_cls, "target_table")
            assert handler_cls.target_table is not None

    def test_each_handler_has_write_method(self):
        for event_type, handler_cls in HANDLER_REGISTRY.items():
            handler = handler_cls()
            assert callable(getattr(handler, "write", None))


# ═══════════════════════════════════════════════════════════════════════════
# DRIFT HANDLER TESTS
# ═══════════════════════════════════════════════════════════════════════════

class TestDriftHandler:
    """Test DriftHandler writes to drift_snapshots."""

    def test_basic_drift_write(self, handler_db):
        cte = _make_cte("drift", {
            "drift_type": "psi",
            "scope": "overall",
            "value": 0.15,
            "status": "Warning",
        })
        DriftHandler().write(handler_db, cte, "model-abc123", 0.15, None)

        row = handler_db.execute("SELECT * FROM drift_snapshots WHERE entity_id = ?",
                                 ("model-abc123",)).fetchone()
        assert row is not None
        assert row["drift_type"] == "psi"
        assert row["scope"] == "overall"
        assert row["value"] == 0.15
        assert row["status"] == "Warning"
        assert row["timestamp"] == "2026-07-15T10:00:00Z"

    def test_drift_auto_status_critical(self, handler_db):
        """Status derived from value when not explicitly provided."""
        cte = _make_cte("drift", {
            "drift_type": "psi",
            "scope": "overall",
            "value": 0.25,
        })
        DriftHandler().write(handler_db, cte, "model-abc123", 0.25, None)

        row = handler_db.execute("SELECT status FROM drift_snapshots").fetchone()
        assert row["status"] == "Critical"

    def test_drift_auto_status_normal(self, handler_db):
        cte = _make_cte("drift", {
            "drift_type": "psi",
            "scope": "overall",
            "value": 0.05,
        })
        DriftHandler().write(handler_db, cte, "model-abc123", 0.05, None)

        row = handler_db.execute("SELECT status FROM drift_snapshots").fetchone()
        assert row["status"] == "Normal"

    def test_drift_feature_scope(self, handler_db):
        cte = _make_cte("drift", {
            "drift_type": "ks",
            "scope": "feature:age",
            "value": 0.12,
            "status": "Warning",
        })
        DriftHandler().write(handler_db, cte, "model-abc123", 0.12, None)

        row = handler_db.execute("SELECT * FROM drift_snapshots WHERE scope = 'feature:age'").fetchone()
        assert row is not None
        assert row["drift_type"] == "ks"

    def test_drift_multiple_writes(self, handler_db):
        for i in range(5):
            cte = _make_cte("drift", {
                "drift_type": "psi",
                "scope": "overall",
                "value": 0.05 * (i + 1),
                "status": "Normal",
            }, timestamp=f"2026-07-{15+i:02d}T10:00:00Z")
            DriftHandler().write(handler_db, cte, "model-abc123", 0.05 * (i + 1), None)

        count = handler_db.execute("SELECT COUNT(*) as cnt FROM drift_snapshots").fetchone()["cnt"]
        assert count == 5


# ═══════════════════════════════════════════════════════════════════════════
# ALERTS HANDLER TESTS
# ═══════════════════════════════════════════════════════════════════════════

class TestAlertsHandler:
    """Test AlertsHandler writes to alerts table."""

    def test_basic_alert_write(self, handler_db):
        cte = _make_cte("alert", {
            "severity": "critical",
            "alert_type": "drift_threshold",
            "title": "PSI exceeded threshold",
            "description": "Model drift PSI=0.32 exceeds threshold of 0.2",
        })
        AlertsHandler().write(handler_db, cte, "model-abc123", None, None)

        row = handler_db.execute("SELECT * FROM alerts WHERE entity_id = ?",
                                 ("model-abc123",)).fetchone()
        assert row is not None
        assert row["severity"] == "critical"
        assert row["alert_type"] == "drift_threshold"
        assert row["title"] == "PSI exceeded threshold"
        assert row["description"] == "Model drift PSI=0.32 exceeds threshold of 0.2"
        assert row["resolved"] == 0

    def test_alert_all_severities(self, handler_db):
        severities = ["critical", "high", "medium", "low", "warning", "info"]
        for i, sev in enumerate(severities):
            cte = _make_cte("alert", {
                "severity": sev,
                "alert_type": "test",
                "title": f"Alert {sev}",
            }, timestamp=f"2026-07-15T10:{i:02d}:00Z")
            AlertsHandler().write(handler_db, cte, "model-abc123", None, None)

        count = handler_db.execute("SELECT COUNT(*) as cnt FROM alerts").fetchone()["cnt"]
        assert count == 6

    def test_alert_resolved(self, handler_db):
        cte = _make_cte("alert", {
            "severity": "medium",
            "alert_type": "latency",
            "title": "Resolved alert",
            "resolved": True,
            "resolved_at": "2026-07-15T12:00:00Z",
        })
        AlertsHandler().write(handler_db, cte, "model-abc123", None, None)

        row = handler_db.execute("SELECT * FROM alerts").fetchone()
        assert row["resolved"] == 1
        assert row["resolved_at"] == "2026-07-15T12:00:00Z"

    def test_alert_defaults(self, handler_db):
        """Test default values for missing optional fields."""
        cte = _make_cte("alert", {
            "severity": "low",
            "alert_type": "generic",
            "title": "Minimal alert",
        })
        AlertsHandler().write(handler_db, cte, "model-abc123", None, None)

        row = handler_db.execute("SELECT * FROM alerts").fetchone()
        assert row["description"] == ""
        assert row["resolved"] == 0
        assert row["resolved_at"] is None


# ═══════════════════════════════════════════════════════════════════════════
# COHORTS HANDLER TESTS
# ═══════════════════════════════════════════════════════════════════════════

class TestCohortsHandler:
    """Test CohortsHandler writes to cohort_metrics table."""

    def test_single_cohort_metric(self, handler_db):
        cte = _make_cte("cohort", {
            "cohort_name": "age_18_25",
            "cohort_dim": "age_group",
            "metric_name": "accuracy",
            "value": 0.92,
            "sample_size": 1500,
        })
        CohortsHandler().write(handler_db, cte, "model-abc123", 0.92, None)

        row = handler_db.execute("SELECT * FROM cohort_metrics").fetchone()
        assert row is not None
        assert row["cohort_name"] == "age_18_25"
        assert row["cohort_dim"] == "age_group"
        assert row["metric_name"] == "accuracy"
        assert row["value"] == 0.92
        assert row["sample_size"] == 1500

    def test_batch_cohort_metrics(self, handler_db):
        cte = _make_cte("cohort", {
            "cohorts": [
                {
                    "cohort_name": "male",
                    "cohort_dim": "gender",
                    "metrics": {"accuracy": 0.91, "precision": 0.88},
                    "sample_size": 2000,
                },
                {
                    "cohort_name": "female",
                    "cohort_dim": "gender",
                    "metrics": {"accuracy": 0.93, "precision": 0.90},
                    "sample_size": 1800,
                },
            ]
        })
        CohortsHandler().write(handler_db, cte, "model-abc123", None, None)

        rows = handler_db.execute("SELECT * FROM cohort_metrics ORDER BY cohort_name, metric_name").fetchall()
        assert len(rows) == 4  # 2 cohorts × 2 metrics

        # Check female accuracy
        female_acc = next(r for r in rows if r["cohort_name"] == "female" and r["metric_name"] == "accuracy")
        assert female_acc["value"] == 0.93
        assert female_acc["sample_size"] == 1800

    def test_cohort_defaults(self, handler_db):
        """Test defaults for minimal payload."""
        cte = _make_cte("cohort", {
            "value": 0.85,
        })
        CohortsHandler().write(handler_db, cte, "model-abc123", 0.85, None)

        row = handler_db.execute("SELECT * FROM cohort_metrics").fetchone()
        assert row["cohort_name"] == "unknown"
        assert row["cohort_dim"] == "segment"
        assert row["metric_name"] == "unknown"


# ═══════════════════════════════════════════════════════════════════════════
# FEATURES HANDLER TESTS
# ═══════════════════════════════════════════════════════════════════════════

class TestFeaturesHandler:
    """Test FeaturesHandler writes to feature_importance table."""

    def test_single_feature(self, handler_db):
        cte = _make_cte("feature_importance", {
            "feature": "income",
            "importance": 0.35,
            "method": "shap",
        })
        FeaturesHandler().write(handler_db, cte, "model-abc123", 0.35, None)

        row = handler_db.execute("SELECT * FROM feature_importance").fetchone()
        assert row is not None
        assert row["feature"] == "income"
        assert row["importance"] == 0.35
        assert row["method"] == "shap"

    def test_batch_features(self, handler_db):
        cte = _make_cte("feature_importance", {
            "features": [
                {"feature": "income", "importance": 0.35},
                {"feature": "age", "importance": 0.25},
                {"feature": "tenure", "importance": 0.20},
                {"feature": "region", "importance": 0.12},
                {"feature": "product", "importance": 0.08},
            ],
            "method": "permutation",
        })
        FeaturesHandler().write(handler_db, cte, "model-abc123", None, None)

        rows = handler_db.execute("SELECT * FROM feature_importance ORDER BY importance DESC").fetchall()
        assert len(rows) == 5
        assert rows[0]["feature"] == "income"
        assert rows[0]["importance"] == 0.35
        assert rows[0]["method"] == "permutation"

    def test_feature_default_method(self, handler_db):
        cte = _make_cte("feature_importance", {
            "feature": "age",
            "importance": 0.20,
        })
        FeaturesHandler().write(handler_db, cte, "model-abc123", 0.20, None)

        row = handler_db.execute("SELECT * FROM feature_importance").fetchone()
        assert row["method"] == "shap"


# ═══════════════════════════════════════════════════════════════════════════
# DATA QUALITY HANDLER TESTS
# ═══════════════════════════════════════════════════════════════════════════

class TestDataQualityHandler:
    """Test DataQualityHandler writes to data_quality table."""

    def test_single_feature_quality(self, handler_db):
        cte = _make_cte("data_quality", {
            "feature": "income",
            "missing_rate": 0.02,
            "outlier_rate": 0.01,
            "schema_valid": True,
            "row_count": 10000,
        })
        DataQualityHandler().write(handler_db, cte, "model-abc123", None, None)

        row = handler_db.execute("SELECT * FROM data_quality").fetchone()
        assert row is not None
        assert row["feature"] == "income"
        assert row["missing_rate"] == 0.02
        assert row["outlier_rate"] == 0.01
        assert row["schema_valid"] == 1
        assert row["row_count"] == 10000

    def test_batch_data_quality(self, handler_db):
        cte = _make_cte("data_quality", {
            "features": [
                {"feature": "income", "missing_rate": 0.02, "outlier_rate": 0.01, "schema_valid": True, "row_count": 10000},
                {"feature": "age", "missing_rate": 0.05, "outlier_rate": 0.03, "schema_valid": True, "row_count": 10000},
                {"feature": "region", "missing_rate": 0.0, "outlier_rate": 0.0, "schema_valid": False, "row_count": 10000},
            ]
        })
        DataQualityHandler().write(handler_db, cte, "model-abc123", None, None)

        rows = handler_db.execute("SELECT * FROM data_quality ORDER BY feature").fetchall()
        assert len(rows) == 3
        assert rows[0]["feature"] == "age"
        assert rows[0]["missing_rate"] == 0.05
        # schema_valid False → 0
        region = next(r for r in rows if r["feature"] == "region")
        assert region["schema_valid"] == 0

    def test_data_quality_nullable_fields(self, handler_db):
        cte = _make_cte("data_quality", {
            "feature": "sparse_col",
            "missing_rate": None,
            "outlier_rate": None,
            "schema_valid": True,
        })
        DataQualityHandler().write(handler_db, cte, "model-abc123", None, None)

        row = handler_db.execute("SELECT * FROM data_quality").fetchone()
        assert row["missing_rate"] is None
        assert row["outlier_rate"] is None
        assert row["row_count"] is None


# ═══════════════════════════════════════════════════════════════════════════
# LIFECYCLE HANDLER TESTS
# ═══════════════════════════════════════════════════════════════════════════

class TestLifecycleHandler:
    """Test LifecycleHandler writes to lineage_events table."""

    def test_basic_lifecycle(self, handler_db):
        cte = _make_cte("lifecycle", {
            "lifecycle_type": "deployment",
            "version": "v2.1",
            "trigger": "scheduled_retrain",
            "status": "champion",
            "training_records": 50000,
        })
        LifecycleHandler().write(handler_db, cte, "model-abc123", None, None)

        row = handler_db.execute("SELECT * FROM lineage_events").fetchone()
        assert row is not None
        assert row["event_type"] == "deployment"
        assert row["version"] == "v2.1"
        assert row["trigger"] == "scheduled_retrain"
        # Metadata should contain extra fields
        meta = json.loads(row["metadata"])
        assert meta["status"] == "champion"
        assert meta["training_records"] == 50000

    def test_lifecycle_retirement(self, handler_db):
        cte = _make_cte("lifecycle", {
            "lifecycle_type": "retirement",
            "version": "v1.0",
            "trigger": "performance_degradation",
            "retired_date": "2026-07-15",
            "performance_at_retire": 0.72,
        })
        LifecycleHandler().write(handler_db, cte, "model-abc123", None, None)

        row = handler_db.execute("SELECT * FROM lineage_events").fetchone()
        assert row["event_type"] == "retirement"
        meta = json.loads(row["metadata"])
        assert meta["retired_date"] == "2026-07-15"
        assert meta["performance_at_retire"] == 0.72

    def test_lifecycle_minimal(self, handler_db):
        """Minimal lifecycle event with only event_type."""
        cte = _make_cte("lifecycle", {
            "event_type": "promotion",
        })
        LifecycleHandler().write(handler_db, cte, "model-abc123", None, None)

        row = handler_db.execute("SELECT * FROM lineage_events").fetchone()
        assert row["event_type"] == "promotion"
        assert row["version"] is None
        assert row["trigger"] is None

    def test_lifecycle_multiple_versions(self, handler_db):
        versions = ["v1.0", "v1.1", "v2.0", "v2.1"]
        for i, v in enumerate(versions):
            cte = _make_cte("lifecycle", {
                "lifecycle_type": "deployment",
                "version": v,
                "trigger": "manual",
            }, timestamp=f"2026-0{i+1}-01T00:00:00Z")
            LifecycleHandler().write(handler_db, cte, "model-abc123", None, None)

        count = handler_db.execute("SELECT COUNT(*) as cnt FROM lineage_events").fetchone()["cnt"]
        assert count == 4


# ═══════════════════════════════════════════════════════════════════════════
# TRACES HANDLER TESTS
# ═══════════════════════════════════════════════════════════════════════════

class TestTracesHandler:
    """Test TracesHandler writes to agent_traces + agent_trace_steps tables."""

    def test_basic_trace_write(self, handler_db):
        cte = _make_cte("trace", {
            "trace_id": "trace-001",
            "query": "What is the refund policy?",
            "response": "The refund policy allows returns within 30 days.",
            "total_latency": 1200,
            "token_count": 450,
            "voice_score": 0.88,
            "policy_pass": True,
            "policy_note": None,
            "steps": [
                {"tool": "search", "action": "query_kb", "latency_ms": 200, "status": "ok"},
                {"tool": "llm", "action": "generate", "latency_ms": 800, "status": "ok"},
            ],
        }, entity_ref="file_drop://agent_traces/Test Agent")
        TracesHandler().write(handler_db, cte, "agent-xyz789", None, None)

        # Check trace record
        trace = handler_db.execute("SELECT * FROM agent_traces WHERE trace_id = ?",
                                   ("trace-001",)).fetchone()
        assert trace is not None
        assert trace["entity_id"] == "agent-xyz789"
        assert trace["query"] == "What is the refund policy?"
        assert trace["total_latency"] == 1200
        assert trace["token_count"] == 450
        assert trace["voice_score"] == 0.88
        assert trace["policy_pass"] == 1

        # Check steps
        steps = handler_db.execute(
            "SELECT * FROM agent_trace_steps WHERE trace_id = ? ORDER BY step_order",
            ("trace-001",),
        ).fetchall()
        assert len(steps) == 2
        assert steps[0]["tool"] == "search"
        assert steps[0]["step_order"] == 1
        assert steps[0]["latency_ms"] == 200
        assert steps[1]["tool"] == "llm"
        assert steps[1]["step_order"] == 2

    def test_trace_no_steps(self, handler_db):
        cte = _make_cte("trace", {
            "trace_id": "trace-002",
            "query": "Hello",
            "response": "Hi there!",
            "total_latency": 100,
            "steps": [],
        }, entity_ref="file_drop://agent_traces/Test Agent")
        TracesHandler().write(handler_db, cte, "agent-xyz789", None, None)

        trace = handler_db.execute("SELECT * FROM agent_traces WHERE trace_id = ?",
                                   ("trace-002",)).fetchone()
        assert trace is not None
        steps = handler_db.execute("SELECT * FROM agent_trace_steps WHERE trace_id = ?",
                                   ("trace-002",)).fetchall()
        assert len(steps) == 0

    def test_trace_auto_generated_id(self, handler_db):
        """Trace ID auto-generated when not provided."""
        cte = _make_cte("trace", {
            "query": "Test query",
            "response": "Test response",
            "total_latency": 500,
            "steps": [{"tool": "llm", "action": "gen", "latency_ms": 500, "status": "ok"}],
        }, entity_ref="file_drop://agent_traces/Test Agent")
        TracesHandler().write(handler_db, cte, "agent-xyz789", None, None)

        trace = handler_db.execute("SELECT * FROM agent_traces WHERE entity_id = ?",
                                   ("agent-xyz789",)).fetchone()
        assert trace is not None
        assert trace["trace_id"].startswith("trace-")

    def test_trace_duplicate_ignored(self, handler_db):
        """Duplicate trace_id should be silently ignored."""
        cte = _make_cte("trace", {
            "trace_id": "trace-dup",
            "query": "First",
            "response": "Response 1",
            "total_latency": 100,
            "steps": [],
        }, entity_ref="file_drop://agent_traces/Test Agent")
        TracesHandler().write(handler_db, cte, "agent-xyz789", None, None)

        cte2 = _make_cte("trace", {
            "trace_id": "trace-dup",
            "query": "Second",
            "response": "Response 2",
            "total_latency": 200,
            "steps": [],
        }, entity_ref="file_drop://agent_traces/Test Agent",
            timestamp="2026-07-15T11:00:00Z")
        TracesHandler().write(handler_db, cte2, "agent-xyz789", None, None)

        traces = handler_db.execute("SELECT * FROM agent_traces WHERE trace_id = ?",
                                    ("trace-dup",)).fetchall()
        assert len(traces) == 1
        assert traces[0]["query"] == "First"

    def test_trace_policy_fail(self, handler_db):
        cte = _make_cte("trace", {
            "trace_id": "trace-fail",
            "query": "Something inappropriate",
            "response": "I cannot help with that.",
            "total_latency": 50,
            "policy_pass": False,
            "policy_note": "Content policy violation",
            "steps": [],
        }, entity_ref="file_drop://agent_traces/Test Agent")
        TracesHandler().write(handler_db, cte, "agent-xyz789", None, None)

        trace = handler_db.execute("SELECT * FROM agent_traces WHERE trace_id = ?",
                                   ("trace-fail",)).fetchone()
        assert trace["policy_pass"] == 0
        assert trace["policy_note"] == "Content policy violation"


# ═══════════════════════════════════════════════════════════════════════════
# MAPPING ENGINE INTEGRATION TESTS
# ═══════════════════════════════════════════════════════════════════════════

class TestMappingEngineHandlerRouting:
    """Test that the mapping engine routes CTEs to the correct handler."""

    def test_drift_cte_routes_to_drift_snapshots(self, handler_db):
        """Drift CTE processed through mapping engine writes to drift_snapshots."""
        from ingestion.staging import insert_ctes
        from ingestion.mapping_engine import MappingEngine
        from pathlib import Path

        cte = _make_cte("drift", {
            "drift_type": "psi",
            "scope": "overall",
            "value": 0.18,
            "status": "Warning",
        })
        insert_ctes(handler_db, [cte])

        engine = MappingEngine(handler_db, Path(__file__).parent.parent / "mappings")
        result = engine.process_batch()

        assert result["mapped"] == 1
        row = handler_db.execute("SELECT * FROM drift_snapshots").fetchone()
        assert row is not None
        assert row["value"] == 0.18

    def test_alert_cte_routes_to_alerts(self, handler_db):
        from ingestion.staging import insert_ctes
        from ingestion.mapping_engine import MappingEngine
        from pathlib import Path

        cte = _make_cte("alert", {
            "severity": "high",
            "alert_type": "performance_drop",
            "title": "Accuracy dropped below threshold",
            "description": "Model accuracy = 0.72, threshold = 0.85",
        })
        insert_ctes(handler_db, [cte])

        engine = MappingEngine(handler_db, Path(__file__).parent.parent / "mappings")
        result = engine.process_batch()

        assert result["mapped"] == 1
        row = handler_db.execute("SELECT * FROM alerts").fetchone()
        assert row is not None
        assert row["severity"] == "high"
        assert row["title"] == "Accuracy dropped below threshold"

    def test_lifecycle_cte_routes_to_lineage(self, handler_db):
        from ingestion.staging import insert_ctes
        from ingestion.mapping_engine import MappingEngine
        from pathlib import Path

        cte = _make_cte("lifecycle", {
            "lifecycle_type": "deployment",
            "version": "v3.0",
            "trigger": "manual",
        })
        insert_ctes(handler_db, [cte])

        engine = MappingEngine(handler_db, Path(__file__).parent.parent / "mappings")
        result = engine.process_batch()

        assert result["mapped"] == 1
        row = handler_db.execute("SELECT * FROM lineage_events").fetchone()
        assert row is not None
        assert row["version"] == "v3.0"

    def test_trace_cte_routes_to_agent_traces(self, handler_db):
        from ingestion.staging import insert_ctes
        from ingestion.mapping_engine import MappingEngine
        from pathlib import Path

        cte = _make_cte("trace", {
            "trace_id": "trace-e2e",
            "query": "E2E test",
            "response": "OK",
            "total_latency": 300,
            "steps": [{"tool": "llm", "action": "gen", "latency_ms": 300, "status": "ok"}],
        }, entity_ref="file_drop://agent_traces/Test Agent")
        insert_ctes(handler_db, [cte])

        engine = MappingEngine(handler_db, Path(__file__).parent.parent / "mappings")
        result = engine.process_batch()

        assert result["mapped"] == 1
        trace = handler_db.execute("SELECT * FROM agent_traces WHERE trace_id = ?",
                                   ("trace-e2e",)).fetchone()
        assert trace is not None
        assert trace["total_latency"] == 300

    def test_cohort_cte_routes_to_cohort_metrics(self, handler_db):
        from ingestion.staging import insert_ctes
        from ingestion.mapping_engine import MappingEngine
        from pathlib import Path

        cte = _make_cte("cohort", {
            "cohort_name": "senior",
            "cohort_dim": "age_group",
            "metric_name": "accuracy",
            "value": 0.89,
            "sample_size": 500,
        })
        insert_ctes(handler_db, [cte])

        engine = MappingEngine(handler_db, Path(__file__).parent.parent / "mappings")
        result = engine.process_batch()

        assert result["mapped"] == 1
        row = handler_db.execute("SELECT * FROM cohort_metrics").fetchone()
        assert row is not None
        assert row["cohort_name"] == "senior"
        assert row["value"] == 0.89

    def test_feature_importance_cte_routes(self, handler_db):
        from ingestion.staging import insert_ctes
        from ingestion.mapping_engine import MappingEngine
        from pathlib import Path

        cte = _make_cte("feature_importance", {
            "feature": "age",
            "importance": 0.42,
            "method": "shap",
        })
        insert_ctes(handler_db, [cte])

        engine = MappingEngine(handler_db, Path(__file__).parent.parent / "mappings")
        result = engine.process_batch()

        assert result["mapped"] == 1
        row = handler_db.execute("SELECT * FROM feature_importance").fetchone()
        assert row is not None
        assert row["feature"] == "age"
        assert row["importance"] == 0.42

    def test_data_quality_cte_routes(self, handler_db):
        from ingestion.staging import insert_ctes
        from ingestion.mapping_engine import MappingEngine
        from pathlib import Path

        cte = _make_cte("data_quality", {
            "feature": "income",
            "missing_rate": 0.03,
            "outlier_rate": 0.01,
            "schema_valid": True,
            "row_count": 5000,
        })
        insert_ctes(handler_db, [cte])

        engine = MappingEngine(handler_db, Path(__file__).parent.parent / "mappings")
        result = engine.process_batch()

        assert result["mapped"] == 1
        row = handler_db.execute("SELECT * FROM data_quality").fetchone()
        assert row is not None
        assert row["feature"] == "income"
        assert row["missing_rate"] == 0.03


# ═══════════════════════════════════════════════════════════════════════════
# DATA SOURCE LIVE MODE INTEGRATION TESTS
# ═══════════════════════════════════════════════════════════════════════════

class TestDataSourceLiveQueries:
    """Test that data_source.py live mode reads from specialized tables."""

    def test_live_alerts_query(self, handler_db):
        """Alerts written by handler are readable by data_source."""
        # Insert an alert directly
        handler_db.execute(
            """INSERT INTO alerts (entity_id, timestamp, severity, alert_type, title, description, resolved)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            ("model-abc123", "2026-07-15T10:00:00Z", "critical", "drift_threshold",
             "PSI exceeded", "Value=0.3", 0),
        )
        handler_db.commit()

        import data_source as ds
        original = ds.DATA_SOURCE
        original_path = ds.DB_PATH
        ds.DATA_SOURCE = "live"
        ds.DB_PATH = handler_db.execute("PRAGMA database_list").fetchone()[2]

        try:
            alerts = ds._live_alerts()
            assert len(alerts) == 1
            assert alerts[0]["severity"] == "critical"
            assert alerts[0]["model_name"] == "Test Model"
        finally:
            ds.DATA_SOURCE = original
            ds.DB_PATH = original_path

    def test_live_model_metrics_with_drift(self, handler_db):
        """Model metrics include drift data from drift_snapshots."""
        # Insert metric
        handler_db.execute(
            """INSERT INTO metric_timeseries (entity_id, metric_name, timestamp, value, source_event_id)
               VALUES (?, ?, ?, ?, ?)""",
            ("model-abc123", "accuracy", "2026-07-15T00:00:00Z", 0.95, "evt-1"),
        )
        # Insert drift
        handler_db.execute(
            """INSERT INTO drift_snapshots (entity_id, timestamp, drift_type, scope, value, status)
               VALUES (?, ?, ?, ?, ?, ?)""",
            ("model-abc123", "2026-07-15T00:00:00Z", "psi", "overall", 0.12, "Warning"),
        )
        handler_db.commit()

        import data_source as ds
        original = ds.DATA_SOURCE
        original_path = ds.DB_PATH
        ds.DATA_SOURCE = "live"
        ds.DB_PATH = handler_db.execute("PRAGMA database_list").fetchone()[2]

        try:
            metrics = ds._live_model_metrics("model-abc123")
            assert metrics is not None
            assert "drift" in metrics
            assert metrics["drift"]["values"] == [0.12]
            assert metrics["drift"]["current"] == 0.12
        finally:
            ds.DATA_SOURCE = original
            ds.DB_PATH = original_path

    def test_live_agent_traces(self, handler_db):
        """Agent traces written by handler are readable via data_source."""
        handler_db.execute(
            """INSERT INTO agent_traces (entity_id, trace_id, timestamp, query, response, total_latency, voice_score, policy_pass)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            ("agent-xyz789", "trace-live-1", "2026-07-15T10:00:00Z",
             "What is X?", "X is Y.", 800, 0.9, 1),
        )
        handler_db.execute(
            """INSERT INTO agent_trace_steps (trace_id, step_order, tool, action, latency_ms, status)
               VALUES (?, ?, ?, ?, ?, ?)""",
            ("trace-live-1", 1, "search", "query", 200, "ok"),
        )
        handler_db.commit()

        import data_source as ds
        original = ds.DATA_SOURCE
        original_path = ds.DB_PATH
        ds.DATA_SOURCE = "live"
        ds.DB_PATH = handler_db.execute("PRAGMA database_list").fetchone()[2]

        try:
            metrics = ds._live_agent_metrics("agent-xyz789")
            assert metrics is not None
            assert len(metrics["traces"]) == 1
            assert metrics["traces"][0]["trace_id"] == "trace-live-1"
            assert metrics["traces"][0]["tool_count"] == 1
        finally:
            ds.DATA_SOURCE = original
            ds.DB_PATH = original_path

    def test_live_lineage_events(self, handler_db):
        """Lineage events are returned by data_source."""
        handler_db.execute(
            """INSERT INTO lineage_events (entity_id, timestamp, event_type, version, trigger, metadata)
               VALUES (?, ?, ?, ?, ?, ?)""",
            ("model-abc123", "2026-07-15T00:00:00Z", "deployment", "v2.0", "manual",
             json.dumps({"status": "champion", "training_records": 50000})),
        )
        handler_db.commit()

        import data_source as ds
        original = ds.DATA_SOURCE
        original_path = ds.DB_PATH
        ds.DATA_SOURCE = "live"
        ds.DB_PATH = handler_db.execute("PRAGMA database_list").fetchone()[2]

        try:
            lineage = ds._live_model_lineage("model-abc123")
            assert lineage is not None
            assert lineage["total_versions"] == 1
            assert lineage["versions"][0]["version"] == "v2.0"
            assert lineage["versions"][0]["trigger"] == "manual"
        finally:
            ds.DATA_SOURCE = original
            ds.DB_PATH = original_path
