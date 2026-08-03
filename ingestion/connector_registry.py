"""Connector registry — discovers and instantiates connectors from config."""

from typing import Optional

from ingestion.connectors.base import BaseConnector
from ingestion.connectors.file_drop import FileDropConnector
from ingestion.connectors.webhook import WebhookConnector


# Registry of connector type names to classes
CONNECTOR_TYPES = {
    "file_drop": FileDropConnector,
    "webhook": WebhookConnector,
}


def create_connector(connector_config: dict) -> BaseConnector:
    """Create a connector instance from a config dict.

    Args:
        connector_config: Dict with at minimum "id" and "type" keys.

    Returns:
        A BaseConnector instance.

    Raises:
        ValueError: If connector type is unknown or config is invalid.
    """
    connector_type = connector_config.get("type")
    if not connector_type:
        raise ValueError(f"Connector config missing 'type': {connector_config}")

    cls = CONNECTOR_TYPES.get(connector_type)
    if cls is None:
        raise ValueError(f"Unknown connector type: {connector_type}")

    connector_id = connector_config.get("id")
    if not connector_id:
        raise ValueError(f"Connector config missing 'id': {connector_config}")

    return cls(connector_config)


def create_all_connectors(connectors_config: list[dict]) -> list[BaseConnector]:
    """Create all connector instances from the config list.

    Args:
        connectors_config: List of connector config dicts from app.yaml.

    Returns:
        List of instantiated BaseConnector objects.
    """
    connectors = []
    for cfg in connectors_config:
        connector = create_connector(cfg)
        connectors.append(connector)
    return connectors
