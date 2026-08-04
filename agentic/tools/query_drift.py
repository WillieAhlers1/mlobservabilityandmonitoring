"""Tool: Query drift events for a model."""

import data_source
from agentic.tools import BaseTool, ToolContext, ToolResult


class QueryDriftTool(BaseTool):
    name = "query_drift"
    description = "Get drift detection status and events for a specific model."
    parameters = {
        "type": "object",
        "properties": {
            "entity_id": {
                "type": "string",
                "description": "The entity ID to check drift for. Use '_first_' for the first available model.",
            }
        },
        "required": ["entity_id"],
    }

    def execute(self, params: dict, context: ToolContext) -> ToolResult:
        entity_id = params.get("entity_id", "")

        # Handle _first_ placeholder
        if entity_id == "_first_":
            models = data_source.get_models()
            if models:
                entity_id = models[0].get("id", "")

        if not entity_id:
            return ToolResult(success=False, error="No entity_id provided and no models available.")

        entity = data_source.get_entity(entity_id)
        if not entity:
            return ToolResult(success=False, error=f"Entity '{entity_id}' not found.")

        # Get drift info from metrics (drift is typically part of model metrics)
        metrics = data_source.get_model_metrics(entity_id)
        drift_info = None
        if metrics:
            drift_info = {
                "entity_id": entity_id,
                "entity_name": entity.get("name", ""),
                "drift_score": metrics.get("drift_score"),
                "drift_status": metrics.get("drift_status", "unknown"),
                "features_drifted": metrics.get("features_drifted", []),
            }

        if not drift_info or drift_info.get("drift_score") is None:
            return ToolResult(
                success=True,
                data={"entity_id": entity_id, "drift": None},
                summary=f"No drift data available for '{entity.get('name', entity_id)}'.",
                source=context.data_source_mode,
            )

        return ToolResult(
            success=True,
            data=drift_info,
            summary=f"Drift status for {entity.get('name', entity_id)}: {drift_info.get('drift_status', 'unknown')}.",
            source=context.data_source_mode,
        )
