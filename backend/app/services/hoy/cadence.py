"""Lista 4 T2 (E8): when a hot contact comes back to Hoy. Pure: no I/O, no clock reads.

A contact that did not book a meeting comes back on one date, in this order: (1) the one the
rep picked after the call (memos.followup_at, written by T4); (2) a dated commitment, which
stays a task and is not this module's business; (3) the last conversation plus the wait of
the stopper that kept it from a meeting. Before that date it is in Próximos, not in Hoy.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

# E8's default waits, in days. The Head of Sales may override any of them per company
# (companies.followup_cadence, {stopper: days}); "interest_none" is never listed - a
# contact who showed no interest does not come back on its own.
DEFAULT_WAIT_DAYS: dict[str, int] = {
    "interest_high": 2,
    "interest_medium": 5,
    "interest_low": 30,
    "price": 7,
    "authority": 5,
    "trust": 7,
    "competitor": 14,
    "status_quo": 14,
    "timing": 21,
    "other": 7,
}
NEVER = "interest_none"
# playbooks/structured.OBJECTION_CATEGORIES; anything else is "other".
OBJECTION_STOPPERS: frozenset[str] = frozenset({"price", "timing", "authority", "competitor", "status_quo", "trust", "other"})
MIN_WAIT_DAYS = 1
MAX_WAIT_DAYS = 90
# memos.rep_outcome values (migration 062) after which a contact never comes back as a
# follow-up: the meeting is booked (the AE's now) or the rep closed it out.
CLOSED_OUTCOMES: frozenset[str] = frozenset({"meeting_booked", "not_interested", "disqualified"})


def stopper_for(touch) -> Optional[str]:
    """Why this contact did not move to a meeting. The latest open objection wins; without
    one, the interest level. Unknown interest stays unknown (None): no guessed follow-up."""
    interest = getattr(touch, "interest", None)
    if interest is None:
        return None
    if interest == "none":
        return NEVER
    objections = getattr(touch, "objections", ()) or ()
    if objections:
        category = objections[-1][0]
        return category if category in OBJECTION_STOPPERS else "other"
    return f"interest_{interest}" if f"interest_{interest}" in DEFAULT_WAIT_DAYS else None


def parse_overrides(raw) -> dict[str, int]:
    """companies.followup_cadence, keeping only known stoppers with whole days in 1..90.
    A malformed entry is dropped (its default applies), never an error on Hoy."""
    if not isinstance(raw, dict):
        return {}
    out: dict[str, int] = {}
    for key, value in raw.items():
        if key not in DEFAULT_WAIT_DAYS or isinstance(value, bool) or not isinstance(value, int):
            continue
        if MIN_WAIT_DAYS <= value <= MAX_WAIT_DAYS:
            out[key] = value
    return out


def wait_days(stopper: Optional[str], overrides: Optional[dict[str, int]] = None) -> Optional[int]:
    if stopper is None or stopper == NEVER:
        return None
    return (overrides or {}).get(stopper, DEFAULT_WAIT_DAYS.get(stopper))


def followup_due_at(
    touch,
    overrides: Optional[dict[str, int]] = None,
    rep_followup_at: Optional[datetime] = None,
) -> Optional[datetime]:
    """The date this touch's contact comes back, or None if it never does on its own.
    The rep's own date (argument, else the touch's followup_at) beats the table."""
    if getattr(touch, "rep_outcome", None) in CLOSED_OUTCOMES:
        return None
    chosen = rep_followup_at or getattr(touch, "followup_at", None)
    if chosen is not None:
        return chosen
    days = wait_days(stopper_for(touch), overrides)
    return touch.at + timedelta(days=days) if days else None
