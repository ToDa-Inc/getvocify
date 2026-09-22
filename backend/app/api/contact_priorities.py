"""GET /contact-priorities. Reads contact_priority_context for the caller's company."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query

from app.deps import get_membership, get_supabase
from app.services.company import Membership
from app.services.hoy.context import build_priority_page, load_context, snapshot_from_rows

router = APIRouter(prefix="/api/v1", tags=["contact-priorities"])

_CLOCK = [datetime.now(timezone.utc)]


def _now() -> datetime:
    return _CLOCK[0]


@router.get("/contact-priorities")
async def list_contact_priorities(
    membership: Membership = Depends(get_membership),
    supabase=Depends(get_supabase),
    limit: int = Query(default=20, ge=1, le=50),
    cursor: str | None = None,
):
    connected, rows, provider, portal_id = load_context(supabase, membership.company_id)
    if not connected:
        snapshot = {"connected": False, "coverage": "unavailable", "candidates": []}
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
