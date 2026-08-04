---
title: "Implementation Plan: Agentic Chat Interface"
description: "Plan for adding a conversational AI assistant to Tredence ML Works"
ms.date: 2026-08-04
ms.topic: plan
---

## Overview

Add a conversational (agentic) chat interface to Tredence ML Works that allows users to interact with the platform using natural language. The assistant can answer questions about model and agent performance, onboard new models/agents, configure alerts, compare entities, and surface actionable insights — all without requiring users to navigate the UI manually.

## Goals

1. Provide a chat panel accessible from every page via a persistent floating widget.
2. Support natural-language queries about model/agent metrics, drift, alerts, and lineage.
3. Allow users to perform actions (onboard, set alerts, compare) through conversation.
4. Return structured, citation-backed responses grounded in actual platform data.
5. Work seamlessly in both mock and live data modes (see Data Mode Behavior below).

## Data Mode Behavior

The agentic interface inherits the platform's dual-data-path design via `data_source.py`. All tools call `data_source.*` functions — never `mock_data.*` or raw SQL directly — so the active `data_source` setting determines what the agent sees.

| Aspect | `data_source: mock` | `data_source: live` |
|--------|---------------------|---------------------|
| Entity listing | Returns industry-specific mock models/agents | Queries `entity_registry` table |
| Metrics | Generated mock metrics (classification/regression) | `metric_timeseries_agg` with raw fallback |
| Alerts | Mock alerts from industry module | `alerts` table |
| Drift | Mock drift events | `drift_snapshots` table |
| Lineage | Mock version history | `lineage_events` table |
| Industry awareness | Agent knows and reports the current industry; switching industry changes available entities | Industry concept is ignored; entities stand alone |
| Contextual prompt | System prompt includes current industry name + project list from mock | System prompt includes project list from DB |
| Onboarding | Writes to SQLite (same as UI onboard) | Writes to SQLite (same as UI onboard) |
| Alert configuration | Writes to SQLite | Writes to SQLite |

### Implementation Rules

1. **Tools always call `data_source.*`** — the router handles mock vs. live transparently.
2. **Industry context is injected** by the orchestrator only when `data_source == "mock"`. In mock mode, the system prompt tells the LLM which industry is active and what that means for the user's data.
3. **Industry switching via chat** — in mock mode, users can say "switch to retail" and the agent calls `data_source.set_industry("retail")`, then confirms the change. In live mode, the agent explains that industry switching is not applicable.
4. **Tool results carry a `source` field** (`"mock"` or `"live"`) so the orchestrator can annotate responses — e.g., "Based on simulated HLS data..." vs. "Based on live telemetry...".
5. **Mock provider (for testing) ≠ mock data mode.** The mock *LLM provider* returns canned responses without calling an API. The mock *data source* returns synthetic platform data. These are independent: tests use mock LLM + mock data; production can use real LLM + either data mode.

## Architecture

```text
┌────────────────────────────────────────────────────────────────┐
│  Browser — Chat Widget (floating panel, all pages)             │
│  Vanilla JS + Bootstrap 5 styling                              │
│  WebSocket or SSE for streaming responses                      │
└──────────────────────┬─────────────────────────────────────────┘
                       │ POST /api/chat  (+ optional SSE stream)
┌──────────────────────▼─────────────────────────────────────────┐
│  routes/chat.py — Flask route                                  │
│    • Session management (conversation history per user)        │
│    • Rate limiting                                             │
│    • Input validation & sanitization                           │
└──────────────────────┬─────────────────────────────────────────┘
                       │
┌──────────────────────▼─────────────────────────────────────────┐
│  agentic/orchestrator.py — Intent Router & Tool Executor       │
│    • Classifies user intent                                    │
│    • Selects and calls the appropriate tool(s)                 │
│    • Composes final response with citations                    │
│    • Manages multi-turn context                                │
└──────────┬───────────────────────┬─────────────────────────────┘
           │                       │
┌──────────▼──────────┐  ┌────────▼──────────────────────────────┐
│  agentic/llm.py     │  │  agentic/tools/                       │
│  LLM Provider       │  │    query_metrics.py                   │
│  (OpenAI / Azure    │  │    query_alerts.py                    │
│   OpenAI / local)   │  │    query_drift.py                     │
│                     │  │    compare_entities.py                 │
│  Configurable via   │  │    onboard_entity.py                  │
│  app.yaml           │  │    set_alert.py                       │
│                     │  │    list_entities.py                    │
│                     │  │    explain_lineage.py                  │
└─────────────────────┘  │    get_summary.py                     │
                         └───────────────────────────────────────┘
                                    │
                         ┌──────────▼────────────────────────────┐
                         │  data_source.py (existing router)      │
                         │  database.py (existing DB layer)       │
                         └───────────────────────────────────────┘
```

## Detailed Design

### Phase 1: Backend Infrastructure

#### 1.1 Configuration Extension (`config/app.yaml`)

```yaml
agentic:
  enabled: true
  provider: openai          # openai | azure_openai | ollama | mock
  model: gpt-4o-mini
  api_key_env: OPENAI_API_KEY
  azure_endpoint_env: AZURE_OPENAI_ENDPOINT   # only for azure_openai
  azure_deployment: gpt-4o-mini               # only for azure_openai
  max_tokens: 1024
  temperature: 0.2
  max_history_turns: 20
  rate_limit_per_minute: 30
  system_prompt_override: null  # optional path to custom system prompt
```

#### 1.2 LLM Abstraction (`agentic/llm.py`)

- `BaseLLMProvider` ABC with `async complete(messages, tools) → response`
- `OpenAIProvider` — calls OpenAI chat completions with function-calling
- `AzureOpenAIProvider` — Azure OpenAI variant
- `OllamaProvider` — local models for air-gapped/dev use
- `MockProvider` — returns canned responses for testing (no API key needed)

#### 1.3 Tool Framework (`agentic/tools/base.py`)

Each tool is a class implementing:

```python
class BaseTool:
    name: str               # unique identifier
    description: str        # shown to LLM for selection
    parameters: dict        # JSON Schema of accepted params
    
    def execute(self, params: dict, context: ToolContext) -> ToolResult:
        """Run the tool and return structured data + natural-language summary."""
```

`ToolContext` carries: `db` connection, `data_source` mode, `industry_id`, `user_session`.

#### 1.4 Tool Implementations (`agentic/tools/`)

| Tool | Purpose | Data Source |
|------|---------|-------------|
| `list_entities` | List models/agents, filter by project/status | `data_source.get_models()`, `get_agents()` |
| `query_metrics` | Get performance metrics for an entity | `data_source.get_model_metrics()`, `get_agent_metrics()` |
| `query_alerts` | List/filter alerts by severity, entity, date | `data_source.get_alerts()` |
| `query_drift` | Get drift events/status for an entity | `data_source.get_drift_events()` |
| `compare_entities` | Side-by-side metric comparison | `data_source.get_model_metrics()` × 2 |
| `onboard_entity` | Onboard a new model or agent | `database.get_db()` INSERT (reuses onboard logic) |
| `set_alert` | Create/update alert thresholds | `database.get_db()` INSERT into alerts config |
| `explain_lineage` | Describe version history & retrain events | `data_source.get_model_lineage()` |
| `get_summary` | Platform-wide stats (counts, health) | `data_source.get_summary_stats_combined()` |
| `get_projects` | List projects with entity counts | `data_source.get_projects()` |
| `get_industry_info` | Current industry + available industries (mock mode) | `data_source.get_current_industry()`, `get_available_industries()` |
| `switch_industry` | Change active industry (mock mode only) | `data_source.set_industry()` |

> **Note:** `get_industry_info` and `switch_industry` are registered only when `data_source == "mock"`. The tool registry is built dynamically at startup based on the active mode, so the LLM never sees inapplicable tools.

#### 1.5 Orchestrator (`agentic/orchestrator.py`)

- Maintains conversation history (in-memory per session, capped at `max_history_turns`)
- Constructs system prompt with platform context (current industry, entities count, capabilities)
- Uses LLM function-calling to select tools
- Executes tool calls, feeds results back to LLM for response synthesis
- Supports multi-step reasoning (tool → result → follow-up tool)
- Returns final markdown-formatted answer with optional structured data (charts, tables)

#### 1.6 Chat Route (`routes/chat.py`)

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/chat` | POST | Send message, receive response |
| `/api/chat/history` | GET | Retrieve current session history |
| `/api/chat/clear` | POST | Clear conversation history |

Request schema:
```json
{
  "message": "How is model fraud-detector-v2 performing?",
  "session_id": "optional-client-session-id"
}
```

Response schema:
```json
{
  "response": "The fraud-detector-v2 model shows...",
  "tool_calls": [{"tool": "query_metrics", "entity_id": "model-fraud-v2"}],
  "suggestions": ["Show drift status", "Compare with v1", "Set alert on accuracy"],
  "data": { ... }  // optional structured data for rich rendering
}
```

### Phase 2: Frontend Chat Widget

#### 2.1 Chat Panel Component (`static/js/chat.js`)

- Floating action button (bottom-right) opens a slide-up chat panel
- Message input with send button and keyboard shortcut (Enter)
- Message history with user/assistant bubbles
- Typing indicator during LLM processing
- Clickable suggestion chips after each response
- Markdown rendering in assistant messages (tables, code, bold)
- Collapsible "tool calls" section for transparency
- Responsive: full-screen on mobile, panel on desktop

#### 2.2 Chat Panel Template (`templates/partials/chat_widget.html`)

- Included in `base.html` so it's available on every page
- Minimal footprint when collapsed (just the FAB)
- Persists open/closed state in localStorage

#### 2.3 Styling (`static/css/chat.css`)

- Follows existing Tredence theme (colors from `tredence-theme.css`)
- Dark-mode compatible
- Smooth open/close animations
- Scrollable message area with auto-scroll to latest

### Phase 3: Conversation Intelligence

#### 3.1 System Prompt (`agentic/prompts/system.md`)

Defines the assistant's persona, capabilities, constraints:
- Expert ML/AI monitoring assistant for Tredence ML Works
- Can only answer questions about entities in the platform
- Cannot execute destructive actions without confirmation
- Cites entity IDs and metric names in responses
- Suggests follow-up actions

#### 3.2 Contextual Awareness

The orchestrator injects dynamic context into each request:

**Common (both modes):**
- Number of models/agents being monitored
- Available projects with entity counts
- Recent alert summary
- Active drift warnings

**Mock mode additions:**
- Current industry name and description (e.g., "Healthcare & Life Sciences")
- Available industries the user can switch to
- Note that data is simulated for demonstration purposes

**Live mode additions:**
- Pipeline health status (connector health, ingestion lag)
- Note that data reflects real telemetry

The `ToolContext` dataclass carries:
```python
@dataclass
class ToolContext:
    db: sqlite3.Connection
    data_source_mode: str       # "mock" or "live"
    current_industry: str       # industry ID (meaningful in mock mode)
    industry_meta: dict         # name, icon, description
    available_industries: list  # for mock mode industry switching
    user_session: dict          # conversation state
```

#### 3.3 Confirmation Flow for Actions

For write operations (onboard, set alert):
1. Assistant proposes the action with parameters
2. User confirms ("yes" / "go ahead")
3. Tool executes and returns confirmation
4. This prevents accidental modifications

### Phase 4: Testing Strategy

#### 4.1 Unit Tests

| Test File | Coverage |
|-----------|----------|
| `tests/test_chat_tools.py` | Each tool's `execute()` in isolation with mock data |
| `tests/test_orchestrator.py` | Intent classification, multi-turn context, tool selection |
| `tests/test_llm_providers.py` | Provider abstraction, error handling, retries |
| `tests/test_chat_route.py` | API endpoint validation, rate limiting, auth |

#### 4.2 Integration Tests

| Test File | Coverage |
|-----------|----------|
| `tests/test_chat_e2e.py` | Full flow: message → orchestrator → tool → response |
| `tests/test_chat_onboard_flow.py` | Conversational onboarding with confirmation |
| `tests/test_chat_mock_provider.py` | End-to-end with mock LLM (no API key needed) |
| `tests/test_chat_mock_data_mode.py` | Chat with `data_source=mock`: industry awareness, entity queries, switching |
| `tests/test_chat_live_data_mode.py` | Chat with `data_source=live`: DB-backed queries, no industry tools |

#### 4.3 Test Approach

- **Mock LLM provider** for all automated tests — deterministic, no API cost
- **Both data modes tested** — each integration test suite runs once with `data_source=mock` and once with `data_source=live` using a seeded test DB
- **Fixture-based** tool testing using existing `conftest.py` database setup
- **Snapshot tests** for system prompt construction (mock vs. live variants)
- **Rate limit tests** verifying throttle behavior
- **Conversation history** tests for context window management
- **Industry switching tests** — verify mock mode allows switch, live mode rejects gracefully

### Phase 5: Security & Guardrails

| Concern | Mitigation |
|---------|------------|
| Prompt injection | Input sanitization, system prompt hardening, output filtering |
| Data exfiltration | Tools only access data visible in the UI; no raw SQL passthrough |
| API key exposure | Keys read from env vars only; never logged or returned to client |
| Rate limiting | Per-session rate limit (configurable in app.yaml) |
| Action safety | Write operations require explicit user confirmation |
| Input size | Max message length enforced (2000 chars) |
| History overflow | Conversation capped at N turns; oldest dropped |

## File Structure (New Files)

```text
agentic/
    __init__.py
    orchestrator.py        # Main orchestration logic
    llm.py                 # LLM provider abstraction
    prompts/
        system.md          # System prompt template (uses Jinja2 conditionals for mode)
    tools/
        __init__.py        # Tool registry (dynamic based on data_source mode)
        base.py            # BaseTool, ToolContext, ToolResult
        list_entities.py
        query_metrics.py
        query_alerts.py
        query_drift.py
        compare_entities.py
        onboard_entity.py
        set_alert.py
        explain_lineage.py
        get_summary.py
        get_projects.py
        get_industry_info.py   # Mock mode only
        switch_industry.py     # Mock mode only
routes/
    chat.py                # Chat API endpoints
templates/
    partials/
        chat_widget.html   # Chat panel partial (included in base.html)
static/
    js/chat.js             # Chat widget JavaScript
    css/chat.css           # Chat widget styles
tests/
    test_chat_tools.py
    test_orchestrator.py
    test_llm_providers.py
    test_chat_route.py
    test_chat_e2e.py
    test_chat_onboard_flow.py
    test_chat_mock_provider.py
    test_chat_mock_data_mode.py
    test_chat_live_data_mode.py
```

## Dependencies (additions to `requirements.txt`)

```text
openai>=1.30.0             # OpenAI Python SDK (function calling)
tiktoken>=0.7.0            # Token counting for context management
markdown>=3.6              # Server-side markdown rendering (optional)
```

## Implementation Order

| Phase | Deliverable | Depends On |
|-------|-------------|------------|
| 1.1 | Config extension + `config_loader` update | — |
| 1.2 | LLM abstraction with Mock provider | 1.1 |
| 1.3 | Tool base classes + registry | — |
| 1.4 | Tool implementations (read-only first) | 1.3 |
| 1.5 | Orchestrator with mock LLM | 1.2, 1.4 |
| 1.6 | Chat route + session management | 1.5 |
| 2.1–2.3 | Frontend chat widget | 1.6 |
| 3.1–3.3 | System prompt + contextual awareness + confirmations | 1.5 |
| 4.1–4.3 | Full test suite | All above |
| 5 | Security hardening pass | All above |
| 1.4+ | Write tools (onboard, set_alert) with confirmation | 3.3 |

## Success Criteria

- [ ] Chat widget appears on all pages; opens/closes smoothly
- [ ] User can ask "How many models are monitored?" and get correct answer (both modes)
- [ ] User can ask "Show me drift for model X" and get metric data (both modes)
- [ ] User can compare two entities via conversation
- [ ] User can onboard a model through chat (with confirmation step)
- [ ] In mock mode: user can ask "What industry am I viewing?" and get the correct answer
- [ ] In mock mode: user can say "Switch to retail" and the agent changes the industry
- [ ] In live mode: industry-related questions are handled gracefully ("Industry switching is not applicable in live mode")
- [ ] Tool results include `source` annotation ("mock" or "live") for response transparency
- [ ] All tests pass with mock LLM provider (no API key required for CI)
- [ ] Response latency < 3s with mock provider, < 10s with real LLM
- [ ] Rate limiting prevents abuse
- [ ] No prompt injection vectors in input handling

## Open Questions

1. **Streaming**: Should responses stream token-by-token via SSE, or return complete? (Recommend: start with complete responses, add SSE in a follow-up.)
2. **Persistence**: Should conversation history persist across browser sessions (DB-backed) or be ephemeral (in-memory)? (Recommend: in-memory with localStorage backup on client.)
3. **Multi-user**: Current app has no auth. Session isolation via client-generated session ID is sufficient for now.
4. **Ollama default for dev**: Should the mock provider be the default so the feature works without any API keys in development?
5. **Industry switch propagation**: When the agent switches industry in mock mode, should this also update the sidebar/UI state? (Recommend: yes — call the same `set_industry()` that the UI uses, so the next page load reflects the change.)
