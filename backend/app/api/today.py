"""GET /today. CRM tasks are not invented here, so that source stays unavailable until it is read."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from app.deps import get_membership, get_supabase
from app.services.company import Membership
from app.services.hoy.scheduler import build_today_view
from app.services.hoy.signals import Signal

router = APIRouter(prefix="/api/v1", tags=["today"])


def _signal(row: dict) -> Signal:
    return Signal(
        type=row["type"],
        contact_id=row.get("contact_id"),
        deal_id=row.get("deal_id"),
        source_memo_id=row.get("memo_id") or "",
        due_at=None,
        payload=dict(row.get("payload") or {}),
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
    return build_today_view(
        signals=[_signal(row) for row in visible],
        manual_tasks=[],
        now=now,
        coverage={"intelligence": _intelligence(visible), "crm_tasks": "unavailable"},
        generated_at=now.isoformat(),
    )
