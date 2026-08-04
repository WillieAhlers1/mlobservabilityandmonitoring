"""Tool: Switch industry (mock mode only)."""

import data_source
from agentic.tools import BaseTool, ToolContext, ToolResult


class SwitchIndustryTool(BaseTool):
    name = "switch_industry"
    description = "Switch the active industry for mock/demo data. Available industries: hls, retail, industrials, hospitality."
    parameters = {
        "type": "object",
        "properties": {
            "industry_id": {
                "type": "string",
                "enum": ["hls", "retail", "industrials", "hospitality"],
                "description": "The industry to switch to.",
            }
        },
        "required": ["industry_id"],
    }

    def execute(self, params: dict, context: ToolContext) -> ToolResult:
        industry_id = params.get("industry_id", "")
        available = data_source.get_available_industries()
        valid_ids = [ind.get("id", "") for ind in available]

        if industry_id not in valid_ids:
            return ToolResult(
                success=False,
                error=f"Invalid industry '{industry_id}'. Available: {valid_ids}",
                source="mock",
            )

        data_source.set_industry(industry_id)
        new_meta = next((ind for ind in available if ind.get("id") == industry_id), {})

        return ToolResult(
            success=True,
            data={"switched_to": industry_id, "industry_meta": new_meta},
            summary=f"Switched to industry: {new_meta.get('name', industry_id)}.",
            source="mock",
        )
