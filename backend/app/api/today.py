"""GET /today. CRM tasks are not invented here, so that source stays unavailable until it is read."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from app.deps import get_membership, get_supabase, require_rep_workspace
from app.services.company import CompanyService, Membership
from app.services.feature_flags import is_enabled
from app.services.hoy.actions import ActionError, apply_action, undo_action
from app.services.hoy.confirmations import (
    CONFIRM_FLAG,
    CONFIRM_TYPE,
    clear_confirm_write_pending,
    mark_confirm_write_pending,
    schedule_confirm_write,
)
from app.services.handoffs import active_handoffs_for_ae, active_handoffs_for_sdr, close_handoff
from app.services.hoy.assigned import connection_assigned_fetch, fresh_connection
from app.services.hoy.crm_state import contact_exit_states, exit_reason, load_queue_states
from app.services.hoy.lanes import partition_by_lane
from app.services.hoy.no_reply import NO_REPLY_FLAG, refresh_no_reply
from app.services.hoy.priority import rank_candidates
from app.services.hoy.scheduler import attempt_daily_run_claim, build_today_view, collect_open_tasks, contact_record_url
from app.services.hoy.sections import SDR_NEW_CAP, SDR_SOURCE_LIMIT, hoy_sections, sections_for_role, split_items_by_type
from app.services.hoy.signals import DEFAULT_LIMIT, Signal, commitment_task_links, never_contacted_signal
from app.services.hoy.materialize import HOY_MEMO_LIMIT, as_dt, exclude_handoff_contacts, never_contacted_signals, read_hoy_memos, refresh_hoy_signals
from app.services.meetings.today import MEETING_TYPE, MEETINGS_FLAG, refresh_meeting_today
from app.services.hoy.names import NamePair, memo_directory
from app.services.hoy.upcoming import (
    DEFAULT_DAYS,
    MAX_DAYS,
    MIN_DAYS,
    local_midnight,
    upcoming_commitments,
    upcoming_followups,
    upcoming_handoff_followups,
)
from app.services.hoy.visibility import is_today_visible
from app.services.rep_timezone import rep_timezone

AE_DEALS_FLAG = "HOY_AE_DEALS_ENABLED"
SDR_SECTIONS_FLAG = "HOY_SDR_SECTIONS_ENABLED"
# Lista 4 T2: with the cadence on, followup_due replaces these two; their stored rows are
# hidden on read (not resolved), and followup_due rows are hidden with it off.
CADENCE_REPLACED_TYPES = frozenset({"going_cold", "objection_open"})
FOLLOWUP_TYPE = "followup_due"
NEVER_CONTACTED_TYPE = "never_contacted"

logger = logging.getLogger(__name__)

NO_REPLY_MAX_AGE = timedelta(hours=1)


router = APIRouter(prefix="/api/v1", tags=["today"])

_TASKS = None
_FETCH = None


def set_today_tasks(reader) -> None:
    """reader(company_id) -> (manual_tasks, coverage). None reads the connected CRM."""
    global _TASKS
    _TASKS = reader


def set_today_fetch(fetch) -> None:
    """fetch(request) -> CRM page. None uses the connection token."""
    global _FETCH
    _FETCH = fetch


_NO_REPLY_FETCH = None
_NO_REPLY_REP_EMAIL = None
_NO_REPLY_RUNS: dict[tuple[str, str], tuple[datetime, str]] = {}
_NO_REPLY_REFRESHING: set[tuple[str, str]] = set()


def set_no_reply_fetch(factory) -> None:
    """factory(connection) -> fetch(request). None uses the connection token with 429 retries."""
    global _NO_REPLY_FETCH
    _NO_REPLY_FETCH = factory


def set_no_reply_rep_email(loader) -> None:
    """loader(supabase, company_id, user_id) -> email. None reads Supabase auth."""
    global _NO_REPLY_REP_EMAIL
    _NO_REPLY_REP_EMAIL = loader


def reset_no_reply_runs() -> None:
    _NO_REPLY_RUNS.clear()
    _NO_REPLY_REFRESHING.clear()


def _rep_email(supabase, company_id: str, user_id: str) -> str | None:
    if _NO_REPLY_REP_EMAIL is not None:
        return _NO_REPLY_REP_EMAIL(supabase, company_id, user_id)
    return CompanyService(supabase)._auth_emails_by_ids([user_id]).get(user_id) or None


def _live_connection(supabase, company_id: str) -> dict | None:
    stored = (
        supabase.table("crm_connections")
        .select("id,status,provider,access_token,refresh_token,token_expires_at,metadata,company_id")
        .eq("company_id", company_id)
        .execute()
    )
    return next((row for row in stored.data or [] if row.get("status") == "connected"), None)


def _lazy_fetch(factory, connection: dict):
    built: list = []

    def fetch(request: dict) -> dict:
        if not built:
            built.append(factory(connection))
        return built[0](request)

    return fetch


def _refresh_no_reply_sync(supabase, company_id: str, user_id: str, connection: dict, now: datetime, tz_name: str) -> str:
    hubspot = str(connection.get("provider") or "").lower() == "hubspot"
    result = refresh_no_reply(
        supabase,
        company_id=company_id,
        user_id=user_id,
        rep_email=_rep_email(supabase, company_id, user_id) if hubspot else None,
        connection=connection,
        fetch=_lazy_fetch(_NO_REPLY_FETCH or connection_assigned_fetch, connection),
        now=now,
        tz_name=tz_name,
    )
    return result["coverage"]


async def _run_no_reply(supabase, company_id: str, user_id: str, now: datetime, tz_name: str) -> str:
    try:
        connection = _live_connection(supabase, company_id)
        if connection is None:
            coverage = "unavailable"
        else:
            if str(connection.get("provider") or "").lower() == "hubspot":
                connection = await fresh_connection(supabase, connection)
            coverage = await run_in_threadpool(
                _refresh_no_reply_sync, supabase, company_id, user_id, connection, now, tz_name,
            )
    except Exception:
        logger.exception("no_reply refresh failed for company %s", company_id)
        coverage = "unavailable"
    _NO_REPLY_RUNS[(company_id, user_id)] = (now, coverage)
    return coverage


async def _no_reply_behind(supabase, company_id: str, user_id: str, now: datetime, tz_name: str) -> None:
    try:
        await _run_no_reply(supabase, company_id, user_id, now, tz_name)
    finally:
        _NO_REPLY_REFRESHING.discard((company_id, user_id))


async def _no_reply_coverage(supabase, company_id: str, user_id: str, now: datetime, tz_name: str, background: BackgroundTasks) -> str:
    """First read of the process runs now. A stale one answers with the last coverage and reads after the response."""
    key = (company_id, user_id)
    cached = _NO_REPLY_RUNS.get(key)
    if cached is None:
        return await _run_no_reply(supabase, company_id, user_id, now, tz_name)
    read_at, coverage = cached
    if now - read_at >= NO_REPLY_MAX_AGE and key not in _NO_REPLY_REFRESHING:
        _NO_REPLY_REFRESHING.add(key)
        background.add_task(_no_reply_behind, supabase, company_id, user_id, now, tz_name)
    return coverage


def _connection(supabase, company_id: str) -> dict | None:
    stored = (
        supabase.table("crm_connections")
        .select("id,status,provider,access_token,metadata,company_id")
        .eq("company_id", company_id)
        .execute()
    )
    for row in stored.data or []:
        if row.get("status") == "connected":
            return row
    return None


def _http_task_page(connection: dict, request: dict, client=None) -> dict:
    import httpx

    token = connection.get("access_token")
    provider = connection.get("provider")
    if not token or provider not in {"hubspot", "pipedrive"}:
        return {"error_kind": "unavailable"}
    owns_client = client is None
    if owns_client:
        client = httpx.Client(timeout=8.0)
    try:
        if provider == "hubspot":
            response = client.post(
                "https://api.hubapi.com" + request["path"],
                headers={"Authorization": f"Bearer {token}"},
                json=request.get("json") or {},
            )
        else:
            domain = str((connection.get("metadata") or {}).get("api_domain") or "").rstrip("/")
            if not domain:
                return {"error_kind": "unavailable"}
            response = client.get(
                domain + "/api/v1" + request["path"],
                headers={"Authorization": f"Bearer {token}"},
                params=request.get("params") or {},
            )
    except httpx.TimeoutException:
        return {"error_kind": "timeout"}
    except httpx.HTTPError:
        return {"error_kind": "transport"}
    finally:
        if owns_client:
            client.close()
    if response.status_code in (401, 403):
        return {"error_kind": str(response.status_code)}
    if response.status_code >= 400:
        return {"error_kind": "transport"}
    body = response.json()
    return body if isinstance(body, dict) else {"error_kind": "transport"}


def _task_owner_id(connection: dict, user_id: str) -> str | None:
    """The rep's HubSpot owner from the connection's owner cache; None when not known."""
    if str(connection.get("provider") or "") != "hubspot":
        return None
    from app.services.hubspot.sync import owner_id_from_connection_metadata

    return owner_id_from_connection_metadata(connection.get("metadata") or {}, user_id)


def _read_tasks(connection: dict, user_id: str | None = None) -> tuple[list[dict], str]:
    provider = str(connection.get("provider") or "")
    connection_id = str(connection.get("id") or "")
    owner_id = _task_owner_id(connection, user_id) if user_id else None
    fetch = _FETCH if _FETCH is not None else (lambda request: _http_task_page(connection, request))
    try:
        tasks, coverage = collect_open_tasks(provider, fetch, connection_id=connection_id, owner_id=owner_id)
    except (ValueError, TimeoutError, OSError):
        return [], "unavailable"
    if provider == "hubspot" and _FETCH is None:
        _fill_hubspot_contacts(connection, tasks)
    return tasks, coverage


def _fill_hubspot_contacts(connection: dict, tasks: list[dict]) -> None:
    """Open the person, not the task list. A failed lookup leaves the card without a link."""
    import httpx

    token = connection.get("access_token")
    pending = [task for task in tasks if not task.get("contact_id") and task.get("remote_id")][:7]
    if not token or not pending:
        return
    try:
        with httpx.Client(timeout=8.0) as client:
            response = client.post(
                "https://api.hubapi.com/crm/v4/associations/tasks/contacts/batch/read",
                headers={"Authorization": f"Bearer {token}"},
                json={"inputs": [{"id": task["remote_id"]} for task in pending]},
            )
    except httpx.HTTPError:
        return
    if response.status_code >= 400:
        return
    found: dict[str, str] = {}
    for row in response.json().get("results") or []:
        task_id = str((row.get("from") or {}).get("id") or "")
        targets = row.get("to") or []
        object_id = targets[0].get("toObjectId") if targets else None
        if task_id and object_id is not None:
            found[task_id] = str(object_id)
    for task in tasks:
        if not task.get("contact_id"):
            task["contact_id"] = found.get(str(task.get("remote_id") or ""))


def _signal(row: dict) -> Signal:
    payload = dict(row.get("payload") or {})
    if row.get("id"):
        payload["signal_id"] = row["id"]
        payload["version"] = row.get("version")
        payload["status"] = row.get("status") or "pending"
        if row.get("undo_deadline"):
            payload["undo_deadline"] = row.get("undo_deadline")
        if row.get("last_action_request_id"):
            payload["last_action_request_id"] = row.get("last_action_request_id")
    due_at = None
    raw_due = payload.get("due_at")
    if isinstance(raw_due, str) and raw_due:
        try:
            due_at = datetime.fromisoformat(raw_due.replace("Z", "+00:00"))
        except ValueError:
            due_at = None
    return Signal(
        type=row["type"],
        contact_id=row.get("contact_id"),
        deal_id=row.get("deal_id"),
        source_memo_id=row.get("memo_id") or "",
        due_at=due_at,
        payload=payload,
        dedupe_key=row["dedupe_key"],
        connection_id=row.get("connection_id"),
    )


def _intelligence(rows: list[dict]) -> str:
    if not rows:
        return "complete"
    coverages = {row.get("coverage") or "unavailable" for row in rows}
    if coverages == {"complete"}:
        return "complete"
    return "partial"


def _sections_enabled(supabase, membership: Membership) -> bool:
    """Lista 4 T2/T8 (E7/E8, E13, E16): Hoy por bloques and the follow-up cadence, for every
    sales role - SDR (Tareas/Seguimiento/Nuevos), AE (Demos de hoy/Tareas/Seguimiento) and
    General (all four). Lead tiers (Nuevos, callbacks) stay SDR/General only."""
    return is_enabled(supabase, membership.company_id, SDR_SECTIONS_FLAG)


def _prospects(membership: Membership) -> bool:
    """SDR or General (D1: null is general): the roles lead tiers are for."""
    return membership.sales_role in (None, "sdr", "general")


def _never_contacted_for_rep(
    supabase, *, company_id: str, user_id: str, now: datetime, touched_contact_ids: set[str], limit: int = DEFAULT_LIMIT,
) -> list[Signal]:
    """T5 review: reads the contact_priorities cache only (load_context/snapshot_from_rows -
    no CRM call in-request, same source as GET /contact-priorities). Ephemeral - these cards
    are never written to action_signals, so they simply stop appearing once the cache moves
    on (a call, a memo, a CRM change) instead of needing their own reconcile pass."""
    try:
        connected, rows, _provider, _portal_id, _connection = load_context(supabase, company_id)
        snapshot = snapshot_from_rows(rows, connected=connected)
        visible = [
            row for row in snapshot.get("candidates") or []
            if not row.get("owner_ambiguous") and row.get("owner_user_id") == user_id
        ]
        ranked = rank_candidates(visible, now)
        return never_contacted_signals(ranked, touched_contact_ids=touched_contact_ids, limit=limit)
    except Exception:
        return []


def _own_deal_memos(supabase, company_id: str, user_id: str) -> list[dict]:
    """A failed read yields no own deals - the section keeps whatever handoffs give it.
    T6 review: scoped to this company, newest first, capped like every other Hoy memo
    read (HOY_MEMO_LIMIT) - the same bound meetings/today.py's own `_read_memos` uses."""
    try:
        stored = (
            supabase.table("memos")
            .select("id,user_id,hubspot_contact_id,hubspot_deal_id,created_at")
            .eq("company_id", company_id)
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .limit(HOY_MEMO_LIMIT)
            .execute()
        )
    except Exception:
        return []
    return stored.data or []


def _received_handoffs(supabase, membership: Membership) -> list[dict] | None:
    """Active handoffs where this rep is the AE. [] when handoffs do not apply (flag off,
    or an SDR): a stored handoff "Reunión hoy" card then resolves instead of lingering.
    None only when the read failed - callers treat None as "unknown", never as "none"."""
    if membership.sales_role not in (None, "ae", "general"):
        return []
    if not is_enabled(supabase, membership.company_id, "HANDOFF_ENABLED"):
        return []
    try:
        return active_handoffs_for_ae(supabase, company_id=membership.company_id, ae_user_id=membership.user_id)
    except Exception:
        return None


def _handoff_contact_memos(supabase, company_id: str, handoffs: list[dict] | None) -> list[dict] | None:
    """The handing-off SDRs' memos about the handed-off contacts - to name those contacts
    on the AE's cards and (Lista 4 T8) to time the follow-up of a handed-off contact the AE
    has not talked to yet (T4/D8 already lets the AE read exactly these memos). None when
    the read failed - callers treat it as "unknown", never as "no memos"."""
    rows = handoffs or []
    sdr_ids = sorted({str(row.get("sdr_user_id")) for row in rows if row.get("sdr_user_id")})
    contact_ids = sorted({str(row.get("contact_id")) for row in rows if row.get("contact_id")})
    if not sdr_ids or not contact_ids:
        return []
    try:
        stored = (
            supabase.table("memos")
            .select("id,user_id,hubspot_contact_id,hubspot_deal_id,extraction,capture_started_at,created_at,screening_outcome")
            .eq("company_id", company_id)
            .in_("user_id", sdr_ids)
            .in_("hubspot_contact_id", contact_ids)
            .order("created_at", desc=True)
            .limit(HOY_MEMO_LIMIT)
            .execute()
        )
    except Exception:
        return None
    return list(stored.data or [])


def _stamp_names_by_contact(items: list[dict], directory: tuple[dict, dict]) -> None:
    """Deal cards are built after the Hoy items were named; give them the same names."""
    _by_memo, by_contact = directory
    for item in items:
        if item.get("contact_name"):
            continue
        found = by_contact.get(str(item.get("contact_id") or ""))
        if not found:
            continue
        name, company = found
        if name:
            item["contact_name"] = name
        if company and not item.get("company_name"):
            item["company_name"] = company


DEAL_STAGE_DEADLINE = 3.0


async def _read_deal_stages(connection: dict, provider_name: str, deal_ids: list[str]) -> dict[str, dict]:
    """T6 review: `deal_stages_by_provider` is synchronous CRM I/O, so it runs off the
    event loop in a threadpool, under a total deadline - a slow CRM (or one that never
    answers) yields {} rather than blocking GET /today. {} reads as "unknown" everywhere
    this is used: the deal stays listed, and no handoff closes on it."""
    fetch = _FETCH if _FETCH is not None else (lambda request: _http_task_page(connection, request))
    try:
        return await asyncio.wait_for(
            run_in_threadpool(deal_stages_by_provider, fetch, provider_name, deal_ids),
            timeout=DEAL_STAGE_DEADLINE,
        )
    except Exception:
        return {}


async def _deal_items(
    supabase,
    *,
    membership: Membership,
    connection: dict | None,
    provider: str | None,
    portal_id: str | None,
    domain: str | None,
    now: datetime,
    lang: str,
    handoffs: list[dict] | None = None,
) -> list[dict]:
    """T6: the AE's (or General's) 'deals en curso' - active handoffs to them plus their
    own deals with a memo, minus whichever the CRM now shows in an end stage. A
    handed-off deal observed there closes its handoff (lazy close, D6/T3) - the only
    trigger for that."""
    company_id, user_id = membership.company_id, membership.user_id
    handoffs = list(handoffs or [])
    own = own_deal_candidates(_own_deal_memos(supabase, company_id, user_id))
    # T6 review: newest_first + the DEFAULT_LIMIT cut happens BEFORE any CRM read - a
    # company with many deals never spends a stage read on a candidate the card list
    # would fold away anyway.
    candidates = newest_first(merge_deal_candidates(handoffs, own), limit=DEFAULT_LIMIT)
    if not candidates:
        return []
    provider_name = str(provider or "")
    current_connection_id = str((connection or {}).get("id") or "")
    # T6 review: a handoff created against a different CRM connection than the one now
    # connected is never stage-read, excluded or closed here - its deal id would not even
    # resolve against this connection's API. "Own" deals carry no connection_id (memos
    # have no such column) and are always read against the single connected CRM.
    readable_ids = [
        row["deal_id"] for row in candidates
        if row.get("deal_id")
        and (row.get("source") != "handoff" or (current_connection_id and row.get("connection_id") == current_connection_id))
    ]
    stages: dict[str, dict] = {}
    if connection is not None and readable_ids:
        stages = await _read_deal_stages(connection, provider_name, readable_ids)
    for row in candidates:
        if row.get("source") != "handoff" or not row.get("deal_id"):
            continue
        if not stage_known_ended(stages, row["deal_id"], provider=provider_name):
            continue
        try:
            close_handoff(
                supabase,
                company_id=company_id,
                connection_id=str(row.get("connection_id") or ""),
                contact_id=str(row.get("contact_id") or ""),
                reason="deal_closed",
                now=now,
            )
        except Exception:
            pass
    open_candidates = [
        row for row in candidates
        if not stage_known_ended(stages, row.get("deal_id"), provider=provider_name)
    ]
    items = []
    for row in open_candidates:
        items.append({
            "type": DEAL_TYPE,
            "contact_id": row.get("contact_id"),
            "deal_id": row.get("deal_id"),
            "connection_id": row.get("connection_id"),
            "reason": deal_reason(row.get("source") or "own", lang=lang),
            "meeting_starts_at": row.get("meeting_starts_at"),
            "handoff_id": row.get("handoff_id"),
            "open_url": contact_record_url(
                provider=provider, contact_id=row.get("contact_id"), portal_id=portal_id, company_domain=domain,
            ),
        })
    return items


@router.get("/today")
async def get_today(
    background: BackgroundTasks,
    membership: Membership = Depends(get_membership),
    supabase=Depends(get_supabase),
    accept_language: str | None = Header(default=None, alias="Accept-Language"),
):
    lang = "en" if (accept_language or "").lower().startswith("en") else "es"
    now = _now()
    email_coverage = None
    if is_enabled(supabase, membership.company_id, NO_REPLY_FLAG):
        email_coverage = await _no_reply_coverage(
            supabase,
            membership.company_id,
            membership.user_id,
            now,
            rep_timezone(membership.user_id),
            background,
        )
    tz_name = rep_timezone(membership.user_id)
    # T5: lead tiers (callback_no_answer, stale_hot wording, heat) are for a SDR or General
    # rep only - the AE's Hoy is deals-focused (T6), not this list.
    # Lista 4 T2: the SDR sections are built on lead tiers (Tareas holds the callbacks, Nuevos
    # the never-contacted leads), so turning them on turns lead tiers on for that rep too.
    # Lista 4 T8: the AE gets the sections and the cadence too, never the lead tiers.
    sections_enabled = _sections_enabled(supabase, membership)
    lead_tiers_enabled = _prospects(membership) and (
        sections_enabled or is_enabled(supabase, membership.company_id, "HOY_LEAD_TIERS_ENABLED")
    )
    cadence = CompanyService(supabase).followup_cadence(membership.company_id) if sections_enabled else None
    callback_after_days = (
        CompanyService(supabase).callback_after_days(membership.company_id) if lead_tiers_enabled else None
    )
    # Handoffs this rep received (AE, or General with a route): read once, reused for their
    # follow-ups, their "Reunión hoy" cards, the contact names on those cards and the deals.
    received_handoffs = _received_handoffs(supabase, membership)
    handoff_memos = _handoff_contact_memos(supabase, membership.company_id, received_handoffs)
    if _TASKS is None:
        try:
            refresh_hoy_signals(
                supabase,
                company_id=membership.company_id,
                user_id=membership.user_id,
                now=now,
                tz_name=tz_name,
                lead_tiers_enabled=lead_tiers_enabled,
                callback_after_days=callback_after_days or 2,
                cadence=cadence,
                handoffs=received_handoffs,
                handoff_memos=handoff_memos,
            )
        except Exception:
            pass
    sales_roles = is_enabled(supabase, membership.company_id, "SALES_ROLES_ENABLED")
    team_view = sales_roles and membership.role in ("owner", "admin")
    signals_query = (
        supabase.table("action_signals")
        .select("*")
        .eq("company_id", membership.company_id)
    )
    if not team_view:
        signals_query = signals_query.eq("user_id", membership.user_id)
    stored = signals_query.execute()
    now = _now()
    confirm_enabled = is_enabled(supabase, membership.company_id, CONFIRM_FLAG)
    visible = [row for row in (stored.data or []) if is_today_visible(row, now)]
    connection = None
    if _TASKS is not None:
        manual_tasks, task_coverage = _TASKS(membership.company_id)
    else:
        connection = _connection(supabase, membership.company_id)
        if connection is None:
            manual_tasks, task_coverage = [], "unavailable"
        else:
            manual_tasks, task_coverage = _read_tasks(connection)
    states = load_queue_states(
        supabase,
        membership.company_id,
        connection_id=str(connection["id"]) if connection else None,
    )
    reason_by_contact: dict[str, Optional[str]] = {}
    if states is not None:
        try:
            context_rows = (
                supabase.table("contact_priority_context")
                .select("contact_id,payload")
                .eq("company_id", membership.company_id)
                .execute()
            )
            rows = list(context_rows.data or [])
            if sales_roles:
                for row in rows:
                    contact_id = str(row.get("contact_id") or "")
                    if not contact_id:
                        continue
                    payload = row.get("payload") or {}
                    reason_by_contact[contact_id] = exit_reason(payload.get("crm_state"), states)
            else:
                exited = contact_exit_states(rows, states)
                if exited:
                    visible = [
                        row for row in visible
                        if str(row.get("contact_id") or "") not in exited
                    ]
        except Exception:
            logger.exception("today queue-state filter failed for company %s", membership.company_id)
    calls_rows = visible
    meetings_rows: list[dict] = []
    if sales_roles:
        calls_rows, meetings_rows = partition_by_lane(
            visible,
            reason_by_contact,
            membership.sales_role,
            membership.role,
            limit=7,
        )
    attempt_daily_run_claim(supabase, membership.company_id, now, _daily_run_timezone(membership.user_id))
    meta = (connection or {}).get("metadata") or {}
    portal = meta.get("portal_id") or meta.get("hub_id") or meta.get("portalId")
    domain = str(meta.get("company_domain") or "").strip() or None
    coverage_rows = calls_rows + meetings_rows if sales_roles else visible
    coverage = {"intelligence": _intelligence(coverage_rows), "crm_tasks": task_coverage}
    if email_coverage is not None:
        coverage["crm_emails"] = email_coverage
    view_kwargs = dict(
        now=now,
        coverage=coverage,
        generated_at=now.isoformat(),
        lang=lang,
        provider=(connection or {}).get("provider"),
        portal_id=str(portal) if portal else None,
        company_domain=domain,
        task_links=task_links,
        confirm_rows=confirm_rows,
        tz_name=rep_timezone(membership.user_id),
        lead_tiers=lead_tiers_enabled,
        limit=SDR_SOURCE_LIMIT if sections_enabled else DEFAULT_LIMIT,
    )
    view = build_today_view(
        signals=[_signal(row) for row in calls_rows],
        manual_tasks=manual_tasks,
        **view_kwargs,
    )
    if sales_roles:
        for item in view.get("items") or []:
            item["lane"] = "calls"
        meetings_view = build_today_view(
            signals=[_signal(row) for row in meetings_rows],
            manual_tasks=[],
            **view_kwargs,
        )
        for item in meetings_view.get("items") or []:
            item["lane"] = "meetings"
        view["items"] = list(view.get("items") or []) + list(meetings_view.get("items") or [])
        _stamp_booking_memo_ids(view, supabase, membership.company_id)
        if team_view:
            _stamp_rep_names(view, calls_rows + meetings_rows, _member_display_names(supabase, membership.company_id))
    stamp_rows = calls_rows + meetings_rows if sales_roles else visible
    _stamp_contact_names(view, stamp_rows, _memo_directory(supabase, membership.user_id))
    return view


def _user_memos(supabase, user_id: str) -> list[dict]:
    """A failed read leaves cards unnamed and CRM tasks unlinked."""
    try:
        stored = (
            supabase.table("memos")
            .select("id,user_id,hubspot_contact_id,extraction")
            .eq("user_id", user_id)
            .execute()
        )
    except Exception:
        return []
    return stored.data or []


def _memo_directory(supabase, user_id: str) -> tuple[dict[str, NamePair], dict[str, NamePair]]:
    """Names already extracted on the memo. A failed read leaves the card unnamed."""
    return memo_directory(_user_memos(supabase, user_id))


def _dialled_numbers(supabase, view: dict) -> dict[str, str]:
    """The number dialled for each unanswered-call card still without a name. Never raises."""
    ids = [
        str(item.get("dedupe_key"))[len("callback:call:"):] for item in view.get("items") or []
        if not item.get("contact_name") and str(item.get("dedupe_key") or "").startswith("callback:call:")
    ]
    if not ids:
        return {}
    try:
        rows = supabase.table("outbound_calls").select("id,to_number").in_("id", ids).execute().data or []
    except Exception:
        return {}
    return {str(row["id"]): str(row["to_number"]) for row in rows if row.get("to_number")}


def _stamp_contact_names(view: dict, signals: list[dict], directory: tuple[dict, dict], dialled: dict | None = None) -> None:
    by_memo, by_contact = directory
    row_by_key = {row.get("dedupe_key"): row for row in signals if row.get("dedupe_key")}
    for item in view.get("items") or []:
        row = row_by_key.get(item.get("dedupe_key")) or {}
        memo_id = row.get("memo_id")
        found = by_memo.get(str(memo_id)) if memo_id else None
        name, company = found if found else (None, None)
        if not name:
            found = by_contact.get(str(item.get("contact_id") or ""))
            if found:
                name, company = found
        if not name and not item.get("contact_name"):
            # A call nobody answered has no memo to name it: the number dialled is better than "Contacto".
            name = str((row.get("payload") or {}).get("phone") or "").strip() or (dialled or {}).get(
                str(item.get("dedupe_key") or "").removeprefix("callback:call:")
            ) or None
        if name:
            item["contact_name"] = name
        if company:
            item["company_name"] = company


def _member_display_names(supabase, company_id: str) -> dict[str, str]:
    try:
        members = CompanyService(supabase).list_members(company_id)
    except Exception:
        logger.exception("today rep names failed for company %s", company_id)
        return {}
    names: dict[str, str] = {}
    for member in members:
        user_id = str(member.get("user_id") or "")
        if not user_id:
            continue
        label = _clean_name(member.get("full_name")) or _clean_name(member.get("email"))
        if label:
            names[user_id] = label
    return names


def _stamp_rep_names(view: dict, signals: list[dict], names: dict[str, str]) -> None:
    if not names:
        return
    row_by_key = {row.get("dedupe_key"): row for row in signals if row.get("dedupe_key")}
    for item in view.get("items") or []:
        row = row_by_key.get(item.get("dedupe_key")) or {}
        user_id = str(row.get("user_id") or "")
        label = names.get(user_id)
        if label:
            item["rep_name"] = label


def _stamp_booking_memo_ids(view: dict, supabase, company_id: str) -> None:
    contact_ids = sorted({
        str(item.get("contact_id") or "")
        for item in (view.get("items") or [])
        if item.get("lane") == "meetings" and item.get("contact_id")
    })
    if not contact_ids:
        return
    try:
        stored = (
            supabase.table("memos")
            .select("id,hubspot_contact_id,created_at")
            .eq("company_id", company_id)
            .in_("hubspot_contact_id", contact_ids)
            .order("created_at", desc=True)
            .execute()
        )
    except Exception:
        logger.exception("today booking memo lookup failed for company %s", company_id)
        return
    latest: dict[str, str] = {}
    for memo in stored.data or []:
        contact_id = str(memo.get("hubspot_contact_id") or "")
        memo_id = memo.get("id")
        if contact_id and memo_id and contact_id not in latest:
            latest[contact_id] = str(memo_id)
    for item in view.get("items") or []:
        if item.get("lane") != "meetings":
            continue
        memo_id = latest.get(str(item.get("contact_id") or ""))
        if memo_id:
            item["booking_memo_id"] = memo_id


_CLOCK_DEFAULT = datetime.now(timezone.utc)
_CLOCK = [_CLOCK_DEFAULT]


def _now() -> datetime:
    return datetime.now(timezone.utc) if _CLOCK[0] is _CLOCK_DEFAULT else _CLOCK[0]


@router.get("/today/upcoming")
async def get_today_upcoming(
    days: int = Query(DEFAULT_DAYS),
    membership: Membership = Depends(get_membership),
    supabase=Depends(get_supabase),
    accept_language: str | None = Header(default=None, alias="Accept-Language"),
):
    require_rep_workspace(supabase, membership.company_id)
    if not MIN_DAYS <= days <= MAX_DAYS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"days must be between {MIN_DAYS} and {MAX_DAYS}",
        )
    now = _now()
    tz_name = rep_timezone(membership.user_id)
    sections_enabled = _sections_enabled(supabase, membership)
    memos = read_hoy_memos(
        supabase, company_id=membership.company_id, user_id=membership.user_id, with_followup=sections_enabled,
    )
    rows = upcoming_commitments(memos, now=now, tz_name=tz_name, days=days)
    if not sections_enabled:
        return rows
    # Lista 4 T2/T8 (E8, E13): the follow-ups the cadence is holding back, on the date they
    # return - the rep's own, and (AE/General) handed-off contacts not talked to yet.
    lang = "en" if (accept_language or "").lower().startswith("en") else "es"
    overrides = CompanyService(supabase).followup_cadence(membership.company_id)
    rows += upcoming_followups(memos, now=now, tz_name=tz_name, days=days, overrides=overrides, lang=lang)
    handoffs = _received_handoffs(supabase, membership)
    handoff_memos = _handoff_contact_memos(supabase, membership.company_id, handoffs)
    if handoffs and handoff_memos:
        rows += upcoming_handoff_followups(
            handoffs,
            handoff_memos,
            own_contact_ids={str(memo.get("hubspot_contact_id") or "") for memo in memos} - {""},
            now=now,
            tz_name=tz_name,
            days=days,
            overrides=overrides,
            lang=lang,
        )
    rows.sort(key=lambda row: (as_dt(row["due_at"]), row["memo_id"]))
    return rows


@router.get("/today/done")
async def get_today_done(membership: Membership = Depends(get_membership), supabase=Depends(get_supabase)):
    require_rep_workspace(supabase, membership.company_id)
    now = _now()
    tz_name = rep_timezone(membership.user_id)
    since = local_midnight(now, tz_name).isoformat()
    signals = (
        supabase.table("action_signals")
        .select("*")
        .eq("company_id", membership.company_id)
        .eq("user_id", membership.user_id)
        .gte("last_action_at", since)
        .execute()
    )
    # sent_at is always written as UTC isoformat, so the text comparison on the JSON field holds.
    followups = (
        supabase.table("memos")
        .select("id,hubspot_contact_id,followup")
        .eq("user_id", membership.user_id)
        .or_(f"company_id.eq.{membership.company_id},company_id.is.null")
        .gte("followup->>sent_at", since)
        .execute()
    )
    calls = (
        supabase.table("outbound_calls")
        .select("memo_id,hubspot_contact_id,call_disposition,answered_at,created_at")
        .eq("user_id", membership.user_id)
        .gte("created_at", since)
        .execute()
    )
    return done_today(
        signals=signals.data or [],
        followups=followups.data or [],
        calls=calls.data or [],
        names=_memo_directory(supabase, membership.user_id),
        now=now,
        tz_name=tz_name,
    )


class ResolveBody(BaseModel):
    action: str
    request_id: str
    expected_version: int
    until: Optional[datetime] = None


class UndoBody(BaseModel):
    request_id: str
    expected_version: int


def _load(supabase, signal_id: str, membership: Membership) -> dict | None:
    stored = (
        supabase.table("action_signals")
        .select("*")
        .eq("id", signal_id)
        .eq("company_id", membership.company_id)
        .eq("user_id", membership.user_id)
        .execute()
    )
    rows = stored.data or []
    return rows[0] if rows else None


def _public(row: dict) -> dict:
    return {
        "id": row.get("id"),
        "status": row.get("status"),
        "version": row.get("version"),
        "undo_deadline": row.get("undo_deadline"),
        "previous_status": row.get("previous_status"),
    }


def _conflict(row: dict) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=_public(row))


class NeverContactedBody(BaseModel):
    contact_id: str
    connection_id: Optional[str] = None


@router.post("/today/never-contacted")
async def persist_never_contacted(
    body: NeverContactedBody,
    membership: Membership = Depends(get_membership),
    supabase=Depends(get_supabase),
):
    """T5 cards for never-contacted leads are computed on the fly and carry no id, so the
    rep could not snooze, dismiss or disqualify them. The first action persists the card
    as a normal action_signals row (idempotent per contact) and returns its id/version;
    the client then resolves it through POST /today/{id}/resolve like any other card,
    with the same undo window. GET /today hides a persisted row once the lead has a
    conversation (see _drop_touched_never_contacted)."""
    contact_id = (body.contact_id or "").strip()
    if not contact_id:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="contact_id requerido")
    connection_id = (body.connection_id or "").strip()
    signal = never_contacted_signal(contact_id=contact_id, connection_id=connection_id or None)

    def _existing() -> dict | None:
        rows = (
            supabase.table("action_signals")
            .select("*")
            .eq("company_id", membership.company_id)
            .eq("user_id", membership.user_id)
            .eq("dedupe_key", signal.dedupe_key)
            .execute()
        ).data or []
        return rows[0] if rows else None

    row = _existing()
    if row is None:
        supabase.table("action_signals").upsert(
            {
                "company_id": membership.company_id,
                "user_id": membership.user_id,
                "connection_id": connection_id,
                "contact_id": contact_id,
                "deal_id": None,
                "memo_id": None,
                "type": NEVER_CONTACTED_TYPE,
                "dedupe_key": signal.dedupe_key,
                "payload": {},
                "status": "pending",
                "coverage": "complete",
            },
            on_conflict="company_id,user_id,connection_id,dedupe_key",
            ignore_duplicates=True,
        ).execute()
        row = _existing()
    if row is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="No se pudo guardar la tarjeta")
    return _public(row)


def _drop_touched_never_contacted(rows: list[dict], touched: set[str]) -> list[dict]:
    """A persisted never_contacted card stops being true once the lead has a conversation."""
    return [
        row for row in rows
        if not (row.get("type") == NEVER_CONTACTED_TYPE and str(row.get("contact_id") or "") in touched)
    ]


@router.post("/today/{signal_id}/resolve")
async def resolve_today(signal_id: str, body: ResolveBody, membership: Membership = Depends(get_membership), supabase=Depends(get_supabase)):
    row = _load(supabase, signal_id, membership)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Señal no encontrada")
    if body.action == "confirm":
        if not is_enabled(supabase, membership.company_id, CONFIRM_FLAG):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Señal no encontrada")
        if row.get("type") != CONFIRM_TYPE:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Acción no válida")
    try:
        result = apply_action(
            row,
            action=body.action,
            request_id=body.request_id,
            expected_version=body.expected_version,
            until=body.until,
            now=_now(),
            user_id=membership.user_id,
            company_id=membership.company_id,
        )
    except ActionError as error:
        if error.code == "conflict":
            raise _conflict(error.row) from error
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Acción no válida") from error
    if not result["replayed"]:
        update_payload: dict = {
            "status": result["status"],
            "version": result["version"],
            "previous_status": result["previous_status"],
            "last_action_request_id": result["last_action_request_id"],
            "last_action_at": result["last_action_at"],
            "undo_deadline": result["undo_deadline"],
            "snoozed_until": result["snoozed_until"],
        }
        if body.action == "confirm":
            update_payload["payload"] = mark_confirm_write_pending(dict(row.get("payload") or {}))
        elif body.action == "disqualify":
            # T3: "Descalificar" - resolved, with the reason kept for reporting (T5/T12).
            update_payload["payload"] = {**dict(row.get("payload") or {}), "resolution_reason": "disqualified"}
        saved = (
            supabase.table("action_signals")
            .update(update_payload)
            .eq("id", signal_id)
            .eq("company_id", membership.company_id)
            .eq("user_id", membership.user_id)
            .eq("version", row["version"])
            .execute()
        )
        if not (saved.data or []):
            current = _load(supabase, signal_id, membership) or row
            raise _conflict(current)
        result = saved.data[0]
        if body.action == "confirm":
            schedule_confirm_write(supabase, signal_id, result.get("undo_deadline"))
    return _public(result)


@router.patch("/today/{signal_id}")
async def undo_today(signal_id: str, body: UndoBody, membership: Membership = Depends(get_membership), supabase=Depends(get_supabase)):
    row = _load(supabase, signal_id, membership)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Señal no encontrada")
    try:
        result = undo_action(
            row,
            request_id=body.request_id,
            expected_version=body.expected_version,
            now=_now(),
            user_id=membership.user_id,
            company_id=membership.company_id,
        )
    except ActionError as error:
        if error.code == "expired":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"reason": "undo_expired", **_public(error.row)}) from error
        if error.code == "conflict":
            raise _conflict(error.row) from error
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Señal no encontrada") from error
    undo_update: dict = {
        "status": result["status"],
        "version": result["version"],
        "previous_status": result["previous_status"],
        "undo_deadline": None,
        "snoozed_until": None,
    }
    if row.get("type") == CONFIRM_TYPE:
        undo_update["payload"] = clear_confirm_write_pending(dict(row.get("payload") or {}))
    saved = (
        supabase.table("action_signals")
        .update(undo_update)
        .eq("id", signal_id)
        .eq("company_id", membership.company_id)
        .eq("user_id", membership.user_id)
        .eq("version", row["version"])
        .execute()
    )
    if not (saved.data or []):
        current = _load(supabase, signal_id, membership) or row
        raise _conflict(current)
    return _public(saved.data[0])
