"""Migrate existing onboarded_models and onboarded_agents rows into entity_registry.

Run once after upgrading the schema. Safe to re-run (skips rows that already have entity_id).

Usage:
    python migrations/seed_entity_registry.py [--db-path ml_monitor.db]
"""

import json
import os
import sqlite3
import sys
import uuid
from datetime import datetime, timezone


def migrate(db_path: str) -> dict:
    """Migrate existing onboarded rows into entity_registry.

    Returns a summary dict with counts of migrated models and agents.
    """
    db = sqlite3.connect(db_path)
    db.row_factory = sqlite3.Row
    now_iso = datetime.now(timezone.utc).isoformat()
    migrated_models = 0
    migrated_agents = 0

    # Migrate models
    rows = db.execute(
        "SELECT * FROM onboarded_models WHERE entity_id IS NULL"
    ).fetchall()
    for row in rows:
        entity_id = f"model-{uuid.uuid4().hex[:8]}"
        project_id = row["project_id"] or ""
        name = row["model_name"]

        metadata = json.dumps({
            "model_type": row["model_type"] or "",
            "algorithm": row["algorithm"] or "",
            "version": row["version"] or "",
        })

        db.execute(
            """INSERT INTO entity_registry
               (entity_id, entity_type, industry_id, project_id, name, status, metadata, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (entity_id, "model", "unknown", project_id, name, "Unknown", metadata, now_iso, now_iso),
        )
        db.execute(
            "INSERT INTO entity_aliases (entity_id, alias_type, alias_value) VALUES (?,?,?)",
            (entity_id, "onboard_name", name),
        )
        if row["endpoint"]:
            db.execute(
                "INSERT INTO entity_aliases (entity_id, alias_type, alias_value) VALUES (?,?,?)",
                (entity_id, "endpoint", row["endpoint"]),
            )
        db.execute(
            "UPDATE onboarded_models SET entity_id = ? WHERE id = ?",
            (entity_id, row["id"]),
        )
        migrated_models += 1

    # Migrate agents
    rows = db.execute(
        "SELECT * FROM onboarded_agents WHERE entity_id IS NULL"
    ).fetchall()
    for row in rows:
        entity_id = f"agent-{uuid.uuid4().hex[:8]}"
        project_id = row["project_id"] or ""
        name = row["agent_name"]

        metadata = json.dumps({
            "framework": row["framework"] or "",
            "llm_backbone": row["llm_backbone"] or "",
            "version": row["version"] or "",
        })

        db.execute(
            """INSERT INTO entity_registry
               (entity_id, entity_type, industry_id, project_id, name, status, metadata, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (entity_id, "agent", "unknown", project_id, name, "Unknown", metadata, now_iso, now_iso),
        )
        db.execute(
            "INSERT INTO entity_aliases (entity_id, alias_type, alias_value) VALUES (?,?,?)",
            (entity_id, "onboard_name", name),
        )
        if row["endpoint"]:
            db.execute(
                "INSERT INTO entity_aliases (entity_id, alias_type, alias_value) VALUES (?,?,?)",
                (entity_id, "endpoint", row["endpoint"]),
            )
        db.execute(
            "UPDATE onboarded_agents SET entity_id = ? WHERE id = ?",
            (entity_id, row["id"]),
        )
        migrated_agents += 1

    db.commit()
    db.close()
    return {"models": migrated_models, "agents": migrated_agents}


if __name__ == "__main__":
    db_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "ml_monitor.db"
    )
    if not os.path.exists(db_path):
        print(f"Database not found: {db_path}")
        sys.exit(1)
    result = migrate(db_path)
    print(f"Migration complete: {result['models']} models, {result['agents']} agents migrated.")
