"""Orchestrator for the agentic chat interface.

Manages conversation history, constructs system prompts with platform context,
routes user messages through the LLM with tool-calling, and synthesizes responses.
"""

import json
import time
from collections import defaultdict
from dataclasses import dataclass, field

import data_source
from config_loader import config
from agentic.llm import LLMMessage, LLMResponse, BaseLLMProvider, create_provider
from agentic.tools import ToolContext, ToolResult, ToolRegistry, build_registry


# ── Session Management ──────────────────────────────────────────────────────

@dataclass
class ChatSession:
    """Conversation state for a single user session."""
    session_id: str
    history: list[LLMMessage] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    last_active: float = field(default_factory=time.time)
    message_count: int = 0


class SessionStore:
    """In-memory session store with cleanup."""

    def __init__(self, max_history_turns: int = 20):
        self._sessions: dict[str, ChatSession] = {}
        self._max_history = max_history_turns

    def get_or_create(self, session_id: str) -> ChatSession:
        if session_id not in self._sessions:
            self._sessions[session_id] = ChatSession(session_id=session_id)
        session = self._sessions[session_id]
        session.last_active = time.time()
        return session

    def clear(self, session_id: str):
        if session_id in self._sessions:
            del self._sessions[session_id]

    def get_history(self, session_id: str) -> list[dict]:
        session = self._sessions.get(session_id)
        if not session:
            return []
        return [
            {"role": m.role, "content": m.content}
            for m in session.history
            if m.role in ("user", "assistant")
        ]

    def trim_history(self, session: ChatSession):
        """Keep only the last N user/assistant pairs."""
        max_msgs = self._max_history * 2  # pairs
        if len(session.history) > max_msgs:
            session.history = session.history[-max_msgs:]


# ── Rate Limiter ────────────────────────────────────────────────────────────

class RateLimiter:
    """Simple per-session rate limiter."""

    def __init__(self, max_per_minute: int = 30):
        self._max = max_per_minute
        self._timestamps: dict[str, list[float]] = defaultdict(list)

    def is_allowed(self, session_id: str) -> bool:
        now = time.time()
        window_start = now - 60
        # Clean old timestamps
        self._timestamps[session_id] = [
            ts for ts in self._timestamps[session_id] if ts > window_start
        ]
        if len(self._timestamps[session_id]) >= self._max:
            return False
        self._timestamps[session_id].append(now)
        return True


# ── System Prompt Builder ───────────────────────────────────────────────────

def build_system_prompt(data_source_mode: str) -> str:
    """Build the system prompt with platform context."""
    base = (
        "You are an AI assistant for Tredence ML Works, an ML/AI monitoring platform. "
        "You help users understand model and agent performance, investigate alerts, "
        "explore drift, compare entities, and manage the monitoring platform.\n\n"
        "Guidelines:\n"
        "- Be concise and data-driven in your responses\n"
        "- Cite entity IDs and metric names when referencing data\n"
        "- Suggest follow-up actions the user might want to take\n"
        "- For write operations (onboarding, alerts), confirm parameters before executing\n"
        "- Never fabricate data — only report what tools return\n"
    )

    if data_source_mode == "mock":
        industry = data_source.get_current_industry()
        available = data_source.get_available_industries()
        industry_names = [ind.get("name", ind.get("id", "")) for ind in available]
        base += (
            f"\nCurrent mode: DEMO (simulated data)\n"
            f"Active industry: {industry}\n"
            f"Available industries: {', '.join(industry_names)}\n"
            f"Note: Data shown is simulated for demonstration. "
            f"Users can switch industries to see different scenarios.\n"
        )
    else:
        base += (
            "\nCurrent mode: LIVE (real telemetry)\n"
            "Data reflects actual production telemetry ingested via the pipeline.\n"
            "Industry switching is not applicable in live mode.\n"
        )

    return base


# ── Orchestrator ────────────────────────────────────────────────────────────

class Orchestrator:
    """Main orchestrator that ties LLM, tools, and sessions together."""

    def __init__(self, agentic_config: dict | None = None):
        cfg = agentic_config or config.agentic
        self._provider: BaseLLMProvider = create_provider(cfg)
        self._data_source_mode = data_source.DATA_SOURCE
        self._registry: ToolRegistry = build_registry(self._data_source_mode)
        self._sessions = SessionStore(max_history_turns=cfg.get("max_history_turns", 20))
        self._rate_limiter = RateLimiter(max_per_minute=cfg.get("rate_limit_per_minute", 30))
        self._max_tool_rounds = 3  # Max LLM→tool→LLM cycles per message

    def _get_data_source_mode(self) -> str:
        """Get current data source mode (may change at runtime via settings)."""
        return data_source.DATA_SOURCE

    def _build_context(self, db=None) -> ToolContext:
        """Build a ToolContext for the current state."""
        mode = self._get_data_source_mode()
        industry = data_source.get_current_industry()
        try:
            industry_meta = data_source.INDUSTRY_META or {}
        except Exception:
            industry_meta = {}
        available = data_source.get_available_industries()

        return ToolContext(
            db=db,
            data_source_mode=mode,
            current_industry=industry,
            industry_meta=industry_meta if isinstance(industry_meta, dict) else {},
            available_industries=available,
        )

    def chat(self, message: str, session_id: str = "default", db=None) -> dict:
        """Process a user message and return a response.

        Args:
            message: The user's message text.
            session_id: Session identifier for conversation continuity.
            db: Optional database connection (for write tools).

        Returns:
            dict with keys: response, tool_calls, suggestions, data, error
        """
        # Rate limiting
        if not self._rate_limiter.is_allowed(session_id):
            return {
                "response": "You're sending messages too quickly. Please wait a moment.",
                "tool_calls": [],
                "suggestions": [],
                "data": None,
                "error": "rate_limited",
            }

        # Input validation
        if not message or not message.strip():
            return {
                "response": "Please enter a message.",
                "tool_calls": [],
                "suggestions": [],
                "data": None,
                "error": "empty_message",
            }

        if len(message) > 2000:
            return {
                "response": "Message too long. Please keep messages under 2000 characters.",
                "tool_calls": [],
                "suggestions": [],
                "data": None,
                "error": "message_too_long",
            }

        # Get/create session
        session = self._sessions.get_or_create(session_id)
        session.message_count += 1

        # Rebuild registry in case data_source mode changed
        current_mode = self._get_data_source_mode()
        if current_mode != self._data_source_mode:
            self._data_source_mode = current_mode
            self._registry = build_registry(current_mode)

        # Build context
        context = self._build_context(db)

        # Build system prompt
        system_prompt = build_system_prompt(current_mode)

        # Prepare messages for LLM
        messages = [LLMMessage(role="system", content=system_prompt)]
        messages.extend(session.history)
        messages.append(LLMMessage(role="user", content=message))

        # Get tool definitions
        tools_defs = self._registry.get_openai_tools()

        # LLM interaction loop (supports multi-step tool calling)
        tool_calls_made = []
        collected_data = None
        rounds = 0

        while rounds < self._max_tool_rounds:
            rounds += 1
            response = self._provider.complete(messages, tools_defs if tools_defs else None)

            if not response.tool_calls:
                # LLM gave a direct response
                break

            # Process tool calls
            for tc in response.tool_calls:
                tool = self._registry.get(tc.name)
                if tool is None:
                    # Tool not found — add error message
                    messages.append(LLMMessage(
                        role="tool",
                        content=json.dumps({"error": f"Tool '{tc.name}' not found."}),
                        tool_call_id=tc.id,
                        name=tc.name,
                    ))
                    tool_calls_made.append({"tool": tc.name, "error": "not_found"})
                    continue

                # Execute tool
                result = tool.execute(tc.arguments, context)
                tool_calls_made.append({
                    "tool": tc.name,
                    "params": tc.arguments,
                    "success": result.success,
                    "summary": result.summary,
                })

                # Keep track of collected data
                if result.data:
                    collected_data = result.data

                # Feed result back to LLM
                result_content = json.dumps({
                    "success": result.success,
                    "summary": result.summary,
                    "data": result.data,
                    "source": result.source,
                    "error": result.error,
                }, default=str)

                # Add assistant message with tool_calls then tool result
                if rounds == 1 or not any(m.role == "assistant" and m.tool_calls for m in messages[-3:]):
                    messages.append(LLMMessage(
                        role="assistant",
                        content=None,
                        tool_calls=[{"id": tc.id, "type": "function", "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)}}],
                    ))

                messages.append(LLMMessage(
                    role="tool",
                    content=result_content,
                    tool_call_id=tc.id,
                    name=tc.name,
                ))

        # Extract final response
        final_content = response.content if response.content else ""
        if not final_content and tool_calls_made:
            # If LLM didn't produce a final text response, use tool summaries
            summaries = [tc["summary"] for tc in tool_calls_made if tc.get("summary")]
            final_content = " ".join(summaries) if summaries else "I processed your request."

        # Generate suggestions
        suggestions = self._generate_suggestions(message, tool_calls_made, current_mode)

        # Update session history
        session.history.append(LLMMessage(role="user", content=message))
        session.history.append(LLMMessage(role="assistant", content=final_content))
        self._sessions.trim_history(session)

        return {
            "response": final_content,
            "tool_calls": tool_calls_made,
            "suggestions": suggestions,
            "data": collected_data,
            "error": None,
        }

    def get_history(self, session_id: str) -> list[dict]:
        """Get conversation history for a session."""
        return self._sessions.get_history(session_id)

    def clear_session(self, session_id: str):
        """Clear a session's conversation history."""
        self._sessions.clear(session_id)

    def _generate_suggestions(self, message: str, tool_calls: list, mode: str) -> list[str]:
        """Generate follow-up suggestion chips based on context."""
        suggestions = []
        tools_used = {tc["tool"] for tc in tool_calls if "tool" in tc}

        if "list_entities" in tools_used:
            suggestions.extend(["Show metrics for a model", "Check active alerts"])
        elif "query_metrics" in tools_used:
            suggestions.extend(["Check drift status", "Compare with another model"])
        elif "query_alerts" in tools_used:
            suggestions.extend(["Show critical alerts only", "Get platform summary"])
        elif "get_summary" in tools_used:
            suggestions.extend(["List all models", "Show recent alerts"])
        else:
            suggestions.extend(["Platform overview", "List all entities", "Show alerts"])

        if mode == "mock" and "switch_industry" not in tools_used:
            suggestions.append("Switch industry")

        return suggestions[:3]
