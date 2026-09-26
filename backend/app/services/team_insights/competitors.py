"""Named competitor mentions from current C04 intelligence. Stale revisions do not count."""

from __future__ import annotations

from datetime import datetime, timezone

from app.services.intelligence.extract import is_current

COMPETITORS_FLAG = "TEAM_COMPETITORS_ENABLED"


def _parse_instant(value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        dt = datetime.fromisoformat(text)
    else:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def normalize_competitor_name(name: str) -> str:
    return " ".join(str(name).upper().split())


def _memo_instant(memo: dict) -> datetime | None:
    observed = _parse_instant(memo.get("capture_started_at"))
    if observed is not None:
        return observed
    return _parse_instant(memo.get("created_at"))


def competitor_counts(
    memos: list[dict],
    *,
    start: datetime,
    end: datetime,
) -> list[dict]:
    """Count memos with current intelligence in [start, end), grouped by normalized name."""
    if not memos:
        return []
    tallies: dict[str, int] = {}
    for memo in memos:
        if not is_current(memo):
            continue
        instant = _memo_instant(memo)
        if instant is None or instant < start or instant >= end:
            continue
        extraction = memo.get("extraction") if isinstance(memo.get("extraction"), dict) else {}
        intelligence = extraction.get("intelligence") if isinstance(extraction.get("intelligence"), dict) else {}
        mentions = intelligence.get("competitor_mentions")
        if not isinstance(mentions, list):
            continue
        seen_in_memo: set[str] = set()
        for mention in mentions:
            if isinstance(mention, str):
                raw_name = mention
            elif isinstance(mention, dict):
                raw_name = mention.get("name")
            else:
                continue
            if raw_name is None or not str(raw_name).strip():
                continue
            name = normalize_competitor_name(str(raw_name))
            if name in seen_in_memo:
                continue
            seen_in_memo.add(name)
            tallies[name] = tallies.get(name, 0) + 1
    ordered = [{"name": name, "count": count} for name, count in tallies.items()]
    ordered.sort(key=lambda item: (-item["count"], item["name"]))
    return ordered
