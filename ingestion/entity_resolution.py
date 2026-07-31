"""Entity resolution for the mapping engine.

Resolves CTEs to registered entities by looking up source_entity_ref
against the entity_aliases table.
"""

import sqlite3
from typing import Optional


def resolve_entity(db: sqlite3.Connection, source_entity_ref: str) -> Optional[str]:
    """Resolve a source entity reference to an entity_id.

    Looks up the source_entity_ref in entity_aliases (alias_type='source_ref')
    and falls back to checking against onboard_name and endpoint aliases.

    Args:
        db: SQLite connection.
        source_entity_ref: The source reference string (e.g., "mlflow://exp-1/model-a").

    Returns:
        The entity_id if found, None otherwise.
    """
    # Direct match on alias_value (any alias_type)
    row = db.execute(
        "SELECT entity_id FROM entity_aliases WHERE alias_value = ?",
        (source_entity_ref,),
    ).fetchone()
    if row:
        return row["entity_id"]

    # Try matching just the trailing segment (e.g., "model-a" from "mlflow://exp-1/model-a")
    if "/" in source_entity_ref:
        short_ref = source_entity_ref.rsplit("/", 1)[-1]
        row = db.execute(
            "SELECT entity_id FROM entity_aliases WHERE alias_value = ?",
            (short_ref,),
        ).fetchone()
        if row:
            return row["entity_id"]

    return None


def resolve_entity_with_strategy(db: sqlite3.Connection, source_entity_ref: str,
                                  on_no_match: str = "reject") -> tuple[Optional[str], Optional[str]]:
    """Resolve entity with configurable fallback strategy.

    Args:
        db: SQLite connection.
        source_entity_ref: The source reference string.
        on_no_match: Strategy when entity not found:
            "reject" — return None (CTE will be rejected)
            "skip" — return None (CTE will be silently dropped)
            "queue_for_review" — return None with specific reason

    Returns:
        Tuple of (entity_id, rejection_reason). If entity found, reason is None.
        If not found, entity_id is None and reason describes why.
    """
    entity_id = resolve_entity(db, source_entity_ref)
    if entity_id:
        return entity_id, None

    if on_no_match == "reject":
        return None, f"Entity not found for ref: {source_entity_ref}"
    elif on_no_match == "skip":
        return None, "Entity not found (skip strategy)"
    elif on_no_match == "queue_for_review":
        return None, f"Entity unresolved, queued for review: {source_entity_ref}"
    else:
        return None, f"Entity not found for ref: {source_entity_ref}"
