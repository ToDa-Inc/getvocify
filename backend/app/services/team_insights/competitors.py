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


def _folded(name: str) -> str:
    import unicodedata

    plain = unicodedata.normalize("NFKD", name)
    return "".join(c for c in plain if c.isalnum()).upper()


def _merge_spellings(
    tallies: dict[str, int], quotes: dict[str, list[tuple[datetime, str]]]
) -> tuple[dict[str, int], dict[str, list[tuple[datetime, str]]]]:
    """The audio spells one product several ways ("Ringover", "Ring Over", "RingGover"): they are
    one competitor, named by its most frequent spelling."""
    from difflib import SequenceMatcher

    groups: list[list[str]] = []
    for name in sorted(tallies, key=lambda n: (-tallies[n], n)):
        key = _folded(name)
        for group in groups:
            head = _folded(group[0])
            if key == head or (min(len(key), len(head)) >= 5 and SequenceMatcher(None, key, head).ratio() >= 0.85):
                group.append(name)
                break
        else:
            groups.append([name])
    merged_tallies: dict[str, int] = {}
    merged_quotes: dict[str, list[tuple[datetime, str]]] = {}
    for group in groups:
        merged_tallies[group[0]] = sum(tallies[n] for n in group)
        merged_quotes[group[0]] = [q for n in group for q in quotes.get(n, [])]
    return merged_tallies, merged_quotes


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
    tallies, quotes = _merge_spellings(tallies, quotes)
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
