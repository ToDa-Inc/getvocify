"""T4 (D8): what the AE may read of the SDR after a handoff - memos, briefs, Ask.

Kept apart from services/handoffs.py (T3, concurrent work) so the two tasks never touch
the same file. Reads the same deal_handoffs table T3's migration creates, with the same
missing-table fallback: a company that hasn't had migration 056 applied yet, or has
HANDOFF_ENABLED off, gets today's behaviour - no handoff-based reads at all.
"""

from __future__ import annotations

from typing import Any, Optional

_HANDOFF_STATUSES = ["active", "closed"]


def _missing_handoffs_table(exc: BaseException) -> bool:
    """True when migration 056_deal_handoffs.sql has not run yet: an undefined-table/relation
    error naming deal_handoffs (42P01, or PostgREST's PGRST205 schema-cache miss). Mirrors
    services/handoffs.py's own check; duplicated rather than imported so the two modules
    never need to change together."""
    try:
        from postgrest.exceptions import APIError
    except ImportError:
        APIError = ()  # type: ignore[misc, assignment]

    if isinstance(exc, APIError):
        code = str(exc.code or "").upper()
        msg = (exc.message or str(exc)).lower()
        if (
            code in {"42P01", "PGRST205"} or "does not exist" in msg or "could not find the table" in msg
        ) and "deal_handoffs" in msg:
            return True

    msg = str(exc).lower()
    return "deal_handoffs" in msg and ("42p01" in msg or "does not exist" in msg)


def handoff_reads_enabled(supabase: Any, company_id: Optional[str]) -> bool:
    """HANDOFF_ENABLED is the same flag that creates handoffs (T3) - reading what got
    handed off is gated the same way, off by default."""
    if not company_id:
        return False
    from app.services.feature_flags import is_enabled

    return is_enabled(supabase, company_id, "HANDOFF_ENABLED")


def handoff_sdr_ids_for_ae(supabase: Any, *, company_id: str, ae_user_id: str) -> dict[str, str]:
    """contact_id -> sdr_user_id for every handoff (active or closed) to this AE.

    D8: the AE reads the SDR's memos of a contact handed off to them, both while the
    handoff is active and after it closes - history doesn't vanish once the deal is done.
    """
    try:
        rows = (
            supabase.table("deal_handoffs")
            .select("contact_id,sdr_user_id,status")
            .eq("company_id", company_id)
            .eq("ae_user_id", ae_user_id)
            .in_("status", _HANDOFF_STATUSES)
            .execute()
        ).data or []
    except Exception as exc:
        if _missing_handoffs_table(exc):
            return {}
        raise
    out: dict[str, str] = {}
    for row in rows:
        contact_id = row.get("contact_id")
        sdr_id = row.get("sdr_user_id")
        if contact_id and sdr_id and (row.get("status") in _HANDOFF_STATUSES):
            out[str(contact_id)] = str(sdr_id)
    return out


def handoff_sdr_ids_for_viewer(supabase: Any, *, company_id: Optional[str], viewer_id: str) -> dict[str, str]:
    """handoff_sdr_ids_for_ae, but empty outright unless HANDOFF_ENABLED for the company -
    flag OFF must equal pre-change behaviour (no handoff-based read at all)."""
    if not handoff_reads_enabled(supabase, company_id):
        return {}
    return handoff_sdr_ids_for_ae(supabase, company_id=str(company_id), ae_user_id=viewer_id)
