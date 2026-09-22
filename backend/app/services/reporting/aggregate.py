"""Period snapshot. A meeting is not a win, and an unproven close is unavailable, not zero."""

from __future__ import annotations

from app.services.coaching.metrics import aggregate_adherence


def build_snapshot(
    *,
    scope: str,
    period_start: str,
    period_end: str,
    timezone: str,
    interactions: list[dict],
    outcomes: dict,
    adherence_parts: list[dict] | None = None,
) -> dict:
    attempts = 0
    connected = 0
    meetings = 0
    examples: list[str] = []
    for item in interactions:
        captured = item.get("captured_at")
        if captured is None or captured < period_start or captured >= period_end:
            continue
        attempts += 1
        if item.get("screening") not in {"voicemail", "no_response"} and item.get("connected"):
            connected += 1
        if item.get("meeting_agreed") is True:
            meetings += 1
        if item.get("memo_id") and len(examples) < 3:
            examples.append(item["memo_id"])
    coverage = outcomes.get("coverage") or "unavailable"
    if coverage != "complete":
        deals_won = None
        deals_lost = None
    else:
        deals_won = int(outcomes.get("won") or 0)
        deals_lost = int(outcomes.get("lost") or 0)
    adherence = None
    if adherence_parts:
        adherence = aggregate_adherence(adherence_parts)["adherence"]
    return {
        "scope": scope,
        "period_start": period_start,
        "period_end": period_end,
        "timezone": timezone,
        "metrics": {
            "attempts": attempts,
            "connected_calls": connected,
            "meetings_agreed": meetings,
            "deals_won": deals_won,
            "deals_lost": deals_lost,
            "adherence": adherence,
        },
        "coverage": {"crm_outcomes": coverage},
        "examples": examples,
        "coaching": None,
    }
