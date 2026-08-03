---
title: "Implementation Plan: Live Data Parity"
description: "Plan to achieve full data parity between mock and live modes across all industries"
author: "ML Works Team"
ms.date: 2026-08-03
ms.topic: concept
status: Complete
---

## Problem Statement

When switching from mock to live data source mode, the application displays incomplete
data across multiple views. The root cause is a schema and content mismatch between
what templates expect (rich, fully-populated objects from mock_data) and what the live
DB/data_source functions actually provide (sparse entities with minimal metadata).

Additionally, the synthetic data generator only supports `hls` and `retail` industries
but the application supports four: `hls`, `retail`, `industrials`, and `hospitality`.
The live data must respect the user's industry selection.

## Design Principles

1. Mock mode remains unchanged and continues to showcase full application capabilities
2. Live mode must render identically rich content using DB-stored data
3. The synthetic generator is the canonical source for populating live-mode DBs
4. Industry selection drives which entities, projects, and compliance framework apply
5. HIPAA compliance fields are HLS-specific; other industries use a generalized
   data compliance framework (same schema key `hipaa`, different content)
6. No template changes required; fix the data layer to produce matching shapes

## Industry-Specific Compliance Mapping

| Industry | Compliance Label | data_classification | phi_handling | baa_signed |
|----------|-----------------|--------------------:|--------------|------------|
| HLS | HIPAA | PHI | De-identified per Safe Harbor / Expert Determination | true |
| Retail | Data Privacy | Customer Data / PII | PII Protected | false |
| Industrials | Data Security | Proprietary / OT Data | N/A - No PHI | false |
| Hospitality | Data Privacy | Guest PII | PII Protected | false |

## Scope of Changes

### Phase 1: Enrich Synthetic Data Generator

**Goal**: Make `generate_synthetic_data.py` produce entities with all fields templates need.

#### Step 1.1: Add all four industries to the generator

- Add `industrials` and `hospitality` entity definitions to `INDUSTRY_ENTITIES` dict
- Each industry needs: models (4-8), agents (2-4), projects, and feature lists
- Mirror the structure already present for `hls` and `retail`

#### Step 1.2: Enrich entity metadata in manifest output

For each entity in the manifest, include additional fields:

**Models**:

- `algorithm` (e.g., XGBoost, LightGBM, Random Forest, Neural Network)
- `version` (e.g., 3.2.1)
- `owner` (person name matching the project owner from mock data)
- `description` (one-line purpose description)
- `features` (list of 8-10 feature names)
- `hipaa` / compliance object (industry-appropriate values)
- `predictions_today` (random int 1000-20000)
- `avg_latency_ms` (random int 20-150)

**Agents**:

- `framework` (e.g., LangChain, AutoGen, Semantic Kernel)
- `llm_backbone` (e.g., GPT-4o, Claude 3.5, Gemini Pro)
- `version` (e.g., 1.2.0)
- `owner` (person name)
- `description` (one-line purpose)
- `tools` (list of tool names the agent uses)

#### Step 1.3: Generate agent time-series metrics

Add agent metrics to `model_metrics.csv` (or a separate file) covering:

- `task_completion` (daily, 0.7-0.99)
- `groundedness` (daily, 0.75-0.98)
- `safety` (daily, 0.85-1.0)
- `input_tokens` (daily, 500-5000)
- `output_tokens` (daily, 200-3000)
- `cost_per_day` (daily, 0.50-25.00)

These should follow the same scenario-based degradation curves as model metrics.

#### Step 1.4: Generate feature_importance data

Create a `features.csv` (or integrate into existing output) with:

- One row per (entity_id, feature_name) pair
- `importance` value (0.01-0.35, summing to ~1.0 per entity)
- Only for model entities

#### Step 1.5: Enrich project definitions

When seeding projects, include:

- Meaningful `name` (e.g., "Patient Safety" not "Proj Hls 1")
- `description` (one sentence about the project)
- `owner` (person name)
- `team` (team name)

Source these from the `INDUSTRY_ENTITIES` definition or a parallel dict.

### Phase 2: Enrich the Data Loader

**Goal**: Make `load_synthetic_data.py` store full entity metadata into the DB.

#### Step 2.1: Store enriched metadata in entity_registry

Update `seed_entities()` to write all manifest fields into the `metadata` JSON column:

```python
metadata = {
    "model_type": entity.get("model_type"),
    "algorithm": entity.get("algorithm"),
    "version": entity.get("version"),
    "owner": entity.get("owner"),
    "description": entity.get("description"),
    "features": entity.get("features"),
    "hipaa": entity.get("hipaa"),
    "predictions_today": entity.get("predictions_today"),
    "avg_latency_ms": entity.get("avg_latency_ms"),
    # ... etc
}
```

#### Step 2.2: Enrich project seeding

Update project creation to use names/descriptions from the manifest rather than
generating generic names from the project ID.

#### Step 2.3: Handle feature_importance loading

Add a handler for the new feature_importance CSV/data so it populates the
`feature_importance` table.

### Phase 3: Fix Live Data Functions

**Goal**: Make `data_source.py` live functions produce the same shape as mock.

#### Step 3.1: Fix `_live_entity_list()` and `_live_get_entity()`

- Read `algorithm`, `version`, `owner`, `description`, `features`, `hipaa`,
  `predictions_today`, `avg_latency_ms` from the metadata JSON
- These already call `entity.setdefault(...)` but with empty defaults; instead
  use `meta.get("field", default)` to pull from stored metadata

#### Step 3.2: Fix `_live_agent_metrics()` — derive aggregates from traces

Compute from `agent_traces` + `agent_trace_steps`:

- **tool_usage**: GROUP BY tool from `agent_trace_steps`, compute call count,
  success rate, avg latency
- **policy_violations**: Filter traces where `policy_pass=0`, build violation list
- **voice_scores**: Aggregate `voice_score` into overall + dimension scores
- **task_breakdown**: Not derivable from current data; leave empty or derive from
  trace query patterns

Also read agent time-series from `metric_timeseries` (after Phase 1 generates it).

#### Step 3.3: Fix `_live_alerts()`

- Look up `project_id` from `entity_registry` (already queried), then find project
  name from `projects` table
- Compute `timestamp_relative` using a helper (e.g., "3h ago", "2d ago")

#### Step 3.4: Compute `dqm_score` in entity list

- Query `data_quality` for each entity, compute `1 - avg(missing_rate)` as DQM score
- Store in the entity dict so cockpit renders it

#### Step 3.5: Add confusion matrix support

Generate confusion matrix data in the synthetic generator (TP, FP, FN, TN values
per model based on accuracy/precision/recall) and store in a new field in
`metric_timeseries` or entity metadata. Alternatively compute from the last known
precision/recall values.

### Phase 4: Regenerate and Validate

#### Step 4.1: Regenerate synthetic data for all industries

```bash
python tools/generate_synthetic_data.py --industry hls --days 90 --seed 42
python tools/generate_synthetic_data.py --industry retail --days 90 --seed 43
python tools/generate_synthetic_data.py --industry industrials --days 90 --seed 44
python tools/generate_synthetic_data.py --industry hospitality --days 90 --seed 45
```

Store each industry's output in `data/synthetic/<industry>/`.

#### Step 4.2: Reload database per selected industry

Update `load_synthetic_data.py` to accept `--industry` flag and clear/reseed
the relevant tables. The app's `default_industry` config determines which
synthetic dataset is loaded.

#### Step 4.3: End-to-end validation

For each page, verify in live mode:

- **Cockpit**: Algorithm, version, owner, compliance badge, drift/perf/DQM scores
- **Dashboard (model)**: Description, predictions, latency, metrics charts,
  confusion matrix, feature importance, data quality, cohorts
- **Dashboard (agent)**: Metrics charts, tool usage, traces, policy violations,
  voice scores
- **Alerts**: Project name shown, relative timestamps
- **Projects**: Named projects with entity counts and links
- **Compare**: Full model data in comparison cards
- **Lineage**: Version history with metadata

#### Step 4.4: Mock mode regression test

Confirm mock mode still works identically after all changes by running the full
test suite and manually verifying each industry switch.

## File Change Summary

| File | Change Type | Description |
|------|-------------|-------------|
| `tools/generate_synthetic_data.py` | Major | Add industries, enrich metadata, add agent metrics, feature importance |
| `tools/load_synthetic_data.py` | Medium | Store enriched metadata, fix project seeding, handle features |
| `data_source.py` | Medium | Fix entity field extraction, derive agent aggregates, fix alerts |
| `data/synthetic/manifest.json` | Regenerated | Output of updated generator |
| `data/synthetic/*.csv` | Regenerated | Output of updated generator |
| `config/app.yaml` | Minor | No schema change; industry selection already works |
| Templates | None | No changes needed; data layer provides correct shapes |

## Dependencies and Risks

- Mock mode must remain untouched; all changes are to the live path and generator
- The `hipaa` key name is reused across industries for the compliance object; this is
  intentional to avoid template changes (templates check `model.hipaa.compliant`)
- Agent metrics in `metric_timeseries` are a new data category; the existing
  ingestion pipeline handlers support it but the generator didn't produce it
- Confusion matrix is the only field requiring either a new table column or a
  computed derivation; recommend storing in entity metadata as static values

## Success Criteria

1. Switching `data_source: live` in app.yaml shows fully-populated pages
2. All four industries can be generated and loaded independently
3. Industry switch in mock mode and live mode both show appropriate compliance labels
4. No test regressions in existing test suite
5. The live data is visually indistinguishable from mock data in richness
