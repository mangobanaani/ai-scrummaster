import pytest
from pydantic import ValidationError
from src.schemas.findings import Finding, FindingType, SecurityFindings, Severity
from src.schemas.story import TicketDraft, DecomposedStories
from src.schemas.triage import RouteType, TriageResult


def test_ticket_draft_defaults_empty_deps():
    t = TicketDraft(
        title="Setup project",
        type="epic",
        category="infra",
        size="L",
        priority="high",
        body="As a developer...",
    )
    assert t.depends_on == []


def test_ticket_draft_with_deps():
    t = TicketDraft(
        title="Board model",
        type="story",
        category="data-model",
        size="S",
        priority="medium",
        body="As a developer...",
        depends_on=[0],
    )
    assert t.depends_on == [0]


def test_ticket_draft_rejects_invalid_type():
    with pytest.raises(ValidationError):
        TicketDraft(
            title="X", type="sprint", category="x",
            size="S", priority="low", body="x"
        )


def test_ticket_draft_rejects_invalid_size():
    with pytest.raises(ValidationError):
        TicketDraft(
            title="X", type="story", category="x",
            size="HUGE", priority="low", body="x"
        )


def test_decomposed_stories_empty_default():
    d = DecomposedStories()
    assert d.tickets == []


def test_decomposed_stories_with_tickets():
    d = DecomposedStories(tickets=[
        TicketDraft(title="Epic", type="epic", category="infra", size="L", priority="high", body="..."),
        TicketDraft(title="Story", type="story", category="backend", size="S", priority="medium",
                    body="...", depends_on=[0]),
    ])
    assert len(d.tickets) == 2
    assert d.tickets[1].depends_on == [0]


def test_triage_result_fields():
    r = TriageResult(route=RouteType.issue, repo="owner/repo", entity_id=42)
    assert r.repo == "owner/repo"
    assert r.entity_id == 42


def test_security_findings_has_critical():
    f = Finding(
        type=FindingType.cve,
        severity=Severity.critical,
        description="Critical CVE",
        recommendation="Upgrade now",
    )
    sf = SecurityFindings(findings=[f])
    assert sf.has_critical is True
    assert len(sf.critical_cves) == 1


def test_security_findings_no_critical():
    sf = SecurityFindings(findings=[])
    assert sf.has_critical is False
