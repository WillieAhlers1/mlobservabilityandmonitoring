"""Tool: Get projects list."""

import data_source
from agentic.tools import BaseTool, ToolContext, ToolResult


class GetProjectsTool(BaseTool):
    name = "get_projects"
    description = "List all projects with their entity counts and status."
    parameters = {
        "type": "object",
        "properties": {},
        "required": [],
    }

    def execute(self, params: dict, context: ToolContext) -> ToolResult:
        projects = data_source.get_projects()

        if not projects:
            return ToolResult(
                success=True,
                data=[],
                summary="No projects found.",
                source=context.data_source_mode,
            )

        project_list = []
        for p in projects:
            project_list.append({
                "id": p.get("id", ""),
                "name": p.get("name", ""),
                "description": p.get("description", ""),
                "status": p.get("status", "Active"),
            })

        return ToolResult(
            success=True,
            data=project_list,
            summary=f"Found {len(project_list)} project(s).",
            source=context.data_source_mode,
        )
