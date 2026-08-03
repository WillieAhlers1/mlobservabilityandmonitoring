---
title: "Progress Tracker"
description: "Implementation progress for ML Works telemetry ingestion and live data parity"
author: "ML Works Team"
ms.date: 2026-08-03
ms.topic: overview
---

## Completed Work (Sessions 1-11)

### Session 1: Metric Store Schema and Entity Registry

- [x] Metric store tables added to `init_db()`
- [x] `entity_registry` + `entity_aliases` tables created
- [x] `entity_id` column added to `onboarded_models` and `onboarded_agents`
- [x] Onboard POST writes to `entity_registry` (model + agent)
- [x] Migration script for existing onboarded rows
- [x] `tests/test_entity_registry.py` passes (19/19)

### Session 2: Data Source Router and Metric Store Read Path

- [x] `data_source.py` created with router logic
- [x] All routes use `data_source` instead of `mock_data` directly
- [x] Mock mode behaves identically to current
- [x] Live mode with empty DB returns graceful empty states
- [x] `tests/test_data_source_shapes.py` passes (46/46)

### Session 2.5: Synthetic Telemetry Data Generator

- [x] `tools/generate_synthetic_data.py` with CLI
- [x] All 7 CSV types generated (metrics, drift, alerts, traces, lifecycle, DQ, cohorts)
- [x] `manifest.json` generated
- [x] Edge cases included (duplicates, late arrivals, missing fields)
- [x] Deterministic output (same seed = same files)
- [x] `tests/test_synthetic_generator.py` passes (24/24)

### Session 3: Staging Store and CTE Write Path

- [x] `staging_events` table in `init_db()`
- [x] `ingestion/models.py` with CTE dataclass
- [x] `ingestion/staging.py` with insert + dedup logic
- [x] `tests/test_staging.py` passes (25/25)

### Session 4: Mapping Engine Core

- [x] Mapping loader, entity resolution, transforms, validation
- [x] `ingestion/mapping_engine.py` orchestrator
- [x] All mapping YAML files created
- [x] `tests/test_mapping_engine.py` passes (51/51)

### Session 5: Aggregation Engine and Time Bucketing

- [x] `ingestion/aggregation.py` created
- [x] `metric_timeseries_agg` table added
- [x] Grace period logic for late arrivals
- [x] `tests/test_aggregation.py` passes (22/22)

### Session 6: Connector Framework and FileDropConnector

- [x] `ingestion/connectors/base.py` with BaseConnector ABC
- [x] `ingestion/connectors/file_drop.py` reads CSV/JSON
- [x] `connector_health` table and connector registry
- [x] `tests/test_file_drop_e2e.py` passes (22/22)

### Session 7: WebhookConnector and Ingestion API

- [x] `ingestion/connectors/webhook.py` created
- [x] HMAC signature verification, rate limiting
- [x] `tests/test_webhook_connector.py` passes (32/32)

### Session 8: Connector Scheduler and Background Processing

- [x] `ingestion/scheduler.py` with APScheduler
- [x] Scheduler only starts when `DATA_SOURCE=live`
- [x] `tests/test_scheduler.py` passes (15/15)

### Session 9: Onboard-to-Live Pipeline Integration

- [x] Source reference creates alias for connector matching
- [x] Completeness score per entity
- [x] E2E: onboard → file drop → dashboard shows data
- [x] `tests/test_onboard_to_dashboard.py` passes (13/13)

### Session 10: Drift, Alerts, and Specialized Metric Tables

- [x] All specialized handlers (drift, alerts, cohorts, features, DQ, lifecycle, traces)
- [x] Live-mode queries for each table in `data_source.py`
- [x] `tests/test_handlers.py` passes (41/41)

### Session 11: Observability — Ingestion Health and Dead-Letter Queue

- [x] `/ingestion/health` and `/ingestion/dead-letter` routes
- [x] Pages only accessible in live mode
- [x] `tests/test_ingestion_health.py` passes (31/31)

### Session 12: Data Source Switching Fix

- [x] Fixed `data_source.DATA_SOURCE` stale caching bug
- [x] `_get_data_source()` reads live module variable
- [x] Settings page updates `data_source.DATA_SOURCE` on save
- [x] Sidebar conditional rendering works for both modes
- [x] Compare page defaults to first available models (not hardcoded IDs)
- [x] Ingestion routes use live `DATA_SOURCE` check
- [x] All views verified switching correctly between mock and live

---

## Current Work: Live Data Parity

**Plan document**: `docs/implementation-plan-data.md` (2026-08-03)

### Phase 1: Enrich Synthetic Data Generator

- [x] Step 1.1: Add `industrials` and `hospitality` industries to generator
- [x] Step 1.2: Enrich entity metadata (algorithm, version, owner, description,
  features, compliance)
- [x] Step 1.3: Generate agent time-series metrics (task_completion, groundedness,
  safety, tokens, cost)
- [x] Step 1.4: Generate feature_importance data
- [x] Step 1.5: Enrich project definitions with meaningful names/descriptions

### Phase 2: Enrich the Data Loader

- [x] Step 2.1: Store enriched metadata in `entity_registry` JSON column
- [x] Step 2.2: Enrich project seeding (names, descriptions, owners)
- [x] Step 2.3: Handle feature_importance loading into DB table

### Phase 3: Fix Live Data Functions

- [x] Step 3.1: Fix `_live_entity_list()` / `_live_get_entity()` to read full metadata
- [x] Step 3.2: Fix `_live_agent_metrics()` — derive tool_usage, policy violations,
  voice scores from traces
- [x] Step 3.3: Fix `_live_alerts()` — add project_name lookup, timestamp_relative
- [x] Step 3.4: Compute `dqm_score` in entity list from data_quality table
- [x] Step 3.5: Add confusion matrix support (generate + read)

### Phase 4: Regenerate and Validate

- [x] Step 4.1: Regenerate synthetic data for all four industries
- [x] Step 4.2: Reload database per selected industry
- [x] Step 4.3: End-to-end validation (all pages, both modes)
- [x] Step 4.4: Mock mode regression test (full test suite green)

---

## Quick Status

| Session | Status | Date |
|---------|--------|------|
| 1-11 | Complete | 2026-07-31 to 2026-08-02 |
| 12 (switching fix) | Complete | 2026-08-03 |
| Live Data Parity | Complete | 2026-08-03 |
