"""Period snapshot. A meeting is not a win, and an unproven close is unavailable, not zero."""

from __future__ import annotations

from app.services.coaching.metrics import aggregate_adherence

# T12 (REPORTING_BY_FLOW_ENABLED): which report cards a rep's flow shows. SDR prospects and
# hands off; AE closes what the SDR booked. General (or an unset/unknown role) sees both, D1.
SDR_SECTIONS: tuple[str, ...] = ("attempts", "connected_calls", "meetings_agreed", "handoffs")
AE_SECTIONS: tuple[str, ...] = ("meetings_held", "deals_in_progress", "proposals_sent", "deals_won")
FLOW_METRIC_KEYS: tuple[str, ...] = ("handoffs", "meetings_held", "deals_in_progress", "proposals_sent")


def flow_sections(sales_role: str | None) -> list[str]:
    """D1: null/unknown sales_role behaves like "general" - both blocks, no duplicates."""
    role = (sales_role or "").strip().lower()
    if role == "sdr":
        return list(SDR_SECTIONS)
    if role == "ae":
        return list(AE_SECTIONS)
    return list(dict.fromkeys([*SDR_SECTIONS, *AE_SECTIONS]))


def build_snapshot(
    *,
    scope: str,
    period_start: str,
    period_end: str,
    timezone: str,
    interactions: list[dict],
    outcomes: dict,
    adherence_parts: list[dict] | None = None,
    channels: dict[str, int] | None = None,
    sales_role: str | None = None,
    flow_facts: dict | None = None,
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
    metrics = {
        "attempts": attempts,
        "connected_calls": connected,
        "meetings_agreed": meetings,
        "deals_won": deals_won,
        "deals_lost": deals_lost,
        "adherence": adherence,
    }
    if channels is not None:
        metrics["channels"] = dict(channels)
    facts = flow_facts or {}
    if sales_role is not None:
        for key in FLOW_METRIC_KEYS:
            metrics[key] = facts.get(key)
    snapshot = {
        "scope": scope,
        "period_start": period_start,
        "period_end": period_end,
        "timezone": timezone,
        "metrics": metrics,
        "coverage": {"crm_outcomes": coverage},
        "examples": examples,
        "coaching": None,
    }
    if sales_role is not None:
        snapshot["sections"] = flow_sections(sales_role)
    return snapshot
