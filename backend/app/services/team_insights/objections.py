"""Team objection frequencies. A superseded row is not a current objection.

T11/PLAYBOOK_TAB_ENABLED: with `include_guidance=True`, each category also carries
how_to (the published playbook's own guidance for that category) and best_example (the
most recent resolved objection's response, team-wide). Flag off (the default) returns
the exact pre-T11 shape, since reporting (weekly self/team reports) never asks for it."""

from __future__ import annotations

from datetime import datetime, timezone

_OBJECTION_KEYS = frozenset({
    "price",
    "timing",
    "authority",
    "competitor",
    "status_quo",
    "trust",
    "other",
})


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


def _objection_name(category: str) -> str:
    key = str(category).strip().lower()
    if key in _OBJECTION_KEYS:
        return key
    return key


def _row_instant(row: dict) -> datetime | None:
    observed = _parse_instant(row.get("observed_at"))
    if observed is not None:
        return observed
    return _parse_instant(row.get("created_at"))


def _resolution_bucket(row: dict) -> str:
    value = row.get("resolution")
    if value == "resolved":
        return "resolved"
    if value == "open":
        return "open"
    return "unknown"


def _guidance_by_category(playbook_entries: list[dict] | None) -> dict[str, str]:
    """The published playbook's own words for each objection category, first entry wins."""
    mapping: dict[str, str] = {}
    for entry in playbook_entries or []:
        if not isinstance(entry, dict):
            continue
        category = str(entry.get("category") or "").strip().lower()
        if not category or category in mapping:
            continue
        guidance = " ".join(str(entry.get("guidance") or "").split())
        if guidance:
            mapping[category] = guidance
    return mapping


EXAMPLE_MAX_CHARS = 240


def response_text(value) -> str:
    """The rep's answer as a reader sees it: the text of a stored {"text": ...} (dict or JSON string),
    in one line, cut at a sentence end when a monologue runs long."""
    import json

    if isinstance(value, str) and value.strip().startswith("{"):
        try:
            value = json.loads(value)
        except ValueError:
            pass
    if isinstance(value, dict):
        value = value.get("text") or ""
    text = " ".join(str(value or "").split())
    if len(text) <= EXAMPLE_MAX_CHARS:
        return text
    cut = text[:EXAMPLE_MAX_CHARS]
    end = max(cut.rfind(". "), cut.rfind("? "), cut.rfind("! "))
    return (cut[:end + 1] if end > EXAMPLE_MAX_CHARS // 3 else cut.rsplit(" ", 1)[0]) + " …"


def objection_counts(
    rows: list[dict],
    *,
    start: datetime,
    end: datetime,
    playbook_entries: list[dict] | None = None,
    include_guidance: bool = False,
) -> list[dict]:
    """Count active objections by category in [start, end). Obstacles and superseded rows do not count.

    With `include_guidance=True` (PLAYBOOK_TAB_ENABLED), each item also carries `how_to`
    (from `playbook_entries`, the published playbook's guidance for that category) and
    `best_example` (the response of the most recent resolved row in that category, from
    the same rows) — either can be None when there is nothing to show. Flag off is the
    default and keeps the exact pre-T11 shape: no `how_to`/`best_example` keys at all."""
    if not rows:
        return []
    guidance = _guidance_by_category(playbook_entries) if include_guidance else {}
    tallies: dict[str, dict[str, int]] = {}
    best_example: dict[str, tuple[datetime, str]] = {}
    for row in rows:
        if row.get("superseded"):
            continue
        if row.get("kind") != "objection":
            continue
        category = row.get("category")
        if not category:
            continue
        instant = _row_instant(row)
        if instant is None or instant < start or instant >= end:
            continue
        name = _objection_name(str(category))
        bucket = tallies.setdefault(name, {"resolved": 0, "open": 0, "unknown": 0})
        bucket[_resolution_bucket(row)] += 1
        if include_guidance and row.get("resolution") == "resolved":
            response = response_text(row.get("response"))
            if response:
                current = best_example.get(name)
                if current is None or instant > current[0]:
                    best_example[name] = (instant, response)
    ordered = []
    for name, parts in tallies.items():
        count = parts["resolved"] + parts["open"] + parts["unknown"]
        item = {"name": name, "count": count, **parts}
        if include_guidance:
            example = best_example.get(name)
            item["how_to"] = guidance.get(name)
            item["best_example"] = example[1] if example else None
        ordered.append(item)
    ordered.sort(key=lambda item: (-item["count"], item["name"]))
    return ordered
