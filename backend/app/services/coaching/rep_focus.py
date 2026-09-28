"""One focus per rep from the previous full Madrid week: the Head of Sales table, the daily
and weekly coaching lines. Same flow / motion / published steps as /coaching/me/summary.
Reads are tolerant: any failure means no focus."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.services.coaching import rep_coaching as engine
from app.services.coaching import rep_coaching_reads as reads
from app.services.playbooks.motion import flow_for_motion

FLOW_MOTION = {"sdr": "discovery", "ae": "closing"}


def resolve_flow(sales_role: str | None, rows: list[dict]) -> str:
    """sdr -> discovery, ae -> closing; general -> the flow with most of the rep's interactions."""
    if sales_role in FLOW_MOTION:
        return sales_role
    counts = {"sdr": 0, "ae": 0}
    for row in rows:
        flow = flow_for_motion(row["motion"])
        if flow:
            counts[flow] += 1
    return "ae" if counts["ae"] > counts["sdr"] else "sdr"


def previous_week_start(week_start: datetime) -> datetime:
    from app.services.team_insights.aggregate import madrid_week_bounds

    return madrid_week_bounds(now=week_start - timedelta(hours=12))[0]


def in_window(rows: list[dict], start: datetime, end: datetime) -> list[dict]:
    return [r for r in rows if start <= engine.parse_instant(r["observed_at"]) < end]


def rows_of(memos: list[dict]) -> list[dict]:
    return [row for row in (engine.interaction_row(memo) for memo in memos) if row is not None]


def rep_focus(
    rows: list[dict], sales_role: str | None, playbook_for, *, prev_start: datetime, week_start: datetime
) -> dict | None:
    """{motion, steps, focus} for one rep or None when their flow has no published playbook.
    `rows` are the rep's interaction rows (any motion); focus is chosen over [prev_start, week_start)."""
    motion = FLOW_MOTION[resolve_flow(sales_role, rows)]
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
        memos = reads.load_memos(supabase, company_id, ids, start=prev_start)
    except Exception:
        return out
    rows_by_user: dict[str, list[dict]] = {}
    for row in in_window(rows_of(memos), prev_start, week_end):
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
