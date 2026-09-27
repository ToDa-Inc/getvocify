"""SDR->AE handoff (T3, D2/D6). Rules are pure; supabase effects are kept apart so the rules
stay unit-testable without a client. A missing deal_handoffs table (migration 056 not applied
yet) degrades to "no handoff": callers get an empty read or a skipped write, never a 500 -
old behaviour."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

ACTIVE = "active"
CLOSED = "closed"
CANCELLED = "cancelled"


class HandoffError(Exception):
    """code is one of: needs_ae, self_owned, invalid_ae."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _missing_handoffs_table(exc: BaseException) -> bool:
    """True when migration 056_deal_handoffs.sql has not run yet: an undefined-table/relation
    error naming deal_handoffs (42P01, or PostgREST's PGRST205 schema-cache miss)."""
    try:
        from postgrest.exceptions import APIError
    except ImportError:
        APIError = ()  # type: ignore[misc, assignment]

    if isinstance(exc, APIError):
        code = str(exc.code or "").upper()
        msg = (exc.message or str(exc)).lower()
        if (code in {"42P01", "PGRST205"} or "does not exist" in msg or "could not find the table" in msg) and "deal_handoffs" in msg:
            return True

    msg = str(exc).lower()
    return "deal_handoffs" in msg and ("42p01" in msg or "does not exist" in msg)


def resolve_ae(sdr_membership: Any, requested_ae_user_id: Optional[str] = None) -> str:
    """D2: the AE for an SDR handoff. An explicit choice (used to fill in a missing route)
    wins; otherwise the SDR's own handoff_ae_user_id. Neither -> needs_ae, so the caller
    can ask the SDR to pick one."""
    ae = requested_ae_user_id or getattr(sdr_membership, "handoff_ae_user_id", None)
    if not ae:
        raise HandoffError("needs_ae")
    return str(ae)


def resolve_owner_for_general(membership: Any, requested_ae_user_id: Optional[str] = None) -> Optional[str]:
    """A General with no route configured (and none given) keeps the deal - D2/T3: 'un
    General sin AE no traspasa'. Returns None for that case; the caller raises self_owned."""
    return requested_ae_user_id or getattr(membership, "handoff_ae_user_id", None)


def ae_membership_row(supabase: Any, *, company_id: str, ae_user_id: str) -> Optional[dict]:
    rows = (
        supabase.table("company_members")
        .select("user_id,sales_role,status")
        .eq("company_id", company_id)
        .eq("user_id", str(ae_user_id))
        .limit(1)
        .execute()
    ).data or []
    return rows[0] if rows else None


def valid_ae(row: Optional[dict]) -> bool:
    """D1: a null sales_role behaves as 'general'. An AE handoff target is an active
    member who is an AE or a General - never another SDR."""
    if not row or (row.get("status") or "active") != "active":
        return False
    return row.get("sales_role") in (None, "ae", "general")


def create_handoff(
    supabase: Any,
    *,
    company_id: str,
    connection_id: str,
    contact_id: str,
    sdr_user_id: str,
    ae_user_id: str,
    deal_id: Optional[str] = None,
    source_memo_id: Optional[str] = None,
    meeting_starts_at: Optional[str] = None,
) -> dict:
    """Idempotent (D6): a request that repeats an already-active handoff for this contact
    returns that row as-is - the transfer already happened, even to a different AE."""
    try:
        existing = (
            supabase.table("deal_handoffs")
            .select("*")
            .eq("company_id", company_id)
            .eq("connection_id", connection_id)
            .eq("contact_id", str(contact_id))
            .eq("status", ACTIVE)
            .limit(1)
            .execute()
        ).data or []
    except Exception as exc:
        if _missing_handoffs_table(exc):
            return {"skipped": "table_missing", "created": False}
        raise
    if existing:
        return {**existing[0], "created": False}

    payload = {
        "company_id": company_id,
        "connection_id": connection_id,
        "contact_id": str(contact_id),
        "deal_id": str(deal_id) if deal_id else None,
        "sdr_user_id": str(sdr_user_id),
        "ae_user_id": str(ae_user_id),
        "source_memo_id": str(source_memo_id) if source_memo_id else None,
        "meeting_starts_at": meeting_starts_at,
        "status": ACTIVE,
    }
    try:
        inserted = supabase.table("deal_handoffs").insert(payload).execute().data or []
    except Exception as exc:
        if _missing_handoffs_table(exc):
            return {"skipped": "table_missing", "created": False}
        raise
    row = inserted[0] if inserted else dict(payload)
    return {**row, "created": True}


def close_handoff(
    supabase: Any,
    *,
    company_id: str,
    connection_id: str,
    contact_id: str,
    reason: str = "deal_closed",
    now: Optional[datetime] = None,
) -> Optional[dict]:
    """Closes the active handoff for a contact once its deal reaches an end stage, or it
    is cancelled. No active row -> no-op (None), never an error."""
    status_value = CANCELLED if reason == "cancelled" else CLOSED
    closed_at = (now or datetime.now(timezone.utc)).isoformat()
    try:
        updated = (
            supabase.table("deal_handoffs")
            .update({"status": status_value, "closed_at": closed_at})
            .eq("company_id", company_id)
            .eq("connection_id", connection_id)
            .eq("contact_id", str(contact_id))
            .eq("status", ACTIVE)
            .execute()
        ).data or []
    except Exception as exc:
        if _missing_handoffs_table(exc):
            return None
        raise
    return updated[0] if updated else None


_END_STAGES = {
    "hubspot": {"closedwon", "closedlost"},
    "pipedrive": {"won", "lost"},
}


def stage_ends_deal(
    provider: Optional[str],
    *,
    stage_id: Optional[str] = None,
    status: Optional[str] = None,
    is_closed: Optional[bool] = None,
) -> bool:
    """True when a deal just reached an end stage for this provider (used to trigger
    close_handoff). HubSpot: the well-known stage ids, or the pipeline's own isClosed
    metadata when the caller already has it. Pipedrive: deal status won/lost."""
    if is_closed:
        return True
    name = (provider or "").strip().lower()
    if name == "hubspot":
        return (stage_id or "").strip().lower() in _END_STAGES["hubspot"]
    if name == "pipedrive":
        return (status or "").strip().lower() in _END_STAGES["pipedrive"]
    return False


def active_handoffs_for_ae(supabase: Any, *, company_id: str, ae_user_id: str) -> list[dict]:
    try:
        return (
            supabase.table("deal_handoffs")
            .select("*")
            .eq("company_id", company_id)
            .eq("ae_user_id", ae_user_id)
            .eq("status", ACTIVE)
            .execute()
        ).data or []
    except Exception as exc:
        if _missing_handoffs_table(exc):
            return []
        raise


def active_handoffs_for_sdr(supabase: Any, *, company_id: str, sdr_user_id: str) -> list[dict]:
    try:
        return (
            supabase.table("deal_handoffs")
            .select("*")
            .eq("company_id", company_id)
            .eq("sdr_user_id", sdr_user_id)
            .eq("status", ACTIVE)
            .execute()
        ).data or []
    except Exception as exc:
        if _missing_handoffs_table(exc):
            return []
        raise
