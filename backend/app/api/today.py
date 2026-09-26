"""GET /today. CRM tasks are not invented here, so that source stays unavailable until it is read."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from app.deps import get_membership, get_supabase, require_rep_workspace
from app.services.company import CompanyService, Membership
from app.services.coaching.brief_preferences import read_preference
from app.services.feature_flags import is_enabled
from app.services.hoy.actions import ActionError, apply_action, undo_action
from app.services.hoy.assigned import connection_assigned_fetch, fresh_connection
from app.services.hoy.done import done_today
from app.services.hoy.no_reply import NO_REPLY_FLAG, refresh_no_reply
from app.services.hoy.scheduler import attempt_daily_run_claim, build_today_view, collect_open_tasks
from app.services.hoy.signals import Signal
from app.services.hoy.materialize import read_hoy_memos
from app.services.hoy.names import NamePair, memo_directory
from app.services.hoy.upcoming import DEFAULT_DAYS, MAX_DAYS, MIN_DAYS, local_midnight, upcoming_commitments
from app.services.hoy.visibility import is_today_visible

logger = logging.getLogger(__name__)

_DEFAULT_HOY_TZ = "Europe/Madrid"
NO_REPLY_MAX_AGE = timedelta(hours=1)


def _daily_run_timezone(user_id: str) -> str:
    try:
        tz = read_preference(user_id).get("timezone")
        if tz:
            return tz
    except Exception:
        pass
    return _DEFAULT_HOY_TZ

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


def _read_tasks(connection: dict) -> tuple[list[dict], str]:
    provider = str(connection.get("provider") or "")
    connection_id = str(connection.get("id") or "")
    fetch = _FETCH if _FETCH is not None else (lambda request: _http_task_page(connection, request))
    try:
        tasks, coverage = collect_open_tasks(provider, fetch, connection_id=connection_id)
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
            _daily_run_timezone(membership.user_id),
            background,
        )
    if _TASKS is None:
        try:
            from app.services.hoy.materialize import refresh_hoy_signals

            refresh_hoy_signals(
                supabase,
                company_id=membership.company_id,
                user_id=membership.user_id,
                now=now,
                tz_name=_daily_run_timezone(membership.user_id),
            )
        except Exception:
            pass
    stored = (
        supabase.table("action_signals")
        .select("*")
        .eq("company_id", membership.company_id)
        .eq("user_id", membership.user_id)
        .execute()
    )
    now = _now()
    visible = [row for row in (stored.data or []) if is_today_visible(row, now)]
    attempt_daily_run_claim(supabase, membership.company_id, now, _daily_run_timezone(membership.user_id))
    connection = None
    if _TASKS is not None:
        manual_tasks, task_coverage = _TASKS(membership.company_id)
    else:
        connection = _connection(supabase, membership.company_id)
        if connection is None:
            manual_tasks, task_coverage = [], "unavailable"
        else:
            manual_tasks, task_coverage = _read_tasks(connection)
    meta = (connection or {}).get("metadata") or {}
    portal = meta.get("portal_id") or meta.get("hub_id") or meta.get("portalId")
    domain = str(meta.get("company_domain") or "").strip() or None
    coverage = {"intelligence": _intelligence(visible), "crm_tasks": task_coverage}
    if email_coverage is not None:
        coverage["crm_emails"] = email_coverage
    view = build_today_view(
        signals=[_signal(row) for row in visible],
        manual_tasks=manual_tasks,
        now=now,
        coverage=coverage,
        generated_at=now.isoformat(),
        lang=lang,
        provider=(connection or {}).get("provider"),
        portal_id=str(portal) if portal else None,
        company_domain=domain,
    )
    _stamp_contact_names(view, visible, _memo_directory(supabase, membership.user_id))
    return view


def _memo_directory(supabase, user_id: str) -> tuple[dict[str, NamePair], dict[str, NamePair]]:
    """Names already extracted on the memo. A failed read leaves the card unnamed."""
    try:
        stored = (
            supabase.table("memos")
            .select("id,user_id,hubspot_contact_id,extraction")
            .eq("user_id", user_id)
            .execute()
        )
    except Exception:
        return {}, {}
    return memo_directory(stored.data or [])


def _stamp_contact_names(view: dict, signals: list[dict], directory: tuple[dict, dict]) -> None:
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
        if name:
            item["contact_name"] = name
        if company:
            item["company_name"] = company


_CLOCK_DEFAULT = datetime.now(timezone.utc)
_CLOCK = [_CLOCK_DEFAULT]


def _now() -> datetime:
    return datetime.now(timezone.utc) if _CLOCK[0] is _CLOCK_DEFAULT else _CLOCK[0]


@router.get("/today/upcoming")
async def get_today_upcoming(
    days: int = Query(DEFAULT_DAYS),
    membership: Membership = Depends(get_membership),
    supabase=Depends(get_supabase),
):
    require_rep_workspace(supabase, membership.company_id)
    if not MIN_DAYS <= days <= MAX_DAYS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"days must be between {MIN_DAYS} and {MAX_DAYS}",
        )
    now = _now()
    return upcoming_commitments(
        read_hoy_memos(supabase, company_id=membership.company_id, user_id=membership.user_id),
        now=now,
        tz_name=_daily_run_timezone(membership.user_id),
        days=days,
    )


@router.get("/today/done")
async def get_today_done(membership: Membership = Depends(get_membership), supabase=Depends(get_supabase)):
    require_rep_workspace(supabase, membership.company_id)
    now = _now()
    tz_name = _daily_run_timezone(membership.user_id)
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


@router.post("/today/{signal_id}/resolve")
async def resolve_today(signal_id: str, body: ResolveBody, membership: Membership = Depends(get_membership), supabase=Depends(get_supabase)):
    row = _load(supabase, signal_id, membership)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Señal no encontrada")
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
        saved = (
            supabase.table("action_signals")
            .update({
                "status": result["status"],
                "version": result["version"],
                "previous_status": result["previous_status"],
                "last_action_request_id": result["last_action_request_id"],
                "last_action_at": result["last_action_at"],
                "undo_deadline": result["undo_deadline"],
                "snoozed_until": result["snoozed_until"],
            })
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
    saved = (
        supabase.table("action_signals")
        .update({
            "status": result["status"],
            "version": result["version"],
            "previous_status": result["previous_status"],
            "undo_deadline": None,
            "snoozed_until": None,
        })
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
