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

- [ ] `staging_events` table in `init_db()`
- [ ] `ingestion/models.py` with CTE dataclass
- [ ] `ingestion/staging.py` with insert + dedup logic
- [ ] Deterministic `event_id` computation
- [ ] Batch insert (INSERT OR IGNORE)
- [ ] `fetch_pending_batch(limit)` works
- [ ] `mark_processed(event_id, status, reason)` works
- [ ] `tests/test_staging.py` passes

## Session 4: Mapping Engine Core

- [ ] `ingestion/mapping_loader.py` loads and validates YAML
- [ ] `ingestion/entity_resolution.py` resolves via aliases
- [ ] `ingestion/transforms.py` (identity, clamp, scale, round)
- [ ] `ingestion/validation.py` rule engine
- [ ] `ingestion/mapping_engine.py` orchestrator
- [ ] `mappings/example_classification.yaml` created
- [ ] End-to-end: CTE → metric_timeseries row
- [ ] Rejected CTEs get status + reason
- [ ] `tests/test_mapping_engine.py` passes

## Session 5: Aggregation Engine and Time Bucketing

- [ ] `ingestion/aggregation.py` created
- [ ] `metric_timeseries_agg` table added
- [ ] Aggregation methods: last, mean, max, min, sum
- [ ] Grace period logic for late arrivals
- [ ] Re-aggregation on modified buckets
- [ ] `data_source.py` live mode reads from agg table
- [ ] `tests/test_aggregation.py` passes

## Session 6: Connector Framework and FileDropConnector

- [ ] `ingestion/connectors/base.py` with BaseConnector ABC
- [ ] `ingestion/connectors/file_drop.py` reads CSV/JSON
- [ ] `connector_health` table created
- [ ] `ingestion/connector_registry.py` discovers connectors by config
- [ ] `config/ingestion.yaml` created
- [ ] `ingestion/config_loader.py` validates config
- [ ] Processed files moved to `processed/` dir
- [ ] E2E: file drop → staging → mapping → metric store → API
- [ ] `tests/test_file_drop_e2e.py` passes

## Session 7: WebhookConnector and Ingestion API

- [ ] `ingestion/connectors/webhook.py` created
- [ ] `POST /api/ingest/webhook` route in `app.py`
- [ ] HMAC signature verification
- [ ] Request validation (schema, required fields)
- [ ] Idempotency key support
- [ ] Proper error responses (400, 401, 409, 429)
- [ ] `tests/test_webhook_connector.py` passes

## Session 8: Connector Scheduler and Background Processing

- [ ] `ingestion/scheduler.py` with APScheduler
- [ ] Connectors polled at configured intervals
- [ ] Mapping engine batch processing job
- [ ] Scheduler only starts when `DATA_SOURCE=live`
- [ ] Graceful startup/shutdown
- [ ] Processing lag metric computed
- [ ] `apscheduler` in `requirements.txt`
- [ ] `tests/test_scheduler.py` passes

## Session 9: Onboard-to-Live Pipeline Integration

- [ ] Onboard form has telemetry source config fields
- [ ] Source reference creates alias for connector matching
- [ ] Dashboard: "Awaiting telemetry" state for new entities
- [ ] Dashboard: partial metrics render with "No data" badges
- [ ] Dashboard: full metrics render normally
- [ ] Completeness score per entity
- [ ] E2E: onboard → file drop → dashboard shows data
- [ ] No regressions in mock mode
- [ ] `tests/test_onboard_to_dashboard.py` passes

## Session 10: Drift, Alerts, and Specialized Metric Tables

- [ ] `ingestion/handlers/drift.py` → `drift_snapshots`
- [ ] `ingestion/handlers/alerts.py` → `alerts`
- [ ] `ingestion/handlers/cohorts.py` → `cohort_metrics`
- [ ] `ingestion/handlers/features.py` → `feature_importance`
- [ ] `ingestion/handlers/data_quality.py` → `data_quality`
- [ ] Lifecycle events → `lineage_events`
- [ ] Agent traces → `agent_traces` + `agent_trace_steps`
- [ ] Live-mode queries for each table in `data_source.py`
- [ ] `/alerts` renders from DB in live mode
- [ ] `tests/test_handlers/` passes

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
| 3 | Not started | | |
| 4 | Not started | | |
| 5 | Not started | | |
| 6 | Not started | | |
| 7 | Not started | | |
| 8 | Not started | | |
| 9 | Not started | | |
| 10 | Not started | | |
| 11 | Not started | | |
