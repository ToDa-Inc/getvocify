"""D4/D5: which playbook flow a rep's role and interaction land in, pure and DB-free."""

from __future__ import annotations

from typing import Optional

# D5: SDR always prospects, AE always closes. General (or no sales_role) follows the
# channel: a call is prospecting, a meeting or visit is demo/close.
_ROLE_MOTION = {"sdr": "discovery", "ae": "closing"}

# D4: each flow's business objective. Motions outside this map (custom types, qualification)
# have no default goal.
GOAL_FOR_MOTION = {
    "discovery": "meeting_booked",
    "closing": "proposal_and_close",
}


def motion_for(sales_role: Optional[str], interaction_kind: str) -> Optional[str]:
    """The sales motion a capture should pin to, from the rep's sales_role and the channel.
    A SDR/AE always gets their flow, whatever the channel. General (or no role) follows the
    channel only for call/meeting/visit; anything else (e.g. voice_note) has no fixed flow,
    so the caller falls back to its existing rule (single published playbook)."""
    role = (sales_role or "").strip().lower()
    if role in _ROLE_MOTION:
        return _ROLE_MOTION[role]
    if interaction_kind == "call":
        return "discovery"
    if interaction_kind in ("meeting", "visit"):
        return "closing"
    return None


def goal_for(sales_motion_key: str) -> Optional[str]:
    """The flow's objective, or None when the motion has no fixed goal (D4)."""
    return GOAL_FOR_MOTION.get(sales_motion_key)


def visible_to_role(sales_motion_key: str, sales_role: Optional[str]) -> bool:
    """Whether a member with this sales_role should see this motion (D5). A SDR does not
    need the closing flow and an AE does not need discovery; everything else (general,
    no role, custom motions, qualification) stays visible."""
    role = (sales_role or "").strip().lower()
    if role == "sdr":
        return sales_motion_key != "closing"
    if role == "ae":
        return sales_motion_key != "discovery"
    return True
