"""Tool: Get current industry info (mock mode only)."""

import data_source
from agentic.tools import BaseTool, ToolContext, ToolResult


class GetIndustryInfoTool(BaseTool):
    name = "get_industry_info"
    description = "Get the currently active industry and list available industries. Only available in mock/demo mode."
    parameters = {
        "type": "object",
        "properties": {},
        "required": [],
    }

    def execute(self, params: dict, context: ToolContext) -> ToolResult:
        current = data_source.get_current_industry()
        available = data_source.get_available_industries()

        return ToolResult(
            success=True,
            data={
                "current_industry": current,
                "industry_meta": context.industry_meta,
                "available_industries": available,
            },
            summary=f"Current industry: {context.industry_meta.get('name', current)}. "
                    f"{len(available)} industries available.",
            source="mock",
        )
