"""GET /contact-priorities. Reads contact_priority_context for the caller's company."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from starlette.concurrency import run_in_threadpool

from app.deps import get_membership, get_supabase
from app.services.company import CompanyService, Membership
from app.services.hoy.assigned import connection_assigned_fetch, fresh_connection
from app.services.hoy.context import (
    build_priority_page,
    is_stale,
    load_context,
    maybe_refresh_assigned_context,
    snapshot_from_rows,
)
from app.services.hoy.memo_facts import apply_memo_facts, load_memo_facts

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["contact-priorities"])

_CLOCK_DEFAULT = datetime.now(timezone.utc)
_CLOCK = [_CLOCK_DEFAULT]
_ASSIGNED_FETCH: Callable[[dict], Callable[[dict], dict]] | None = None
_FOLD_MEMBERS: Callable[[object, str], list[dict]] | None = None
_REFRESHING: set[str] = set()


def set_assigned_fetch_factory(factory: Callable[[dict], Callable[[dict], dict]] | None) -> None:
    global _ASSIGNED_FETCH
    _ASSIGNED_FETCH = factory


def set_fold_members(loader: Callable[[object, str], list[dict]] | None) -> None:
    global _FOLD_MEMBERS
    _FOLD_MEMBERS = loader


def _now() -> datetime:
    return datetime.now(timezone.utc) if _CLOCK[0] is _CLOCK_DEFAULT else _CLOCK[0]


def _observed_at(now: datetime) -> str:
    stamp = now if now.tzinfo else now.replace(tzinfo=timezone.utc)
    return stamp.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _fold_members(supabase, company_id: str) -> list[dict]:
    if _FOLD_MEMBERS is not None:
        return _FOLD_MEMBERS(supabase, company_id)
    members = CompanyService(supabase).list_members(company_id)
    return [
        {"user_id": member["user_id"], "email": member.get("email"), "name": member.get("full_name")}
        for member in members
        if member.get("status") == "active"
    ]


async def _refresh(supabase, company_id: str, connection: dict, rows: list[dict], observed_at: str):
    connection = await fresh_connection(supabase, connection)
    return await run_in_threadpool(
        maybe_refresh_assigned_context,
        supabase,
        company_id,
        connection,
        rows,
        _fold_members(supabase, company_id),
        observed_at=observed_at,
        fetch_factory=_ASSIGNED_FETCH or connection_assigned_fetch,
    )


async def _refresh_behind(supabase, company_id: str, connection: dict, rows: list[dict], observed_at: str) -> None:
    try:
        await _refresh(supabase, company_id, connection, rows, observed_at)
    except Exception:
        logger.exception("contact priority refresh failed for company %s", company_id)
    finally:
        _REFRESHING.discard(company_id)


def _with_memo_facts(supabase, company_id: str, user_id: str, snapshot: dict, now: datetime) -> dict:
    candidates = snapshot.get("candidates") or []
    mine = [str(row["contact_id"]) for row in candidates if row.get("owner_user_id") == user_id]
    if not mine:
        return snapshot
    try:
        facts = load_memo_facts(supabase, company_id, mine, now=now)
    except Exception as exc:
        logger.warning("memo facts unavailable for company %s: %s", company_id, exc)
        return snapshot
    return {**snapshot, "candidates": apply_memo_facts(candidates, facts)}


@router.get("/contact-priorities")
async def list_contact_priorities(
    background: BackgroundTasks,
    membership: Membership = Depends(get_membership),
    supabase=Depends(get_supabase),
    limit: int = Query(default=20, ge=1, le=50),
    cursor: str | None = None,
):
    """An empty cache is read now. A stale one answers at once and is refreshed after the response."""
    company_id = membership.company_id
    connected, rows, provider, portal_id, connection = load_context(supabase, company_id)
    fetch_hint = None
    refreshing = False
    now = _now()
    if connected and connection is not None:
        observed_at = _observed_at(now)
        if not rows:
            rows, fetch_hint = await _refresh(supabase, company_id, connection, rows, observed_at)
        elif is_stale(rows, observed_at):
            refreshing = True
            if company_id not in _REFRESHING:
                _REFRESHING.add(company_id)
                background.add_task(_refresh_behind, supabase, company_id, connection, list(rows), observed_at)
    if not connected:
        snapshot = {"connected": False, "coverage": "unavailable", "candidates": []}
    elif fetch_hint is not None:
        snapshot = {**fetch_hint, "provider": provider, "portal_id": portal_id}
    else:
        snapshot = snapshot_from_rows(rows, connected=True)
        snapshot["provider"] = provider
        snapshot["portal_id"] = portal_id
        snapshot = await run_in_threadpool(_with_memo_facts, supabase, company_id, membership.user_id, snapshot, now)
    page = build_priority_page(
        snapshot=snapshot,
        user_id=membership.user_id,
        role=membership.role,
        now=now,
        limit=limit,
        cursor=cursor,
    )
    return {**page, "stale": refreshing}
