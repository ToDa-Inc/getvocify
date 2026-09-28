"""Head of Sales team dashboard API."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, Query
from supabase import Client

from app.deps import get_supabase, get_user_id
from app.services.company import CompanyService
from app.services.team_metrics import (
    build_team_metrics,
    fetch_calls,
    filter_members,
    resolve_periods,
    useful_call_seconds_from,
)

router = APIRouter(prefix="/api/v1/team", tags=["team"])


@router.get("/metrics")
async def get_team_metrics(
    period: Literal["week", "month", "last_30", "quarter"] = Query("month"),
    sales_role: Literal["all", "sdr", "ae"] = Query("all"),
    user_id: str = Depends(get_user_id),
    supabase: Client = Depends(get_supabase),
):
    """Team activity for the period vs the comparable previous stretch.

    Owners and admins only: this is the whole team's activity.
    """
    svc = CompanyService(supabase)
    membership = svc.require_manage_role(user_id)
    members = svc.list_members(membership.company_id)
    shown = filter_members(members, sales_role)
    current, previous = resolve_periods(period, datetime.now(timezone.utc))
    calls = fetch_calls(
        supabase,
        [str(m["user_id"]) for m in shown],
        since=previous.start,
        until=current.end,
    )
    payload = build_team_metrics(
        members=members,
        calls=calls,
        current=current,
        previous=previous,
        useful_call_seconds=useful_call_seconds_from(
            svc.get_sales_settings(membership.company_id)
        ),
        sales_role=sales_role,
    )
    return {"preset": period, "generated_at": datetime.now(timezone.utc).isoformat(), **payload}
