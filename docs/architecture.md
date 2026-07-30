---
title: "Architecture Overview"
description: "System architecture and data flow for Tredence ML Works"
ms.date: 2026-07-30
ms.topic: concept
---

## System Architecture

Tredence ML Works is a single-process Flask application with no external service dependencies. All data is generated deterministically from mock data modules, making it fully self-contained.

### Component Diagram

```text
┌─────────────────────────────────────────────────────────┐
│                      Browser                            │
│  Bootstrap 5 + Chart.js 4 + Font Awesome 6              │
└──────────────────────┬──────────────────────────────────┘
                       │ HTTP
┌──────────────────────▼──────────────────────────────────┐
│                    Flask (app.py)                        │
│                                                         │
│  Routes:                                                │
│    / (cockpit)          /dashboard/<id>                  │
│    /projects            /lineage/<id>                    │
│    /alerts              /compare                        │
│    /onboard             /switch-industry/<id>            │
│    /api/model/<id>/metrics                              │
│                                                         │
│  Context Processor:                                     │
│    current_industry, available_industries                │
│                                                         │
│  SQLite: projects, onboarded_models (persistent)        │
└──────────────────────┬──────────────────────────────────┘
                       │ imports
┌──────────────────────▼──────────────────────────────────┐
│               mock_data.py (Router)                     │
│                                                         │
│  Global state: PROJECTS, MODELS, AGENTS                 │
│  set_industry(id) swaps data at runtime                 │
│  Core generators: time series, drift, cohorts,          │
│    feature importance, data quality, confusion matrix   │
│  Agent generators: metrics, traces, policy, voice       │
│  Alert generator: model + agent alerts                  │
└──────────────────────┬──────────────────────────────────┘
                       │ importlib
┌──────────────────────▼──────────────────────────────────┐
│              industries/ (Data Packages)                 │
│                                                         │
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

### Data Flow

1. On startup, `mock_data.set_industry("hls")` loads the default industry
2. `PROJECTS`, `MODELS`, `AGENTS` module-level lists are populated from the industry file
3. Flask routes call `mock_data.get_*()` functions that read these lists
4. Generator functions (`_generate_time_series`, `_get_classification_metrics`, etc.) produce deterministic data using `random.seed(hash(entity_id))` for reproducibility
5. Templates render server-side via Jinja2; Chart.js data is injected as `{{ data | tojson }}`
6. Industry switching via `/switch-industry/<id>` calls `set_industry()` and redirects to Projects

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
├── cockpit.html        — toggle filter (All/Models/Agents) + dual tables
├── dashboard.html      — 7-tab model dashboard (Performance, Drift, Interpretability, DQ, Compliance, Equity)
├── agent_dashboard.html — 7-tab agent dashboard (Performance, Tools, Cost, Safety, Compliance, Policy, Traces)
├── alerts.html         — alert history with severity + type filters
├── compare.html        — side-by-side model comparison
├── projects.html       — project cards with models + agents listed
├── onboard.html        — 4-step registration form
└── lineage.html        — version timeline (shared by models and agents)
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
