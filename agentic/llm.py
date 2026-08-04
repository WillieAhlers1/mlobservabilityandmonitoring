"""LLM provider abstraction for the agentic chat interface.

Supports multiple backends: mock (testing), openai, azure_openai, ollama.
"""

import json
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class LLMMessage:
    """A single message in a conversation."""
    role: str  # "system", "user", "assistant", "tool"
    content: str | None = None
    tool_calls: list = field(default_factory=list)
    tool_call_id: str | None = None
    name: str | None = None


@dataclass
class ToolCall:
    """A tool call requested by the LLM."""
    id: str
    name: str
    arguments: dict


@dataclass
class LLMResponse:
    """Response from the LLM."""
    content: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    finish_reason: str = "stop"


class BaseLLMProvider(ABC):
    """Abstract base class for LLM providers."""

    def __init__(self, config: dict):
        self.config = config
        self.model = config.get("model", "gpt-4o-mini")
        self.max_tokens = config.get("max_tokens", 1024)
        self.temperature = config.get("temperature", 0.2)

    @abstractmethod
    def complete(self, messages: list[LLMMessage], tools: list[dict] | None = None) -> LLMResponse:
        """Send messages to the LLM and get a response.

        Args:
            messages: Conversation history as LLMMessage objects.
            tools: Optional list of tool definitions (OpenAI function-calling format).

        Returns:
            LLMResponse with content and/or tool_calls.
        """


class MockProvider(BaseLLMProvider):
    """Mock LLM provider for testing — returns deterministic responses.

    The mock provider inspects the last user message and simulates
    tool calls or direct responses based on keyword matching.
    """

    def complete(self, messages: list[LLMMessage], tools: list[dict] | None = None) -> LLMResponse:
        last_user_msg = ""
        for msg in reversed(messages):
            if msg.role == "user":
                last_user_msg = (msg.content or "").lower()
                break

        # If this is a follow-up after tool results, synthesize a response
        for msg in reversed(messages):
            if msg.role == "tool":
                return LLMResponse(
                    content=f"Based on the data retrieved, here is what I found: {msg.content[:200] if msg.content else 'No data available.'}",
                    finish_reason="stop",
                )
            if msg.role == "user":
                break

        # Simulate tool calls based on keywords
        if tools:
            tool_names = {t["function"]["name"] for t in tools}

            if any(w in last_user_msg for w in ["how many", "list", "show me all", "what models", "what agents"]):
                if "list_entities" in tool_names:
                    return LLMResponse(
                        tool_calls=[ToolCall(id="call_mock_1", name="list_entities", arguments={"entity_type": "all"})],
                        finish_reason="tool_calls",
                    )

            if any(w in last_user_msg for w in ["metric", "performance", "accuracy", "how is"]):
                if "query_metrics" in tool_names:
                    # Try to extract an entity reference
                    return LLMResponse(
                        tool_calls=[ToolCall(id="call_mock_2", name="query_metrics", arguments={"entity_id": "_first_"})],
                        finish_reason="tool_calls",
                    )

            if any(w in last_user_msg for w in ["alert", "warning", "notification"]):
                if "query_alerts" in tool_names:
                    return LLMResponse(
                        tool_calls=[ToolCall(id="call_mock_3", name="query_alerts", arguments={})],
                        finish_reason="tool_calls",
                    )

            if any(w in last_user_msg for w in ["drift", "distribution"]):
                if "query_drift" in tool_names:
                    return LLMResponse(
                        tool_calls=[ToolCall(id="call_mock_4", name="query_drift", arguments={"entity_id": "_first_"})],
                        finish_reason="tool_calls",
                    )

            if any(w in last_user_msg for w in ["compare"]):
                if "compare_entities" in tool_names:
                    return LLMResponse(
                        tool_calls=[ToolCall(id="call_mock_5", name="compare_entities", arguments={"entity_a": "_first_", "entity_b": "_second_"})],
                        finish_reason="tool_calls",
                    )

            if any(w in last_user_msg for w in ["summary", "overview", "status"]):
                if "get_summary" in tool_names:
                    return LLMResponse(
                        tool_calls=[ToolCall(id="call_mock_6", name="get_summary", arguments={})],
                        finish_reason="tool_calls",
                    )

            if any(w in last_user_msg for w in ["industry", "which industry", "what industry"]):
                if "get_industry_info" in tool_names:
                    return LLMResponse(
                        tool_calls=[ToolCall(id="call_mock_7", name="get_industry_info", arguments={})],
                        finish_reason="tool_calls",
                    )

            if any(w in last_user_msg for w in ["switch to", "change industry"]):
                if "switch_industry" in tool_names:
                    # Extract industry name
                    industry = "retail"
                    for ind in ["retail", "hls", "industrials", "hospitality"]:
                        if ind in last_user_msg:
                            industry = ind
                            break
                    return LLMResponse(
                        tool_calls=[ToolCall(id="call_mock_8", name="switch_industry", arguments={"industry_id": industry})],
                        finish_reason="tool_calls",
                    )

            if any(w in last_user_msg for w in ["lineage", "version", "history"]):
                if "explain_lineage" in tool_names:
                    return LLMResponse(
                        tool_calls=[ToolCall(id="call_mock_9", name="explain_lineage", arguments={"entity_id": "_first_"})],
                        finish_reason="tool_calls",
                    )

            if any(w in last_user_msg for w in ["project"]):
                if "get_projects" in tool_names:
                    return LLMResponse(
                        tool_calls=[ToolCall(id="call_mock_10", name="get_projects", arguments={})],
                        finish_reason="tool_calls",
                    )

        # Default: direct response
        return LLMResponse(
            content="I can help you with model and agent monitoring. Try asking about metrics, alerts, drift, or entity status.",
            finish_reason="stop",
        )


class OpenAIProvider(BaseLLMProvider):
    """OpenAI API provider using the openai Python SDK."""

    def __init__(self, config: dict):
        super().__init__(config)
        api_key_env = config.get("api_key_env", "OPENAI_API_KEY")
        api_key = os.environ.get(api_key_env)
        if not api_key:
            raise ValueError(f"Environment variable {api_key_env} is not set")

        try:
            import openai
        except ImportError:
            raise ImportError("openai package is required for OpenAIProvider. Install with: pip install openai")

        self._client = openai.OpenAI(api_key=api_key)

    def complete(self, messages: list[LLMMessage], tools: list[dict] | None = None) -> LLMResponse:
        import openai

        api_messages = []
        for msg in messages:
            m = {"role": msg.role, "content": msg.content or ""}
            if msg.tool_call_id:
                m["tool_call_id"] = msg.tool_call_id
            if msg.name:
                m["name"] = msg.name
            if msg.tool_calls:
                m["tool_calls"] = msg.tool_calls
            api_messages.append(m)

        kwargs = {
            "model": self.model,
            "messages": api_messages,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        response = self._client.chat.completions.create(**kwargs)
        choice = response.choices[0]

        tool_calls = []
        if choice.message.tool_calls:
            for tc in choice.message.tool_calls:
                tool_calls.append(ToolCall(
                    id=tc.id,
                    name=tc.function.name,
                    arguments=json.loads(tc.function.arguments),
                ))

        return LLMResponse(
            content=choice.message.content,
            tool_calls=tool_calls,
            finish_reason=choice.finish_reason or "stop",
        )


class AzureOpenAIProvider(BaseLLMProvider):
    """Azure OpenAI provider."""

    def __init__(self, config: dict):
        super().__init__(config)
        endpoint_env = config.get("azure_endpoint_env", "AZURE_OPENAI_ENDPOINT")
        api_key_env = config.get("api_key_env", "OPENAI_API_KEY")
        endpoint = os.environ.get(endpoint_env)
        api_key = os.environ.get(api_key_env)
        if not endpoint or not api_key:
            raise ValueError(f"Environment variables {endpoint_env} and {api_key_env} must be set")

        try:
            import openai
        except ImportError:
            raise ImportError("openai package is required for AzureOpenAIProvider. Install with: pip install openai")

        self._client = openai.AzureOpenAI(
            azure_endpoint=endpoint,
            api_key=api_key,
            api_version="2024-06-01",
        )
        self._deployment = config.get("azure_deployment", "gpt-4o-mini")

    def complete(self, messages: list[LLMMessage], tools: list[dict] | None = None) -> LLMResponse:
        import openai

        api_messages = []
        for msg in messages:
            m = {"role": msg.role, "content": msg.content or ""}
            if msg.tool_call_id:
                m["tool_call_id"] = msg.tool_call_id
            if msg.name:
                m["name"] = msg.name
            if msg.tool_calls:
                m["tool_calls"] = msg.tool_calls
            api_messages.append(m)

        kwargs = {
            "model": self._deployment,
            "messages": api_messages,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        response = self._client.chat.completions.create(**kwargs)
        choice = response.choices[0]

        tool_calls = []
        if choice.message.tool_calls:
            for tc in choice.message.tool_calls:
                tool_calls.append(ToolCall(
                    id=tc.id,
                    name=tc.function.name,
                    arguments=json.loads(tc.function.arguments),
                ))

        return LLMResponse(
            content=choice.message.content,
            tool_calls=tool_calls,
            finish_reason=choice.finish_reason or "stop",
        )


def create_provider(config: dict) -> BaseLLMProvider:
    """Factory function to create the appropriate LLM provider."""
    provider_type = config.get("provider", "mock")
    providers = {
        "mock": MockProvider,
        "openai": OpenAIProvider,
        "azure_openai": AzureOpenAIProvider,
    }
    provider_cls = providers.get(provider_type)
    if provider_cls is None:
        raise ValueError(f"Unknown LLM provider: {provider_type}. Available: {list(providers.keys())}")
    return provider_cls(config)
