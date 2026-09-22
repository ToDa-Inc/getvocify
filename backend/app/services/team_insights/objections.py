"""Team objection frequencies. A superseded row is not a current objection."""

from __future__ import annotations

from datetime import datetime, timezone

_OBJECTION_LABELS: dict[str, str] = {
    "price": "Precio",
    "timing": "Plazo",
    "authority": "Autoridad",
    "competitor": "Competidor",
    "status_quo": "Statu quo",
    "trust": "Confianza",
    "other": "Otra",
}


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


def _objection_label(category: str) -> str:
    key = str(category).strip().lower()
    return _OBJECTION_LABELS.get(key, "Otra")


def _row_instant(row: dict) -> datetime | None:
    observed = _parse_instant(row.get("observed_at"))
    if observed is not None:
        return observed
    return _parse_instant(row.get("created_at"))


def objection_counts(
    rows: list[dict],
    *,
    start: datetime,
    end: datetime,
) -> list[dict]:
    """Count active objections by category in [start, end). Obstacles and superseded rows do not count."""
    if not rows:
        return []
    tallies: dict[str, int] = {}
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
        name = _objection_label(str(category))
        tallies[name] = tallies.get(name, 0) + 1
    ordered = [{"name": name, "count": count} for name, count in tallies.items()]
    ordered.sort(key=lambda item: (-item["count"], item["name"]))
    return ordered
