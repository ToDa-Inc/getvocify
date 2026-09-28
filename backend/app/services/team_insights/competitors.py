"""Named competitor mentions from current C04 intelligence. Stale revisions do not count.

T11: each competitor also carries `quotes`, its last 3 dated citas (a mention with a
`quote` field), most recent first."""

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
    quotes: dict[str, list[tuple[datetime, str]]] = {}
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
                quote_text = None
            elif isinstance(mention, dict):
                raw_name = mention.get("name")
                quote_text = mention.get("quote")
            else:
                continue
            if raw_name is None or not str(raw_name).strip():
                continue
            name = normalize_competitor_name(str(raw_name))
            if name in seen_in_memo:
                continue
            seen_in_memo.add(name)
            tallies[name] = tallies.get(name, 0) + 1
            if quote_text is not None:
                text = " ".join(str(quote_text).split())
                if text:
                    quotes.setdefault(name, []).append((instant, text))
    ordered = []
    for name, count in tallies.items():
        recent = sorted(quotes.get(name, []), key=lambda pair: pair[0], reverse=True)[:3]
        ordered.append({
            "name": name,
            "count": count,
            "quotes": [
                {"quote": text, "date": stamp.isoformat().replace("+00:00", "Z")}
                for stamp, text in recent
            ],
        })
    ordered.sort(key=lambda item: (-item["count"], item["name"]))
    return ordered
