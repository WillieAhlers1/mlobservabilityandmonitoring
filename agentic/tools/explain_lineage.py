"""Tool: Explain model/agent lineage and version history."""

import data_source
from agentic.tools import BaseTool, ToolContext, ToolResult


class ExplainLineageTool(BaseTool):
    name = "explain_lineage"
    description = "Describe the version history and lifecycle events for a model or agent."
    parameters = {
        "type": "object",
        "properties": {
            "entity_id": {
                "type": "string",
                "description": "The entity ID to get lineage for. Use '_first_' for the first available.",
            }
        },
        "required": ["entity_id"],
    }

    def execute(self, params: dict, context: ToolContext) -> ToolResult:
        entity_id = params.get("entity_id", "")

        # Handle placeholder
        if entity_id == "_first_":
            models = data_source.get_models()
            if models:
                entity_id = models[0].get("id", "")

        if not entity_id:
            return ToolResult(success=False, error="No entity_id provided.")

        entity = data_source.get_entity(entity_id)
        if not entity:
            return ToolResult(success=False, error=f"Entity '{entity_id}' not found.")

        lineage = data_source.get_model_lineage(entity_id)

        if not lineage:
            return ToolResult(
                success=True,
                data={"entity_id": entity_id, "lineage": None},
                summary=f"No lineage data available for '{entity.get('name', entity_id)}'.",
                source=context.data_source_mode,
            )

        return ToolResult(
            success=True,
            data={"entity_id": entity_id, "entity_name": entity.get("name", ""), "lineage": lineage},
            summary=f"Lineage for {entity.get('name', entity_id)}: {len(lineage.get('versions', [])) if isinstance(lineage, dict) else 0} versions.",
            source=context.data_source_mode,
        )
