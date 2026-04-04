import os
from unittest.mock import MagicMock, patch

_FAKE_LLM = "ollama/" + os.environ.get("OLLAMA_MODEL", "qwen2.5:7b")


@patch("crewai.agent.core.create_llm", return_value=MagicMock())
def test_maintenance_agent_role(_mock):
    from src.agents.maintenance import build_maintenance_agent
    agent = build_maintenance_agent(_FAKE_LLM, tools=[])
    assert "Maintenance" in agent.role or "maintenance" in agent.role.lower()


@patch("crewai.agent.core.create_llm", return_value=MagicMock())
def test_maintenance_task_includes_stale_issues(_mock):
    from src.agents.maintenance import build_maintenance_agent, build_maintenance_task
    agent = build_maintenance_agent(_FAKE_LLM, tools=[])
    stale = [{"number": 5, "title": "Old issue", "html_url": "https://github.com/o/r/issues/5", "days_stale": 10}]
    task = build_maintenance_task(
        agent=agent, stale_issues=stale, auto_close_issues=[],
        wip_violations=[], repo="owner/repo",
    )
    assert "#5" in task.description
    assert "Old issue" in task.description


@patch("crewai.agent.core.create_llm", return_value=MagicMock())
def test_maintenance_task_includes_wip_violations(_mock):
    from src.agents.maintenance import build_maintenance_agent, build_maintenance_task
    agent = build_maintenance_agent(_FAKE_LLM, tools=[])
    violations = [{"label": "feature", "count": 7, "limit": 5}]
    task = build_maintenance_task(
        agent=agent, stale_issues=[], auto_close_issues=[],
        wip_violations=violations, repo="owner/repo",
    )
    assert "feature" in task.description
    assert "7" in task.description
