"""The playbook assistant (spec 2026-10-16-playbook-volcado-y-perfeccionamiento-design): helping a Head of Sales pour
what they know into the playbook, and improve it with use.

Owner/admin only and dark behind PLAYBOOK_ASSISTANT_ENABLED (404 for a company without it). Until the tables of
migration 082 exist the answer is 503 `not_activated`. Nothing here publishes: every change lands in the draft of
a call type (or, for a figure two documents disagree about, in the company notes) and reaches the team when the
Head of Sales publishes.

  POST /intake                       several documents at once, put together per call type and saved once
  POST /trial, GET /trial/{id}, POST /trial/{id}/cases/{case}/run|verdict, GET /trial/{id}/result, POST /trial/{id}/activate
  POST /gaps/session, GET /gaps/session/current, POST /gaps/session/{id}/answer|skip|undo
  GET  /model-calls/recent, POST /model-calls/propose, POST /model-calls/apply
        (a model call is never stored: it is read, proposals are made, only what is accepted is kept)
  GET  /improve/stats                coverage always; the success rate and the queue only with PLAYBOOK_SUCCESS_RATE_ENABLED
  POST /improve/refresh, GET /improve/queue, POST /improve/queue/{moment}/action, POST /improve/publish,
  POST /improve/outcomes/{event}/verdict
        (judging a finished call happens here, later and in batches: never when a call ends)
"""

from __future__ import annotations

import functools
import inspect
import logging
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from supabase import Client

from app.api.playbooks import _playbooks_changed
from app.api.playbook_intake import (
    _company_payload,
    _keep_source,
    _questions_only_item,
    intake_candidates,
    intake_items,
    saved_types,
)
from app.deps import get_membership, get_supabase
from app.services.company import Membership
from app.services.feature_flags import is_enabled
from app.services.playbooks.api_support import StructureRequest, fill_failed, read_source, require_manager
from app.services.playbooks.assistant import (
    AssistantError,
    add_gaps,
    answer_gap,
    draft_content,
    public_gap,
    public_session,
    save_content,
    skip_gap,
    start_gaps_session,
    undo_gap,
)
from app.services.playbooks.assistant_store import AssistantStore, AssistantUnavailable, get_assistant_store
from app.services.playbooks.fill import FillError
from app.services.playbooks.gaps import detect_conflicts, recent_suggest_events
from app.services.playbooks.intake import merge_split_results, public_candidates
from app.services.playbooks.knowledge import StaleKnowledgeError, merge_knowledge, normalize_knowledge
from app.services.playbooks.model_calls import apply_proposals, propose
from app.services.playbooks.questions import add_questions, extract_questions
from app.services.playbooks.repository import PlaybookRepository, get_playbook_repository
from app.services.playbooks.review_queue import (
    COVERAGE_DAYS,
    act_on_moment,
    correct_verdict,
    coverage_stats,
    failing_by_answer,
    judged_stats,
    public_queue,
    publish_queue_changes,
    recent_outcomes,
    refresh_moments,
    refresh_outcomes,
)
from app.services.playbooks import trial_session
from app.services.playbooks.structure import detect_language, split_source
from app.services.playbooks.structured import PlaybookDraftError
from app.services.playbooks.trial import run_case, similar_phrase
from app.services.playbooks.trial_session import TrialError
from app.services.playbooks.versions import StaleDraftError

logger = logging.getLogger(__name__)

FLAG = "PLAYBOOK_ASSISTANT_ENABLED"
SUCCESS_FLAG = "PLAYBOOK_SUCCESS_RATE_ENABLED"
MAX_SOURCES = 8
RECENT_CALLS = 30
SUMMARY_CHARS = 140
_NOT_FOUND = frozenset({"session_not_found", "gap_not_found", "call_not_found", "case_not_found", "moment_not_found", "outcome_not_found"})
# What a verdict or a transcript can be refused for: the person's words are kept and the screen says why.
_REFUSED = frozenset({
    "empty_transcript", "transcript_too_long", "guidance_too_long", "text_required", "no_answer_to_attach",
    "too_many_custom_objections",
})
_LIVE = frozenset({"published", "paused", "draft"})

router = APIRouter(prefix="/api/v1/playbook-assistant", tags=["playbook-assistant"])


# --- gate and errors -------------------------------------------------------------------------------


def _gate(supabase: Client, membership: Membership) -> AssistantStore:
    require_manager(membership)
    if not is_enabled(supabase, membership.company_id, FLAG):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return get_assistant_store(supabase)


def _success_gate(supabase: Client, membership: Membership) -> AssistantStore:
    """The gate of everything that depends on judging finished calls: the assistant's flag and the success rate's."""
    store = _gate(supabase, membership)
    if not is_enabled(supabase, membership.company_id, SUCCESS_FLAG):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return store


def _mapped(fn):
    """The domain errors of this module as the HTTP answers the screens understand. A handler that awaits nothing is a plain
    `def` and runs in the threadpool, so its database calls never hold the event loop every request shares."""

    @functools.wraps(fn)
    async def wrapper(*args, **kwargs):
        try:
            if inspect.iscoroutinefunction(fn):
                return await fn(*args, **kwargs)
            return await run_in_threadpool(fn, *args, **kwargs)
        except AssistantUnavailable as exc:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail={"code": "not_activated"}) from exc
        except AssistantError as exc:
            code = status.HTTP_404_NOT_FOUND if exc.code in _NOT_FOUND else status.HTTP_409_CONFLICT
            raise HTTPException(status_code=code, detail={"code": exc.code}) from exc
        except FillError as exc:
            raise fill_failed() from exc
        except StaleDraftError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": "stale_draft"}) from exc
        except StaleKnowledgeError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": "stale_knowledge"}) from exc
        except PlaybookDraftError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail={"code": exc.code}) from exc
        except TrialError as exc:
            code = status.HTTP_404_NOT_FOUND if exc.code in _NOT_FOUND else status.HTTP_422_UNPROCESSABLE_ENTITY
            raise HTTPException(status_code=code, detail={"code": exc.code}) from exc
        except ValueError as exc:
            if str(exc) in _REFUSED:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail={"code": str(exc)}) from exc
            raise

    return wrapper


def _lang(value: Optional[str]) -> str:
    return "en" if (value or "").lower().startswith("en") else "es"


def _default_motion(repository: PlaybookRepository, company_id: str) -> str:
    types = repository.list_types(company_id, include_draft=True)
    return next((key for key, row in types.items() if row.get("status") in _LIVE), "discovery")


def _code_of(exc: HTTPException) -> Optional[str]:
    return str(exc.detail["code"]) if isinstance(exc.detail, dict) and exc.detail.get("code") else None


# --- several documents at once -------------------------------------------------------------------------


class IntakeManyRequest(BaseModel):
    sources: list[StructureRequest] = Field(min_length=1, max_length=MAX_SOURCES)


def _nothing_read(failed: list[dict]) -> dict:
    return {
        "source": None, "sources": [], "failed": failed, "fallback": False, "error": None, "reason": None,
        "candidates": [], "types": [], "company": None, "conflicts": [],
    }


@router.post("/intake")
@_mapped
async def intake_many(
    body: IntakeManyRequest,
    supabase: Client = Depends(get_supabase),
    membership: Membership = Depends(get_membership),
):
    """Reads every document (one that cannot be read is reported by name and does not stop the others), splits each by
    call type, puts the results together and saves them ONCE: a type's draft is replaced by an intake, so saving
    document by document would leave only the last one. Also keeps the product questions the documents answer and
    reports the facts they disagree about (`conflicts`), which become the first questions of the guided assistant."""
    store = _gate(supabase, membership)
    repository = get_playbook_repository()
    company_id = membership.company_id
    readable, failed = [], []
    for source in body.sources:
        name = (source.name or "").strip()[:200] or source.kind
        try:
            readable.append((source, name, await read_source(source)))
        except HTTPException as exc:
            failed.append({"name": name, "code": _code_of(exc)})
    if not readable:
        return _nothing_read(failed)

    lang = detect_language("\n\n".join(text for _, _, text in readable))
    routing, candidates = intake_candidates(supabase, company_id, repository, lang)
    parts: list[tuple[dict, list[dict]]] = []
    kept: list[dict] = []
    for source, name, text in readable:
        row = _keep_source(repository, membership, None, source, text, lang)
        result = await split_source(text, candidates, lang, branches=True)
        if result["fallback"]:
            failed.append({"name": name, "code": "unreadable"})
            continue
        parts.append((result, await extract_questions(text, lang)))
        if row:
            kept.append(row)
    if not parts:
        return _nothing_read(failed)

    questions: list[dict] = []
    for _, found_questions in parts:
        questions = add_questions(questions, found_questions)
    merged_types = merge_split_results([result["types"] for result, _ in parts])
    items, reasons = intake_items(merged_types, candidates, questions, routing=routing, lang=lang)
    if questions and not items:
        placed = _questions_only_item(repository, company_id, candidates, questions, routing=routing, lang=lang)
        items.append(placed)
        reasons[placed["key"]] = None

    existing = repository.get_knowledge(company_id)
    current = normalize_knowledge((existing or {}).get("data"))
    filled: list[str] = []
    conflicts = []
    for result, _ in parts:
        found = result.get("company")
        conflicts += [g for g in detect_conflicts(current, found or {}, lang) if g.key not in {c.key for c in conflicts}]
        current, now_filled = merge_knowledge(current, found)
        filled += [key for key in now_filled if key not in filled]
    merged = current if filled else None
    saved: dict = {"types": [], "knowledge": None}
    if items or filled:
        saved = repository.save_intake(company_id, items, merged, (kept[0] if kept else {}).get("id"))

    if conflicts:
        await _queue_conflicts(store, repository, supabase, membership, conflicts, lang, merged_types)
    return {
        "source": kept[0] if kept else None,
        "sources": kept,
        "failed": failed,
        "fallback": False,
        "error": None,
        "reason": None if (items or filled) else "no_process",
        "candidates": public_candidates(candidates),
        "types": saved_types(repository, company_id, saved, reasons),
        "company": _company_payload(saved["knowledge"] or existing, merged, filled),
        "conflicts": [public_gap(g.as_dict()) for g in conflicts],
    }


async def _queue_conflicts(
    store: AssistantStore, repository: PlaybookRepository, supabase: Client, membership: Membership,
    conflicts: list, lang: str, merged_types: dict,
) -> None:
    """What the documents disagree about goes to the front of the guided questions. The intake never depends on the
    assistant's tables: if they are not there, the conflicts are only reported."""
    try:
        open_session = store.latest_open_session(membership.company_id, "gaps")
        if open_session is not None:
            add_gaps(store, membership, open_session, conflicts)
        else:
            motion = next(iter(merged_types), None) or _default_motion(repository, membership.company_id)
            await start_gaps_session(store, repository, supabase, membership, motion_key=motion, lang=lang, conflicts=conflicts)
    except AssistantUnavailable:
        logger.info("playbook assistant: conflicts not queued, tables not activated")


# --- the guided questions ---------------------------------------------------------------------------------


class GapSessionRequest(BaseModel):
    motion_key: Optional[str] = None
    lang: Optional[str] = None


class GapAnswerRequest(StructureRequest):
    gap_key: str


class GapKeyRequest(BaseModel):
    gap_key: str


@router.post("/gaps/session")
@_mapped
async def create_gaps_session(
    body: GapSessionRequest,
    supabase: Client = Depends(get_supabase),
    membership: Membership = Depends(get_membership),
):
    """The company's open session of guided questions, or a new one (up to 10 questions)."""
    store = _gate(supabase, membership)
    repository = get_playbook_repository()
    motion = (body.motion_key or "").strip() or _default_motion(repository, membership.company_id)
    session = await start_gaps_session(store, repository, supabase, membership, motion_key=motion, lang=_lang(body.lang))
    return public_session(session)


@router.get("/gaps/session/current")
@_mapped
def current_gaps_session(
    supabase: Client = Depends(get_supabase),
    membership: Membership = Depends(get_membership),
):
    store = _gate(supabase, membership)
    session = store.latest_open_session(membership.company_id, "gaps")
    return {"session": public_session(session) if session else None}


@router.post("/gaps/session/{session_id}/answer")
@_mapped
async def answer_gaps_session(
    session_id: str,
    body: GapAnswerRequest,
    supabase: Client = Depends(get_supabase),
    membership: Membership = Depends(get_membership),
):
    store = _gate(supabase, membership)
    source = StructureRequest(kind=body.kind, payload=body.payload, name=body.name)
    return await answer_gap(
        store, get_playbook_repository(), supabase, membership, session_id=session_id, gap_key=body.gap_key, source=source,
    )


@router.post("/gaps/session/{session_id}/skip")
@_mapped
def skip_gaps_session(
    session_id: str,
    body: GapKeyRequest,
    supabase: Client = Depends(get_supabase),
    membership: Membership = Depends(get_membership),
):
    store = _gate(supabase, membership)
    return skip_gap(store, membership, session_id=session_id, gap_key=body.gap_key)


@router.post("/gaps/session/{session_id}/undo")
@_mapped
def undo_gaps_session(
    session_id: str,
    body: GapKeyRequest,
    supabase: Client = Depends(get_supabase),
    membership: Membership = Depends(get_membership),
):
    store = _gate(supabase, membership)
    return undo_gap(store, get_playbook_repository(), membership, session_id=session_id, gap_key=body.gap_key)


# --- model calls -----------------------------------------------------------------------------------------
# A model call is a transcript the Head of Sales marks as a good example. It is read once, proposals are made and the
# transcript is dropped: nothing about it is stored, and only what the Head of Sales accepts reaches the playbook.


class ModelCallRequest(BaseModel):
    motion_key: str
    transcript: Optional[str] = None
    memo_id: Optional[str] = None
    scope: dict = Field(default_factory=lambda: {"kind": "whole"})
    note: Optional[str] = Field(default=None, max_length=1000)


class ProposalIn(BaseModel):
    """A proposal as `propose` returned it, after the Head of Sales chose it (and maybe rewrote its `text`).
    `as_custom` keeps a branch that does not fit as an objection of its own, under that name."""

    id: str = Field(max_length=20)
    kind: str
    step_index: Optional[int] = None
    category: Optional[str] = None
    label: Optional[str] = Field(default=None, max_length=120)
    when: Optional[str] = Field(default=None, max_length=300)
    text: str = Field(max_length=1500)
    as_custom: Optional[str] = Field(default=None, max_length=120)


class ApplyRequest(BaseModel):
    motion_key: str
    proposals: list[ProposalIn] = Field(max_length=60)


def _call_summary(extraction: Any) -> str:
    text = str((extraction or {}).get("summary") or "") if isinstance(extraction, dict) else ""
    return " ".join(text.split())[:SUMMARY_CHARS]


def _memo_transcript(supabase: Client, company_id: str, memo_id: str) -> str:
    rows = supabase.table("memos").select("id,company_id,transcript").eq("id", memo_id).limit(1).execute().data or []
    row = rows[0] if rows else None
    if not row or str(row.get("company_id") or "") != company_id or not str(row.get("transcript") or "").strip():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"code": "call_not_found"})
    return str(row["transcript"])


@router.get("/model-calls/recent")
@_mapped
def recent_calls(
    supabase: Client = Depends(get_supabase),
    membership: Membership = Depends(get_membership),
):
    """The company's latest calls, to pick one as a model call."""
    _gate(supabase, membership)
    rows = (
        supabase.table("memos").select("id,created_at,sales_motion_key,extraction")
        .eq("company_id", membership.company_id).order("created_at", desc=True).limit(RECENT_CALLS).execute().data or []
    )
    return {"calls": [
        {"id": r["id"], "created_at": r.get("created_at"), "sales_motion_key": r.get("sales_motion_key"), "summary": _call_summary(r.get("extraction"))}
        for r in rows
    ]}


@router.post("/model-calls/propose")
@_mapped
async def propose_from_model_call(
    body: ModelCallRequest,
    supabase: Client = Depends(get_supabase),
    membership: Membership = Depends(get_membership),
):
    """Reads one call (pasted transcript or one of the company's calls) -> {proposals, speaker_warning}. Stores nothing."""
    _gate(supabase, membership)
    if bool(body.transcript) == bool(body.memo_id):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail={"code": "one_transcript_needed"})
    company_id = membership.company_id
    transcript = body.transcript if body.transcript else _memo_transcript(supabase, company_id, str(body.memo_id))
    current, _ = draft_content(get_playbook_repository(), company_id, body.motion_key)
    return await propose(transcript, body.scope, body.note or "", current, detect_language(transcript))


@router.post("/model-calls/apply")
@_mapped
def apply_model_call(
    body: ApplyRequest,
    supabase: Client = Depends(get_supabase),
    membership: Membership = Depends(get_membership),
):
    """Applies the proposals the Head of Sales chose to the draft of the call type -> {editor, applied, skipped}. A
    proposal that does not fit is skipped with a code and changes nothing; the rest are applied."""
    _gate(supabase, membership)
    repository = get_playbook_repository()
    company_id, motion = membership.company_id, body.motion_key
    chosen = [proposal.model_dump(exclude_none=True) for proposal in body.proposals]
    for attempt in (0, 1):
        content, base = draft_content(repository, company_id, motion)
        result = apply_proposals(content, chosen)
        if not result["applied"]:
            break
        try:
            save_content(repository, company_id, motion, result, base)
        except StaleDraftError:
            if attempt == 1:
                raise
            continue
        break
    content, _ = draft_content(repository, company_id, motion)
    return {"editor": {"sales_motion_key": motion, **content}, "applied": result["applied"], "skipped": result["skipped"]}


# --- the trial ---------------------------------------------------------------------------------------------


class TrialRequest(BaseModel):
    motion_key: Optional[str] = None
    lang: Optional[str] = None
    # "Repetir la prueba": close the open one and start again.
    fresh: bool = False


class VerdictRequest(BaseModel):
    verdict: str
    text: Optional[str] = Field(default=None, max_length=4000)
    # For a branch: the situation it is for, in the customer's words.
    when: Optional[str] = Field(default=None, max_length=300)


@router.post("/trial")
@_mapped
async def start_trial(
    body: TrialRequest,
    supabase: Client = Depends(get_supabase),
    membership: Membership = Depends(get_membership),
):
    """The company's open trial, or a new one: 10 to 12 things a customer might say."""
    store = _gate(supabase, membership)
    repository = get_playbook_repository()
    motion = (body.motion_key or "").strip() or _default_motion(repository, membership.company_id)
    session = await trial_session.start_trial(
        store, repository, supabase, membership, motion_key=motion, lang=_lang(body.lang), fresh=body.fresh,
    )
    return trial_session.public_trial(session)


def _trial(store: AssistantStore, membership: Membership, session_id: str) -> dict:
    session = store.get_session(membership.company_id, session_id)
    if session is None or session.get("kind") != "trial":
        raise TrialError("session_not_found")
    return session


@router.get("/trial/{session_id}")
@_mapped
def get_trial(
    session_id: str,
    supabase: Client = Depends(get_supabase),
    membership: Membership = Depends(get_membership),
):
    store = _gate(supabase, membership)
    return trial_session.public_trial(_trial(store, membership, session_id))


@router.post("/trial/{session_id}/cases/{case_id}/run")
@_mapped
async def run_trial_case(
    session_id: str,
    case_id: str,
    supabase: Client = Depends(get_supabase),
    membership: Membership = Depends(get_membership),
):
    """The case as live help would answer it with the draft as it is now -> {case, run}. Nothing is published."""
    store = _gate(supabase, membership)
    return await trial_session.run_trial_case(
        store, get_playbook_repository(), supabase, membership, session_id=session_id, case_id=case_id, runner=run_case,
    )


@router.post("/trial/{session_id}/cases/{case_id}/verdict")
@_mapped
async def decide_trial_case(
    session_id: str,
    case_id: str,
    body: VerdictRequest,
    supabase: Client = Depends(get_supabase),
    membership: Membership = Depends(get_membership),
):
    """approve | corrected | unknown | never_say | branch -> {run, similar, result, trial}. A verdict that changes the
    answer edits the draft and runs the case again; an answer that does not fit is a 422 and nothing changes."""
    store = _gate(supabase, membership)
    return await trial_session.decide_case(
        store, get_playbook_repository(), supabase, membership, session_id=session_id, case_id=case_id,
        verdict=body.verdict, text=body.text, when=body.when, runner=run_case, similar=similar_phrase,
    )


@router.get("/trial/{session_id}/result")
@_mapped
def trial_result(
    session_id: str,
    supabase: Client = Depends(get_supabase),
    membership: Membership = Depends(get_membership),
):
    store = _gate(supabase, membership)
    return trial_session.public_trial(_trial(store, membership, session_id))["result"]


@router.post("/trial/{session_id}/activate")
@_mapped
def activate_trial(
    session_id: str,
    supabase: Client = Depends(get_supabase),
    membership: Membership = Depends(get_membership),
):
    """Publishes the drafts the trial touched, whatever the score (below 80% the screen has warned; the Head of Sales
    decides) -> {published, failed}. Live help reads the new answers on its next card."""
    store = _gate(supabase, membership)
    outcome = trial_session.finish_trial(store, get_playbook_repository(), membership, session_id=session_id)
    _playbooks_changed(membership.company_id)
    return outcome


# --- improving with use: the numbers, the later batch and the queue ---------------------------------------


class QueueAction(BaseModel):
    action: Literal["keep", "correct", "branch", "new_objection"]
    text: Optional[str] = Field(default=None, max_length=4000)
    # For a branch: the situation it is for. For a new objection: what to name it after.
    when: Optional[str] = Field(default=None, max_length=300)
    lang: Optional[str] = None


class VerdictCorrection(BaseModel):
    resolved: Literal["resolved", "not_resolved"]


def _queue(store: AssistantStore, supabase: Client, membership: Membership) -> dict:
    repository = get_playbook_repository()
    return public_queue(store, repository, membership.company_id, _default_motion(repository, membership.company_id))


@router.get("/improve/stats")
@_mapped
def improve_stats(
    supabase: Client = Depends(get_supabase),
    membership: Membership = Depends(get_membership),
):
    """{coverage} always: how much of what customers raised had an approved answer (a rate needs three cases). With the
    success rate switched on also {success, queue}: how often a suggestion that was said settled it, and how many answers wait."""
    store = _gate(supabase, membership)
    body: dict = {"coverage": coverage_stats(recent_suggest_events(supabase, membership.company_id, days=COVERAGE_DAYS))}
    if is_enabled(supabase, membership.company_id, SUCCESS_FLAG):
        body.update(judged_stats(store, membership.company_id))
    return body


@router.post("/improve/refresh")
@_mapped
async def improve_refresh(
    supabase: Client = Depends(get_supabase),
    membership: Membership = Depends(get_membership),
):
    """Judges the next batch of finished calls and queues the answers that keep failing -> {judged, queued}. Calling it
    again goes on with the next batch; a card is never judged twice."""
    store = _success_gate(supabase, membership)
    judged = await refresh_outcomes(store, supabase, membership.company_id)
    queued = refresh_moments(store, membership.company_id, failing_by_answer(recent_outcomes(store, membership.company_id, after_fixes=True)))
    return {"judged": judged, "queued": queued}


@router.get("/improve/queue")
@_mapped
def improve_queue(
    supabase: Client = Depends(get_supabase),
    membership: Membership = Depends(get_membership),
):
    """{groups, publish}: the answers that keep failing, each with what it says now and its cases, and the call types
    with changes waiting to be published."""
    store = _success_gate(supabase, membership)
    return _queue(store, supabase, membership)


@router.post("/improve/queue/{moment_id}/action")
@_mapped
def improve_queue_action(
    moment_id: str,
    body: QueueAction,
    supabase: Client = Depends(get_supabase),
    membership: Membership = Depends(get_membership),
):
    """keep | correct | branch | new_objection on one case. The last three edit the draft (nothing goes live until
    /improve/publish); an answer that does not fit is a 422 and the case stays open -> {status, queue}."""
    store = _success_gate(supabase, membership)
    repository = get_playbook_repository()
    saved = act_on_moment(
        store, repository, membership.company_id, moment_id, body.action, text=body.text, when=body.when,
        default_motion=_default_motion(repository, membership.company_id), lang=_lang(body.lang),
    )
    return {"status": saved["status"], "queue": _queue(store, supabase, membership)}


@router.post("/improve/publish")
@_mapped
def improve_publish(
    supabase: Client = Depends(get_supabase),
    membership: Membership = Depends(get_membership),
):
    """Publishes the drafts the queue changed -> {published, failed}. Live help reads them on its next card."""
    store = _success_gate(supabase, membership)
    outcome = publish_queue_changes(store, get_playbook_repository(), membership)
    if outcome["published"]:
        _playbooks_changed(membership.company_id)
    return outcome


@router.post("/improve/outcomes/{event_id}/verdict")
@_mapped
def improve_outcome_verdict(
    event_id: str,
    body: VerdictCorrection,
    supabase: Client = Depends(get_supabase),
    membership: Membership = Depends(get_membership),
):
    """The Head of Sales says whether a suggestion settled it, whatever the judge decided -> {resolved, success, queue}."""
    store = _success_gate(supabase, membership)
    saved = correct_verdict(store, membership.company_id, event_id, body.resolved)
    return {"resolved": saved["resolved"], **judged_stats(store, membership.company_id)}
