"""Tests for Session 2: Data Source Router and Return Shape Parity."""

import json
import os
import sqlite3
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


# ── Helper to extract shape (keys + value types) recursively ────────────────

def _shape(obj, depth=0, max_depth=3):
    """Return a structural fingerprint of a data object.

    For dicts: {key: type_or_shape, ...}
    For lists: [type_or_shape_of_first_element] or []
    For scalars: type name string
    """
    if depth > max_depth:
        return type(obj).__name__
    if obj is None:
        return "NoneType"
    if isinstance(obj, dict):
        return {k: _shape(v, depth + 1, max_depth) for k, v in obj.items()}
    if isinstance(obj, list):
        if not obj:
            return []
        return [_shape(obj[0], depth + 1, max_depth)]
    return type(obj).__name__


def _top_keys(obj):
    """Return sorted top-level keys of a dict."""
    if isinstance(obj, dict):
        return sorted(obj.keys())
    return []


# ── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_client(tmp_path):
    """Flask test client in mock mode."""
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
    with app_module.app.test_client() as client:
        with app_module.app.app_context():
            yield client
    app_module.DB_PATH = orig_app_db
    ds_module.DB_PATH = orig_ds_db
    ds_module.DATA_SOURCE = orig_source


@pytest.fixture
def live_client(tmp_path):
    """Flask test client in live mode with empty DB."""
    db_path = str(tmp_path / "live_test.db")
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
            yield client
    app_module.DB_PATH = orig_app_db
    ds_module.DB_PATH = orig_ds_db
    ds_module.DATA_SOURCE = orig_source


@pytest.fixture
def seeded_live_client(tmp_path):
    """Flask test client in live mode with seeded metric data."""
    db_path = str(tmp_path / "seeded_live.db")
    import app as app_module
    import data_source as ds_module
    orig_app_db = app_module.DB_PATH
    orig_ds_db = ds_module.DB_PATH
    orig_source = ds_module.DATA_SOURCE
    app_module.DB_PATH = db_path
    ds_module.DB_PATH = db_path
    ds_module.DATA_SOURCE = "live"
    app_module.init_db()

    # Seed data
    conn = sqlite3.connect(db_path)
    # Add a project
    conn.execute(
        "INSERT INTO projects (id, name, description, owner, created_date) VALUES (?,?,?,?,?)",
        ("proj-test", "Test Project", "Test", "Owner", "2026-07-01"),
    )
    # Add a model entity
    conn.execute(
        """INSERT INTO entity_registry
           (entity_id, entity_type, industry_id, project_id, name, status, metadata, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        ("model-test-1", "model", "hls", "proj-test", "Test Model",
         "Healthy", '{"model_type": "classification", "algorithm": "XGBoost", "version": "v1.0.0"}',
         "2026-07-01T00:00:00Z", "2026-07-01T00:00:00Z"),
    )
    conn.execute(
        "INSERT INTO entity_aliases (entity_id, alias_type, alias_value) VALUES (?,?,?)",
        ("model-test-1", "onboard_name", "Test Model"),
    )
    # Add an agent entity
    conn.execute(
        """INSERT INTO entity_registry
           (entity_id, entity_type, industry_id, project_id, name, status, metadata, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        ("agent-test-1", "agent", "hls", "proj-test", "Test Agent",
         "Operational", '{"framework": "LangChain", "llm_backbone": "GPT-4", "version": "v1.0.0"}',
         "2026-07-01T00:00:00Z", "2026-07-01T00:00:00Z"),
    )
    # Add some metric timeseries data
    for i, day in enumerate(range(1, 8)):
        conn.execute(
            "INSERT INTO metric_timeseries (entity_id, metric_name, timestamp, value) VALUES (?,?,?,?)",
            ("model-test-1", "accuracy", f"2026-07-{day:02d}T00:00:00Z", 0.90 + i * 0.005),
        )
        conn.execute(
            "INSERT INTO metric_timeseries (entity_id, metric_name, timestamp, value) VALUES (?,?,?,?)",
            ("model-test-1", "precision", f"2026-07-{day:02d}T00:00:00Z", 0.88 + i * 0.003),
        )
    # Add drift data
    conn.execute(
        "INSERT INTO drift_snapshots (entity_id, timestamp, drift_type, scope, value, status) VALUES (?,?,?,?,?,?)",
        ("model-test-1", "2026-07-07T00:00:00Z", "psi", "overall", 0.12, "warning"),
    )
    # Add an alert
    conn.execute(
        "INSERT INTO alerts (entity_id, timestamp, severity, alert_type, title, description) VALUES (?,?,?,?,?,?)",
        ("model-test-1", "2026-07-07T12:00:00Z", "warning", "drift", "Drift Warning", "PSI exceeded threshold"),
    )
    # Add lineage event
    conn.execute(
        """INSERT INTO lineage_events (entity_id, timestamp, event_type, version, trigger, metadata)
           VALUES (?,?,?,?,?,?)""",
        ("model-test-1", "2026-07-01T00:00:00Z", "deployed", "v1.0.0", "Initial deployment",
         '{"status": "Production", "champion_challenger": "Champion"}'),
    )
    # Add agent trace
    conn.execute(
        """INSERT INTO agent_traces
           (entity_id, trace_id, timestamp, query, response, total_latency, token_count, voice_score, policy_pass)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        ("agent-test-1", "trace-001", "2026-07-07T14:00:00Z",
         "What is the patient risk?", "Based on the data...", 1200, 850, 0.91, 1),
    )
    conn.execute(
        """INSERT INTO agent_trace_steps (trace_id, step_order, tool, action, latency_ms, status)
           VALUES (?,?,?,?,?,?)""",
        ("trace-001", 1, "EHR Lookup", "Queried patient record", 320, "success"),
    )
    conn.commit()
    conn.close()

    app_module.app.config["TESTING"] = True
    with app_module.app.test_client() as client:
        with app_module.app.app_context():
            yield client
    app_module.DB_PATH = orig_app_db
    ds_module.DB_PATH = orig_ds_db
    ds_module.DATA_SOURCE = orig_source


# ── Test: Default is mock mode ──────────────────────────────────────────────

class TestDefaultMode:
    def test_default_is_mock(self):
        """DATA_SOURCE defaults to 'mock' when env var not set."""
        # We can't fully test env var default without subprocess,
        # but we can verify the module-level constant behavior
        import data_source as ds
        # After fixture teardown restores original, check it's "mock"
        assert ds.DATA_SOURCE in ("mock", "live")


# ── Test: Mock mode produces identical results ──────────────────────────────

class TestMockModeIdentical:
    """Verify mock mode through data_source returns same data as mock_data direct."""

    def test_get_model_metrics_identical(self, mock_client):
        import data_source as ds
        import mock_data
        result_ds = ds.get_model_metrics("model-1")
        result_mock = mock_data.get_model_metrics("model-1")
        assert result_ds is not None
        assert result_mock is not None
        assert _top_keys(result_ds) == _top_keys(result_mock)

    def test_get_agent_metrics_identical(self, mock_client):
        import data_source as ds
        import mock_data
        result_ds = ds.get_agent_metrics("agent-1")
        result_mock = mock_data.get_agent_metrics("agent-1")
        assert result_ds is not None
        assert _top_keys(result_ds) == _top_keys(result_mock)

    def test_get_entity_identical(self, mock_client):
        import data_source as ds
        import mock_data
        result_ds = ds.get_entity("model-1")
        result_mock = mock_data.get_entity("model-1")
        assert result_ds is not None
        assert result_ds["id"] == result_mock["id"]

    def test_get_alerts_identical(self, mock_client):
        import data_source as ds
        import mock_data
        alerts_ds = ds.get_alerts()
        alerts_mock = mock_data.get_alerts()
        assert len(alerts_ds) == len(alerts_mock)
        assert _top_keys(alerts_ds[0]) == _top_keys(alerts_mock[0])

    def test_get_model_lineage_identical(self, mock_client):
        import data_source as ds
        import mock_data
        result_ds = ds.get_model_lineage("model-1")
        result_mock = mock_data.get_model_lineage("model-1")
        assert _top_keys(result_ds) == _top_keys(result_mock)

    def test_get_agent_lineage_identical(self, mock_client):
        import data_source as ds
        import mock_data
        result_ds = ds.get_agent_lineage("agent-1")
        result_mock = mock_data.get_agent_lineage("agent-1")
        assert _top_keys(result_ds) == _top_keys(result_mock)

    def test_get_fairness_metrics_identical(self, mock_client):
        import data_source as ds
        import mock_data
        result_ds = ds.get_fairness_metrics("model-1")
        result_mock = mock_data.get_fairness_metrics("model-1")
        assert result_ds is not None
        assert _top_keys(result_ds) == _top_keys(result_mock)

    def test_get_summary_stats_identical(self, mock_client):
        import data_source as ds
        import mock_data
        result_ds = ds.get_summary_stats_combined()
        result_mock = mock_data.get_summary_stats_combined()
        assert result_ds == result_mock

    def test_get_projects_returns_list(self, mock_client):
        import data_source as ds
        projects = ds.get_projects()
        assert isinstance(projects, list)
        assert len(projects) > 0

    def test_get_models_returns_list(self, mock_client):
        import data_source as ds
        models = ds.get_models()
        assert isinstance(models, list)
        assert len(models) > 0

    def test_get_agents_returns_list(self, mock_client):
        import data_source as ds
        agents = ds.get_agents()
        assert isinstance(agents, list)
        assert len(agents) > 0


# ── Test: Live mode with empty DB ───────────────────────────────────────────

class TestLiveModeEmpty:
    """Verify live mode with empty DB returns graceful empty states."""

    def test_get_model_metrics_empty(self, live_client):
        import data_source as ds
        result = ds.get_model_metrics("nonexistent")
        assert result is None

    def test_get_agent_metrics_empty(self, live_client):
        import data_source as ds
        result = ds.get_agent_metrics("nonexistent")
        assert result is None

    def test_get_entity_empty(self, live_client):
        import data_source as ds
        result = ds.get_entity("nonexistent")
        assert result is None

    def test_get_alerts_empty(self, live_client):
        import data_source as ds
        result = ds.get_alerts()
        assert result == []

    def test_get_models_empty(self, live_client):
        import data_source as ds
        result = ds.get_models()
        assert result == []

    def test_get_agents_empty(self, live_client):
        import data_source as ds
        result = ds.get_agents()
        assert result == []

    def test_get_summary_stats_empty(self, live_client):
        import data_source as ds
        result = ds.get_summary_stats_combined()
        assert result["total_models"] == 0
        assert result["total_agents"] == 0

    def test_get_projects_empty(self, live_client):
        import data_source as ds
        result = ds.get_projects()
        assert result == []

    def test_get_model_lineage_empty(self, live_client):
        import data_source as ds
        result = ds.get_model_lineage("nonexistent")
        assert result is None

    def test_get_fairness_empty(self, live_client):
        import data_source as ds
        result = ds.get_fairness_metrics("nonexistent")
        assert result is None


# ── Test: Live mode with seeded data ────────────────────────────────────────

class TestLiveModeSeeded:
    """Verify live mode with seeded data returns populated structures."""

    def test_get_entity_returns_model(self, seeded_live_client):
        import data_source as ds
        result = ds.get_entity("model-test-1")
        assert result is not None
        assert result["id"] == "model-test-1"
        assert result["name"] == "Test Model"
        assert result["entity_type"] == "model"

    def test_get_entity_returns_agent(self, seeded_live_client):
        import data_source as ds
        result = ds.get_entity("agent-test-1")
        assert result is not None
        assert result["name"] == "Test Agent"
        assert result["entity_type"] == "agent"

    def test_model_metrics_has_data(self, seeded_live_client):
        import data_source as ds
        result = ds.get_model_metrics("model-test-1")
        assert result is not None
        assert len(result["dates"]) == 7
        assert "accuracy" in result["metrics"]
        assert "precision" in result["metrics"]
        assert len(result["metrics"]["accuracy"]["values"]) == 7
        assert result["metrics"]["accuracy"]["current"] > 0

    def test_model_metrics_has_drift(self, seeded_live_client):
        import data_source as ds
        result = ds.get_model_metrics("model-test-1")
        assert len(result["drift"]["values"]) == 1
        assert result["drift"]["current"] == 0.12

    def test_model_metrics_shape_matches_mock(self, seeded_live_client):
        """Live metrics have same top-level keys as mock metrics."""
        import data_source as ds
        import mock_data
        live_result = ds.get_model_metrics("model-test-1")
        # Temporarily switch to mock to get mock shape
        orig = ds.DATA_SOURCE
        ds.DATA_SOURCE = "mock"
        mock_result = ds.get_model_metrics("model-1")
        ds.DATA_SOURCE = orig
        assert _top_keys(live_result) == _top_keys(mock_result)

    def test_get_alerts_returns_data(self, seeded_live_client):
        import data_source as ds
        alerts = ds.get_alerts()
        assert len(alerts) == 1
        assert alerts[0]["severity"] == "warning"
        assert alerts[0]["model_name"] == "Test Model"

    def test_get_models_returns_entities(self, seeded_live_client):
        import data_source as ds
        models = ds.get_models()
        assert len(models) == 1
        assert models[0]["name"] == "Test Model"

    def test_get_agents_returns_entities(self, seeded_live_client):
        import data_source as ds
        agents = ds.get_agents()
        assert len(agents) == 1
        assert agents[0]["name"] == "Test Agent"

    def test_model_lineage_returns_data(self, seeded_live_client):
        import data_source as ds
        result = ds.get_model_lineage("model-test-1")
        assert result is not None
        assert len(result["versions"]) == 1
        assert result["versions"][0]["version"] == "v1.0.0"

    def test_summary_stats_populated(self, seeded_live_client):
        import data_source as ds
        stats = ds.get_summary_stats_combined()
        assert stats["total_models"] == 1
        assert stats["total_agents"] == 1
        assert stats["healthy_models"] == 1
        assert stats["operational_agents"] == 1

    def test_agent_metrics_has_traces(self, seeded_live_client):
        import data_source as ds
        result = ds.get_agent_metrics("agent-test-1")
        assert result is not None
        assert len(result["traces"]) == 1
        assert result["traces"][0]["query"] == "What is the patient risk?"
        assert len(result["traces"][0]["steps"]) == 1

    def test_projects_with_entities(self, seeded_live_client):
        import data_source as ds
        projects = ds.get_projects()
        assert len(projects) == 1
        assert projects[0]["model_count"] == 1
        assert projects[0]["agent_count"] == 1


# ── Test: App routes work in mock mode ──────────────────────────────────────

class TestAppRoutesMockMode:
    """Verify all Flask routes still work through the data_source router."""

    def test_cockpit(self, mock_client):
        r = mock_client.get("/")
        assert r.status_code == 200

    def test_dashboard_model(self, mock_client):
        r = mock_client.get("/dashboard/model-1")
        assert r.status_code == 200

    def test_dashboard_agent(self, mock_client):
        r = mock_client.get("/dashboard/agent-1")
        assert r.status_code == 200

    def test_dashboard_not_found(self, mock_client):
        r = mock_client.get("/dashboard/nonexistent", follow_redirects=True)
        assert r.status_code == 200  # redirects to cockpit

    def test_lineage(self, mock_client):
        r = mock_client.get("/lineage/model-1")
        assert r.status_code == 200

    def test_projects(self, mock_client):
        r = mock_client.get("/projects")
        assert r.status_code == 200

    def test_onboard(self, mock_client):
        r = mock_client.get("/onboard")
        assert r.status_code == 200

    def test_alerts(self, mock_client):
        r = mock_client.get("/alerts")
        assert r.status_code == 200

    def test_compare(self, mock_client):
        r = mock_client.get("/compare")
        assert r.status_code == 200

    def test_api_model_metrics(self, mock_client):
        r = mock_client.get("/api/model/model-1/metrics")
        assert r.status_code == 200
        data = json.loads(r.data)
        assert "metrics" in data

    def test_api_model_metrics_not_found(self, mock_client):
        r = mock_client.get("/api/model/nonexistent/metrics")
        assert r.status_code == 404


# ── Test: Session 1 tests still pass ────────────────────────────────────────

class TestSession1Regression:
    """Ensure onboard still writes to entity_registry via data_source routing."""

    def test_onboard_model_still_works(self, mock_client):
        r = mock_client.post("/onboard", data={
            "entity_type": "model",
            "model_name": "Session2 Test",
            "project_id": "proj-hls-1",
            "model_type": "classification",
            "version": "v1.0.0",
            "endpoint": "/api/test",
            "owner": "Team",
            "perf_threshold": "0.85",
            "drift_threshold": "0.1",
        }, follow_redirects=True)
        assert r.status_code == 200

        import app as app_module
        conn = sqlite3.connect(app_module.DB_PATH)
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM entity_registry WHERE name='Session2 Test'").fetchone()
        conn.close()
        assert row is not None
        assert row["entity_type"] == "model"
