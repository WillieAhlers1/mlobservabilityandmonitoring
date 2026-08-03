# Telemetry Ingestion — Progress Tracker

## Session 1: Metric Store Schema and Entity Registry

- [x] Metric store tables added to `init_db()`
- [x] `entity_registry` + `entity_aliases` tables created
- [x] `entity_id` column added to `onboarded_models` and `onboarded_agents`
- [x] Onboard POST writes to `entity_registry` (model)
- [x] Onboard POST writes to `entity_registry` (agent)
- [x] Onboard POST creates `entity_aliases` rows
- [x] Migration script for existing onboarded rows
- [x] `tests/conftest.py` with shared fixtures
- [x] `tests/test_entity_registry.py` passes (19/19)

## Session 2: Data Source Router and Metric Store Read Path

- [x] `data_source.py` created with router logic
- [x] All `app.py` routes use `data_source` instead of `mock_data` directly
- [x] Mock mode behaves identically to current
- [x] Live mode with empty DB returns graceful empty states
- [x] Snapshot tests confirm return shape parity
- [x] `tests/test_data_source_shapes.py` passes (46/46)

## Session 2.5: Synthetic Telemetry Data Generator

- [x] `tools/generate_synthetic_data.py` with CLI
- [x] `model_metrics.csv` generated
- [x] `drift_events.csv` generated
- [x] `alerts.csv` generated
- [x] `agent_traces.csv` generated
- [x] `lifecycle_events.csv` generated
- [x] `data_quality.csv` generated
- [x] `cohort_metrics.csv` generated
- [x] `manifest.json` generated
- [x] Edge cases included (duplicates, late arrivals, missing fields)
- [x] Output is deterministic (same seed = same files)
- [x] `tests/test_synthetic_generator.py` passes (24/24)

## Session 3: Staging Store and CTE Write Path

- [x] `staging_events` table in `init_db()`
- [x] `ingestion/models.py` with CTE dataclass
- [x] `ingestion/staging.py` with insert + dedup logic
- [x] Deterministic `event_id` computation
- [x] Batch insert (INSERT OR IGNORE)
- [x] `fetch_pending_batch(limit)` works
- [x] `mark_processed(event_id, status, reason)` works
- [x] `tests/test_staging.py` passes (25/25)

## Session 4: Mapping Engine Core

- [x] `ingestion/mapping_loader.py` loads and validates YAML
- [x] `ingestion/entity_resolution.py` resolves via aliases
- [x] `ingestion/transforms.py` (identity, clamp, scale, round)
- [x] `ingestion/validation.py` rule engine
- [x] `ingestion/mapping_engine.py` orchestrator
- [x] `mappings/file_drop_metrics.yaml` created
- [x] `mappings/file_drop_drift.yaml` created
- [x] End-to-end: CTE → metric_timeseries row
- [x] Rejected CTEs get status + reason
- [x] `tests/test_mapping_engine.py` passes (51/51)

## Session 5: Aggregation Engine and Time Bucketing

- [x] `ingestion/aggregation.py` created
- [x] `metric_timeseries_agg` table added
- [x] Aggregation methods: last, mean, max, min, sum
- [x] Grace period logic for late arrivals
- [x] Re-aggregation on modified buckets
- [x] `data_source.py` live mode reads from agg table
- [x] `tests/test_aggregation.py` passes (22/22)

## Session 6: Connector Framework and FileDropConnector

- [x] `ingestion/connectors/base.py` with BaseConnector ABC
- [x] `ingestion/connectors/file_drop.py` reads CSV/JSON
- [x] `connector_health` table created
- [x] `ingestion/connector_registry.py` discovers connectors by config
- [x] `config/app.yaml` updated with connector definition
- [x] `ingestion/config_loader.py` validates config
- [x] Processed files moved to `processed/` dir
- [x] E2E: file drop → staging → mapping → metric store → API
- [x] `tests/test_file_drop_e2e.py` passes (22/22)

## Session 7: WebhookConnector and Ingestion API

- [x] `ingestion/connectors/webhook.py` created
- [x] `POST /api/ingest/webhook` route in `app.py`
- [x] HMAC signature verification
- [x] Request validation (schema, required fields)
- [x] Idempotency key support
- [x] Proper error responses (400, 401, 409, 429)
- [x] `tests/test_webhook_connector.py` passes (32/32)

## Session 8: Connector Scheduler and Background Processing

- [x] `ingestion/scheduler.py` with APScheduler
- [x] Connectors polled at configured intervals
- [x] Mapping engine batch processing job
- [x] Scheduler only starts when `DATA_SOURCE=live`
- [x] Graceful startup/shutdown
- [x] Processing lag metric computed
- [x] `apscheduler` in `requirements.txt`
- [x] `tests/test_scheduler.py` passes (15/15)

## Session 9: Onboard-to-Live Pipeline Integration

- [x] Onboard form has telemetry source config fields
- [x] Source reference creates alias for connector matching
- [x] Dashboard: "Awaiting telemetry" state for new entities
- [x] Dashboard: partial metrics render with "No data" badges
- [x] Dashboard: full metrics render normally
- [x] Completeness score per entity
- [x] E2E: onboard → file drop → dashboard shows data
- [x] No regressions in mock mode
- [x] `tests/test_onboard_to_dashboard.py` passes (13/13)

## Session 10: Drift, Alerts, and Specialized Metric Tables

- [x] `ingestion/handlers/drift.py` → `drift_snapshots`
- [x] `ingestion/handlers/alerts.py` → `alerts`
- [x] `ingestion/handlers/cohorts.py` → `cohort_metrics`
- [x] `ingestion/handlers/features.py` → `feature_importance`
- [x] `ingestion/handlers/data_quality.py` → `data_quality`
- [x] Lifecycle events → `lineage_events`
- [x] Agent traces → `agent_traces` + `agent_trace_steps`
- [x] Live-mode queries for each table in `data_source.py`
- [x] `/alerts` renders from DB in live mode
- [x] `tests/test_handlers.py` passes (41/41)

## Session 11: Observability — Ingestion Health and Dead-Letter Queue

- [ ] `/ingestion/health` route and template
- [ ] Connector state display (healthy/degraded/down)
- [ ] Processing lag and throughput metrics
- [ ] `/ingestion/dead-letter` route and template
- [ ] Reprocess action for rejected CTEs
- [ ] Schema drift detection alert
- [ ] Pages only accessible in live mode
- [ ] `tests/test_ingestion_health.py` passes

---

## Quick Status

| Session | Status | Date Started | Date Completed |
|---------|--------|--------------|----------------|
| 1 | Complete | 2026-07-31 | 2026-07-31 |
| 2 | Complete | 2026-07-31 | 2026-07-31 |
| 2.5 | Complete | 2026-07-31 | 2026-07-31 |
| 3 | Complete | 2026-07-31 | 2026-07-31 |
| 4 | Complete | 2026-07-31 | 2026-07-31 |
| 5 | Complete | 2026-07-31 | 2026-07-31 |
| 6 | Complete | 2026-07-31 | 2026-07-31 |
| 7 | Complete | 2026-07-31 | 2026-07-31 |
| 8 | Complete | 2026-07-31 | 2026-07-31 |
| 9 | Complete | 2026-08-02 | 2026-08-02 |
| 10 | Complete | 2026-08-02 | 2026-08-02 |
| 11 | Not started | | |
