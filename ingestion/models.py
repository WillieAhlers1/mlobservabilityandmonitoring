"""Canonical Telemetry Event (CTE) data model.

Every raw event from any source is normalized to this intermediate format
before being stored in the staging store and processed by the mapping engine.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class CanonicalTelemetryEvent:
    """A single normalized telemetry event.

    Attributes:
        event_id: Deterministic hash for deduplication.
        source_connector: Connector that produced this event (e.g., "mlflow", "file_drop").
        source_entity_ref: Source-specific entity reference (e.g., "mlflow://exp-1/run-abc").
        event_type: One of: metric, prediction, drift, trace, alert, lifecycle.
        timestamp: ISO 8601 UTC event time (when the event occurred at source).
        received_at: ISO 8601 UTC ingestion time (when we received it).
        mapping_version: Version of the mapping definition used to process.
        payload: Arbitrary JSON-serializable dict with event-specific data.
        processing_status: One of: pending, mapped, rejected, duplicate.
        rejection_reason: Set when processing_status is "rejected".
    """

    event_id: str
    source_connector: str
    source_entity_ref: str
    event_type: str
    timestamp: str
    received_at: str
    mapping_version: str
    payload: dict
    processing_status: str = "pending"
    rejection_reason: Optional[str] = None
