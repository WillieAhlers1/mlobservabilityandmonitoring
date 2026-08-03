"""Tests for Session 11: Ingestion Health Dashboard and Dead-Letter Queue.

Tests cover:
- Pipeline stats computation
- Processing lag calculation
- Connector health display
- Dead-letter queue listing and reprocessing
- Schema drift detection
- Live-mode-only access control
"""

import json
import os
import sqlite3
import sys
from datetime import datetime, timezone, timedelta

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


@pytest.fixture
def health_db(tmp_db):
    """DB connection with test data for health/observability tests."""
    conn = sqlite3.connect(tmp_db)
    conn.row_factory = sqlite3.Row

    # Create project and entity
    conn.execute(
        "INSERT INTO projects (id, name, description, owner, team, created_date, status) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("proj-1", "Test Project", "Desc", "owner", "team", "2026-01-01", "Active"),
    )
    conn.execute(
        "INSERT INTO entity_registry (entity_id, entity_type, industry_id, project_id, name, status, metadata, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("model-abc123", "model", "retail", "proj-1", "Test Model", "Healthy",
         json.dumps({}), "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z"),
    )
    conn.execute(
        "INSERT INTO entity_aliases (entity_id, alias_type, alias_value) VALUES (?, ?, ?)",
        ("model-abc123", "source_ref", "file_drop://metrics/Test Model"),
    )
    conn.commit()
    yield conn
    conn.close()


def _insert_staging_event(db, event_id, status="pending", event_type="metric",
                          connector="file_drop", entity_ref="file_drop://metrics/Test Model",
                          received_at=None, timestamp=None, processed_at=None,
                          rejection_reason=None):
    """Helper to insert a staging event."""
    now = datetime.now(timezone.utc)
    if received_at is None:
        received_at = now.isoformat()
    if timestamp is None:
        timestamp = (now - timedelta(minutes=5)).isoformat()

    db.execute(
        """INSERT OR IGNORE INTO staging_events
           (event_id, source_connector, source_entity_ref, event_type,
            timestamp, received_at, mapping_version, payload, processing_status,
            rejection_reason, processed_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (event_id, connector, entity_ref, event_type,
         timestamp, received_at, "1", json.dumps({"value": 1.0}),
         status, rejection_reason, processed_at),
    )
    db.commit()


# ═══════════════════════════════════════════════════════════════════════════
# PIPELINE STATS TESTS
# ═══════════════════════════════════════════════════════════════════════════

class TestPipelineStats:
    """Test ingestion/metrics.py pipeline statistics."""

    def test_empty_db_stats(self, health_db):
        from ingestion.metrics import get_pipeline_stats
        stats = get_pipeline_stats(health_db)
        assert stats["total_events"] == 0
        assert stats["pending"] == 0
        assert stats["rejected"] == 0
        assert stats["mapped"] == 0
        assert stats["rejection_rate"] == 0.0

    def test_mixed_status_counts(self, health_db):
        from ingestion.metrics import get_pipeline_stats

        now = datetime.now(timezone.utc).isoformat()
        _insert_staging_event(health_db, "evt-1", "pending")
        _insert_staging_event(health_db, "evt-2", "pending")
        _insert_staging_event(health_db, "evt-3", "mapped", processed_at=now)
        _insert_staging_event(health_db, "evt-4", "mapped", processed_at=now)
        _insert_staging_event(health_db, "evt-5", "mapped", processed_at=now)
        _insert_staging_event(health_db, "evt-6", "rejected", processed_at=now,
                              rejection_reason="No matching mapping")

        stats = get_pipeline_stats(health_db)
        assert stats["total_events"] == 6
        assert stats["pending"] == 2
        assert stats["mapped"] == 3
        assert stats["rejected"] == 1
        assert abs(stats["rejection_rate"] - 1/6) < 0.01

    def test_processed_1h_filter(self, health_db):
        from ingestion.metrics import get_pipeline_stats

        now = datetime.now(timezone.utc)
        recent = now.isoformat()
        old = (now - timedelta(hours=2)).isoformat()

        _insert_staging_event(health_db, "evt-recent", "mapped", processed_at=recent)
        _insert_staging_event(health_db, "evt-old", "mapped", processed_at=old)

        stats = get_pipeline_stats(health_db)
        assert stats["processed_1h"] == 1
        assert stats["processed_24h"] == 2


class TestProcessingLag:
    """Test processing lag computation."""

    def test_no_pending_events(self, health_db):
        from ingestion.metrics import get_processing_lag
        lag = get_processing_lag(health_db)
        assert lag["lag_seconds"] is None
        assert lag["oldest_pending_at"] is None

    def test_pending_events_show_lag(self, health_db):
        from ingestion.metrics import get_processing_lag

        five_min_ago = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        _insert_staging_event(health_db, "evt-lag", "pending", received_at=five_min_ago)

        lag = get_processing_lag(health_db)
        assert lag["lag_seconds"] is not None
        assert lag["lag_seconds"] >= 290  # ~5 minutes
        assert lag["oldest_pending_at"] == five_min_ago

    def test_oldest_pending_selected(self, health_db):
        from ingestion.metrics import get_processing_lag

        now = datetime.now(timezone.utc)
        older = (now - timedelta(minutes=10)).isoformat()
        newer = (now - timedelta(minutes=2)).isoformat()

        _insert_staging_event(health_db, "evt-old", "pending", received_at=older)
        _insert_staging_event(health_db, "evt-new", "pending", received_at=newer)

        lag = get_processing_lag(health_db)
        assert lag["oldest_pending_at"] == older


class TestConnectorHealth:
    """Test connector health retrieval."""

    def test_empty_connector_health(self, health_db):
        from ingestion.metrics import get_connector_health
        connectors = get_connector_health(health_db)
        assert connectors == []

    def test_connectors_returned(self, health_db):
        from ingestion.metrics import get_connector_health

        health_db.execute(
            """INSERT INTO connector_health
               (connector_id, connector_type, state, last_success, consecutive_failures, error_message)
               VALUES (?, ?, ?, ?, ?, ?)""",
            ("file-drop-1", "file_drop", "healthy", "2026-07-15T10:00:00Z", 0, None),
        )
        health_db.execute(
            """INSERT INTO connector_health
               (connector_id, connector_type, state, last_success, last_failure, consecutive_failures, error_message)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            ("webhook-1", "webhook", "degraded", "2026-07-15T09:00:00Z",
             "2026-07-15T10:00:00Z", 3, "Connection timeout"),
        )
        health_db.commit()

        connectors = get_connector_health(health_db)
        assert len(connectors) == 2
        assert connectors[0]["connector_id"] == "file-drop-1"
        assert connectors[0]["state"] == "healthy"
        assert connectors[1]["connector_id"] == "webhook-1"
        assert connectors[1]["state"] == "degraded"
        assert connectors[1]["error_message"] == "Connection timeout"


# ═══════════════════════════════════════════════════════════════════════════
# DEAD LETTER QUEUE TESTS
# ═══════════════════════════════════════════════════════════════════════════

class TestDeadLetterQueue:
    """Test dead letter queue functions."""

    def test_empty_rejected_list(self, health_db):
        from ingestion.metrics import get_rejected_events, get_rejected_count
        events = get_rejected_events(health_db)
        assert events == []
        assert get_rejected_count(health_db) == 0

    def test_rejected_events_listed(self, health_db):
        from ingestion.metrics import get_rejected_events, get_rejected_count

        now = datetime.now(timezone.utc).isoformat()
        _insert_staging_event(health_db, "rej-1", "rejected", processed_at=now,
                              rejection_reason="No matching mapping")
        _insert_staging_event(health_db, "rej-2", "rejected", processed_at=now,
                              rejection_reason="Validation failed: value out of range")

        events = get_rejected_events(health_db)
        assert len(events) == 2
        assert get_rejected_count(health_db) == 2
        assert events[0]["rejection_reason"] in [
            "No matching mapping", "Validation failed: value out of range"
        ]

    def test_rejected_pagination(self, health_db):
        from ingestion.metrics import get_rejected_events

        now = datetime.now(timezone.utc).isoformat()
        for i in range(10):
            _insert_staging_event(health_db, f"rej-{i}", "rejected", processed_at=now,
                                  rejection_reason=f"Reason {i}")

        page1 = get_rejected_events(health_db, limit=5, offset=0)
        page2 = get_rejected_events(health_db, limit=5, offset=5)
        assert len(page1) == 5
        assert len(page2) == 5
        # No overlap
        ids1 = {e["event_id"] for e in page1}
        ids2 = {e["event_id"] for e in page2}
        assert ids1.isdisjoint(ids2)

    def test_reprocess_single_event(self, health_db):
        from ingestion.metrics import reprocess_event

        now = datetime.now(timezone.utc).isoformat()
        _insert_staging_event(health_db, "rej-reprocess", "rejected", processed_at=now,
                              rejection_reason="Transform error")

        result = reprocess_event(health_db, "rej-reprocess")
        assert result is True

        # Verify status is now pending
        row = health_db.execute(
            "SELECT processing_status, rejection_reason, processed_at FROM staging_events WHERE event_id = ?",
            ("rej-reprocess",),
        ).fetchone()
        assert row["processing_status"] == "pending"
        assert row["rejection_reason"] is None
        assert row["processed_at"] is None

    def test_reprocess_nonexistent_event(self, health_db):
        from ingestion.metrics import reprocess_event
        result = reprocess_event(health_db, "nonexistent")
        assert result is False

    def test_reprocess_non_rejected_event(self, health_db):
        from ingestion.metrics import reprocess_event
        _insert_staging_event(health_db, "evt-mapped", "mapped")
        result = reprocess_event(health_db, "evt-mapped")
        assert result is False

    def test_reprocess_all_rejected(self, health_db):
        from ingestion.metrics import reprocess_all_rejected, get_rejected_count

        now = datetime.now(timezone.utc).isoformat()
        for i in range(5):
            _insert_staging_event(health_db, f"rej-all-{i}", "rejected", processed_at=now,
                                  rejection_reason="Error")

        count = reprocess_all_rejected(health_db)
        assert count == 5
        assert get_rejected_count(health_db) == 0


class TestLateEventCount:
    """Test late event detection."""

    def test_no_late_events(self, health_db):
        from ingestion.metrics import get_late_event_count

        now = datetime.now(timezone.utc)
        _insert_staging_event(health_db, "evt-ontime",
                              timestamp=now.isoformat(),
                              received_at=(now + timedelta(minutes=1)).isoformat())

        count = get_late_event_count(health_db, grace_period_hours=6)
        assert count == 0

    def test_late_events_detected(self, health_db):
        from ingestion.metrics import get_late_event_count

        now = datetime.now(timezone.utc)
        # Event occurred 10 hours ago but only received now
        old_time = (now - timedelta(hours=10)).isoformat()
        _insert_staging_event(health_db, "evt-late",
                              timestamp=old_time,
                              received_at=now.isoformat())

        count = get_late_event_count(health_db, grace_period_hours=6)
        assert count == 1


# ═══════════════════════════════════════════════════════════════════════════
# SCHEMA DRIFT DETECTION TESTS
# ═══════════════════════════════════════════════════════════════════════════

class TestSchemaDriftDetection:
    """Test ingestion/drift_detector.py."""

    def test_no_drift_when_no_rejections(self, health_db):
        from ingestion.drift_detector import detect_schema_drift

        now = datetime.now(timezone.utc).isoformat()
        for i in range(10):
            _insert_staging_event(health_db, f"ok-{i}", "mapped",
                                  received_at=now, processed_at=now)

        alerts = detect_schema_drift(health_db)
        assert alerts == []

    def test_drift_detected_above_threshold(self, health_db):
        from ingestion.drift_detector import detect_schema_drift

        now = datetime.now(timezone.utc).isoformat()
        # 8 mapped, 2 rejected = 20% rejection rate (above 5% default threshold)
        for i in range(8):
            _insert_staging_event(health_db, f"ok-{i}", "mapped",
                                  received_at=now, processed_at=now)
        for i in range(2):
            _insert_staging_event(health_db, f"rej-{i}", "rejected",
                                  received_at=now, processed_at=now,
                                  rejection_reason="Transform error: field missing")

        alerts = detect_schema_drift(health_db)
        assert len(alerts) == 1
        assert alerts[0]["connector"] == "file_drop"
        assert alerts[0]["event_type"] == "metric"
        assert alerts[0]["rejection_rate"] == 0.2
        assert alerts[0]["rejected_events"] == 2
        assert alerts[0]["total_events"] == 10
        assert len(alerts[0]["common_reasons"]) > 0

    def test_no_drift_below_threshold(self, health_db):
        from ingestion.drift_detector import detect_schema_drift

        now = datetime.now(timezone.utc).isoformat()
        # 99 mapped, 1 rejected = 1% (below 5% threshold)
        for i in range(99):
            _insert_staging_event(health_db, f"ok-{i}", "mapped",
                                  received_at=now, processed_at=now)
        _insert_staging_event(health_db, "rej-0", "rejected",
                              received_at=now, processed_at=now,
                              rejection_reason="Minor error")

        alerts = detect_schema_drift(health_db, failure_threshold=0.05)
        assert alerts == []

    def test_drift_per_connector_event_type(self, health_db):
        from ingestion.drift_detector import detect_schema_drift

        now = datetime.now(timezone.utc).isoformat()
        # file_drop/metric: 5 mapped, 5 rejected = 50%
        for i in range(5):
            _insert_staging_event(health_db, f"fd-ok-{i}", "mapped",
                                  connector="file_drop", event_type="metric",
                                  received_at=now, processed_at=now)
        for i in range(5):
            _insert_staging_event(health_db, f"fd-rej-{i}", "rejected",
                                  connector="file_drop", event_type="metric",
                                  received_at=now, processed_at=now,
                                  rejection_reason="Schema mismatch")
        # webhook/alert: 10 mapped, 0 rejected = 0%
        for i in range(10):
            _insert_staging_event(health_db, f"wh-ok-{i}", "mapped",
                                  connector="webhook", event_type="alert",
                                  received_at=now, processed_at=now)

        alerts = detect_schema_drift(health_db)
        assert len(alerts) == 1
        assert alerts[0]["connector"] == "file_drop"
        assert alerts[0]["event_type"] == "metric"

    def test_generate_schema_drift_alerts(self, health_db):
        from ingestion.drift_detector import generate_schema_drift_alerts

        now = datetime.now(timezone.utc).isoformat()
        for i in range(5):
            _insert_staging_event(health_db, f"ok-{i}", "mapped",
                                  received_at=now, processed_at=now)
        for i in range(5):
            _insert_staging_event(health_db, f"rej-{i}", "rejected",
                                  received_at=now, processed_at=now,
                                  rejection_reason="Parse error: unknown field")

        count = generate_schema_drift_alerts(health_db)
        assert count == 1

        # Check alert was written to alerts table
        alert = health_db.execute(
            "SELECT * FROM alerts WHERE alert_type = 'schema_drift'"
        ).fetchone()
        assert alert is not None
        assert "file_drop" in alert["description"]
        assert alert["resolved"] == 0

    def test_no_duplicate_drift_alerts(self, health_db):
        from ingestion.drift_detector import generate_schema_drift_alerts

        now = datetime.now(timezone.utc).isoformat()
        for i in range(5):
            _insert_staging_event(health_db, f"ok-{i}", "mapped",
                                  received_at=now, processed_at=now)
        for i in range(5):
            _insert_staging_event(health_db, f"rej-{i}", "rejected",
                                  received_at=now, processed_at=now,
                                  rejection_reason="Error")

        # Generate first time
        count1 = generate_schema_drift_alerts(health_db)
        assert count1 == 1
        # Generate again — should not create duplicate
        count2 = generate_schema_drift_alerts(health_db)
        assert count2 == 0


# ═══════════════════════════════════════════════════════════════════════════
# ROUTE ACCESS CONTROL TESTS
# ═══════════════════════════════════════════════════════════════════════════

class TestRouteAccessControl:
    """Test that ingestion pages redirect when not in live mode."""

    def test_health_redirects_in_mock_mode(self, test_client):
        import data_source as ds
        original = ds.DATA_SOURCE
        ds.DATA_SOURCE = "mock"
        try:
            resp = test_client.get("/ingestion/health")
            assert resp.status_code == 302
            assert "/" in resp.headers["Location"]
        finally:
            ds.DATA_SOURCE = original

    def test_dead_letter_redirects_in_mock_mode(self, test_client):
        import data_source as ds
        original = ds.DATA_SOURCE
        ds.DATA_SOURCE = "mock"
        try:
            resp = test_client.get("/ingestion/dead-letter")
            assert resp.status_code == 302
            assert "/" in resp.headers["Location"]
        finally:
            ds.DATA_SOURCE = original

    def test_reprocess_forbidden_in_mock_mode(self, test_client):
        import data_source as ds
        original = ds.DATA_SOURCE
        ds.DATA_SOURCE = "mock"
        try:
            resp = test_client.post("/ingestion/reprocess",
                                    data={"event_id": "test"})
            assert resp.status_code == 403
        finally:
            ds.DATA_SOURCE = original

    def test_health_accessible_in_live_mode(self, test_client):
        import data_source as ds
        original = ds.DATA_SOURCE
        ds.DATA_SOURCE = "live"
        try:
            resp = test_client.get("/ingestion/health")
            assert resp.status_code == 200
            assert b"Ingestion Pipeline Health" in resp.data
        finally:
            ds.DATA_SOURCE = original

    def test_dead_letter_accessible_in_live_mode(self, test_client):
        import data_source as ds
        original = ds.DATA_SOURCE
        ds.DATA_SOURCE = "live"
        try:
            resp = test_client.get("/ingestion/dead-letter")
            assert resp.status_code == 200
            assert b"Dead Letter Queue" in resp.data
        finally:
            ds.DATA_SOURCE = original


# ═══════════════════════════════════════════════════════════════════════════
# INTEGRATION TESTS: ROUTES WITH DATA
# ═══════════════════════════════════════════════════════════════════════════

class TestHealthPageWithData:
    """Test the health page renders with real data."""

    def test_health_shows_stats(self, test_client):
        import data_source as ds
        import app as app_module

        original = ds.DATA_SOURCE
        ds.DATA_SOURCE = "live"
        try:
            # Insert test data into the app's DB
            db = sqlite3.connect(app_module.DB_PATH)
            db.row_factory = sqlite3.Row
            now = datetime.now(timezone.utc).isoformat()
            db.execute(
                """INSERT INTO staging_events
                   (event_id, source_connector, source_entity_ref, event_type,
                    timestamp, received_at, mapping_version, payload, processing_status, processed_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                ("test-evt-1", "file_drop", "ref", "metric", now, now, "1",
                 '{"value": 1}', "mapped", now),
            )
            db.commit()
            db.close()

            resp = test_client.get("/ingestion/health")
            assert resp.status_code == 200
            assert b"Processed (24h)" in resp.data
            assert b"Rejection Rate" in resp.data
        finally:
            ds.DATA_SOURCE = original

    def test_dead_letter_shows_rejected(self, test_client):
        import data_source as ds
        import app as app_module

        original = ds.DATA_SOURCE
        ds.DATA_SOURCE = "live"
        try:
            db = sqlite3.connect(app_module.DB_PATH)
            db.row_factory = sqlite3.Row
            now = datetime.now(timezone.utc).isoformat()
            db.execute(
                """INSERT INTO staging_events
                   (event_id, source_connector, source_entity_ref, event_type,
                    timestamp, received_at, mapping_version, payload, processing_status,
                    rejection_reason, processed_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                ("rej-page-1", "file_drop", "ref", "metric", now, now, "1",
                 '{"value": 1}', "rejected", "No matching mapping", now),
            )
            db.commit()
            db.close()

            resp = test_client.get("/ingestion/dead-letter")
            assert resp.status_code == 200
            assert b"No matching mapping" in resp.data
            assert b"rej-page-1" in resp.data or b"rej-page-1..."[:12].encode() in resp.data
        finally:
            ds.DATA_SOURCE = original

    def test_reprocess_action(self, test_client):
        import data_source as ds
        import app as app_module

        original = ds.DATA_SOURCE
        ds.DATA_SOURCE = "live"
        try:
            db = sqlite3.connect(app_module.DB_PATH)
            db.row_factory = sqlite3.Row
            now = datetime.now(timezone.utc).isoformat()
            db.execute(
                """INSERT INTO staging_events
                   (event_id, source_connector, source_entity_ref, event_type,
                    timestamp, received_at, mapping_version, payload, processing_status,
                    rejection_reason, processed_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                ("rej-reprocess-1", "file_drop", "ref", "metric", now, now, "1",
                 '{"value": 1}', "rejected", "Error", now),
            )
            db.commit()
            db.close()

            resp = test_client.post("/ingestion/reprocess",
                                    data={"event_id": "rej-reprocess-1"},
                                    follow_redirects=True)
            assert resp.status_code == 200

            # Verify status changed
            db = sqlite3.connect(app_module.DB_PATH)
            db.row_factory = sqlite3.Row
            row = db.execute(
                "SELECT processing_status FROM staging_events WHERE event_id = ?",
                ("rej-reprocess-1",),
            ).fetchone()
            db.close()
            assert row["processing_status"] == "pending"
        finally:
            ds.DATA_SOURCE = original
