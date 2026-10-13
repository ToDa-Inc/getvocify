"""Playbook insights (Fase 3): what the calls say about a playbook, per step and per objection.

Pure functions over rows the API module already read: no supabase, no clock. A step's
rate is the rep's coaching number (done over done + not done, rep_coaching.step_rates) across
the read conversations of the period, and only once at least
MIN_APPLICABLE calls could be judged on it; below that a number would be noise, so it is
None. Objections reuse team_insights.objections (same counting, same best_example rule)
and never carry a rep name: `best_example` is the response quote and nothing else.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from app.services.coaching.rep_coaching import interaction_row, step_rates
from app.services.team_insights.aggregate import _parse_instant
from app.services.team_insights.objections import objection_counts

# met + missed below this and the step has no rate.
MIN_APPLICABLE = 10
PERIODS = ("week", "month")


def memo_instant(memo: dict) -> datetime | None:
    """The call's own time, like team adherence: capture_started_at, else created_at."""
    return _parse_instant(memo.get("capture_started_at")) or _parse_instant(memo.get("created_at"))


def coaching_row(memo: dict) -> dict | None:
    """The call as the rep's coaching reads it (rep_coaching.interaction_row), so a step's rate
    here is the rep's number: the same states, conversations only, a step matched by its
    criterion. The extraction may come as JSON text, and older calls keep their observations
    under the flat extraction.playbook_observations (extraction.intelligence wins)."""
    extraction = memo.get("extraction")
    if isinstance(extraction, str):
        try:
            extraction = json.loads(extraction)
        except ValueError:
            extraction = {}
    extraction = extraction if isinstance(extraction, dict) else {}
    intelligence = extraction.get("intelligence") if isinstance(extraction.get("intelligence"), dict) else {}
    if not isinstance(intelligence.get("playbook_observations"), list):
        flat = extraction.get("playbook_observations")
        intelligence = {**intelligence, "playbook_observations": flat if isinstance(flat, list) else []}
    return interaction_row({**memo, "extraction": {**extraction, "intelligence": intelligence}})


def consider_memos(memos: list[dict], *, motion: str, start: datetime, end: datetime) -> list[dict]:
    """The read conversations of this motion whose call time is in [start, end): calls with step
    verdicts, minus voicemails, no-answers and calls under 30 s (rep_coaching.is_conversation)."""
    kept: list[dict] = []
    for memo in memos:
        if str(memo.get("sales_motion_key") or "") != motion:
            continue
        instant = memo_instant(memo)
        if instant is None or instant < start or instant >= end:
            continue
        row = coaching_row(memo)
        if row is None or not row["is_conversation"]:
            continue
        kept.append(memo)
    return kept


def step_insights(memos: list[dict], steps: list[dict]) -> list[dict]:
    """One entry per step of the active version, in its order: rep_coaching.step_rates over these
    calls (done, improvable included, over done + not done; a verdict counts for the step with its
    criterion). The rate needs MIN_APPLICABLE calls judged on the step."""
    live: list[dict] = []
    seen: set[str] = set()
    for step in steps or []:
        step_id = str(step.get("step_id") or "").strip() if isinstance(step, dict) else ""
        if step_id and step_id not in seen:
            seen.add(step_id)
            live.append({**step, "step_id": step_id})
    rows = [row for row in (coaching_row(memo) for memo in memos) if row is not None]
    return [
        {
            "step_id": rate["step_id"],
            "met": rate["done"],
            "missed": rate["missing"],
            "rate": rate["done"] / rate["applicable"] if rate["applicable"] >= MIN_APPLICABLE else None,
        }
        for rate in step_rates(rows, live)
    ]


def objection_insights(
    memos: list[dict],
    pattern_rows: list[dict],
    entries: list[dict],
) -> list[dict]:
    """Objection categories of these memos, most frequent first. `pattern_rows` are the
    interaction_patterns of these memos (extracted objections); each is dated with its
    memo's call time so "most recent" means the latest call, not the latest extraction."""
    calls = len(memos)
    instants = {str(memo.get("id")): memo_instant(memo) for memo in memos}
    rows = [
        {**row, "observed_at": instants[str(row.get("memo_id"))]}
        for row in pattern_rows
        if instants.get(str(row.get("memo_id"))) is not None
    ]
    counted = objection_counts(
        rows,
        start=datetime.min.replace(tzinfo=timezone.utc),
        end=datetime.max.replace(tzinfo=timezone.utc),
        playbook_entries=entries,
        include_guidance=True,
    )
    return [
        {
            "category": item["name"],
            "count": item["count"],
            "share": item["count"] / calls if calls else 0,
            "answered": bool(item.get("how_to")),
            "best_example": item.get("best_example"),
        }
        for item in counted
    ]


def build_insights(
    *,
    period: str,
    memos: list[dict],
    pattern_rows: list[dict],
    steps: list[dict],
    entries: list[dict],
    start: datetime,
    end: datetime,
    motion: str,
) -> dict:
    """The response body. memos are any candidate memos; only the read conversations of `motion`
    in the period are considered. steps/entries are the active version's (empty without one)."""
    considered = consider_memos(memos, motion=motion, start=start, end=end)
    return {
        "period": period,
        "calls": len(considered),
        "steps": step_insights(considered, steps),
        "objections": objection_insights(considered, pattern_rows, entries),
    }
