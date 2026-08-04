"""Tool: List entities (models and/or agents)."""

import data_source
from agentic.tools import BaseTool, ToolContext, ToolResult


class ListEntitiesTool(BaseTool):
    name = "list_entities"
    description = "List all monitored models and/or agents. Can filter by entity type (model, agent, or all)."
    parameters = {
        "type": "object",
        "properties": {
            "entity_type": {
                "type": "string",
                "enum": ["model", "agent", "all"],
                "description": "Filter by entity type. Defaults to 'all'.",
            }
        },
        "required": [],
    }

    def execute(self, params: dict, context: ToolContext) -> ToolResult:
        entity_type = params.get("entity_type", "all")

        results = []
        if entity_type in ("model", "all"):
            models = data_source.get_models()
            for m in models:
                results.append({
                    "id": m.get("id", ""),
                    "name": m.get("name", ""),
                    "type": "model",
                    "status": m.get("status", ""),
                    "model_type": m.get("model_type", ""),
                })

        if entity_type in ("agent", "all"):
            agents = data_source.get_agents()
            for a in agents:
                results.append({
                    "id": a.get("id", ""),
                    "name": a.get("name", ""),
                    "type": "agent",
                    "status": a.get("status", ""),
                    "framework": a.get("framework", ""),
                })

        summary = f"Found {len(results)} entities"
        if entity_type != "all":
            summary += f" of type '{entity_type}'"

        return ToolResult(
            success=True,
            data=results,
            summary=summary,
            source=context.data_source_mode,
        )
