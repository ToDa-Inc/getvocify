"""Live call objection copilot API."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, replace
from typing import Annotated, Literal, Optional

from fastapi import APIRouter, BackgroundTasks, Depends
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask
from pydantic import BaseModel, Field
from supabase import Client

from app.api.briefs import _handoff_restricted_user_ids
from app.deps import get_membership, get_supabase, get_user_id
from app.services.company import Membership
from app.services.copilot.contact_history import load_contact_history
from app.services.copilot.context import live_assist_kind_from_call_mode, resolve_suggest_context
from app.services.copilot import call_type, events, live_context, playbook_objections, turn
from app.services.copilot.checklist import build_meeting_checklist
from app.services.copilot.load_grounding import (
    load_company_knowledge,
    load_company_suggest_grounding,
    load_suggest_grounding,
)
from app.services.copilot.prompts import today_line
from app.services.copilot.grounding import SuggestGrounding
from app.services.copilot.suggest import silent_suggestion, stream_objection_suggestion
from app.services.rep_timezone import DEFAULT_TZ, rep_timezone
from app.services.playbooks.catalog import INTERNAL_KEY

logger = logging.getLogger(__name__)

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
    # The live recording's id (its draft's), only for the event log: unlike capture_id it never loads a stored capture.
    call_id: Optional[str] = Field(default=None, max_length=128)
    contact_id: Optional[str] = Field(default=None, max_length=128)
    request_id: Optional[str] = Field(default=None, max_length=128)
    # The call's type, decided once for the call (Vocify's guess or proposal, or the rep's pick).
    sales_motion_key: Optional[str] = Field(default=None, max_length=64)
    # The objection the turn check already put on screen: the answer is written for it.
    objection_type: Optional[str] = Field(default=None, max_length=32)
    # The playbook's own objection the turn check matched (objection_type "custom"): its answer is followed.
    entry_id: Optional[str] = Field(default=None, max_length=200)
    # The filler line the rep is already saying for it: the answer is the next sentence.
    filler: Optional[str] = Field(default=None, max_length=200)
    # The lines live help already showed in this call, oldest first: the new one must differ.
    previous_answers: list[Annotated[str, Field(max_length=400)]] = Field(default_factory=list, max_length=8)


class TurnRequest(BaseModel):
    transcript_window: str = Field(..., max_length=20000)
    latest_turn: str = Field(..., max_length=4000)
    sales_motion_key: Optional[str] = Field(default=None, max_length=64)
    call_id: Optional[str] = Field(default=None, max_length=128)
    # What the client saw as the check started (which rule fired it, how long their audio was quiet, how long since
    # the words changed): only logged, after the known keys are checked. Never used to decide anything.
    timing: Optional[dict] = Field(default=None)


class CallTypeGuessRequest(BaseModel):
    interaction_kind: Literal["call", "meeting"] = "meeting"
    contact_id: Optional[str] = Field(default=None, max_length=128)


class CallTypeOption(BaseModel):
    key: str = Field(..., max_length=64)
    label: str = Field(..., max_length=200)


class CallTypeProposeRequest(BaseModel):
    transcript_window: str = Field(..., max_length=20000)
    # The call's channel: with types by channel only its types are proposed.
    interaction_kind: Optional[Literal["call", "meeting"]] = None
    options: list[CallTypeOption] = Field(default_factory=list, max_length=50)


def _empty_objection(event: dict) -> bool:
    """A result that flags an objection with no line to say: shown, it would vanish at once."""
    suggestion = event.get("suggestion") or {}
    return suggestion.get("is_objection") is True and not str(suggestion.get("say_this") or "").strip()


def _matched_entry(grounding, entry_id: Optional[str]) -> Optional[dict]:
    """The playbook entry the turn check matched, when it is one of this call's published answers."""
    wanted = (entry_id or "").strip()
    entries = (grounding.playbook_snapshot or {}).get("entries") if grounding else None
    return next(
        (e for e in entries or [] if isinstance(e, dict) and wanted and e.get("entry_id") == wanted and e.get("guidance")),
        None,
    )


def _sse(events: list[dict]) -> StreamingResponse:
    body = "".join(f"data: {json.dumps(event, ensure_ascii=False)}\n\n" for event in events)
    return StreamingResponse(iter([body]), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


@dataclass(frozen=True)
class LiveContext:
    """What a card reads before the model writes it (see services/copilot/live_context.py)."""

    product_context: str
    knowledge: Optional[dict]
    grounding: Optional[SuggestGrounding]
    timezone: str
    cache: str


async def _live_context(
    supabase: Client, *, user_id: str, company_id: str, motion: Optional[str], kind: str, need_product: bool,
) -> LiveContext:
    """The rep's offer, the company's knowledge, the call type's playbook (when the call has a type) and the rep's
    timezone: from the short-lived cache when fresh, else read at the same time in worker threads. A read that
    fails gives what live help used before (no offer, no knowledge, no playbook) for this request only."""
    from app.services.extraction_context import load_product_context  # resolved here: tests replace it

    reads = [
        lambda: live_context.cached(("product", user_id), lambda: load_product_context(supabase, user_id, strict=True), fallback="")
        if need_product else _nothing(""),
        lambda: live_context.cached(
            ("knowledge", company_id), lambda: load_company_knowledge(supabase, company_id=company_id, strict=True),
        ),
        lambda: live_context.cached(
            ("grounding", company_id, motion),
            lambda: call_type.grounding_for_type(supabase, company_id, motion, kind, strict=True),
        ) if motion else _nothing(None),
        lambda: live_context.cached(("timezone", user_id), lambda: rep_timezone(user_id), fallback=DEFAULT_TZ),
    ]
    if live_context.ttl_s() > 0:
        product, knowledge, grounding, timezone = await asyncio.gather(*(read() for read in reads))
    else:
        # The cache is off: one read after the other, exactly as live help did before it existed.
        product, knowledge, grounding, timezone = [await read() for read in reads]
    taken = [read for read, used in ((product, need_product), (knowledge, True), (grounding, bool(motion)), (timezone, True)) if used]
    found = grounding.value
    if found is not None and found.interaction_kind != kind:
        # The playbook is the company's for this type; "call" or "meeting" is this request's.
        found = replace(found, interaction_kind=kind)
    return LiveContext(product.value or "", knowledge.value, found, timezone.value, live_context.cache_state(taken))


async def _nothing(value):
    return live_context.Loaded(value, hit=True)


async def _warm_context(supabase: Client, user_id: str, motion: Optional[str]) -> None:
    """After a turn check: read what the card that may follow will need, so that card finds it ready. Never raises."""
    company_id = playbook_objections.company_of(user_id)
    if not company_id or live_context.ttl_s() <= 0:
        return
    try:
        await _live_context(supabase, user_id=user_id, company_id=company_id, motion=motion, kind="call", need_product=True)
    except Exception:
        logger.warning("live help: warming the context failed", exc_info=True)


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
    started = time.perf_counter()
    motion = (body.sales_motion_key or "").strip() or None
    if motion == INTERNAL_KEY:
        # No customer in the conversation: no help, and no model call.
        return _sse([{"type": "result", "suggestion": silent_suggestion()}, {"type": "done"}])

    # Desktop meetings don't carry the offer; use the one the rep saved for extraction.
    product_context = (body.product_context or "").strip()
    typed = bool(motion and not body.capture_id)
    live = await _live_context(
        supabase, user_id=membership.user_id, company_id=membership.company_id,
        motion=motion if typed else None, kind=live_assist_kind_from_call_mode(body.call_mode),
        need_product=not product_context,
    )
    product_context = product_context or live.product_context

    context = resolve_suggest_context(
        body.contact_id,
        call_mode=body.call_mode,
    )
    if typed:
        grounding = live.grounding
    elif body.capture_id:
        # Tied to a stored capture: read for this capture, never kept.
        grounding = await run_in_threadpool(
            lambda: load_suggest_grounding(
                supabase,
                user_id=membership.user_id,
                company_id=membership.company_id,
                capture_id=body.capture_id,
                context=context,
            )
        )
    else:
        # No call type yet: the playbook this rep's routing would pin (it depends on their role and the contact).
        grounding = await run_in_threadpool(
            lambda: load_company_suggest_grounding(
                supabase,
                company_id=membership.company_id,
                call_mode=body.call_mode,
                context=context,
                user_id=membership.user_id,
            )
        )

    company_knowledge = live.knowledge
    contact_history = None
    if context.contact_id:
        # Same memo visibility as the pre-call brief for this contact.
        allowed_user_ids = await run_in_threadpool(
            _handoff_restricted_user_ids, supabase, membership, connection_id=None, contact_id=context.contact_id,
        )
        contact_history = await load_contact_history(
            supabase,
            company_id=membership.company_id,
            contact_id=context.contact_id,
            allowed_user_ids=allowed_user_ids,
        )

    today = today_line(live.timezone)

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
            entry=_matched_entry(grounding, body.entry_id),
            today=today,
            filler=body.filler,
            previous_answers=body.previous_answers,
        )

    def sse(event: dict) -> str:
        if event.get("type") == "result":
            if body.capture_id:
                event = {**event, "capture_id": body.capture_id}
            if body.request_id:
                event = {**event, "request_id": body.request_id}
        return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    # What happened, for the event log: filled while the answer streams, written after it is sent.
    trail: dict = {"result": None, "restarted": False, "error": None, "prep_ms": None}

    def note(event: dict) -> None:
        if event.get("type") == "result":
            trail["result"] = event
        elif event.get("type") == "error":
            trail["error"] = event.get("message")

    def log_card() -> None:
        events.record(supabase, events.suggest_row(
            user_id=membership.user_id, company_id=membership.company_id, sales_motion_key=motion,
            call_mode=body.call_mode, latest_turn=body.latest_turn, objection_type=body.objection_type,
            entry_id=body.entry_id, capture_id=body.capture_id or body.call_id, result=trail["result"],
            restarted=trail["restarted"], error=trail["error"],
            playbook_version_id=grounding.playbook_version_id if grounding else None,
            # Where the time before the model went, on the server: reading what the card needs, and from where.
            server_timing={"prep_ms": trail["prep_ms"], "cache": live.cache},
        ))

    async def event_gen():
        trail["prep_ms"] = int((time.perf_counter() - started) * 1000)
        async for event in ask(grounding):
            if event.get("type") == "result" and grounding is not None and _empty_objection(event):
                # The playbook can make the model flag an objection and say nothing: ask once more
                # without it, as general help. The client drops what it streamed so far.
                trail["restarted"] = True
                yield sse({"type": "restart"})
                async for retry in ask(None):
                    note(retry)
                    yield sse(retry)
                break
            note(event)
            yield sse(event)
        yield "data: {\"type\": \"done\"}\n\n"

    return StreamingResponse(
        event_gen(),
        background=BackgroundTask(log_card),
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
    background: BackgroundTasks,
    user_id: str = Depends(get_user_id),
    supabase: Client = Depends(get_supabase),
):
    """About 0.3 s: has the prospect finished, and which objection is it. Nulls mean no classifier.
    It runs on every pause, so the type's own objections (custom playbook entries) are looked up once
    and kept for a minute, off the event loop; without a type there is nothing to look up."""
    motion = (body.sales_motion_key or "").strip()
    if motion == INTERNAL_KEY:
        return {"finished": True, "objection": "none"}
    custom = await run_in_threadpool(playbook_objections.custom_for, supabase, user_id, motion) if motion else None
    started = time.perf_counter()
    reading = await turn.read_turn(body.transcript_window, body.latest_turn, custom)
    # The card that may follow reads its context next: have it ready (a worker thread, after this response).
    background.add_task(_warm_context, supabase, user_id, motion or None)
    background.add_task(
        events.record, supabase,
        events.turn_row(
            user_id=user_id, company_id=playbook_objections.company_of(user_id), sales_motion_key=motion,
            latest_turn=body.latest_turn, reading=reading, check_ms=int((time.perf_counter() - started) * 1000),
            timing=body.timing, capture_id=body.call_id,
        ),
    )
    return reading


@router.post("/call-type/guess")
async def guess_call_type(
    body: CallTypeGuessRequest,
    membership: Membership = Depends(get_membership),
    supabase: Client = Depends(get_supabase),
):
    """The type to start a live call with, at no model cost."""
    key, source = call_type.guess(
        supabase, membership.company_id, membership.user_id, body.interaction_kind, body.contact_id,
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
    proposal = await call_type.propose(
        supabase, membership.company_id, body.transcript_window, labels, body.interaction_kind,
    )
    return {"type": proposal[0], "confident": proposal[1]} if proposal else {"type": None, "confident": False}


@router.get("/health")
async def copilot_health():
    return {"ok": True, "feature": "objection-copilot"}
