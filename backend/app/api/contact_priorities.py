"""GET /contact-priorities. A missing CRM is not an empty complete list."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query

from app.deps import get_membership
from app.services.company import Membership
from app.services.hoy.context import build_priority_page

router = APIRouter(prefix="/api/v1", tags=["contact-priorities"])

# Keyed by company and user. The table in 042 is the durable shape; this process cache is what the route reads today.
_SNAPSHOTS: dict[tuple[str, str], dict] = {}


def _now() -> datetime:
    return datetime.now(timezone.utc)


@router.get("/contact-priorities")
async def list_contact_priorities(
    membership: Membership = Depends(get_membership),
    limit: int = Query(default=20, ge=1, le=50),
    cursor: str | None = None,
):
    snapshot = _SNAPSHOTS.get((membership.company_id, membership.user_id))
    if snapshot is None:
        snapshot = {"connected": False, "coverage": "unavailable", "candidates": []}
    return build_priority_page(
        snapshot=snapshot,
        user_id=membership.user_id,
        role=membership.role,
        now=_now(),
        limit=limit,
        cursor=cursor,
    )
