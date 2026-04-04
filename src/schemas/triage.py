from enum import Enum

from pydantic import BaseModel


class RouteType(str, Enum):
    story = "story"
    issue = "issue"
    pr = "pr"
    push = "push"
    scan = "scan"


class TriageResult(BaseModel):
    route: RouteType
    repo: str  # "owner/repo"
    entity_id: int | None = None  # issue number, PR number, or None for push/scan
    ref: str | None = None  # git ref for push events
    pr_author: str | None = None
    event_action: str | None = None  # "opened", "edited", "synchronize", etc.
