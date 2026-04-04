import os
from unittest.mock import MagicMock, patch

_FAKE_LLM = "ollama/" + os.environ.get("OLLAMA_MODEL", "qwen2.5:7b")


@patch("crewai.agent.core.create_llm", return_value=MagicMock())
def test_standup_agent_role(_mock):
    from src.agents.standup import build_standup_agent
    agent = build_standup_agent(_FAKE_LLM)
    assert "Standup" in agent.role or "standup" in agent.role.lower()


@patch("crewai.agent.core.create_llm", return_value=MagicMock())
def test_standup_task_includes_activity(_mock):
    from src.agents.standup import build_standup_agent, build_standup_task
    agent = build_standup_agent(_FAKE_LLM)
    activity = {
        "merged_prs": [{"number": 10, "title": "Add auth", "author": "dev1"}],
        "active_prs": [],
        "opened_issues": [{"number": 5, "title": "Bug report", "author": "user1"}],
        "closed_issues": [],
    }
    task = build_standup_task(agent, activity, "owner/repo")
    assert "Add auth" in task.description
    assert "Bug report" in task.description
    assert "owner/repo" in task.description


@patch("crewai.agent.core.create_llm", return_value=MagicMock())
def test_standup_task_handles_empty_activity(_mock):
    from src.agents.standup import build_standup_agent, build_standup_task
    agent = build_standup_agent(_FAKE_LLM)
    activity = {"merged_prs": [], "active_prs": [], "opened_issues": [], "closed_issues": []}
    task = build_standup_task(agent, activity, "owner/repo")
    assert "quiet" in task.description.lower() or "no activity" in task.description.lower()
