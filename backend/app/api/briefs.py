"""GET /briefs. Facts for one contact. Another contact's read is not reused here."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from app.deps import get_membership, get_supabase
from app.services.briefs.preparation import prepare_brief
from app.services.briefs.v2 import prepare_brief_v2
from app.services.company import Membership
from app.services.feature_flags import is_enabled
from app.services.playbooks.versions import get_published_playbook
from app.services.hoy.no_reply import NO_REPLY_FLAG
from app.services.hoy.reasons import reason as hoy_reason
from app.services.hoy.signals import Signal
from app.services.rep_timezone import rep_timezone

router = APIRouter(prefix="/api/v1", tags=["briefs"])

BRIEF_V2_FLAG = "BRIEF_V2_ENABLED"
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
        return prepare_brief(**facts)

    rows, coverage = _read_memos(
        supabase,
        membership.company_id,
        contact_id,
        connection_id=connection_id,
        deal_id=deal_id,
    )
    if is_enabled(supabase, membership.company_id, BRIEF_V2_FLAG):
        steps, entries = _playbook_for_memo(supabase, membership.company_id, rows)
        now = datetime.now(timezone.utc)
        return prepare_brief_v2(
            coverage=coverage,
            memos=rows,
            tz_name=rep_timezone(membership.user_id),
            now=now,
            no_reply=_pending_no_reply(
                supabase,
                membership.company_id,
                membership.user_id,
                contact_id,
            ),
            crm_task=_open_crm_task(supabase, membership, contact_id, connection_id),
            playbook_steps=steps,
            playbook_entries=entries,
        )
    return prepare_brief(**_legacy_facts(rows, coverage=coverage))


def _read_memos(
    supabase,
    company_id: str,
    contact_id: str,
    *,
    connection_id: str | None = None,
    deal_id: str | None = None,
) -> tuple[list[dict], str]:
    del connection_id
    try:
        query = (
            supabase.table("memos")
            .select(
                "id,created_at,capture_started_at,extraction,hubspot_contact_id,hubspot_deal_id,"
                "matched_deal_id,playbook_version_id,sales_motion_key,user_id,company_id",
            )
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
        return [], "unavailable"
    return rows, "complete"


def _legacy_facts(rows: list[dict], *, coverage: str = "complete") -> dict:
    if coverage == "unavailable":
        return {"coverage": "unavailable"}
    if not rows:
        return {"coverage": "complete"}
    newest = max(rows, key=lambda row: str(row.get("created_at") or ""))
    extraction = newest.get("extraction") or {}
    if not isinstance(extraction, dict):
        extraction = {}
    pending = _first_text(extraction.get("next_steps") or extraction.get("nextSteps"))
    objection = _first_text(extraction.get("objections"))
    intelligence = extraction.get("intelligence") if isinstance(extraction.get("intelligence"), dict) else {}
    pain = intelligence.get("pain_confirmed") is True or extraction.get("pain_confirmed") is True
    summary = extraction.get("summary") or ""
    return {
        "coverage": coverage,
        "last": {"text": summary, "observed_at": newest.get("created_at"), "source_ref": newest.get("id")},
        "pending": {"text": pending, "source_ref": newest.get("id")} if pending else None,
        "objection": {"text": objection, "source_ref": newest.get("id")} if objection else None,
        "pain_confirmed": pain,
    }


def _from_memos(
    supabase,
    company_id: str,
    contact_id: str,
    *,
    connection_id: str | None = None,
    deal_id: str | None = None,
) -> dict:
    rows, coverage = _read_memos(
        supabase,
        company_id,
        contact_id,
        connection_id=connection_id,
        deal_id=deal_id,
    )
    return _legacy_facts(rows, coverage=coverage)


def _playbook_for_memo(supabase, company_id: str, rows: list[dict]) -> tuple[list[dict], list[dict]]:
    if not rows:
        return [], []
    newest = max(rows, key=lambda row: str(row.get("created_at") or ""))
    version_id = str(newest.get("playbook_version_id") or "").strip() or None
    extraction = newest.get("extraction") if isinstance(newest.get("extraction"), dict) else {}
    intelligence = extraction.get("intelligence") if isinstance(extraction.get("intelligence"), dict) else {}
    motion = str(intelligence.get("sales_motion_key") or newest.get("sales_motion_key") or "").strip() or None
    if not version_id and not motion:
        return [], []
    try:
        query = supabase.table("playbooks").select("id,company_id,sales_motion_key,active_version_id")
        query = query.eq("company_id", company_id)
        if motion:
            query = query.eq("sales_motion_key", motion)
        result = query.limit(1).execute()
        playbooks = list(getattr(result, "data", None) or [])
        if not playbooks:
            return [], []
        playbook = playbooks[0]
        versions = (
            supabase.table("playbook_versions")
            .select("id,status,steps,entries")
            .eq("playbook_id", playbook["id"])
            .execute()
        )
        snapshot = get_published_playbook(
            playbook,
            list(getattr(versions, "data", None) or []),
            version_id=version_id,
        )
        if not snapshot:
            return [], []
        return list(snapshot.get("steps") or []), list(snapshot.get("entries") or [])
    except Exception:
        return [], []


def _pending_no_reply(
    supabase,
    company_id: str,
    user_id: str,
    contact_id: str,
) -> dict | None:
    if not is_enabled(supabase, company_id, NO_REPLY_FLAG):
        return None
    try:
        stored = (
            supabase.table("action_signals")
            .select("id,payload,type,contact_id,source_memo_id")
            .eq("company_id", company_id)
            .eq("user_id", user_id)
            .eq("contact_id", contact_id)
            .eq("type", "no_reply")
            .eq("status", "pending")
            .limit(1)
            .execute()
        )
        rows = list(getattr(stored, "data", None) or [])
    except Exception:
        return None
    if not rows:
        return None
    row = rows[0]
    signal = Signal(
        "no_reply",
        contact_id=contact_id,
        deal_id=None,
        source_memo_id=str(row.get("source_memo_id") or ""),
        due_at=None,
        payload=row.get("payload") or {},
        dedupe_key="",
    )
    text = hoy_reason(signal, lang="es")
    return {"text": text, "source_ref": row.get("id"), "observed_at": None}


def _open_crm_task(supabase, membership: Membership, contact_id: str, connection_id: str | None) -> dict | None:
    del supabase, membership, contact_id, connection_id
    return None


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
