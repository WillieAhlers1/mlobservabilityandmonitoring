"""Tool: Query alerts."""

import data_source
from agentic.tools import BaseTool, ToolContext, ToolResult


class QueryAlertsTool(BaseTool):
    name = "query_alerts"
    description = "List recent alerts across all monitored entities. Can filter by severity."
    parameters = {
        "type": "object",
        "properties": {
            "severity": {
                "type": "string",
                "enum": ["critical", "warning", "info", "all"],
                "description": "Filter alerts by severity level. Defaults to 'all'.",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of alerts to return. Defaults to 10.",
            },
        },
        "required": [],
    }

    def execute(self, params: dict, context: ToolContext) -> ToolResult:
        severity_filter = params.get("severity", "all")
        limit = params.get("limit", 10)

        alerts = data_source.get_alerts()
        if not alerts:
            return ToolResult(
                success=True,
                data=[],
                summary="No alerts found.",
                source=context.data_source_mode,
            )

        # Filter by severity if specified
        if severity_filter and severity_filter != "all":
            alerts = [a for a in alerts if a.get("severity", "").lower() == severity_filter.lower()]

        # Limit results
        alerts = alerts[:limit]

        # Summarize
        summary_parts = [f"Found {len(alerts)} alert(s)"]
        if severity_filter != "all":
            summary_parts.append(f"with severity '{severity_filter}'")

        return ToolResult(
            success=True,
            data=alerts,
            summary=" ".join(summary_parts) + ".",
            source=context.data_source_mode,
        )
