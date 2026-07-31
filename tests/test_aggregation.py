"""Tests for Session 5: Aggregation Engine and Time Bucketing."""

import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from ingestion.aggregation import (
    aggregate_after_mapping,
    aggregate_bucket,
    aggregate_entity_metric,
    compute_bucket_start,
    is_within_grace_period,
    reaggregate_bucket,
    upsert_aggregate,
)


@pytest.fixture
def agg_db(tmp_path):
    """Create a temp DB with full schema and seed some raw metric rows."""
    db_path = str(tmp_path / "agg_test.db")
    import app as app_module
    original_path = app_module.DB_PATH
    app_module.DB_PATH = db_path
    app_module.init_db()
    app_module.DB_PATH = original_path

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Register an entity
    conn.execute(
        """INSERT INTO entity_registry
           (entity_id, entity_type, industry_id, project_id, name, status, metadata, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        ("model-agg-001", "model", "hls", "proj-1", "Agg Test Model", "Healthy",
         '{}', "2026-07-01T00:00:00Z", "2026-07-01T00:00:00Z"),
    )
    conn.commit()
    yield conn
    conn.close()


def _seed_metrics(db, entity_id="model-agg-001", metric_name="accuracy",
                  start_hour=10, count=10, base_value=0.90, increment=0.005,
                  date="2026-07-30"):
    """Seed raw metric rows within a single hour."""
    for i in range(count):
        minute = i * (60 // max(count, 1))
        ts = f"{date}T{start_hour:02d}:{minute:02d}:00Z"
        value = base_value + i * increment
        db.execute(
            "INSERT INTO metric_timeseries (entity_id, metric_name, timestamp, value) VALUES (?,?,?,?)",
            (entity_id, metric_name, ts, round(value, 4)),
        )
    db.commit()


def _seed_24h_metrics(db, entity_id="model-agg-001", metric_name="accuracy",
                      date="2026-07-30", base=0.90):
    """Seed one metric row per hour for 24 hours."""
    for hour in range(24):
        ts = f"{date}T{hour:02d}:30:00Z"
        value = base + hour * 0.001
        db.execute(
            "INSERT INTO metric_timeseries (entity_id, metric_name, timestamp, value) VALUES (?,?,?,?)",
            (entity_id, metric_name, ts, round(value, 4)),
        )
    db.commit()


# ── Test: Bucket Start Computation ─────────────────────────────────────────

class TestComputeBucketStart:

    def test_1h_bucket(self):
        assert compute_bucket_start("2026-07-30T14:35:00Z", "1h") == "2026-07-30T14:00:00Z"

    def test_1h_bucket_exact(self):
        assert compute_bucket_start("2026-07-30T14:00:00Z", "1h") == "2026-07-30T14:00:00Z"

    def test_1d_bucket(self):
        assert compute_bucket_start("2026-07-30T14:35:00Z", "1d") == "2026-07-30T00:00:00Z"

    def test_1d_bucket_midnight(self):
        assert compute_bucket_start("2026-07-30T00:00:00Z", "1d") == "2026-07-30T00:00:00Z"


# ── Test: Aggregation Methods ───────────────────────────────────────────────

class TestAggregateBucket:

    def test_last_method(self, agg_db):
        """10 rows in same hour, last method returns final value."""
        _seed_metrics(agg_db, start_hour=14, count=10, base_value=0.90, increment=0.005)
        result = aggregate_bucket(agg_db, "model-agg-001", "accuracy",
                                  "2026-07-30T14:00:00Z", "1h", "last")
        assert result is not None
        assert result["sample_count"] == 10
        # Last value: 0.90 + 9*0.005 = 0.945
        assert abs(result["value"] - 0.945) < 0.001

    def test_mean_method(self, agg_db):
        """Mean of 10 sequential values."""
        _seed_metrics(agg_db, start_hour=14, count=10, base_value=0.90, increment=0.01)
        result = aggregate_bucket(agg_db, "model-agg-001", "accuracy",
                                  "2026-07-30T14:00:00Z", "1h", "mean")
        # Mean of 0.90, 0.91, ..., 0.99 = 0.945
        assert abs(result["value"] - 0.945) < 0.001

    def test_max_method(self, agg_db):
        _seed_metrics(agg_db, start_hour=14, count=5, base_value=0.80, increment=0.05)
        result = aggregate_bucket(agg_db, "model-agg-001", "accuracy",
                                  "2026-07-30T14:00:00Z", "1h", "max")
        # Max: 0.80 + 4*0.05 = 1.0
        assert abs(result["value"] - 1.0) < 0.001

    def test_min_method(self, agg_db):
        _seed_metrics(agg_db, start_hour=14, count=5, base_value=0.80, increment=0.05)
        result = aggregate_bucket(agg_db, "model-agg-001", "accuracy",
                                  "2026-07-30T14:00:00Z", "1h", "min")
        assert abs(result["value"] - 0.80) < 0.001

    def test_sum_method(self, agg_db):
        _seed_metrics(agg_db, start_hour=14, count=3, base_value=1.0, increment=0.0)
        result = aggregate_bucket(agg_db, "model-agg-001", "accuracy",
                                  "2026-07-30T14:00:00Z", "1h", "sum")
        assert abs(result["value"] - 3.0) < 0.001

    def test_empty_bucket_returns_none(self, agg_db):
        """No rows in this hour → None."""
        result = aggregate_bucket(agg_db, "model-agg-001", "accuracy",
                                  "2026-07-30T14:00:00Z", "1h", "last")
        assert result is None


# ── Test: Multiple Buckets ──────────────────────────────────────────────────

class TestMultipleBuckets:

    def test_24_hourly_buckets(self, agg_db):
        """24 hours of data → 24 aggregate rows."""
        _seed_24h_metrics(agg_db)
        written = aggregate_entity_metric(agg_db, "model-agg-001", "accuracy", "1h", "last")
        assert written == 24

        rows = agg_db.execute(
            "SELECT * FROM metric_timeseries_agg WHERE entity_id = 'model-agg-001' ORDER BY bucket_start"
        ).fetchall()
        assert len(rows) == 24

    def test_daily_bucket(self, agg_db):
        """24 hours of data with 1d bucket → 1 aggregate row."""
        _seed_24h_metrics(agg_db)
        written = aggregate_entity_metric(agg_db, "model-agg-001", "accuracy", "1d", "last")
        assert written == 1

        row = agg_db.execute(
            "SELECT * FROM metric_timeseries_agg WHERE bucket_size = '1d'"
        ).fetchone()
        assert row is not None
        assert row["bucket_start"] == "2026-07-30T00:00:00Z"
        # Last value in day: hour 23 → 0.90 + 23*0.001 = 0.923
        assert abs(row["value"] - 0.923) < 0.001

    def test_since_parameter(self, agg_db):
        """'since' limits which raw rows to consider."""
        _seed_24h_metrics(agg_db)
        # Only aggregate from hour 20 onwards
        written = aggregate_entity_metric(agg_db, "model-agg-001", "accuracy", "1h", "last",
                                           since="2026-07-30T20:00:00Z")
        assert written == 4  # hours 20, 21, 22, 23


# ── Test: Re-aggregation ───────────────────────────────────────────────────

class TestReaggregation:

    def test_reaggregate_updates_value(self, agg_db):
        """New event in existing bucket triggers value update."""
        _seed_metrics(agg_db, start_hour=14, count=5, base_value=0.90, increment=0.01)
        aggregate_entity_metric(agg_db, "model-agg-001", "accuracy", "1h", "last")

        # Verify initial agg value (last of 0.90..0.94 = 0.94)
        row = agg_db.execute(
            "SELECT value, sample_count FROM metric_timeseries_agg WHERE bucket_start = '2026-07-30T14:00:00Z'"
        ).fetchone()
        assert abs(row["value"] - 0.94) < 0.001
        assert row["sample_count"] == 5

        # Add a new row in the same bucket
        agg_db.execute(
            "INSERT INTO metric_timeseries (entity_id, metric_name, timestamp, value) VALUES (?,?,?,?)",
            ("model-agg-001", "accuracy", "2026-07-30T14:55:00Z", 0.99),
        )
        agg_db.commit()

        # Re-aggregate
        result = reaggregate_bucket(agg_db, "model-agg-001", "accuracy",
                                    "2026-07-30T14:55:00Z", "1h", "last")
        assert result is True

        row = agg_db.execute(
            "SELECT value, sample_count FROM metric_timeseries_agg WHERE bucket_start = '2026-07-30T14:00:00Z'"
        ).fetchone()
        assert abs(row["value"] - 0.99) < 0.001
        assert row["sample_count"] == 6

    def test_upsert_replaces_existing(self, agg_db):
        """upsert_aggregate replaces existing row for same bucket."""
        upsert_aggregate(agg_db, "model-agg-001", "accuracy",
                         "2026-07-30T14:00:00Z", "1h", "last", 0.90, 5)
        upsert_aggregate(agg_db, "model-agg-001", "accuracy",
                         "2026-07-30T14:00:00Z", "1h", "last", 0.95, 6)

        count = agg_db.execute(
            "SELECT COUNT(*) as cnt FROM metric_timeseries_agg WHERE bucket_start = '2026-07-30T14:00:00Z'"
        ).fetchone()["cnt"]
        assert count == 1

        row = agg_db.execute(
            "SELECT value, sample_count FROM metric_timeseries_agg WHERE bucket_start = '2026-07-30T14:00:00Z'"
        ).fetchone()
        assert row["value"] == 0.95
        assert row["sample_count"] == 6


# ── Test: Grace Period ──────────────────────────────────────────────────────

class TestGracePeriod:

    def test_recent_event_within_grace(self):
        """Event from 2 hours ago is within 6h grace."""
        ts = (datetime.now(timezone.utc) - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
        assert is_within_grace_period(ts, grace_period_hours=6) is True

    def test_old_event_outside_grace(self):
        """Event from 12 hours ago is outside 6h grace."""
        ts = (datetime.now(timezone.utc) - timedelta(hours=12)).strftime("%Y-%m-%dT%H:%M:%SZ")
        assert is_within_grace_period(ts, grace_period_hours=6) is False

    def test_event_exactly_at_boundary(self):
        """Event just inside grace boundary is within."""
        # Use 5h59m to be safely inside 6h grace (avoids sub-second timing issues)
        ts = (datetime.now(timezone.utc) - timedelta(hours=5, minutes=59)).strftime("%Y-%m-%dT%H:%M:%SZ")
        assert is_within_grace_period(ts, grace_period_hours=6) is True

    def test_aggregate_after_mapping_within_grace(self, agg_db):
        """Recent event triggers aggregation."""
        recent_ts = (datetime.now(timezone.utc) - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        # Seed a row at that time
        agg_db.execute(
            "INSERT INTO metric_timeseries (entity_id, metric_name, timestamp, value) VALUES (?,?,?,?)",
            ("model-agg-001", "accuracy", recent_ts, 0.95),
        )
        agg_db.commit()

        result = aggregate_after_mapping(agg_db, "model-agg-001", "accuracy",
                                         recent_ts, "1h", "last", grace_period_hours=6)
        assert result is True

        # Verify agg row exists
        count = agg_db.execute(
            "SELECT COUNT(*) as cnt FROM metric_timeseries_agg WHERE entity_id = 'model-agg-001'"
        ).fetchone()["cnt"]
        assert count == 1

    def test_aggregate_after_mapping_outside_grace(self, agg_db):
        """Old event does NOT trigger aggregation."""
        old_ts = (datetime.now(timezone.utc) - timedelta(hours=12)).strftime("%Y-%m-%dT%H:%M:%SZ")
        agg_db.execute(
            "INSERT INTO metric_timeseries (entity_id, metric_name, timestamp, value) VALUES (?,?,?,?)",
            ("model-agg-001", "accuracy", old_ts, 0.88),
        )
        agg_db.commit()

        result = aggregate_after_mapping(agg_db, "model-agg-001", "accuracy",
                                         old_ts, "1h", "last", grace_period_hours=6)
        assert result is False

        # No agg row written
        count = agg_db.execute(
            "SELECT COUNT(*) as cnt FROM metric_timeseries_agg WHERE entity_id = 'model-agg-001'"
        ).fetchone()["cnt"]
        assert count == 0


# ── Test: Dashboard reads from agg table ────────────────────────────────────

class TestDashboardUsesAgg:

    def test_live_mode_reads_agg(self, tmp_path):
        """data_source in live mode prefers metric_timeseries_agg."""
        db_path = str(tmp_path / "dashboard_agg.db")
        import app as app_module
        import data_source as ds_module
        orig_app_db = app_module.DB_PATH
        orig_ds_db = ds_module.DB_PATH
        orig_source = ds_module.DATA_SOURCE
        app_module.DB_PATH = db_path
        ds_module.DB_PATH = db_path
        ds_module.DATA_SOURCE = "live"
        app_module.init_db()

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        # Register entity
        conn.execute(
            """INSERT INTO entity_registry
               (entity_id, entity_type, industry_id, project_id, name, status, metadata, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            ("model-dash-1", "model", "hls", "proj-1", "Dash Model", "Healthy",
             '{"model_type": "classification"}', "2026-07-01T00:00:00Z", "2026-07-01T00:00:00Z"),
        )
        # Insert agg rows (this should be preferred over raw)
        for hour in range(5):
            conn.execute(
                """INSERT INTO metric_timeseries_agg
                   (entity_id, metric_name, bucket_start, bucket_size, agg_method, value, sample_count)
                   VALUES (?,?,?,?,?,?,?)""",
                ("model-dash-1", "accuracy", f"2026-07-30T{hour + 10:02d}:00:00Z", "1h", "last", 0.90 + hour * 0.01, 10),
            )
        conn.commit()
        conn.close()

        try:
            result = ds_module.get_model_metrics("model-dash-1")
            assert result is not None
            assert len(result["dates"]) == 5
            assert "accuracy" in result["metrics"]
            assert len(result["metrics"]["accuracy"]["values"]) == 5
            # Values should come from agg table
            assert result["metrics"]["accuracy"]["values"][0] == 0.90
        finally:
            app_module.DB_PATH = orig_app_db
            ds_module.DB_PATH = orig_ds_db
            ds_module.DATA_SOURCE = orig_source

    def test_live_mode_falls_back_to_raw(self, tmp_path):
        """When no agg data exists, falls back to raw metric_timeseries."""
        db_path = str(tmp_path / "dashboard_raw.db")
        import app as app_module
        import data_source as ds_module
        orig_app_db = app_module.DB_PATH
        orig_ds_db = ds_module.DB_PATH
        orig_source = ds_module.DATA_SOURCE
        app_module.DB_PATH = db_path
        ds_module.DB_PATH = db_path
        ds_module.DATA_SOURCE = "live"
        app_module.init_db()

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        conn.execute(
            """INSERT INTO entity_registry
               (entity_id, entity_type, industry_id, project_id, name, status, metadata, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            ("model-dash-2", "model", "hls", "proj-1", "Raw Model", "Healthy",
             '{"model_type": "classification"}', "2026-07-01T00:00:00Z", "2026-07-01T00:00:00Z"),
        )
        # Only raw rows, no agg
        for i in range(3):
            conn.execute(
                "INSERT INTO metric_timeseries (entity_id, metric_name, timestamp, value) VALUES (?,?,?,?)",
                ("model-dash-2", "precision", f"2026-07-30T{10 + i:02d}:00:00Z", 0.85 + i * 0.01),
            )
        conn.commit()
        conn.close()

        try:
            result = ds_module.get_model_metrics("model-dash-2")
            assert result is not None
            assert "precision" in result["metrics"]
            assert len(result["metrics"]["precision"]["values"]) == 3
        finally:
            app_module.DB_PATH = orig_app_db
            ds_module.DB_PATH = orig_ds_db
            ds_module.DATA_SOURCE = orig_source
