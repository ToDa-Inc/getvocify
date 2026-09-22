"""GET /today. CRM tasks are not invented here, so that source stays unavailable until it is read."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.deps import get_membership, get_supabase
from app.services.company import Membership
from app.services.hoy.actions import ActionError, apply_action, undo_action
from app.services.hoy.scheduler import build_today_view, collect_open_tasks
from app.services.hoy.signals import Signal

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
        return collect_open_tasks(provider, fetch, connection_id=connection_id)
    except (ValueError, TimeoutError, OSError):
        return [], "unavailable"


def _signal(row: dict) -> Signal:
    payload = dict(row.get("payload") or {})
    if row.get("id"):
        payload["signal_id"] = row["id"]
        payload["version"] = row.get("version")
        payload["status"] = row.get("status") or "pending"
    return Signal(
        type=row["type"],
        contact_id=row.get("contact_id"),
        deal_id=row.get("deal_id"),
        source_memo_id=row.get("memo_id") or "",
        due_at=None,
        payload=payload,
        dedupe_key=row["dedupe_key"],
        connection_id=row.get("connection_id"),
    )


def _intelligence(rows: list[dict]) -> str:
    if not rows:
        return "unavailable"
    coverages = {row.get("coverage") or "unavailable" for row in rows}
    if coverages == {"complete"}:
        return "complete"
    return "partial"


@router.get("/today")
async def get_today(membership: Membership = Depends(get_membership), supabase=Depends(get_supabase)):
    stored = (
        supabase.table("action_signals")
        .select("*")
        .eq("company_id", membership.company_id)
        .eq("user_id", membership.user_id)
        .execute()
    )
    visible = [row for row in (stored.data or []) if row.get("status") == "pending"]
    now = datetime.now(timezone.utc)
    if _TASKS is not None:
        manual_tasks, task_coverage = _TASKS(membership.company_id)
    else:
        connection = _connection(supabase, membership.company_id)
        if connection is None:
            manual_tasks, task_coverage = [], "unavailable"
        else:
            manual_tasks, task_coverage = _read_tasks(connection)
    return build_today_view(
        signals=[_signal(row) for row in visible],
        manual_tasks=manual_tasks,
        now=now,
        coverage={"intelligence": _intelligence(visible), "crm_tasks": task_coverage},
        generated_at=now.isoformat(),
    )


_CLOCK = [datetime.now(timezone.utc)]


def _now() -> datetime:
    return _CLOCK[0]


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
