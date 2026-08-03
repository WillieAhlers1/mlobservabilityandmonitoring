---
title: "Codebase Map"
description: "Quick reference for routes, functions, templates, and data structures"
ms.date: 2026-07-31
ms.topic: reference
---

## Routes (app.py)

| URL | Method | Template | Key Data |
|-----|--------|----------|----------|
| `/` | GET | `cockpit.html` | `models`, `agents`, `stats`, `view` (query: all/models/agents) |
| `/dashboard/<entity_id>` | GET | `dashboard.html` or `agent_dashboard.html` | Routes by `entity_type`; passes `model`/`agent`, `metrics`, `fairness`, `lineage` |
| `/lineage/<entity_id>` | GET | `lineage.html` | `model` (entity dict), `lineage` (version history) |
| `/projects` | GET/POST | `projects.html` | `projects` (mock + SQLite custom); POST creates in SQLite |
| `/onboard` | GET/POST | `onboard.html` | `projects`, `onboarded` (from SQLite); POST inserts model + entity_registry |
| `/alerts` | GET | `alerts.html` | `alerts`, `stats`, `severity_filter`, `type_filter` |
| `/compare` | GET | `compare.html` | `models`, `agents`, `model_a`, `model_b`, `metrics_a`, `metrics_b` |
| `/switch-industry/<id>` | GET | redirect → `/projects` | Calls `data_source.set_industry(id)` |
| `/api/model/<id>/metrics` | GET | JSON | Returns `data_source.get_model_metrics()` or 404 |
| `/api/ingest/webhook` | POST | JSON | HMAC-authenticated telemetry ingestion endpoint |
| `/ingestion/health` | GET | `ingestion_health.html` | Pipeline stats, connector health, schema drift (live only) |
| `/ingestion/dead-letter` | GET | `dead_letter.html` | Rejected CTEs with reasons, pagination (live only) |
| `/ingestion/reprocess` | POST | redirect | Reset rejected CTE(s) to pending (live only) |

## data_source.py (Data Router)

All routes use `data_source.*` instead of `mock_data.*` directly. Controlled by `config.data_source`:

| Function | Mock Mode | Live Mode |
|----------|-----------|-----------|
| `get_models()` | `mock_data.MODELS` | `entity_registry WHERE type='model'` |
| `get_agents()` | `mock_data.AGENTS` | `entity_registry WHERE type='agent'` |
| `get_entity(id)` | `mock_data.get_entity()` | `entity_registry` lookup |
| `get_model_metrics(id)` | `mock_data.get_model_metrics()` | `metric_timeseries_agg` (fallback: raw) |
| `get_agent_metrics(id)` | `mock_data.get_agent_metrics()` | `metric_timeseries` + `agent_traces` |
| `get_alerts()` | `mock_data.get_alerts()` | `alerts` table |
| `get_model_lineage(id)` | `mock_data.get_model_lineage()` | `lineage_events` table |
| `get_summary_stats_combined()` | `mock_data.get_summary_stats_combined()` | `GROUP BY status` on registry |
| `get_projects()` | `mock_data.get_projects()` | `projects` + entity counts |

## Ingestion Pipeline (ingestion/)

| Module | Purpose |
|--------|---------|
| `ingestion/models.py` | `CanonicalTelemetryEvent` dataclass |
| `ingestion/staging.py` | Staging store: insert, dedup, fetch pending, mark status |
| `ingestion/mapping_engine.py` | Orchestrator: resolve → transform → validate → write |
| `ingestion/entity_resolution.py` | Alias-based entity lookup |
| `ingestion/transforms.py` | identity, clamp, scale, round |
| `ingestion/validation.py` | Range, not_null, numeric, timestamp rules |
| `ingestion/mapping_loader.py` | YAML mapping definitions loader |
| `ingestion/aggregation.py` | Time-bucketed aggregation (1h/1d) |
| `ingestion/connector_registry.py` | Creates connectors from config |
| `ingestion/connectors/base.py` | BaseConnector ABC with health tracking |
| `ingestion/connectors/file_drop.py` | CSV/JSON file watcher connector |
| `ingestion/connectors/webhook.py` | HTTP POST webhook connector with HMAC auth |
| `ingestion/handlers/__init__.py` | Handler registry mapping event_type → handler class |
| `ingestion/handlers/drift.py` | DriftHandler → `drift_snapshots` |
| `ingestion/handlers/alerts.py` | AlertsHandler → `alerts` |
| `ingestion/handlers/cohorts.py` | CohortsHandler → `cohort_metrics` |
| `ingestion/handlers/features.py` | FeaturesHandler → `feature_importance` |
| `ingestion/handlers/data_quality.py` | DataQualityHandler → `data_quality` |
| `ingestion/handlers/lifecycle.py` | LifecycleHandler → `lineage_events` |
| `ingestion/handlers/traces.py` | TracesHandler → `agent_traces` + `agent_trace_steps` |
| `ingestion/metrics.py` | Pipeline stats, lag, rejected events, reprocess actions |
| `ingestion/drift_detector.py` | Schema drift detection from rejection patterns |

## mock_data.py Functions

### Industry management

| Function | Returns | Purpose |
|----------|---------|---------|
| `set_industry(id)` | None | Swaps PROJECTS/MODELS/AGENTS/COHORT_DEFINITIONS/TRACE_TEMPLATES from industry module |
| `get_current_industry()` | str | Current industry ID |
| `get_available_industries()` | list[dict] | INDUSTRY_META from all 4 industry modules |

### Model metrics

| Function | Returns | Purpose |
|----------|---------|---------|
| `get_model(id)` | dict/None | Lookup model by ID |
| `get_model_metrics(id)` | dict/None | Routes to classification or regression metrics |
| `get_fairness_metrics(id)` | dict/None | 4 demographic dimensions with disparate impact |
| `get_model_lineage(id)` | dict/None | Version timeline with retrain triggers |
| `get_summary_stats()` | dict | Model-only counts |

### Agent metrics

| Function | Returns | Purpose |
|----------|---------|---------|
| `get_agent(id)` | dict/None | Lookup agent by ID |
| `get_agent_metrics(id)` | dict/None | Completion, groundedness, safety, tokens, tools, policy, voice, traces |
| `get_agent_lineage(id)` | dict/None | Version timeline with prompt/tool change triggers |

### Shared

| Function | Returns | Purpose |
|----------|---------|---------|
| `get_entity(id)` | dict/None | Lookup any entity (model or agent) |
| `get_all_entities()` | list | MODELS + AGENTS |
| `get_projects()` | list | Projects with model/agent counts and lists |
| `get_summary_stats_combined()` | dict | Counts for both models and agents |
| `get_alerts()` | list | 50 model alerts + 20 agent alerts, sorted by timestamp |

### Core generators (private)

| Function | Purpose |
|----------|---------|
| `_generate_time_series()` | 90-day series with noise, trend, optional anomaly |
| `_generate_drift_series()` | PSI series with optional spike |
| `_generate_prediction_cohorts()` | Performance by cohort using COHORT_DEFINITIONS |
| `_generate_feature_importance()` | Normalized importance scores |
| `_generate_feature_drift()` | Per-feature PSI with status |
| `_generate_feature_accuracy_drop()` | Per-feature accuracy drop with affected cohort |
| `_generate_data_quality()` | Missing rates, outlier rates, schema validation |
| `_generate_confusion_matrix()` | 2x2 matrix from predictions_today |
| `_get_classification_metrics()` | Full suite: accuracy/precision/recall/F1/AUC-ROC + drift + cohorts + features + DQ |
| `_get_regression_metrics()` | Full suite: R²/MAE/RMSE/MAPE + drift + cohorts + features + DQ |
| `_generate_policy_violations()` | 10 violation types across 5 categories |
| `_generate_voice_scores()` | 5 voice dimensions with 90-day trends |
| `_generate_agent_traces()` | Sample interaction traces from TRACE_TEMPLATES |

## Industry Data Structure

Each file in `industries/` exports:

```python
INDUSTRY_META = {"id": "hls", "name": "Healthcare & Life Sciences", "icon": "fa-heartbeat", "color": "#ef4444"}

PROJECTS = [
    {"id": "proj-1", "name": "...", "description": "...", "owner": "...", "created_date": "...", "status": "Active"},
    # ... 6 total
]

MODELS = [
    {
        "id": "model-1", "name": "...", "entity_type": "model",
        "project_id": "proj-X", "project_name": "...", "owner": "...",
        "model_type": "classification|regression", "algorithm": "...", "version": "...",
        "status": "Healthy|Warning|Degraded|Critical", "status_color": "...",
        "drift_score": 0.0-1.0, "performance_score": 0.0-1.0, "dqm_score": 0.0-1.0,
        "last_updated": "YYYY-MM-DD", "endpoint": "...",
        "predictions_today": int, "avg_latency_ms": int, "description": "...",
        "features": ["feature1", ..., "feature10"],
        "hipaa": {
            "phi_handling": "...", "data_classification": "...",
            "encryption_at_rest": bool, "encryption_in_transit": bool,
            "access_control": "...", "audit_logging": bool, "baa_signed": bool,
            "last_risk_assessment": "YYYY-MM-DD", "deid_method": "...",
            "min_necessary": bool, "retention_days": int, "compliant": bool,
        },
    },
    # ... 8 total, status distribution: 4 Healthy, 2 Warning, 1 Degraded, 1 Critical
]

AGENTS = [
    {
        "id": "agent-1", "name": "...", "entity_type": "agent",
        "project_id": "proj-X", "project_name": "...", "owner": "...",
        "framework": "Semantic Kernel|LangGraph|AutoGen",
        "llm_backbone": "GPT-4o|GPT-4o-mini", "version": "...",
        "status": "Operational|Warning|Degraded", "status_color": "...",
        "task_completion_rate": 0.0-1.0, "groundedness_score": 0.0-1.0,
        "safety_score": 0.0-1.0, "avg_cost_per_interaction": float,
        "last_updated": "YYYY-MM-DD", "endpoint": "...",
        "sessions_today": int, "avg_latency_ms": int, "description": "...",
        "tool_models": ["model-1", "model-2"],  # IDs of models this agent calls
        "tools": ["Model Name", "API Name", ...],
        "hipaa": { ... },  # same structure as models
    },
    # ... 4 total, status distribution: 2 Operational, 1 Warning, 1 Degraded
]

COHORT_DEFINITIONS = {
    "model-1": {"name": "Cohort Dimension Name", "segments": ["Seg1", "Seg2", "Seg3", "Seg4", "Seg5"]},
    # ... one per model ID
}

TRACE_TEMPLATES = {
    "agent-1": [
        {
            "query": "User question",
            "steps": [{"tool": "...", "action": "...", "latency_ms": int, "status": "success"}],
            "response": "Agent response text",
            "voice_score": 0.80-0.96,
            "policy_pass": bool,
            "policy_note": "optional failure reason",
        },
    ],
    # ... one list per agent ID
}
```

## CSS Classes (style.css)

| Class | Purpose |
|-------|---------|
| `.sidebar`, `.sidebar-header`, `.sidebar-nav`, `.sidebar-footer` | Left navigation panel |
| `.brand-mark` | Tredence "T" logo with angled clip-path |
| `.stat-card`, `.stat-card.total/healthy/warning/critical` | Summary metric cards |
| `.model-table` | Table container with shadow and rounded corners |
| `.status-badge`, `.status-badge.healthy/warning/critical/degraded/operational` | Color-coded status pills |
| `.score-indicator`, `.score-bar`, `.score-value` | Inline progress bar with value |
| `.score-good/score-warning/score-bad` | Semantic text colors |
| `.dash-card`, `.card-title` | Content card with icon title |
| `.metric-card`, `.metric-value`, `.metric-label` | Centered metric display with top border |
| `.dashboard-header`, `.model-name`, `.model-meta`, `.meta-item` | Entity header with metadata row |
| `.dash-tabs`, `.tab-content` | Tab navigation and content area |
| `.hipaa-badge`, `.hipaa-compliant/hipaa-non-compliant/hipaa-phi/hipaa-limited/hipaa-non-phi` | Compliance indicator pills |
| `.timeline`, `.timeline-item`, `.timeline-marker`, `.marker-production/marker-retired` | Version history timeline |
| `.trace-steps`, `.trace-step`, `.trace-step-marker`, `.trace-step-content` | Agent interaction trace steps |
| `.drift-bar`, `.drift-normal/drift-warning/drift-critical` | Colored progress bar for drift/DQ |
| `.confusion-matrix`, `.cm-tp/cm-tn/cm-fp/cm-fn` | 2x2 confusion matrix grid |
| `.project-card`, `.project-name`, `.project-stats` | Project listing cards |
| `.form-card` | Form container for onboarding |
| `.search-box` | Search input with icon |

## JS Files

| File | Global Variable | Charts Rendered | Init Pattern |
|------|----------------|-----------------|--------------|
| `dashboard.js` | `MODEL_DATA` | Performance trend (line), cohort bar, feature accuracy drop (h-bar), drift trend (line+thresholds), feature drift (h-bar), feature importance (h-bar), DQ missing/outlier (bar) | Performance tab immediate; others lazy via `shown.bs.tab` |
| `agent_dashboard.js` | `AD` | Agent perf trend (3-line), task breakdown (h-bar), cost trend (line), token trend (stacked bar), safety trend (line+threshold), voice dimensions (5-line) | Performance tab immediate; others lazy |
| `compare.js` | `MA`, `MB` | Performance comparison (2-line), drift comparison (2-line+thresholds), feature importance A (h-bar), feature importance B (h-bar) | All on DOMContentLoaded |

## SQLite Schema (ml_monitor.db)

```sql
CREATE TABLE projects (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT,
    owner TEXT NOT NULL, team TEXT, created_date TEXT, status TEXT DEFAULT 'Active'
);

CREATE TABLE onboarded_models (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model_name TEXT NOT NULL, project_id TEXT, model_type TEXT,
    algorithm TEXT, description TEXT, version TEXT, endpoint TEXT,
    owner TEXT, environment TEXT, primary_metric TEXT,
    drift_method TEXT, perf_threshold REAL, drift_threshold REAL,
    monitoring_frequency TEXT, features TEXT, created_date TEXT,
    FOREIGN KEY (project_id) REFERENCES projects(id)
);
```
