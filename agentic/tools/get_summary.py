"""Tool: Get platform summary stats."""

import data_source
from agentic.tools import BaseTool, ToolContext, ToolResult


class GetSummaryTool(BaseTool):
    name = "get_summary"
    description = "Get a high-level summary of the platform: total models, agents, active alerts, and health status."
    parameters = {
        "type": "object",
        "properties": {},
        "required": [],
    }

    def execute(self, params: dict, context: ToolContext) -> ToolResult:
        stats = data_source.get_summary_stats_combined()
        alerts = data_source.get_alerts()

        alert_summary = {"total": 0, "critical": 0, "warning": 0, "info": 0}
        if alerts:
            alert_summary["total"] = len(alerts)
            for a in alerts:
                sev = a.get("severity", "").lower()
                if sev in alert_summary:
                    alert_summary[sev] += 1

        summary_data = {
            "stats": stats,
            "alerts": alert_summary,
            "data_source_mode": context.data_source_mode,
        }

        if context.data_source_mode == "mock":
            summary_data["industry"] = context.current_industry

        total_entities = stats.get("total_models", 0) + stats.get("total_agents", 0)
        summary = (
            f"Platform monitoring {total_entities} entities "
            f"({stats.get('total_models', 0)} models, {stats.get('total_agents', 0)} agents). "
            f"{alert_summary['total']} active alerts ({alert_summary['critical']} critical)."
        )

        return ToolResult(
            success=True,
            data=summary_data,
            summary=summary,
            source=context.data_source_mode,
        )
