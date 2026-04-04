import json
import pytest
import respx
import httpx
from src.tools.github_api import create_issue, link_sub_issue

REPO = "owner/repo"
TOKEN = "ghp_test"


@pytest.mark.asyncio
async def test_create_issue_returns_number_and_id():
    with respx.mock:
        respx.post("https://api.github.com/repos/owner/repo/issues").mock(
            return_value=httpx.Response(201, json={"number": 42, "id": 9001})
        )
        number, db_id = await create_issue(TOKEN, REPO, "My issue", "body text", ["type:story"])
    assert number == 42
    assert db_id == 9001


@pytest.mark.asyncio
async def test_create_issue_sends_correct_payload():
    with respx.mock:
        route = respx.post("https://api.github.com/repos/owner/repo/issues").mock(
            return_value=httpx.Response(201, json={"number": 7, "id": 700})
        )
        await create_issue(TOKEN, REPO, "Title", "Body", ["type:epic", "size:L"])

    body = json.loads(route.calls[0].request.content)
    assert body["title"] == "Title"
    assert body["body"] == "Body"
    assert body["labels"] == ["type:epic", "size:L"]


@pytest.mark.asyncio
async def test_create_issue_sets_auth_header():
    with respx.mock:
        route = respx.post("https://api.github.com/repos/owner/repo/issues").mock(
            return_value=httpx.Response(201, json={"number": 1, "id": 100})
        )
        await create_issue(TOKEN, REPO, "T", "B", [])

    assert route.calls[0].request.headers["authorization"] == f"Bearer {TOKEN}"


@pytest.mark.asyncio
async def test_create_issue_raises_on_http_error():
    with respx.mock:
        respx.post("https://api.github.com/repos/owner/repo/issues").mock(
            return_value=httpx.Response(422, json={"message": "Validation Failed"})
        )
        with pytest.raises(httpx.HTTPStatusError):
            await create_issue(TOKEN, REPO, "Title", "Body", [])


@pytest.mark.asyncio
async def test_link_sub_issue_posts_correct_endpoint():
    with respx.mock:
        route = respx.post(
            "https://api.github.com/repos/owner/repo/issues/1/sub_issues"
        ).mock(return_value=httpx.Response(200, json={}))
        await link_sub_issue(TOKEN, REPO, parent_number=1, child_id=9001)

    body = json.loads(route.calls[0].request.content)
    assert body["sub_issue_id"] == 9001


@pytest.mark.asyncio
async def test_link_sub_issue_raises_on_http_error():
    with respx.mock:
        respx.post(
            "https://api.github.com/repos/owner/repo/issues/1/sub_issues"
        ).mock(return_value=httpx.Response(404, json={"message": "Not Found"}))
        with pytest.raises(httpx.HTTPStatusError):
            await link_sub_issue(TOKEN, REPO, parent_number=1, child_id=9001)
