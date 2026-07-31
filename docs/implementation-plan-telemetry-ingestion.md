---
title: "Telemetry Ingestion Implementation Plan"
description: "Multi-session implementation plan for staging store, mapping engine, and metric store"
ms.date: 2026-07-31
ms.topic: concept
---

## Overview

This plan covers the implementation of three core data layers from the telemetry ingestion design, plus their integration with the existing Flask app. Work is divided into sessions that each deliver a testable, shippable increment.

## Current State Assessment

| Component | Status | Notes |
|-----------|--------|-------|
| SQLite DB | Exists | Tables: `projects`, `onboarded_models`, `onboarded_agents` |
| Onboard flow | Works | Writes to DB but records are unused by dashboards |
| Dashboard data | Mock only | `mock_data.get_*()` generates everything from industry modules |
| Entity identity | Fragmented | Mock entities use `model-1` IDs; onboarded entities use autoincrement |
| Dependencies | Minimal | Flask + Gunicorn only |

### Critical Integration Insight

The onboard page currently writes to `onboarded_models` / `onboarded_agents` but these records are **never read by monitoring dashboards**. Dashboards consume `mock_data.MODELS` and `mock_data.AGENTS` lists. The telemetry system must bridge this gap: when the data source is `live`, onboarded entities become the source of truth via `entity_registry`.

---

## Session 1: Metric Store Schema and Entity Registry

### Goal

Create the metric store tables, the entity registry, and modify the onboard flow to write into `entity_registry` when entities are registered. This is the foundation everything else depends on.

### Deliverables

| # | Deliverable | File(s) |
|---|-------------|---------|
| 1.1 | Metric store schema creation in `init_db()` | `app.py` |
| 1.2 | `entity_registry` + `entity_aliases` tables | `app.py` |
| 1.3 | Onboard POST handler writes to `entity_registry` | `app.py` |
| 1.4 | Migration utility for existing `onboarded_*` rows into registry | `migrations/seed_entity_registry.py` |
| 1.5 | Unit tests for schema creation and entity registration | `tests/test_entity_registry.py` |

### Schema (from design doc, implemented in SQLite)

```sql
CREATE TABLE IF NOT EXISTS entity_registry (
    entity_id       TEXT PRIMARY KEY,
    entity_type     TEXT NOT NULL CHECK(entity_type IN ('model', 'agent')),
    industry_id     TEXT NOT NULL,
    project_id      TEXT NOT NULL,
    name            TEXT NOT NULL,
    status          TEXT DEFAULT 'Unknown',
    metadata        JSON,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id)
);

CREATE TABLE IF NOT EXISTS entity_aliases (
    entity_id   TEXT NOT NULL,
    alias_type  TEXT NOT NULL,
    alias_value TEXT NOT NULL,
    PRIMARY KEY (entity_id, alias_type, alias_value),
    FOREIGN KEY (entity_id) REFERENCES entity_registry(entity_id)
);
```

### Onboard Integration Logic

When a model/agent is onboarded:

1. Generate `entity_id` as `{entity_type}-{uuid4_short}` (e.g., `model-a3f2b1c8`)
2. INSERT into `entity_registry` with industry from session, project from form
3. INSERT aliases: `(entity_id, "onboard_name", model_name)`, `(entity_id, "endpoint", endpoint)`
4. Keep existing INSERT into `onboarded_models`/`onboarded_agents` for backward compat
5. Store `entity_id` as a new column in `onboarded_models`/`onboarded_agents`

### Functional Tests

| Test | Input | Expected |
|------|-------|----------|
| Schema creates all tables | Call `init_db()` on empty DB | All metric store tables exist |
| Onboard model writes registry | POST model form | Row in `entity_registry` with type=model |
| Onboard agent writes registry | POST agent form | Row in `entity_registry` with type=agent |
| Duplicate name different entity | Two POSTs same name | Two distinct entity_ids |
| Aliases created | POST with endpoint | Alias row for endpoint exists |
| Entity lookup by alias | Query alias_value | Returns correct entity_id |
| Migration script | Existing `onboarded_models` rows | Corresponding `entity_registry` rows created |

### Acceptance Criteria

- [ ] `init_db()` creates all tables from the design doc schema idempotently
- [ ] Onboard POST for model creates entity_registry + entity_aliases rows
- [ ] Onboard POST for agent creates entity_registry + entity_aliases rows
- [ ] `entity_id` column added to `onboarded_models` and `onboarded_agents`
- [ ] Migration script converts existing rows without data loss
- [ ] All tests pass with `pytest tests/test_entity_registry.py`

---

## Session 2: Data Source Router and Metric Store Read Path

### Goal

Create the `data_source.py` module that routes between mock and live data. Implement the read path from the metric store. When `DATA_SOURCE=mock`, behavior is identical to today. When `DATA_SOURCE=live`, it queries the metric store tables.

### Deliverables

| # | Deliverable | File(s) |
|---|-------------|---------|
| 2.1 | `data_source.py` router module | `data_source.py` |
| 2.2 | Live-mode query functions matching mock return shapes | `data_source.py` |
| 2.3 | `app.py` routes call `data_source` instead of `mock_data` directly | `app.py` |
| 2.4 | Feature flag via `ML_WORKS_DATA_SOURCE` env var | `data_source.py` |
| 2.5 | Snapshot tests: live return shape == mock return shape | `tests/test_data_source_shapes.py` |

### Router Design

```python
# data_source.py
import os
DATA_SOURCE = os.environ.get("ML_WORKS_DATA_SOURCE", "mock")

def get_model_metrics(entity_id):
    if DATA_SOURCE == "live":
        return _live_model_metrics(entity_id)
    import mock_data
    return mock_data.get_model_metrics(entity_id)
```

The router must implement these functions (matching mock_data signatures):

| Function | Return Shape | Used By |
|----------|-------------|---------|
| `get_model_metrics(id)` | `{model, metric_type, dates, metrics, drift, cohorts, ...}` | `/dashboard/<id>` |
| `get_agent_metrics(id)` | `{agent, dates, task_completion, groundedness, ...}` | `/dashboard/<id>` |
| `get_entity(id)` | Entity dict or None | `/dashboard/<id>`, `/lineage/<id>` |
| `get_model_lineage(id)` | `{model, versions, ...}` | `/lineage/<id>` |
| `get_agent_lineage(id)` | `{model, versions, ...}` | `/lineage/<id>` |
| `get_alerts()` | List of alert dicts | `/alerts` |
| `get_fairness_metrics(id)` | `{demographics, ...}` | `/dashboard/<id>` |
| `get_summary_stats_combined()` | Stats dict | `/` cockpit |
| `get_projects()` | List of project dicts | `/projects` |
| `MODELS` / `AGENTS` | Lists | cockpit, compare |

### Functional Tests

| Test | Input | Expected |
|------|-------|----------|
| Mock mode returns mock data | `DATA_SOURCE=mock`, call `get_model_metrics("model-1")` | Returns same dict as `mock_data.get_model_metrics("model-1")` |
| Live mode with empty DB | `DATA_SOURCE=live`, call `get_model_metrics("model-1")` | Returns None or empty structure (no crash) |
| Live mode with seeded data | Seed metric_timeseries rows, call `get_model_metrics` | Returns populated dict matching mock shape |
| Return shape parity | Both modes for all functions | Same top-level keys, same value types |
| Env var default | No env var set | Uses mock mode |
| app.py routes unchanged | GET `/dashboard/model-1` in mock mode | 200, same template renders |

### Acceptance Criteria

- [ ] `data_source.py` exists and all routes in `app.py` use it
- [ ] Setting `ML_WORKS_DATA_SOURCE=mock` produces identical behavior to current
- [ ] Setting `ML_WORKS_DATA_SOURCE=live` with empty DB returns graceful empty states
- [ ] Snapshot test confirms return shapes are structurally identical between modes
- [ ] No template changes required (shapes match exactly)

---

## Session 2.5: Synthetic Telemetry Data Generator

### Goal

Create a standalone script that generates realistic synthetic telemetry data in CSV format, covering all event types (metric, drift, alert, trace, lifecycle, prediction). These files serve as the primary test harness for the entire pipeline — from FileDropConnector through to dashboard rendering — since no live systems are available for integration.

### Deliverables

| # | Deliverable | File(s) |
|---|-------------|---------|
| 2.5.1 | Generator script with CLI interface | `tools/generate_synthetic_data.py` |
| 2.5.2 | CSV output for model metrics (classification + regression) | `data/synthetic/model_metrics.csv` |
| 2.5.3 | CSV output for drift measurements | `data/synthetic/drift_events.csv` |
| 2.5.4 | CSV output for alerts | `data/synthetic/alerts.csv` |
| 2.5.5 | CSV output for agent traces | `data/synthetic/agent_traces.csv` |
| 2.5.6 | CSV output for lifecycle/lineage events | `data/synthetic/lifecycle_events.csv` |
| 2.5.7 | CSV output for data quality metrics | `data/synthetic/data_quality.csv` |
| 2.5.8 | CSV output for cohort/fairness metrics | `data/synthetic/cohort_metrics.csv` |
| 2.5.9 | JSON manifest mapping files to entity references | `data/synthetic/manifest.json` |
| 2.5.10 | Unit tests for generator correctness | `tests/test_synthetic_generator.py` |

### Design Principles

| Principle | Rationale |
|-----------|-----------|
| Deterministic with seed | Same seed → same output; reproducible test runs |
| Mirrors mock_data patterns | Generates degradation curves, drift spikes, anomalies matching existing status scenarios |
| Entity references match entity_registry | Uses entity IDs that will be registered in Session 1's onboard flow |
| Covers edge cases | Includes duplicates, out-of-order timestamps, missing fields, and late arrivals |
| Configurable scale | CLI flags for number of entities, time range, event density |
| Industry-aware | Can generate data for any configured industry (HLS, Retail, etc.) |

### CSV Schemas

**model_metrics.csv**
```csv
source_entity_ref,metric_name,metric_value,timestamp,model_type,dimensions
mlflow://experiment-1/churn-model,accuracy,0.934,2026-07-30T14:00:00Z,classification,"{""cohort"": ""all""}"
mlflow://experiment-1/churn-model,precision,0.912,2026-07-30T14:00:00Z,classification,"{""cohort"": ""all""}"
```

**drift_events.csv**
```csv
source_entity_ref,drift_type,scope,value,timestamp,status
mlflow://experiment-1/churn-model,psi,overall,0.087,2026-07-30T14:00:00Z,normal
mlflow://experiment-1/churn-model,psi,feature:age,0.234,2026-07-30T14:00:00Z,critical
```

**alerts.csv**
```csv
source_entity_ref,severity,alert_type,title,description,timestamp
mlflow://experiment-1/churn-model,critical,drift_threshold,PSI Exceeded Threshold,Overall PSI 0.28 exceeds 0.25 threshold,2026-07-30T15:00:00Z
```

**agent_traces.csv**
```csv
source_entity_ref,trace_id,query,response,total_latency_ms,token_count,voice_score,policy_pass,timestamp,steps_json
agent://clinical-copilot,trace-001,What is patient risk?,Based on...,1250,890,0.91,true,2026-07-30T14:05:00Z,"[{""tool"":""EHR Lookup"",""latency_ms"":320,""status"":""success""}]"
```

**lifecycle_events.csv**
```csv
source_entity_ref,event_type,version,trigger,timestamp,metadata_json
mlflow://experiment-1/churn-model,deployed,v2.1.0,Scheduled retrain,2026-07-30T10:00:00Z,"{""training_records"": 50000}"
```

**data_quality.csv**
```csv
source_entity_ref,feature,missing_rate,outlier_rate,schema_valid,row_count,timestamp
mlflow://experiment-1/churn-model,age,0.02,0.005,true,10000,2026-07-30T14:00:00Z
```

**cohort_metrics.csv**
```csv
source_entity_ref,cohort_name,cohort_dim,metric_name,value,sample_size,timestamp
mlflow://experiment-1/churn-model,age_65_plus,age_group,accuracy,0.891,1500,2026-07-30T14:00:00Z
```

### CLI Interface

```bash
# Generate 90 days of data for 8 models + 4 agents (HLS industry)
python tools/generate_synthetic_data.py \
    --industry hls \
    --days 90 \
    --output-dir data/synthetic \
    --seed 42

# Generate with specific scenarios (degrading model, drifting features)
python tools/generate_synthetic_data.py \
    --industry hls \
    --days 90 \
    --scenarios healthy,degrading,critical,recovering \
    --include-edge-cases \
    --output-dir data/synthetic

# Generate minimal set for quick smoke tests
python tools/generate_synthetic_data.py \
    --industry hls \
    --days 7 \
    --entities 2 \
    --output-dir data/synthetic/quick
```

### Scenario Coverage

| Scenario | What It Generates | Tests |
|----------|-------------------|-------|
| Healthy model | Stable accuracy ~0.94, low drift | Happy path |
| Degrading model | Accuracy dropping over 30 days | Trend detection |
| Critical drift | PSI spike at day 50 | Alert triggering |
| Recovering model | Drop then improvement after retrain | Lifecycle events |
| Agent operational | Consistent task completion, low cost | Agent dashboard |
| Agent degraded | Rising latency, falling groundedness | Agent alerts |
| Duplicate events | Same event_id repeated 3x | Deduplication |
| Late arrivals | Events with timestamp 8h before received_at | Grace period |
| Out-of-order | Events arriving non-chronologically | Ordering logic |
| Missing fields | Rows with null metric_value | Validation rules |
| Schema violation | Wrong types in value columns | Rejection handling |
| Burst traffic | 500 events in same 1-minute window | Aggregation |

### Manifest File

The manifest links synthetic data to entity_registry entries so the FileDropConnector can resolve them:

```json
{
  "generated_at": "2026-07-31T10:00:00Z",
  "seed": 42,
  "industry": "hls",
  "entities": [
    {
      "entity_id": "model-synth-001",
      "entity_type": "model",
      "source_entity_ref": "mlflow://experiment-1/churn-model",
      "name": "Patient Readmission Predictor",
      "model_type": "classification",
      "scenario": "degrading",
      "project_id": "proj-hls-1"
    },
    {
      "entity_id": "agent-synth-001",
      "entity_type": "agent",
      "source_entity_ref": "agent://clinical-copilot",
      "name": "Clinical Decision Support Agent",
      "scenario": "operational",
      "project_id": "proj-hls-1"
    }
  ],
  "files": [
    {"path": "model_metrics.csv", "row_count": 12960, "event_type": "metric"},
    {"path": "drift_events.csv", "row_count": 720, "event_type": "drift"},
    {"path": "alerts.csv", "row_count": 45, "event_type": "alert"},
    {"path": "agent_traces.csv", "row_count": 2400, "event_type": "trace"},
    {"path": "lifecycle_events.csv", "row_count": 32, "event_type": "lifecycle"},
    {"path": "data_quality.csv", "row_count": 7200, "event_type": "metric"},
    {"path": "cohort_metrics.csv", "row_count": 4320, "event_type": "prediction"}
  ],
  "edge_cases": {
    "duplicate_event_ids": 15,
    "late_arrivals": 30,
    "out_of_order": 50,
    "missing_fields": 10,
    "schema_violations": 5
  }
}
```

### Integration with Other Sessions

| Session | How Synthetic Data Is Used |
|---------|---------------------------|
| Session 3 (Staging) | Load CSVs directly as CTEs to test dedup and batch insert |
| Session 4 (Mapping) | Feed staged CTEs through mapping engine, verify metric store output |
| Session 5 (Aggregation) | Burst traffic CSV tests aggregation bucketing |
| Session 6 (FileDropConnector) | Drop CSVs into watch directory for E2E test |
| Session 8 (Scheduler) | Trickle-feed files to test continuous processing |
| Session 9 (Onboard→Dashboard) | Register manifest entities, drop files, verify dashboard |
| Session 10 (Handlers) | Each CSV type exercises its respective handler |
| Session 11 (Health) | Edge case files trigger rejection/dead-letter scenarios |

### Functional Tests

| Test | Input | Expected |
|------|-------|----------|
| Generator produces valid CSV | Run with default args | All CSVs parse without error |
| Deterministic output | Same seed twice | Byte-identical files |
| Different seed, different data | Seed 42 vs 43 | Different values |
| Row counts match manifest | Generate + count rows | Manifest row_count is accurate |
| All entity_refs in manifest | Parse CSVs | Every source_entity_ref appears in manifest |
| Edge cases present | `--include-edge-cases` | Duplicates, late arrivals in output |
| Timestamps span full range | `--days 90` | Min timestamp ~90 days ago, max ~now |
| Industry-specific content | `--industry retail` | Entity names match retail domain |
| Minimal generation | `--days 1 --entities 1` | Small valid output |
| Large scale generation | `--days 365 --entities 50` | Completes without error, ~500K rows |

### Acceptance Criteria

- [ ] `python tools/generate_synthetic_data.py --help` shows CLI usage
- [ ] Default run produces all 7 CSV files + manifest.json
- [ ] Output is deterministic (same seed = same output)
- [ ] Generated data covers all 6 CTE event types
- [ ] Edge cases (duplicates, late arrivals, missing fields) are present
- [ ] Manifest correctly describes all generated entities and files
- [ ] Data patterns match realistic ML monitoring scenarios (drift curves, degradation)
- [ ] Files can be loaded by the FileDropConnector column mapping (Session 6)
- [ ] All tests pass with `pytest tests/test_synthetic_generator.py`

---

## Session 3: Staging Store and CTE Write Path

### Goal

Implement the staging store (append-only event log) and the CTE insertion logic with deduplication. This is the write side — events go in, duplicates are rejected.

### Deliverables

| # | Deliverable | File(s) |
|---|-------------|---------|
| 3.1 | `staging_events` table in `init_db()` | `app.py` |
| 3.2 | `ingestion/staging.py` module: insert, deduplicate, query | `ingestion/staging.py` |
| 3.3 | `ingestion/models.py`: CTE dataclass | `ingestion/models.py` |
| 3.4 | Deterministic event_id computation | `ingestion/staging.py` |
| 3.5 | Batch insert with dedup (INSERT OR IGNORE) | `ingestion/staging.py` |
| 3.6 | Status transitions: pending → mapped / rejected / duplicate | `ingestion/staging.py` |
| 3.7 | Unit tests for staging operations | `tests/test_staging.py` |

### CTE Dataclass

```python
@dataclass
class CanonicalTelemetryEvent:
    event_id: str
    source_connector: str
    source_entity_ref: str
    event_type: str
    timestamp: str
    received_at: str
    mapping_version: str
    payload: dict
    processing_status: str = "pending"
```

### Key Behaviors

| Behavior | Implementation |
|----------|---------------|
| Deduplication | `event_id` is SHA-256 hash of `(connector, entity_ref, type, timestamp, metric_name)` |
| Append-only | INSERTs only; no UPDATEs to payload; status field is the only mutable column |
| Batch writes | Accept list of CTEs, insert in single transaction |
| Idempotency | INSERT OR IGNORE — duplicate `event_id` silently dropped |
| Query pending | `SELECT WHERE processing_status='pending' ORDER BY timestamp LIMIT batch_size` |

### Functional Tests

| Test | Input | Expected |
|------|-------|----------|
| Insert single CTE | Valid CTE dict | Row in staging_events, status=pending |
| Insert duplicate | Same CTE twice | Only one row exists |
| Deterministic event_id | Same inputs | Same hash every time |
| Different event_id | Different timestamp | Different hash |
| Batch insert 100 CTEs | List of 100 | All 100 inserted |
| Batch with 3 duplicates | 100 CTEs, 3 repeated | 97 new inserts, 3 ignored |
| Query pending batch | 50 pending, 50 mapped | Returns 50 pending |
| Status transition | Mark as "mapped" | Status updated, processed_at set |
| Reject with reason | Mark as "rejected" | Status + rejection_reason set |
| Payload stored as JSON | Nested dict payload | Retrievable as dict |

### Acceptance Criteria

- [ ] `staging_events` table created by `init_db()`
- [ ] `insert_ctes()` handles single and batch inserts
- [ ] Duplicate CTEs are silently dropped (no errors)
- [ ] `fetch_pending_batch(limit)` returns oldest pending CTEs
- [ ] `mark_processed(event_id, status, reason=None)` transitions status
- [ ] All tests pass with `pytest tests/test_staging.py`

---

## Session 4: Mapping Engine Core (Entity Resolution + Field Mapping)

### Goal

Build the mapping engine that reads pending CTEs from the staging store, resolves them to entities, applies field-level transforms, validates, and writes to the metric store.

### Deliverables

| # | Deliverable | File(s) |
|---|-------------|---------|
| 4.1 | `ingestion/mapping_engine.py`: orchestrator | `ingestion/mapping_engine.py` |
| 4.2 | `ingestion/entity_resolution.py`: alias-based lookup | `ingestion/entity_resolution.py` |
| 4.3 | `ingestion/transforms.py`: identity, clamp, rename | `ingestion/transforms.py` |
| 4.4 | `ingestion/validation.py`: rule engine | `ingestion/validation.py` |
| 4.5 | YAML mapping loader | `ingestion/mapping_loader.py` |
| 4.6 | Example mapping definition | `mappings/example_classification.yaml` |
| 4.7 | Integration test: CTE → metric store row | `tests/test_mapping_engine.py` |

### Mapping Engine Processing Steps

```text
For each pending CTE:
  1. Find matching mapping definition (source_connector + event_type + filter)
  2. Resolve entity (alias lookup in entity_aliases → entity_registry)
  3. Apply field_mappings with transforms
  4. Run validation_rules
  5. If valid → INSERT into appropriate metric store table
  6. If invalid → mark CTE as rejected with reason
  7. Update CTE status to mapped/rejected
```

### Entity Resolution Logic

```python
def resolve_entity(cte: CTE, mapping: MappingDef, db) -> str | None:
    """Return entity_id or None if unresolvable."""
    for match_field in mapping.entity_resolution.match_fields:
        source_value = extract_field(cte, match_field.source)
        row = db.execute(
            "SELECT entity_id FROM entity_aliases WHERE alias_value = ?",
            (source_value,)
        ).fetchone()
        if row:
            return row["entity_id"]
    # Handle on_no_match strategy
    ...
```

### Transform Functions

| Transform | Behavior | Example |
|-----------|----------|---------|
| `identity` | Pass through unchanged | `0.934 → 0.934` |
| `clamp(min, max)` | Clip to range | `clamp(0, 1)`: `1.2 → 1.0` |
| `scale(factor)` | Multiply by factor | `scale(100)`: `0.93 → 93.0` |
| `rename` | No value change, maps to different target field | Source field → target field |
| `round(decimals)` | Round to N decimal places | `round(4)`: `0.93421 → 0.9342` |

### Validation Rules

| Rule | Syntax | Behavior |
|------|--------|----------|
| Range check | `"0 <= value <= 1"` | Reject if outside range |
| Not null | `"value is not None"` | Reject if null |
| Timestamp sanity | `"timestamp <= now() + 5m"` | Reject future timestamps |
| Type check | `"isinstance(value, float)"` | Reject wrong types |

### Functional Tests

| Test | Input | Expected |
|------|-------|----------|
| Resolve by alias | CTE with known alias | Returns correct entity_id |
| Resolve unknown alias | CTE with no matching alias | Returns None, applies on_no_match strategy |
| Identity transform | value=0.934 | metric_timeseries row with value=0.934 |
| Clamp transform | value=1.5 | Stored as 1.0 |
| Validation pass | value=0.85 with rule "0<=v<=1" | Row written |
| Validation fail | value=-0.5 with rule "0<=v<=1" | CTE marked rejected |
| YAML load valid | Well-formed mapping YAML | MappingDef object returned |
| YAML load invalid | Missing required field | Error raised at startup |
| End-to-end: CTE → metric row | Insert CTE, run engine | metric_timeseries has row |
| Batch processing | 100 pending CTEs | All processed (mapped or rejected) |
| No pending CTEs | Empty staging queue | Engine does nothing gracefully |
| Mapping filter matches | CTE matching filter expression | Correct mapping selected |
| Mapping filter no match | CTE not matching any mapping | CTE marked as rejected |

### Acceptance Criteria

- [ ] YAML mapping definitions load and validate at startup
- [ ] Entity resolution uses alias table to find entity_id
- [ ] All transform functions work correctly
- [ ] Validation rejects invalid data with clear reasons
- [ ] End-to-end: CTE inserted → engine run → metric_timeseries populated
- [ ] Rejected CTEs have `processing_status='rejected'` and `rejection_reason` set
- [ ] All tests pass with `pytest tests/test_mapping_engine.py`

---

## Session 5: Aggregation Engine and Time Bucketing

### Goal

Add time-bucketed aggregation to the mapping engine. Raw CTEs produce individual metric rows; the aggregation engine rolls them into time buckets (1h, 1d) for efficient dashboard queries.

### Deliverables

| # | Deliverable | File(s) |
|---|-------------|---------|
| 5.1 | `ingestion/aggregation.py`: bucket computation | `ingestion/aggregation.py` |
| 5.2 | Aggregation methods: last, mean, max, min, sum | `ingestion/aggregation.py` |
| 5.3 | Grace period handling for late-arriving data | `ingestion/aggregation.py` |
| 5.4 | Re-aggregation trigger for modified buckets | `ingestion/aggregation.py` |
| 5.5 | `metric_timeseries_agg` table for bucketed data | schema addition |
| 5.6 | Unit tests for aggregation logic | `tests/test_aggregation.py` |

### Aggregation Flow

```text
Raw metric_timeseries rows (many per hour)
    ↓ aggregate(entity_id, metric_name, bucket="1h", method="last")
metric_timeseries_agg rows (one per hour per metric)
    ↓ dashboard queries this table
Rendered chart with hourly data points
```

### Table Addition

```sql
CREATE TABLE IF NOT EXISTS metric_timeseries_agg (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_id   TEXT NOT NULL,
    metric_name TEXT NOT NULL,
    semantic_tag TEXT,
    bucket_start TEXT NOT NULL,  -- ISO 8601 start of bucket
    bucket_size  TEXT NOT NULL,  -- "1h" | "1d"
    agg_method   TEXT NOT NULL,  -- last | mean | max | min | sum
    value        REAL NOT NULL,
    sample_count INTEGER NOT NULL,
    UNIQUE(entity_id, metric_name, bucket_start, bucket_size)
);
```

### Functional Tests

| Test | Input | Expected |
|------|-------|----------|
| Aggregate 10 rows into 1h bucket (last) | 10 metrics in same hour | 1 agg row, value = last metric |
| Aggregate 10 rows (mean) | values [0.9, 0.91, 0.92, ...] | 1 agg row, value = mean |
| Multiple buckets | 24 hours of data | 24 agg rows |
| Late arrival within grace | Event 2h old arrives | Bucket re-aggregated |
| Late arrival outside grace | Event 12h old arrives (grace=6h) | Staging accepted, agg NOT updated |
| Re-aggregation correctness | New event in existing bucket | Agg value recalculated |
| Empty bucket | No events for an hour | No agg row (gaps allowed) |
| Dashboard query uses agg table | `get_model_metrics` in live mode | Reads from `metric_timeseries_agg` |

### Acceptance Criteria

- [ ] Aggregation produces one row per (entity, metric, bucket)
- [ ] All aggregation methods (last, mean, max, min, sum) work correctly
- [ ] Late events within grace period trigger re-aggregation
- [ ] Late events outside grace period do NOT alter agg table
- [ ] `data_source.py` live-mode queries read from agg table for time series charts
- [ ] All tests pass with `pytest tests/test_aggregation.py`

---

## Session 6: Connector Framework and FileDropConnector

### Goal

Implement the connector plugin system and the first concrete connector (FileDropConnector) to prove the full pipeline: file → CTE → staging → mapping → metric store → dashboard.

### Deliverables

| # | Deliverable | File(s) |
|---|-------------|---------|
| 6.1 | `ingestion/connectors/base.py`: BaseConnector ABC | `ingestion/connectors/base.py` |
| 6.2 | `ingestion/connectors/file_drop.py`: CSV/JSON file connector | `ingestion/connectors/file_drop.py` |
| 6.3 | `connector_health` table and health tracking | `ingestion/connectors/base.py` |
| 6.4 | Connector registry (discover by config ID) | `ingestion/connector_registry.py` |
| 6.5 | `config/ingestion.yaml` configuration file | `config/ingestion.yaml` |
| 6.6 | Config loader with validation | `ingestion/config_loader.py` |
| 6.7 | End-to-end integration test | `tests/test_file_drop_e2e.py` |

### FileDropConnector Behavior

1. Watches a configured directory for `.csv` and `.json` files
2. Reads new files (tracks processed files via cursor)
3. Parses rows into CTEs using column-to-CTE mapping from config
4. Writes CTEs to staging store
5. Moves processed files to `processed/` subdirectory

### Config Structure

```yaml
connectors:
  - id: file-drop-local
    type: file_drop
    watch_directory: "./data/incoming"
    processed_directory: "./data/processed"
    file_pattern: "*.csv"
    poll_interval_seconds: 30
    column_mapping:
      entity_ref_column: "model_name"
      metric_name_column: "metric"
      value_column: "value"
      timestamp_column: "timestamp"
```

### Functional Tests

| Test | Input | Expected |
|------|-------|----------|
| FileDropConnector reads CSV | Drop `metrics.csv` into watch dir | CTEs created for each row |
| FileDropConnector reads JSON | Drop `metrics.json` into watch dir | CTEs created for each record |
| File moved after processing | Process a file | File in `processed/` dir |
| Already-processed file ignored | Same file dropped again | No new CTEs |
| Connector health: healthy | Successful poll | `connector_health.state = 'healthy'` |
| Connector health: degraded | Watch dir doesn't exist | `connector_health.state = 'degraded'` |
| Config loads connectors | Valid `ingestion.yaml` | Connector instances registered |
| Invalid config rejected | Missing required field | Error at startup |
| End-to-end pipeline | Drop CSV → run engine → query dashboard | Metrics appear in live mode |

### Acceptance Criteria

- [ ] `BaseConnector` ABC defines `connector_id()`, `poll()`, `health_check()`
- [ ] `FileDropConnector` reads CSV/JSON files and produces valid CTEs
- [ ] Processed files are moved (not deleted) for audit
- [ ] Connector health is tracked in `connector_health` table
- [ ] Config file is loaded and validated at app startup
- [ ] E2E test: file drop → staging → mapping → metric store → API returns data
- [ ] All tests pass with `pytest tests/test_file_drop_e2e.py`

---

## Session 7: WebhookConnector and Ingestion API

### Goal

Add a push-based connector: an HTTP endpoint that external systems can POST telemetry to. This completes both pull (FileDropConnector) and push patterns.

### Deliverables

| # | Deliverable | File(s) |
|---|-------------|---------|
| 7.1 | `ingestion/connectors/webhook.py`: WebhookConnector | `ingestion/connectors/webhook.py` |
| 7.2 | Flask route: `POST /api/ingest/webhook` | `app.py` |
| 7.3 | HMAC signature verification | `ingestion/connectors/webhook.py` |
| 7.4 | Request validation (schema, required fields) | `ingestion/connectors/webhook.py` |
| 7.5 | Idempotency key support | `ingestion/connectors/webhook.py` |
| 7.6 | Rate limiting (basic: per-connector token bucket) | `ingestion/connectors/webhook.py` |
| 7.7 | Integration tests | `tests/test_webhook_connector.py` |

### Endpoint Specification

```text
POST /api/ingest/webhook
Headers:
  X-Webhook-Signature: sha256=<hmac_hex>
  X-Idempotency-Key: <optional client-provided key>
  Content-Type: application/json
Body:
  {
    "source_entity_ref": "mlflow://experiment-1/run-abc",
    "event_type": "metric",
    "timestamp": "2026-07-30T14:22:00Z",
    "payload": { "metric_name": "accuracy", "metric_value": 0.934, ... }
  }
Response:
  201 Created: {"event_id": "...", "status": "accepted"}
  400 Bad Request: {"error": "validation failure description"}
  401 Unauthorized: {"error": "invalid signature"}
  409 Conflict: {"error": "duplicate event", "event_id": "..."}
  429 Too Many Requests: {"error": "rate limit exceeded"}
```

### Functional Tests

| Test | Input | Expected |
|------|-------|----------|
| Valid POST with HMAC | Correct signature + body | 201, CTE in staging |
| Invalid HMAC | Wrong signature | 401 |
| Missing signature header | No X-Webhook-Signature | 401 |
| Missing required fields | No event_type | 400 |
| Duplicate idempotency key | Same key posted twice | First 201, second 409 |
| Rate limit exceeded | Burst of 1000 requests | 429 after limit |
| Unknown entity_ref | Valid POST, unknown entity | CTE accepted (status=pending) |
| Large payload | 1MB body | 400 (payload too large) |
| Content-Type validation | Non-JSON content type | 400 |

### Acceptance Criteria

- [ ] `POST /api/ingest/webhook` accepts valid telemetry events
- [ ] HMAC signature verification prevents unauthorized access
- [ ] Invalid requests return appropriate 4xx errors
- [ ] Idempotency keys prevent duplicate processing
- [ ] CTEs flow through the full pipeline to metric store
- [ ] All tests pass with `pytest tests/test_webhook_connector.py`

---

## Session 8: Connector Scheduler and Background Processing

### Goal

Wire connectors to run on a schedule (poll-based) and the mapping engine to process batches continuously. The app should ingest and process telemetry without manual intervention.

### Deliverables

| # | Deliverable | File(s) |
|---|-------------|---------|
| 8.1 | `ingestion/scheduler.py`: APScheduler integration | `ingestion/scheduler.py` |
| 8.2 | Connector polling at configured intervals | `ingestion/scheduler.py` |
| 8.3 | Mapping engine batch processing job | `ingestion/scheduler.py` |
| 8.4 | Graceful startup/shutdown | `app.py` |
| 8.5 | Processing lag metric | `ingestion/scheduler.py` |
| 8.6 | `apscheduler` added to requirements | `requirements.txt` |
| 8.7 | Integration tests for scheduled processing | `tests/test_scheduler.py` |

### Scheduler Design

```python
# Only starts when DATA_SOURCE == "live"
scheduler = BackgroundScheduler()

# Poll each connector at its configured interval
for connector in registered_connectors:
    scheduler.add_job(
        poll_connector, 'interval',
        seconds=connector.poll_interval,
        args=[connector]
    )

# Process staging queue every 10 seconds
scheduler.add_job(process_pending_batch, 'interval', seconds=10)
```

### Functional Tests

| Test | Input | Expected |
|------|-------|----------|
| Scheduler starts in live mode | `DATA_SOURCE=live` | Jobs registered |
| Scheduler does NOT start in mock mode | `DATA_SOURCE=mock` | No scheduler running |
| Connector polled on interval | Config: 30s interval | Poll called within 30s |
| Mapping engine runs on interval | Pending CTEs exist | Processed within 10s |
| Graceful shutdown | App stop signal | Scheduler shuts down cleanly |
| Processing lag computed | 50 pending CTEs, oldest 5min | Lag metric = 5 minutes |

### Acceptance Criteria

- [ ] APScheduler runs connector polls at configured intervals
- [ ] Mapping engine processes pending CTEs automatically
- [ ] Scheduler only activates when `DATA_SOURCE=live`
- [ ] App starts and stops cleanly with scheduler
- [ ] Processing lag is measurable
- [ ] All tests pass with `pytest tests/test_scheduler.py`

---

## Session 9: Onboard-to-Live Pipeline Integration

### Goal

Close the loop between the onboard page and live monitoring. When a user onboards an entity and a connector starts receiving telemetry for it, the dashboard should render real data without manual steps.

### Deliverables

| # | Deliverable | File(s) |
|---|-------------|---------|
| 9.1 | Onboard form adds connector configuration fields | `templates/onboard.html` |
| 9.2 | Entity registration creates aliases for connector matching | `app.py` |
| 9.3 | Dashboard graceful degradation (partial data) | `data_source.py` |
| 9.4 | Completeness score per entity | `ingestion/completeness.py` |
| 9.5 | "No data yet" UI states for newly onboarded entities | templates |
| 9.6 | Onboard → File Drop → Dashboard E2E test | `tests/test_onboard_to_dashboard.py` |

### Onboard Form Additions

New optional section in the onboard form: "Telemetry Source Configuration"

| Field | Purpose |
|-------|---------|
| Source Type | Dropdown: MLflow, Azure ML, File Drop, Webhook, Manual |
| Source Reference | Text: the identifier the connector uses (e.g., MLflow experiment name) |
| Endpoint/Path | Text: API URL or file path |
| Auth Method | Dropdown: None, Token, Service Principal |

When submitted:
- Creates `entity_aliases` entry with `alias_type="source_ref"` and the source reference value
- This is what entity resolution uses to match incoming CTEs to the entity

### Dashboard Graceful Degradation

When `DATA_SOURCE=live` and an entity has:
- No metrics yet → Show "Awaiting first telemetry" card
- Partial metrics (e.g., accuracy but no drift) → Show available data, "No data" badge for missing
- Full metrics → Normal dashboard render

### Functional Tests

| Test | Input | Expected |
|------|-------|----------|
| Onboard with source config | Fill form + source reference | entity_aliases has source_ref row |
| Connector matches onboarded entity | CTE with matching source_ref | Entity resolved correctly |
| Dashboard: no metrics | Live mode, new entity, no CTEs | "Awaiting telemetry" message |
| Dashboard: partial metrics | Only accuracy ingested | Accuracy chart renders, others show "No data" |
| Dashboard: full metrics | All expected metrics present | Full dashboard render |
| Completeness score | 3 of 5 expected metrics | Score = 60% |
| End-to-end onboard → dashboard | Onboard → drop file → view dashboard | Real metrics visible |

### Acceptance Criteria

- [ ] Onboard form has optional telemetry source configuration
- [ ] Source reference creates alias for connector matching
- [ ] Dashboard handles empty/partial/full metric states gracefully
- [ ] Completeness score is computed and accessible
- [ ] E2E test proves: onboard → file drop → dashboard shows data
- [ ] No regressions in mock mode
- [ ] All tests pass with `pytest tests/test_onboard_to_dashboard.py`

---

## Session 10: Drift, Alerts, and Specialized Metric Tables

### Goal

Extend the mapping engine to write to `drift_snapshots`, `alerts`, `cohort_metrics`, `feature_importance`, and `data_quality` tables. These are the specialized stores beyond simple time-series metrics.

### Deliverables

| # | Deliverable | File(s) |
|---|-------------|---------|
| 10.1 | Drift CTE handling → `drift_snapshots` | `ingestion/handlers/drift.py` |
| 10.2 | Alert CTE handling → `alerts` | `ingestion/handlers/alerts.py` |
| 10.3 | Cohort metric extraction → `cohort_metrics` | `ingestion/handlers/cohorts.py` |
| 10.4 | Feature importance → `feature_importance` | `ingestion/handlers/features.py` |
| 10.5 | Data quality → `data_quality` | `ingestion/handlers/data_quality.py` |
| 10.6 | Mapping YAML examples for each event type | `mappings/` |
| 10.7 | Live-mode query functions for each table | `data_source.py` |
| 10.8 | Unit tests per handler | `tests/test_handlers/` |

### Event Type → Table Routing

| CTE event_type | Target Table | Key Fields |
|----------------|-------------|------------|
| `metric` | `metric_timeseries` | metric_name, value, timestamp |
| `drift` | `drift_snapshots` | drift_type, scope, value, status |
| `alert` | `alerts` | severity, alert_type, title, description |
| `prediction` | `cohort_metrics` (post-aggregation) | cohort_name, metric_name, value |
| `lifecycle` | `lineage_events` | event_type, version, trigger |
| `trace` | `agent_traces` + `agent_trace_steps` | trace_id, steps, latency |

### Functional Tests

| Test | Input | Expected |
|------|-------|----------|
| Drift CTE → drift_snapshots | CTE with event_type=drift | Row in drift_snapshots |
| Alert CTE → alerts | CTE with event_type=alert, severity=critical | Row in alerts |
| Cohort CTE → cohort_metrics | CTE with cohort dimensions | Row per cohort |
| Feature importance CTE | CTE with importance payload | Rows in feature_importance |
| Data quality CTE | CTE with quality stats | Row in data_quality |
| Lifecycle CTE → lineage | CTE with event_type=lifecycle | Row in lineage_events |
| Trace CTE → agent_traces | CTE with steps array | Trace + step rows |
| Live mode alerts page | Alerts in DB | `/alerts` renders them |
| Live mode drift chart | Drift rows in DB | Dashboard drift section populated |

### Acceptance Criteria

- [ ] Each CTE event_type routes to the correct metric store table
- [ ] All specialized tables are queryable by the live-mode data source
- [ ] `/alerts` page renders alerts from DB in live mode
- [ ] Dashboard drift section uses drift_snapshots in live mode
- [ ] Agent dashboard uses agent_traces in live mode
- [ ] All tests pass with `pytest tests/test_handlers/`

---

## Session 11: Observability: Ingestion Health Dashboard and Dead-Letter Queue

### Goal

Provide visibility into the ingestion pipeline health: connector status, processing lag, rejection rates, and a UI for reviewing/reprocessing failed events.

### Deliverables

| # | Deliverable | File(s) |
|---|-------------|---------|
| 11.1 | `/ingestion/health` route and template | `app.py`, `templates/ingestion_health.html` |
| 11.2 | Connector state display (healthy/degraded/down) | template |
| 11.3 | Processing lag and throughput metrics | `ingestion/metrics.py` |
| 11.4 | `/ingestion/dead-letter` route: rejected CTEs UI | `app.py`, `templates/dead_letter.html` |
| 11.5 | Reprocess action for dead-letter items | `app.py` |
| 11.6 | Schema drift detection alert | `ingestion/drift_detector.py` |
| 11.7 | Tests for health and dead-letter endpoints | `tests/test_ingestion_health.py` |

### Health Dashboard Content

| Section | Data Source |
|---------|------------|
| Connector status cards | `connector_health` table |
| Events processed (last 1h / 24h) | COUNT on staging_events |
| Rejection rate | rejected / total ratio |
| Processing lag | max(received_at) - max(processed_at) for pending |
| Late event count | Events where `received_at - timestamp > grace_period` |

### Functional Tests

| Test | Input | Expected |
|------|-------|----------|
| Health page loads | GET `/ingestion/health` | 200, shows connector cards |
| Connector state shown | One healthy, one degraded | Cards show correct colors |
| Rejection rate calculated | 10 rejected out of 100 | Shows 10% |
| Dead-letter page loads | GET `/ingestion/dead-letter` | 200, shows rejected CTEs |
| Reprocess action | POST reprocess for CTE | Status reset to pending |
| Schema drift alert | >5% parse failures | Alert generated |
| Only visible in live mode | `DATA_SOURCE=mock` | Routes return 404 or redirect |

### Acceptance Criteria

- [ ] Ingestion health page shows real-time pipeline status
- [ ] Dead-letter queue shows rejected events with reasons
- [ ] Rejected events can be reprocessed
- [ ] Schema drift detection fires alerts
- [ ] Pages only accessible in live mode
- [ ] All tests pass

---

## Cross-Cutting Concerns (Apply Throughout All Sessions)

### Database Migrations

Each session may add tables. Use this pattern:

```python
def init_db():
    db = sqlite3.connect(DB_PATH)
    # Existing tables...
    # New tables (idempotent with IF NOT EXISTS)...
    # Schema version tracking
    db.execute("""CREATE TABLE IF NOT EXISTS schema_version (
        version INTEGER PRIMARY KEY, applied_at TEXT
    )""")
    db.commit()
    db.close()
```

### Testing Infrastructure (Set Up in Session 1)

```text
tests/
├── conftest.py          # Fixtures: temp DB, test client, CTE factories
├── test_entity_registry.py
├── test_synthetic_generator.py
├── test_data_source_shapes.py
├── test_staging.py
├── test_mapping_engine.py
├── test_aggregation.py
├── test_file_drop_e2e.py
├── test_webhook_connector.py
├── test_scheduler.py
├── test_onboard_to_dashboard.py
├── test_handlers/
│   ├── test_drift.py
│   ├── test_alerts.py
│   ├── test_cohorts.py
│   └── ...
└── test_ingestion_health.py
```

### Test Fixtures (conftest.py)

```python
@pytest.fixture
def test_db(tmp_path):
    """Create a temporary SQLite DB with full schema."""
    db_path = tmp_path / "test.db"
    # Run init_db() against this path
    ...

@pytest.fixture
def test_client(test_db):
    """Flask test client with test DB."""
    ...

@pytest.fixture
def sample_cte():
    """Factory for creating test CTEs."""
    def _make(event_type="metric", **overrides):
        ...
    return _make

@pytest.fixture
def registered_entity(test_db):
    """Insert an entity into entity_registry for testing."""
    ...
```

### Package Structure (Final State)

```text
ML Monitoring/
├── app.py
├── data_source.py              # Session 2
├── mock_data.py                # Existing (untouched)
├── tools/
│   └── generate_synthetic_data.py  # Session 2.5
├── data/
│   └── synthetic/              # Session 2.5 (generated output)
│       ├── manifest.json
│       ├── model_metrics.csv
│       ├── drift_events.csv
│       ├── alerts.csv
│       ├── agent_traces.csv
│       ├── lifecycle_events.csv
│       ├── data_quality.csv
│       └── cohort_metrics.csv
├── config/
│   └── ingestion.yaml          # Session 6
├── ingestion/
│   ├── __init__.py
│   ├── models.py               # Session 3 (CTE dataclass)
│   ├── staging.py              # Session 3
│   ├── mapping_engine.py       # Session 4
│   ├── entity_resolution.py    # Session 4
│   ├── transforms.py           # Session 4
│   ├── validation.py           # Session 4
│   ├── mapping_loader.py       # Session 4
│   ├── aggregation.py          # Session 5
│   ├── scheduler.py            # Session 8
│   ├── completeness.py         # Session 9
│   ├── metrics.py              # Session 11
│   ├── drift_detector.py       # Session 11
│   ├── config_loader.py        # Session 6
│   ├── connector_registry.py   # Session 6
│   ├── connectors/
│   │   ├── __init__.py
│   │   ├── base.py             # Session 6
│   │   ├── file_drop.py        # Session 6
│   │   └── webhook.py          # Session 7
│   └── handlers/
│       ├── __init__.py
│       ├── drift.py            # Session 10
│       ├── alerts.py           # Session 10
│       ├── cohorts.py          # Session 10
│       ├── features.py         # Session 10
│       └── data_quality.py     # Session 10
├── mappings/
│   └── example_classification.yaml  # Session 4
├── migrations/
│   └── seed_entity_registry.py      # Session 1
└── tests/
    ├── conftest.py
    └── ...
```

### Dependency Additions by Session

| Session | New Dependencies |
|---------|------------------|
| 1 | `pytest` (dev) |
| 2.5 | (none — stdlib csv/json/random/argparse only) |
| 3 | (none — stdlib only) |
| 4 | `pyyaml` |
| 6 | `pyyaml` (already added) |
| 7 | (none — Flask built-in) |
| 8 | `apscheduler>=3.10` |

### Risk Mitigations

| Risk | Mitigation |
|------|------------|
| Onboard regression | Mock mode is default; onboard still writes to existing tables |
| Template breakage | Return shapes enforced by snapshot tests (Session 2) |
| Performance at scale | Aggregation (Session 5) ensures dashboard queries are O(buckets) not O(events) |
| Partial implementation | Each session is independently deployable with `DATA_SOURCE=mock` as fallback |
| Data loss during dev | Staging store is append-only; rejected events are never deleted |

---

## Session Dependency Graph

```text
Session 1 ──→ Session 2 ──→ Session 2.5 ──→ Session 9
    │              │              │
    ▼              ▼              │ (test data for all below)
    │              │              ▼
Session 3 ──→ Session 4 ──→ Session 5
    │              │              │
    │              ▼              │
    │         Session 10 ←───────┘
    │
    ▼
Session 6 ──→ Session 7
    │
    ▼
Session 8 ──→ Session 11
```

Sessions 1-2 must come first. Session 2.5 follows immediately after.
- Session 2.5 (synthetic data) provides test data consumed by ALL subsequent sessions
- Sessions 3-5 (staging + mapping + aggregation) form a chain
- Sessions 6-8 (connectors + scheduler) form a parallel chain after Session 3
- Session 9 depends on both chains being complete
- Sessions 10-11 can happen any time after Session 4

---

## Definition of Done (Entire Feature)

The telemetry ingestion system is complete when:

1. A user can onboard an entity via the UI with telemetry source configuration
2. A FileDropConnector picks up a CSV of metrics for that entity
3. The staging store deduplicates and stores the raw events
4. The mapping engine resolves the entity, transforms values, validates, and writes to metric store
5. The aggregation engine produces time-bucketed data
6. The dashboard renders real metrics from the metric store
7. The ingestion health page shows pipeline status
8. Mock mode continues to work identically to current behavior
9. All automated tests pass
