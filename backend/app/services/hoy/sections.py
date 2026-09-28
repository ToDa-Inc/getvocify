"""T6: GET /today's `sections` - the same items, split by role instead of one flat list.
`items` keeps working for compatibility; `sections` is additive and only appears with
HOY_AE_DEALS_ENABLED."""

from __future__ import annotations

from app.services.hoy.materialize import as_dt
from app.services.meetings.today import MEETING_TYPE


def split_items_by_type(items: list[dict]) -> tuple[list[dict], list[dict]]:
    """(calls, meetings) - everything that is not a meeting_today card is a call."""
    calls, meetings = [], []
    for item in items:
        (meetings if item.get("type") == MEETING_TYPE else calls).append(item)
    return calls, meetings


def sections_for_role(sales_role: str | None, *, calls: list[dict], meetings: list[dict], deals: list[dict]) -> dict:
    """D1: null behaves as general. SDR's Hoy is calls-focused (no deals, no separate
    meetings bucket - a booked meeting already left its Hoy via the handoff); AE and
    General get every bucket.

    The AE keeps `calls`: those are the AE's own follow-ups ("te llamo el jueves", an
    open objection, a confirmation) - dropping them would lose promises the AE made.
    Prospecting cards (never_contacted, callback_no_answer) never reach an AE anyway:
    lead tiers are only computed for SDR/General."""
    role = sales_role or "general"
    if role == "sdr":
        return {"calls": calls}
    return {"calls": calls, "meetings": meetings, "deals": deals}


# Lista 4 T2 (E7, HOY_SDR_SECTIONS_ENABLED): the SDR's/General's Hoy in three blocks, each
# with its own cap so the new leads never vanish behind the hot ones.
SDR_TASKS_CAP = 20
SDR_FOLLOWUPS_CAP = 7
SDR_NEW_CAP = 10
FOLLOWUP_TYPE = "followup_due"
NEW_TYPE = "never_contacted"
# build_today_view's cap while the sections are built from its items: high enough that no
# card is dropped before the per-section caps apply.
SDR_SOURCE_LIMIT = 1000


# Lista 4 T8 (E13, E16): the AE's and the General's Hoy add «Demos de hoy» - today's
# meetings, their own and the ones an SDR booked for them - in start order.
DEMOS_CAP = 20
SECTION_KEYS: dict[str, tuple[str, ...]] = {
    "sdr": ("tasks", "followups", "new"),
    "ae": ("tasks", "followups", "demos"),
    "general": ("tasks", "followups", "demos", "new"),
}
SECTION_CAPS: dict[str, int] = {
    "tasks": SDR_TASKS_CAP, "followups": SDR_FOLLOWUPS_CAP, "demos": DEMOS_CAP, "new": SDR_NEW_CAP,
}


def _section_for(kind: str | None, keys: tuple[str, ...]) -> str | None:
    if kind == FOLLOWUP_TYPE:
        return "followups"
    if kind == NEW_TYPE:
        # An AE never prospects (lead tiers are SDR/General only): such a card has no block.
        return "new" if "new" in keys else None
    if kind == MEETING_TYPE and "demos" in keys:
        return "demos"
    return "tasks"


def _starts_at(item: dict) -> tuple[int, float]:
    """meeting_today items carry the meeting's start as due_at (ISO, any offset); an
    unknown or unreadable start sorts last."""
    try:
        start = as_dt(item.get("due_at"))
    except (TypeError, ValueError):
        start = None
    return (0, start.timestamp()) if start else (1, 0.0)


def hoy_sections(items: list[dict], sales_role: str | None) -> tuple[dict, dict]:
    """(sections, folded per section) from the ranked items, order kept (demos by start
    time). Tasks are everything else: commitments due, callbacks, no-reply emails,
    confirmations, the rep's manual CRM tasks - and, for an SDR, a meeting today.
    D1: null behaves as general; an unknown role too."""
    keys = SECTION_KEYS.get(sales_role or "general", SECTION_KEYS["general"])
    buckets: dict[str, list[dict]] = {key: [] for key in keys}
    for item in items:
        key = _section_for(item.get("type"), keys)
        if key is not None:
            buckets[key].append(item)
    if "demos" in buckets:
        buckets["demos"].sort(key=_starts_at)
    sections = {key: rows[:SECTION_CAPS[key]] for key, rows in buckets.items()}
    folded = {key: max(0, len(rows) - SECTION_CAPS[key]) for key, rows in buckets.items()}
    return sections, folded
