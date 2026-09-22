"""Scope a priority snapshot to one person. Another owner's row never becomes an empty list."""

from __future__ import annotations

from datetime import datetime

from app.services.hoy.priority import empty_priority_copy, rank_candidates


def build_priority_page(
    *,
    snapshot: dict,
    user_id: str,
    role: str,
    now: datetime,
    limit: int = 20,
    cursor: str | None = None,
) -> dict:
    connected = bool(snapshot.get("connected"))
    coverage = snapshot.get("coverage") or "unavailable"
    observed_at = snapshot.get("observed_at")
    if not connected:
        copy = empty_priority_copy(connected=False, coverage=coverage, role=role)
        return {
            "items": [],
            "coverage": "unavailable",
            "observed_at": None,
            "next_cursor": None,
            "stale": False,
            **copy,
        }

    visible = []
    for row in snapshot.get("candidates") or []:
        if row.get("owner_ambiguous"):
            continue
        owner = row.get("owner_user_id")
        if owner and owner != user_id:
            continue
        visible.append(row)

    ranked = rank_candidates(visible, now)
    if cursor:
        ranked = [row for row in ranked if row["id"] > cursor]
    page = ranked[:limit]
    next_cursor = page[-1]["id"] if len(ranked) > limit else None
    if page and coverage != "complete":
        copy = {"title": "Falta parte del historial", "action": "Reintentar"}
    elif page:
        copy = {"title": None, "action": None}
    else:
        copy = empty_priority_copy(
            connected=True,
            coverage=coverage,
            role=role,
            assigned=snapshot.get("assigned", True),
        )
    return {
        "items": page,
        "coverage": coverage,
        "observed_at": observed_at,
        "next_cursor": next_cursor,
        "stale": False,
        **copy,
    }
