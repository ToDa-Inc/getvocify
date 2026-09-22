"""GET /contact-priorities. Rows are the cached context, not a separate snapshot."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query

from app.deps import get_membership
from app.services.company import Membership
from app.services.hoy.context import build_priority_page, snapshot_from_rows

router = APIRouter(prefix="/api/v1", tags=["contact-priorities"])

# company_id -> rows shaped like contact_priority_context. Tests fill this; a live reader can replace it.
_ROWS: dict[str, list[dict]] = {}
_CONNECTED: set[str] = set()
_CLOCK = [datetime.now(timezone.utc)]


def _now() -> datetime:
    return _CLOCK[0]


@router.get("/contact-priorities")
async def list_contact_priorities(
    membership: Membership = Depends(get_membership),
    limit: int = Query(default=20, ge=1, le=50),
    cursor: str | None = None,
):
    if membership.company_id not in _CONNECTED:
        snapshot = {"connected": False, "coverage": "unavailable", "candidates": []}
    else:
        snapshot = snapshot_from_rows(_ROWS.get(membership.company_id) or [], connected=True)
    return build_priority_page(
        snapshot=snapshot,
        user_id=membership.user_id,
        role=membership.role,
        now=_now(),
        limit=limit,
        cursor=cursor,
    )
