"""Tool base classes and registry for the agentic interface."""

from dataclasses import dataclass, field
from abc import ABC, abstractmethod
import json
import sqlite3


@dataclass
class ToolContext:
    """Context passed to every tool execution."""
    db: sqlite3.Connection | None = None
    data_source_mode: str = "mock"  # "mock" or "live"
    current_industry: str = "hls"
    industry_meta: dict = field(default_factory=dict)
    available_industries: list = field(default_factory=list)
    user_session: dict = field(default_factory=dict)


@dataclass
class ToolResult:
    """Result returned by a tool execution."""
    success: bool = True
    data: dict | list | None = None
    summary: str = ""
    source: str = "mock"  # "mock" or "live"
    error: str | None = None


class BaseTool(ABC):
    """Abstract base class for all agentic tools."""

    name: str = ""
    description: str = ""
    parameters: dict = {}

    @abstractmethod
    def execute(self, params: dict, context: ToolContext) -> ToolResult:
        """Execute the tool with given parameters and context."""

    def to_openai_function(self) -> dict:
        """Convert this tool to OpenAI function-calling format."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class ToolRegistry:
    """Registry of available tools, built dynamically based on data source mode."""

    def __init__(self):
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool):
        """Register a tool by its name."""
        self._tools[tool.name] = tool

    def get(self, name: str) -> BaseTool | None:
        """Get a tool by name."""
        return self._tools.get(name)

    def get_all(self) -> list[BaseTool]:
        """Return all registered tools."""
        return list(self._tools.values())

    def get_openai_tools(self) -> list[dict]:
        """Return all tools in OpenAI function-calling format."""
        return [tool.to_openai_function() for tool in self._tools.values()]

    @property
    def names(self) -> list[str]:
        """Return all registered tool names."""
        return list(self._tools.keys())


def build_registry(data_source_mode: str) -> ToolRegistry:
    """Build a tool registry appropriate for the current data source mode.

    In mock mode, includes industry-specific tools (get_industry_info, switch_industry).
    In live mode, those tools are excluded.
    """
    from agentic.tools.list_entities import ListEntitiesTool
    from agentic.tools.query_metrics import QueryMetricsTool
    from agentic.tools.query_alerts import QueryAlertsTool
    from agentic.tools.query_drift import QueryDriftTool
    from agentic.tools.compare_entities import CompareEntitiesTool
    from agentic.tools.explain_lineage import ExplainLineageTool
    from agentic.tools.get_summary import GetSummaryTool
    from agentic.tools.get_projects import GetProjectsTool

    registry = ToolRegistry()

    # Core tools (available in both modes)
    registry.register(ListEntitiesTool())
    registry.register(QueryMetricsTool())
    registry.register(QueryAlertsTool())
    registry.register(QueryDriftTool())
    registry.register(CompareEntitiesTool())
    registry.register(ExplainLineageTool())
    registry.register(GetSummaryTool())
    registry.register(GetProjectsTool())

    # Mock-mode-only tools
    if data_source_mode == "mock":
        from agentic.tools.get_industry_info import GetIndustryInfoTool
        from agentic.tools.switch_industry import SwitchIndustryTool
        registry.register(GetIndustryInfoTool())
        registry.register(SwitchIndustryTool())

    return registry
