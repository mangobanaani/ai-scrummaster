from contextlib import contextmanager
from crewai_tools import MCPServerAdapter
from src.config import settings

# Per-agent tool whitelists — only these MCP tools can be called by each agent.
AGENT_TOOL_WHITELIST: dict[str, list[str]] = {
    "triage": [],
    "dedup": ["search_issues"],
    "devsecops": ["get_file_contents", "pull_request_read"],
    "action": [
        "add_issue_comment",
        "create_issue",
        "issue_write",
        "list_issues",
        "create_check_run",
    ],
}


@contextmanager
def mcp_tools_for(agent_name: str):
    """
    Context manager that yields a filtered list of CrewAI tools for the given agent.
    Opens a connection to the GitHub MCP SSE server and closes it on exit.
    Only tools in AGENT_TOOL_WHITELIST[agent_name] are returned.
    """
    whitelist = AGENT_TOOL_WHITELIST.get(agent_name, [])

    if not whitelist:
        yield []
        return

    token = settings.github_token
    server_config = {
        "url": settings.mcp_server_url,
        "transport": "sse",
        "headers": {"Authorization": f"Bearer {token}"},
    }

    with MCPServerAdapter(server_config) as tools:
        filtered = tools.filter_by_names(whitelist)
        missing = set(whitelist) - {t.name for t in filtered}
        if missing:
            import logging
            logging.getLogger(__name__).warning(
                "MCP tools not found on server (check server version): %s", missing
            )
        yield list(filtered)
