"""Follow-up draft per memo: read (polled by every surface) and record the hand-off."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from supabase import Client

from app.api.memos import _require_readable_memo
from app.deps import get_membership, get_supabase, get_user_id, require_rep_workspace
from app.models.followup import FollowupActionRequest, WritingSamplesRequest
from app.services.company import Membership
from app.services.followup import schedule_followup
from app.services.followup_logic import (
    LIST_LIMIT,
    LIST_WINDOW,
    apply_action,
    clean_pasted,
    followup_view,
    is_eligible,
    listable_statuses,
    next_voice_samples,
    pasted_samples,
    pending_row,
    should_generate,
    with_pasted,
)

router = APIRouter(prefix="/api/v1/memos", tags=["followup"])
listing = APIRouter(prefix="/api/v1", tags=["followup"])


def _now() -> datetime:
    return datetime.now(timezone.utc)


@listing.get("/followups")
async def list_followups(
    status_filter: str = Query("ready", alias="status"),
    membership: Membership = Depends(get_membership),
    supabase: Client = Depends(get_supabase),
) -> list[dict]:
    """Drafts the caller wrote and has not sent. Author only, managers included: only the author sends."""
    require_rep_workspace(supabase, membership.company_id)
    try:
        wanted = listable_statuses(status_filter)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error
    rows = (
        supabase.table("memos")
        .select("id,hubspot_contact_id,extraction,followup,created_at")
        .eq("user_id", membership.user_id)
        .or_(f"company_id.eq.{membership.company_id},company_id.is.null")
        .in_("followup->>status", list(wanted))
        .neq("status", "rejected")
        .gte("created_at", (_now() - LIST_WINDOW).isoformat())
        .order("created_at", desc=True)
        .limit(LIST_LIMIT)
        .execute()
    ).data or []
    return [pending_row(memo) for memo in rows]


@router.get("/{memo_id}/followup")
async def get_followup(
    memo_id: UUID,
    supabase: Client = Depends(get_supabase),
    user_id: str = Depends(get_user_id),
) -> dict:
    memo = _require_readable_memo(supabase, str(memo_id), user_id)
    # Safety net for any path that completed an extraction without scheduling.
    scheduled = (
        is_eligible(memo)
        and should_generate(memo.get("followup"), datetime.now(timezone.utc))
        and schedule_followup(supabase, str(memo_id), company_id=memo.get("company_id"))
    )
    return followup_view(memo, scheduled=scheduled)


@router.post("/{memo_id}/followup")
async def record_followup_action(
    memo_id: UUID,
    payload: FollowupActionRequest,
    supabase: Client = Depends(get_supabase),
    user_id: str = Depends(get_user_id),
) -> dict:
    memo = _require_readable_memo(supabase, str(memo_id), user_id)
    if str(memo.get("user_id") or "") != user_id:
        # Managers can read a rep's draft; only the rep sends it, from their own mailbox.
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the memo's author can send its follow-up")
    current = memo.get("followup") or {}
    if current.get("status") not in ("ready", "sent"):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Follow-up is not ready")
    updated = apply_action(
        current,
        action=payload.action,
        channel=payload.channel,
        subject=payload.subject,
        body=payload.body,
        now=datetime.now(timezone.utc),
    )
    supabase.table("memos").update({"followup": updated}).eq("id", str(memo_id)).execute()

    samples = _writing_samples(supabase, user_id)
    learned = next_voice_samples(samples, payload.body, updated["edit_ratio"])
    if learned != samples:
        supabase.table("user_profiles").update({"writing_samples": learned}).eq("id", user_id).execute()

    return followup_view({**memo, "followup": updated})


def _writing_samples(supabase: Client, user_id: str) -> list:
    rows = supabase.table("user_profiles").select("writing_samples").eq("id", user_id).limit(1).execute().data
    return list(((rows or [{}])[0]).get("writing_samples") or [])


@listing.get("/writing-samples")
async def get_writing_samples(
    supabase: Client = Depends(get_supabase),
    user_id: str = Depends(get_user_id),
) -> dict:
    """The emails the rep pasted so the first draft already sounds like them."""
    return {"samples": pasted_samples(_writing_samples(supabase, user_id))}


@listing.put("/writing-samples")
async def put_writing_samples(
    payload: WritingSamplesRequest,
    supabase: Client = Depends(get_supabase),
    user_id: str = Depends(get_user_id),
) -> dict:
    """Replaces the pasted samples; samples learned from edits are kept."""
    try:
        pasted = clean_pasted(payload.samples)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error
    stored = _writing_samples(supabase, user_id)
    supabase.table("user_profiles").update({"writing_samples": with_pasted(stored, pasted)}).eq("id", user_id).execute()
    return {"samples": pasted}
