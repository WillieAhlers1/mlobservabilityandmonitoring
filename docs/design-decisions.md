---
title: "Design Decisions"
description: "Key design decisions and rationale for Tredence ML Works"
ms.date: 2026-08-03
ms.topic: concept
---

## Design Decisions

### Entity-type toggle vs separate pages

**Decision:** Single cockpit page with All/Models/Agents toggle filter.

**Rationale:** Models and agents belong to the same projects and share alert infrastructure. Separate pages would fragment the monitoring view. The toggle keeps the cockpit as the single source of truth while allowing focused views. Agent columns (Safety, Completion, Groundedness, Cost) differ from model columns (Drift, Performance, DQM) because their observability profiles are fundamentally different.

### Industry data as separate modules

**Decision:** Each industry is a standalone Python file in `industries/` with no imports. `mock_data.py` acts as a router that swaps module-level globals at runtime.

**Rationale:** Avoids a monolithic data file. Adding a new industry means creating one file and adding one entry to `AVAILABLE_INDUSTRIES`. Industry files are pure data — no logic — making them safe to generate or edit independently. The `set_industry()` function uses `importlib.import_module()` for lazy loading.

**Trade-off:** Module-level globals (`MODELS`, `AGENTS`, etc.) mean industry state is per-process, not per-request. Acceptable for a prototype; a production system would use request-scoped context.

### Deterministic mock data via seeded random

**Decision:** All time-series and metric generation uses `random.seed(hash(entity_id + suffix))`.

**Rationale:** Same entity always produces the same charts and metrics across page reloads. This makes the prototype feel like a real monitoring system rather than random noise. Different suffixes (`"_fairness"`, `"_lineage"`, `"_traces"`) ensure independence between metric types for the same entity.

### Agent dashboard tabs are different from model tabs

**Decision:** Agents get Performance, Tool Usage, Cost & Tokens, Safety, Compliance, Policy, Traces. Models get Performance, Drift, Interpretability, Data Quality, Compliance, Equity.

**Rationale:** Models are stateless prediction functions — drift, feature importance, and confusion matrices matter. Agents are stateful orchestrators — tool call patterns, token costs, safety events, and voice/tone policy compliance matter. Shared tabs (Compliance) use the same HIPAA structure for consistency.

### Agents reference models via tool_models

**Decision:** Each agent has a `tool_models` list of model IDs it depends on. The agent dashboard shows linked model health.

**Rationale:** This creates a dependency graph: when a model degrades, the agent dashboard surfaces it. Alerts for tool failures link back to the model dashboard. This mirrors real-world agent-model relationships.

### HIPAA compliance structure for all industries

**Decision:** The `hipaa` dict is present on every model and agent across all industries, not just HLS. Non-healthcare industries use adapted field values (e.g., `data_classification: "Proprietary"`, `phi_handling: "N/A - No PHI"`).

**Rationale:** The compliance tab is a showcase feature. Keeping the structure consistent avoids template conditionals. The field names are generic enough (encryption, access control, audit logging, retention) to apply to any regulated industry.

### SQLite for persistence, mock data for everything else

**Decision:** Only user-created projects and onboarded models persist in SQLite. All monitoring data (metrics, alerts, lineage, fairness) is generated dynamically.

**Rationale:** The prototype demonstrates monitoring views, not data ingestion pipelines. SQLite makes project/onboard forms feel real without requiring a database server. The DB file is gitignored and ephemeral on Azure App Service.

### Tredence brand theme via CSS custom properties

**Decision:** All colors, fonts, and shadows use CSS custom properties (`--tr-orange`, `--tr-teal`, etc.) defined in `:root`.

**Rationale:** A single file edit changes the entire theme. Bootstrap is overridden via `!important` only where necessary (buttons, badges). The Poppins font is loaded via Google Fonts CDN.

### Lazy chart initialization

**Decision:** Chart.js charts render only when their tab is first activated via Bootstrap's `shown.bs.tab` event.

**Rationale:** Each dashboard has 5-7 tabs with 2-4 charts each. Rendering all at once causes visible jank and wastes resources. The `inited` object tracks which tabs have been initialized to avoid duplicate renders.

### Industry switcher redirects to Projects (not Cockpit)

**Decision:** After switching industries, the user lands on the Projects page.

**Rationale:** Projects provide the best orientation for a new industry — showing all projects, their models, and agents in context. The cockpit table is less useful until you understand the project structure.

### Agents have voice/tone scoring and policy violations

**Decision:** Agent dashboards include a Policy tab with 5 voice dimensions (empathy, professionalism, reading level, brand consistency, clinical language accuracy) and a Traces tab with step-by-step interaction logs.

**Rationale:** In regulated industries (especially HLS), an agent's "voice" matters as much as its accuracy. Policy violations track whether the agent follows institutional communication guidelines, uses approved terminology, maintains reading level requirements, and includes required disclaimers. Traces provide the evidence chain for auditing.

### Deterministic event ID for deduplication

**Decision:** Each CTE's `event_id` is a SHA-256 hash of `(source_connector, source_entity_ref, event_type, timestamp, metric_name)`. The staging store uses `INSERT OR IGNORE` on this primary key.

**Rationale:** Network retries, polling overlaps, and at-least-once delivery all produce duplicates. A deterministic ID means the same logical event always produces the same key, regardless of how many times it arrives. No UUID generation, no coordination, no bloom filters — just a hash and a unique constraint.

**Trade-off:** Two genuinely different events with identical (connector, ref, type, timestamp, metric_name) would collide. In practice, this combination is a natural composite key for telemetry.

### YAML-driven mapping definitions

**Decision:** Mapping logic lives in `mappings/*.yaml` files, not in code. Each file declares source_connector, event_type, field_mappings, transforms, validation_rules, and target_table.

**Rationale:** Adding a new data source or changing field extraction requires no code changes — only a new YAML file. Mappings are versioned alongside the app and auditable. This decouples "how to parse" from "how to route and store."

**Trade-off:** Complex conditional logic is harder to express in YAML than in code. The `when` clause supports simple expressions (`payload.metric_name == 'accuracy'`), but deeply nested logic would require a code handler.

### Append-only staging with replay capability

**Decision:** The staging store is an immutable event log. Events are never deleted — only their `processing_status` changes (pending → mapped | rejected). Rejected events can be reprocessed.

**Rationale:** Append-only storage provides a full audit trail for compliance. If a mapping definition is fixed after a bug, all rejected events from the affected window can be replayed without re-ingesting from the source. The dead-letter queue UI surfaces rejected events for human review.

### Handler pattern for specialized tables

**Decision:** A handler registry maps `event_type` → handler class. Each handler knows how to write its event type to the correct table (DriftHandler → drift_snapshots, AlertsHandler → alerts, TracesHandler → agent_traces + steps).

**Rationale:** The metric_timeseries table handles numeric time series, but drift, alerts, and traces have fundamentally different schemas. Rather than force everything into one table or add if/else branches in the mapping engine, each event type gets a dedicated writer that understands its target schema.

### Webhook HMAC authentication with rate limiting

**Decision:** The webhook connector validates an `X-Webhook-Signature` header using HMAC-SHA256. A token bucket rate limiter enforces request/second limits.

**Rationale:** Webhooks are internet-facing endpoints. Without signature validation, any actor could inject false telemetry. HMAC is simple, stateless, and well-understood. The rate limiter prevents burst traffic from overwhelming the staging store. In development mode (no secret configured), the webhook accepts all requests for convenience.

### APScheduler for background processing

**Decision:** Background jobs (connector polling, batch mapping, aggregation, health checks) run via APScheduler's BackgroundScheduler, activated only in live mode.

**Rationale:** APScheduler is lightweight, runs in-process (no Redis/Celery dependency), and provides interval-based scheduling with proper shutdown hooks. The scheduler is a no-op in mock mode, keeping development fast. For horizontal scaling, the scheduler could be replaced with an external job runner without changing the job logic.

### Completeness scoring for partial telemetry

**Decision:** Each entity tracks a completeness score (0-1) based on which expected metrics are present. Dashboards render "No data" badges for missing metrics instead of zeros.

**Rationale:** A newly onboarded entity won't have all metrics immediately. Showing zeros would be misleading (is accuracy really 0, or just not reported yet?). The completeness score gives operators visibility into which entities need attention, and the "Awaiting telemetry" state provides clear user feedback.
