import hashlib
import logging
import re
from dataclasses import dataclass

_REPO_FORMAT = re.compile(r"^[\w][\w.-]{0,98}/[\w][\w.-]{0,98}$", re.ASCII)

logger = logging.getLogger(__name__)

_INJECTION_PATTERNS: list[re.Pattern] = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"<\|system\|>",
        r"<\|user\|>",
        r"<\|assistant\|>",
        r"\[INST\]",
        r"\[\/INST\]",
        r"<s>(?!\w)",
        r"<\/s>",
        r"IGNORE\s+PREVIOUS\s+INSTRUCTIONS?",
        r"FORGET\s+(ALL|EVERYTHING)\s+(PREVIOUS|PRIOR)",
        r"SYSTEM\s*:",
        r"###\s*(SYSTEM|INSTRUCTION|OVERRIDE|PROMPT)",
        r"You are now\b",
        r"Act as\s+(?:if\s+)?(?:you are\s+)?(?:an?\s+)?\w+\s+with no (?:limits|restrictions)",
        r"Disregard\s+(all\s+)?(?:previous|prior)\s+instructions?",
        r"New\s+instruction\s*:",
        r"Override\s*:",
    ]
]

_FIELD_LIMITS: dict[str, int] = {
    "title": 256,
    "body": 4000,
    "diff": 8000,
    "comment": 2000,
    "repo": 140,
}


def sanitize_field(content: str, field_name: str) -> str:
    """Strip injection patterns and enforce length limits on a single field."""
    if not content:
        return content

    original_hash = hashlib.sha256(content.encode()).hexdigest()[:12]
    cleaned = content
    was_modified = False

    for pattern in _INJECTION_PATTERNS:
        new = pattern.sub("[removed]", cleaned)
        if new != cleaned:
            was_modified = True
            cleaned = new

    limit = _FIELD_LIMITS.get(field_name)
    if limit and len(cleaned) > limit:
        cleaned = cleaned[:limit]
        was_modified = True

    if was_modified:
        logger.warning(
            "sanitized field '%s' (original hash: %s)",
            field_name,
            original_hash,
        )

    return cleaned


def validate_repo(repo: str) -> str:
    """Sanitize and validate a GitHub repository name (owner/name format).

    Raises ValueError if the format is invalid after sanitization.
    """
    cleaned = sanitize_field(repo, "repo")
    if not _REPO_FORMAT.match(cleaned):
        raise ValueError(f"Invalid repository format: {cleaned!r}")
    return cleaned


@dataclass
class SanitizedPayload:
    repo: str
    title: str
    body: str
    diff: str = ""
    event_type: str = ""
    action: str = ""
    entity_id: int | None = None
    ref: str | None = None
    pr_author: str | None = None


def sanitize_payload(raw: dict) -> SanitizedPayload:
    """Extract and sanitize all untrusted string fields from a GitHub webhook payload."""
    raw_repo = raw.get("repository", {}).get("full_name", "")
    repo = validate_repo(raw_repo)

    issue = raw.get("issue") or raw.get("pull_request") or {}
    title = sanitize_field(str(issue.get("title") or ""), "title")
    body = sanitize_field(str(issue.get("body") or ""), "body")
    entity_id = issue.get("number")
    pr_author = issue.get("user", {}).get("login") if raw.get("pull_request") else None

    action = sanitize_field(raw.get("action", ""), "title")
    if pr_author:
        pr_author = sanitize_field(pr_author, "title")

    diff = sanitize_field(raw.get("diff", ""), "diff") if raw.get("diff") else ""

    return SanitizedPayload(
        repo=repo,
        title=title,
        body=body,
        entity_id=entity_id,
        action=action,
        pr_author=pr_author,
        event_type=sanitize_field(raw.get("event_type", ""), "title"),
        diff=diff,
    )
