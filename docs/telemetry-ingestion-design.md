---
title: "Telemetry Ingestion Design"
description: "Architecture and plan for ingesting real model and agent telemetry into ML Works"
ms.date: 2026-07-30
ms.topic: design
---

## Problem Statement

ML Works currently renders monitoring views from deterministic mock data. To deliver production value, the application must ingest real telemetry from deployed models and agents, map heterogeneous source schemas to the internal entity model, and do so repeatably without manual intervention.

## Design Goals

| Goal | Constraint |
|------|-----------|
| Ingest from multiple telemetry sources (MLflow, Azure ML, OpenTelemetry, custom REST) | No single-vendor lock-in |
| Map arbitrary source schemas to the ML Works entity model | Mapping must be declarative, versioned, and auditable |
| Handle late-arriving, duplicate, and out-of-order events | Exactly-once semantics at the application layer |
| Remain compatible with mock data for demos and development | Feature flag to switch between real and mock data |
| Scale from single-model prototypes to hundreds of entities | Horizontal ingestion workers without app redesign |

## High-Level Architecture

```text
┌──────────────────────────────────────────────────────────────────────┐
│                        Telemetry Sources                              │
│  MLflow Tracking │ Azure ML │ OpenTelemetry │ Custom HTTP │ File Drop│
└────────┬─────────┴────┬─────┴───────┬───────┴──────┬──────┴────┬─────┘
         │              │             │              │           │
         ▼              ▼             ▼              ▼           ▼
┌──────────────────────────────────────────────────────────────────────┐
│                      Connector Layer                                  │
│                                                                      │
│  Each connector:                                                     │
│    1. Authenticates to source                                        │
│    2. Pulls/receives raw events (poll or webhook)                    │
│    3. Normalizes to Canonical Telemetry Event (CTE) schema           │
│    4. Writes CTEs to the staging store                               │
│                                                                      │
│  Connectors are pluggable Python classes registered in config.       │
└──────────────────────────┬───────────────────────────────────────────┘
                           │ CTEs
┌──────────────────────────▼───────────────────────────────────────────┐
│                      Staging Store                                    │
│                                                                      │
│  Append-only event log. Each CTE is written with:                    │
│    event_id (UUID), source_connector, source_entity_ref,             │
│    event_type, timestamp, received_at, payload (JSON),               │
│    mapping_version, processing_status                                │
│                                                                      │
│  Implementation: SQLite (dev) / PostgreSQL (prod) / Event Hub (scale)│
└──────────────────────────┬───────────────────────────────────────────┘
                           │
┌──────────────────────────▼───────────────────────────────────────────┐
│                   Mapping & Transform Engine                          │
│                                                                      │
│  Reads CTEs from staging, applies mapping definitions to produce     │
│  materialized metric rows for the ML Works entity model.             │
│                                                                      │
│  Steps:                                                              │
│    1. Entity Resolution — match CTE to an ML Works entity            │
│    2. Schema Mapping — apply field-level transforms via config       │
│    3. Aggregation — roll up events into time-bucketed metrics        │
│    4. Validation — reject rows failing business rules                │
│    5. Write — upsert into the Metric Store                           │
│                                                                      │
│  All mappings are YAML files versioned alongside the app.            │
└──────────────────────────┬───────────────────────────────────────────┘
                           │
┌──────────────────────────▼───────────────────────────────────────────┐
│                      Metric Store                                     │
│                                                                      │
│  Materialized tables matching the existing get_*_metrics() return    │
│  shapes. The Flask app queries these instead of mock_data.py.        │
│                                                                      │
│  Tables:                                                             │
│    entity_registry, metric_timeseries, drift_snapshots,              │
│    cohort_metrics, feature_importance, data_quality,                  │
│    agent_traces, agent_tool_usage, alerts, lineage_events            │
│                                                                      │
│  Implementation: SQLite (dev) / PostgreSQL (prod)                    │
└──────────────────────────┬───────────────────────────────────────────┘
                           │
┌──────────────────────────▼───────────────────────────────────────────┐
│                      Flask App (app.py)                               │
│                                                                      │
│  Data source router:                                                 │
│    if DATA_SOURCE == "live":                                         │
│        query Metric Store                                            │
│    else:                                                             │
│        call mock_data.get_*() (existing behavior)                    │
└──────────────────────────────────────────────────────────────────────┘
```

## Canonical Telemetry Event (CTE) Schema

Every raw event from any source is normalized to this intermediate format before mapping.

```json
{
  "event_id": "uuid-v4",
  "source_connector": "mlflow | azureml | otel | custom",
  "source_entity_ref": "mlflow://experiment/run | azureml://endpoint/deployment",
  "event_type": "metric | prediction | drift | trace | alert | lifecycle",
  "timestamp": "2026-07-30T14:22:00Z",
  "received_at": "2026-07-30T14:22:01Z",
  "mapping_version": "v2",
  "payload": {
    "metric_name": "accuracy",
    "metric_value": 0.934,
    "dimensions": {"cohort": "age_65_plus", "feature": null},
    "metadata": {}
  },
  "processing_status": "pending | mapped | rejected | duplicate"
}
```

### Event Types

| Type | Description | Example Sources |
|------|-------------|-----------------|
| `metric` | A single numeric measurement | MLflow logged metric, Azure ML metric, custom POST |
| `prediction` | A batch or individual prediction record | Scoring endpoint log, inference server |
| `drift` | Feature or prediction distribution shift measurement | Evidently, Azure ML data drift monitor |
| `trace` | Agent interaction step log | OpenTelemetry span, LangSmith trace |
| `alert` | A threshold breach or anomaly detection event | Azure Monitor, custom rule engine |
| `lifecycle` | Entity version change, deployment, retirement | MLflow model registry, AzureML endpoint events |

## Mapping Definition Format

Mappings are YAML files in `mappings/` that declare how CTE fields map to ML Works metrics.

```yaml
# mappings/mlflow_classification.yaml
version: "2"
applies_to:
  source_connector: mlflow
  event_type: metric
  filter: "payload.metadata.model_type == 'classification'"

entity_resolution:
  strategy: lookup  # lookup | create | skip
  match_fields:
    - source: payload.metadata.registered_model_name
      target: entity_registry.source_name
    - source: payload.metadata.experiment_id
      target: entity_registry.source_experiment_id
  on_no_match: queue_for_review  # queue_for_review | auto_create | reject

field_mappings:
  - source: payload.metric_value
    target: metric_timeseries.value
    when: "payload.metric_name == 'accuracy'"
    transform: identity

  - source: payload.metric_value
    target: metric_timeseries.value
    when: "payload.metric_name == 'f1_score'"
    transform: identity

  - source: payload.metric_value
    target: drift_snapshots.psi_value
    when: "payload.metric_name == 'psi'"
    transform: clamp(0, 1)

aggregation:
  bucket: 1h  # 1h | 1d | raw
  method: last  # last | mean | max | min | sum

validation_rules:
  - field: target.value
    rule: "0 <= value <= 1"
    on_fail: reject_with_reason
  - field: timestamp
    rule: "timestamp <= now() + 5m"
    on_fail: reject_with_reason
```

### Entity Resolution Strategies

| Strategy | Behavior | When to Use |
|----------|----------|-------------|
| `lookup` | Match CTE to existing entity by configured fields | Default. Entities pre-registered via onboard flow. |
| `create` | Auto-create entity in registry if no match found | Development, auto-discovery scenarios. |
| `skip` | Silently drop events for unknown entities | Production with strict entity governance. |
| `queue_for_review` | Park in dead-letter queue for human review | Default safe choice. |

## Edge Cases and Mitigations

### 1. Duplicate Events

**Problem:** Network retries, at-least-once delivery, or polling overlaps can produce duplicate CTEs.

**Mitigation:**
- Each CTE gets a deterministic `event_id` derived from `(source_connector, source_entity_ref, event_type, timestamp, metric_name)`.
- Staging store enforces UNIQUE on `event_id`.
- INSERT OR IGNORE semantics — duplicates are silently dropped.
- For sources without natural idempotency keys (e.g., raw HTTP POSTs), require a client-provided `idempotency_key` header.

### 2. Late-Arriving Data

**Problem:** Events arrive after the aggregation window has closed (e.g., a metric from 3 hours ago arrives now).

**Mitigation:**
- Staging store records both `timestamp` (event time) and `received_at` (wall clock).
- The mapping engine processes events by `timestamp`, not `received_at`.
- Aggregation uses a configurable **grace period** (default: 6 hours). Events within the grace period trigger re-aggregation of the affected bucket.
- Events outside the grace period are accepted into the staging store (audit trail) but do NOT update materialized metrics unless manually triggered.
- A `late_event_count` metric tracks how often this occurs per connector.

### 3. Schema Evolution

**Problem:** Source systems change their telemetry schema (renamed fields, new metrics, changed types).

**Mitigation:**
- Mapping definitions are versioned (`version: "2"`). Each CTE records which mapping version processed it.
- When a CTE fails to map against the current version, it is parked with `processing_status: "rejected"` and a `rejection_reason`.
- A **schema drift detector** compares incoming CTE payloads against a learned schema fingerprint and raises an alert when >5% of events fail to parse.
- Rolling back a mapping version re-processes all CTEs for that version window from the staging store (replay capability).

### 4. Entity Identity Resolution Failures

**Problem:** The same model may appear with different names across MLflow (experiment name), Azure ML (endpoint name), and custom sources.

**Mitigation:**
- The `entity_registry` table supports multiple **aliases** per entity:
  ```
  entity_id | alias_type      | alias_value
  model-1   | mlflow_run      | exp-42/run-abc
  model-1   | azureml_endpoint| prod-churn-v3
  model-1   | display_name    | Churn Predictor
  ```
- Entity resolution checks ALL aliases, not just the primary name.
- A disambiguation UI shows unresolved CTEs with suggested matches (fuzzy name similarity + project context).

### 5. Partial Metric Sets

**Problem:** Some sources report accuracy but not precision/recall. The dashboard expects a complete metric suite.

**Mitigation:**
- The metric store allows NULLs for any non-required field.
- The Flask app's data access layer fills missing metrics with a `null` marker (not a zero).
- Templates render "No data" badges for null metrics instead of misleading zeros.
- A **completeness score** per entity tracks what percentage of expected metrics are populated.
- Mapping definitions declare `required: true|false` per field — required fields failing populate the completeness alert.

### 6. Burst Traffic and Backpressure

**Problem:** A model serving 10K predictions/second generates telemetry faster than the mapping engine processes.

**Mitigation:**
- The staging store is append-only and decoupled from the mapping engine. Writes never block.
- The mapping engine processes in configurable batch sizes (default: 1000 CTEs/batch).
- A high-water mark in the staging store triggers an alert if the processing lag exceeds a threshold (default: 30 minutes).
- For prediction-level telemetry, connectors pre-aggregate at the source into 1-minute summary buckets before emitting CTEs.

### 7. Clock Skew Across Sources

**Problem:** Different source systems have different clock offsets, causing ordering issues.

**Mitigation:**
- All timestamps in CTEs are UTC. Connectors are responsible for timezone normalization.
- The `received_at` timestamp is set by the ingestion layer (authoritative clock).
- Aggregation windows use event timestamps but tolerate ±5 minute jitter within a bucket.
- A clock skew alert fires if `abs(timestamp - received_at) > 10 minutes` for >1% of events from a connector.

### 8. Source Unavailability and Recovery

**Problem:** A connector cannot reach its source (network partition, API rate limit, credential expiry).

**Mitigation:**
- Each connector maintains a **cursor** (last successfully fetched timestamp or offset) persisted in the staging store.
- On failure, the connector logs the error, backs off exponentially (max 15 minutes), and retries from the cursor.
- After recovery, the connector replays from the cursor, and the deduplication layer prevents double-processing.
- A `connector_health` table tracks: last_success, last_failure, consecutive_failures, state (healthy | degraded | down).
- Connector state surfaces as a system health panel in the Flask UI.

### 9. Multi-Tenant / Multi-Industry Isolation

**Problem:** The app supports multiple industries. Telemetry for HLS entities must not leak into Retail views.

**Mitigation:**
- Every entity in `entity_registry` has an `industry_id` foreign key.
- The mapping engine tags each materialized metric row with `industry_id`.
- Flask queries always filter by `current_industry_id` (from session).
- The staging store does NOT filter by industry — it stores all CTEs globally for cross-industry audit.

### 10. Metric Semantics Conflict

**Problem:** "accuracy" from Source A is micro-averaged; from Source B it is macro-averaged. They are not the same number.

**Mitigation:**
- Mapping definitions support a `semantic_tag` field:
  ```yaml
  - source: payload.metric_value
    target: metric_timeseries.value
    semantic_tag: "accuracy_micro"
  ```
- The metric store records the semantic tag alongside the value.
- Dashboard aggregation groups by semantic tag, never mixes differently-tagged metrics.
- A **conflict detector** alerts when the same entity receives the same metric name with different semantic tags.

## Data Store Schema (Metric Store)

```sql
-- Central entity registry (replaces mock MODELS/AGENTS lists)
CREATE TABLE entity_registry (
    entity_id       TEXT PRIMARY KEY,
    entity_type     TEXT NOT NULL CHECK(entity_type IN ('model', 'agent')),
    industry_id     TEXT NOT NULL,
    project_id      TEXT NOT NULL,
    name            TEXT NOT NULL,
    status          TEXT DEFAULT 'Unknown',
    metadata        JSON,  -- algorithm, framework, llm_backbone, features, hipaa, etc.
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id)
);

CREATE TABLE entity_aliases (
    entity_id   TEXT NOT NULL,
    alias_type  TEXT NOT NULL,
    alias_value TEXT NOT NULL,
    PRIMARY KEY (entity_id, alias_type, alias_value),
    FOREIGN KEY (entity_id) REFERENCES entity_registry(entity_id)
);

-- Time-series metrics (accuracy, F1, latency, cost, etc.)
CREATE TABLE metric_timeseries (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_id       TEXT NOT NULL,
    metric_name     TEXT NOT NULL,
    semantic_tag    TEXT,
    timestamp       TEXT NOT NULL,
    value           REAL NOT NULL,
    dimensions      JSON,  -- {"cohort": "...", "feature": "..."}
    source_event_id TEXT,
    FOREIGN KEY (entity_id) REFERENCES entity_registry(entity_id)
);
CREATE INDEX idx_metric_ts_entity_time ON metric_timeseries(entity_id, metric_name, timestamp);

-- Drift measurements
CREATE TABLE drift_snapshots (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_id   TEXT NOT NULL,
    timestamp   TEXT NOT NULL,
    drift_type  TEXT NOT NULL,  -- psi | kl | js | wasserstein
    scope       TEXT NOT NULL,  -- overall | feature:<name>
    value       REAL NOT NULL,
    status      TEXT,           -- normal | warning | critical
    FOREIGN KEY (entity_id) REFERENCES entity_registry(entity_id)
);

-- Cohort-level metrics
CREATE TABLE cohort_metrics (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_id   TEXT NOT NULL,
    timestamp   TEXT NOT NULL,
    cohort_name TEXT NOT NULL,
    cohort_dim  TEXT NOT NULL,
    metric_name TEXT NOT NULL,
    value       REAL NOT NULL,
    sample_size INTEGER,
    FOREIGN KEY (entity_id) REFERENCES entity_registry(entity_id)
);

-- Feature importance snapshots
CREATE TABLE feature_importance (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_id   TEXT NOT NULL,
    timestamp   TEXT NOT NULL,
    feature     TEXT NOT NULL,
    importance  REAL NOT NULL,
    method      TEXT,  -- shap | permutation | gain
    FOREIGN KEY (entity_id) REFERENCES entity_registry(entity_id)
);

-- Data quality metrics
CREATE TABLE data_quality (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_id       TEXT NOT NULL,
    timestamp       TEXT NOT NULL,
    feature         TEXT NOT NULL,
    missing_rate    REAL,
    outlier_rate    REAL,
    schema_valid    BOOLEAN,
    row_count       INTEGER,
    FOREIGN KEY (entity_id) REFERENCES entity_registry(entity_id)
);

-- Agent traces
CREATE TABLE agent_traces (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_id       TEXT NOT NULL,
    trace_id        TEXT NOT NULL UNIQUE,
    timestamp       TEXT NOT NULL,
    query           TEXT,
    response        TEXT,
    total_latency   INTEGER,
    token_count     INTEGER,
    voice_score     REAL,
    policy_pass     BOOLEAN,
    policy_note     TEXT,
    FOREIGN KEY (entity_id) REFERENCES entity_registry(entity_id)
);

CREATE TABLE agent_trace_steps (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    trace_id    TEXT NOT NULL,
    step_order  INTEGER NOT NULL,
    tool        TEXT NOT NULL,
    action      TEXT,
    latency_ms  INTEGER,
    status      TEXT,
    FOREIGN KEY (trace_id) REFERENCES agent_traces(trace_id)
);

-- Alerts (replaces mock alert generation)
CREATE TABLE alerts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_id   TEXT NOT NULL,
    timestamp   TEXT NOT NULL,
    severity    TEXT NOT NULL CHECK(severity IN ('critical', 'high', 'medium', 'low')),
    alert_type  TEXT NOT NULL,
    title       TEXT NOT NULL,
    description TEXT,
    resolved    BOOLEAN DEFAULT FALSE,
    resolved_at TEXT,
    FOREIGN KEY (entity_id) REFERENCES entity_registry(entity_id)
);

-- Entity lifecycle / lineage
CREATE TABLE lineage_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_id   TEXT NOT NULL,
    timestamp   TEXT NOT NULL,
    event_type  TEXT NOT NULL,  -- deployed | retrained | config_change | retired
    version     TEXT,
    trigger     TEXT,
    metadata    JSON,
    FOREIGN KEY (entity_id) REFERENCES entity_registry(entity_id)
);

-- Staging store for raw CTEs
CREATE TABLE staging_events (
    event_id            TEXT PRIMARY KEY,
    source_connector    TEXT NOT NULL,
    source_entity_ref   TEXT NOT NULL,
    event_type          TEXT NOT NULL,
    timestamp           TEXT NOT NULL,
    received_at         TEXT NOT NULL,
    mapping_version     TEXT,
    payload             JSON NOT NULL,
    processing_status   TEXT DEFAULT 'pending',
    rejection_reason    TEXT,
    processed_at        TEXT
);
CREATE INDEX idx_staging_status ON staging_events(processing_status, received_at);
CREATE INDEX idx_staging_entity ON staging_events(source_entity_ref, timestamp);

-- Connector health tracking
CREATE TABLE connector_health (
    connector_id        TEXT PRIMARY KEY,
    connector_type      TEXT NOT NULL,
    config_hash         TEXT,
    cursor_value        TEXT,
    last_success        TEXT,
    last_failure        TEXT,
    consecutive_failures INTEGER DEFAULT 0,
    state               TEXT DEFAULT 'healthy',
    error_message       TEXT
);
```

## Connector Plugin Interface

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Iterator

@dataclass
class CanonicalTelemetryEvent:
    event_id: str
    source_connector: str
    source_entity_ref: str
    event_type: str  # metric | prediction | drift | trace | alert | lifecycle
    timestamp: str   # ISO 8601 UTC
    received_at: str
    mapping_version: str
    payload: dict
    processing_status: str = "pending"

class BaseConnector(ABC):
    """Plugin interface for telemetry source connectors."""

    @abstractmethod
    def connector_id(self) -> str:
        """Unique identifier for this connector instance."""

    @abstractmethod
    def poll(self, cursor: str | None) -> Iterator[CanonicalTelemetryEvent]:
        """Fetch new events since cursor. Yields CTEs."""

    @abstractmethod
    def health_check(self) -> bool:
        """Return True if the source is reachable."""

    def compute_event_id(self, source_entity_ref: str, event_type: str,
                         timestamp: str, metric_name: str | None) -> str:
        """Deterministic event ID for deduplication."""
        import hashlib
        key = f"{self.connector_id()}|{source_entity_ref}|{event_type}|{timestamp}|{metric_name or ''}"
        return hashlib.sha256(key.encode()).hexdigest()[:32]
```

## Connector Implementations (Planned)

| Connector | Source | Pull/Push | Auth |
|-----------|--------|-----------|------|
| `MLflowConnector` | MLflow Tracking Server | Poll (REST API) | Token / Basic |
| `AzureMLConnector` | Azure ML Workspace | Poll (SDK) | Service Principal |
| `OTelConnector` | OpenTelemetry Collector | Push (OTLP/HTTP) | mTLS / API Key |
| `FileDropConnector` | Local/blob CSV/JSON files | Poll (filesystem) | N/A |
| `WebhookConnector` | Generic HTTP POST | Push (Flask endpoint) | HMAC signature |

## Mapping Engine Processing Loop

```text
┌─────────────────────────────────────────────────────────┐
│  1. SELECT batch FROM staging_events                    │
│     WHERE processing_status = 'pending'                 │
│     ORDER BY timestamp ASC LIMIT 1000                   │
├─────────────────────────────────────────────────────────┤
│  2. For each CTE in batch:                              │
│     a. Find matching mapping definition (connector +    │
│        event_type + filter)                             │
│     b. Resolve entity (alias lookup → entity_registry)  │
│     c. Apply field_mappings + transforms                │
│     d. Run validation_rules                             │
│     e. If valid: write to metric store                  │
│        If invalid: mark rejected + reason               │
│     f. Update processing_status                         │
├─────────────────────────────────────────────────────────┤
│  3. Update connector cursor to max(timestamp) of batch  │
├─────────────────────────────────────────────────────────┤
│  4. Check aggregation windows needing refresh           │
│     Re-aggregate affected time buckets                  │
├─────────────────────────────────────────────────────────┤
│  5. Emit processing metrics:                            │
│     events_processed, events_rejected, lag_seconds      │
└─────────────────────────────────────────────────────────┘
```

## Flask Integration Pattern

The existing `mock_data.py` functions become a **fallback** behind a data source router:

```python
# data_source.py (new module)
import os

DATA_SOURCE = os.environ.get("ML_WORKS_DATA_SOURCE", "mock")  # "mock" | "live"

def get_model_metrics(entity_id):
    if DATA_SOURCE == "live":
        return _query_metric_store(entity_id, entity_type="model")
    else:
        import mock_data
        return mock_data.get_model_metrics(entity_id)
```

Routes in `app.py` switch from `mock_data.get_*()` to `data_source.get_*()`. The return shape is identical — no template changes required.

## Configuration File

```yaml
# config/ingestion.yaml
data_source: mock  # mock | live

connectors:
  - id: mlflow-prod
    type: mlflow
    endpoint: "http://mlflow.internal:5000"
    poll_interval_seconds: 60
    auth:
      type: token
      env_var: MLFLOW_TRACKING_TOKEN

  - id: azureml-workspace
    type: azureml
    subscription_id: "${AZURE_SUBSCRIPTION_ID}"
    resource_group: "${AZURE_RG}"
    workspace_name: "${AZURE_ML_WORKSPACE}"
    poll_interval_seconds: 300
    auth:
      type: service_principal
      env_var_prefix: AZURE_SP_

  - id: webhook-receiver
    type: webhook
    path: /api/ingest/webhook
    auth:
      type: hmac
      secret_env_var: WEBHOOK_SECRET

mapping_engine:
  batch_size: 1000
  grace_period_hours: 6
  max_lag_alert_minutes: 30

aggregation:
  default_bucket: 1h
  retention_days: 90
```

## Implementation Plan

### Phase 1: Foundation (Core Infrastructure)

| Step | Deliverable | Acceptance Criteria |
|------|-------------|---------------------|
| 1.1 | Metric Store schema migration | Tables created via `init_db()` alongside existing tables |
| 1.2 | `entity_registry` CRUD operations | Can register, alias, and look up entities |
| 1.3 | Staging store write path | CTEs can be inserted with deduplication |
| 1.4 | `data_source.py` router module | Routes to mock or live based on env var |
| 1.5 | Config loader (`config/ingestion.yaml`) | Validated config available at startup |

### Phase 2: Connector Framework

| Step | Deliverable | Acceptance Criteria |
|------|-------------|---------------------|
| 2.1 | `BaseConnector` ABC + registration | Connectors discoverable by config ID |
| 2.2 | `FileDropConnector` (simplest) | Ingests CSV/JSON from a watched directory |
| 2.3 | `WebhookConnector` (push path) | POST to `/api/ingest/webhook` creates CTEs |
| 2.4 | Connector health tracking | `connector_health` table updated on poll |
| 2.5 | Connector scheduler (APScheduler or thread pool) | Polls at configured intervals |

### Phase 3: Mapping Engine

| Step | Deliverable | Acceptance Criteria |
|------|-------------|---------------------|
| 3.1 | Mapping YAML loader + validator | Invalid mappings rejected at startup |
| 3.2 | Entity resolution logic | Alias-based lookup with configurable fallback |
| 3.3 | Field mapping + transform execution | Supports identity, clamp, rename, expression |
| 3.4 | Validation rule engine | Rejects invalid rows with reason |
| 3.5 | Aggregation engine (time bucketing) | Configurable bucket sizes, re-aggregation on late data |

### Phase 4: Production Connectors

| Step | Deliverable | Acceptance Criteria |
|------|-------------|---------------------|
| 4.1 | `MLflowConnector` | Polls experiments, extracts metrics + model registry events |
| 4.2 | `AzureMLConnector` | Pulls endpoint metrics + deployment events |
| 4.3 | `OTelConnector` | Receives OTLP/HTTP spans, maps to agent traces |
| 4.4 | Pre-built mapping definitions for each connector | One YAML per connector-entity-type combination |

### Phase 5: Observability and Operations

| Step | Deliverable | Acceptance Criteria |
|------|-------------|---------------------|
| 5.1 | Ingestion health dashboard (new Flask route) | Shows connector state, lag, rejection rates |
| 5.2 | Dead-letter queue UI | Unresolved CTEs reviewable and re-processable |
| 5.3 | Schema drift detection alerts | Fires when >5% parse failures from a connector |
| 5.4 | Replay capability | Re-process staging events for a time range |
| 5.5 | Metric completeness scoring | Per-entity completeness visible in cockpit |

## Testing Strategy

| Layer | Test Type | What It Validates |
|-------|-----------|-------------------|
| Connectors | Unit + integration (mocked HTTP) | CTE output matches expected schema for known inputs |
| Mapping engine | Unit (fixture CTEs → metric rows) | Transforms, validation, entity resolution |
| Deduplication | Unit (insert same event twice) | Second insert is no-op |
| Late arrival | Unit (event outside grace period) | Accepted to staging, not materialized |
| End-to-end | Integration (FileDropConnector → dashboard) | Drop a file, verify dashboard shows updated metric |
| Regression | Snapshot tests | `data_source.get_model_metrics()` return shape matches `mock_data.get_model_metrics()` shape |

## Migration Path

1. Deploy with `DATA_SOURCE=mock` (zero behavior change).
2. Register entities via onboard flow (populates `entity_registry`).
3. Configure one connector (FileDropConnector recommended for first pass).
4. Create mapping YAML for that connector.
5. Switch to `DATA_SOURCE=live` for a single project.
6. Validate dashboard renders correctly with real data.
7. Expand to additional connectors and projects.

## Open Questions

| # | Question | Impact | Recommended Default |
|---|----------|--------|---------------------|
| 1 | Should the staging store be in the same SQLite DB or separate? | Operational isolation vs. simplicity | Same DB for dev, separate for prod |
| 2 | Should connectors run in-process or as separate workers? | Scalability vs. deployment complexity | In-process (APScheduler) for Phase 1, workers for Phase 5+ |
| 3 | How long to retain raw staging events? | Storage cost vs. replay capability | 90 days, then archive to cold storage |
| 4 | Should the webhook endpoint require entity pre-registration? | Security vs. convenience | Yes — reject events for unknown entities by default |
| 5 | What is the maximum acceptable dashboard staleness? | UX expectation | 5 minutes for metrics, 1 minute for alerts |
