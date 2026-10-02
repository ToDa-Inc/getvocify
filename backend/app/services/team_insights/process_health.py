"""Head of Sales phase 2: is a flow failing because reps skip the playbook, or because the
playbook itself does not work? (docs/features/HEAD_OF_SALES_DASHBOARD_PLAN.md §0, §5)

Each scored interaction lands in one cell: follows the playbook or not (step adherence
>= FOLLOWS_THRESHOLD) x reached the flow's goal or not. Comparing the goal rate of the two
groups tells the two causes apart. Pure and deterministic: no LLM decides a verdict.

Only goals observable in a single interaction are measured. Today that is discovery's
meeting_booked (a meeting agreed in the call). Closing's goal (proposal and close) lives
in the CRM deal, not in one conversation, so that flow reports goal_not_measurable
instead of a made-up number.
"""

from __future__ import annotations

from typing import Optional

from app.services.playbooks.motion import goal_for

FOLLOWS_THRESHOLD = 0.7
# Below this many interactions in a group there is no rate and no verdict.
MIN_GROUP = 10
# Below this many reached goals (meetings the reps declared) in the whole flow, "0 % against 0 %"
# compares nothing: no verdict either.
MIN_OUTCOMES = 3
# Goal-rate gap (absolute) that counts as a real difference between the groups.
MIN_GAP = 0.05
# Share of interactions that follow the playbook below which the fix is coaching.
LOW_FOLLOW_SHARE = 0.5

MEASURABLE_GOALS = frozenset({"meeting_booked"})


def follows_playbook(part: dict) -> Optional[bool]:
    """Met / (met + missed) >= threshold. Unknown steps are not misses. None = not scorable."""
    met = int(part.get("met_steps") or 0)
    missed = int(part.get("missed_steps") or 0)
    applicable = met + missed
    if applicable == 0:
        return None
    return met / applicable >= FOLLOWS_THRESHOLD


def _rate(hits: int, total: int) -> Optional[float]:
    return hits / total if total >= MIN_GROUP else None


def _verdict(follows_n: int, deviates_n: int, follows_rate, deviates_rate, share) -> str:
    if follows_n < MIN_GROUP:
        return "insufficient_data"
    if deviates_n < MIN_GROUP:
        return "no_comparison"
    gap = follows_rate - deviates_rate
    if gap <= -MIN_GAP:
        return "playbook_underperforms"
    if gap < MIN_GAP:
        return "no_difference"
    return "coach_reps" if share < LOW_FOLLOW_SHARE else "playbook_works"


def _flow_health(motion: str, rows: list[dict]) -> dict:
    goal = goal_for(motion)
    base = {"motion": motion, "goal": goal, "scored": len(rows)}
    if goal not in MEASURABLE_GOALS:
        return {**base, "verdict": "goal_not_measurable", "matrix": None}
    cells = {"follows_goal": 0, "follows_no_goal": 0, "deviates_goal": 0, "deviates_no_goal": 0}
    for row in rows:
        group = "follows" if row["_follows"] else "deviates"
        cells[f"{group}_{'goal' if row.get('goal_met') else 'no_goal'}"] += 1
    follows_n = cells["follows_goal"] + cells["follows_no_goal"]
    deviates_n = cells["deviates_goal"] + cells["deviates_no_goal"]
    follows_rate = _rate(cells["follows_goal"], follows_n)
    deviates_rate = _rate(cells["deviates_goal"], deviates_n)
    share = follows_n / len(rows) if rows else None
    verdict = _verdict(follows_n, deviates_n, follows_rate, deviates_rate, share)
    outcomes = cells["follows_goal"] + cells["deviates_goal"]
    if verdict in ("playbook_underperforms", "no_difference", "coach_reps", "playbook_works") and outcomes < MIN_OUTCOMES:
        verdict = "few_outcomes"
    return {
        **base,
        "verdict": verdict,
        "matrix": cells,
        "follow_share": share,
        "follows_goal_rate": follows_rate,
        "deviates_goal_rate": deviates_rate,
        "min_group": MIN_GROUP,
        "needed": max(0, MIN_GROUP - follows_n) if verdict == "insufficient_data" else 0,
        "outcomes": outcomes,
    }


def process_health(rows: list[dict]) -> list[dict]:
    """rows: one per scored interaction in the period, with motion, step counts, goal_met."""
    by_motion: dict[str, list[dict]] = {}
    for row in rows:
        motion = str(row.get("motion") or "").strip()
        follows = follows_playbook(row)
        if not motion or follows is None:
            continue
        by_motion.setdefault(motion, []).append({**row, "_follows": follows})
    return [_flow_health(motion, by_motion[motion]) for motion in sorted(by_motion)]
