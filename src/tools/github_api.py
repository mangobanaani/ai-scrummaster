import httpx
import logging

logger = logging.getLogger(__name__)

_GITHUB_API = "https://api.github.com"
_HEADERS = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
    "User-Agent": "github-crew/1.0",
}


async def create_issue(
    token: str, repo: str, title: str, body: str, labels: list[str]
) -> tuple[int, int]:
    """Creates a GitHub issue and returns (number, id)."""
    url = f"{_GITHUB_API}/repos/{repo}/issues"
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            url,
            headers={**_HEADERS, "Authorization": f"Bearer {token}"},
            json={"title": title, "body": body, "labels": labels},
        )
        resp.raise_for_status()
        data = resp.json()
        return data["number"], data["id"]


async def fetch_open_issue_titles(token: str, repo: str) -> list[str]:
    """Returns titles of all open issues in the repo (up to 500)."""
    url = f"{_GITHUB_API}/repos/{repo}/issues"
    titles: list[str] = []
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
            titles.extend(
                issue["title"] for issue in batch if not issue.get("pull_request")
            )
    return titles


async def link_sub_issue(
    token: str, repo: str, parent_number: int, child_id: int
) -> None:
    """Links child_id (database id) as a sub-issue of parent_number."""
    url = f"{_GITHUB_API}/repos/{repo}/issues/{parent_number}/sub_issues"
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            url,
            headers={**_HEADERS, "Authorization": f"Bearer {token}"},
            json={"sub_issue_id": child_id},
        )
        resp.raise_for_status()


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
                if issue.get("pull_request"):
                    continue  # GitHub issues API includes PRs; skip them
                all_issues.append(
                    {
                        "number": issue["number"],
                        "title": issue["title"],
                        "updated_at": issue["updated_at"],
                        "labels": issue.get("labels", []),
                        "assignee": issue.get("assignee"),
                        "html_url": issue["html_url"],
                    }
                )
    return all_issues


_DEP_FILE_PATTERNS = {"requirements.txt", "package.json", "go.mod"}


def _is_dependency_file(filename: str) -> bool:
    """Check if a filename is a dependency manifest."""
    basename = filename.rsplit("/", 1)[-1].lower()
    if basename in _DEP_FILE_PATTERNS:
        return True
    if "requirements" in basename and basename.endswith(".txt"):
        return True
    return False


async def fetch_changed_dep_files(
    token: str, repo: str, ref: str, commits: list[dict]
) -> dict[str, str]:
    """Extract dependency filenames from push event commits, fetch their contents."""
    dep_files: set[str] = set()
    for commit in commits:
        for key in ("added", "modified"):
            for f in commit.get(key, []):
                if _is_dependency_file(f):
                    dep_files.add(f)

    if not dep_files:
        return {}

    result: dict[str, str] = {}
    async with httpx.AsyncClient(timeout=30.0) as client:
        for filepath in dep_files:
            url = f"{_GITHUB_API}/repos/{repo}/contents/{filepath}"
            try:
                resp = await client.get(
                    url,
                    headers={
                        **_HEADERS,
                        "Authorization": f"Bearer {token}",
                        "Accept": "application/vnd.github.raw+json",
                    },
                    params={"ref": ref},
                )
                resp.raise_for_status()
                result[filepath] = resp.text
            except httpx.HTTPError as exc:
                logger.warning("Failed to fetch %s from %s: %s", filepath, repo, exc)
    return result


async def fetch_repo_dep_files(token: str, repo: str) -> dict[str, str]:
    """Fetch known dependency manifests from the repo's default branch."""
    result: dict[str, str] = {}
    async with httpx.AsyncClient(timeout=30.0) as client:
        for filepath in sorted(_DEP_FILE_PATTERNS):
            url = f"{_GITHUB_API}/repos/{repo}/contents/{filepath}"
            try:
                resp = await client.get(
                    url,
                    headers={
                        **_HEADERS,
                        "Authorization": f"Bearer {token}",
                        "Accept": "application/vnd.github.raw+json",
                    },
                )
                if resp.status_code == 200:
                    result[filepath] = resp.text
            except httpx.HTTPError:
                pass
    return result


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
        since_dt_issues = datetime.fromisoformat(since.replace("Z", "+00:00"))
        for item in resp.json():
            if item.get("pull_request"):
                continue
            entry = {
                "number": item["number"],
                "title": item["title"],
                "author": item["user"]["login"],
            }
            if item["state"] == "closed":
                closed_at = item.get("closed_at")
                if closed_at:
                    closed_dt = datetime.fromisoformat(closed_at.replace("Z", "+00:00"))
                    if closed_dt >= since_dt_issues:
                        activity["closed_issues"].append(entry)
            else:
                created = datetime.fromisoformat(
                    item["created_at"].replace("Z", "+00:00")
                )
                if created >= since_dt_issues:
                    activity["opened_issues"].append(entry)

        # Fetch recently updated PRs
        resp = await client.get(
            f"{_GITHUB_API}/repos/{repo}/pulls",
            headers=headers,
            params={
                "state": "all",
                "sort": "updated",
                "direction": "desc",
                "per_page": 50,
            },
        )
        resp.raise_for_status()
        since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
        for pr in resp.json():
            updated = datetime.fromisoformat(pr["updated_at"].replace("Z", "+00:00"))
            if updated < since_dt:
                break  # sorted desc by updated, so all remaining are older
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
