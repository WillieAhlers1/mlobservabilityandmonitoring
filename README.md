---
title: "Tredence ML Works"
description: "ML model and AI agent observability platform with telemetry ingestion pipeline"
author: "Willie Ahlers"
ms.date: 2026-07-31
ms.topic: overview
---

## Overview

Tredence ML Works is a prototype web application demonstrating monitoring and observability for both ML models and AI agents in production. It supports 4 industries with runtime switching, providing comprehensive views of model health, agent performance, drift, data quality, compliance, fairness, policy enforcement, and version lineage.

**Live Demo:** [https://tredence-mlworks.azurewebsites.net](https://tredence-mlworks.azurewebsites.net)

**Source:** [https://github.com/WillieAhlers1/mlobservabilityandmonitoring](https://github.com/WillieAhlers1/mlobservabilityandmonitoring)

### Key Features

| Feature | Description |
|---------|-------------|
| **Cockpit** | Toggle between All/Models/Agents with entity-specific columns (status, HIPAA, drift, performance, DQM for models; safety, task completion, groundedness, cost for agents) |
| **Model Dashboard** | 7-tab deep-dive: Performance, Drift, Interpretability, Data Quality, Compliance, Equity |
| **Agent Dashboard** | 7-tab deep-dive: Performance, Tool Usage, Cost & Tokens, Safety, Compliance, Policy, Traces |
| **Alerts** | 70 alerts (model + agent) with filters for drift, performance, data quality, latency, safety, cost, groundedness |
| **Compare** | Side-by-side model comparison with overlaid performance and drift trends |
| **Projects** | Project cards showing models and agents with persistent creation (SQLite) |
| **Onboard** | 4-step registration wizard with monitoring configuration |
| **Lineage** | Version timeline with retrain/prompt-change triggers and performance deltas |
| **Industry Switcher** | Runtime switching between HLS, Industrials, Retail, and Hospitality datasets |

### Multi-Industry Support

Switch industries at runtime via the sidebar dropdown. Each industry provides 6 projects, 8 models, and 4 agents with domain-specific data:

| Industry | Icon | Example Models | Example Agents |
|----------|------|---------------|----------------|
| Healthcare & Life Sciences | heartbeat | Patient Readmission Risk, ADE Detector, Radiology Anomaly | Clinical Decision Support, Prior Auth, Trial Matching |
| Manufacturing & Industrial | industry | Equipment Failure Predictor, Defect Detection, Vibration Anomaly | Maintenance Scheduling, Quality Inspection, Supply Chain |
| Retail & E-Commerce | shopping-cart | Customer Churn, Product Recommendations, Dynamic Pricing | Personal Shopping, Pricing Strategy, Customer Service |
| Hospitality & Travel | concierge-bell | Guest Satisfaction, Rate Optimization, No-Show Predictor | Concierge, Revenue Management, Guest Recovery |

### Model Dashboard Tabs

- **Performance** — Accuracy, precision, recall, F1, AUC-ROC trends; prediction cohort analysis; feature accuracy drop; confusion matrix
- **Drift** — PSI trend with warning/critical thresholds; feature-level drift
- **Interpretability** — Global feature importance (SHAP); top feature insights
- **Data Quality** — Missing rates, outlier rates, distribution shift, schema validation
- **Compliance** — Technical and administrative safeguards; feature PHI sensitivity map
- **Equity** — Fairness metrics across 4 demographic dimensions; disparate impact with 4/5 rule

### Agent Dashboard Tabs

- **Performance** — Task completion, groundedness, safety trends (90 days); task breakdown by category; linked model health
- **Tool Usage** — Per-tool success rate, latency, call volume; ML model vs API classification
- **Cost & Tokens** — Daily cost trend, stacked input/output token chart, 30-day totals
- **Safety** — Safety score trend with threshold; event log (PHI detection, hallucination, content filter)
- **Compliance** — HIPAA safeguards (same structure as models)
- **Policy** — Voice/tone scoring (empathy, professionalism, reading level, brand consistency, clinical language); policy violation log with categories
- **Traces** — Step-by-step interaction traces with tool calls, latency, voice score, policy pass/fail, full response text

## Quickstart

### Prerequisites

- Python 3.9 or later
- pip

### Install dependencies

```bash
pip install -r requirements.txt
```

Dependencies: Flask, gunicorn, PyYAML.

### Run the application

```bash
python app.py
```

The application starts on [http://127.0.0.1:5000](http://127.0.0.1:5000).

### Navigate the prototype

1. Open [http://127.0.0.1:5000](http://127.0.0.1:5000) in your browser
2. Use the **Industry** dropdown at the bottom of the sidebar to switch datasets
3. The **Projects** page shows all projects with their models and agents
4. The **Cockpit** page shows the production model/agent table with toggle filter
5. Click any entity name or **Dashboard** button for the detailed view
6. Click **Lineage** on any dashboard to view version history
7. Use **Alerts** to see the filterable event log (model + agent alerts)

### Project structure

```text
ML Monitoring/
├── app.py                       # Flask routes, SQLite, entity registry
├── data_source.py               # Data router (mock ↔ live metric store)
├── config_loader.py             # Centralized YAML + env var configuration
├── mock_data.py                 # Mock data generators (industry modules)
├── requirements.txt             # Python dependencies
├── config/
│   └── app.yaml                 # Application configuration
├── data/
│   └── synthetic/               # Generated test telemetry data
├── tools/
│   └── generate_synthetic_data.py  # Synthetic telemetry generator CLI
├── migrations/
│   └── seed_entity_registry.py  # Migrate onboarded entities to registry
├── industries/                  # Industry data packages
│   ├── __init__.py
│   ├── hls.py                   # Healthcare & Life Sciences
│   ├── industrials.py           # Manufacturing & Industrial
│   ├── retail.py                # Retail & E-Commerce
│   └── hospitality.py           # Hospitality & Travel
├── static/
│   ├── css/style.css            # Tredence-themed stylesheet
│   └── js/
│       ├── dashboard.js         # Chart.js for model dashboard
│       ├── agent_dashboard.js   # Chart.js for agent dashboard
│       └── compare.js           # Chart.js for model comparison
├── templates/                   # Jinja2 templates
├── tests/                       # Automated test suite (pytest)
├── docs/                        # Architecture and design documentation
├── styling/
│   └── tredence-theme.css       # Brand token reference
├── DEPLOYMENT.md                # Azure deployment guide
└── README.md                    # This file
```

## Azure Deployment

The app is deployed to Azure App Service (Free tier, Central US). See [DEPLOYMENT.md](DEPLOYMENT.md) for the full deployment process.

| Resource | Value |
|----------|-------|
| Live URL | https://tredence-mlworks.azurewebsites.net |
| Subscription | `4758145a-611a-4660-bca4-cf297fbf7e78` |
| Resource Group | `mlworks-rg` |
| App Service | `tredence-mlworks` (Python 3.11, Linux, Free F1) |

### Redeploy after changes

```bash
cd "c:\Sandbox\ML Monitoring"
Compress-Archive -Path app.py, data_source.py, config_loader.py, mock_data.py, requirements.txt, config, static, templates, industries -DestinationPath deploy.zip -Force
az webapp deploy --name tredence-mlworks --resource-group mlworks-rg --src-path deploy.zip --type zip --track-status false
Remove-Item deploy.zip
```

## Technology

- **Backend**: Python / Flask
- **Frontend**: Bootstrap 5, Chart.js 4, Font Awesome 6
- **Database**: SQLite (entity registry, metric store, staging events)
- **Configuration**: YAML (`config/app.yaml`) with env var overrides (`ML_WORKS_*`)
- **Theme**: Tredence brand (Poppins font, orange #ee6f27, teal #0a9396, green #4c9a2a)
- **Data**: Deterministic mock data (default) or live metric store via `data_source` router
- **Testing**: pytest (89 automated tests across 3 test modules)
- **Hosting**: Azure App Service (Free F1 tier, Central US)

## Telemetry Ingestion Pipeline (In Progress)

The platform is being extended with a real telemetry ingestion system that can replace mock data with live metrics from deployed models and agents.

| Layer | Status | Description |
|-------|--------|-------------|
| Entity Registry | Complete | Central identity for all monitored entities |
| Data Source Router | Complete | Feature-flagged switching between mock and live |
| Synthetic Data Generator | Complete | CLI tool producing test CSVs for all event types |
| Staging Store | Planned | Append-only event log with deduplication |
| Mapping Engine | Planned | YAML-driven CTE → metric store transforms |
| Connectors | Planned | FileDropConnector, WebhookConnector |

See [docs/telemetry-ingestion-design.md](docs/telemetry-ingestion-design.md) for the full architecture and [docs/PROGRESS.md](docs/PROGRESS.md) for implementation status.

## Configuration

All settings live in `config/app.yaml` and can be overridden via environment variables:

| Setting | Env Variable | Default | Description |
|---------|-------------|---------|-------------|
| `data_source` | `ML_WORKS_DATA_SOURCE` | `mock` | `mock` or `live` |
| `db_path` | `ML_WORKS_DB_PATH` | `ml_monitor.db` | SQLite database path |
| `default_industry` | `ML_WORKS_DEFAULT_INDUSTRY` | `hls` | Startup industry |

## Running Tests

```bash
pip install pytest
python -m pytest tests/ -v
```

## Documentation

| Document | Description |
|----------|-------------|
| [docs/architecture.md](docs/architecture.md) | System diagram and data flow |
| [docs/how-to-guide.md](docs/how-to-guide.md) | Operational how-to procedures |
| [docs/how-to-extend.md](docs/how-to-extend.md) | Adding industries, tabs, routes |
| [docs/telemetry-ingestion-design.md](docs/telemetry-ingestion-design.md) | Ingestion pipeline design |
| [docs/implementation-plan-telemetry-ingestion.md](docs/implementation-plan-telemetry-ingestion.md) | Multi-session implementation plan |
| [docs/PROGRESS.md](docs/PROGRESS.md) | Session progress tracker |
