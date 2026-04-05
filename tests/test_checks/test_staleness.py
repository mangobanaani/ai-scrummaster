from datetime import datetime, timezone, timedelta
from src.checks.staleness import find_stale_issues, check_wip_limits


def _make_issue(number, updated_days_ago, labels=None):
    updated = datetime.now(timezone.utc) - timedelta(days=updated_days_ago)
    return {
        "number": number,
        "title": f"Issue #{number}",
        "updated_at": updated.isoformat(),
        "labels": [{"name": l} for l in (labels or [])],
        "assignee": {"login": "dev1"} if number % 2 == 0 else None,
        "html_url": f"https://github.com/owner/repo/issues/{number}",
    }


def test_find_stale_issues_returns_old_issues():
    issues = [_make_issue(1, 10), _make_issue(2, 3), _make_issue(3, 8)]
    stale = find_stale_issues(issues, stale_days=7)
    numbers = [i["number"] for i in stale]
    assert 1 in numbers
    assert 3 in numbers
    assert 2 not in numbers


def test_find_stale_issues_none_stale():
    issues = [_make_issue(1, 1), _make_issue(2, 3)]
    stale = find_stale_issues(issues, stale_days=7)
    assert stale == []


def test_check_wip_limits_detects_violations():
    issues = [_make_issue(i, 1, labels=["feature"]) for i in range(6)]
    limits = {"feature": 5, "bug": 10}
    violations = check_wip_limits(issues, limits)
    assert len(violations) == 1
    assert violations[0]["label"] == "feature"
    assert violations[0]["count"] == 6
    assert violations[0]["limit"] == 5


def test_check_wip_limits_no_violations():
    issues = [_make_issue(1, 1, labels=["feature"])]
    limits = {"feature": 5}
    violations = check_wip_limits(issues, limits)
    assert violations == []
