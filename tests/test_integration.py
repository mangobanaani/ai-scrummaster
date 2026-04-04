import hashlib
import hmac
import json
import pytest
import respx
import httpx
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient, ASGITransport
from src.main import app
from src.config import settings


def _sign(body: bytes, secret: str) -> str:
    sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={sig}"


@pytest.fixture
def issue_payload():
    return {
        "action": "opened",
        "issue": {
            "number": 42,
            "title": "Fix login button",
            "body": "The login button does not work.\n\n## Acceptance Criteria\n- [ ] Works on iOS\n",
            "user": {"login": "dev1"},
        },
        "repository": {"full_name": "owner/repo"},
    }


@pytest.mark.asyncio
async def test_webhook_invalid_signature(issue_payload):
    body = json.dumps(issue_payload).encode()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/webhook",
            content=body,
            headers={
                "X-GitHub-Event": "issues",
                "X-Hub-Signature-256": "sha256=invalidsignature",
                "Content-Type": "application/json",
            },
        )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_webhook_valid_signature_accepted(issue_payload):
    body = json.dumps(issue_payload).encode()
    sig = _sign(body, settings.github_webhook_secret)

    with patch("src.webhook_router.run_crew_for_event", new_callable=AsyncMock) as mock_crew:
        mock_crew.return_value = {"status": "processed", "findings": 0}
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/webhook",
                content=body,
                headers={
                    "X-GitHub-Event": "issues",
                    "X-Hub-Signature-256": sig,
                    "Content-Type": "application/json",
                },
            )
    assert resp.status_code == 202
    mock_crew.assert_called_once()


@pytest.mark.asyncio
async def test_stories_endpoint():
    payload = {"repo": "owner/repo", "story": "As a user I want to log in"}

    with patch("src.webhook_router.run_crew_for_event", new_callable=AsyncMock) as mock_crew:
        mock_crew.return_value = {"status": "story_created"}
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/stories", json=payload, headers={"X-Api-Key": settings.api_key}
            )
    assert resp.status_code == 202
    mock_crew.assert_called_once()


@pytest.mark.asyncio
async def test_webhook_invalid_repo_rejected():
    """Webhook with a malformed repository.full_name is rejected with 400."""
    payload = {
        "action": "opened",
        "issue": {"number": 1, "title": "x", "body": "y"},
        "repository": {"full_name": "not-a-valid-repo"},
    }
    body = json.dumps(payload).encode()
    sig = _sign(body, settings.github_webhook_secret)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/webhook",
            content=body,
            headers={
                "X-GitHub-Event": "issues",
                "X-Hub-Signature-256": sig,
                "Content-Type": "application/json",
            },
        )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_stories_missing_api_key():
    payload = {"repo": "owner/repo", "story": "As a user I want to log in"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/stories", json=payload)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_stories_invalid_repo():
    payload = {"repo": "not-a-valid-repo", "story": "As a user I want to log in"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/stories", json=payload, headers={"X-Api-Key": settings.api_key}
        )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_scan_endpoint():
    with patch("src.webhook_router.run_crew_for_event", new_callable=AsyncMock) as mock_crew:
        mock_crew.return_value = {"status": "processed"}
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/scan",
                json={"repo": "owner/repo"},
                headers={"X-Api-Key": settings.api_key},
            )
    assert resp.status_code == 202
    mock_crew.assert_called_once()


@pytest.mark.asyncio
async def test_scan_missing_api_key():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/scan", json={"repo": "owner/repo"})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_health_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_story_decomposition_creates_issues():
    """Story route: decomposer LLM -> parse -> topo sort -> create issues -> link sub-issues."""
    decomposer_json = """[
        {"title": "App Epic", "type": "epic", "category": "infra",
         "size": "L", "priority": "high", "body": "epic body", "depends_on": []},
        {"title": "Core Story", "type": "story", "category": "backend",
         "size": "S", "priority": "medium", "body": "story body", "depends_on": [0]}
    ]"""

    mock_decomposer_output = MagicMock()
    mock_decomposer_output.__str__ = lambda self: decomposer_json

    with (
        respx.mock,
        patch("src.crew.Crew") as mock_crew_cls,
        patch("src.crew._make_llm"),
        patch("src.crew.build_triage_agent"),
        patch("src.crew.build_triage_task"),
        patch("src.crew.build_story_decomposer_agent"),
        patch("src.crew.build_story_decomposer_task"),
        patch("src.crew.mcp_tools_for"),
        patch("src.crew.PolicyEngine"),
        patch("src.crew.scan_for_secrets", return_value=[]),
        patch("src.crew.classify_owasp", return_value=[]),
    ):
        mock_crew_instance = AsyncMock()
        mock_crew_instance.kickoff_async = AsyncMock(side_effect=[mock_decomposer_output])
        mock_crew_cls.return_value = mock_crew_instance

        existing_issues_route = respx.get("https://api.github.com/repos/owner/repo/issues").mock(
            return_value=httpx.Response(200, json=[])
        )
        issues_route = respx.post("https://api.github.com/repos/owner/repo/issues").mock(
            side_effect=[
                httpx.Response(201, json={"number": 10, "id": 1001}),  # epic
                httpx.Response(201, json={"number": 11, "id": 1002}),  # story
            ]
        )
        sub_issues_route = respx.post(
            "https://api.github.com/repos/owner/repo/issues/10/sub_issues"
        ).mock(return_value=httpx.Response(200, json={}))

        from src.crew import run_crew_for_event
        from src.sanitizer import SanitizedPayload

        payload = SanitizedPayload(
            repo="owner/repo", title="", body="", action="opened",
            entity_id=None, diff=None, pr_author=None,
        )
        result = await run_crew_for_event(payload, {"event_type": "story", "story": "Build an app"})

    assert result["status"] == "story_created"
    assert result["tickets_created"] == 2
    assert result["tickets_skipped"] == 0
    assert existing_issues_route.call_count == 1
    assert issues_route.call_count == 2
    assert sub_issues_route.call_count == 1


@pytest.mark.asyncio
async def test_story_decomposition_skips_duplicates():
    """When existing issues match generated tickets, they are skipped."""
    decomposer_json = """[
        {"title": "App Epic", "type": "epic", "category": "infra",
         "size": "L", "priority": "high", "body": "epic body", "depends_on": []},
        {"title": "Core Story", "type": "story", "category": "backend",
         "size": "S", "priority": "medium", "body": "story body", "depends_on": [0]}
    ]"""
    mock_decomposer_output = MagicMock()
    mock_decomposer_output.__str__ = lambda self: decomposer_json

    with (
        respx.mock,
        patch("src.crew.Crew") as mock_crew_cls,
        patch("src.crew._make_llm"),
        patch("src.crew.build_triage_agent"),
        patch("src.crew.build_triage_task"),
        patch("src.crew.build_story_decomposer_agent"),
        patch("src.crew.build_story_decomposer_task"),
        patch("src.crew.mcp_tools_for"),
        patch("src.crew.PolicyEngine"),
        patch("src.crew.scan_for_secrets", return_value=[]),
        patch("src.crew.classify_owasp", return_value=[]),
    ):
        mock_crew_instance = AsyncMock()
        mock_crew_instance.kickoff_async = AsyncMock(side_effect=[mock_decomposer_output])
        mock_crew_cls.return_value = mock_crew_instance

        # Both tickets already exist (exact title matches)
        respx.get("https://api.github.com/repos/owner/repo/issues").mock(
            return_value=httpx.Response(200, json=[
                {"title": "App Epic"},
                {"title": "Core Story"},
            ])
        )
        issues_route = respx.post("https://api.github.com/repos/owner/repo/issues").mock(
            return_value=httpx.Response(201, json={"number": 10, "id": 1001})
        )

        from src.crew import run_crew_for_event
        from src.sanitizer import SanitizedPayload

        payload = SanitizedPayload(
            repo="owner/repo", title="", body="", action="opened",
            entity_id=None, diff=None, pr_author=None,
        )
        result = await run_crew_for_event(payload, {"event_type": "story", "story": "Build an app"})

    assert result["status"] == "story_created"
    assert result["tickets_created"] == 0
    assert result["tickets_skipped"] == 2
    assert issues_route.call_count == 0


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


@pytest.mark.asyncio
async def test_standup_rejects_negative_since_hours():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/standup",
            json={"repo": "owner/repo", "since_hours": -5},
            headers={"X-Api-Key": settings.api_key},
        )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_standup_rejects_excessive_since_hours():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/standup",
            json={"repo": "owner/repo", "since_hours": 9999},
            headers={"X-Api-Key": settings.api_key},
        )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_standup_rejects_non_integer_since_hours():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/standup",
            json={"repo": "owner/repo", "since_hours": "abc"},
            headers={"X-Api-Key": settings.api_key},
        )
    assert resp.status_code == 422
