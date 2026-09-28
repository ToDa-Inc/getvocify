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


def sdr_sections(items: list[dict]) -> tuple[dict, dict]:
    """(sections, folded per section) from the ranked items, order kept. Tasks are everything
    that is neither a follow-up nor a new lead: commitments due, callbacks, no-reply emails,
    today's meetings, confirmations and the rep's manual CRM tasks."""
    buckets: dict[str, list[dict]] = {"tasks": [], "followups": [], "new": []}
    for item in items:
        kind = item.get("type")
        key = "followups" if kind == FOLLOWUP_TYPE else "new" if kind == NEW_TYPE else "tasks"
        buckets[key].append(item)
    caps = {"tasks": SDR_TASKS_CAP, "followups": SDR_FOLLOWUPS_CAP, "new": SDR_NEW_CAP}
    sections = {key: rows[:caps[key]] for key, rows in buckets.items()}
    folded = {key: max(0, len(rows) - caps[key]) for key, rows in buckets.items()}
    return sections, folded
