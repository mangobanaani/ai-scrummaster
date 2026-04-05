from typing import Literal
from pydantic import BaseModel, Field


class StoryInput(BaseModel):
    repo: str  # "owner/repo"
    story: str  # free-text story description


class StructuredIssue(BaseModel):
    title: str
    body: str  # full markdown body with AC + DoD
    labels: list[str]  # e.g. ["type:feature", "size:M", "priority:medium"]
    assignees: list[str] = []


class TicketDraft(BaseModel):
    title: str
    type: Literal["epic", "story", "task"]
    category: str  # e.g. "data-model", "frontend", "backend", "infra"
    size: Literal["XS", "S", "M", "L", "XL"]
    priority: Literal["low", "medium", "high", "critical"]
    body: str  # markdown with user story, AC (Given/When/Then), and DoD checkboxes
    depends_on: list[int] = Field(
        default_factory=list
    )  # 0-based indices into DecomposedStories.tickets


class DecomposedStories(BaseModel):
    tickets: list[TicketDraft] = Field(default_factory=list)
