"""Tool: Query metrics for a model or agent."""

import data_source
from agentic.tools import BaseTool, ToolContext, ToolResult


class QueryMetricsTool(BaseTool):
    name = "query_metrics"
    description = "Get performance metrics for a specific model or agent by entity ID."
    parameters = {
        "type": "object",
        "properties": {
            "entity_id": {
                "type": "string",
                "description": "The entity ID to query metrics for. Use '_first_' to get the first available entity.",
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
            else:
                agents = data_source.get_agents()
                if agents:
                    entity_id = agents[0].get("id", "")

        if not entity_id:
            return ToolResult(success=False, error="No entity_id provided and no entities available.")

        # Determine entity type
        entity = data_source.get_entity(entity_id)
        if not entity:
            return ToolResult(success=False, error=f"Entity '{entity_id}' not found.")

        entity_type = entity.get("entity_type", entity.get("type", "model"))

        if entity_type == "agent":
            metrics = data_source.get_agent_metrics(entity_id)
        else:
            metrics = data_source.get_model_metrics(entity_id)

        if not metrics:
            return ToolResult(
                success=True,
                data={"entity_id": entity_id, "metrics": None},
                summary=f"No metrics available for entity '{entity_id}'.",
                source=context.data_source_mode,
            )

        return ToolResult(
            success=True,
            data={"entity_id": entity_id, "entity_name": entity.get("name", ""), "metrics": metrics},
            summary=f"Retrieved metrics for {entity.get('name', entity_id)} ({entity_type}).",
            source=context.data_source_mode,
        )
