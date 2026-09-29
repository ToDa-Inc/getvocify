"""Playbook insights (Fase 3): what the calls say about a playbook, per step and per objection.

Pure functions over rows the API module already read: no supabase, no clock. A step's
rate is met / (met + missed) across the scored calls of the period, and only once at least
MIN_APPLICABLE calls could be judged on it; below that a number would be noise, so it is
None. Objections reuse team_insights.objections (same counting, same best_example rule)
and never carry a rep name: `best_example` is the response quote and nothing else.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from app.services.team_insights.aggregate import _current_scores, _parse_instant
from app.services.team_insights.objections import objection_counts

# met + missed below this and the step has no rate.
MIN_APPLICABLE = 10
PERIODS = ("week", "month")
_SCORED = frozenset({"ready", "partial"})


def memo_instant(memo: dict) -> datetime | None:
    """The call's own time, like team adherence: capture_started_at, else created_at."""
    return _parse_instant(memo.get("capture_started_at")) or _parse_instant(memo.get("created_at"))


def scored_memo_ids(score_rows: list[dict]) -> set[str]:
    """Memos whose current (latest revision) score is ready or partial."""
    ids: set[str] = set()
    for memo_id, row in _current_scores(score_rows).items():
        score = row.get("score")
        if isinstance(score, dict) and score.get("status") in _SCORED:
            ids.add(memo_id)
    return ids


def consider_memos(
    memos: list[dict],
    *,
    motion: str,
    scored_ids: set[str],
    start: datetime,
    end: datetime,
) -> list[dict]:
    """The scored memos of this motion whose call time is in [start, end)."""
    kept: list[dict] = []
    for memo in memos:
        if str(memo.get("sales_motion_key") or "") != motion:
            continue
        if str(memo.get("id")) not in scored_ids:
            continue
        instant = memo_instant(memo)
        if instant is None or instant < start or instant >= end:
            continue
        kept.append(memo)
    return kept


def memo_observations(memo: dict) -> dict[str, str]:
    """{step_id: status} of a memo. extraction.intelligence first, then the flat
    extraction.playbook_observations. The first entry of a step wins."""
    extraction = memo.get("extraction")
    if isinstance(extraction, str):
        try:
            extraction = json.loads(extraction)
        except ValueError:
            extraction = {}
    if not isinstance(extraction, dict):
        return {}
    intelligence = extraction.get("intelligence")
    observations = intelligence.get("playbook_observations") if isinstance(intelligence, dict) else None
    if not isinstance(observations, list):
        observations = extraction.get("playbook_observations")
    by_step: dict[str, str] = {}
    for item in observations if isinstance(observations, list) else []:
        if not isinstance(item, dict):
            continue
        step_id = str(item.get("step_id") or "").strip()
        if step_id and step_id not in by_step:
            by_step[step_id] = str(item.get("status") or "").strip().lower()
    return by_step


def step_insights(memos: list[dict], steps: list[dict]) -> list[dict]:
    """One entry per step of the active version, in its order. Step ids the version does
    not have are ignored; not_applicable and unknown are not counted."""
    order: list[str] = []
    for step in steps or []:
        step_id = str(step.get("step_id") or "").strip() if isinstance(step, dict) else ""
        if step_id and step_id not in order:
            order.append(step_id)
    tallies = {step_id: {"met": 0, "missed": 0} for step_id in order}
    for memo in memos:
        for step_id, status in memo_observations(memo).items():
            tally = tallies.get(step_id)
            if tally is not None and status in tally:
                tally[status] += 1
    out: list[dict] = []
    for step_id in order:
        met, missed = tallies[step_id]["met"], tallies[step_id]["missed"]
        applicable = met + missed
        out.append({
            "step_id": step_id,
            "met": met,
            "missed": missed,
            "rate": met / applicable if applicable >= MIN_APPLICABLE else None,
        })
    return out


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
    scored_ids: set[str],
    pattern_rows: list[dict],
    steps: list[dict],
    entries: list[dict],
    start: datetime,
    end: datetime,
    motion: str,
) -> dict:
    """The response body. memos are any candidate memos; only the scored, in-period ones
    of `motion` are considered. steps/entries are the active version's (empty without one)."""
    considered = consider_memos(memos, motion=motion, scored_ids=scored_ids, start=start, end=end)
    return {
        "period": period,
        "calls": len(considered),
        "steps": step_insights(considered, steps),
        "objections": objection_insights(considered, pattern_rows, entries),
    }
