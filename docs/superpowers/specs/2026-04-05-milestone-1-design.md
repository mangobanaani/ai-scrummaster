# Milestone 1: Complete the Core Loop

Three features that finish what's half-built and add the first proactive automation.

## Feature 1: PR Diff Review

### Problem

The DevSecOps pipeline accepts a `diff` field on `SanitizedPayload` and passes it to the secret scanner and DevSecOps agent, but `sanitize_payload` never fetches the actual diff from GitHub. The secret scanner and diff-aware analysis are dead code for PR events.

### Solution

Fetch the PR diff via the GitHub REST API when a PR webhook arrives, populate `payload.diff`, and let the existing pipeline do its job.

### Implementation

**New function in `src/tools/github_api.py`:**

```python
async def fetch_pr_diff(token: str, repo: str, pr_number: int) -> str:
    """Fetch the unified diff for a pull request."""
```

- Calls `GET /repos/{owner}/{repo}/pulls/{pr_number}` with header `Accept: application/vnd.github.diff`
- Returns raw diff string, truncated to 8000 chars (matches `_FIELD_LIMITS["diff"]`)
- Returns empty string on error (logged, non-fatal)

**Changes to `src/crew.py` in `run_crew_for_event`:**

After triage determines `route == pr`, before the pre-scan phase:

```python
if triage.route == RouteType.pr and triage.entity_id:
    diff = await fetch_pr_diff(settings.github_token, triage.repo, triage.entity_id)
    payload = dataclasses.replace(payload, diff=sanitize_field(diff, "diff"))
```

**Webhook action filter in `src/webhook_router.py`:**

Only dispatch for PR actions that involve code changes:

```python
PR_ACTIONS = {"opened", "synchronize", "reopened"}
if event_type == "pull_request" and raw.get("action") not in PR_ACTIONS:
    return Response(status_code=200)  # acknowledge but skip
```

### What this enables

- `scan_for_secrets(payload.diff)` will find leaked credentials in PR diffs
- The DevSecOps agent receives actual code changes to review
- The action agent can post findings as PR comments with line references

### Testing

- Unit test: mock GitHub API response with a sample diff, verify `fetch_pr_diff` returns truncated content
- Integration test: mock the full pipeline with a PR webhook, verify secret findings are detected in the diff
- Edge cases: empty diff, diff exceeding 8KB, API error returns empty string

---

## Feature 2: Stale Issue Management

### Problem

The policy engine defines `stale_days: 7` and `wip_limits` but nothing uses them proactively. Stale issues accumulate, WIP limits are never enforced, and the scrum master only reacts to incoming events.

### Solution

A maintenance endpoint that runs on a schedule (via cron, GitHub Action, or manual trigger), scans open issues, and takes action on stale ones.

### Implementation

**New file `src/checks/staleness.py`:**

Pure functions with no LLM dependency:

```python
def find_stale_issues(issues: list[dict], stale_days: int) -> list[dict]:
    """Return issues where updated_at is older than stale_days."""

def check_wip_limits(issues: list[dict], limits: dict[str, int]) -> list[dict]:
    """Return label types that exceed their WIP limit, with counts."""
```

**New file `src/agents/maintenance.py`:**

```python
def build_maintenance_agent(llm, tools) -> Agent:
    """Agent that writes nudge comments and close messages."""

def build_maintenance_task(agent, stale_issues, wip_violations, repo, policy) -> Task:
    """Task: for each stale issue, post a nudge or close with explanation."""
```

**New functions in `src/tools/github_api.py`:**

```python
async def fetch_open_issues_with_dates(token: str, repo: str) -> list[dict]:
    """Fetch open issues with updated_at, labels, and assignee."""
```

**New endpoint in `src/webhook_router.py`:**

```
POST /maintenance
Header: X-Api-Key (required)
Body: {"repo": "owner/repo"}
Response: 202 Accepted
```

**Policy config additions (`policies/rules.yaml`):**

```yaml
stale_days: 7              # existing
auto_close_days: 30        # new: close after this many days of inactivity
stale_nudge_message: ""    # new: optional custom message, LLM generates if empty
```

### Behavior

1. Fetch all open issues for the repo
2. Identify stale issues (updated_at > stale_days ago)
3. For issues stale but under auto_close_days: apply `stale` label, post nudge comment
4. For issues stale beyond auto_close_days: close with explanation comment
5. Check WIP limits per label type, post a summary comment on any violations
6. Return summary: `{stale_nudged: N, stale_closed: N, wip_violations: [...]}`

### Testing

- Unit tests for `find_stale_issues` and `check_wip_limits` with various date scenarios
- Integration test: mock GitHub API, verify correct issues get nudged vs closed
- Edge cases: no stale issues, all issues stale, WIP limit of 0

---

## Feature 3: Standup Summaries

### Problem

There's no way to get a quick overview of what happened in the last day. Team members have to manually check GitHub activity.

### Solution

An endpoint that gathers recent activity, has an LLM summarize it into a standup format, and posts it as a GitHub issue with a `standup` label.

### Implementation

**New functions in `src/tools/github_api.py`:**

```python
async def fetch_recent_activity(token: str, repo: str, since_hours: int = 24) -> dict:
    """Fetch recent PRs, issues, and comments. Returns grouped activity."""
```

Returns:
```python
{
    "merged_prs": [{"number": N, "title": "...", "author": "..."}],
    "opened_issues": [...],
    "closed_issues": [...],
    "active_prs": [{"number": N, "title": "...", "reviewers": [...]}],
}
```

**New file `src/agents/standup.py`:**

```python
def build_standup_agent(llm) -> Agent:
    """Agent that writes concise standup summaries."""

def build_standup_task(agent, activity, repo) -> Task:
    """Summarize activity into Done / In Progress / Blocked format."""
```

The agent receives structured activity data (not raw API responses) and produces a markdown summary. No MCP tools needed - the action is just creating an issue.

**New endpoint in `src/webhook_router.py`:**

```
POST /standup
Header: X-Api-Key (required)
Body: {"repo": "owner/repo", "since_hours": 24}
Response: 202 Accepted
```

**Output format (posted as GitHub issue):**

```markdown
## Daily Standup - 2026-04-05

### Done
- PR #45 merged: Add user authentication (by @dev1)
- Issue #40 closed: Fix login button

### In Progress
- PR #47: Database migration (2 reviews pending)
- Issue #42: API rate limiting (assigned to @dev2)

### Blocked
- Issue #38: Waiting on design review (stale 5 days)

### Metrics
- 3 PRs merged, 2 issues closed, 1 blocked
```

### Testing

- Unit test: mock `fetch_recent_activity` with sample data, verify standup format
- Integration test: mock full pipeline, verify issue is created with `standup` label
- Edge case: no activity in the last 24 hours produces a "quiet day" summary

---

## Shared Infrastructure Changes

### Scheduler support

All three features benefit from scheduled execution. Add a `src/scheduler.py` with a lightweight approach:

- Use FastAPI's `on_event("startup")` to register background tasks
- Or document a GitHub Actions workflow that calls the endpoints on a cron schedule
- Recommendation: GitHub Actions cron is simpler and more reliable than in-process scheduling

**Example `.github/workflows/maintenance.yml`:**

```yaml
on:
  schedule:
    - cron: '0 9 * * 1-5'  # weekdays at 9am
jobs:
  standup:
    runs-on: ubuntu-latest
    steps:
      - run: |
          curl -X POST ${{ secrets.APP_URL }}/standup \
            -H "X-Api-Key: ${{ secrets.API_KEY }}" \
            -d '{"repo": "${{ github.repository }}"}'
  maintenance:
    runs-on: ubuntu-latest
    steps:
      - run: |
          curl -X POST ${{ secrets.APP_URL }}/maintenance \
            -H "X-Api-Key: ${{ secrets.API_KEY }}" \
            -d '{"repo": "${{ github.repository }}"}'
```

### `SanitizedPayload` as a dataclass

Currently `SanitizedPayload` is a frozen-ish dataclass. The PR diff feature needs to update `diff` after initial creation. Use `dataclasses.replace()` to create a modified copy rather than mutating.

### New dependencies

None. All features use existing dependencies (httpx, crewai, fastapi).

---

## Out of Scope

- Slack/Discord notifications (Milestone 2+)
- Sprint velocity tracking (Milestone 2)
- Code quality metrics (Milestone 3)
- Multi-repo support (future)
