"""Playbook insights (Fase 3): per-step compliance and objection frequencies of a playbook's
motion, from the team's scored calls. Managers only: a member is rejected before any read."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse

from app.deps import get_membership, get_supabase
from app.services.coaching.rep_coaching_reads import load_published_playbook
from app.services.company import Membership
from app.services.coaching.crm_meetings import apply_rep_meetings
from app.services.playbooks.insights import build_insights, consider_memos
from app.services.team_insights.aggregate import _TEAM_ROLES, _paged, _paged_in, load_team_reps
from app.services.team_insights.period import period_windows

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/playbooks", tags=["playbooks"])

# capture_started_at <= created_at, so created_at >= start - margin loses no call.
_CAPTURE_MARGIN = timedelta(days=1)
_MEMO_COLUMNS = (
    "id,user_id,company_id,sales_motion_key,screening_outcome,audio_duration,capture_started_at,created_at,"
    "hubspot_contact_id,hubspot_deal_id,extraction"
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _load_memos(supabase, company_id: str, member_ids: list[str], motion: str, since: datetime) -> list[dict]:
    """Every memo of this motion created since `since`, paged (PostgREST caps a response).
    Scoped like team adherence: the company's members' memos (older ones have no company_id),
    or the company's own memos when the member list is unavailable."""

    columns = [_MEMO_COLUMNS + ",rep_outcome"]  # rep_outcome (migration 062) when the column exists

    def build():
        query = (
            supabase.table("memos")
            .select(columns[0])
            .eq("sales_motion_key", motion)
            .gte("created_at", since.isoformat())
        )
        if member_ids:
            query = query.in_("user_id", member_ids).or_(f"company_id.eq.{company_id},company_id.is.null")
        else:
            query = query.eq("company_id", company_id)
        return query.order("created_at").order("id")

    try:
        memos = _paged(build)
    except Exception:
        columns[0] = _MEMO_COLUMNS
        memos = _paged(build)
    # The meeting step is settled by what the rep declared, as in their own coaching.
    return apply_rep_meetings(supabase, memos)


@router.get("/{sales_motion_key}/insights")
def get_playbook_insights(
    sales_motion_key: str,
    period: Literal["week", "month"] = Query("week"),
    membership: Membership = Depends(get_membership),
    supabase=Depends(get_supabase),
):
    # 403 before any read: members (even with team visibility) never see these numbers.
    if membership.role not in _TEAM_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No puedes ver el equipo")
    window, _previous = period_windows(period, now=_now())
    # Head of Sales pages do not count managers' own calls (they do not sell).
    member_ids = [
        str(rep["userId"])
        for rep in load_team_reps(supabase, membership.company_id, exclude_managers=True)
        if rep.get("userId")
    ]
    playbook = load_published_playbook(supabase, membership.company_id, sales_motion_key)
    try:
        candidates = _load_memos(
            supabase, membership.company_id, member_ids, sales_motion_key, window.start - _CAPTURE_MARGIN
        )
        considered = consider_memos(candidates, motion=sales_motion_key, start=window.start, end=window.end)
        pattern_rows = _paged_in(
            supabase,
            "interaction_patterns",
            "memo_id,category,kind,resolution,response,superseded,created_at",
            "memo_id",
            [str(memo["id"]) for memo in considered],
            ("memo_id", "pattern_id", "input_revision"),
        )
    except Exception:
        logger.warning("playbook insights: read failed", exc_info=True)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="No se pudieron leer las llamadas")
    return JSONResponse(
        build_insights(
            period=period,
            memos=considered,
            pattern_rows=pattern_rows,
            steps=playbook["steps"],
            entries=playbook["entries"],
            start=window.start,
            end=window.end,
            motion=sales_motion_key,
        )
    )
