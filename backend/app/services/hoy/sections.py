"""T6: GET /today's `sections` - the same items, split by role instead of one flat list.
`items` keeps working for compatibility; `sections` is additive and only appears with
HOY_AE_DEALS_ENABLED."""

from __future__ import annotations

from app.services.meetings.today import MEETING_TYPE


def split_items_by_type(items: list[dict]) -> tuple[list[dict], list[dict]]:
    """(calls, meetings) - everything that is not a meeting_today card is a call."""
    calls, meetings = [], []
    for item in items:
        (meetings if item.get("type") == MEETING_TYPE else calls).append(item)
    return calls, meetings


def sections_for_role(sales_role: str | None, *, calls: list[dict], meetings: list[dict], deals: list[dict]) -> dict:
    """D1: null behaves as general. AE's Hoy is deals-focused (no calls bucket); SDR's is
    calls-focused (no deals, no separate meetings bucket - a booked meeting already left
    its Hoy via the handoff); General keeps every bucket, same as before this task."""
    role = sales_role or "general"
    if role == "ae":
        return {"meetings": meetings, "deals": deals}
    if role == "sdr":
        return {"calls": calls}
    return {"calls": calls, "meetings": meetings, "deals": deals}
