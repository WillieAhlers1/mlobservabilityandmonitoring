"""Tool: Compare two entities side by side."""

import data_source
from agentic.tools import BaseTool, ToolContext, ToolResult


class CompareEntitiesTool(BaseTool):
    name = "compare_entities"
    description = "Compare metrics between two models or agents side by side."
    parameters = {
        "type": "object",
        "properties": {
            "entity_a": {
                "type": "string",
                "description": "First entity ID. Use '_first_' for the first available.",
            },
            "entity_b": {
                "type": "string",
                "description": "Second entity ID. Use '_second_' for the second available.",
            },
        },
        "required": ["entity_a", "entity_b"],
    }

    def execute(self, params: dict, context: ToolContext) -> ToolResult:
        entity_a_id = params.get("entity_a", "")
        entity_b_id = params.get("entity_b", "")

        # Resolve placeholders
        all_entities = data_source.get_models() + data_source.get_agents()
        if entity_a_id == "_first_" and len(all_entities) > 0:
            entity_a_id = all_entities[0].get("id", "")
        if entity_b_id == "_second_" and len(all_entities) > 1:
            entity_b_id = all_entities[1].get("id", "")

        if not entity_a_id or not entity_b_id:
            return ToolResult(success=False, error="Need at least two entities to compare.")

        entity_a = data_source.get_entity(entity_a_id)
        entity_b = data_source.get_entity(entity_b_id)

        if not entity_a:
            return ToolResult(success=False, error=f"Entity '{entity_a_id}' not found.")
        if not entity_b:
            return ToolResult(success=False, error=f"Entity '{entity_b_id}' not found.")

        # Get metrics for both
        type_a = entity_a.get("entity_type", entity_a.get("type", "model"))
        type_b = entity_b.get("entity_type", entity_b.get("type", "model"))

        metrics_a = (data_source.get_agent_metrics(entity_a_id)
                     if type_a == "agent" else data_source.get_model_metrics(entity_a_id))
        metrics_b = (data_source.get_agent_metrics(entity_b_id)
                     if type_b == "agent" else data_source.get_model_metrics(entity_b_id))

        comparison = {
            "entity_a": {"id": entity_a_id, "name": entity_a.get("name", ""), "type": type_a, "metrics": metrics_a},
            "entity_b": {"id": entity_b_id, "name": entity_b.get("name", ""), "type": type_b, "metrics": metrics_b},
        }

        return ToolResult(
            success=True,
            data=comparison,
            summary=f"Comparison between {entity_a.get('name', entity_a_id)} and {entity_b.get('name', entity_b_id)}.",
            source=context.data_source_mode,
        )
