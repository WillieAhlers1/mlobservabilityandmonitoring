"""Tests for LLM providers."""

import pytest
from agentic.llm import (
    MockProvider, LLMMessage, LLMResponse, ToolCall,
    create_provider, BaseLLMProvider,
)


class TestMockProvider:
    """Test the mock LLM provider."""

    def setup_method(self):
        self.provider = MockProvider({"provider": "mock"})
        self.tools = [
            {"type": "function", "function": {"name": "list_entities", "description": "List entities", "parameters": {}}},
            {"type": "function", "function": {"name": "query_metrics", "description": "Query metrics", "parameters": {}}},
            {"type": "function", "function": {"name": "query_alerts", "description": "Query alerts", "parameters": {}}},
            {"type": "function", "function": {"name": "get_summary", "description": "Get summary", "parameters": {}}},
            {"type": "function", "function": {"name": "get_industry_info", "description": "Get industry", "parameters": {}}},
            {"type": "function", "function": {"name": "switch_industry", "description": "Switch industry", "parameters": {}}},
            {"type": "function", "function": {"name": "query_drift", "description": "Drift", "parameters": {}}},
            {"type": "function", "function": {"name": "compare_entities", "description": "Compare", "parameters": {}}},
            {"type": "function", "function": {"name": "explain_lineage", "description": "Lineage", "parameters": {}}},
            {"type": "function", "function": {"name": "get_projects", "description": "Projects", "parameters": {}}},
        ]

    def test_default_response_without_tools(self):
        msgs = [LLMMessage(role="user", content="Hello")]
        resp = self.provider.complete(msgs)
        assert resp.content is not None
        assert resp.finish_reason == "stop"
        assert resp.tool_calls == []

    def test_list_entities_trigger(self):
        msgs = [LLMMessage(role="user", content="How many models are there?")]
        resp = self.provider.complete(msgs, self.tools)
        assert len(resp.tool_calls) == 1
        assert resp.tool_calls[0].name == "list_entities"

    def test_query_metrics_trigger(self):
        msgs = [LLMMessage(role="user", content="Show me performance metrics")]
        resp = self.provider.complete(msgs, self.tools)
        assert len(resp.tool_calls) == 1
        assert resp.tool_calls[0].name == "query_metrics"

    def test_query_alerts_trigger(self):
        msgs = [LLMMessage(role="user", content="What alerts are active?")]
        resp = self.provider.complete(msgs, self.tools)
        assert len(resp.tool_calls) == 1
        assert resp.tool_calls[0].name == "query_alerts"

    def test_summary_trigger(self):
        msgs = [LLMMessage(role="user", content="Give me a platform overview")]
        resp = self.provider.complete(msgs, self.tools)
        assert len(resp.tool_calls) == 1
        assert resp.tool_calls[0].name == "get_summary"

    def test_industry_info_trigger(self):
        msgs = [LLMMessage(role="user", content="What industry am I viewing?")]
        resp = self.provider.complete(msgs, self.tools)
        assert len(resp.tool_calls) == 1
        assert resp.tool_calls[0].name == "get_industry_info"

    def test_switch_industry_trigger(self):
        msgs = [LLMMessage(role="user", content="Switch to retail")]
        resp = self.provider.complete(msgs, self.tools)
        assert len(resp.tool_calls) == 1
        assert resp.tool_calls[0].name == "switch_industry"
        assert resp.tool_calls[0].arguments["industry_id"] == "retail"

    def test_drift_trigger(self):
        msgs = [LLMMessage(role="user", content="Check drift status")]
        resp = self.provider.complete(msgs, self.tools)
        assert len(resp.tool_calls) == 1
        assert resp.tool_calls[0].name == "query_drift"

    def test_compare_trigger(self):
        msgs = [LLMMessage(role="user", content="Compare model A and B")]
        resp = self.provider.complete(msgs, self.tools)
        assert len(resp.tool_calls) == 1
        assert resp.tool_calls[0].name == "compare_entities"

    def test_lineage_trigger(self):
        msgs = [LLMMessage(role="user", content="Show version history")]
        resp = self.provider.complete(msgs, self.tools)
        assert len(resp.tool_calls) == 1
        assert resp.tool_calls[0].name == "explain_lineage"

    def test_projects_trigger(self):
        msgs = [LLMMessage(role="user", content="Show me the project catalog")]
        resp = self.provider.complete(msgs, self.tools)
        assert len(resp.tool_calls) == 1
        assert resp.tool_calls[0].name == "get_projects"

    def test_tool_result_synthesis(self):
        """When tool results are present, provider synthesizes a response."""
        msgs = [
            LLMMessage(role="user", content="Show alerts"),
            LLMMessage(role="tool", content='{"data": []}', tool_call_id="tc1", name="query_alerts"),
        ]
        resp = self.provider.complete(msgs, self.tools)
        assert resp.content is not None
        assert "data retrieved" in resp.content.lower() or "found" in resp.content.lower()


class TestCreateProvider:
    """Test the provider factory."""

    def test_create_mock(self):
        p = create_provider({"provider": "mock"})
        assert isinstance(p, MockProvider)

    def test_create_unknown_raises(self):
        with pytest.raises(ValueError, match="Unknown LLM provider"):
            create_provider({"provider": "nonexistent"})

    def test_create_openai_without_key_raises(self):
        """OpenAI provider requires API key env var."""
        with pytest.raises((ValueError, ImportError)):
            create_provider({"provider": "openai", "api_key_env": "FAKE_KEY_NOT_SET_XYZ"})
