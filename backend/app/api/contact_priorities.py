"""GET /contact-priorities. Reads contact_priority_context for the caller's company."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query

from app.deps import get_membership, get_supabase
from app.services.company import CompanyService, Membership
from app.services.hoy.assigned import connection_assigned_fetch
from app.services.hoy.context import (
    build_priority_page,
    load_context,
    maybe_refresh_assigned_context,
    snapshot_from_rows,
)

router = APIRouter(prefix="/api/v1", tags=["contact-priorities"])

_CLOCK = [datetime.now(timezone.utc)]
_ASSIGNED_FETCH: Callable[[dict], Callable[[dict], dict]] | None = None
_FOLD_MEMBERS: Callable[[object, str], list[dict]] | None = None


def set_assigned_fetch_factory(factory: Callable[[dict], Callable[[dict], dict]] | None) -> None:
    global _ASSIGNED_FETCH
    _ASSIGNED_FETCH = factory


def set_fold_members(loader: Callable[[object, str], list[dict]] | None) -> None:
    global _FOLD_MEMBERS
    _FOLD_MEMBERS = loader


def _now() -> datetime:
    return _CLOCK[0]


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


@router.get("/contact-priorities")
async def list_contact_priorities(
    membership: Membership = Depends(get_membership),
    supabase=Depends(get_supabase),
    limit: int = Query(default=20, ge=1, le=50),
    cursor: str | None = None,
):
    connected, rows, provider, portal_id, connection = load_context(supabase, membership.company_id)
    fetch_hint = None
    if connected and connection is not None:
        factory = _ASSIGNED_FETCH or connection_assigned_fetch
        rows, fetch_hint = maybe_refresh_assigned_context(
            supabase,
            membership.company_id,
            connection,
            rows,
            _fold_members(supabase, membership.company_id),
            observed_at=_observed_at(_now()),
            fetch_factory=factory,
        )
    if not connected:
        snapshot = {"connected": False, "coverage": "unavailable", "candidates": []}
    elif fetch_hint is not None:
        snapshot = {**fetch_hint, "provider": provider, "portal_id": portal_id}
    else:
        snapshot = snapshot_from_rows(rows, connected=True)
        snapshot["provider"] = provider
        snapshot["portal_id"] = portal_id
    return build_priority_page(
        snapshot=snapshot,
        user_id=membership.user_id,
        role=membership.role,
        now=_now(),
        limit=limit,
        cursor=cursor,
    )
