"""Queue exit by CRM state (F16). Pure helpers plus thin Supabase loaders."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from app.services.deal_stage_confirm import FLAG as DEAL_STAGE_FLAG
from app.services.feature_flags import is_enabled

FLAG = "CRM_STATE_EXIT_ENABLED"
SOURCE_DEAL = "deal_stage"
SOURCE_LEAD = "lead_status"
PIPEDRIVE_WON = "status:won"
PIPEDRIVE_LOST = "status:lost"


@dataclass(frozen=True)
class QueueStates:
    source: str
    booked: tuple[str, ...]
    ended: tuple[str, ...]

    @property
    def booked_set(self) -> frozenset[str]:
        return frozenset(self.booked)

    @property
    def ended_set(self) -> frozenset[str]:
        return frozenset(self.ended)


def queue_states_enabled(supabase: Any, company_id: Optional[str]) -> bool:
    return is_enabled(supabase, company_id, FLAG) and is_enabled(supabase, company_id, DEAL_STAGE_FLAG)


def load_queue_states(
    supabase: Any,
    company_id: Optional[str],
    *,
    connection_id: Optional[str] = None,
) -> Optional[QueueStates]:
    if not company_id or not queue_states_enabled(supabase, company_id):
        return None
    query = supabase.table("crm_configurations").select(
        "queue_state_source,queue_booked_states,queue_ended_states,connection_id"
    )
    if connection_id:
        query = query.eq("connection_id", connection_id)
    else:
        query = query.eq("company_id", company_id)
    result = query.limit(1).execute()
    rows = getattr(result, "data", None) or []
    if not rows:
        return QueueStates(source=SOURCE_DEAL, booked=(), ended=())
    row = rows[0] if isinstance(rows, list) else rows
    source = str(row.get("queue_state_source") or SOURCE_DEAL).strip() or SOURCE_DEAL
    if source not in {SOURCE_DEAL, SOURCE_LEAD}:
        source = SOURCE_DEAL
    booked = tuple(dict.fromkeys(str(v).strip() for v in (row.get("queue_booked_states") or []) if str(v).strip()))
    ended = tuple(
        dict.fromkeys(
            str(v).strip()
            for v in (row.get("queue_ended_states") or [])
            if str(v).strip() and str(v).strip() not in booked
        )
    )
    return QueueStates(source=source, booked=booked, ended=ended)


def exit_reason(state: Optional[str], states: Optional[QueueStates]) -> Optional[str]:
    if not states or state in (None, ""):
        return None
    value = str(state).strip()
    if not value:
        return None
    if value in states.booked_set:
        return "booked"
    if value in states.ended_set:
        return "ended"
    return None


def _as_dt(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value).strip()
    if not text:
        return None
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def pick_deal_state(deals: list[dict], *, provider: str = "hubspot") -> Optional[str]:
    """Most recently modified deal wins; tie → greater id. Pipedrive won/lost become status:*."""
    if not deals:
        return None
    ranked = sorted(
        deals,
        key=lambda d: (
            _as_dt(d.get("updated_at") or d.get("update_time") or d.get("hs_lastmodifieddate"))
            or datetime.min.replace(tzinfo=timezone.utc),
            str(d.get("id") or ""),
        ),
        reverse=True,
    )
    deal = ranked[0]
    name = (provider or "").lower()
    if name == "pipedrive":
        status = str(deal.get("status") or "").strip().lower()
        if status == "won":
            return PIPEDRIVE_WON
        if status == "lost":
            return PIPEDRIVE_LOST
        stage = deal.get("stage_id")
        return str(stage) if stage not in (None, "") else None
    stage = deal.get("dealstage") if deal.get("dealstage") not in (None, "") else deal.get("stage_id")
    return str(stage) if stage not in (None, "") else None


def confirmed_state_from_extraction(
    extraction: Any,
    source: str,
    provider: str,
) -> Optional[str]:
    raw = getattr(extraction, "raw_extraction", None)
    if raw is None and isinstance(extraction, dict):
        raw = extraction.get("raw_extraction")
    if not isinstance(raw, dict):
        raw = {}
    if source == SOURCE_LEAD:
        contact = raw.get("contact_properties")
        if isinstance(contact, dict):
            value = contact.get("hs_lead_status")
            if value not in (None, ""):
                return str(value)
        value = raw.get("hs_lead_status")
        return str(value) if value not in (None, "") else None
    name = (provider or "").lower()
    if name == "pipedrive":
        for key in ("stage_id", "dealstage"):
            if isinstance(raw, dict) and raw.get(key) not in (None, ""):
                return str(raw[key])
        value = getattr(extraction, "dealStage", None) if not isinstance(extraction, dict) else extraction.get("dealStage")
        return str(value) if value not in (None, "") else None
    if isinstance(raw, dict) and raw.get("dealstage") not in (None, ""):
        return str(raw["dealstage"])
    value = getattr(extraction, "dealStage", None) if not isinstance(extraction, dict) else extraction.get("dealStage")
    return str(value) if value not in (None, "") else None


def apply_confirmed_crm_state(
    supabase: Any,
    *,
    company_id: str,
    connection_id: str,
    contact_id: str,
    state: str,
) -> None:
    stored = (
        supabase.table("contact_priority_context")
        .select("*")
        .eq("company_id", company_id)
        .eq("connection_id", connection_id)
        .eq("contact_id", str(contact_id))
        .execute()
    )
    for row in getattr(stored, "data", None) or []:
        payload = dict(row.get("payload") or {})
        payload["crm_state"] = state
        (
            supabase.table("contact_priority_context")
            .update({"payload": payload})
            .eq("company_id", company_id)
            .eq("connection_id", connection_id)
            .eq("contact_id", str(contact_id))
            .eq("deal_id", row.get("deal_id") or "")
            .execute()
        )


def contact_exit_states(rows: list[dict], states: Optional[QueueStates]) -> set[str]:
    """Contact ids whose cached crm_state is a queue exit."""
    if not states:
        return set()
    exited: set[str] = set()
    for row in rows:
        payload = row.get("payload") or {}
        if exit_reason(payload.get("crm_state"), states):
            exited.add(str(row.get("contact_id") or ""))
    exited.discard("")
    return exited
