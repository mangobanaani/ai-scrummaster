import httpx

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
            titles.extend(issue["title"] for issue in batch)
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
