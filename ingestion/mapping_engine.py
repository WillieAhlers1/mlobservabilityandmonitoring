"""Mapping engine orchestrator.

Reads pending CTEs from the staging store, resolves entities, applies transforms,
validates, and writes to the appropriate metric store table.
"""

import json
import sqlite3
from pathlib import Path
from typing import Optional

from ingestion.entity_resolution import resolve_entity_with_strategy
from ingestion.handlers import HANDLER_REGISTRY
from ingestion.mapping_loader import (
    MappingDefinition,
    find_matching_mapping,
    load_all_mappings,
)
from ingestion.models import CanonicalTelemetryEvent
from ingestion.staging import fetch_pending_batch, mark_batch_processed
from ingestion.transforms import apply_transform
from ingestion.validation import run_validation_rules


class MappingEngine:
    """Orchestrates CTE processing: resolve → transform → validate → write."""

    def __init__(self, db: sqlite3.Connection, mappings_dir: Path = None):
        """Initialize the mapping engine.

        Args:
            db: SQLite connection to the metric store.
            mappings_dir: Directory containing mapping YAML files.
                          Defaults to <project_root>/mappings/.
        """
        self.db = db
        if mappings_dir is None:
            mappings_dir = Path(__file__).parent.parent / "mappings"
        self.mappings = load_all_mappings(mappings_dir)

    def process_batch(self, batch_size: int = 1000) -> dict:
        """Process a batch of pending CTEs.

        Returns:
            Dict with counts: {"processed": N, "mapped": N, "rejected": N, "no_mapping": N}
        """
        ctes = fetch_pending_batch(self.db, limit=batch_size)
        if not ctes:
            return {"processed": 0, "mapped": 0, "rejected": 0, "no_mapping": 0}

        updates = []
        mapped_count = 0
        rejected_count = 0
        no_mapping_count = 0

        for cte in ctes:
            status, reason = self._process_single(cte)
            updates.append((cte.event_id, status, reason))
            if status == "mapped":
                mapped_count += 1
            else:
                rejected_count += 1
                if reason and "No matching mapping" in reason:
                    no_mapping_count += 1

        mark_batch_processed(self.db, updates)

        return {
            "processed": len(ctes),
            "mapped": mapped_count,
            "rejected": rejected_count,
            "no_mapping": no_mapping_count,
        }

    def _process_single(self, cte: CanonicalTelemetryEvent) -> tuple[str, Optional[str]]:
        """Process a single CTE through the full pipeline.

        Returns:
            (status, reason) — ("mapped", None) or ("rejected", reason_string)
        """
        # Step 1: Find matching mapping definition
        mapping = find_matching_mapping(
            self.mappings, cte.source_connector, cte.event_type, cte.payload
        )
        if not mapping:
            return "rejected", f"No matching mapping for connector={cte.source_connector}, event_type={cte.event_type}"

        # Step 2: Resolve entity
        entity_id, resolve_reason = resolve_entity_with_strategy(
            self.db, cte.source_entity_ref, mapping.entity_resolution.on_no_match
        )
        if not entity_id:
            return "rejected", resolve_reason

        # Step 3: Apply field mappings and transforms
        try:
            transformed_value = self._apply_field_mappings(cte, mapping)
        except Exception as e:
            return "rejected", f"Transform error: {str(e)}"

        # Step 4: Run validation rules
        if mapping.validation_rules:
            valid, val_reason = run_validation_rules(
                mapping.validation_rules, transformed_value, cte.timestamp
            )
            if not valid:
                return "rejected", f"Validation failed: {val_reason}"

        # Step 5: Write to metric store
        try:
            self._write_to_store(cte, mapping, entity_id, transformed_value)
        except Exception as e:
            return "rejected", f"Write error: {str(e)}"

        return "mapped", None

    def _apply_field_mappings(self, cte: CanonicalTelemetryEvent,
                              mapping: MappingDefinition) -> Optional[float]:
        """Apply field mappings to extract and transform the primary value.

        For metric/drift events, this extracts the numeric value from the payload
        and applies the configured transform.

        Returns:
            The transformed value, or None if no applicable mapping found.
        """
        for fm in mapping.field_mappings:
            # Check 'when' condition if present
            if fm.when:
                if not self._evaluate_when(fm.when, cte.payload):
                    continue

            # Extract source value from payload
            value = self._extract_value(fm.source, cte)
            if value is None:
                continue

            # Apply transform
            value = apply_transform(fm.transform, value, fm.transform_params or None)
            return value

        # If no field mapping matched, try extracting the default value field
        return cte.payload.get("metric_value", cte.payload.get("value"))

    def _extract_value(self, source_path: str, cte: CanonicalTelemetryEvent):
        """Extract a value from the CTE using a dot-path.

        Supports paths like:
            "payload.metric_value"
            "payload.value"
            "payload.dimensions.cohort"
        """
        if source_path.startswith("payload."):
            path = source_path[len("payload."):]
            parts = path.split(".")
            current = cte.payload
            for part in parts:
                if isinstance(current, dict):
                    current = current.get(part)
                else:
                    return None
            return current
        return None

    def _evaluate_when(self, when_expr: str, payload: dict) -> bool:
        """Evaluate a 'when' condition against the payload.

        Supports: "payload.metric_name == 'accuracy'"
        """
        try:
            if "==" in when_expr:
                left, right = when_expr.split("==", 1)
                left = left.strip()
                right = right.strip().strip("'\"")

                if left.startswith("payload."):
                    path = left[len("payload."):]
                    parts = path.split(".")
                    current = payload
                    for part in parts:
                        if isinstance(current, dict):
                            current = current.get(part)
                        else:
                            return False
                    return str(current) == right
        except (KeyError, TypeError):
            pass
        return False

    def _write_to_store(self, cte: CanonicalTelemetryEvent,
                        mapping: MappingDefinition,
                        entity_id: str, value) -> None:
        """Write the processed value to the appropriate metric store table."""
        # Check if there's a registered handler for this event type
        handler_cls = HANDLER_REGISTRY.get(cte.event_type)
        if handler_cls and mapping.target_table != "metric_timeseries":
            handler = handler_cls()
            handler.write(self.db, cte, entity_id, value, mapping)
        elif mapping.target_table == "metric_timeseries":
            self._write_metric_timeseries(cte, entity_id, value, mapping)
        elif mapping.target_table == "drift_snapshots":
            # Fallback for drift mapped via target_table without event_type handler
            from ingestion.handlers.drift import DriftHandler
            DriftHandler().write(self.db, cte, entity_id, value, mapping)
        else:
            # Try handler based on target_table name
            for evt_type, hcls in HANDLER_REGISTRY.items():
                if hcls.target_table == mapping.target_table:
                    hcls().write(self.db, cte, entity_id, value, mapping)
                    return
            # Ultimate fallback: metric_timeseries
            self._write_metric_timeseries(cte, entity_id, value, mapping)

    def _write_metric_timeseries(self, cte: CanonicalTelemetryEvent,
                                  entity_id: str, value, mapping: MappingDefinition) -> None:
        """Insert a row into metric_timeseries."""
        metric_name = cte.payload.get("metric_name", "unknown")
        dimensions = cte.payload.get("dimensions")
        if isinstance(dimensions, dict):
            dimensions = json.dumps(dimensions)
        elif dimensions and isinstance(dimensions, str):
            pass  # Already a JSON string
        else:
            dimensions = None

        # Find semantic_tag from field mappings
        semantic_tag = None
        for fm in mapping.field_mappings:
            if fm.semantic_tag:
                semantic_tag = fm.semantic_tag
                break

        self.db.execute(
            """INSERT INTO metric_timeseries
               (entity_id, metric_name, semantic_tag, timestamp, value, dimensions, source_event_id)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (entity_id, metric_name, semantic_tag, cte.timestamp, value, dimensions, cte.event_id),
        )
        self.db.commit()
