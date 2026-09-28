"""T13: extra reads for the manager's per-rep detail page. Adherence and objections are
already generic in aggregate.py/adherence_trend.py (user_id filter); this is only what
those two do not carry - the rep's own sales_role and its handoffs."""

from __future__ import annotations

from typing import Any, Optional


def _missing_handoffs_table(exc: BaseException) -> bool:
    """Same fallback rule as services/handoffs.py: migration 056 not applied yet degrades
    to an empty read, never a 500."""
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


def rep_in_company(supabase: Any, *, company_id: str, user_id: str) -> bool:
    """False when user_id has no company_members row in this company - a manager cannot
    fish for another company's rep by guessing their id."""
    try:
        rows = (
            supabase.table("company_members")
            .select("user_id")
            .eq("company_id", company_id)
            .eq("user_id", str(user_id))
            .limit(1)
            .execute()
        ).data or []
    except Exception:
        return True  # a failed read never turns a real rep into a 404
    return bool(rows)


def rep_sales_role(supabase: Any, *, company_id: str, user_id: str) -> Optional[str]:
    """Best-effort: None on any read failure or missing row, never an error."""
    try:
        rows = (
            supabase.table("company_members")
            .select("sales_role")
            .eq("company_id", company_id)
            .eq("user_id", str(user_id))
            .limit(1)
            .execute()
        ).data or []
    except Exception:
        return None
    return rows[0].get("sales_role") if rows else None


def _sorted_recent(rows: list[dict], *, limit: int) -> list[dict]:
    return sorted(rows, key=lambda row: str(row.get("created_at") or ""), reverse=True)[:limit]


def rep_handoffs(supabase: Any, *, company_id: str, user_id: str, limit: int = 20) -> dict:
    """All handoffs (any status) with this rep on either side, most recent first -
    'as_sdr' is what they passed on (D6), 'as_ae' is what they received (D2)."""
    try:
        sdr_rows = (
            supabase.table("deal_handoffs")
            .select("*")
            .eq("company_id", company_id)
            .eq("sdr_user_id", str(user_id))
            .execute()
        ).data or []
        ae_rows = (
            supabase.table("deal_handoffs")
            .select("*")
            .eq("company_id", company_id)
            .eq("ae_user_id", str(user_id))
            .execute()
        ).data or []
    except Exception as exc:
        if _missing_handoffs_table(exc):
            return {"as_sdr": [], "as_ae": []}
        raise
    return {"as_sdr": _sorted_recent(sdr_rows, limit=limit), "as_ae": _sorted_recent(ae_rows, limit=limit)}


def name_handoff_contacts(supabase: Any, *, company_id: str, handoffs: dict) -> dict:
    """Adds contact_name/company_name to each handoff row from the company's memos about
    that contact, so the page never shows a bare CRM id. A failed read leaves rows as
    they were (the page falls back to the id)."""
    rows = list(handoffs.get("as_sdr") or []) + list(handoffs.get("as_ae") or [])
    contact_ids = sorted({str(row.get("contact_id")) for row in rows if row.get("contact_id")})
    if not contact_ids:
        return handoffs
    try:
        memos = (
            supabase.table("memos")
            .select("id,hubspot_contact_id,extraction")
            .eq("company_id", company_id)
            .in_("hubspot_contact_id", contact_ids)
            .execute()
        ).data or []
    except Exception:
        return handoffs
    from app.services.hoy.names import memo_directory

    _by_memo, by_contact = memo_directory(memos)

    def named(row: dict) -> dict:
        found = by_contact.get(str(row.get("contact_id") or ""))
        if not found:
            return row
        name, company = found
        return {**row, "contact_name": name, "company_name": company}

    return {key: [named(row) for row in handoffs.get(key) or []] for key in ("as_sdr", "as_ae")}


def rep_name(supabase: Any, *, company_id: str, user_id: str) -> Optional[str]:
    """The rep's display name for the page title; None if not an active member."""
    from app.services.team_insights.aggregate import load_team_reps

    for rep in load_team_reps(supabase, company_id):
        if rep.get("userId") == str(user_id):
            return rep.get("name")
    return None
