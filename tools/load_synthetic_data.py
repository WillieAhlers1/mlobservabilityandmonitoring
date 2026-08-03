"""Load synthetic data from data/synthetic/ into the live metric store.

Reads the manifest.json to register entities, then ingests each CSV file
through the staging → mapping engine pipeline, writing to the specialized
metric store tables.

Usage:
    python tools/load_synthetic_data.py [--db-path ml_monitor.db]

After running, start the app with:
    set ML_WORKS_DATA_SOURCE=live
    python app.py
"""

import csv
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

# Ensure project root is importable
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from ingestion.models import CanonicalTelemetryEvent
from ingestion.staging import compute_event_id, insert_ctes
from ingestion.mapping_engine import MappingEngine


SYNTHETIC_DIR = PROJECT_ROOT / "data" / "synthetic"


def load_manifest(synthetic_dir: Path) -> dict:
    """Load and return the manifest.json."""
    manifest_path = synthetic_dir / "manifest.json"
    with open(manifest_path, "r", encoding="utf-8") as f:
        return json.load(f)


def seed_entities(db: sqlite3.Connection, manifest: dict) -> int:
    """Register all entities from the manifest into entity_registry + aliases.

    Returns the number of entities registered.
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    industry = manifest.get("industry", "hls")
    registered = 0

    # Create projects from manifest metadata (enriched in generator)
    manifest_projects = manifest.get("projects", [])
    if manifest_projects:
        for proj in manifest_projects:
            db.execute(
                """INSERT OR REPLACE INTO projects (id, name, description, owner, team, created_date, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (proj["id"], proj["name"], proj.get("description", ""),
                 proj.get("owner", ""), proj.get("team", ""), now_iso[:10], "Active"),
            )
    else:
        # Fallback: create projects from entity references
        project_ids = set()
        for entity in manifest["entities"]:
            pid = entity.get("project_id", "proj-default")
            if pid not in project_ids:
                project_ids.add(pid)
                db.execute(
                    """INSERT OR IGNORE INTO projects (id, name, description, owner, team, created_date, status)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (pid, pid.replace("-", " ").title(), f"Synthetic project {pid}",
                     "synthetic", "synthetic", now_iso[:10], "Active"),
                )

    for entity in manifest["entities"]:
        entity_id = entity["entity_id"]
        entity_type = entity["entity_type"]
        name = entity["name"]
        project_id = entity.get("project_id", "proj-default")
        source_ref = entity["source_entity_ref"]

        # Build enriched metadata from manifest
        metadata = {}
        if entity_type == "model":
            metadata["model_type"] = entity.get("model_type", "classification")
            metadata["scenario"] = entity.get("scenario", "healthy")
            metadata["algorithm"] = entity.get("algorithm", "")
            metadata["version"] = entity.get("version", "")
            metadata["owner"] = entity.get("owner", "")
            metadata["description"] = entity.get("description", "")
            metadata["features"] = entity.get("features", [])
            metadata["hipaa"] = entity.get("hipaa", {})
            metadata["predictions_today"] = entity.get("predictions_today", 0)
            metadata["avg_latency_ms"] = entity.get("avg_latency_ms", 0)
        else:
            metadata["scenario"] = entity.get("scenario", "operational")
            metadata["framework"] = entity.get("framework", "")
            metadata["llm_backbone"] = entity.get("llm_backbone", "")
            metadata["version"] = entity.get("version", "")
            metadata["owner"] = entity.get("owner", "")
            metadata["description"] = entity.get("description", "")
            metadata["tools"] = entity.get("tools", [])
            metadata["hipaa"] = entity.get("hipaa", {})

        # Upsert into entity_registry
        existing = db.execute(
            "SELECT 1 FROM entity_registry WHERE entity_id = ?", (entity_id,)
        ).fetchone()
        if existing:
            # Update metadata for existing entities
            db.execute(
                "UPDATE entity_registry SET metadata = ?, updated_at = ? WHERE entity_id = ?",
                (json.dumps(metadata), now_iso, entity_id),
            )
        else:
            db.execute(
                """INSERT INTO entity_registry
                   (entity_id, entity_type, industry_id, project_id, name, status, metadata, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (entity_id, entity_type, industry, project_id, name,
                 "Healthy" if entity_type == "model" else "Operational",
                 json.dumps(metadata), now_iso, now_iso),
            )
            registered += 1

        # Create aliases for entity resolution
        db.execute(
            """INSERT OR IGNORE INTO entity_aliases (entity_id, alias_type, alias_value)
               VALUES (?, ?, ?)""",
            (entity_id, "source_ref", source_ref),
        )
        db.execute(
            """INSERT OR IGNORE INTO entity_aliases (entity_id, alias_type, alias_value)
               VALUES (?, ?, ?)""",
            (entity_id, "onboard_name", name),
        )

    db.commit()
    return registered


def csv_to_ctes(csv_path: Path, event_type: str, connector: str = "file_drop") -> list[CanonicalTelemetryEvent]:
    """Convert a CSV file to a list of CTEs based on event_type."""
    ctes = []
    now_iso = datetime.now(timezone.utc).isoformat()

    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            source_ref = row.get("source_entity_ref", "")
            timestamp = row.get("timestamp", now_iso)

            if event_type == "metric":
                metric_name = row.get("metric_name", "unknown")
                event_id = compute_event_id(connector, source_ref, "metric", timestamp, metric_name)
                payload = {
                    "metric_name": metric_name,
                    "metric_value": _safe_float(row.get("metric_value")),
                    "model_type": row.get("model_type"),
                    "dimensions": _safe_json(row.get("dimensions")),
                }
            elif event_type == "drift":
                event_id = compute_event_id(connector, source_ref, "drift", timestamp, row.get("scope"))
                payload = {
                    "drift_type": row.get("drift_type", "psi"),
                    "scope": row.get("scope", "overall"),
                    "value": _safe_float(row.get("value")),
                    "status": row.get("status"),
                }
            elif event_type == "alert":
                event_id = compute_event_id(connector, source_ref, "alert", timestamp, row.get("alert_type"))
                payload = {
                    "severity": row.get("severity", "medium"),
                    "alert_type": row.get("alert_type", "unknown"),
                    "title": row.get("title", ""),
                    "description": row.get("description", ""),
                }
            elif event_type == "trace":
                trace_id = row.get("trace_id", "")
                event_id = compute_event_id(connector, source_ref, "trace", timestamp, trace_id)
                steps = _safe_json(row.get("steps_json", "[]"))
                if not isinstance(steps, list):
                    steps = []
                payload = {
                    "trace_id": trace_id,
                    "query": row.get("query", ""),
                    "response": row.get("response", ""),
                    "total_latency": _safe_int(row.get("total_latency_ms")),
                    "token_count": _safe_int(row.get("token_count")),
                    "voice_score": _safe_float(row.get("voice_score")),
                    "policy_pass": row.get("policy_pass", "true").lower() == "true",
                    "steps": steps,
                }
            elif event_type == "lifecycle":
                event_id = compute_event_id(connector, source_ref, "lifecycle", timestamp, row.get("version"))
                metadata = _safe_json(row.get("metadata_json", "{}"))
                if not isinstance(metadata, dict):
                    metadata = {}
                payload = {
                    "lifecycle_type": row.get("event_type", "deployment"),
                    "version": row.get("version"),
                    "trigger": row.get("trigger"),
                    **metadata,
                }
            elif event_type == "data_quality":
                feature = row.get("feature", row.get("metric_name", "unknown"))
                event_id = compute_event_id(connector, source_ref, "data_quality", timestamp, feature)
                payload = {
                    "feature": feature,
                    "missing_rate": _safe_float(row.get("missing_rate")),
                    "outlier_rate": _safe_float(row.get("outlier_rate")),
                    "schema_valid": row.get("schema_valid", "true").lower() == "true",
                    "row_count": _safe_int(row.get("row_count")),
                }
            elif event_type == "cohort":
                cohort_name = row.get("cohort_name", "unknown")
                metric_name = row.get("metric_name", "unknown")
                event_id = compute_event_id(connector, source_ref, "cohort", timestamp,
                                            f"{cohort_name}:{metric_name}")
                payload = {
                    "cohort_name": cohort_name,
                    "cohort_dim": row.get("cohort_dim", "segment"),
                    "metric_name": metric_name,
                    "value": _safe_float(row.get("value")),
                    "sample_size": _safe_int(row.get("sample_size")),
                }
            elif event_type == "feature_importance":
                feature = row.get("feature", "unknown")
                event_id = compute_event_id(connector, source_ref, "feature_importance", timestamp, feature)
                payload = {
                    "feature": feature,
                    "importance": _safe_float(row.get("importance")),
                }
            else:
                continue

            cte = CanonicalTelemetryEvent(
                event_id=event_id,
                source_connector=connector,
                source_entity_ref=source_ref,
                event_type=event_type,
                timestamp=timestamp,
                received_at=now_iso,
                mapping_version="1",
                payload=payload,
            )
            ctes.append(cte)

    return ctes


def _safe_float(val):
    if val is None or val == "":
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _safe_int(val):
    if val is None or val == "":
        return None
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return None


def _safe_json(val):
    if val is None or val == "":
        return None
    try:
        return json.loads(val)
    except (json.JSONDecodeError, TypeError):
        return val


# Map manifest event_type → our CTE event_type + CSV filename
FILE_EVENT_MAP = {
    "model_metrics.csv": "metric",
    "agent_metrics.csv": "metric",
    "drift_events.csv": "drift",
    "alerts.csv": "alert",
    "agent_traces.csv": "trace",
    "lifecycle_events.csv": "lifecycle",
    "data_quality.csv": "data_quality",
    "cohort_metrics.csv": "cohort",
    "feature_importance.csv": "feature_importance",
}


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Load synthetic data into the live metric store")
    parser.add_argument("--db-path", default=None, help="Path to SQLite DB (default: from config)")
    parser.add_argument("--synthetic-dir", default=str(SYNTHETIC_DIR), help="Path to synthetic data dir")
    args = parser.parse_args()

    # Initialize DB
    import app as app_module
    if args.db_path:
        app_module.DB_PATH = args.db_path
    db_path = app_module.DB_PATH
    app_module.init_db()

    print(f"Database: {db_path}")
    print(f"Synthetic data: {args.synthetic_dir}")

    db = sqlite3.connect(db_path, timeout=30)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA busy_timeout=30000")
    synthetic_dir = Path(args.synthetic_dir)

    # Step 1: Load manifest and seed entities
    manifest = load_manifest(synthetic_dir)
    entity_count = seed_entities(db, manifest)
    print(f"Registered {entity_count} entities ({len(manifest['entities'])} in manifest)")

    # Step 2: Ingest each CSV into staging
    total_staged = 0
    for filename, event_type in FILE_EVENT_MAP.items():
        csv_path = synthetic_dir / filename
        if not csv_path.exists():
            print(f"  SKIP {filename} (not found)")
            continue

        ctes = csv_to_ctes(csv_path, event_type)
        inserted = insert_ctes(db, ctes)
        total_staged += inserted
        print(f"  Staged {inserted}/{len(ctes)} CTEs from {filename} (event_type={event_type})")

    print(f"Total staged: {total_staged}")

    # Step 3: Process through mapping engine
    # Metric and drift types go through the mapping engine (they have YAML mappings)
    # Other types need direct handler routing — the mapping engine handles this via HANDLER_REGISTRY
    engine = MappingEngine(db)
    batch_num = 0
    total_mapped = 0
    total_rejected = 0

    while True:
        result = engine.process_batch(batch_size=2000)
        if result["processed"] == 0:
            break
        batch_num += 1
        total_mapped += result["mapped"]
        total_rejected += result["rejected"]
        print(f"  Batch {batch_num}: processed={result['processed']}, "
              f"mapped={result['mapped']}, rejected={result['rejected']}, "
              f"no_mapping={result['no_mapping']}")

    print(f"\nDone! Mapped: {total_mapped}, Rejected: {total_rejected}")
    print(f"\nTo run the app in live mode:")
    print(f"  set ML_WORKS_DATA_SOURCE=live")
    print(f"  python app.py")

    db.close()


if __name__ == "__main__":
    main()
