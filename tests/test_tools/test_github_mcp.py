from unittest.mock import MagicMock, patch
from src.tools.github_mcp import mcp_tools_for, AGENT_TOOL_WHITELIST


def _make_mock_tool(name: str):
    t = MagicMock()
    t.name = name
    return t


def test_triage_gets_no_tools():
    with mcp_tools_for("triage") as tools:
        assert tools == []


def test_whitelist_filters_tools():
    expected_whitelist = AGENT_TOOL_WHITELIST["action"]
    allowed = [_make_mock_tool(n) for n in expected_whitelist]

    mock_adapter = MagicMock()
    mock_adapter.__enter__ = MagicMock(return_value=mock_adapter)
    mock_adapter.__exit__ = MagicMock(return_value=False)
    mock_adapter.filter_by_names = MagicMock(return_value=allowed)

    with patch("src.tools.github_mcp.MCPServerAdapter", return_value=mock_adapter):
        with mcp_tools_for("action") as tools:
            tool_names = [t.name for t in tools]

    mock_adapter.filter_by_names.assert_called_once_with(expected_whitelist)
    assert set(tool_names) == set(expected_whitelist)


def test_unknown_agent_gets_no_tools():
    with mcp_tools_for("nonexistent_agent") as tools:
        assert tools == []


def test_whitelist_completeness():
    # All 4 agents must be in the whitelist
    for agent in ["triage", "dedup", "devsecops", "action"]:
        assert agent in AGENT_TOOL_WHITELIST


def test_action_has_required_tools():
    action_tools = AGENT_TOOL_WHITELIST["action"]
    for required in [
        "add_issue_comment",
        "issue_write",
        "list_issues",
        "create_check_run",
        "create_issue",
    ]:
        assert required in action_tools
