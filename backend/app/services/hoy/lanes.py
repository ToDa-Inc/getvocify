"""Hoy lanes for SDR, AE, and general. Flag gating stays at the call site."""

from __future__ import annotations

from typing import Optional

CALLS = "calls"
MEETINGS = "meetings"
BOTH = (CALLS, MEETINGS)
ALL_MOTIONS = ("discovery", "qualification", "closing")


def lane_for_exit(reason: Optional[str]) -> Optional[str]:
    """ended is hidden. booked is a meeting. anything else is a call."""
    if reason == "ended":
        return None
    if reason == "booked":
        return MEETINGS
    return CALLS


def visible_lanes(sales_role: Optional[str], permission: str) -> tuple[str, ...]:
    """Owner and admin always see both lanes. Members follow their sales role."""
    if permission in ("owner", "admin"):
        return BOTH
    if sales_role == "sdr":
        return (CALLS,)
    if sales_role == "ae":
        return (MEETINGS,)
    return BOTH


def keep_lane(lane: Optional[str], lanes: tuple[str, ...]) -> bool:
    return lane is not None and lane in lanes


def motions_for(sales_role: Optional[str], permission: str) -> tuple[str, ...]:
    if permission in ("owner", "admin") or sales_role not in ("sdr", "ae"):
        return ALL_MOTIONS
    if sales_role == "sdr":
        return ("discovery", "qualification")
    return ("closing",)


def partition_by_lane(
    rows: list[dict],
    reason_by_contact: dict[str, Optional[str]],
    sales_role: Optional[str],
    permission: str,
    limit: int = 7,
) -> tuple[list[dict], list[dict]]:
    """Split rows the viewer may see. Missing reason means a call. Each row gains `lane`."""
    lanes = visible_lanes(sales_role, permission)
    calls: list[dict] = []
    meetings: list[dict] = []
    for row in rows:
        contact_id = str(row.get("contact_id") or "")
        lane = lane_for_exit(reason_by_contact.get(contact_id))
        if not keep_lane(lane, lanes):
            continue
        stamped = {**row, "lane": lane}
        if lane == MEETINGS:
            meetings.append(stamped)
        else:
            calls.append(stamped)
    return calls[:limit], meetings[:limit]


def default_motion(sales_role: Optional[str], permission: str) -> Optional[str]:
    """Filled only when a member SDR or AE captures without choosing a motion."""
    if permission in ("owner", "admin"):
        return None
    if sales_role == "sdr":
        return "discovery"
    if sales_role == "ae":
        return "closing"
    return None
