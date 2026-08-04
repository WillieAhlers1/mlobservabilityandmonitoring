"""End-to-end tests for the chat interface with mock data source mode."""

import pytest
import data_source


@pytest.fixture(autouse=True)
def mock_mode(monkeypatch):
    monkeypatch.setattr(data_source, "DATA_SOURCE", "mock")


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test_mock.db")
    import app as app_module
    original_path = app_module.DB_PATH
    app_module.DB_PATH = db_path
    app_module.init_db()
    app_module.app.config["TESTING"] = True

    from config_loader import config
    config.agentic["enabled"] = True

    import routes.chat as chat_module
    chat_module._orchestrator = None

    with app_module.app.test_client() as c:
        with app_module.app.app_context():
            yield c

    app_module.DB_PATH = original_path
    chat_module._orchestrator = None


class TestMockDataMode:
    """Tests that verify agentic behavior with mock data source."""

    def test_list_entities_returns_mock_data(self, client):
        resp = client.post("/api/chat", json={"message": "Show me all models", "session_id": "mock-1"})
        data = resp.get_json()
        assert data["tool_calls"][0]["tool"] == "list_entities"
        assert data["response"]  # Should have content

    def test_industry_awareness(self, client):
        resp = client.post("/api/chat", json={"message": "What industry am I viewing?", "session_id": "mock-2"})
        data = resp.get_json()
        assert any(tc["tool"] == "get_industry_info" for tc in data["tool_calls"])

    def test_switch_industry(self, client):
        resp = client.post("/api/chat", json={"message": "Switch to retail", "session_id": "mock-3"})
        data = resp.get_json()
        assert any(tc["tool"] == "switch_industry" for tc in data["tool_calls"])
        # Verify it actually switched
        assert data_source.get_current_industry() == "retail"
        # Switch back
        data_source.set_industry("hls")

    def test_alerts_in_mock_mode(self, client):
        resp = client.post("/api/chat", json={"message": "What alerts are active?", "session_id": "mock-4"})
        data = resp.get_json()
        assert any(tc["tool"] == "query_alerts" for tc in data["tool_calls"])

    def test_platform_summary(self, client):
        resp = client.post("/api/chat", json={"message": "Give me the platform status", "session_id": "mock-5"})
        data = resp.get_json()
        assert any(tc["tool"] == "get_summary" for tc in data["tool_calls"])

    def test_multi_turn_conversation(self, client):
        sid = "mock-multi"
        client.post("/api/chat", json={"message": "Hello", "session_id": sid})
        client.post("/api/chat", json={"message": "Show models", "session_id": sid})
        resp = client.get(f"/api/chat/history?session_id={sid}")
        history = resp.get_json()["history"]
        assert len(history) >= 4  # 2 user + 2 assistant turns
