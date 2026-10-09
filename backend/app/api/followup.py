"""Follow-up draft per memo: read (polled by every surface) and record the hand-off."""
from __future__ import annotations

import uuid
import asyncio
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from supabase import Client

from app.api.memos import _require_readable_memo
from app.deps import get_membership, get_supabase, get_user_id, require_rep_workspace
from app.models.followup import (
    FollowupActionRequest,
    FollowupPreference,
    FollowupSendRequest,
    FollowupSkipRequest,
    WritingSamplesRequest,
)
from app.services.company import Membership
from app.services.feature_flags import is_enabled
from app.services.followup import read_followup_preference, schedule_followup, write_followup_preference
from app.services.followup_crm_note import log_followup_note
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
    skip_followup,
    unskip_followup,
    with_pasted,
)
from app.services.followup_send import claim_send, finish_send, rate_limited, rep_identity, send_followup_email, send_hash

router = APIRouter(prefix="/api/v1/memos", tags=["followup"])
listing = APIRouter(prefix="/api/v1", tags=["followup"])

SEND_FLAG = "FOLLOWUP_SEND_ENABLED"
SENT_CHANNEL = "vocify_email"


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
    # The read runs in a thread; scheduling stays on the loop (it starts a task there).
    memo = await asyncio.to_thread(_require_readable_memo, supabase, str(memo_id), user_id)
    # Safety net for any path that completed an extraction without scheduling.
    scheduled = (
        is_eligible(memo)
        and should_generate(memo.get("followup"), datetime.now(timezone.utc))
        and schedule_followup(supabase, str(memo_id), company_id=memo.get("company_id"))
    )
    return followup_view(memo, scheduled=scheduled)


@router.post("/{memo_id}/followup/skip")
async def skip_followup_draft(
    memo_id: UUID,
    payload: FollowupSkipRequest,
    supabase: Client = Depends(get_supabase),
    user_id: str = Depends(get_user_id),
) -> dict:
    """The rep won't send this draft (or takes that back). Only the author decides."""
    memo = _require_readable_memo(supabase, str(memo_id), user_id)
    if str(memo.get("user_id") or "") != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the memo's author can skip its follow-up")
    current = memo.get("followup") or {}
    try:
        updated = unskip_followup(current) if payload.undo else skip_followup(current, _now())
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    supabase.table("memos").update({"followup": updated}).eq("id", str(memo_id)).execute()
    return followup_view({**memo, "followup": updated})


@listing.get("/followup-preference", response_model=FollowupPreference)
async def get_followup_preference(
    supabase: Client = Depends(get_supabase),
    user_id: str = Depends(get_user_id),
) -> FollowupPreference:
    return FollowupPreference(suggest=read_followup_preference(supabase, user_id))


@listing.put("/followup-preference", response_model=FollowupPreference)
async def put_followup_preference(
    payload: FollowupPreference,
    supabase: Client = Depends(get_supabase),
    user_id: str = Depends(get_user_id),
) -> FollowupPreference:
    write_followup_preference(supabase, user_id, payload.suggest)
    return payload


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


@router.post("/{memo_id}/followup/send")
async def send_followup(
    memo_id: UUID,
    payload: FollowupSendRequest,
    membership: Membership = Depends(get_membership),
    supabase: Client = Depends(get_supabase),
) -> dict:
    """D9: send the reviewed draft from Vocify via Resend, log it in the CRM, and record
    the hand-off the same way apply_action does for copy/mailto. Idempotent by memo and by
    the reviewed subject+body: resending the same revision is a no-op, an edited one sends.

    Sending is claimed atomically (claim_send) before Resend is ever called, so two
    concurrent requests for the same reviewed body cannot both send: the loser gets back
    the winner's outcome instead of a duplicate email."""
    if not is_enabled(supabase, membership.company_id, SEND_FLAG):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")
    memo = _require_readable_memo(supabase, str(memo_id), membership.user_id)
    if str(memo.get("user_id") or "") != membership.user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the memo's author can send its follow-up")
    current = memo.get("followup") or {}
    if current.get("status") not in ("ready", "sent"):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Follow-up is not ready")

    subject, body = payload.subject.strip(), payload.body.strip()
    revision = send_hash(subject, body)
    already_sent = current.get("channel") == SENT_CHANNEL and current.get("vocify_send_hash") == revision \
        and current.get("vocify_send_state") == "sent"
    if already_sent:
        # The email already went out for this exact revision. The CRM note is best-effort
        # and safe to retry on its own (never on a resend of the email itself), but only
        # while it has not already succeeded - never repeated once it has.
        if (current.get("crm_note") or {}).get("status") != "done":
            note = await log_followup_note(supabase, memo, body)
            updated = {**current, "crm_note": note}
            supabase.table("memos").update({"followup": updated}).eq("id", str(memo_id)).execute()
            return followup_view({**memo, "followup": updated})
        return followup_view(memo)

    rep_name, rep_email = rep_identity(supabase, membership.user_id)
    if not rep_email:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Rep has no email on file; cannot send a follow-up from Vocify",
        )
    if rate_limited(membership.user_id):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many follow-ups sent recently")

    run_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    claim, claimed_followup = claim_send(supabase, str(memo_id), current, revision, run_id, now)
    if claim != "claimed":
        # Another request already owns this exact revision (mid-send or already sent):
        # report its state, never send a second time.
        return followup_view({**memo, "followup": claimed_followup})

    sent = await send_followup_email(
        to=payload.to,
        subject=subject,
        body=body,
        rep_name=rep_name,
        rep_email=rep_email,
        idempotency_key=f"followup-send-{memo_id}-{revision}",
    )
    if not sent.get("ok"):
        finish_send(supabase, str(memo_id), run_id, {**current, "vocify_send_hash": revision,
                                                      "vocify_send_state": "failed"})
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=sent.get("error") or "Could not send email")

    # The sent hash is written before the CRM note is even attempted: a retry of this same
    # revision (crash, or the rep pressing send again) can only ever repair the note, never
    # resend the email.
    sent_marker = apply_action(current, action="sent", channel=SENT_CHANNEL, subject=subject, body=body, now=now)
    sent_marker["vocify_send_hash"] = revision
    sent_marker["vocify_send_state"] = "sent"
    sent_marker["vocify_send_run_id"] = run_id
    finish_send(supabase, str(memo_id), run_id, sent_marker)

    crm_note = await log_followup_note(supabase, memo, body)
    updated = {**sent_marker, "crm_note": crm_note}
    supabase.table("memos").update({"followup": updated}).eq("id", str(memo_id)).execute()

    samples = _writing_samples(supabase, membership.user_id)
    learned = next_voice_samples(samples, body, updated["edit_ratio"])
    if learned != samples:
        supabase.table("user_profiles").update({"writing_samples": learned}).eq("id", membership.user_id).execute()

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
