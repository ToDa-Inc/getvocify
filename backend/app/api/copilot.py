"""Live call objection copilot API."""

from __future__ import annotations

import json
from typing import Literal, Optional

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from supabase import Client

from app.api.briefs import _handoff_restricted_user_ids
from app.deps import get_membership, get_supabase
from app.services.company import Membership
from app.services.copilot.contact_history import load_contact_history
from app.services.copilot.context import live_assist_kind_from_call_mode, resolve_suggest_context
from app.services.copilot import call_type, turn
from app.services.copilot.checklist import build_meeting_checklist
from app.services.copilot.load_grounding import (
    load_company_knowledge,
    load_company_suggest_grounding,
    load_suggest_grounding,
)
from app.services.copilot.suggest import silent_suggestion, stream_objection_suggestion
from app.services.playbooks.catalog import INTERNAL_KEY

router = APIRouter(prefix="/api/v1/copilot", tags=["copilot"])


class ChecklistRequest(BaseModel):
    call_mode: Literal["speakerphone", "softphone", "meeting"] = "meeting"
    capture_id: Optional[str] = Field(default=None, max_length=128)
    input_revision: Optional[str] = Field(default=None, max_length=128)
    elapsed_seconds: Optional[float] = Field(default=None, ge=0)
    finalized_turns: Optional[list[dict]] = Field(default=None)


class SuggestRequest(BaseModel):
    transcript_window: str = Field(..., max_length=20000)
    latest_turn: str = Field(..., max_length=4000)
    product_context: Optional[str] = Field(default=None, max_length=8000)
    language: Literal["auto", "en", "es"] = "auto"
    call_mode: Literal["speakerphone", "softphone", "meeting"] = "speakerphone"
    speaker_role: Literal["prospect", "rep", "unknown"] = "unknown"
    capture_id: Optional[str] = Field(default=None, max_length=128)
    contact_id: Optional[str] = Field(default=None, max_length=128)
    request_id: Optional[str] = Field(default=None, max_length=128)
    # The call's type, decided once for the call (Vocify's guess or proposal, or the rep's pick).
    sales_motion_key: Optional[str] = Field(default=None, max_length=64)
    # The objection the turn check already put on screen: the answer is written for it.
    objection_type: Optional[str] = Field(default=None, max_length=32)


class TurnRequest(BaseModel):
    transcript_window: str = Field(..., max_length=20000)
    latest_turn: str = Field(..., max_length=4000)
    sales_motion_key: Optional[str] = Field(default=None, max_length=64)


class CallTypeGuessRequest(BaseModel):
    interaction_kind: Literal["call", "meeting"] = "meeting"
    contact_id: Optional[str] = Field(default=None, max_length=128)


class CallTypeOption(BaseModel):
    key: str = Field(..., max_length=64)
    label: str = Field(..., max_length=200)


class CallTypeProposeRequest(BaseModel):
    transcript_window: str = Field(..., max_length=20000)
    options: list[CallTypeOption] = Field(default_factory=list, max_length=50)


def _empty_objection(event: dict) -> bool:
    """A result that flags an objection with no line to say: shown, it would vanish at once."""
    suggestion = event.get("suggestion") or {}
    return suggestion.get("is_objection") is True and not str(suggestion.get("say_this") or "").strip()


def _sse(events: list[dict]) -> StreamingResponse:
    body = "".join(f"data: {json.dumps(event, ensure_ascii=False)}\n\n" for event in events)
    return StreamingResponse(iter([body]), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


@router.post("/checklist")
async def meeting_playbook_checklist(
    body: ChecklistRequest,
    membership: Membership = Depends(get_membership),
    supabase: Client = Depends(get_supabase),
):
    """Return playbook step progress for a meeting from stored observations only."""
    del body.input_revision, body.finalized_turns, body.elapsed_seconds
    return build_meeting_checklist(
        supabase,
        user_id=membership.user_id,
        company_id=membership.company_id,
        call_mode=body.call_mode,
        capture_id=body.capture_id,
    )


@router.post("/suggest")
async def suggest_objection_handling(
    body: SuggestRequest,
    membership: Membership = Depends(get_membership),
    supabase: Client = Depends(get_supabase),
):
    """Stream a structured objection-handling suggestion (SSE)."""
    motion = (body.sales_motion_key or "").strip() or None
    if motion == INTERNAL_KEY:
        # No customer in the conversation: no help, and no model call.
        return _sse([{"type": "result", "suggestion": silent_suggestion()}, {"type": "done"}])

    product_context = (body.product_context or "").strip()
    if not product_context:
        # Desktop meetings don't carry the offer; use the one the rep saved for extraction.
        from app.services.extraction_context import load_product_context

        product_context = load_product_context(supabase, membership.user_id)

    context = resolve_suggest_context(
        body.contact_id,
        call_mode=body.call_mode,
    )
    if motion and not body.capture_id:
        grounding = call_type.grounding_for_type(
            supabase, membership.company_id, motion, live_assist_kind_from_call_mode(body.call_mode),
        )
    elif body.capture_id:
        grounding = load_suggest_grounding(
            supabase,
            user_id=membership.user_id,
            company_id=membership.company_id,
            capture_id=body.capture_id,
            context=context,
        )
    else:
        grounding = load_company_suggest_grounding(
            supabase,
            company_id=membership.company_id,
            call_mode=body.call_mode,
            context=context,
            user_id=membership.user_id,
        )

    company_knowledge = load_company_knowledge(supabase, company_id=membership.company_id)
    contact_history = None
    if context.contact_id:
        contact_history = await load_contact_history(
            supabase,
            company_id=membership.company_id,
            contact_id=context.contact_id,
            # Same memo visibility as the pre-call brief for this contact.
            allowed_user_ids=_handoff_restricted_user_ids(
                supabase, membership, connection_id=None, contact_id=context.contact_id,
            ),
        )

    def ask(with_grounding):
        return stream_objection_suggestion(
            transcript_window=body.transcript_window,
            latest_turn=body.latest_turn,
            product_context=product_context or None,
            language=body.language,
            call_mode=body.call_mode,
            speaker_role=body.speaker_role,
            grounding=with_grounding,
            context=context,
            company_knowledge=company_knowledge,
            contact_history=contact_history,
            objection_type=body.objection_type if body.objection_type in turn.OBJECTIONS else None,
        )

    def sse(event: dict) -> str:
        if event.get("type") == "result":
            if body.capture_id:
                event = {**event, "capture_id": body.capture_id}
            if body.request_id:
                event = {**event, "request_id": body.request_id}
        return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    async def event_gen():
        async for event in ask(grounding):
            if event.get("type") == "result" and grounding is not None and _empty_objection(event):
                # The playbook can make the model flag an objection and say nothing: ask once more
                # without it, as general help. The client drops what it streamed so far.
                yield sse({"type": "restart"})
                async for retry in ask(None):
                    yield sse(retry)
                break
            yield sse(event)
        yield "data: {\"type\": \"done\"}\n\n"

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/turn")
async def check_turn(
    body: TurnRequest,
    membership: Membership = Depends(get_membership),
):
    """About 0.3 s: has the prospect finished, and which objection is it. Nulls mean no classifier."""
    del membership
    if (body.sales_motion_key or "").strip() == INTERNAL_KEY:
        return {"finished": True, "objection": "none"}
    return await turn.read_turn(body.transcript_window, body.latest_turn)


@router.post("/call-type/guess")
async def guess_call_type(
    body: CallTypeGuessRequest,
    membership: Membership = Depends(get_membership),
    supabase: Client = Depends(get_supabase),
):
    """The type to start a live call with, at no model cost."""
    key, source = call_type.provisional_type(
        call_type.last_contact_type(supabase, membership.company_id, body.contact_id),
        call_type.rule_type(supabase, membership.company_id, membership.user_id, body.interaction_kind, body.contact_id),
        call_type.published_keys(supabase, membership.company_id),
    )
    return {"type": key, "source": source}


@router.post("/call-type/propose")
async def propose_call_type(
    body: CallTypeProposeRequest,
    membership: Membership = Depends(get_membership),
    supabase: Client = Depends(get_supabase),
):
    """One model call: the published type the conversation so far points to."""
    labels = {option.key: option.label for option in body.options}
    proposal = await call_type.propose(supabase, membership.company_id, body.transcript_window, labels)
    return {"type": proposal[0], "confident": proposal[1]} if proposal else {"type": None, "confident": False}


@router.get("/health")
async def copilot_health():
    return {"ok": True, "feature": "objection-copilot"}
