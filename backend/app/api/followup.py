"""Follow-up draft per memo: read (polled by every surface) and record the hand-off."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from supabase import Client

from app.api.memos import _require_readable_memo
from app.deps import get_supabase, get_user_id
from app.models.followup import FollowupActionRequest
from app.services.followup import schedule_followup
from app.services.followup_logic import (
    apply_action,
    followup_view,
    is_eligible,
    next_voice_samples,
    should_generate,
)

router = APIRouter(prefix="/api/v1/memos", tags=["followup"])


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
        and schedule_followup(supabase, str(memo_id))
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

    rows = supabase.table("user_profiles").select("writing_samples").eq("id", user_id).limit(1).execute().data
    samples = list(((rows or [{}])[0]).get("writing_samples") or [])
    learned = next_voice_samples(samples, payload.body, updated["edit_ratio"])
    if learned != samples:
        supabase.table("user_profiles").update({"writing_samples": learned}).eq("id", user_id).execute()

    return followup_view({**memo, "followup": updated})
