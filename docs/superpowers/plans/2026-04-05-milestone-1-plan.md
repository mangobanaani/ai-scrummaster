# Milestone 1: Complete the Core Loop — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire up PR diff fetching so DevSecOps scanning works on real code, add stale issue management with WIP enforcement, and add daily standup summaries.

**Architecture:** Three features sharing `src/tools/github_api.py` for GitHub REST calls. PR diff review plugs into the existing `run_crew_for_event` pipeline. Stale management and standup summaries get new endpoints, agents, and a GitHub Actions cron workflow.

**Tech Stack:** Python 3.12, FastAPI, httpx, CrewAI, Pydantic

---

## File Map

| Action | Path | Responsibility |
|--------|------|---------------|
| Modify | `src/tools/github_api.py` | Add `fetch_pr_diff`, `fetch_open_issues_with_dates`, `fetch_recent_activity` |
| Modify | `src/crew.py` | Fetch diff after triage for PR events; add `run_maintenance`, `run_standup` |
| Modify | `src/webhook_router.py` | PR action filter; `/maintenance` and `/standup` endpoints |
| Modify | `src/checks/policy.py` | Add `auto_close_days`, `stale_nudge_message` to `PolicyRules` |
| Modify | `policies/rules.yaml` | Add `auto_close_days: 30` |
| Create | `src/checks/staleness.py` | Pure functions: `find_stale_issues`, `check_wip_limits` |
| Create | `src/agents/maintenance.py` | Maintenance agent and task builder |
| Create | `src/agents/standup.py` | Standup agent and task builder |
| Create | `tests/test_checks/test_staleness.py` | Tests for staleness functions |
| Create | `tests/test_agents/test_maintenance.py` | Tests for maintenance agent/task |
| Create | `tests/test_agents/test_standup.py` | Tests for standup agent/task |
| Modify | `tests/test_tools/test_github_api.py` | Tests for new API functions |
| Modify | `tests/test_integration.py` | Integration tests for new endpoints |
| Create | `.github/workflows/maintenance.yml` | Cron workflow for maintenance + standup |

---

### Task 1: `fetch_pr_diff` — test and implement

**Files:**
- Modify: `src/tools/github_api.py`
- Modify: `tests/test_tools/test_github_api.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_tools/test_github_api.py`:

```python
@pytest.mark.asyncio
@respx.mock
async def test_fetch_pr_diff_returns_diff():
    diff_text = "+added line\n-removed line\n context line"
    respx.get("https://api.github.com/repos/owner/repo/pulls/5").mock(
        return_value=httpx.Response(200, text=diff_text)
    )
    from src.tools.github_api import fetch_pr_diff
    result = await fetch_pr_diff("tok", "owner/repo", 5)
    assert "+added line" in result
    assert "-removed line" in result


@pytest.mark.asyncio
@respx.mock
async def test_fetch_pr_diff_truncates_at_8000():
    diff_text = "x" * 10000
    respx.get("https://api.github.com/repos/owner/repo/pulls/1").mock(
        return_value=httpx.Response(200, text=diff_text)
    )
    from src.tools.github_api import fetch_pr_diff
    result = await fetch_pr_diff("tok", "owner/repo", 1)
    assert len(result) == 8000


@pytest.mark.asyncio
@respx.mock
async def test_fetch_pr_diff_returns_empty_on_error():
    respx.get("https://api.github.com/repos/owner/repo/pulls/1").mock(
        return_value=httpx.Response(404)
    )
    from src.tools.github_api import fetch_pr_diff
    result = await fetch_pr_diff("tok", "owner/repo", 1)
    assert result == ""
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_tools/test_github_api.py::test_fetch_pr_diff_returns_diff tests/test_tools/test_github_api.py::test_fetch_pr_diff_truncates_at_8000 tests/test_tools/test_github_api.py::test_fetch_pr_diff_returns_empty_on_error -v`

Expected: FAIL with `ImportError` — `fetch_pr_diff` does not exist yet.

- [ ] **Step 3: Implement `fetch_pr_diff`**

Add to `src/tools/github_api.py` after the existing imports:

```python
import logging

logger = logging.getLogger(__name__)
```

Add at the end of the file:

```python
async def fetch_pr_diff(token: str, repo: str, pr_number: int) -> str:
    """Fetch the unified diff for a pull request. Returns empty string on error."""
    url = f"{_GITHUB_API}/repos/{repo}/pulls/{pr_number}"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                url,
                headers={
                    **_HEADERS,
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/vnd.github.diff",
                },
            )
            resp.raise_for_status()
            diff = resp.text
            return diff[:8000]
    except httpx.HTTPError as exc:
        logger.warning("Failed to fetch diff for %s PR #%d: %s", repo, pr_number, exc)
        return ""
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_tools/test_github_api.py -v`

Expected: All 3 new tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/tools/github_api.py tests/test_tools/test_github_api.py
git commit -m "feat: add fetch_pr_diff to fetch PR diffs from GitHub API"
```

---

### Task 2: Wire diff fetching into the crew pipeline

**Files:**
- Modify: `src/crew.py:207-232`
- Modify: `src/webhook_router.py:38-60`

- [ ] **Step 1: Add PR action filter to webhook**

In `src/webhook_router.py`, add at the top of the `webhook` function, after the signature check and JSON parsing (after line 53 `raw["event_type"] = event_type`):

```python
    _PR_ACTIONS = {"opened", "synchronize", "reopened"}
    if event_type == "pull_request" and raw.get("action") not in _PR_ACTIONS:
        return Response(status_code=200)
```

- [ ] **Step 2: Add diff fetching to `run_crew_for_event`**

In `src/crew.py`, add the import at the top with other imports:

```python
import dataclasses
from src.tools.github_api import create_issue, fetch_open_issue_titles, link_sub_issue, fetch_pr_diff
```

Then after the triage block (after line `logger.info("Triage result: %s", triage.model_dump())`), add before the `# --- Pre-scan ---` comment:

```python
    # --- Fetch PR diff ---
    if triage.route == RouteType.pr and triage.entity_id:
        from src.sanitizer import sanitize_field
        diff = await fetch_pr_diff(settings.github_token, triage.repo, triage.entity_id)
        if diff:
            payload = dataclasses.replace(payload, diff=sanitize_field(diff, "diff"))
```

- [ ] **Step 3: Write integration test for PR diff pipeline**

Add to `tests/test_integration.py`:

```python
@pytest.mark.asyncio
async def test_webhook_pr_opened_fetches_diff():
    payload = {
        "action": "opened",
        "pull_request": {
            "number": 10,
            "title": "Add feature",
            "body": "PR body",
            "user": {"login": "dev1"},
        },
        "repository": {"full_name": "owner/repo"},
    }
    body = json.dumps(payload).encode()
    sig = _sign(body, settings.github_webhook_secret)

    with patch("src.webhook_router.run_crew_for_event", new_callable=AsyncMock) as mock_crew:
        mock_crew.return_value = {"status": "processed"}
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/webhook",
                content=body,
                headers={
                    "X-GitHub-Event": "pull_request",
                    "X-Hub-Signature-256": sig,
                    "Content-Type": "application/json",
                },
            )
    assert resp.status_code == 202
    mock_crew.assert_called_once()


@pytest.mark.asyncio
async def test_webhook_pr_labeled_is_skipped():
    payload = {
        "action": "labeled",
        "pull_request": {"number": 10, "title": "X", "body": ""},
        "repository": {"full_name": "owner/repo"},
    }
    body = json.dumps(payload).encode()
    sig = _sign(body, settings.github_webhook_secret)

    with patch("src.webhook_router.run_crew_for_event", new_callable=AsyncMock) as mock_crew:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/webhook",
                content=body,
                headers={
                    "X-GitHub-Event": "pull_request",
                    "X-Hub-Signature-256": sig,
                    "Content-Type": "application/json",
                },
            )
    assert resp.status_code == 200
    mock_crew.assert_not_called()
```

- [ ] **Step 4: Run all tests**

Run: `python -m pytest tests/test_integration.py -v`

Expected: All tests PASS including the two new ones.

- [ ] **Step 5: Commit**

```bash
git add src/crew.py src/webhook_router.py tests/test_integration.py
git commit -m "feat: fetch PR diffs and filter non-code webhook actions"
```

---

### Task 3: Staleness checker — pure functions

**Files:**
- Create: `src/checks/staleness.py`
- Create: `tests/test_checks/test_staleness.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_checks/test_staleness.py`:

```python
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
    issues = [
        _make_issue(i, 1, labels=["feature"]) for i in range(6)
    ]
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_checks/test_staleness.py -v`

Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement staleness functions**

Create `src/checks/staleness.py`:

```python
from datetime import datetime, timezone, timedelta


def find_stale_issues(issues: list[dict], stale_days: int) -> list[dict]:
    """Return issues where updated_at is older than stale_days ago."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=stale_days)
    stale = []
    for issue in issues:
        updated = datetime.fromisoformat(issue["updated_at"])
        if updated < cutoff:
            stale.append(issue)
    return stale


def check_wip_limits(issues: list[dict], limits: dict[str, int]) -> list[dict]:
    """Return label types that exceed their WIP limit."""
    label_counts: dict[str, int] = {}
    for issue in issues:
        for label in issue.get("labels", []):
            name = label["name"] if isinstance(label, dict) else label
            if name in limits:
                label_counts[name] = label_counts.get(name, 0) + 1

    violations = []
    for label, limit in limits.items():
        count = label_counts.get(label, 0)
        if count > limit:
            violations.append({"label": label, "count": count, "limit": limit})
    return violations
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_checks/test_staleness.py -v`

Expected: All 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/checks/staleness.py tests/test_checks/test_staleness.py
git commit -m "feat: add staleness checker for stale issues and WIP limits"
```

---

### Task 4: Policy config additions for staleness

**Files:**
- Modify: `src/checks/policy.py:16-23`
- Modify: `policies/rules.yaml`

- [ ] **Step 1: Add fields to `PolicyRules`**

In `src/checks/policy.py`, add two fields to `PolicyRules`:

```python
class PolicyRules(BaseModel):
    wip_limits: dict[str, int] = {"feature": 5, "bug": 10, "security": 3}
    stale_days: int = 7
    auto_close_days: int = 30
    stale_nudge_message: str = ""
    branch_naming: BranchNamingRule = BranchNamingRule()
    pr_requires_linked_issue: bool = True
    protected_branches: list[str] = ["main", "master"]
    cve_thresholds: CveThresholds = CveThresholds()
    dedup_confidence_threshold: float = 0.85
```

- [ ] **Step 2: Update rules.yaml**

Add to `policies/rules.yaml` after `stale_days: 7`:

```yaml
auto_close_days: 30
```

- [ ] **Step 3: Run existing policy tests**

Run: `python -m pytest tests/test_checks/test_policy.py -v`

Expected: All PASS (new fields have defaults, backward compatible).

- [ ] **Step 4: Commit**

```bash
git add src/checks/policy.py policies/rules.yaml
git commit -m "feat: add auto_close_days and stale_nudge_message to policy config"
```

---

### Task 5: `fetch_open_issues_with_dates` API function

**Files:**
- Modify: `src/tools/github_api.py`
- Modify: `tests/test_tools/test_github_api.py`

- [ ] **Step 1: Write failing test**

Add to `tests/test_tools/test_github_api.py`:

```python
@pytest.mark.asyncio
@respx.mock
async def test_fetch_open_issues_with_dates():
    respx.get("https://api.github.com/repos/owner/repo/issues").mock(
        return_value=httpx.Response(200, json=[
            {
                "number": 1,
                "title": "Issue 1",
                "updated_at": "2026-03-01T00:00:00Z",
                "labels": [{"name": "bug"}],
                "assignee": {"login": "dev1"},
                "html_url": "https://github.com/owner/repo/issues/1",
            },
        ])
    )
    from src.tools.github_api import fetch_open_issues_with_dates
    issues = await fetch_open_issues_with_dates("tok", "owner/repo")
    assert len(issues) == 1
    assert issues[0]["number"] == 1
    assert issues[0]["updated_at"] == "2026-03-01T00:00:00Z"
    assert issues[0]["labels"][0]["name"] == "bug"
```

- [ ] **Step 2: Implement**

Add to `src/tools/github_api.py`:

```python
async def fetch_open_issues_with_dates(token: str, repo: str) -> list[dict]:
    """Fetch open issues with updated_at, labels, assignee, and html_url."""
    url = f"{_GITHUB_API}/repos/{repo}/issues"
    all_issues: list[dict] = []
    async with httpx.AsyncClient(timeout=30.0) as client:
        for page in range(1, 6):
            resp = await client.get(
                url,
                headers={**_HEADERS, "Authorization": f"Bearer {token}"},
                params={"state": "open", "per_page": 100, "page": page},
            )
            resp.raise_for_status()
            batch = resp.json()
            if not batch:
                break
            for issue in batch:
                all_issues.append({
                    "number": issue["number"],
                    "title": issue["title"],
                    "updated_at": issue["updated_at"],
                    "labels": issue.get("labels", []),
                    "assignee": issue.get("assignee"),
                    "html_url": issue["html_url"],
                })
    return all_issues
```

- [ ] **Step 3: Run tests**

Run: `python -m pytest tests/test_tools/test_github_api.py -v`

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add src/tools/github_api.py tests/test_tools/test_github_api.py
git commit -m "feat: add fetch_open_issues_with_dates for maintenance scanning"
```

---

### Task 6: Maintenance agent and task builder

**Files:**
- Create: `src/agents/maintenance.py`
- Create: `tests/test_agents/test_maintenance.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_agents/test_maintenance.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_agents/test_maintenance.py -v`

Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

Create `src/agents/maintenance.py`:

```python
from crewai import Agent, Task, LLM


def build_maintenance_agent(llm: LLM, tools: list) -> Agent:
    return Agent(
        role="Repository Maintenance Manager",
        goal=(
            "Manage stale issues by posting nudge comments, closing abandoned issues, "
            "and reporting WIP limit violations. Follow exact instructions."
        ),
        backstory=(
            "You are a project maintenance agent. You keep the issue tracker healthy "
            "by nudging stale issues and enforcing work-in-progress limits."
        ),
        llm=llm,
        tools=tools,
        verbose=False,
        max_iter=10,
    )


def build_maintenance_task(
    agent: Agent,
    stale_issues: list[dict],
    auto_close_issues: list[dict],
    wip_violations: list[dict],
    repo: str,
) -> Task:
    instructions = [
        f"Execute maintenance actions for repository '{repo}':\n",
    ]

    if stale_issues:
        instructions.append("**Stale issues to nudge** (post a comment reminding the assignee):")
        for issue in stale_issues:
            assignee = issue.get("assignee", {})
            assignee_name = assignee.get("login", "unassigned") if assignee else "unassigned"
            instructions.append(
                f"- Issue #{issue['number']}: \"{issue['title']}\" "
                f"(stale {issue['days_stale']} days, assigned to @{assignee_name})"
            )
            instructions.append(
                f"  Call add_issue_comment on #{issue['number']} with a polite nudge."
            )
            instructions.append(
                f"  Call issue_write on #{issue['number']} to add label 'stale'."
            )

    if auto_close_issues:
        instructions.append("\n**Issues to close** (inactive beyond auto-close threshold):")
        for issue in auto_close_issues:
            instructions.append(
                f"- Issue #{issue['number']}: \"{issue['title']}\" "
                f"(stale {issue['days_stale']} days)"
            )
            instructions.append(
                f"  Call add_issue_comment on #{issue['number']} explaining closure due to inactivity."
            )
            instructions.append(
                f"  Call issue_write on #{issue['number']} with state='closed'."
            )

    if wip_violations:
        instructions.append("\n**WIP limit violations:**")
        for v in wip_violations:
            instructions.append(
                f"- Label '{v['label']}': {v['count']} open issues (limit: {v['limit']})"
            )

    if not stale_issues and not auto_close_issues and not wip_violations:
        instructions.append("No maintenance actions needed. All clear.")

    instructions.append("\nDo not make any tool calls not listed above.")

    return Task(
        description="\n".join(instructions),
        expected_output="Confirmation of all maintenance actions taken.",
        agent=agent,
    )
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_agents/test_maintenance.py -v`

Expected: All 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/agents/maintenance.py tests/test_agents/test_maintenance.py
git commit -m "feat: add maintenance agent for stale issues and WIP enforcement"
```

---

### Task 7: Maintenance endpoint and crew runner

**Files:**
- Modify: `src/webhook_router.py`
- Modify: `src/crew.py`
- Modify: `tests/test_integration.py`

- [ ] **Step 1: Add `run_maintenance` to `src/crew.py`**

Add imports at the top of `src/crew.py`:

```python
from src.checks.staleness import find_stale_issues, check_wip_limits
from src.agents.maintenance import build_maintenance_agent, build_maintenance_task
from src.tools.github_api import create_issue, fetch_open_issue_titles, link_sub_issue, fetch_pr_diff, fetch_open_issues_with_dates
```

Add at the end of the file:

```python
async def run_maintenance(repo: str) -> dict:
    """Run stale issue detection and WIP limit enforcement."""
    llm = _make_llm()
    policy = _get_policy()

    issues = await fetch_open_issues_with_dates(settings.github_token, repo)

    stale = find_stale_issues(issues, policy.rules.stale_days)
    wip_violations = check_wip_limits(issues, policy.rules.wip_limits)

    stale_nudge = []
    stale_close = []
    for issue in stale:
        from datetime import datetime, timezone
        updated = datetime.fromisoformat(issue["updated_at"])
        days = (datetime.now(timezone.utc) - updated).days
        entry = {**issue, "days_stale": days}
        if days >= policy.rules.auto_close_days:
            stale_close.append(entry)
        else:
            stale_nudge.append(entry)

    if not stale_nudge and not stale_close and not wip_violations:
        return {"status": "clean", "repo": repo}

    with mcp_tools_for("action") as tools:
        agent = build_maintenance_agent(llm, tools)
        task = build_maintenance_task(
            agent=agent,
            stale_issues=stale_nudge,
            auto_close_issues=stale_close,
            wip_violations=wip_violations,
            repo=repo,
        )
        crew = Crew(agents=[agent], tasks=[task], process=Process.sequential)
        await crew.kickoff_async()

    return {
        "status": "maintenance_complete",
        "repo": repo,
        "stale_nudged": len(stale_nudge),
        "stale_closed": len(stale_close),
        "wip_violations": len(wip_violations),
    }
```

- [ ] **Step 2: Add `/maintenance` endpoint to `src/webhook_router.py`**

Add import at top:

```python
from src.crew import run_crew_for_event, run_maintenance
```

Add the endpoint after the `/scan` endpoint:

```python
@router.post("/maintenance")
async def maintenance(
    request: Request,
    background_tasks: BackgroundTasks,
    _: None = Depends(_require_api_key),
):
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")
    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="Expected JSON object")
    try:
        repo = validate_repo(data.get("repo", ""))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    async def _run():
        try:
            result = await run_maintenance(repo)
            logger.info("Maintenance completed: %s", result)
        except Exception:
            logger.exception("Maintenance failed for repo %s", repo)

    background_tasks.add_task(_run)
    return Response(status_code=202)
```

- [ ] **Step 3: Write integration test**

Add to `tests/test_integration.py`:

```python
@pytest.mark.asyncio
async def test_maintenance_endpoint():
    with patch("src.webhook_router.run_maintenance", new_callable=AsyncMock) as mock_maint:
        mock_maint.return_value = {"status": "clean"}
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/maintenance",
                json={"repo": "owner/repo"},
                headers={"X-Api-Key": settings.api_key},
            )
    assert resp.status_code == 202
    mock_maint.assert_called_once()


@pytest.mark.asyncio
async def test_maintenance_missing_api_key():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/maintenance", json={"repo": "owner/repo"})
    assert resp.status_code == 403
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_integration.py -v`

Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add src/crew.py src/webhook_router.py tests/test_integration.py
git commit -m "feat: add /maintenance endpoint for stale issue management"
```

---

### Task 8: `fetch_recent_activity` API function

**Files:**
- Modify: `src/tools/github_api.py`
- Modify: `tests/test_tools/test_github_api.py`

- [ ] **Step 1: Write failing test**

Add to `tests/test_tools/test_github_api.py`:

```python
@pytest.mark.asyncio
@respx.mock
async def test_fetch_recent_activity():
    now = "2026-04-05T12:00:00Z"
    respx.get("https://api.github.com/repos/owner/repo/issues").mock(
        return_value=httpx.Response(200, json=[
            {"number": 1, "title": "Open issue", "state": "open",
             "pull_request": None, "updated_at": now, "user": {"login": "dev1"},
             "labels": [], "assignee": None},
            {"number": 2, "title": "Closed issue", "state": "closed",
             "pull_request": None, "closed_at": now, "updated_at": now,
             "user": {"login": "dev1"}, "labels": [], "assignee": None},
        ])
    )
    respx.get("https://api.github.com/repos/owner/repo/pulls").mock(
        return_value=httpx.Response(200, json=[
            {"number": 10, "title": "Active PR", "state": "open",
             "merged_at": None, "user": {"login": "dev2"},
             "requested_reviewers": [{"login": "rev1"}]},
        ])
    )
    from src.tools.github_api import fetch_recent_activity
    activity = await fetch_recent_activity("tok", "owner/repo", since_hours=24)
    assert len(activity["opened_issues"]) >= 1
    assert len(activity["active_prs"]) == 1
    assert activity["active_prs"][0]["author"] == "dev2"
```

- [ ] **Step 2: Implement**

Add to `src/tools/github_api.py`:

```python
async def fetch_recent_activity(token: str, repo: str, since_hours: int = 24) -> dict:
    """Fetch recent issues and PRs for standup summaries."""
    from datetime import datetime, timezone, timedelta
    since = (datetime.now(timezone.utc) - timedelta(hours=since_hours)).isoformat()
    headers = {**_HEADERS, "Authorization": f"Bearer {token}"}

    activity = {
        "merged_prs": [],
        "active_prs": [],
        "opened_issues": [],
        "closed_issues": [],
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Fetch recently updated issues
        resp = await client.get(
            f"{_GITHUB_API}/repos/{repo}/issues",
            headers=headers,
            params={"state": "all", "since": since, "per_page": 100, "sort": "updated"},
        )
        resp.raise_for_status()
        for item in resp.json():
            if item.get("pull_request"):
                continue
            entry = {"number": item["number"], "title": item["title"], "author": item["user"]["login"]}
            if item["state"] == "open":
                activity["opened_issues"].append(entry)
            else:
                activity["closed_issues"].append(entry)

        # Fetch recently updated PRs
        resp = await client.get(
            f"{_GITHUB_API}/repos/{repo}/pulls",
            headers=headers,
            params={"state": "all", "sort": "updated", "direction": "desc", "per_page": 50},
        )
        resp.raise_for_status()
        for pr in resp.json():
            entry = {
                "number": pr["number"],
                "title": pr["title"],
                "author": pr["user"]["login"],
                "reviewers": [r["login"] for r in pr.get("requested_reviewers", [])],
            }
            if pr.get("merged_at"):
                activity["merged_prs"].append(entry)
            elif pr["state"] == "open":
                activity["active_prs"].append(entry)

    return activity
```

- [ ] **Step 3: Run tests**

Run: `python -m pytest tests/test_tools/test_github_api.py -v`

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add src/tools/github_api.py tests/test_tools/test_github_api.py
git commit -m "feat: add fetch_recent_activity for standup summaries"
```

---

### Task 9: Standup agent and task builder

**Files:**
- Create: `src/agents/standup.py`
- Create: `tests/test_agents/test_standup.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_agents/test_standup.py`:

```python
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
```

- [ ] **Step 2: Implement**

Create `src/agents/standup.py`:

```python
from crewai import Agent, Task, LLM


def build_standup_agent(llm: LLM) -> Agent:
    return Agent(
        role="Daily Standup Reporter",
        goal="Summarize recent repository activity into a concise daily standup report.",
        backstory=(
            "You are a scrum master who writes clear, brief daily standup summaries. "
            "You organize activity into Done, In Progress, and Blocked sections. "
            "Keep it factual and concise."
        ),
        llm=llm,
        tools=[],
        verbose=False,
        max_iter=3,
    )


def build_standup_task(agent: Agent, activity: dict, repo: str) -> Task:
    merged = activity.get("merged_prs", [])
    active = activity.get("active_prs", [])
    opened = activity.get("opened_issues", [])
    closed = activity.get("closed_issues", [])

    total = len(merged) + len(active) + len(opened) + len(closed)
    if total == 0:
        description = (
            f"Write a brief daily standup summary for '{repo}'.\n\n"
            f"There was no activity in the last 24 hours. Write a short 'quiet day' summary."
        )
    else:
        lines = [f"Write a daily standup summary for '{repo}' based on this activity:\n"]

        if merged:
            lines.append("**Merged PRs (Done):**")
            for pr in merged:
                lines.append(f"- PR #{pr['number']}: {pr['title']} (by @{pr['author']})")

        if closed:
            lines.append("\n**Closed Issues (Done):**")
            for issue in closed:
                lines.append(f"- Issue #{issue['number']}: {issue['title']}")

        if active:
            lines.append("\n**Active PRs (In Progress):**")
            for pr in active:
                reviewers = ", ".join(f"@{r}" for r in pr.get("reviewers", []))
                lines.append(f"- PR #{pr['number']}: {pr['title']} (by @{pr['author']}, reviewers: {reviewers or 'none'})")

        if opened:
            lines.append("\n**Opened Issues:**")
            for issue in opened:
                lines.append(f"- Issue #{issue['number']}: {issue['title']} (by @{issue['author']})")

        lines.append(
            "\nFormat the output as a clean markdown standup with sections: "
            "Done, In Progress, Blocked (if any seem blocked), and Metrics."
        )
        description = "\n".join(lines)

    return Task(
        description=description,
        expected_output=(
            "A markdown-formatted daily standup report with sections: "
            "Done, In Progress, Blocked, Metrics."
        ),
        agent=agent,
    )
```

- [ ] **Step 3: Run tests**

Run: `python -m pytest tests/test_agents/test_standup.py -v`

Expected: All 3 tests PASS.

- [ ] **Step 4: Commit**

```bash
git add src/agents/standup.py tests/test_agents/test_standup.py
git commit -m "feat: add standup agent for daily activity summaries"
```

---

### Task 10: Standup endpoint and crew runner

**Files:**
- Modify: `src/crew.py`
- Modify: `src/webhook_router.py`
- Modify: `tests/test_integration.py`

- [ ] **Step 1: Add `run_standup` to `src/crew.py`**

Add imports at top:

```python
from src.agents.standup import build_standup_agent, build_standup_task
from src.tools.github_api import create_issue, fetch_open_issue_titles, link_sub_issue, fetch_pr_diff, fetch_open_issues_with_dates, fetch_recent_activity
```

Add at the end of the file:

```python
async def run_standup(repo: str, since_hours: int = 24) -> dict:
    """Generate and post a daily standup summary."""
    llm = _make_llm()

    activity = await fetch_recent_activity(settings.github_token, repo, since_hours)

    agent = build_standup_agent(llm)
    task = build_standup_task(agent, activity, repo)
    crew = Crew(agents=[agent], tasks=[task], process=Process.sequential)
    output = await crew.kickoff_async()

    summary = str(output)
    from datetime import date
    title = f"Daily Standup - {date.today().isoformat()}"

    await create_issue(
        token=settings.github_token,
        repo=repo,
        title=title,
        body=summary,
        labels=["standup"],
    )

    return {"status": "standup_posted", "repo": repo, "title": title}
```

- [ ] **Step 2: Add `/standup` endpoint to `src/webhook_router.py`**

Update the import:

```python
from src.crew import run_crew_for_event, run_maintenance, run_standup
```

Add endpoint after `/maintenance`:

```python
@router.post("/standup")
async def standup(
    request: Request,
    background_tasks: BackgroundTasks,
    _: None = Depends(_require_api_key),
):
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")
    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="Expected JSON object")
    try:
        repo = validate_repo(data.get("repo", ""))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    since_hours = data.get("since_hours", 24)

    async def _run():
        try:
            result = await run_standup(repo, since_hours)
            logger.info("Standup completed: %s", result)
        except Exception:
            logger.exception("Standup failed for repo %s", repo)

    background_tasks.add_task(_run)
    return Response(status_code=202)
```

- [ ] **Step 3: Write integration tests**

Add to `tests/test_integration.py`:

```python
@pytest.mark.asyncio
async def test_standup_endpoint():
    with patch("src.webhook_router.run_standup", new_callable=AsyncMock) as mock_standup:
        mock_standup.return_value = {"status": "standup_posted"}
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/standup",
                json={"repo": "owner/repo"},
                headers={"X-Api-Key": settings.api_key},
            )
    assert resp.status_code == 202
    mock_standup.assert_called_once()


@pytest.mark.asyncio
async def test_standup_missing_api_key():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/standup", json={"repo": "owner/repo"})
    assert resp.status_code == 403
```

- [ ] **Step 4: Run all tests**

Run: `python -m pytest tests/ -v`

Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add src/crew.py src/webhook_router.py tests/test_integration.py
git commit -m "feat: add /standup endpoint for daily standup summaries"
```

---

### Task 11: GitHub Actions cron workflow

**Files:**
- Create: `.github/workflows/maintenance.yml`

- [ ] **Step 1: Create workflow file**

Create `.github/workflows/maintenance.yml`:

```yaml
name: Daily Maintenance

on:
  schedule:
    - cron: '0 9 * * 1-5'
  workflow_dispatch:

jobs:
  standup:
    runs-on: ubuntu-latest
    steps:
      - name: Post daily standup
        run: |
          curl -sf -X POST "${{ secrets.APP_URL }}/standup" \
            -H "Content-Type: application/json" \
            -H "X-Api-Key: ${{ secrets.API_KEY }}" \
            -d "{\"repo\": \"${{ github.repository }}\"}"

  maintenance:
    runs-on: ubuntu-latest
    steps:
      - name: Run stale issue maintenance
        run: |
          curl -sf -X POST "${{ secrets.APP_URL }}/maintenance" \
            -H "Content-Type: application/json" \
            -H "X-Api-Key: ${{ secrets.API_KEY }}" \
            -d "{\"repo\": \"${{ github.repository }}\"}"
```

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/maintenance.yml
git commit -m "ci: add cron workflow for daily standup and maintenance"
```

---

### Task 12: Final integration test and push

- [ ] **Step 1: Run full test suite**

Run: `python -m pytest tests/ -v --tb=short`

Expected: All tests PASS.

- [ ] **Step 2: Push to remote**

```bash
git push origin main
```
