"""T4 (D8): what the AE may read of the SDR after a handoff - memos, briefs, Ask.

Kept apart from services/handoffs.py (T3, concurrent work) so the two tasks never touch
the same file. Reads the same deal_handoffs table T3's migration creates, with the same
missing-table fallback: a company that hasn't had migration 056 applied yet, or has
HANDOFF_ENABLED off, gets today's behaviour - no handoff-based reads at all.

Any failure reading deal_handoffs (missing table, a transient DB error, anything) is
swallowed here and logged, never raised: a broken handoff lookup must not turn an
otherwise-readable memo into a 500. Callers that already have another route to "yes" (the
viewer is the memo's own author, or a manager who can see the whole company) should skip
calling into this module at all - see memos.py and viewer.py - both to save the query and
because a handoff is never needed to justify a read that's already allowed.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

_HANDOFF_STATUSES = ["active", "closed"]

# (connection_id, contact_id) -> the sdr_user_id(s) who ran that contact for this AE. A
# contact can have more than one SDR across its history (handed back and re-routed), so
# each key maps to a set. connection_id is None when the row didn't carry one.
HandoffMap = dict[tuple[Optional[str], str], set[str]]


def _missing_handoffs_table(exc: BaseException) -> bool:
    """True when migration 056_deal_handoffs.sql has not run yet: an undefined-table/relation
    error naming deal_handoffs (42P01, or PostgREST's PGRST205 schema-cache miss). Mirrors
    services/handoffs.py's own check; duplicated rather than imported so the two modules
    never need to change together. Used only to make the log line more specific - every
    exception here is swallowed either way."""
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
    try:
        from app.services.feature_flags import is_enabled

        return is_enabled(supabase, company_id, "HANDOFF_ENABLED")
    except Exception:
        logger.warning("HANDOFF_ENABLED lookup failed for company %s", company_id, exc_info=True)
        return False


def handoff_sdr_map_for_ae(supabase: Any, *, company_id: str, ae_user_id: str) -> HandoffMap:
    """(connection_id, contact_id) -> sdr_user_id set, for every handoff (active or closed)
    to this AE. D8: the AE reads the SDR's memos of a contact handed off to them, both
    while the handoff is active and after it closes - history doesn't vanish once the deal
    is done."""
    try:
        rows = (
            supabase.table("deal_handoffs")
            .select("connection_id,contact_id,sdr_user_id,status")
            .eq("company_id", company_id)
            .eq("ae_user_id", ae_user_id)
            .in_("status", _HANDOFF_STATUSES)
            .execute()
        ).data or []
    except Exception as exc:
        logger.warning(
            "deal_handoffs read failed for company %s (%s): %s",
            company_id,
            "missing table" if _missing_handoffs_table(exc) else "error",
            exc,
        )
        return {}
    out: HandoffMap = {}
    for row in rows:
        contact_id = row.get("contact_id")
        sdr_id = row.get("sdr_user_id")
        if not contact_id or not sdr_id or row.get("status") not in _HANDOFF_STATUSES:
            continue
        connection_id = row.get("connection_id")
        key = (str(connection_id) if connection_id else None, str(contact_id))
        out.setdefault(key, set()).add(str(sdr_id))
    return out


def handoff_sdr_map_for_viewer(supabase: Any, *, company_id: Optional[str], viewer_id: str) -> HandoffMap:
    """handoff_sdr_map_for_ae, but empty outright unless HANDOFF_ENABLED for the company -
    flag OFF must equal pre-change behaviour (no handoff-based read at all)."""
    if not handoff_reads_enabled(supabase, company_id):
        return {}
    return handoff_sdr_map_for_ae(supabase, company_id=str(company_id), ae_user_id=viewer_id)


def sdr_ids_for_contact(
    handoff_map: HandoffMap,
    contact_id: Optional[str],
    *,
    connection_id: Optional[str] = None,
) -> set[str]:
    """The sdr_user_id(s) handoff_map allows for this contact. With connection_id, only that
    connection's row(s); without it (memos carry no connection_id column), every connection
    handed off for that contact."""
    if not contact_id:
        return set()
    cid = str(contact_id)
    if connection_id:
        return set(handoff_map.get((str(connection_id), cid), set()))
    result: set[str] = set()
    for (_conn, mapped_cid), sdr_ids in handoff_map.items():
        if mapped_cid == cid:
            result |= sdr_ids
    return result


def active_member_ids(supabase: Any, *, company_id: Optional[str], user_ids: set[str]) -> set[str]:
    """Which of user_ids are still active members of company_id - scope=handoffs and briefs
    only surface a handoff SDR who's still on the team. Any failure here degrades to "none
    of them", never a 500."""
    if not company_id or not user_ids:
        return set()
    try:
        rows = (
            supabase.table("company_members")
            .select("user_id,status")
            .eq("company_id", company_id)
            .in_("user_id", list(user_ids))
            .execute()
        ).data or []
    except Exception:
        logger.warning("company_members active-check failed for company %s", company_id, exc_info=True)
        return set()
    return {str(row["user_id"]) for row in rows if (row.get("status") or "active") == "active"}
