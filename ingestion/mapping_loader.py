"""YAML mapping definition loader.

Loads and validates mapping definitions from YAML files in the mappings/ directory.
Each mapping defines how CTEs from a specific source_connector + event_type
are transformed and written to the metric store.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml


@dataclass
class FieldMapping:
    """A single field-level mapping rule."""
    source: str          # Dot-path into CTE payload (e.g., "payload.metric_value")
    target: str          # Target table.column (e.g., "metric_timeseries.value")
    when: Optional[str] = None    # Conditional expression (e.g., "payload.metric_name == 'accuracy'")
    transform: str = "identity"   # Transform name
    transform_params: dict = field(default_factory=dict)
    semantic_tag: Optional[str] = None


@dataclass
class EntityResolutionConfig:
    """How to resolve CTEs to entities."""
    strategy: str = "lookup"           # lookup | create | skip | queue_for_review
    match_fields: list[dict] = field(default_factory=list)
    on_no_match: str = "reject"        # reject | skip | queue_for_review


@dataclass
class MappingDefinition:
    """A complete mapping definition loaded from YAML."""
    version: str
    source_connector: str
    event_type: str
    filter_expr: Optional[str] = None  # Optional filter on payload fields
    entity_resolution: EntityResolutionConfig = field(default_factory=EntityResolutionConfig)
    field_mappings: list[FieldMapping] = field(default_factory=list)
    validation_rules: list[dict] = field(default_factory=list)
    target_table: str = "metric_timeseries"


def load_mapping_file(filepath: Path) -> MappingDefinition:
    """Load a single mapping YAML file and return a MappingDefinition.

    Args:
        filepath: Path to the YAML file.

    Returns:
        A validated MappingDefinition object.

    Raises:
        ValueError: If required fields are missing or invalid.
    """
    with open(filepath, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    if not raw:
        raise ValueError(f"Empty mapping file: {filepath}")

    # Required fields
    version = raw.get("version")
    if not version:
        raise ValueError(f"Missing 'version' in {filepath}")

    applies_to = raw.get("applies_to", {})
    source_connector = applies_to.get("source_connector")
    event_type = applies_to.get("event_type")
    if not source_connector or not event_type:
        raise ValueError(f"Missing 'applies_to.source_connector' or 'applies_to.event_type' in {filepath}")

    filter_expr = applies_to.get("filter")

    # Entity resolution
    er_raw = raw.get("entity_resolution", {})
    entity_resolution = EntityResolutionConfig(
        strategy=er_raw.get("strategy", "lookup"),
        match_fields=er_raw.get("match_fields", []),
        on_no_match=er_raw.get("on_no_match", "reject"),
    )

    # Field mappings
    field_mappings = []
    for fm_raw in raw.get("field_mappings", []):
        transform = fm_raw.get("transform", "identity")
        transform_params = {}
        # Parse transform params from string like "clamp(0, 1)"
        if "(" in transform:
            name, params_str = transform.split("(", 1)
            params_str = params_str.rstrip(")")
            transform = name.strip()
            # Parse simple numeric params
            parts = [p.strip() for p in params_str.split(",") if p.strip()]
            if transform == "clamp" and len(parts) == 2:
                transform_params = {"min_val": float(parts[0]), "max_val": float(parts[1])}
            elif transform == "scale" and len(parts) == 1:
                transform_params = {"factor": float(parts[0])}
            elif transform == "round" and len(parts) == 1:
                transform_params = {"decimals": int(parts[0])}

        field_mappings.append(FieldMapping(
            source=fm_raw.get("source", ""),
            target=fm_raw.get("target", ""),
            when=fm_raw.get("when"),
            transform=transform,
            transform_params=transform_params,
            semantic_tag=fm_raw.get("semantic_tag"),
        ))

    # Validation rules
    validation_rules = raw.get("validation_rules", [])

    # Target table
    target_table = raw.get("target_table", "metric_timeseries")

    return MappingDefinition(
        version=version,
        source_connector=source_connector,
        event_type=event_type,
        filter_expr=filter_expr,
        entity_resolution=entity_resolution,
        field_mappings=field_mappings,
        validation_rules=validation_rules,
        target_table=target_table,
    )


def load_all_mappings(mappings_dir: Path) -> list[MappingDefinition]:
    """Load all YAML mapping files from a directory.

    Args:
        mappings_dir: Directory containing .yaml mapping files.

    Returns:
        List of MappingDefinition objects.

    Raises:
        ValueError: If any mapping file is invalid.
    """
    if not mappings_dir.exists():
        return []

    mappings = []
    for filepath in sorted(mappings_dir.glob("*.yaml")):
        mapping = load_mapping_file(filepath)
        mappings.append(mapping)
    return mappings


def find_matching_mapping(mappings: list[MappingDefinition],
                          source_connector: str,
                          event_type: str,
                          payload: dict) -> Optional[MappingDefinition]:
    """Find the first mapping that matches a CTE's connector, event_type, and filter.

    Args:
        mappings: All loaded mapping definitions.
        source_connector: The CTE's source_connector.
        event_type: The CTE's event_type.
        payload: The CTE's payload dict.

    Returns:
        The matching MappingDefinition or None.
    """
    for mapping in mappings:
        if mapping.source_connector != source_connector:
            continue
        if mapping.event_type != event_type:
            continue
        # Check filter expression if present
        if mapping.filter_expr:
            if not _evaluate_filter(mapping.filter_expr, payload):
                continue
        return mapping
    return None


def _evaluate_filter(filter_expr: str, payload: dict) -> bool:
    """Evaluate a simple filter expression against a payload.

    Supports expressions like:
        "payload.metadata.model_type == 'classification'"
        "payload.metric_name == 'accuracy'"

    Args:
        filter_expr: Simple equality expression.
        payload: The CTE payload dict.

    Returns:
        True if the filter matches, False otherwise.
    """
    try:
        # Support "field == 'value'" syntax
        if "==" in filter_expr:
            left, right = filter_expr.split("==", 1)
            left = left.strip()
            right = right.strip().strip("'\"")

            # Navigate dot path through payload
            value = _extract_dot_path(left, payload)
            return str(value) == right
    except (KeyError, TypeError, IndexError):
        pass
    return False


def _extract_dot_path(path: str, data: dict) -> Any:
    """Extract a value from a nested dict using dot notation.

    Strips leading "payload." prefix if present since we're already in payload context.
    """
    # Strip "payload." prefix
    if path.startswith("payload."):
        path = path[len("payload."):]

    parts = path.split(".")
    current = data
    for part in parts:
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return None
    return current
