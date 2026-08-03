---
title: "Architecture Overview"
description: "System architecture and data flow for Tredence ML Works"
ms.date: 2026-08-03
ms.topic: concept
---

## System Architecture

Tredence ML Works is a Flask application with a dual data path: mock data for demos (default) and a live telemetry ingestion pipeline for production monitoring. The `data_source` router switches between them via configuration.

### Component Diagram

```text
┌─────────────────────────────────────────────────────────┐
│                      Browser                            │
│  Bootstrap 5 + Chart.js 4 + Font Awesome 6              │
└──────────────────────┬──────────────────────────────────┘
                       │ HTTP
┌──────────────────────▼──────────────────────────────────┐
│                    Flask Application                     │
│                                                         │
│  app.py          — App factory, scheduler, context      │
│  database.py     — Schema init, get_db(), migrations    │
│  routes/core.py  — Cockpit, dashboard, projects, etc.   │
│  routes/onboard.py — Model/agent onboarding             │
│  routes/ingestion.py — Pipeline health, webhook         │
│  routes/settings.py — Configuration UI                  │
│                                                         │
│  Routes:                                                │
│    / (cockpit)          /dashboard/<id>                  │
│    /projects            /lineage/<id>                    │
│    /alerts              /compare                        │
│    /onboard             /switch-industry/<id>            │
│    /settings            /api/model/<id>/metrics          │
│    /ingestion/health    /api/ingest/webhook (POST)       │
│    /ingestion/dead-letter  /ingestion/reprocess (POST)   │
│                                                         │
│  SQLite: entity_registry, metric_timeseries,            │
│    metric_timeseries_agg, drift_snapshots, alerts,      │
│    staging_events, connector_health, ...                │
└──────────────────────┬──────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────┐
│            data_source.py (Router)                       │
│                                                         │
│  if DATA_SOURCE == "live":                              │
│      query metric store (agg → raw fallback)            │
│  else:                                                  │
│      delegate to mock_data.*                            │
└────────┬─────────────────────────────┬──────────────────┘
         │ mock mode                   │ live mode
┌────────▼───────────┐   ┌────────────▼──────────────────┐
│  mock_data.py      │   │  Ingestion Pipeline           │
│                    │   │                                │
│  Industry modules  │   │  Connectors (poll/push)       │
│  (hls, retail,     │   │    FileDropConnector (CSV/JSON)│
│   industrials,     │   │    WebhookConnector (HMAC)     │
│   hospitality)     │   │       ↓                       │
│                    │   │  Staging Store (dedup)         │
│                    │   │       ↓                       │
│                    │   │  Mapping Engine (YAML-driven)  │
│                    │   │    Entity Resolution           │
│                    │   │    Transforms + Validation     │
│                    │   │       ↓                       │
│                    │   │  Handler Registry              │
│                    │   │    (alerts, drift, traces, ..) │
│                    │   │       ↓                       │
│                    │   │  Metric Store + Aggregation    │
│                    │   │                                │
│                    │   │  Scheduler (APScheduler)       │
│                    │   │    poll, process, aggregate    │
└────────────────────┘   └────────────────────────────────┘
```

### Ingestion Pipeline Data Flow

```text
Data Sources:
  CSV/JSON files → FileDropConnector ─┐
  HTTP POST      → WebhookConnector  ─┤
                                      ↓
                              Canonical Telemetry Events (CTEs)
                                      ↓
                              Staging Store (INSERT OR IGNORE = dedup)
                                      ↓
                              Mapping Engine Orchestrator:
                                1. Find mapping definition (YAML)
                                2. Resolve entity via aliases
                                3. Apply field transforms
                                4. Validate (range, not_null, numeric)
                                      ↓
                              Handler Registry (routes by event_type):
                                metric  → metric_timeseries
                                drift   → drift_snapshots
                                alert   → alerts
                                trace   → agent_traces + agent_trace_steps
                                cohort  → cohort_metrics
                                feature → feature_importance
                                quality → data_quality
                                lifecycle → lineage_events
                                      ↓
                              Aggregation Engine (1h/1d buckets)
                                      ↓
                              metric_timeseries_agg → Dashboard queries
```
### Industry Modules

```text
┌─────────────────────────────────────────────────────────┐
│  industries/                                            │
│  hls.py          → Healthcare & Life Sciences           │
│  industrials.py  → Manufacturing & Industrial           │
│  retail.py       → Retail & E-Commerce                  │
│  hospitality.py  → Hospitality & Travel                 │
│                                                         │
│  Each exports: INDUSTRY_META, PROJECTS (6),             │
│    MODELS (8), AGENTS (4), COHORT_DEFINITIONS (8),      │
│    TRACE_TEMPLATES (4)                                  │
└─────────────────────────────────────────────────────────┘
```

### Data Flow (Mock Mode)

1. On startup, `mock_data.set_industry("hls")` loads the default industry
2. `PROJECTS`, `MODELS`, `AGENTS` module-level lists are populated from the industry file
3. Flask routes call `data_source.get_*()` which delegates to `mock_data.get_*()` in mock mode
4. Generator functions (`_generate_time_series`, `_get_classification_metrics`, etc.) produce deterministic data using `random.seed(hash(entity_id))` for reproducibility
5. Templates render server-side via Jinja2; Chart.js data is injected as `{{ data | tojson }}`
6. Industry switching via `/switch-industry/<id>` calls `set_industry()` and redirects to Projects

### Data Flow (Live Mode)

1. Connectors poll sources or receive webhook pushes at configured intervals
2. Raw data is normalized to Canonical Telemetry Events (CTEs) with deterministic event IDs
3. CTEs are inserted into the staging store (INSERT OR IGNORE for dedup)
4. The scheduler triggers the mapping engine to process pending CTEs in batches
5. The mapping engine resolves entities, applies transforms, validates, and routes to handlers
6. Handlers write to specialized metric store tables (drift_snapshots, alerts, agent_traces, etc.)
7. The aggregation engine rolls raw metrics into 1h/1d buckets for dashboard performance
8. `data_source.get_*()` queries the agg table (fallback: raw) and returns the same shape as mock mode

### Entity Model

```text
Project (6 per industry)
├── Models (8 total, mapped by project_id)
│   ├── entity_type: "model"
│   ├── model_type: "classification" | "regression"
│   ├── hipaa: { compliant, phi_handling, encryption, ... }
│   └── features: [10 feature names]
│
└── Agents (4 total, mapped by project_id)
    ├── entity_type: "agent"
    ├── tool_models: [model IDs this agent calls]
    ├── tools: [model names + external APIs]
    ├── framework: "Semantic Kernel" | "LangGraph" | "AutoGen"
    ├── llm_backbone: "GPT-4o" | "GPT-4o-mini"
    └── hipaa: { same structure as models }
```

### Template Hierarchy

```text
base.html (sidebar + topbar + industry switcher)
├── cockpit.html         — toggle filter (All/Models/Agents) + dual tables
├── dashboard.html       — 7-tab model dashboard (Performance, Drift, Interpretability, DQ, Compliance, Equity)
├── agent_dashboard.html — 7-tab agent dashboard (Performance, Tools, Cost, Safety, Compliance, Policy, Traces)
├── alerts.html          — alert history with severity + type filters
├── compare.html         — side-by-side model comparison
├── projects.html        — project cards with models + agents listed
├── onboard.html         — 4-step registration form with telemetry source config
├── lineage.html         — version timeline (shared by models and agents)
├── ingestion_health.html — pipeline stats, connector state, lag (live mode only)
├── dead_letter.html     — rejected CTEs with reasons and reprocess (live mode only)
└── settings.html        — application settings
```

### Chart.js Data Injection Pattern

Templates pass data to JS via a global variable:

```html
<!-- In dashboard.html -->
<script>const MODEL_DATA = {{ metrics | tojson }};</script>
<script src="{{ url_for('static', filename='js/dashboard.js') }}"></script>

<!-- In agent_dashboard.html -->
<script>var AD = {{ metrics | tojson }};</script>
<script src="{{ url_for('static', filename='js/agent_dashboard.js') }}"></script>
```

JS files use lazy initialization — charts for non-visible tabs render only when the tab is first shown via `shown.bs.tab` events.

### Database Schema (SQLite)

| Table | Purpose |
|-------|---------|
| `entity_registry` | Central catalog: entity_id, type, industry, project, name, status, metadata |
| `entity_aliases` | Source ref resolution: entity_id + alias_type + alias_value |
| `metric_timeseries` | Raw metrics: entity_id, metric_name, semantic_tag, timestamp, value, dimensions |
| `metric_timeseries_agg` | Aggregated (1h/1d): bucket_start, bucket_size, agg_method, value, sample_count |
| `drift_snapshots` | Drift detection: drift_type, scope, value, status |
| `cohort_metrics` | Cohort-level aggregates: cohort_name, cohort_dim, metric_name, value |
| `feature_importance` | Feature attribution: feature, importance, method |
| `data_quality` | Quality checks: feature, missing_rate, outlier_rate, schema_valid |
| `agent_traces` | Agent execution: trace_id, query, response, latency, tokens, voice_score, policy_pass |
| `agent_trace_steps` | Sub-steps: step_order, tool, action, latency_ms, status |
| `alerts` | Alert events: severity, alert_type, title, description, resolved |
| `staging_events` | Append-only CTE log: event_id (PK), payload (JSON), processing_status |
| `connector_health` | Connector state: last_success, last_failure, consecutive_failures, state |
| `projects` | Project registry: name, description, owner, team, status |
| `onboarded_models` | Legacy model registry with entity_id FK |
| `onboarded_agents` | Legacy agent registry with entity_id FK |

### Background Scheduler

When `DATA_SOURCE=live`, the APScheduler background scheduler runs these jobs:

| Job | Interval | Purpose |
|-----|----------|---------|
| Connector Polling | 60s (configurable) | Calls `poll()` on all connectors, inserts CTEs to staging |
| Batch Processing | 10s (configurable) | Runs mapping engine on pending CTEs |
| Aggregation | configurable | Re-aggregates modified time buckets |
| Health Checks | configurable | Calls `health_check()` on all connectors |

The scheduler only starts in live mode and shuts down gracefully on app exit.
