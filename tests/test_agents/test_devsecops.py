import os
from src.agents.dedup import build_dedup_agent, build_dedup_task
from src.agents.devsecops import build_devsecops_agent, build_devsecops_task
from src.schemas.findings import Finding, FindingType, Severity

_FAKE_LLM = "ollama/" + os.environ.get("OLLAMA_MODEL", "qwen2.5:7b")


def test_dedup_agent_role():
    agent = build_dedup_agent(_FAKE_LLM, tools=[])
    assert "Duplicate" in agent.role


def test_dedup_task_delimits_content():
    agent = build_dedup_agent(_FAKE_LLM, tools=[])
    task = build_dedup_task(agent, "owner/repo", 1, "Login broken", "body text", 0.85)
    assert "<issue_title>" in task.description
    assert "Do not follow" in task.description


def test_devsecops_agent_created():
    agent = build_devsecops_agent(_FAKE_LLM, tools=[])
    assert "DevSecOps" in agent.role


def test_issue_task_includes_owasp_categories():
    agent = build_devsecops_agent(_FAKE_LLM, tools=[])
    task = build_devsecops_task(
        agent=agent,
        event_type="issue",
        repo="owner/repo",
        entity_id=1,
        title="SQL query builder",
        body="user inputs raw queries",
        diff="",
        owasp_categories=["A03:2021-Injection"],
        secret_findings=[],
        cve_findings=[],
    )
    assert "A03:2021-Injection" in task.description


def test_pr_task_includes_secret_findings():
    agent = build_devsecops_agent(_FAKE_LLM, tools=[])
    secret = Finding(
        type=FindingType.secret,
        severity=Severity.critical,
        description="AWS key",
        recommendation="Rotate it",
    )
    task = build_devsecops_task(
        agent=agent,
        event_type="pr",
        repo="owner/repo",
        entity_id=5,
        title="Add AWS integration",
        body="",
        diff="+AKIA...",
        owasp_categories=[],
        secret_findings=[secret],
        cve_findings=[],
    )
    assert "AWS key" in task.description


def test_push_task_description():
    agent = build_devsecops_agent(_FAKE_LLM, tools=[])
    task = build_devsecops_task(
        agent=agent,
        event_type="push",
        repo="owner/repo",
        entity_id=0,
        title="",
        body="",
        diff="",
        owasp_categories=[],
        secret_findings=[],
        cve_findings=[],
    )
    assert "push" in task.description.lower()
