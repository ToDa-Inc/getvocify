"""Playbook intake API: one document in, a draft per call type (and the company's knowledge) out.

POST /playbooks/structure reads the whole company's document; POST /playbooks/{key}/structure structures it for
one call type when the caller already knows which. Neither publishes anything."""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends
from supabase import Client

from app.deps import get_membership, get_supabase
from app.services.company import Membership
from app.services.feature_flags import is_enabled
from app.services.playbooks import channel_types
from app.services.playbooks.api_support import (
    StructureRequest,
    company_context,
    editor_response,
    fill_failed,
    read_source,
    require_manager,
)
from app.services.playbooks.fill import FillError, fill_playbook
from app.services.playbooks.intake import candidate_types, ensure_payload, public_candidates
from app.services.playbooks.questions import add_questions, extract_questions
from app.services.playbooks.knowledge import merge_knowledge, sections
from app.services.playbooks.repository import PlaybookRepository, get_playbook_repository
from app.services.playbooks.routing import motions_and_stored, routing_enabled
from app.services.playbooks.structure import (
    detect_language,
    set_playbook_structure_llm,
    split_source,
    structure_source,
)
from app.services.playbooks.structured import editor_view, normalize_objections, normalize_qualification, normalize_steps

logger = logging.getLogger(__name__)

__all__ = ["router", "set_playbook_structure_llm"]

router = APIRouter(prefix="/api/v1/playbooks", tags=["playbook-intake"])

_DEFAULT_SOURCE_NAMES = {
    "es": {"text": "Texto pegado", "pdf": "PDF", "audio": "Audio"},
    "en": {"text": "Pasted text", "pdf": "PDF", "audio": "Audio"},
}


def _keep_source(repository: PlaybookRepository, membership: Membership, key: Optional[str], body: StructureRequest, text: str, lang: str):
    name = (body.name or "").strip()[:200] or _DEFAULT_SOURCE_NAMES[lang].get(body.kind, body.kind)
    try:
        return repository.save_source(membership.company_id, key, body.kind, name, text)
    except Exception:  # keeping the original is a courtesy; it never blocks structuring
        logger.exception("playbook source not saved")
        return None


@router.post("/structure")
async def structure_company_source(
    body: StructureRequest,
    supabase: Client = Depends(get_supabase),
    membership: Membership = Depends(get_membership),
):
    """One input for the whole company. Vocify detects which call types the document covers
    (with routing on: the five catalog types and the company's own types that have a rule;
    off: discovery and closing), structures each with ONE model call and saves each as that
    type's draft (a live version stays live until published). If the model fails nothing is
    saved and `fallback` is true: the caller asks which call type it is and uses
    POST /{key}/structure."""
    require_manager(membership)
    repository = get_playbook_repository()
    text = await read_source(body)
    lang = detect_language(text)
    routing, candidates = intake_candidates(supabase, membership.company_id, repository, lang)
    source = _keep_source(repository, membership, None, body, text, lang)
    # The playbook assistant (dark by default) also keeps the product questions a document answers, and lets an
    # objection answer carry branches ("Si X: … Si Y: …").
    assistant = is_enabled(supabase, membership.company_id, "PLAYBOOK_ASSISTANT_ENABLED")
    result = await split_source(text, candidates, lang, branches=assistant)
    questions = [] if (result["fallback"] or not assistant) else await extract_questions(text, lang)

    found = {item["key"]: item for item in result["types"]}
    items, reasons = intake_items(found, candidates, questions, routing=routing, lang=lang)
    if questions and not items:
        # A product sheet has no steps: its questions go to the playbook the company already has, else to the first call type.
        placed = _questions_only_item(repository, membership.company_id, candidates, questions, routing=routing, lang=lang)
        items.append(placed)
        reasons[placed["key"]] = None
        result = {**result, "reason": None}
    existing, merged, filled = _merge_company(repository, membership.company_id, result.get("company"))
    source_id = (source or {}).get("id")
    saved = {"types": [], "knowledge": None}
    if items or filled:
        saved = repository.save_intake(membership.company_id, items, merged if filled else None, source_id)
    types = saved_types(repository, membership.company_id, saved, reasons)
    return {
        "source": source,
        "fallback": bool(result["fallback"]),
        # Why the model path failed ({kind, detail}), so the screen can say it instead of guessing.
        "error": result.get("error") if result["fallback"] else None,
        "reason": result["reason"],
        "candidates": public_candidates(candidates),
        "types": types,
        "company": _company_payload(saved["knowledge"] or existing, merged, filled),
    }


def intake_candidates(supabase: Client, company_id: str, repository: PlaybookRepository, lang: str) -> tuple[bool, list[dict]]:
    """(routing, the call types a document can be split into) for this company."""
    routing = routing_enabled(supabase, company_id)
    types = repository.list_types(company_id, include_draft=False)
    motions, stored = motions_and_stored(types)
    for key, row in types.items():
        stored[key]["recognize"] = row.get("recognize")
    # The types the company's own Proceso de venta lists: with types by channel that list is the company's.
    by_channel = is_enabled(supabase, company_id, channel_types.FLAG)
    return routing, candidate_types(routing, motions, stored, lang, by_channel=by_channel)


def intake_items(
    found: dict[str, dict], candidates: list[dict], questions: list[dict], *, routing: bool, lang: str,
) -> tuple[list[dict], dict]:
    """The `save_intake` items for the types a document (or several) covered, in candidate order, and each type's
    reason. The first type also gets the product questions the document answered."""
    items: list[dict] = []
    reasons: dict = {}
    first_key = next((c["key"] for c in candidates if c["key"] in found), None)
    for candidate in candidates:  # candidate order (catalog order), not the model's
        item = found.get(candidate["key"])
        if item is None:
            continue
        key = item["key"]
        criteria = normalize_qualification(item.get("qualification"))
        reasons[key] = item["reason"]
        items.append({
            "key": key,
            "steps": item["steps"],
            "entries": normalize_objections(
                add_questions(item["objections"], questions) if questions and key == first_key else item["objections"]
            ),
            # A document without criteria must not wipe the ones already in the draft.
            "qualification": criteria or None,
            "ensure": ensure_payload(key, routing=routing, lang=lang),
        })
    return items, reasons


def saved_types(repository: PlaybookRepository, company_id: str, saved: dict, reasons: dict) -> list[dict]:
    """The `types` of an intake answer: each saved type with its reason and its editor."""
    return [
        {
            "sales_motion_key": entry["sales_motion_key"],
            "reason": reasons.get(entry["sales_motion_key"]),
            "editor": editor_response(
                entry["sales_motion_key"],
                repository.editor_snapshot(company_id, entry["sales_motion_key"], include_draft=True),
            ),
        }
        for entry in saved["types"]
    ]


def _questions_only_item(
    repository: PlaybookRepository, company_id: str, candidates: list[dict], questions: list[dict], *, routing: bool, lang: str,
) -> dict:
    """The intake item for a document that only answers questions: the questions added to the content of the first call
    type that already has some (its steps and criteria stay as they are), else the first call type with nothing but them."""
    types = repository.list_types(company_id, include_draft=True)
    key = next((c["key"] for c in candidates if (types.get(c["key"]) or {}).get("status") in {"published", "paused", "draft"}), None)
    if key is None:
        key = candidates[0]["key"]
        return {
            "key": key, "steps": [], "entries": normalize_objections(add_questions([], questions)),
            "qualification": None, "ensure": ensure_payload(key, routing=routing, lang=lang),
        }
    editor = editor_view(repository.editor_snapshot(company_id, key, include_draft=True).get("version"))
    return {
        "key": key, "steps": normalize_steps(editor["steps"]) if editor["steps"] else [],
        "entries": normalize_objections(add_questions(editor["objections"], questions)),
        "qualification": None, "ensure": None,
    }


def _merge_company(repository: PlaybookRepository, company_id: str, found: Optional[dict]) -> tuple[Optional[dict], Optional[dict], list]:
    """What the document said about the company added to what is already stored, never overwriting it:
    (the stored row, the merged knowledge, the keys filled now). The write is part of the intake (one
    transaction with the call types). A failed read (the table is not there yet) means there is nothing to
    merge: the call types are still saved."""
    try:
        existing = repository.get_knowledge(company_id)
    except Exception:
        logger.exception("company knowledge not read")
        return None, None, []
    merged, filled = merge_knowledge((existing or {}).get("data") or {}, found)
    return existing, merged, filled


def _company_payload(row: Optional[dict], merged: Optional[dict], filled: list) -> Optional[dict]:
    """{knowledge, updated_at, sections, filled}, None when the document had nothing company-level and nothing
    is stored."""
    if merged is None or not sections(merged):
        return None
    return {
        "knowledge": merged,
        "updated_at": (row or {}).get("updated_at"),
        "sections": sections(merged),
        "filled": filled,
    }


@router.post("/{sales_motion_key}/structure")
async def structure_playbook_source(
    sales_motion_key: str,
    body: StructureRequest,
    supabase: Client = Depends(get_supabase),
    membership: Membership = Depends(get_membership),
):
    """Turns pasted text, a PDF or an audio recording into steps and objection answers for
    this call type. Creates no version: the caller reviews the result and saves it as the
    draft. The material is kept as `source` so the playbook can link back to it. If the
    model fails the steps come from the line parser and `fallback` is true."""
    require_manager(membership)
    repository = get_playbook_repository()
    text = await read_source(body)
    lang = detect_language(text)
    source = _keep_source(repository, membership, sales_motion_key, body, text, lang)
    result = await structure_source(text, sales_motion_key, lang, type_info=_own_type_info(supabase, repository, membership.company_id, sales_motion_key))
    return {"sales_motion_key": sales_motion_key, **result, "source": source}


def _own_type_info(supabase: Client, repository, company_id: str, key: str) -> Optional[dict]:
    """The company's own name, goal and description of a type of its sales process, for the model that reads its source.
    None when the company does not use the editable process, or anything fails (the catalog's description is used)."""
    try:
        if not is_enabled(supabase, company_id, "SALES_PROCESS_ENABLED"):
            return None
        from app.services.sales_process.process import process_view
        from app.services.sales_process.store import get_sales_process_store

        found = next((t for t in process_view(repository, get_sales_process_store(supabase), company_id) if t["key"] == key), None)
        return {"label": found["label"], "goal": found.get("goal"), "description": found.get("recognize")} if found else None
    except Exception:
        return None


class FillRequest(StructureRequest):
    """What the manager asked for (text, a PDF or an audio note) and the editor's current content
    ({steps, objections, qualification}, as PUT /draft takes it), so unsaved edits are the base."""

    current: dict = {}
    # A "Completar" on one item: only that item may change (see fill.restrict_to).
    scope: Optional[dict] = None


@router.post("/{sales_motion_key}/fill")
async def fill_playbook_draft(
    sales_motion_key: str,
    body: FillRequest,
    supabase: Client = Depends(get_supabase),
    membership: Membership = Depends(get_membership),
):
    """"Dile a Vocify": the request applied to this call type's content -> {steps, objections,
    qualification, changes, summary}. Saves nothing: the editor takes it as its draft (autosave,
    conflict check, nothing reaches the team until it is published). 422 `fill_failed` when the
    model could not do it; the content is untouched."""
    require_manager(membership)
    text = await read_source(body)
    try:
        return await fill_playbook(
            sales_motion_key,
            text,
            body.current,
            company_context(supabase, get_playbook_repository(), membership.company_id),
            scope=body.scope,
        )
    except FillError as exc:
        raise fill_failed() from exc

