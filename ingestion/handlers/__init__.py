"""Handler modules for specialized CTE event types.

Each handler processes CTEs of a specific event_type and writes to
the corresponding metric store table(s).
"""

from ingestion.handlers.drift import DriftHandler
from ingestion.handlers.alerts import AlertsHandler
from ingestion.handlers.cohorts import CohortsHandler
from ingestion.handlers.features import FeaturesHandler
from ingestion.handlers.data_quality import DataQualityHandler
from ingestion.handlers.lifecycle import LifecycleHandler
from ingestion.handlers.traces import TracesHandler

# Registry mapping event_type → handler class
HANDLER_REGISTRY = {
    "drift": DriftHandler,
    "alert": AlertsHandler,
    "cohort": CohortsHandler,
    "feature_importance": FeaturesHandler,
    "data_quality": DataQualityHandler,
    "lifecycle": LifecycleHandler,
    "trace": TracesHandler,
}

__all__ = [
    "HANDLER_REGISTRY",
    "DriftHandler",
    "AlertsHandler",
    "CohortsHandler",
    "FeaturesHandler",
    "DataQualityHandler",
    "LifecycleHandler",
    "TracesHandler",
]
