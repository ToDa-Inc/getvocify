"""Team objection frequencies. A superseded row is not a current objection."""

from __future__ import annotations


def objection_counts(rows: list[dict]) -> list[dict]:
    """Count active objections by category. Obstacles and superseded rows do not count."""
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
        name = str(category)
        tallies[name] = tallies.get(name, 0) + 1
    ordered = [{"name": name, "count": count} for name, count in tallies.items()]
    ordered.sort(key=lambda item: (-item["count"], item["name"]))
    return ordered
