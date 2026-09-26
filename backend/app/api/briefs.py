"""GET /briefs. Facts for one contact. Another contact's read is not reused here."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from starlette.concurrency import run_in_threadpool

from app.deps import get_membership, get_supabase
from app.services.briefs.contact_read import ContactProfileReadFailed, read_contact_profile, set_contact_profile_reader
from app.services.briefs.preparation import legacy_facts, prepare_brief
from app.services.briefs.v2 import prepare_brief_v2
from app.services.company import Membership
from app.services.feature_flags import is_enabled
from app.services.playbooks.versions import get_published_playbook
from app.services.hoy.no_reply import NO_REPLY_FLAG
from app.services.hoy.context import build_priority_page, load_context, snapshot_from_rows
from app.services.hoy.reasons import priority_reason_text, reason as hoy_reason
from app.services.hoy.signals import Signal
from app.services.rep_timezone import rep_timezone

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["briefs"])

BRIEF_V2_FLAG = "BRIEF_V2_ENABLED"
_LOADER = None
_TASKS = None
_PROFILE = None


class _ReadFailed(Exception):
    """A sub-read that failed. The brief keeps the verified lines and says it is partial."""


def set_brief_loader(loader) -> None:
    """loader(...) -> kwargs for prepare_brief. None reads memos for that contact."""
    global _LOADER
    _LOADER = loader


def set_brief_tasks(reader) -> None:
    """reader(company_id) -> (open_tasks, coverage). None reads the connected CRM like Hoy does."""
    global _TASKS
    _TASKS = reader


def set_brief_profile_reader(reader) -> None:
    """reader(connection, contact_id) -> profile dict. None reads the live CRM profile."""
    global _PROFILE
    _PROFILE = reader
    set_contact_profile_reader(reader)


def _now() -> datetime:
    return datetime.now(timezone.utc)


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

    if not is_enabled(supabase, membership.company_id, BRIEF_V2_FLAG):
        return prepare_brief(**_from_memos(
            supabase,
            membership.company_id,
            contact_id,
            connection_id=connection_id,
            deal_id=deal_id,
        ))

    rows, coverage = _read_memos(
        supabase,
        membership.company_id,
        contact_id,
        connection_id=connection_id,
        deal_id=deal_id,
    )
    tz_name = rep_timezone(membership.user_id)
    if coverage == "unavailable":
        return prepare_brief_v2(coverage=coverage, memos=[], tz_name=tz_name)

    complete = True
    cold_profile = None
    hoy_why = None
    motion = None
    now = _now()

    if not rows:
        try:
            cold_profile = await run_in_threadpool(
                _read_contact_profile, supabase, membership.company_id, connection_id, contact_id,
            )
        except _ReadFailed:
            cold_profile, complete = None, False
        try:
            hoy_why = _hoy_priority_why(
                supabase,
                membership.company_id,
                membership.user_id,
                contact_id,
                tz_name,
                created_at=(cold_profile or {}).get("created_at"),
            )
        except _ReadFailed:
            hoy_why, complete = None, False
        motion = str((cold_profile or {}).get("sales_motion_key") or "").strip() or None
        try:
            steps, entries = _playbook_for_motion(supabase, membership.company_id, motion)
        except _ReadFailed:
            steps, entries, complete = [], [], False
        no_reply = None
    else:
        try:
            steps, entries = _playbook_for_memo(supabase, membership.company_id, rows)
        except _ReadFailed:
            steps, entries, complete = [], [], False
        try:
            no_reply = _pending_no_reply(supabase, membership.company_id, membership.user_id, contact_id)
        except _ReadFailed:
            no_reply, complete = None, False

    try:
        crm_task = await run_in_threadpool(_open_crm_task, supabase, membership.company_id, contact_id)
    except _ReadFailed:
        crm_task, complete = None, False

    return prepare_brief_v2(
        coverage=coverage if complete else "partial",
        memos=rows,
        tz_name=tz_name,
        now=now,
        no_reply=no_reply,
        crm_task=crm_task,
        playbook_steps=steps,
        playbook_entries=entries,
        cold_profile=cold_profile,
        hoy_why=hoy_why,
        sales_motion_key=motion,
    )


def _read_memos(
    supabase,
    company_id: str,
    contact_id: str,
    *,
    connection_id: str | None = None,
    deal_id: str | None = None,
) -> tuple[list[dict], str]:
    """memos has no CRM connection column; the contact id and the company scope the read."""
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
    return legacy_facts(rows, coverage=coverage)


def _playbook_for_memo(supabase, company_id: str, rows: list[dict]) -> tuple[list[dict], list[dict]]:
    """The published playbook of the newest memo's sales motion. No motion, no playbook."""
    if not rows:
        return [], []
    newest = max(rows, key=lambda row: str(row.get("created_at") or ""))
    version_id = str(newest.get("playbook_version_id") or "").strip() or None
    extraction = newest.get("extraction") if isinstance(newest.get("extraction"), dict) else {}
    intelligence = extraction.get("intelligence") if isinstance(extraction.get("intelligence"), dict) else {}
    motion = str(intelligence.get("sales_motion_key") or newest.get("sales_motion_key") or "").strip() or None
    if not motion:
        return [], []
    try:
        result = (
            supabase.table("playbooks")
            .select("id,company_id,sales_motion_key,active_version_id")
            .eq("company_id", company_id)
            .eq("sales_motion_key", motion)
            .limit(1)
            .execute()
        )
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
    except Exception as exc:
        logger.warning("brief playbook read failed", extra={"company_id": company_id}, exc_info=True)
        raise _ReadFailed from exc
    if not snapshot:
        return [], []
    return list(snapshot.get("steps") or []), list(snapshot.get("entries") or [])


def _pending_no_reply(
    supabase,
    company_id: str,
    user_id: str,
    contact_id: str,
) -> dict | None:
    """The pending Hoy «no te ha respondido» signal for this contact, as Hoy words it."""
    if not is_enabled(supabase, company_id, NO_REPLY_FLAG):
        return None
    try:
        stored = (
            supabase.table("action_signals")
            .select("id,payload,type,contact_id,memo_id")
            .eq("company_id", company_id)
            .eq("user_id", user_id)
            .eq("contact_id", contact_id)
            .eq("type", "no_reply")
            .eq("status", "pending")
            .limit(1)
            .execute()
        )
        rows = list(getattr(stored, "data", None) or [])
        if not rows:
            return None
        row = rows[0]
        signal = Signal(
            "no_reply",
            contact_id=contact_id,
            deal_id=None,
            source_memo_id=str(row.get("memo_id") or ""),
            due_at=None,
            payload=row.get("payload") or {},
            dedupe_key="",
        )
        text = hoy_reason(signal, lang="es")
    except Exception as exc:
        logger.warning("brief no_reply read failed", extra={"company_id": company_id}, exc_info=True)
        raise _ReadFailed from exc
    return {"text": text, "source_ref": row.get("id"), "observed_at": None}


def _open_crm_task(supabase, company_id: str, contact_id: str) -> dict | None:
    """The contact's first open CRM task, from the same read Hoy uses. No connection is nothing to read."""
    try:
        if _TASKS is not None:
            tasks, coverage = _TASKS(company_id)
        else:
            from app.api.today import _connection, _read_tasks

            connection = _connection(supabase, company_id)
            if connection is None:
                return None
            tasks, coverage = _read_tasks(connection)
    except Exception as exc:
        logger.warning("brief crm task read failed", extra={"company_id": company_id}, exc_info=True)
        raise _ReadFailed from exc
    for task in tasks:
        title = " ".join(str(task.get("title") or "").split())
        if str(task.get("contact_id") or "") == contact_id and title:
            return {"text": title, "source_ref": task.get("remote_id"), "observed_at": None}
    if coverage in {"unavailable", "forbidden"}:
        raise _ReadFailed(coverage)
    return None


def _crm_connection(supabase, company_id: str, connection_id: str | None) -> dict | None:
    stored = (
        supabase.table("crm_connections")
        .select("id,status,company_id,provider,metadata,access_token,refresh_token,token_expires_at")
        .eq("company_id", company_id)
        .execute()
    )
    rows = list(getattr(stored, "data", None) or [])
    live = [row for row in rows if row.get("status") == "connected"]
    if connection_id:
        match = next((row for row in live if str(row.get("id") or "") == connection_id), None)
        if match:
            return match
    return live[0] if live else None


def _read_contact_profile(supabase, company_id: str, connection_id: str, contact_id: str) -> dict | None:
    connection = _crm_connection(supabase, company_id, connection_id)
    if connection is None:
        if _PROFILE is not None:
            connection = {"id": connection_id, "provider": connection_id, "company_id": company_id}
        else:
            return None
    try:
        return read_contact_profile(connection, contact_id)
    except ContactProfileReadFailed as exc:
        logger.warning("brief contact profile read failed", extra={"company_id": company_id}, exc_info=True)
        raise _ReadFailed from exc


def _hoy_priority_why(
    supabase,
    company_id: str,
    user_id: str,
    contact_id: str,
    tz_name: str,
    *,
    created_at,
) -> dict | None:
    try:
        connected, rows, _provider, _portal, _connection = load_context(supabase, company_id)
        if not connected:
            return None
        snapshot = snapshot_from_rows(rows, connected=True)
        page = build_priority_page(snapshot=snapshot, user_id=user_id, role="member", now=_now())
        match = next((item for item in page.get("items") or [] if str(item.get("contact_id") or "") == contact_id), None)
        if not match:
            return None
        text = priority_reason_text(
            str(match.get("reason") or ""),
            created_at=created_at,
            tz_name=tz_name,
        )
        if not text:
            return None
        return {"text": text, "source_ref": match.get("id"), "observed_at": match.get("observed_at")}
    except Exception as exc:
        logger.warning("brief priority read failed", extra={"company_id": company_id}, exc_info=True)
        raise _ReadFailed from exc


def _playbook_for_motion(supabase, company_id: str, motion: str | None) -> tuple[list[dict], list[dict]]:
    if not motion:
        return [], []
    try:
        result = (
            supabase.table("playbooks")
            .select("id,company_id,sales_motion_key,active_version_id")
            .eq("company_id", company_id)
            .eq("sales_motion_key", motion)
            .limit(1)
            .execute()
        )
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
        snapshot = get_published_playbook(playbook, list(getattr(versions, "data", None) or []))
    except Exception as exc:
        logger.warning("brief cold playbook read failed", extra={"company_id": company_id}, exc_info=True)
        raise _ReadFailed from exc
    if not snapshot:
        return [], []
    return list(snapshot.get("steps") or []), list(snapshot.get("entries") or [])
