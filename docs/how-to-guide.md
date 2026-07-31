---
title: "How-To Guide"
description: "Operational procedures for common tasks in ML Works"
ms.date: 2026-07-31
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

# Run a specific session's tests
python -m pytest tests/test_entity_registry.py -v
python -m pytest tests/test_data_source_shapes.py -v
python -m pytest tests/test_synthetic_generator.py -v
```

Current test count: 89 tests across 3 modules.

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
Compress-Archive -Path app.py, data_source.py, config_loader.py, mock_data.py, requirements.txt, config, static, templates, industries -DestinationPath deploy.zip -Force
az webapp deploy --name tredence-mlworks --resource-group mlworks-rg --src-path deploy.zip --type zip --track-status false
Remove-Item deploy.zip
```
