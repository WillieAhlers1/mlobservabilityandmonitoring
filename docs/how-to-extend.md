---
title: "How to Extend"
description: "Guide for adding new features, industries, entities, connectors, and handlers"
ms.date: 2026-08-03
ms.topic: how-to
---

## Adding a New Industry

1. Create `industries/your_industry.py` exporting: `INDUSTRY_META`, `PROJECTS` (6), `MODELS` (8), `AGENTS` (4), `COHORT_DEFINITIONS` (8), `TRACE_TEMPLATES` (4)
2. Follow the exact dict structure documented in [codebase-map.md](codebase-map.md)
3. Add entry to `AVAILABLE_INDUSTRIES` in `mock_data.py`:

```python
AVAILABLE_INDUSTRIES = {
    ...
    "your_id": "industries.your_industry",
}
```

4. No template changes needed — the industry switcher auto-discovers from `get_available_industries()`

### Status distribution convention

- Models: 4 Healthy, 2 Warning, 1 Degraded, 1 Critical
- Agents: 2 Operational, 1 Warning, 1 Degraded
- HIPAA non-compliant: 2 models + 1 agent per industry

## Adding a New Model Tab

1. Add tab button in `templates/dashboard.html` inside `#dashboardTabs`:

```html
<li class="nav-item">
    <button class="nav-link" data-bs-toggle="tab"
            data-bs-target="#your-tab" type="button">
        <i class="fas fa-icon me-1"></i> Tab Name
    </button>
</li>
```

2. Add tab pane inside `<div class="tab-content">`:

```html
<div class="tab-pane fade" id="your-tab" role="tabpanel">
    <!-- content here -->
</div>
```

3. If the tab needs charts, add data to `_get_classification_metrics()` and `_get_regression_metrics()` in `mock_data.py`, then add chart init logic in `static/js/dashboard.js` with lazy initialization:

```javascript
if (target === '#your-tab' && !inited.yourTab) {
    inited.yourTab = true;
    // Chart.js code here
}
```

## Adding a New Agent Tab

Same pattern as model tabs but in `templates/agent_dashboard.html` and `static/js/agent_dashboard.js`. Agent metrics come from `get_agent_metrics()`.

## Adding a New Alert Type

1. Add template to `model_alert_types` or `agent_alert_types` in `mock_data.get_alerts()`:

```python
{"type": "your_type", "icon": "fa-icon-name", "severity": "warning",
 "template": "Description with {model} placeholder"},
```

2. Add filter button in `templates/alerts.html`:

```html
<a href="{{ url_for('alerts', type='your_type', severity=severity_filter) }}"
   class="btn {{ 'btn-primary' if type_filter == 'your_type' else 'btn-outline-secondary' }}">Your Type</a>
```

## Adding a New Route

1. Add route function in the appropriate `routes/*.py` module (or create a new one and register it in `routes/__init__.py`)
2. Create template extending `base.html`:

```html
{% extends "base.html" %}
{% block title %}Page Title{% endblock %}
{% block page_title %}Page Title{% endblock %}
{% block content %}
<!-- content -->
{% endblock %}
```

3. Add sidebar link in `templates/base.html` inside `.sidebar-nav`

## Adding Fields to Models or Agents

1. Add field to the entity dict in all 4 industry files (`industries/*.py`)
2. If displayed in cockpit, update the table in `templates/cockpit.html`
3. If displayed in dashboard, update the relevant tab template
4. If used in metrics generation, update the corresponding `mock_data.py` function

## Key Patterns to Follow

- **Colors:** Use CSS variables (`var(--tr-orange)`, `var(--tr-teal)`, `var(--tr-green)`)
- **Score coloring:** Good = `#4c9a2a` (green), Warning = `#f59e0b` (amber), Bad = `#ef4444` (red)
- **Chart colors:** Orange `#ee6f27`, Teal `#0a9396`, Green `#4c9a2a` (match Tredence brand)
- **Status badges:** Use class `.status-badge.{status|lower}` — `healthy`, `warning`, `critical`, `degraded`, `operational`
- **Entity links:** Always use `url_for('dashboard', entity_id=entity.id)` (not `model_id`)
- **Random seeds:** Use `random.seed(hash(entity_id + "_suffix"))` for deterministic data per entity
- **Icons:** Models use `fa-cube`, agents use `fa-robot` (with teal color)
- **Template variables:** `model` for model entities, `agent` for agent entities, `metrics` for generated data

## Adding a New Connector

1. Create `ingestion/connectors/your_connector.py` implementing `BaseConnector`:

```python
from ingestion.connectors.base import BaseConnector
from ingestion.models import CanonicalTelemetryEvent

class YourConnector(BaseConnector):
    @property
    def connector_id(self) -> str:
        return self._config["id"]

    @property
    def connector_type(self) -> str:
        return "your_type"

    def poll(self) -> list[CanonicalTelemetryEvent]:
        # Fetch data from your source, return CTEs
        ...

    def health_check(self) -> bool:
        # Return True if source is reachable
        ...
```

2. Register the type in `ingestion/connector_registry.py`:

```python
from ingestion.connectors.your_connector import YourConnector

CONNECTOR_TYPES = {
    "file_drop": FileDropConnector,
    "webhook": WebhookConnector,
    "your_type": YourConnector,
}
```

3. Add connector config to `config/app.yaml`:

```yaml
connectors:
  - id: your-connector-id
    type: your_type
    # ... your connector-specific config
```

4. Create mapping definitions in `mappings/your_type_*.yaml` for each event type the connector produces.

## Adding a New Handler

Handlers route specific event types to specialized database tables.

1. Create `ingestion/handlers/your_handler.py`:

```python
class YourHandler:
    def write(self, db, entity_id, cte, mapped_fields):
        """Write the processed CTE to your target table."""
        db.execute(
            "INSERT INTO your_table (entity_id, timestamp, ...) VALUES (?, ?, ...)",
            (entity_id, cte.timestamp, ...),
        )
        db.commit()
```

2. Register in `ingestion/handlers/__init__.py`:

```python
from ingestion.handlers.your_handler import YourHandler

HANDLER_REGISTRY = {
    ...
    "your_event_type": YourHandler,
}
```

3. Create the target table in `database.py`'s `init_db()` function.

4. Add a live-mode query in `data_source.py` if the data should appear in dashboards.

## Adding a New Mapping Definition

Mapping definitions live in `mappings/` and are loaded automatically by the mapping engine.

1. Create `mappings/{connector_type}_{event_type}.yaml`:

```yaml
version: "1"
applies_to:
  source_connector: file_drop    # or webhook, your_type, etc.
  event_type: metric             # metric, drift, alert, trace, lifecycle, etc.
entity_resolution:
  strategy: lookup
  on_no_match: reject            # reject, skip, or queue_for_review
field_mappings:
  - source: payload.your_field
    target: metric_timeseries.value
    transform: identity           # identity, clamp(min,max), scale(factor), round(n)
    when: "payload.metric_name == 'your_metric'"  # optional condition
validation_rules:
  - rule: not_null
    field: value
  - rule: numeric
    field: value
  - rule: range
    field: value
    min: 0
    max: 1
target_table: metric_timeseries  # or use a handler via event type
```

2. No code changes needed — the mapping engine discovers YAML files at runtime.

## Adding a New Transform

1. Add your transform function to `ingestion/transforms.py`:

```python
def your_transform(value, **params):
    """Apply your transformation to the value."""
    return transformed_value
```

2. Register it in the `TRANSFORMS` dict in the same file:

```python
TRANSFORMS = {
    "identity": identity,
    "clamp": clamp,
    "scale": scale,
    "round": round_value,
    "your_transform": your_transform,
}
```

3. Use it in mapping definitions: `transform: your_transform(param1, param2)`
