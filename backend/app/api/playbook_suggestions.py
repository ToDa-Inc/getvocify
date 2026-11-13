"""«Sugerencias» for the head of sales (services/playbooks/suggestions.py): what the team's calls taught, each with a ready
draft to take into the playbook or a reason to set it aside. Owners and admins only."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from supabase import Client

from app.api.playbooks import _playbooks_changed
from app.deps import get_membership, get_supabase
from app.services.company import Membership
from app.services.playbooks import suggestions as engine
from app.services.playbooks.api_support import require_manager

router = APIRouter(prefix="/api/v1/playbook-assistant/suggestions", tags=["playbook-assistant"])

# What an answer can be refused for: the head of sales' words stay on screen and it says why.
_REFUSED = frozenset({
    "text_required", "guidance_too_long", "too_many_custom_objections", "too_many_situations", "already_in_playbook",
})
_ANSWER_KINDS = frozenset({"objection", "question"})


class Accept(BaseModel):
    text: str = Field(..., min_length=1, max_length=engine.TEXT_MAX)


class Dismiss(BaseModel):
    reason: Literal["isolated", "not_applicable", "covered"]
    # «covered»: the playbook answer that already covers it, as the call reading names answers (objection:custom:<slug>, objection:<category>).
    covered_by: Optional[str] = Field(default=None, max_length=200)


def _labels(company_id: str) -> dict[str, str]:
    from app.services.playbooks.repository import get_playbook_repository

    try:
        return {key: str(row.get("label")) for key, row in get_playbook_repository().list_types(company_id, include_draft=True).items() if row.get("label")}
    except Exception:
        return {}


def _answers(supabase: Client, company_id: str, motions: set[str]) -> dict[str, list[dict]]:
    """The published answers of each call type, to say which one already covers a suggestion."""
    from app.services.coaching import rep_coaching_reads as reads
    from app.services.playbooks.structured import OBJECTION_CATEGORIES

    out: dict[str, list[dict]] = {}
    for motion in motions:
        answers = []
        for entry in reads.load_published_playbook(supabase, company_id, motion)["entries"]:
            entry_id = str(entry.get("entry_id") or "")
            category = str(entry.get("category") or "")
            label = " ".join(str(entry.get("label") or entry.get("trigger") or "").split())
            if not entry_id.startswith("objection:") or not (label or category in OBJECTION_CATEGORIES):
                continue
            answers.append({"id": entry_id, "label": label or None, "category": category})
        out[motion] = answers
    return out


_ROW_COLUMNS = "id,user_id,sales_motion_key,capture_started_at,created_at,findings:extraction->intelligence->findings"
_PAGE = 1000


def _rows(supabase: Client, company_id: str, user_ids: list[str], start: datetime) -> list[dict]:
    """The company's read conversations since `start` that carry findings, as build_suggestions reads them. Only the
    findings are fetched (never the whole extraction), and only calls that have them: a findings read happens on
    conversations only."""
    from app.services.playbooks.catalog import INTERNAL_KEY

    rows: list[dict] = []
    offset = 0
    while True:
        page = list(
            supabase.table("memos").select(_ROW_COLUMNS).eq("company_id", company_id).in_("user_id", user_ids)
            .gte("created_at", start.isoformat()).not_.is_("extraction->intelligence->findings", "null")
            .order("created_at").range(offset, offset + _PAGE - 1).execute().data or []
        )
        rows.extend(page)
        if len(page) < _PAGE:
            break
        offset += _PAGE
    return [
        {
            "memo_id": str(row["id"]), "user_id": str(row.get("user_id") or ""), "motion": row.get("sales_motion_key"),
            "observed_at": row.get("capture_started_at") or row.get("created_at"), "is_conversation": True,
            "findings": row.get("findings"),
        }
        for row in rows
        if row.get("sales_motion_key") and row.get("sales_motion_key") != INTERNAL_KEY and isinstance(row.get("findings"), dict)
    ]


def _load(supabase: Client, membership: Membership) -> tuple[list[dict], dict[str, dict]]:
    """Every suggestion still waiting for the head of sales, and their decisions so far."""
    from app.services.team_insights.aggregate import load_team_reps

    # Everyone who sells counts here, managers too: a founder's call teaches as much as a rep's.
    reps = load_team_reps(supabase, membership.company_id)
    names = {str(rep["userId"]): engine.display_name(rep.get("name")) for rep in reps}
    if not names:
        return [], {}
    start = datetime.now(timezone.utc) - timedelta(days=engine.WINDOW_DAYS)
    rows = _rows(supabase, membership.company_id, list(names), start)
    decisions = engine.get_decision_store(supabase).all(membership.company_id)
    return engine.build_suggestions(rows, names, _labels(membership.company_id), decisions), decisions


def _body(supabase: Client, membership: Membership) -> dict:
    suggestions, decisions = _load(supabase, membership)
    return {
        "suggestions": suggestions,
        "answers": _answers(supabase, membership.company_id, {s["motion"] for s in suggestions}),
        "learned": sum(1 for d in decisions.values() if d.get("decision") == "accepted"),
    }


def _refused(exc: ValueError) -> HTTPException:
    if str(exc) in _REFUSED:
        return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail={"code": str(exc)})
    raise exc


@router.get("")
async def list_suggestions(supabase: Client = Depends(get_supabase), membership: Membership = Depends(get_membership)):
    """{suggestions, answers: {motion: [{id, label, category}]}, learned}: what waits, best first."""
    require_manager(membership)
    return await run_in_threadpool(_body, supabase, membership)


def _accept(supabase: Client, membership: Membership, key: str, text: str) -> dict:
    from app.services.playbooks.assistant import edit_draft
    from app.services.playbooks.conduct import get_conduct_store
    from app.services.playbooks.repository import get_playbook_repository
    from app.services.playbooks.trial import activate

    suggestions, _ = _load(supabase, membership)
    suggestion = engine.find(suggestions, key)
    store = engine.get_decision_store(supabase)
    motion = suggestion["motion"]
    # The decision first: without its table nothing is written, so a suggestion never enters the playbook twice.
    store.save(membership.company_id, {
        "key": key, "kind": suggestion["kind"], "motion": motion, "topic": suggestion["title"], "decision": "accepted",
        "reason": None, "covered_by": None, "count_at": suggestion["count"], "text": text, "user_id": membership.user_id,
    })
    published = False
    try:
        if suggestion["kind"] in _ANSWER_KINDS:
            repository = get_playbook_repository()
            had_draft = bool((repository.list_types(membership.company_id, include_draft=True).get(motion) or {}).get("has_draft"))
            edit_draft(repository, membership.company_id, motion, lambda content: engine.add_answer(content, suggestion, text))
            # Live at once, unless the type already had edits of someone's waiting: those are theirs to publish.
            if not had_draft:
                published = motion in activate(repository, membership, [motion])["published"]
        else:
            conduct = get_conduct_store(supabase)
            conduct.set(membership.company_id, motion, engine.add_situation(conduct.get(membership.company_id, motion), suggestion, text))
            published = True
    except Exception:
        store.delete(membership.company_id, key)
        raise
    _playbooks_changed(membership.company_id)
    return {"status": "accepted", "motion": motion, "published": published, **_body(supabase, membership)}


@router.post("/{key}/accept")
async def accept_suggestion(
    key: str, body: Accept, supabase: Client = Depends(get_supabase), membership: Membership = Depends(get_membership),
):
    """Takes it into the playbook with the head of sales' words -> {status, motion, published, suggestions, answers, learned}.
    An objection or a question becomes an answer of the type (published unless the type had other edits waiting); what
    worked and an opening let pass become a situation of «Cómo trabajamos». 422 with the reason when it does not fit."""
    require_manager(membership)
    try:
        return await run_in_threadpool(_accept, supabase, membership, key, body.text.strip())
    except ValueError as exc:
        raise _refused(exc) from exc
    except engine.SuggestionError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"code": exc.code}) from exc
    except engine.SuggestionsUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail={"code": "not_activated"}) from exc


def _dismiss(supabase: Client, membership: Membership, key: str, body: Dismiss) -> dict:
    suggestions, _ = _load(supabase, membership)
    suggestion = engine.find(suggestions, key)
    if body.reason == "covered" and not body.covered_by:
        raise engine.SuggestionError("covered_by_required")
    engine.get_decision_store(supabase).save(membership.company_id, {
        "key": key, "kind": suggestion["kind"], "motion": suggestion["motion"], "topic": suggestion["title"], "decision": "dismissed",
        "reason": body.reason, "covered_by": body.covered_by if body.reason == "covered" else None,
        "count_at": suggestion["count"], "text": None, "user_id": membership.user_id,
    })
    return {"status": "dismissed", **_body(supabase, membership)}


@router.post("/{key}/dismiss")
async def dismiss_suggestion(
    key: str, body: Dismiss, supabase: Client = Depends(get_supabase), membership: Membership = Depends(get_membership),
):
    """Sets it aside with the reason Vocify learns from -> {status, suggestions, answers, learned}."""
    require_manager(membership)
    try:
        return await run_in_threadpool(_dismiss, supabase, membership, key, body)
    except engine.SuggestionError as exc:
        code = status.HTTP_422_UNPROCESSABLE_ENTITY if exc.code == "covered_by_required" else status.HTTP_404_NOT_FOUND
        raise HTTPException(status_code=code, detail={"code": exc.code}) from exc
    except engine.SuggestionsUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail={"code": "not_activated"}) from exc


@router.post("/{key}/undo")
async def undo_dismissal(key: str, supabase: Client = Depends(get_supabase), membership: Membership = Depends(get_membership)):
    """Brings back one set aside by mistake -> {status, suggestions, answers, learned}. What was taken into the playbook is
    changed in the playbook, never undone here."""
    require_manager(membership)

    def run() -> dict:
        store = engine.get_decision_store(supabase)
        decision = store.all(membership.company_id).get(key)
        if decision is None or decision.get("decision") != "dismissed":
            raise engine.SuggestionError("suggestion_not_found")
        store.delete(membership.company_id, key)
        return {"status": "restored", **_body(supabase, membership)}

    try:
        return await run_in_threadpool(run)
    except engine.SuggestionError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"code": exc.code}) from exc
    except engine.SuggestionsUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail={"code": "not_activated"}) from exc


@router.post("/{key}/draft")
async def draft_suggestion(key: str, supabase: Client = Depends(get_supabase), membership: Membership = Depends(get_membership)):
    """«Completar con Vocify»: an answer for an objection or a question written from the company's material and playbook
    only -> {text}; text is null when they do not hold it. Nothing is saved."""
    from app.services.copilot.load_grounding import load_company_knowledge
    from app.services.intelligence.extract import playbook_answers
    from app.services.intelligence.findings import compact_material
    from app.services.llm import LLMClient

    require_manager(membership)

    def gather() -> tuple[dict, dict, list[dict], Optional[str]]:
        from app.services.coaching import rep_coaching_reads as reads

        suggestions, _ = _load(supabase, membership)
        suggestion = engine.find(suggestions, key)
        if suggestion["kind"] not in _ANSWER_KINDS:
            raise engine.SuggestionError("suggestion_not_found")
        material = compact_material(load_company_knowledge(supabase, company_id=membership.company_id))
        answers = playbook_answers(reads.load_published_playbook(supabase, membership.company_id, suggestion["motion"])["entries"])
        rows = supabase.table("companies").select("name").eq("id", membership.company_id).limit(1).execute().data or []
        return suggestion, material, answers, (rows[0].get("name") if rows else None)

    try:
        suggestion, material, answers, company_name = await run_in_threadpool(gather)
    except engine.SuggestionError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"code": exc.code}) from exc
    try:
        text = await engine.write_draft(suggestion, material=material, answers=answers, company_name=company_name, llm=LLMClient())
    except Exception:
        text = None
    return {"text": text}

