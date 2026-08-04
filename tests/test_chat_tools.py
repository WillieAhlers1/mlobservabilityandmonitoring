"""Tests for agentic chat tools — each tool in isolation."""

import pytest
import data_source
from agentic.tools import ToolContext, build_registry
from agentic.tools.list_entities import ListEntitiesTool
from agentic.tools.query_metrics import QueryMetricsTool
from agentic.tools.query_alerts import QueryAlertsTool
from agentic.tools.query_drift import QueryDriftTool
from agentic.tools.compare_entities import CompareEntitiesTool
from agentic.tools.explain_lineage import ExplainLineageTool
from agentic.tools.get_summary import GetSummaryTool
from agentic.tools.get_projects import GetProjectsTool
from agentic.tools.get_industry_info import GetIndustryInfoTool
from agentic.tools.switch_industry import SwitchIndustryTool


@pytest.fixture(autouse=True)
def mock_mode(monkeypatch):
    """Ensure mock data source mode for all tool tests."""
    monkeypatch.setattr(data_source, "DATA_SOURCE", "mock")


@pytest.fixture
def context():
    """Basic mock-mode tool context."""
    return ToolContext(
        db=None,
        data_source_mode="mock",
        current_industry="hls",
        industry_meta={"id": "hls", "name": "Healthcare & Life Sciences", "icon": "fa-heartbeat"},
        available_industries=data_source.get_available_industries(),
    )


class TestListEntities:
    def test_list_all(self, context):
        tool = ListEntitiesTool()
        result = tool.execute({"entity_type": "all"}, context)
        assert result.success
        assert result.source == "mock"
        assert len(result.data) > 0

    def test_list_models_only(self, context):
        tool = ListEntitiesTool()
        result = tool.execute({"entity_type": "model"}, context)
        assert result.success
        assert all(e["type"] == "model" for e in result.data)

    def test_list_agents_only(self, context):
        tool = ListEntitiesTool()
        result = tool.execute({"entity_type": "agent"}, context)
        assert result.success
        assert all(e["type"] == "agent" for e in result.data)

    def test_openai_function_format(self):
        tool = ListEntitiesTool()
        func = tool.to_openai_function()
        assert func["type"] == "function"
        assert func["function"]["name"] == "list_entities"
        assert "description" in func["function"]


class TestQueryMetrics:
    def test_query_first_model(self, context):
        tool = QueryMetricsTool()
        result = tool.execute({"entity_id": "_first_"}, context)
        assert result.success
        assert result.data is not None
        assert "entity_id" in result.data

    def test_query_nonexistent(self, context):
        tool = QueryMetricsTool()
        result = tool.execute({"entity_id": "nonexistent-xyz"}, context)
        assert not result.success
        assert result.error is not None

    def test_empty_entity_id(self, context):
        tool = QueryMetricsTool()
        result = tool.execute({"entity_id": ""}, context)
        # Should resolve to first available or error
        assert result.data is not None or result.error is not None


class TestQueryAlerts:
    def test_all_alerts(self, context):
        tool = QueryAlertsTool()
        result = tool.execute({}, context)
        assert result.success
        assert result.source == "mock"

    def test_filter_by_severity(self, context):
        tool = QueryAlertsTool()
        result = tool.execute({"severity": "critical"}, context)
        assert result.success
        if result.data:
            assert all(
                a.get("severity", "").lower() == "critical" for a in result.data
            )

    def test_limit(self, context):
        tool = QueryAlertsTool()
        result = tool.execute({"limit": 2}, context)
        assert result.success
        assert len(result.data) <= 2


class TestQueryDrift:
    def test_drift_first_model(self, context):
        tool = QueryDriftTool()
        result = tool.execute({"entity_id": "_first_"}, context)
        assert result.success
        assert result.source == "mock"

    def test_drift_nonexistent(self, context):
        tool = QueryDriftTool()
        result = tool.execute({"entity_id": "nonexistent-xyz"}, context)
        assert not result.success


class TestCompareEntities:
    def test_compare_first_two(self, context):
        tool = CompareEntitiesTool()
        result = tool.execute({"entity_a": "_first_", "entity_b": "_second_"}, context)
        assert result.success
        assert "entity_a" in result.data
        assert "entity_b" in result.data

    def test_compare_nonexistent(self, context):
        tool = CompareEntitiesTool()
        result = tool.execute({"entity_a": "fake1", "entity_b": "fake2"}, context)
        assert not result.success


class TestExplainLineage:
    def test_lineage_first(self, context):
        tool = ExplainLineageTool()
        result = tool.execute({"entity_id": "_first_"}, context)
        assert result.success
        assert result.source == "mock"


class TestGetSummary:
    def test_summary(self, context):
        tool = GetSummaryTool()
        result = tool.execute({}, context)
        assert result.success
        assert "stats" in result.data
        assert "alerts" in result.data
        assert result.data["data_source_mode"] == "mock"
        assert "industry" in result.data


class TestGetProjects:
    def test_projects(self, context):
        tool = GetProjectsTool()
        result = tool.execute({}, context)
        assert result.success
        assert isinstance(result.data, list)


class TestGetIndustryInfo:
    def test_industry_info(self, context):
        tool = GetIndustryInfoTool()
        result = tool.execute({}, context)
        assert result.success
        assert result.source == "mock"
        assert "current_industry" in result.data
        assert "available_industries" in result.data


class TestSwitchIndustry:
    def test_switch_valid(self, context):
        tool = SwitchIndustryTool()
        result = tool.execute({"industry_id": "retail"}, context)
        assert result.success
        assert result.data["switched_to"] == "retail"

    def test_switch_invalid(self, context):
        tool = SwitchIndustryTool()
        result = tool.execute({"industry_id": "nonexistent"}, context)
        assert not result.success
        assert "Invalid industry" in result.error


class TestToolRegistry:
    def test_mock_mode_includes_industry_tools(self):
        registry = build_registry("mock")
        assert "get_industry_info" in registry.names
        assert "switch_industry" in registry.names

    def test_live_mode_excludes_industry_tools(self):
        registry = build_registry("live")
        assert "get_industry_info" not in registry.names
        assert "switch_industry" not in registry.names

    def test_core_tools_in_both_modes(self):
        for mode in ("mock", "live"):
            registry = build_registry(mode)
            assert "list_entities" in registry.names
            assert "query_metrics" in registry.names
            assert "query_alerts" in registry.names
            assert "get_summary" in registry.names
