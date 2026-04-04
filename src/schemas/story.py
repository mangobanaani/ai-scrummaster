from typing import Literal
from pydantic import BaseModel, Field, field_validator


class StoryInput(BaseModel):
    repo: str  # "owner/repo"
    story: str  # free-text story description


class StructuredIssue(BaseModel):
    title: str
    body: str  # full markdown body with AC + DoD
    labels: list[str]  # e.g. ["type:feature", "size:M", "priority:medium"]
    assignees: list[str] = []


_VALID_SIZES = {"XS", "S", "M", "L", "XL"}
_VALID_PRIORITIES = {"low", "medium", "high", "critical"}


class TicketDraft(BaseModel):
    title: str
    type: Literal["epic", "story", "task"]
    category: str = "general"
    size: str = "M"
    priority: str = "medium"
    body: str = ""
    depends_on: list[int] = Field(default_factory=list)  # 0-based indices into DecomposedStories.tickets

    @field_validator("size", mode="before")
    @classmethod
    def coerce_size(cls, v: object) -> str:
        return v if v in _VALID_SIZES else "M"

    @field_validator("priority", mode="before")
    @classmethod
    def coerce_priority(cls, v: object) -> str:
        return v if v in _VALID_PRIORITIES else "medium"

    @field_validator("category", mode="before")
    @classmethod
    def coerce_category(cls, v: object) -> str:
        return v if isinstance(v, str) and v.strip() else "general"


class DecomposedStories(BaseModel):
    tickets: list[TicketDraft] = Field(default_factory=list)
