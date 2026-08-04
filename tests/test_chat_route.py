"""Tests for the chat API routes."""

import json
import pytest
import data_source


@pytest.fixture(autouse=True)
def mock_mode(monkeypatch):
    """Use mock data source."""
    monkeypatch.setattr(data_source, "DATA_SOURCE", "mock")


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Flask test client with agentic enabled."""
    db_path = str(tmp_path / "test_chat.db")
    import app as app_module
    original_path = app_module.DB_PATH
    app_module.DB_PATH = db_path
    app_module.init_db()
    app_module.app.config["TESTING"] = True

    # Ensure agentic is enabled
    from config_loader import config
    original_agentic = config.agentic.copy()
    config.agentic["enabled"] = True

    # Reset the orchestrator singleton so it picks up mock mode
    import routes.chat as chat_module
    chat_module._orchestrator = None

    with app_module.app.test_client() as c:
        with app_module.app.app_context():
            yield c

    app_module.DB_PATH = original_path
    config.agentic.update(original_agentic)
    chat_module._orchestrator = None


class TestChatEndpoint:
    def test_post_message(self, client):
        resp = client.post("/api/chat", json={"message": "Hello"})
        assert resp.status_code == 200
        data = resp.get_json()
        assert "response" in data
        assert "session_id" in data

    def test_empty_message(self, client):
        resp = client.post("/api/chat", json={"message": ""})
        assert resp.status_code == 400

    def test_no_json_body(self, client):
        resp = client.post("/api/chat", data="not json", content_type="text/plain")
        assert resp.status_code == 400

    def test_tool_call_in_response(self, client):
        resp = client.post("/api/chat", json={"message": "List all models"})
        assert resp.status_code == 200
        data = resp.get_json()
        assert "tool_calls" in data
        assert len(data["tool_calls"]) > 0

    def test_suggestions_returned(self, client):
        resp = client.post("/api/chat", json={"message": "Show alerts"})
        data = resp.get_json()
        assert "suggestions" in data
        assert len(data["suggestions"]) > 0

    def test_session_persistence(self, client):
        resp1 = client.post("/api/chat", json={"message": "Hello", "session_id": "persist-test"})
        sid = resp1.get_json()["session_id"]
        resp2 = client.post("/api/chat", json={"message": "Show models", "session_id": sid})
        assert resp2.status_code == 200

    def test_custom_session_id(self, client):
        resp = client.post("/api/chat", json={"message": "Hi", "session_id": "my-custom-id"})
        data = resp.get_json()
        assert data["session_id"] == "my-custom-id"


class TestChatHistory:
    def test_get_history(self, client):
        client.post("/api/chat", json={"message": "Hello", "session_id": "hist-1"})
        resp = client.get("/api/chat/history?session_id=hist-1")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "history" in data
        assert len(data["history"]) >= 2  # user + assistant

    def test_empty_history(self, client):
        resp = client.get("/api/chat/history?session_id=nonexistent")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["history"] == []


class TestChatClear:
    def test_clear_session(self, client):
        client.post("/api/chat", json={"message": "Hello", "session_id": "clear-1"})
        resp = client.post("/api/chat/clear", json={"session_id": "clear-1"})
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "cleared"

        # Verify history is gone
        resp2 = client.get("/api/chat/history?session_id=clear-1")
        assert resp2.get_json()["history"] == []


class TestChatDisabled:
    def test_disabled_returns_403(self, client):
        from config_loader import config
        config.agentic["enabled"] = False
        import routes.chat as chat_module
        chat_module._orchestrator = None

        resp = client.post("/api/chat", json={"message": "Hello"})
        assert resp.status_code == 403

        config.agentic["enabled"] = True
