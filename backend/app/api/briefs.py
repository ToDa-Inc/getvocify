"""GET /briefs. Facts for one contact. Another contact's read is not reused here."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.deps import get_membership, get_supabase
from app.services.briefs.preparation import prepare_brief
from app.services.company import Membership

router = APIRouter(prefix="/api/v1", tags=["briefs"])

_LOADER = None


def set_brief_loader(loader) -> None:
    """loader(...) -> kwargs for prepare_brief. None reads memos for that contact."""
    global _LOADER
    _LOADER = loader


@router.get("/briefs")
async def get_brief(
    connection_id: str,
    contact_id: str,
    deal_id: str | None = None,
    membership: Membership = Depends(get_membership),
    supabase=Depends(get_supabase),
):
    if _LOADER is not None:
        facts = _LOADER(
            company_id=membership.company_id,
            connection_id=connection_id,
            contact_id=contact_id,
            deal_id=deal_id,
        )
    else:
        facts = _from_memos(
            supabase,
            membership.company_id,
            contact_id,
            connection_id=connection_id,
            deal_id=deal_id,
        )
    return prepare_brief(**facts)


def _from_memos(
    supabase,
    company_id: str,
    contact_id: str,
    *,
    connection_id: str | None = None,
    deal_id: str | None = None,
) -> dict:
    try:
        query = (
            supabase.table("memos")
            .select("id,created_at,extraction,hubspot_contact_id,hubspot_deal_id,matched_deal_id")
            .eq("company_id", company_id)
            .eq("hubspot_contact_id", contact_id)
            .order("created_at", desc=True)
            .limit(100)
        )
        stored = query.execute()
        rows = list(stored.data or [])
        if deal_id:
            rows = [
                row
                for row in rows
                if str(row.get("hubspot_deal_id") or "") == deal_id
                or str(row.get("matched_deal_id") or "") == deal_id
            ]
    except Exception:
        return {"coverage": "unavailable"}
    if not rows:
        return {"coverage": "complete"}
    newest = max(rows, key=lambda row: str(row.get("created_at") or ""))
    extraction = newest.get("extraction") or {}
    if not isinstance(extraction, dict):
        extraction = {}
    pending = _first_text(extraction.get("next_steps") or extraction.get("nextSteps"))
    objection = _first_text(extraction.get("objections"))
    pain = bool(extraction.get("pain_confirmed"))
    summary = extraction.get("summary") or ""
    return {
        "coverage": "complete",
        "last": {"text": summary, "observed_at": newest.get("created_at"), "source_ref": newest.get("id")},
        "pending": {"text": pending, "source_ref": newest.get("id")} if pending else None,
        "objection": {"text": objection, "source_ref": newest.get("id")} if objection else None,
        "pain_confirmed": pain,
    }


def _first_text(value) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list) and value:
        item = value[0]
        if isinstance(item, str):
            return item.strip()
        if isinstance(item, dict):
            return str(item.get("text") or item.get("subject") or "").strip()
    return ""
