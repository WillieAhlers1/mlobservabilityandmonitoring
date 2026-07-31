"""FileDropConnector — reads CSV/JSON files from a watched directory.

Scans a configured directory for new files, parses rows into CTEs,
and moves processed files to a separate directory for audit.
"""

import csv
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from ingestion.connectors.base import BaseConnector
from ingestion.models import CanonicalTelemetryEvent
from ingestion.staging import compute_event_id


class FileDropConnector(BaseConnector):
    """Connector that reads telemetry from CSV/JSON files in a directory."""

    def __init__(self, connector_config: dict):
        """Initialize from a connector config dict.

        Expected config keys:
            id: Unique connector ID
            watch_directory: Path to watch for new files
            processed_directory: Path to move files after processing
            file_pattern: Glob pattern (default: "*.csv")
            column_mapping: Dict mapping CSV columns to CTE fields
        """
        self._id = connector_config["id"]
        self._watch_dir = Path(connector_config["watch_directory"])
        self._processed_dir = Path(connector_config.get(
            "processed_directory",
            str(self._watch_dir / "processed")
        ))
        self._file_pattern = connector_config.get("file_pattern", "*.csv")
        self._column_mapping = connector_config.get("column_mapping", {})

    def connector_id(self) -> str:
        return self._id

    def connector_type(self) -> str:
        return "file_drop"

    def health_check(self) -> bool:
        """Check if the watch directory exists and is accessible."""
        return self._watch_dir.exists() and self._watch_dir.is_dir()

    def poll(self) -> list[CanonicalTelemetryEvent]:
        """Scan for new files, parse them, and return CTEs.

        Files are moved to processed_directory after successful parsing.
        """
        if not self.health_check():
            return []

        self._processed_dir.mkdir(parents=True, exist_ok=True)

        ctes = []
        for filepath in sorted(self._watch_dir.glob(self._file_pattern)):
            if filepath.is_file() and not filepath.name.startswith("."):
                file_ctes = self._process_file(filepath)
                ctes.extend(file_ctes)
                # Move to processed
                dest = self._processed_dir / filepath.name
                # Handle name collision
                if dest.exists():
                    stem = filepath.stem
                    suffix = filepath.suffix
                    ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
                    dest = self._processed_dir / f"{stem}_{ts}{suffix}"
                shutil.move(str(filepath), str(dest))

        return ctes

    def _process_file(self, filepath: Path) -> list[CanonicalTelemetryEvent]:
        """Parse a single file into CTEs."""
        suffix = filepath.suffix.lower()
        if suffix == ".csv":
            return self._parse_csv(filepath)
        elif suffix == ".json":
            return self._parse_json(filepath)
        return []

    def _parse_csv(self, filepath: Path) -> list[CanonicalTelemetryEvent]:
        """Parse a CSV file into CTEs using column_mapping."""
        ctes = []
        now = datetime.now(timezone.utc).isoformat()

        # Column mapping config
        entity_ref_col = self._column_mapping.get("entity_ref_column", "source_entity_ref")
        event_type_col = self._column_mapping.get("event_type_column", "event_type")
        timestamp_col = self._column_mapping.get("timestamp_column", "timestamp")
        # For metric events
        metric_name_col = self._column_mapping.get("metric_name_column", "metric_name")
        value_col = self._column_mapping.get("value_column", "metric_value")

        with open(filepath, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                entity_ref = row.get(entity_ref_col, "")
                if not entity_ref:
                    continue

                timestamp = row.get(timestamp_col, now)
                event_type = self._infer_event_type(row, filepath, event_type_col)
                metric_name = row.get(metric_name_col)

                # Build payload from all row columns
                payload = {k: v for k, v in row.items()
                           if k not in (entity_ref_col, timestamp_col, event_type_col)}

                # Try to convert value to float
                if value_col in payload:
                    try:
                        payload[value_col] = float(payload[value_col])
                    except (ValueError, TypeError):
                        pass  # Leave as string — validation will catch it

                event_id = compute_event_id(
                    self._id, entity_ref, event_type, timestamp, metric_name
                )

                ctes.append(CanonicalTelemetryEvent(
                    event_id=event_id,
                    source_connector=self._id,
                    source_entity_ref=entity_ref,
                    event_type=event_type,
                    timestamp=timestamp,
                    received_at=now,
                    mapping_version="v1",
                    payload=payload,
                ))

        return ctes

    def _parse_json(self, filepath: Path) -> list[CanonicalTelemetryEvent]:
        """Parse a JSON file (array of objects) into CTEs."""
        ctes = []
        now = datetime.now(timezone.utc).isoformat()

        entity_ref_col = self._column_mapping.get("entity_ref_column", "source_entity_ref")
        timestamp_col = self._column_mapping.get("timestamp_column", "timestamp")
        event_type_col = self._column_mapping.get("event_type_column", "event_type")
        metric_name_col = self._column_mapping.get("metric_name_column", "metric_name")

        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        if isinstance(data, dict):
            data = [data]

        for record in data:
            entity_ref = record.get(entity_ref_col, "")
            if not entity_ref:
                continue

            timestamp = record.get(timestamp_col, now)
            event_type = record.get(event_type_col, "metric")
            metric_name = record.get(metric_name_col)

            payload = {k: v for k, v in record.items()
                       if k not in (entity_ref_col, timestamp_col, event_type_col)}

            event_id = compute_event_id(
                self._id, entity_ref, event_type, timestamp, metric_name
            )

            ctes.append(CanonicalTelemetryEvent(
                event_id=event_id,
                source_connector=self._id,
                source_entity_ref=entity_ref,
                event_type=event_type,
                timestamp=timestamp,
                received_at=now,
                mapping_version="v1",
                payload=payload,
            ))

        return ctes

    def _infer_event_type(self, row: dict, filepath: Path, event_type_col: str) -> str:
        """Infer event type from row content or filename."""
        # Explicit column takes priority
        if event_type_col in row and row[event_type_col]:
            return row[event_type_col]

        # Infer from filename
        name = filepath.stem.lower()
        if "drift" in name:
            return "drift"
        elif "alert" in name:
            return "alert"
        elif "trace" in name:
            return "trace"
        elif "lifecycle" in name:
            return "lifecycle"
        elif "quality" in name:
            return "metric"
        elif "cohort" in name:
            return "prediction"
        return "metric"
