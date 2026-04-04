import hashlib
import hmac
import json
import logging
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response, Security
from fastapi.security import APIKeyHeader
from src.config import settings
from src.sanitizer import sanitize_payload, sanitize_field, validate_repo, SanitizedPayload
from src.crew import run_crew_for_event
from src.schemas.story import StoryInput

logger = logging.getLogger(__name__)
router = APIRouter()

_api_key_header = APIKeyHeader(name="X-Api-Key", auto_error=False)


def _require_api_key(key: str | None = Security(_api_key_header)) -> None:
    if not key or not hmac.compare_digest(key, settings.api_key):
        raise HTTPException(status_code=403, detail="Invalid or missing API key")


def _verify_signature(body: bytes, signature: str) -> bool:
    expected = "sha256=" + hmac.new(
        settings.github_webhook_secret.encode(), body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


async def _dispatch(payload: SanitizedPayload, raw_event: dict) -> None:
    try:
        result = await run_crew_for_event(payload, raw_event)
        logger.info("Crew completed: %s", result)
    except Exception:
        logger.exception("Crew failed for repo %s", payload.repo)


@router.post("/webhook")
async def webhook(request: Request, background_tasks: BackgroundTasks):
    body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256", "")

    if not signature:
        raise HTTPException(status_code=403, detail="Missing signature header")
    if not _verify_signature(body, signature):
        raise HTTPException(status_code=403, detail="Invalid signature")

    event_type = request.headers.get("X-GitHub-Event", "")
    try:
        raw = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON body")
    raw["event_type"] = event_type

    _PR_ACTIONS = {"opened", "synchronize", "reopened"}
    if event_type == "pull_request" and raw.get("action") not in _PR_ACTIONS:
        return Response(status_code=200)

    try:
        payload = sanitize_payload(raw)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    background_tasks.add_task(_dispatch, payload, raw)
    return Response(status_code=202)


@router.post("/stories")
async def create_story(
    story_input: StoryInput,
    background_tasks: BackgroundTasks,
    _: None = Depends(_require_api_key),
):
    try:
        repo = validate_repo(story_input.repo)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    sanitized_story = sanitize_field(story_input.story, "body")
    payload = SanitizedPayload(repo=repo, title="", body=sanitized_story, event_type="story")
    raw_event = {"event_type": "story", "repo": repo, "story": sanitized_story}
    background_tasks.add_task(_dispatch, payload, raw_event)
    return Response(status_code=202)


@router.post("/scan")
async def scan_repo(
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
    payload = SanitizedPayload(repo=repo, title="", body="", event_type="scan")
    raw_event = {"event_type": "scan", "repo": repo}
    background_tasks.add_task(_dispatch, payload, raw_event)
    return Response(status_code=202)
