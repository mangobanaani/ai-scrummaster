from pydantic import BaseModel


class DedupResult(BaseModel):
    is_duplicate: bool
    matched_issue_url: str | None = None
    matched_issue_number: int | None = None
    confidence: float = 0.0  # 0.0-1.0
    reasoning: str = ""
