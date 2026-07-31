"""Tests for Session 4: Mapping Engine Core."""

import json
import os
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from ingestion.entity_resolution import resolve_entity, resolve_entity_with_strategy
from ingestion.mapping_engine import MappingEngine
from ingestion.mapping_loader import (
    MappingDefinition,
    find_matching_mapping,
    load_all_mappings,
    load_mapping_file,
)
from ingestion.models import CanonicalTelemetryEvent
from ingestion.staging import compute_event_id, insert_ctes, insert_single_cte
from ingestion.transforms import apply_transform, clamp, identity, round_value, scale
from ingestion.validation import (
    run_validation_rules,
    validate_not_null,
    validate_numeric,
    validate_range,
    validate_timestamp_not_future,
)


# ── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def engine_db(tmp_path):
    """Create a temp DB with full schema and a registered entity."""
    db_path = str(tmp_path / "engine_test.db")
    import app as app_module
    original_path = app_module.DB_PATH
    app_module.DB_PATH = db_path
    app_module.init_db()
    app_module.DB_PATH = original_path

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Register a model entity with aliases
    conn.execute(
        """INSERT INTO entity_registry
           (entity_id, entity_type, industry_id, project_id, name, status, metadata, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        ("model-test-001", "model", "hls", "proj-1", "Test Model", "Healthy",
         '{"model_type": "classification"}', "2026-07-01T00:00:00Z", "2026-07-01T00:00:00Z"),
    )
    conn.execute(
        "INSERT INTO entity_aliases (entity_id, alias_type, alias_value) VALUES (?, ?, ?)",
        ("model-test-001", "source_ref", "mlflow://experiment-1/test-model"),
    )
    conn.execute(
        "INSERT INTO entity_aliases (entity_id, alias_type, alias_value) VALUES (?, ?, ?)",
        ("model-test-001", "onboard_name", "Test Model"),
    )

    # Register an agent entity
    conn.execute(
        """INSERT INTO entity_registry
           (entity_id, entity_type, industry_id, project_id, name, status, metadata, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        ("agent-test-001", "agent", "hls", "proj-1", "Test Agent", "Operational",
         '{"framework": "LangChain"}', "2026-07-01T00:00:00Z", "2026-07-01T00:00:00Z"),
    )
    conn.execute(
        "INSERT INTO entity_aliases (entity_id, alias_type, alias_value) VALUES (?, ?, ?)",
        ("agent-test-001", "source_ref", "agent://test-agent"),
    )
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def mappings_dir(tmp_path):
    """Create a temp mappings directory with a valid YAML file."""
    mdir = tmp_path / "mappings"
    mdir.mkdir()
    (mdir / "metrics.yaml").write_text("""
version: "1"
applies_to:
  source_connector: file_drop
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
    (mdir / "drift.yaml").write_text("""
version: "1"
applies_to:
  source_connector: file_drop
  event_type: drift
entity_resolution:
  strategy: lookup
  on_no_match: reject
field_mappings:
  - source: payload.value
    target: drift_snapshots.value
    transform: clamp(0, 1)
validation_rules:
  - rule: numeric
    field: value
  - rule: range
    field: value
    min: 0
    max: 1
target_table: drift_snapshots
""", encoding="utf-8")
    return mdir


def _make_metric_cte(entity_ref="mlflow://experiment-1/test-model",
                     metric_name="accuracy", value=0.934,
                     timestamp="2026-07-30T14:00:00Z"):
    """Create a metric CTE for testing."""
    event_id = compute_event_id("file_drop", entity_ref, "metric", timestamp, metric_name)
    return CanonicalTelemetryEvent(
        event_id=event_id,
        source_connector="file_drop",
        source_entity_ref=entity_ref,
        event_type="metric",
        timestamp=timestamp,
        received_at="2026-07-30T14:00:01Z",
        mapping_version="v1",
        payload={"metric_name": metric_name, "metric_value": value},
    )


def _make_drift_cte(entity_ref="mlflow://experiment-1/test-model",
                    drift_type="psi", scope="overall", value=0.12,
                    timestamp="2026-07-30T14:00:00Z"):
    """Create a drift CTE for testing."""
    event_id = compute_event_id("file_drop", entity_ref, "drift", timestamp, scope)
    return CanonicalTelemetryEvent(
        event_id=event_id,
        source_connector="file_drop",
        source_entity_ref=entity_ref,
        event_type="drift",
        timestamp=timestamp,
        received_at="2026-07-30T14:00:01Z",
        mapping_version="v1",
        payload={"drift_type": drift_type, "scope": scope, "value": value, "status": "normal"},
    )


# ── Test: Entity Resolution ────────────────────────────────────────────────

class TestEntityResolution:

    def test_resolve_by_alias(self, engine_db):
        entity_id = resolve_entity(engine_db, "mlflow://experiment-1/test-model")
        assert entity_id == "model-test-001"

    def test_resolve_by_name_alias(self, engine_db):
        entity_id = resolve_entity(engine_db, "Test Model")
        assert entity_id == "model-test-001"

    def test_resolve_agent(self, engine_db):
        entity_id = resolve_entity(engine_db, "agent://test-agent")
        assert entity_id == "agent-test-001"

    def test_resolve_unknown_returns_none(self, engine_db):
        entity_id = resolve_entity(engine_db, "mlflow://unknown/entity")
        assert entity_id is None

    def test_resolve_with_strategy_reject(self, engine_db):
        eid, reason = resolve_entity_with_strategy(engine_db, "unknown-ref", "reject")
        assert eid is None
        assert "not found" in reason.lower()

    def test_resolve_with_strategy_skip(self, engine_db):
        eid, reason = resolve_entity_with_strategy(engine_db, "unknown-ref", "skip")
        assert eid is None
        assert "skip" in reason.lower()


# ── Test: Transforms ────────────────────────────────────────────────────────

class TestTransforms:

    def test_identity(self):
        assert identity(0.934) == 0.934
        assert identity(None) is None
        assert identity("text") == "text"

    def test_clamp_within_range(self):
        assert clamp(0.5, min_val=0.0, max_val=1.0) == 0.5

    def test_clamp_above_max(self):
        assert clamp(1.5, min_val=0.0, max_val=1.0) == 1.0

    def test_clamp_below_min(self):
        assert clamp(-0.5, min_val=0.0, max_val=1.0) == 0.0

    def test_clamp_none(self):
        assert clamp(None) is None

    def test_scale(self):
        assert scale(0.93, factor=100) == 93.0

    def test_scale_none(self):
        assert scale(None) is None

    def test_round_value(self):
        assert round_value(0.93421, decimals=4) == 0.9342

    def test_round_value_2(self):
        assert round_value(0.93421, decimals=2) == 0.93

    def test_apply_transform_identity(self):
        assert apply_transform("identity", 0.5) == 0.5

    def test_apply_transform_clamp(self):
        assert apply_transform("clamp", 1.5, {"min_val": 0, "max_val": 1}) == 1.0

    def test_apply_transform_unknown_raises(self):
        with pytest.raises(ValueError, match="Unknown transform"):
            apply_transform("nonexistent", 0.5)


# ── Test: Validation ────────────────────────────────────────────────────────

class TestValidation:

    def test_range_valid(self):
        ok, reason = validate_range(0.85, min_val=0, max_val=1)
        assert ok is True
        assert reason is None

    def test_range_below_min(self):
        ok, reason = validate_range(-0.5, min_val=0, max_val=1)
        assert ok is False
        assert "below minimum" in reason

    def test_range_above_max(self):
        ok, reason = validate_range(1.5, min_val=0, max_val=1)
        assert ok is False
        assert "above maximum" in reason

    def test_range_none_value(self):
        ok, reason = validate_range(None, min_val=0, max_val=1)
        assert ok is False

    def test_not_null_valid(self):
        ok, reason = validate_not_null(0.5)
        assert ok is True

    def test_not_null_none(self):
        ok, reason = validate_not_null(None)
        assert ok is False

    def test_not_null_empty_string(self):
        ok, reason = validate_not_null("")
        assert ok is False

    def test_numeric_valid(self):
        ok, reason = validate_numeric(0.93)
        assert ok is True

    def test_numeric_string_number(self):
        ok, reason = validate_numeric("0.93")
        assert ok is True

    def test_numeric_invalid(self):
        ok, reason = validate_numeric("NOT_A_NUMBER")
        assert ok is False

    def test_timestamp_valid(self):
        ok, reason = validate_timestamp_not_future("2026-07-30T14:00:00Z")
        assert ok is True

    def test_timestamp_far_future(self):
        ok, reason = validate_timestamp_not_future("2030-01-01T00:00:00Z")
        assert ok is False
        assert "future" in reason

    def test_run_rules_all_pass(self):
        rules = [{"rule": "not_null"}, {"rule": "numeric"}, {"rule": "range", "min": 0, "max": 1}]
        ok, reason = run_validation_rules(rules, 0.85)
        assert ok is True

    def test_run_rules_first_failure(self):
        rules = [{"rule": "not_null"}, {"rule": "numeric"}]
        ok, reason = run_validation_rules(rules, None)
        assert ok is False
        assert "null" in reason.lower()


# ── Test: Mapping Loader ────────────────────────────────────────────────────

class TestMappingLoader:

    def test_load_valid_yaml(self, mappings_dir):
        mapping = load_mapping_file(mappings_dir / "metrics.yaml")
        assert mapping.version == "1"
        assert mapping.source_connector == "file_drop"
        assert mapping.event_type == "metric"
        assert mapping.target_table == "metric_timeseries"
        assert len(mapping.field_mappings) == 1
        assert mapping.field_mappings[0].transform == "identity"

    def test_load_drift_yaml(self, mappings_dir):
        mapping = load_mapping_file(mappings_dir / "drift.yaml")
        assert mapping.event_type == "drift"
        assert mapping.target_table == "drift_snapshots"
        assert mapping.field_mappings[0].transform == "clamp"
        assert mapping.field_mappings[0].transform_params == {"min_val": 0.0, "max_val": 1.0}

    def test_load_all_mappings(self, mappings_dir):
        mappings = load_all_mappings(mappings_dir)
        assert len(mappings) == 2

    def test_load_empty_dir(self, tmp_path):
        empty = tmp_path / "empty_mappings"
        empty.mkdir()
        mappings = load_all_mappings(empty)
        assert mappings == []

    def test_load_missing_dir(self, tmp_path):
        mappings = load_all_mappings(tmp_path / "nonexistent")
        assert mappings == []

    def test_load_invalid_yaml_raises(self, tmp_path):
        bad_dir = tmp_path / "bad"
        bad_dir.mkdir()
        (bad_dir / "invalid.yaml").write_text("version: null\napplies_to: {}", encoding="utf-8")
        with pytest.raises(ValueError):
            load_all_mappings(bad_dir)

    def test_find_matching_mapping(self, mappings_dir):
        mappings = load_all_mappings(mappings_dir)
        result = find_matching_mapping(mappings, "file_drop", "metric", {"metric_name": "accuracy"})
        assert result is not None
        assert result.event_type == "metric"

    def test_find_matching_drift(self, mappings_dir):
        mappings = load_all_mappings(mappings_dir)
        result = find_matching_mapping(mappings, "file_drop", "drift", {"value": 0.1})
        assert result is not None
        assert result.target_table == "drift_snapshots"

    def test_find_no_match(self, mappings_dir):
        mappings = load_all_mappings(mappings_dir)
        result = find_matching_mapping(mappings, "webhook", "metric", {})
        assert result is None


# ── Test: Mapping Engine End-to-End ─────────────────────────────────────────

class TestMappingEngineEndToEnd:

    def test_cte_to_metric_row(self, engine_db, mappings_dir):
        """Insert CTE → run engine → verify metric_timeseries has row."""
        cte = _make_metric_cte(value=0.934)
        insert_single_cte(engine_db, cte)

        engine = MappingEngine(engine_db, mappings_dir)
        result = engine.process_batch()

        assert result["processed"] == 1
        assert result["mapped"] == 1
        assert result["rejected"] == 0

        # Verify metric store row
        row = engine_db.execute(
            "SELECT * FROM metric_timeseries WHERE entity_id = 'model-test-001'"
        ).fetchone()
        assert row is not None
        assert row["metric_name"] == "accuracy"
        assert row["value"] == 0.934
        assert row["source_event_id"] == cte.event_id

    def test_drift_cte_to_snapshot(self, engine_db, mappings_dir):
        """Drift CTE writes to drift_snapshots table."""
        cte = _make_drift_cte(value=0.12)
        insert_single_cte(engine_db, cte)

        engine = MappingEngine(engine_db, mappings_dir)
        result = engine.process_batch()

        assert result["mapped"] == 1
        row = engine_db.execute(
            "SELECT * FROM drift_snapshots WHERE entity_id = 'model-test-001'"
        ).fetchone()
        assert row is not None
        assert row["drift_type"] == "psi"
        assert row["scope"] == "overall"
        assert row["value"] == 0.12

    def test_unknown_entity_rejected(self, engine_db, mappings_dir):
        """CTE with unknown entity_ref is rejected."""
        cte = _make_metric_cte(entity_ref="mlflow://unknown/model", value=0.9)
        insert_single_cte(engine_db, cte)

        engine = MappingEngine(engine_db, mappings_dir)
        result = engine.process_batch()

        assert result["rejected"] == 1
        row = engine_db.execute(
            "SELECT processing_status, rejection_reason FROM staging_events WHERE event_id = ?",
            (cte.event_id,)
        ).fetchone()
        assert row["processing_status"] == "rejected"
        assert "not found" in row["rejection_reason"].lower()

    def test_invalid_value_rejected(self, engine_db, mappings_dir):
        """CTE with non-numeric value is rejected by validation."""
        cte = _make_metric_cte(value="NOT_A_NUMBER")
        insert_single_cte(engine_db, cte)

        engine = MappingEngine(engine_db, mappings_dir)
        result = engine.process_batch()

        assert result["rejected"] == 1
        row = engine_db.execute(
            "SELECT rejection_reason FROM staging_events WHERE event_id = ?",
            (cte.event_id,)
        ).fetchone()
        assert "not numeric" in row["rejection_reason"].lower() or "Validation" in row["rejection_reason"]

    def test_null_value_rejected(self, engine_db, mappings_dir):
        """CTE with None value is rejected."""
        cte = _make_metric_cte(value=None)
        insert_single_cte(engine_db, cte)

        engine = MappingEngine(engine_db, mappings_dir)
        result = engine.process_batch()

        assert result["rejected"] == 1

    def test_clamp_transform_applied(self, engine_db, mappings_dir):
        """Drift value > 1 is clamped to 1.0."""
        cte = _make_drift_cte(value=1.5)
        insert_single_cte(engine_db, cte)

        engine = MappingEngine(engine_db, mappings_dir)
        result = engine.process_batch()

        assert result["mapped"] == 1
        row = engine_db.execute(
            "SELECT value FROM drift_snapshots WHERE entity_id = 'model-test-001'"
        ).fetchone()
        assert row["value"] == 1.0

    def test_batch_processing_100(self, engine_db, mappings_dir):
        """Process 100 CTEs in a batch."""
        ctes = [
            _make_metric_cte(metric_name=f"metric_{i}", value=0.8 + i * 0.001,
                             timestamp=f"2026-07-{(i % 28) + 1:02d}T{i % 24:02d}:00:00Z")
            for i in range(100)
        ]
        insert_ctes(engine_db, ctes)

        engine = MappingEngine(engine_db, mappings_dir)
        result = engine.process_batch()

        assert result["processed"] == 100
        assert result["mapped"] == 100

        count = engine_db.execute(
            "SELECT COUNT(*) as cnt FROM metric_timeseries"
        ).fetchone()["cnt"]
        assert count == 100

    def test_no_pending_does_nothing(self, engine_db, mappings_dir):
        """Engine gracefully handles empty queue."""
        engine = MappingEngine(engine_db, mappings_dir)
        result = engine.process_batch()
        assert result == {"processed": 0, "mapped": 0, "rejected": 0, "no_mapping": 0}

    def test_no_mapping_for_connector(self, engine_db, mappings_dir):
        """CTE from unknown connector type is rejected."""
        event_id = compute_event_id("webhook", "ref", "metric", "2026-07-30T14:00:00Z", "acc")
        cte = CanonicalTelemetryEvent(
            event_id=event_id,
            source_connector="webhook",
            source_entity_ref="mlflow://experiment-1/test-model",
            event_type="metric",
            timestamp="2026-07-30T14:00:00Z",
            received_at="2026-07-30T14:00:01Z",
            mapping_version="v1",
            payload={"metric_name": "acc", "metric_value": 0.9},
        )
        insert_single_cte(engine_db, cte)

        engine = MappingEngine(engine_db, mappings_dir)
        result = engine.process_batch()

        assert result["rejected"] == 1
        assert result["no_mapping"] == 1

    def test_multiple_metrics_same_entity(self, engine_db, mappings_dir):
        """Multiple different metrics for same entity all map correctly."""
        ctes = [
            _make_metric_cte(metric_name="accuracy", value=0.93, timestamp="2026-07-30T14:00:00Z"),
            _make_metric_cte(metric_name="precision", value=0.91, timestamp="2026-07-30T14:00:00Z"),
            _make_metric_cte(metric_name="recall", value=0.89, timestamp="2026-07-30T14:00:00Z"),
        ]
        insert_ctes(engine_db, ctes)

        engine = MappingEngine(engine_db, mappings_dir)
        result = engine.process_batch()

        assert result["mapped"] == 3
        rows = engine_db.execute(
            "SELECT metric_name, value FROM metric_timeseries ORDER BY metric_name"
        ).fetchall()
        assert len(rows) == 3
        names = [r["metric_name"] for r in rows]
        assert "accuracy" in names
        assert "precision" in names
        assert "recall" in names
