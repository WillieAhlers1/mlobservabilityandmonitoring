"""Base classes for agentic tools — re-exported from tools package."""

# The actual classes are defined in agentic/tools/__init__.py for convenience.
# This file exists so imports like `from agentic.tools.base import BaseTool` work.

from agentic.tools import BaseTool, ToolContext, ToolResult

__all__ = ["BaseTool", "ToolContext", "ToolResult"]
