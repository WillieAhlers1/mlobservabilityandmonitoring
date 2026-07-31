"""Tests for Session 3: Staging Store and CTE Write Path."""

import json
import os
import sqlite3
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from ingestion.models import CanonicalTelemetryEvent
from ingestion.staging import (
    compute_event_id,
    count_by_status,
    fetch_pending_batch,
    insert_ctes,
    insert_single_cte,
    mark_batch_processed,
    mark_processed,
)


@pytest.fixture
def staging_db(tmp_path):
    """Create a temp DB with staging_events table."""
    db_path = str(tmp_path / "staging_test.db")
    import app as app_module
    original_path = app_module.DB_PATH
    app_module.DB_PATH = db_path
    app_module.init_db()
    app_module.DB_PATH = original_path

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()


def _make_cte(connector="file_drop", entity_ref="mlflow://exp-1/model-a",
              event_type="metric", timestamp="2026-07-30T14:00:00Z",
              metric_name="accuracy", value=0.934, **overrides):
    """Helper to create a CTE with sensible defaults."""
    event_id = compute_event_id(connector, entity_ref, event_type, timestamp, metric_name)
    payload = {"metric_name": metric_name, "metric_value": value}
    payload.update(overrides.pop("payload_extra", {}))
    defaults = {
        "event_id": event_id,
        "source_connector": connector,
        "source_entity_ref": entity_ref,
        "event_type": event_type,
        "timestamp": timestamp,
        "received_at": "2026-07-30T14:00:01Z",
        "mapping_version": "v1",
        "payload": payload,
        "processing_status": "pending",
    }
    defaults.update(overrides)
    return CanonicalTelemetryEvent(**defaults)


class TestComputeEventId:
    """Deterministic event_id computation."""

    def test_same_inputs_same_hash(self):
        id1 = compute_event_id("mlflow", "mlflow://exp-1/run-a", "metric", "2026-07-30T14:00:00Z", "accuracy")
        id2 = compute_event_id("mlflow", "mlflow://exp-1/run-a", "metric", "2026-07-30T14:00:00Z", "accuracy")
        assert id1 == id2

    def test_different_timestamp_different_hash(self):
        id1 = compute_event_id("mlflow", "mlflow://exp-1/run-a", "metric", "2026-07-30T14:00:00Z", "accuracy")
        id2 = compute_event_id("mlflow", "mlflow://exp-1/run-a", "metric", "2026-07-30T15:00:00Z", "accuracy")
        assert id1 != id2

    def test_different_metric_different_hash(self):
        id1 = compute_event_id("mlflow", "mlflow://exp-1/run-a", "metric", "2026-07-30T14:00:00Z", "accuracy")
        id2 = compute_event_id("mlflow", "mlflow://exp-1/run-a", "metric", "2026-07-30T14:00:00Z", "precision")
        assert id1 != id2

    def test_different_connector_different_hash(self):
        id1 = compute_event_id("mlflow", "ref", "metric", "2026-07-30T14:00:00Z", "accuracy")
        id2 = compute_event_id("azureml", "ref", "metric", "2026-07-30T14:00:00Z", "accuracy")
        assert id1 != id2

    def test_none_metric_name(self):
        id1 = compute_event_id("mlflow", "ref", "alert", "2026-07-30T14:00:00Z", None)
        id2 = compute_event_id("mlflow", "ref", "alert", "2026-07-30T14:00:00Z", None)
        assert id1 == id2
        assert len(id1) == 32

    def test_hash_length(self):
        event_id = compute_event_id("x", "y", "z", "t", "m")
        assert len(event_id) == 32
        assert all(c in "0123456789abcdef" for c in event_id)


class TestInsertSingleCTE:
    """Single CTE insertion."""

    def test_insert_valid_cte(self, staging_db):
        cte = _make_cte()
        result = insert_single_cte(staging_db, cte)
        assert result is True

        row = staging_db.execute(
            "SELECT * FROM staging_events WHERE event_id = ?", (cte.event_id,)
        ).fetchone()
        assert row is not None
        assert row["processing_status"] == "pending"
        assert row["source_connector"] == "file_drop"
        assert row["event_type"] == "metric"

    def test_insert_duplicate_returns_false(self, staging_db):
        cte = _make_cte()
        assert insert_single_cte(staging_db, cte) is True
        assert insert_single_cte(staging_db, cte) is False

    def test_duplicate_only_one_row(self, staging_db):
        cte = _make_cte()
        insert_single_cte(staging_db, cte)
        insert_single_cte(staging_db, cte)
        count = staging_db.execute(
            "SELECT COUNT(*) as cnt FROM staging_events WHERE event_id = ?", (cte.event_id,)
        ).fetchone()["cnt"]
        assert count == 1

    def test_payload_stored_as_json(self, staging_db):
        cte = _make_cte(payload_extra={"dimensions": {"cohort": "age_65_plus"}})
        insert_single_cte(staging_db, cte)
        row = staging_db.execute(
            "SELECT payload FROM staging_events WHERE event_id = ?", (cte.event_id,)
        ).fetchone()
        payload = json.loads(row["payload"])
        assert payload["metric_name"] == "accuracy"
        assert payload["dimensions"]["cohort"] == "age_65_plus"


class TestBatchInsert:
    """Batch CTE insertion."""

    def test_insert_100_ctes(self, staging_db):
        ctes = [
            _make_cte(timestamp=f"2026-07-{(i % 28) + 1:02d}T{i % 24:02d}:00:00Z",
                      metric_name=f"metric_{i}")
            for i in range(100)
        ]
        inserted = insert_ctes(staging_db, ctes)
        assert inserted == 100

        total = staging_db.execute("SELECT COUNT(*) as cnt FROM staging_events").fetchone()["cnt"]
        assert total == 100

    def test_batch_with_duplicates(self, staging_db):
        ctes = [
            _make_cte(timestamp=f"2026-07-{(i % 28) + 1:02d}T{i % 24:02d}:00:00Z",
                      metric_name=f"metric_{i}")
            for i in range(100)
        ]
        # Add 3 duplicates (same as first 3)
        ctes.extend([
            _make_cte(timestamp="2026-07-01T00:00:00Z", metric_name="metric_0"),
            _make_cte(timestamp="2026-07-02T01:00:00Z", metric_name="metric_1"),
            _make_cte(timestamp="2026-07-03T02:00:00Z", metric_name="metric_2"),
        ])
        inserted = insert_ctes(staging_db, ctes)
        assert inserted == 100  # 3 duplicates silently dropped

        total = staging_db.execute("SELECT COUNT(*) as cnt FROM staging_events").fetchone()["cnt"]
        assert total == 100

    def test_empty_list(self, staging_db):
        inserted = insert_ctes(staging_db, [])
        assert inserted == 0


class TestFetchPendingBatch:
    """Fetching pending CTEs."""

    def test_returns_pending_only(self, staging_db):
        # Insert 5 pending
        for i in range(5):
            insert_single_cte(staging_db, _make_cte(
                timestamp=f"2026-07-{i + 1:02d}T10:00:00Z", metric_name=f"m{i}"))
        # Mark 2 as mapped
        rows = staging_db.execute("SELECT event_id FROM staging_events LIMIT 2").fetchall()
        for row in rows:
            mark_processed(staging_db, row["event_id"], "mapped")

        pending = fetch_pending_batch(staging_db, limit=100)
        assert len(pending) == 3
        for cte in pending:
            assert cte.processing_status == "pending"

    def test_respects_limit(self, staging_db):
        for i in range(50):
            insert_single_cte(staging_db, _make_cte(
                timestamp=f"2026-07-{(i % 28) + 1:02d}T{i % 24:02d}:00:00Z",
                metric_name=f"m{i}"))

        batch = fetch_pending_batch(staging_db, limit=10)
        assert len(batch) == 10

    def test_ordered_by_timestamp(self, staging_db):
        # Insert out of order
        insert_single_cte(staging_db, _make_cte(timestamp="2026-07-30T10:00:00Z", metric_name="late"))
        insert_single_cte(staging_db, _make_cte(timestamp="2026-07-01T10:00:00Z", metric_name="early"))
        insert_single_cte(staging_db, _make_cte(timestamp="2026-07-15T10:00:00Z", metric_name="mid"))

        batch = fetch_pending_batch(staging_db, limit=10)
        assert batch[0].timestamp == "2026-07-01T10:00:00Z"
        assert batch[1].timestamp == "2026-07-15T10:00:00Z"
        assert batch[2].timestamp == "2026-07-30T10:00:00Z"

    def test_empty_when_none_pending(self, staging_db):
        batch = fetch_pending_batch(staging_db, limit=10)
        assert batch == []

    def test_payload_deserialized(self, staging_db):
        cte = _make_cte(value=0.95)
        insert_single_cte(staging_db, cte)
        batch = fetch_pending_batch(staging_db, limit=1)
        assert isinstance(batch[0].payload, dict)
        assert batch[0].payload["metric_value"] == 0.95


class TestMarkProcessed:
    """Status transitions."""

    def test_mark_as_mapped(self, staging_db):
        cte = _make_cte()
        insert_single_cte(staging_db, cte)
        mark_processed(staging_db, cte.event_id, "mapped")

        row = staging_db.execute(
            "SELECT processing_status, processed_at FROM staging_events WHERE event_id = ?",
            (cte.event_id,)
        ).fetchone()
        assert row["processing_status"] == "mapped"
        assert row["processed_at"] is not None

    def test_mark_as_rejected_with_reason(self, staging_db):
        cte = _make_cte()
        insert_single_cte(staging_db, cte)
        mark_processed(staging_db, cte.event_id, "rejected", "Value out of range: 1.5")

        row = staging_db.execute(
            "SELECT processing_status, rejection_reason FROM staging_events WHERE event_id = ?",
            (cte.event_id,)
        ).fetchone()
        assert row["processing_status"] == "rejected"
        assert row["rejection_reason"] == "Value out of range: 1.5"

    def test_batch_mark_processed(self, staging_db):
        ctes = [_make_cte(metric_name=f"m{i}", timestamp=f"2026-07-{i+1:02d}T10:00:00Z")
                for i in range(5)]
        insert_ctes(staging_db, ctes)

        updates = [
            (ctes[0].event_id, "mapped", None),
            (ctes[1].event_id, "mapped", None),
            (ctes[2].event_id, "rejected", "Unknown entity"),
            (ctes[3].event_id, "mapped", None),
            (ctes[4].event_id, "rejected", "Validation failed"),
        ]
        mark_batch_processed(staging_db, updates)

        counts = count_by_status(staging_db)
        assert counts.get("mapped", 0) == 3
        assert counts.get("rejected", 0) == 2
        assert counts.get("pending", 0) == 0


class TestCountByStatus:
    """Status counting."""

    def test_counts_correct(self, staging_db):
        for i in range(10):
            insert_single_cte(staging_db, _make_cte(
                metric_name=f"m{i}", timestamp=f"2026-07-{i+1:02d}T10:00:00Z"))

        # Mark some
        rows = staging_db.execute("SELECT event_id FROM staging_events").fetchall()
        mark_processed(staging_db, rows[0]["event_id"], "mapped")
        mark_processed(staging_db, rows[1]["event_id"], "mapped")
        mark_processed(staging_db, rows[2]["event_id"], "rejected", "bad data")

        counts = count_by_status(staging_db)
        assert counts["pending"] == 7
        assert counts["mapped"] == 2
        assert counts["rejected"] == 1

    def test_empty_db(self, staging_db):
        counts = count_by_status(staging_db)
        assert counts == {}


class TestCTEDataclass:
    """CTE dataclass behavior."""

    def test_default_status_is_pending(self):
        cte = CanonicalTelemetryEvent(
            event_id="abc123",
            source_connector="test",
            source_entity_ref="ref",
            event_type="metric",
            timestamp="2026-07-30T10:00:00Z",
            received_at="2026-07-30T10:00:01Z",
            mapping_version="v1",
            payload={"key": "value"},
        )
        assert cte.processing_status == "pending"
        assert cte.rejection_reason is None

    def test_all_fields_settable(self):
        cte = CanonicalTelemetryEvent(
            event_id="id1",
            source_connector="mlflow",
            source_entity_ref="mlflow://exp/run",
            event_type="drift",
            timestamp="2026-07-30T10:00:00Z",
            received_at="2026-07-30T10:00:01Z",
            mapping_version="v2",
            payload={"drift_type": "psi", "value": 0.15},
            processing_status="rejected",
            rejection_reason="Entity not found",
        )
        assert cte.event_type == "drift"
        assert cte.processing_status == "rejected"
        assert cte.rejection_reason == "Entity not found"
