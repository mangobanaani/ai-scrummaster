import os

from src.agents.action import build_action_agent, build_action_task, _format_comment
from src.schemas.findings import Finding, FindingType, Severity, SecurityFindings
from src.schemas.dedup import DedupResult
from src.schemas.triage import TriageResult, RouteType

# Use a fake model string that CrewAI's validator accepts.
_FAKE_LLM = "ollama/" + os.environ.get("OLLAMA_MODEL", "qwen2.5:7b")


def test_format_comment_no_findings():
    result = _format_comment([], None)
    assert "No findings" in result


def test_format_comment_with_critical():
    f = Finding(type=FindingType.secret, severity=Severity.critical,
                description="AWS key found", recommendation="Rotate it")
    result = _format_comment([f], None)
    assert "AWS key found" in result
    assert "CRITICAL" in result


def test_format_comment_with_duplicate():
    dedup = DedupResult(
        is_duplicate=True,
        matched_issue_url="https://github.com/owner/repo/issues/5",
        confidence=0.92,
        reasoning="Same login bug",
    )
    result = _format_comment([], dedup)
    assert "Duplicate detected" in result
    assert "92%" in result


def test_action_agent_role():
    agent = build_action_agent(_FAKE_LLM, tools=[])
    assert "GitHub Action" in agent.role


def test_action_task_critical_cve_creates_ticket():
    agent = build_action_agent(_FAKE_LLM, tools=[])
    triage = TriageResult(route=RouteType.pr, repo="owner/repo", entity_id=10, pr_author="dev1")
    cve = Finding(type=FindingType.cve, severity=Severity.critical,
                  description="CVE-2024-1234 in requests@2.28.0",
                  recommendation="Upgrade to 2.31.0", cve_id="CVE-2024-1234",
                  package="requests", fixed_version="2.31.0")
    task = build_action_task(agent=agent, triage=triage, findings=[cve],
                              dedup=None, pr_number=10, repo="owner/repo")
    assert "issue_write" in task.description
    assert "blocker" in task.description
    assert "CVE-2024-1234" in task.description


def test_action_task_no_findings_adds_reviewed_label():
    agent = build_action_agent(_FAKE_LLM, tools=[])
    triage = TriageResult(route=RouteType.pr, repo="owner/repo", entity_id=5)
    task = build_action_task(agent=agent, triage=triage, findings=[],
                              dedup=None, pr_number=5, repo="owner/repo")
    assert "reviewed" in task.description


def test_action_task_pr_includes_check_run():
    """PR events should include a create_check_run instruction."""
    agent = build_action_agent(_FAKE_LLM, tools=[])
    triage = TriageResult(route=RouteType.pr, repo="owner/repo", entity_id=5)
    task = build_action_task(agent=agent, triage=triage, findings=[],
                              dedup=None, pr_number=5, repo="owner/repo")
    assert "create_check_run" in task.description
    assert "agentic-scrum-master" in task.description
    assert "success" in task.description


def test_action_task_pr_critical_findings_fail_check_run():
    """PR with critical findings should create a failing check run."""
    agent = build_action_agent(_FAKE_LLM, tools=[])
    triage = TriageResult(route=RouteType.pr, repo="owner/repo", entity_id=5)
    cve = Finding(type=FindingType.cve, severity=Severity.critical,
                  description="CVE-2024-1234", recommendation="Upgrade",
                  cve_id="CVE-2024-1234", package="requests")
    task = build_action_task(agent=agent, triage=triage, findings=[cve],
                              dedup=None, pr_number=5, repo="owner/repo")
    assert "create_check_run" in task.description
    assert "failure" in task.description


def test_action_task_issue_no_check_run():
    """Issue events should NOT include a check run instruction."""
    agent = build_action_agent(_FAKE_LLM, tools=[])
    triage = TriageResult(route=RouteType.issue, repo="owner/repo", entity_id=5)
    task = build_action_task(agent=agent, triage=triage, findings=[],
                              dedup=None, pr_number=None, repo="owner/repo")
    assert "create_check_run" not in task.description


def test_action_task_cve_uses_create_issue():
    """CVE ticket creation should use create_issue, not issue_write."""
    agent = build_action_agent(_FAKE_LLM, tools=[])
    triage = TriageResult(route=RouteType.pr, repo="owner/repo", entity_id=5, pr_author="dev1")
    cve = Finding(type=FindingType.cve, severity=Severity.critical,
                  description="CVE-2024-1234 in requests",
                  recommendation="Upgrade", cve_id="CVE-2024-1234",
                  package="requests", fixed_version="2.31.0")
    task = build_action_task(agent=agent, triage=triage, findings=[cve],
                              dedup=None, pr_number=5, repo="owner/repo")
    assert "create_issue" in task.description


def test_action_task_cve_no_pr_omits_pr_reference():
    """CVE ticket for non-PR events should not contain #None."""
    agent = build_action_agent(_FAKE_LLM, tools=[])
    triage = TriageResult(route=RouteType.issue, repo="owner/repo", entity_id=5)
    cve = Finding(type=FindingType.cve, severity=Severity.critical,
                  description="CVE-2024-1234 in requests",
                  recommendation="Upgrade", cve_id="CVE-2024-1234",
                  package="requests")
    task = build_action_task(agent=agent, triage=triage, findings=[cve],
                              dedup=None, pr_number=None, repo="owner/repo")
    assert "#None" not in task.description
    assert "Assigned to:" in task.description
    assignee_line = task.description.split("Assigned to:")[1].split("\n")[0]
    assert "None" not in assignee_line
