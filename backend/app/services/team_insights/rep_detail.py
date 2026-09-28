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
