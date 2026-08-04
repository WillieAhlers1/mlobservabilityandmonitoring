"""End-to-end tests for the chat interface with live data source mode."""

import pytest
import data_source


@pytest.fixture(autouse=True)
def live_mode(monkeypatch):
    monkeypatch.setattr(data_source, "DATA_SOURCE", "live")


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test_live.db")
    import app as app_module
    original_path = app_module.DB_PATH
    app_module.DB_PATH = db_path
    app_module.init_db()
    app_module.app.config["TESTING"] = True

    from config_loader import config
    config.agentic["enabled"] = True

    import routes.chat as chat_module
    chat_module._orchestrator = None

    # Also patch data_source.DB_PATH so live queries hit the test DB
    monkeypatch.setattr(data_source, "DB_PATH", db_path)

    with app_module.app.test_client() as c:
        with app_module.app.app_context():
            yield c

    app_module.DB_PATH = original_path
    chat_module._orchestrator = None


class TestLiveDataMode:
    """Tests that verify agentic behavior with live data source."""

    def test_no_industry_tools(self, client):
        """In live mode, industry tools should not be available."""
        resp = client.post("/api/chat", json={"message": "What industry am I viewing?", "session_id": "live-1"})
        data = resp.get_json()
        # Should NOT call get_industry_info (not registered)
        tool_names = [tc["tool"] for tc in data["tool_calls"]]
        assert "get_industry_info" not in tool_names
        assert "switch_industry" not in tool_names

    def test_list_entities_live(self, client):
        """List entities in live mode (may return empty from test DB)."""
        resp = client.post("/api/chat", json={"message": "Show me all models", "session_id": "live-2"})
        data = resp.get_json()
        assert any(tc["tool"] == "list_entities" for tc in data["tool_calls"])

    def test_alerts_live(self, client):
        resp = client.post("/api/chat", json={"message": "Show active alerts", "session_id": "live-3"})
        data = resp.get_json()
        assert any(tc["tool"] == "query_alerts" for tc in data["tool_calls"])

    def test_summary_live(self, client):
        resp = client.post("/api/chat", json={"message": "Platform overview", "session_id": "live-4"})
        data = resp.get_json()
        assert any(tc["tool"] == "get_summary" for tc in data["tool_calls"])

    def test_core_tools_work(self, client):
        """Verify basic chat works in live mode without errors."""
        resp = client.post("/api/chat", json={"message": "Hello", "session_id": "live-5"})
        assert resp.status_code == 200
        data = resp.get_json()
        assert "response" in data
        assert data["response"] is not None
