"""Priority ranking. Incomplete history is not 'never called', and an agreed meeting is not a cold call."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional


def candidate_id(connection_id: str, contact_id: str, deal_id: Optional[str]) -> str:
    return f"{connection_id}:{contact_id}:{deal_id or ''}"


def contacts_url(provider: str | None, portal_id: str | None = None) -> str | None:
    name = (provider or "").strip().lower()
    if name == "hubspot" and portal_id:
        return f"https://app.hubspot.com/contacts/{portal_id}/objects/0-1"
    if name == "pipedrive":
        return "https://app.pipedrive.com/persons"
    return None


def empty_priority_copy(
    *,
    connected: bool,
    coverage: str,
    role: str = "member",
    assigned: bool | None = True,
    provider: str | None = None,
    portal_id: str | None = None,
) -> dict:
    if not connected:
        action = "connect_crm" if role in ("owner", "admin") else None
        return {"title": "title_connect_crm", "action": action}
    if coverage != "complete":
        return {"title": "title_history_partial", "action": "retry"}
    if assigned is False:
        action = "map_owners" if role in ("owner", "admin") else "review_assignment"
        return {"title": "title_no_assigned", "action": action}
    return {
        "title": "title_none_now",
        "action": "open_contacts",
        "contacts_url": contacts_url(provider, portal_id),
    }


def rank_candidates(candidates: list[dict], now: datetime, recent_days: int = 14) -> list[dict]:
    window = timedelta(days=recent_days)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    ranked = []
    for raw in candidates:
        if raw.get("meeting_agreed") is True:
            continue
        if raw.get("deal_status") == "closed":
            continue
        if raw.get("owner_ambiguous"):
            continue
        coverage = raw.get("coverage") or "partial"
        last_call = raw.get("last_call_at")
        pain_at = _as_dt(raw.get("pain_at"))
        recent_pain = bool(raw.get("pain_confirmed") and pain_at and now - pain_at <= window)
        never_called = last_call is None
        scheduled = _as_dt(raw.get("scheduled_at"))
        if scheduled and scheduled > now:
            tier = 4
            reason = "scheduled_no_early_call"
            next_action = None
        elif recent_pain:
            tier = 1
            reason = "pain_agree_next_step"
            next_action = "agree_next_step"
        elif never_called and coverage != "complete":
            tier = None
            reason = "history_partial"
            next_action = "retry_read"
        elif never_called:
            tier = 2
            reason = "no_calls_logged"
            next_action = "log_first_call"
        else:
            tier = 3
            reason = "followup_pending"
            next_action = "resume_contact"
        identity = candidate_id(raw["connection_id"], raw["contact_id"], raw.get("deal_id"))
        ranked.append({
            "id": identity,
            "connection_id": raw["connection_id"],
            "contact_id": raw["contact_id"],
            "deal_id": raw.get("deal_id"),
            "tier": tier,
            "reason": reason,
            "evidence_refs": list(raw.get("evidence_refs") or []),
            "next_action": next_action,
            "observed_at": raw.get("observed_at"),
            "scheduled_at": raw.get("scheduled_at"),
            "coverage": coverage,
            "never_called": never_called and coverage == "complete",
        })
    ranked.sort(key=lambda row: (row["tier"] is None, row["tier"] or 0, row["id"]))
    return ranked


def _as_dt(value):
    if value is None or isinstance(value, datetime):
        if isinstance(value, datetime) and value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    text = str(value).replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed
