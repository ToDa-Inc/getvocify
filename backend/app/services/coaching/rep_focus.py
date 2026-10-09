"""One focus per rep from the previous full Madrid week: the Head of Sales table, the daily
and weekly coaching lines. Same flow / motion / published steps as /coaching/me/summary.
Reads are tolerant: any failure means no focus."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.services.coaching import rep_coaching as engine
from app.services.coaching import rep_coaching_reads as reads
from app.services.playbooks.motion import MOTION_FLOW, flow_for_motion

FLOW_MOTION = {"sdr": "discovery", "ae": "closing"}
# Every catalog call type of a flow, its default first (a tie goes to it).
FLOW_MOTIONS: dict[str, tuple[str, ...]] = {
    flow: (default, *sorted(m for m, f in MOTION_FLOW.items() if f == flow and m != default))
    for flow, default in FLOW_MOTION.items()
}
# Weeks of a rep's interactions that decide which flow a general/NULL rep is coached on.
FLOW_WEEKS = 8


def published_flows(playbook_for) -> list[str]:
    """The flows (sdr, ae order) with at least one call type that has a published playbook."""
    return [
        flow for flow, motions in FLOW_MOTIONS.items()
        if any(playbook_for(motion)["published"] for motion in motions)
    ]


def motion_for_flow(flow: str, rows: list[dict], playbook_for) -> str:
    """The call type a rep is coached on within their flow: of the flow's types with a
    published playbook, the one they ran most in `rows` (the default wins a tie). An AE whose
    meetings route to discovery or negotiation is coached on those, not on an empty demo."""
    motions = FLOW_MOTIONS[flow]
    published = [motion for motion in motions if playbook_for(motion)["published"]]
    if not published:
        return FLOW_MOTION[flow]
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["motion"]] = counts.get(row["motion"], 0) + 1
    return max(published, key=lambda motion: (counts.get(motion, 0), -motions.index(motion)))


def resolve_flow(
    sales_role: str | None,
    rows: list[dict],
    published: list[str] | None = None,
    requested: str | None = None,
) -> str:
    """sdr -> discovery, ae -> closing, always (a `requested` flow is ignored for them).
    A general/NULL rep gets `requested` when valid; else, among the flows with a published
    playbook (`published`, when known), the one with most of the rep's interactions - a single
    published flow wins outright, a tie goes to sdr."""
    if sales_role in FLOW_MOTION:
        return sales_role
    if requested in FLOW_MOTION:
        return requested
    candidates = [flow for flow in (published or []) if flow in FLOW_MOTION]
    if len(candidates) == 1:
        return candidates[0]
    counts = {"sdr": 0, "ae": 0}
    for row in rows:
        flow = flow_for_motion(row["motion"])
        if flow:
            counts[flow] += 1
    return "ae" if counts["ae"] > counts["sdr"] else "sdr"


def previous_week_start(week_start: datetime) -> datetime:
    from app.services.team_insights.aggregate import madrid_week_bounds

    return madrid_week_bounds(now=week_start - timedelta(hours=12))[0]


def flow_window_start(week_start: datetime) -> datetime:
    """Monday of the oldest of the last FLOW_WEEKS Madrid weeks (the current one included)."""
    start = week_start
    for _ in range(FLOW_WEEKS - 1):
        start = previous_week_start(start)
    return start


def in_window(rows: list[dict], start: datetime, end: datetime) -> list[dict]:
    return [r for r in rows if start <= engine.parse_instant(r["observed_at"]) < end]


def rows_of(memos: list[dict]) -> list[dict]:
    return [row for row in (engine.interaction_row(memo) for memo in memos) if row is not None]


def rep_focus(
    rows: list[dict],
    sales_role: str | None,
    playbook_for,
    *,
    prev_start: datetime,
    week_start: datetime,
    flow: str | None = None,
) -> dict | None:
    """{motion, steps, focus} for one rep or None when their flow has no published playbook.
    `rows` are the rep's interaction rows (any motion) from at least flow_window_start(week_start);
    the flow is resolved over those FLOW_WEEKS weeks, the focus over [prev_start, week_start)."""
    from app.services.team_insights.aggregate import madrid_week_bounds

    week_end = madrid_week_bounds(now=week_start)[1]
    flow_rows = in_window(rows, flow_window_start(week_start), week_end)
    resolved = resolve_flow(sales_role, flow_rows, published_flows(playbook_for), flow)
    motion = motion_for_flow(resolved, flow_rows, playbook_for)
    playbook = playbook_for(motion)
    if not playbook["published"]:
        return None
    prev_week = [r for r in in_window(rows, prev_start, week_start) if r["motion"] == motion]
    return {"motion": motion, "steps": playbook["steps"], "focus": engine.choose_focus(prev_week, playbook["steps"])}


def coaching_focus_by_user(
    supabase, company_id: str, reps: list[dict], *, now: datetime | None = None
) -> dict[str, dict | None]:
    """{user_id: {step_id, label, rate} | None} for every rep. Never raises."""
    from app.services.team_insights.aggregate import madrid_week_bounds

    ids = [str(rep.get("userId")) for rep in reps if rep.get("userId")]
    out: dict[str, dict | None] = {uid: None for uid in ids}
    try:
        week_start, week_end = madrid_week_bounds(now=now or datetime.now(timezone.utc))
        prev_start = previous_week_start(week_start)
        flow_start = flow_window_start(week_start)
        memos = reads.load_memos(supabase, company_id, ids, start=flow_start)
    except Exception:
        return out
    rows_by_user: dict[str, list[dict]] = {}
    for row in in_window(rows_of(memos), flow_start, week_end):
        rows_by_user.setdefault(row["user_id"], []).append(row)
    playbooks: dict[str, dict] = {}

    def playbook_for(motion: str) -> dict:
        if motion not in playbooks:
            playbooks[motion] = reads.load_published_playbook(supabase, company_id, motion)
        return playbooks[motion]

    for rep in reps:
        uid = str(rep.get("userId") or "")
        try:
            found = rep_focus(
                rows_by_user.get(uid, []), rep.get("salesRole"), playbook_for,
                prev_start=prev_start, week_start=week_start,
            )
            focus = found["focus"] if found else None
            if focus:
                out[uid] = {"step_id": focus["step_id"], "label": focus["label"], "rate": focus["rate"]}
        except Exception:
            out[uid] = None
    return out
