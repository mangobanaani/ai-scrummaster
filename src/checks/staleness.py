from datetime import datetime, timezone, timedelta


def find_stale_issues(issues: list[dict], stale_days: int) -> list[dict]:
    """Return issues where updated_at is older than stale_days ago."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=stale_days)
    stale = []
    for issue in issues:
        updated = datetime.fromisoformat(issue["updated_at"])
        if updated < cutoff:
            stale.append(issue)
    return stale


def check_wip_limits(issues: list[dict], limits: dict[str, int]) -> list[dict]:
    """Return label types that exceed their WIP limit."""
    label_counts: dict[str, int] = {}
    for issue in issues:
        for label in issue.get("labels", []):
            name = label["name"] if isinstance(label, dict) else label
            # Match both exact labels ("feature") and prefixed labels ("type:feature")
            matched_key = None
            if name in limits:
                matched_key = name
            elif ":" in name:
                suffix = name.split(":", 1)[1]
                if suffix in limits:
                    matched_key = suffix
            if matched_key:
                label_counts[matched_key] = label_counts.get(matched_key, 0) + 1

    violations = []
    for label, limit in limits.items():
        count = label_counts.get(label, 0)
        if count > limit:
            violations.append({"label": label, "count": count, "limit": limit})
    return violations
