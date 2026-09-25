"""Team objection frequencies. A superseded row is not a current objection."""

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


def objection_counts(
    rows: list[dict],
    *,
    start: datetime,
    end: datetime,
) -> list[dict]:
    """Count active objections by category in [start, end). Obstacles and superseded rows do not count."""
    if not rows:
        return []
    tallies: dict[str, dict[str, int]] = {}
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
    ordered = []
    for name, parts in tallies.items():
        count = parts["resolved"] + parts["open"] + parts["unknown"]
        ordered.append({"name": name, "count": count, **parts})
    ordered.sort(key=lambda item: (-item["count"], item["name"]))
    return ordered
