---
title: "How-To Guide"
description: "Operational procedures for common tasks in ML Works"
ms.date: 2026-08-03
ms.topic: how-to
---

## Generate Synthetic Telemetry Data

The synthetic data generator creates realistic CSV files for testing the ingestion pipeline without live system access.

### Default generation (HLS, 90 days)

```bash
python tools/generate_synthetic_data.py
```

This produces 7 CSV files and a manifest in `data/synthetic/`:

| File | Event Type | Description |
|------|-----------|-------------|
| `model_metrics.csv` | metric | Accuracy, precision, recall, F1, AUC-ROC time series |
| `drift_events.csv` | drift | PSI overall and per-feature drift measurements |
| `alerts.csv` | alert | Threshold breaches and anomaly events |
| `agent_traces.csv` | trace | Agent interaction logs with tool steps |
| `lifecycle_events.csv` | lifecycle | Deploy, retrain, config change events |
| `data_quality.csv` | metric | Per-feature missing rate, outlier rate, schema validity |
| `cohort_metrics.csv` | prediction | Fairness metrics across demographic cohorts |
| `manifest.json` | — | Entity mapping and file metadata |

### Customize generation

```bash
# Minimal set for quick smoke tests
python tools/generate_synthetic_data.py --days 7 --entities 2 --output-dir data/synthetic/quick

# Retail industry with specific scenarios
python tools/generate_synthetic_data.py --industry retail --days 90 --seed 99

# Without edge cases (no duplicates, missing fields, etc.)
python tools/generate_synthetic_data.py --no-edge-cases

# Large-scale generation
python tools/generate_synthetic_data.py --days 365 --seed 42 --output-dir data/synthetic/large
```

### CLI flags

| Flag | Default | Description |
|------|---------|-------------|
| `--industry` | `hls` | Industry dataset (`hls` or `retail`) |
| `--days` | `90` | Number of days of historical data |
| `--seed` | `42` | Random seed for reproducibility |
| `--entities` | all | Limit total entity count |
| `--scenarios` | auto | Comma-separated model scenarios |
| `--include-edge-cases` | enabled | Include duplicates, late arrivals, schema violations |
| `--no-edge-cases` | — | Disable edge case injection |
| `--output-dir` | `data/synthetic` | Output directory |

### Edge cases

When edge cases are enabled (default), the generator injects:

- **Duplicate rows** — identical events repeated to test deduplication
- **Late arrivals** — timestamps shifted 8 hours back from arrival time
- **Out-of-order events** — rows shuffled to test ordering logic
- **Missing fields** — blank `metric_value` columns to test validation
- **Schema violations** — non-numeric values in numeric columns

### Determinism

Same seed always produces byte-identical output. Use different seeds to generate varied test data:

```bash
python tools/generate_synthetic_data.py --seed 42   # Always the same
python tools/generate_synthetic_data.py --seed 43   # Different data, same structure
```

---

## Load Synthetic Data into the Metric Store

After generating synthetic CSVs, use the bulk loader to ingest them through the full pipeline (staging → mapping engine → metric store).

### Load with defaults

```bash
python tools/load_synthetic_data.py
```

This reads `data/synthetic/manifest.json`, registers all entities in the entity registry with aliases, parses CSVs into staging events, and runs the mapping engine to populate all metric store tables.

### Customize the load

```bash
# Use a different database file
python tools/load_synthetic_data.py --db-path my_test.db

# Use a different data directory
python tools/load_synthetic_data.py --data-dir data/synthetic/large
```

### End-to-end: generate and view live data

```bash
# Generate 90 days of HLS data
python tools/generate_synthetic_data.py --industry hls --days 90

# Load into the metric store
python tools/load_synthetic_data.py

# Start the app in live mode
$env:ML_WORKS_DATA_SOURCE = "live"
python app.py
```

---

## Switch Between Mock and Live Data

The application supports two data source modes controlled by configuration.

### Using config file

Edit `config/app.yaml`:

```yaml
data_source: mock   # Use mock data generators (default)
# data_source: live  # Query the metric store tables
```

### Using environment variable

```bash
# Windows PowerShell
$env:ML_WORKS_DATA_SOURCE = "live"
python app.py

# Linux/macOS
ML_WORKS_DATA_SOURCE=live python app.py
```

The environment variable overrides the YAML config.

### Behavior differences

| Mode | Entity source | Metrics | Alerts |
|------|--------------|---------|--------|
| `mock` | Industry modules (8 models, 4 agents per industry) | Generated deterministically | Generated from templates |
| `live` | `entity_registry` table (onboarded entities) | Queried from `metric_timeseries` | Queried from `alerts` table |

In `live` mode with no data, dashboards show "awaiting telemetry" states rather than crashing.

---

## Onboard a Model or Agent

### Via the UI

1. Navigate to `/onboard`
2. Toggle between **ML Model** and **Agent** using the button group
3. Fill in the required fields (name, project, type, version, endpoint, owner)
4. Configure monitoring thresholds
5. Submit

On submission, the entity is registered in:

- `onboarded_models` or `onboarded_agents` table (backward compatibility)
- `entity_registry` table (central identity for telemetry matching)
- `entity_aliases` table (name and endpoint aliases for connector resolution)

### Entity resolution

When live telemetry arrives, the system matches events to entities using aliases. The onboard flow creates these automatically:

| Alias Type | Value | Purpose |
|-----------|-------|---------|
| `onboard_name` | Entity name | Match by name |
| `endpoint` | Prediction endpoint | Match by API path |

---

## Run the Test Suite

```bash
# Install test dependencies
pip install pytest

# Run all tests
python -m pytest tests/ -v

# Run a specific module's tests
python -m pytest tests/test_entity_registry.py -v
python -m pytest tests/test_data_source_shapes.py -v
python -m pytest tests/test_synthetic_generator.py -v
python -m pytest tests/test_staging.py -v
python -m pytest tests/test_mapping_engine.py -v
python -m pytest tests/test_aggregation.py -v
python -m pytest tests/test_file_drop_e2e.py -v
python -m pytest tests/test_webhook_connector.py -v
python -m pytest tests/test_scheduler.py -v
python -m pytest tests/test_onboard_to_dashboard.py -v
python -m pytest tests/test_handlers.py -v
python -m pytest tests/test_ingestion_health.py -v
```

Current test count: 209+ tests across 12 modules.

---

## Migrate Existing Onboarded Entities

If you have entities in `onboarded_models` or `onboarded_agents` that were created before the entity registry existed, run the migration script:

```bash
python migrations/seed_entity_registry.py
```

This:

1. Finds rows where `entity_id IS NULL`
2. Generates a unique `entity_id` for each
3. Creates corresponding `entity_registry` and `entity_aliases` rows
4. Updates the original row with the new `entity_id`

Safe to re-run — skips already-migrated rows.

---

## Change Application Configuration

All settings are centralized in `config/app.yaml`:

```yaml
data_source: mock
db_path: ml_monitor.db
default_industry: hls

flask:
  debug: false
  port: 5000

ingestion:
  batch_size: 1000
  grace_period_hours: 6
  max_lag_alert_minutes: 30

aggregation:
  default_bucket: 1h
  retention_days: 90

connectors:
  - id: file-drop-local
    type: file_drop
    watch_directory: ./data/incoming
    processed_directory: ./data/processed
    file_pattern: "*.csv"
    column_mapping:
      entity_ref_column: source_entity_ref
      metric_name_column: metric_name
      value_column: metric_value
      timestamp_column: timestamp
```

### Environment variable overrides

Any top-level setting can be overridden with `ML_WORKS_` prefix:

| Config Key | Environment Variable |
|-----------|---------------------|
| `data_source` | `ML_WORKS_DATA_SOURCE` |
| `db_path` | `ML_WORKS_DB_PATH` |
| `default_industry` | `ML_WORKS_DEFAULT_INDUSTRY` |
| `flask.debug` | `ML_WORKS_FLASK_DEBUG` |
| `flask.port` | `ML_WORKS_FLASK_PORT` |

---

## Deploy to Azure

See [DEPLOYMENT.md](../DEPLOYMENT.md) for the full Azure App Service deployment process.

Quick redeploy:

```bash
Compress-Archive -Path app.py, database.py, data_source.py, config_loader.py, mock_data.py, requirements.txt, config, routes, static, templates, industries, ingestion, mappings -DestinationPath deploy.zip -Force
az webapp deploy --name tredence-mlworks --resource-group mlworks-rg --src-path deploy.zip --type zip --track-status false
Remove-Item deploy.zip
```

---

## Ingest Data Using the FileDropConnector

The FileDropConnector watches a directory for CSV/JSON files, parses them into Canonical Telemetry Events (CTEs), and feeds them through the ingestion pipeline.

### Set up the file drop directory

```bash
mkdir data/incoming
mkdir data/processed
```

### Configure the connector

In `config/app.yaml`:

```yaml
connectors:
  - id: file-drop-local
    type: file_drop
    watch_directory: ./data/incoming
    processed_directory: ./data/processed
    file_pattern: "*.csv"
    column_mapping:
      entity_ref_column: source_entity_ref
      metric_name_column: metric_name
      value_column: metric_value
      timestamp_column: timestamp
```

### Drop a CSV file

Place a CSV in the watch directory with these columns:

```csv
source_entity_ref,metric_name,metric_value,timestamp
mlflow://experiment-1/my-model,accuracy,0.934,2026-07-30T14:00:00Z
mlflow://experiment-1/my-model,precision,0.91,2026-07-30T14:00:00Z
```

The `source_entity_ref` must match an alias registered for an entity in the `entity_aliases` table.

### Process the file programmatically

```python
import sqlite3
from ingestion.connectors.file_drop import FileDropConnector
from ingestion.staging import insert_ctes
from ingestion.mapping_engine import MappingEngine
from pathlib import Path

# Create connector
config = {
    "id": "file-drop-local",
    "type": "file_drop",
    "watch_directory": "./data/incoming",
    "processed_directory": "./data/processed",
    "file_pattern": "*.csv",
    "column_mapping": {
        "entity_ref_column": "source_entity_ref",
        "metric_name_column": "metric_name",
        "value_column": "metric_value",
        "timestamp_column": "timestamp",
    },
}
connector = FileDropConnector(config)

# Poll for new files → CTEs
ctes = connector.poll()

# Insert into staging store
db = sqlite3.connect("ml_monitor.db")
db.row_factory = sqlite3.Row
inserted = insert_ctes(db, ctes)

# Run mapping engine to process CTEs → metric store
engine = MappingEngine(db, Path("mappings"))
result = engine.process_batch()
print(f"Mapped: {result['mapped']}, Rejected: {result['rejected']}")
```

### Supported file formats

| Format | Pattern | Parsing |
|--------|---------|---------|
| CSV | `*.csv` | `csv.DictReader`, one CTE per row |
| JSON | `*.json` | Array of objects, one CTE per object |

### Event type inference

If the CSV lacks an explicit `event_type` column, the connector infers it from the filename:

| Filename contains | Event type |
|-------------------|-----------|
| `drift` | `drift` |
| `alert` | `alert` |
| `trace` | `trace` |
| `lifecycle` | `lifecycle` |
| `quality` | `metric` |
| `cohort` | `prediction` |
| (anything else) | `metric` |

---

## Work with the Staging Store

The staging store is the append-only event log that sits between connectors and the mapping engine.

### Insert CTEs directly

```python
from ingestion.models import CanonicalTelemetryEvent
from ingestion.staging import compute_event_id, insert_single_cte, insert_ctes
import sqlite3

db = sqlite3.connect("ml_monitor.db")
db.row_factory = sqlite3.Row

# Compute deterministic event ID
event_id = compute_event_id("file_drop", "mlflow://exp/model", "metric", "2026-07-30T14:00:00Z", "accuracy")

cte = CanonicalTelemetryEvent(
    event_id=event_id,
    source_connector="file_drop",
    source_entity_ref="mlflow://exp/model",
    event_type="metric",
    timestamp="2026-07-30T14:00:00Z",
    received_at="2026-07-30T14:00:01Z",
    mapping_version="v1",
    payload={"metric_name": "accuracy", "metric_value": 0.934},
)

inserted = insert_single_cte(db, cte)  # True if new, False if duplicate
```

### Query pending events

```python
from ingestion.staging import fetch_pending_batch, count_by_status

pending = fetch_pending_batch(db, limit=100)
counts = count_by_status(db)  # {"pending": 50, "mapped": 200, "rejected": 3}
```

### Deduplication

Events are deduplicated by `event_id` (SHA-256 of connector + entity_ref + event_type + timestamp + metric_name). Inserting the same event twice silently drops the duplicate.

---

## Create Mapping Definitions

Mapping definitions are YAML files in the `mappings/` directory that tell the mapping engine how to process CTEs.

### Minimal metric mapping

```yaml
version: "1"
applies_to:
  source_connector: file_drop
  event_type: metric
entity_resolution:
  strategy: lookup
  on_no_match: reject
field_mappings:
  - source: payload.metric_value
    target: metric_timeseries.value
    transform: identity
validation_rules:
  - rule: not_null
    field: value
  - rule: numeric
    field: value
target_table: metric_timeseries
```

### Available transforms

| Transform | Syntax | Example |
|-----------|--------|---------|
| `identity` | `identity` | Pass through unchanged |
| `clamp` | `clamp(0, 1)` | Clip to range |
| `scale` | `scale(100)` | Multiply by factor |
| `round` | `round(4)` | Round to N decimals |

### Available validation rules

| Rule | Parameters | Rejects when |
|------|-----------|-------------|
| `not_null` | — | Value is None or empty |
| `numeric` | — | Value is not a number |
| `range` | `min`, `max` | Value outside range |
| `timestamp_not_future` | `tolerance_minutes` | Timestamp ahead of now |

### Entity resolution strategies

| Strategy | Behavior |
|----------|----------|
| `lookup` | Match `source_entity_ref` against `entity_aliases` table |
| `reject` | On no match: mark CTE as rejected |
| `skip` | On no match: silently drop |

---

## Aggregate Metrics into Time Buckets

The aggregation engine rolls raw metric rows into hourly or daily buckets for dashboard performance.

### Aggregate all data for an entity

```python
from ingestion.aggregation import aggregate_entity_metric
import sqlite3

db = sqlite3.connect("ml_monitor.db")
db.row_factory = sqlite3.Row

# Aggregate accuracy into 1-hour buckets using 'last' value
buckets_written = aggregate_entity_metric(db, "model-123", "accuracy", "1h", "last")
```

### Aggregation methods

| Method | Behavior |
|--------|----------|
| `last` | Last value in the bucket (default) |
| `mean` | Average of all values |
| `max` | Maximum value |
| `min` | Minimum value |
| `sum` | Sum of all values |

### Grace period

Events within the grace period (default 6 hours) trigger re-aggregation of their bucket. Events outside the grace period are stored in staging but do not update aggregated data.

```python
from ingestion.aggregation import aggregate_after_mapping

# Called after mapping engine writes a metric — only re-aggregates if recent
updated = aggregate_after_mapping(db, "model-123", "accuracy",
                                   "2026-07-30T14:00:00Z", "1h", "last",
                                   grace_period_hours=6)
```

### Dashboard reads from agg table

When `data_source=live`, the dashboard prefers `metric_timeseries_agg` for chart data. If no aggregated data exists, it falls back to raw `metric_timeseries` rows.

---

## Ingest Data via the Webhook API

The webhook endpoint accepts telemetry via HTTP POST with HMAC-SHA256 authentication.

### Endpoint

```text
POST /api/ingest/webhook
```

### Send a metric event

```bash
# Compute HMAC signature
SECRET="your-webhook-secret"
BODY='{"source_entity_ref":"mlflow://exp-1/model-a","event_type":"metric","timestamp":"2026-07-30T14:00:00Z","payload":{"metric_name":"accuracy","metric_value":0.934}}'
SIGNATURE=$(echo -n "$BODY" | openssl dgst -sha256 -hmac "$SECRET" | awk '{print $2}')

curl -X POST http://localhost:5000/api/ingest/webhook \
  -H "Content-Type: application/json" \
  -H "X-Webhook-Signature: sha256=$SIGNATURE" \
  -d "$BODY"
```

### Response codes

| Code | Meaning | When |
|------|---------|------|
| 201 | Created | Event accepted into staging |
| 400 | Bad Request | Missing fields, invalid JSON, wrong Content-Type |
| 401 | Unauthorized | Invalid or missing HMAC signature |
| 409 | Conflict | Duplicate event (content or idempotency key) |
| 429 | Too Many Requests | Rate limit exceeded |

### Idempotency

Include the `X-Idempotency-Key` header to prevent duplicate processing on retries:

```bash
curl -X POST http://localhost:5000/api/ingest/webhook \
  -H "Content-Type: application/json" \
  -H "X-Webhook-Signature: sha256=$SIGNATURE" \
  -H "X-Idempotency-Key: unique-request-123" \
  -d "$BODY"
```

### Configure the webhook secret

Set the secret via environment variable:

```bash
export WEBHOOK_SECRET="your-secret-here"
```

Or in `config/app.yaml`:

```yaml
connectors:
  - id: webhook-receiver
    type: webhook
    secret_env_var: WEBHOOK_SECRET
    rate_limit: 100
    rate_capacity: 200
```

Without a secret configured, the webhook accepts all requests (development mode only).

### Rate limiting

The webhook uses a token bucket rate limiter. Default: 100 requests/second with burst capacity of 200. Configure via the connector config.
