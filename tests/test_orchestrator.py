"""Tests for the orchestrator — multi-turn, tool selection, context management."""

import pytest
import data_source
from agentic.orchestrator import (
    Orchestrator, ChatSession, SessionStore, RateLimiter, build_system_prompt,
)


@pytest.fixture(autouse=True)
def mock_mode(monkeypatch):
    """Use mock data source."""
    monkeypatch.setattr(data_source, "DATA_SOURCE", "mock")


@pytest.fixture
def orchestrator():
    return Orchestrator({"provider": "mock", "max_history_turns": 10, "rate_limit_per_minute": 60})


class TestSystemPrompt:
    def test_mock_mode_prompt(self):
        prompt = build_system_prompt("mock")
        assert "DEMO" in prompt
        assert "industry" in prompt.lower()

    def test_live_mode_prompt(self):
        prompt = build_system_prompt("live")
        assert "LIVE" in prompt
        assert "industry switching is not applicable" in prompt.lower()


class TestSessionStore:
    def test_get_or_create(self):
        store = SessionStore()
        s = store.get_or_create("test-1")
        assert isinstance(s, ChatSession)
        assert s.session_id == "test-1"

    def test_same_session_returned(self):
        store = SessionStore()
        s1 = store.get_or_create("test-1")
        s2 = store.get_or_create("test-1")
        assert s1 is s2

    def test_clear(self):
        store = SessionStore()
        store.get_or_create("test-1")
        store.clear("test-1")
        assert store.get_history("test-1") == []

    def test_trim_history(self):
        store = SessionStore(max_history_turns=2)
        session = store.get_or_create("test-1")
        from agentic.llm import LLMMessage
        for i in range(10):
            session.history.append(LLMMessage(role="user", content=f"msg {i}"))
            session.history.append(LLMMessage(role="assistant", content=f"reply {i}"))
        store.trim_history(session)
        assert len(session.history) <= 4  # 2 turns * 2 messages


class TestRateLimiter:
    def test_allows_within_limit(self):
        limiter = RateLimiter(max_per_minute=5)
        for _ in range(5):
            assert limiter.is_allowed("s1")

    def test_blocks_over_limit(self):
        limiter = RateLimiter(max_per_minute=2)
        assert limiter.is_allowed("s1")
        assert limiter.is_allowed("s1")
        assert not limiter.is_allowed("s1")

    def test_different_sessions_independent(self):
        limiter = RateLimiter(max_per_minute=1)
        assert limiter.is_allowed("s1")
        assert limiter.is_allowed("s2")
        assert not limiter.is_allowed("s1")


class TestOrchestrator:
    def test_basic_chat(self, orchestrator):
        result = orchestrator.chat("Hello", session_id="test")
        assert result["response"]
        assert result["error"] is None

    def test_empty_message(self, orchestrator):
        result = orchestrator.chat("", session_id="test")
        assert result["error"] == "empty_message"

    def test_long_message(self, orchestrator):
        result = orchestrator.chat("x" * 2001, session_id="test")
        assert result["error"] == "message_too_long"

    def test_tool_call_triggered(self, orchestrator):
        result = orchestrator.chat("Show me all models", session_id="test")
        assert len(result["tool_calls"]) > 0
        assert result["tool_calls"][0]["tool"] == "list_entities"

    def test_suggestions_generated(self, orchestrator):
        result = orchestrator.chat("Show alerts", session_id="test")
        assert len(result["suggestions"]) > 0

    def test_multi_turn_history(self, orchestrator):
        orchestrator.chat("Hello", session_id="mt")
        orchestrator.chat("Show models", session_id="mt")
        history = orchestrator.get_history("mt")
        assert len(history) == 4  # 2 user + 2 assistant

    def test_clear_session(self, orchestrator):
        orchestrator.chat("Hello", session_id="cs")
        orchestrator.clear_session("cs")
        history = orchestrator.get_history("cs")
        assert history == []

    def test_rate_limiting(self):
        o = Orchestrator({"provider": "mock", "max_history_turns": 10, "rate_limit_per_minute": 2})
        o.chat("msg1", session_id="rl")
        o.chat("msg2", session_id="rl")
        result = o.chat("msg3", session_id="rl")
        assert result["error"] == "rate_limited"

    def test_industry_tool_in_mock_mode(self, orchestrator):
        result = orchestrator.chat("What industry am I viewing?", session_id="ind")
        assert any(tc["tool"] == "get_industry_info" for tc in result["tool_calls"])

    def test_switch_industry_in_mock_mode(self, orchestrator):
        result = orchestrator.chat("Switch to retail", session_id="sw")
        assert any(tc["tool"] == "switch_industry" for tc in result["tool_calls"])


class TestOrchestratorLiveMode:
    """Test orchestrator behavior in live data mode."""

    @pytest.fixture(autouse=True)
    def set_live(self, monkeypatch):
        monkeypatch.setattr(data_source, "DATA_SOURCE", "live")

    def test_no_industry_tools_in_live(self):
        o = Orchestrator({"provider": "mock", "max_history_turns": 10, "rate_limit_per_minute": 60})
        assert "get_industry_info" not in o._registry.names
        assert "switch_industry" not in o._registry.names

    def test_core_tools_available_live(self):
        o = Orchestrator({"provider": "mock", "max_history_turns": 10, "rate_limit_per_minute": 60})
        assert "list_entities" in o._registry.names
        assert "query_alerts" in o._registry.names
