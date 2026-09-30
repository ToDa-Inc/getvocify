"""Playbook import API. Members cannot write. Imports never publish."""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from supabase import Client

from app.deps import get_membership, get_supabase
from app.services.company import Membership
from app.services.feature_flags import is_enabled
from app.services.playbooks.catalog import (
    RuleError,
    catalog_label,
    default_applies_to,
    is_catalog,
    validate_applies_to,
)
from app.services.playbooks.imports import start_import
from app.services.playbooks.intake import candidate_types, ensure_payload, public_candidates
from app.services.playbooks.knowledge import merge_knowledge, sections
from app.services.playbooks.motion import goal_for, visible_to_role
from app.services.playbooks.repository import (
    PlaybookRepository,
    get_playbook_repository,
    set_playbook_repository,
)
from app.services.playbooks.routing import build_details, motions_and_stored, routing_enabled
from app.services.playbooks.structure import (
    detect_language,
    set_playbook_structure_llm,
    split_source,
    structure_source,
)
from app.services.playbooks.structured import (
    OBJECTION_CATEGORIES,
    PlaybookDraftError,
    editor_view,
    normalize_objections,
    normalize_qualification,
    normalize_steps,
)
from app.services.playbooks.versions import LifecycleError, PublishError, StaleDraftError, can_publish

SALES_ROLES_FLAG = "SALES_ROLES_ENABLED"
MANAGE_ROLES = frozenset({"owner", "admin"})

logger = logging.getLogger(__name__)

__all__ = ["router", "set_playbook_repository", "set_playbook_transcriber", "set_playbook_structure_llm"]

router = APIRouter(prefix="/api/v1/playbooks", tags=["playbooks"])

_transcriber = None


def set_playbook_transcriber(transcriber) -> None:
    global _transcriber
    _transcriber = transcriber


async def _audio_text(payload: str) -> str:
    transcriber = _transcriber
    if transcriber is None:
        import base64

        from app.services.stt_batch import transcribe_bytes

        raw = base64.b64decode(payload)
        return await transcribe_bytes(raw, source="playbook_import")
    result = transcriber(payload)
    if asyncio.iscoroutine(result):
        return await result
    return result


class TypeRequest(BaseModel):
    type_key: str
    name: str = ""
    applies_to: Optional[dict] = None


@router.post("/types")
async def create_type(
    body: TypeRequest,
    supabase: Client = Depends(get_supabase),
    membership: Membership = Depends(get_membership),
):
    if not can_publish(membership.role):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Solo owner o admin pueden añadir una tipología")
    repository = get_playbook_repository()
    key = body.type_key.strip()
    rule = None
    if key:
        try:
            rule = _rule_for_new_type(supabase, membership.company_id, key, body.applies_to)
        except RuleError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail={"code": exc.code}
            ) from exc
    named = {}
    if rule is not None:
        named = {"label": body.name.strip() or catalog_label(key) or None, "applies_to": rule}
    try:
        repository.add_type(membership.company_id, body.type_key, body.name or body.type_key, **named)
    except PublishError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="La tipología necesita una clave") from exc
    motions, stored = motions_and_stored(repository.list_types(membership.company_id))
    return {"motions": motions, "details": build_details(motions, stored)}


def _rule_for_new_type(supabase: Client, company_id: str, key: str, applies_to: Optional[dict]) -> Optional[dict]:
    """The rule a new type is saved with. With PLAYBOOK_ROUTING_ENABLED a type outside the
    catalog needs one (rule_required): a type that applies to no call is the P1 problem.
    A catalog type takes the catalog default. Flag off: only a rule the caller sent."""
    routing = is_enabled(supabase, company_id, "PLAYBOOK_ROUTING_ENABLED")
    if applies_to is not None:
        return validate_applies_to(applies_to)
    if not routing:
        return None
    if is_catalog(key):
        return default_applies_to(key)
    raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail={"code": "rule_required"})


class ImportRequest(BaseModel):
    import_id: str
    kind: str
    payload: str = ""
    active_version_id: Optional[str] = None
    sales_motion_key: Optional[str] = None


def _guard(membership: Membership) -> None:
    if not can_publish(membership.role):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Solo owner o admin pueden importar un playbook")


@router.post("/imports")
async def create_import(body: ImportRequest, membership: Membership = Depends(get_membership)):
    _guard(membership)
    repository = get_playbook_repository()
    stt = None
    if body.kind == "audio":
        try:
            spoken = await _audio_text(body.payload)
            stt = lambda _raw, spoken=spoken: spoken
        except Exception:
            stt = None
    record = start_import(
        import_id=body.import_id,
        kind=body.kind,
        payload=body.payload,
        active_version_id=body.active_version_id,
        existing=repository.get_import(membership.company_id, body.import_id),
        stt=stt,
    )
    if body.sales_motion_key:
        record = {**record, "sales_motion_key": body.sales_motion_key}
    repository.save_import(membership.company_id, record, body.sales_motion_key)
    return record


_COUNT_FIELDS = ("step_count", "answer_count", "criteria_count", "has_draft")


def _playbooks_payload(supabase: Client, membership: Membership, repository: PlaybookRepository) -> dict:
    """The one shape of GET /playbooks, and of pause, resume, delete and restore: `motions`
    (paused ones say "paused"; deleted ones are not there), `details` and, with the roles flag,
    `goals`; a rep only gets what their role can see. Each `details[key]` gains step_count,
    answer_count, criteria_count and has_draft of the version the editor would open: the pending
    draft for a manager, else the live one. A rep only ever sees the live version, so for them
    has_draft is false and the counts are the live ones."""
    manager = membership.role in MANAGE_ROLES
    types = repository.list_types(membership.company_id, include_draft=manager)
    motions, stored = motions_and_stored(types)
    details = {
        key: {**detail, **{name: types[key][name] for name in _COUNT_FIELDS}}
        for key, detail in build_details(motions, stored).items()
    }
    if not is_enabled(supabase, membership.company_id, SALES_ROLES_FLAG):
        return {"motions": motions, "details": details}
    if not manager:
        motions = {
            key: status_
            for key, status_ in motions.items()
            if visible_to_role(key, membership.sales_role, details[key]["applies_to"])
        }
        details = {key: details[key] for key in motions}
    goals = {key: goal_for(key) for key in motions if goal_for(key)}
    return {"motions": motions, "goals": goals, "details": details}


@router.get("")
async def list_playbooks(
    supabase: Client = Depends(get_supabase),
    membership: Membership = Depends(get_membership),
):
    return _playbooks_payload(supabase, membership, get_playbook_repository())


@router.post("/{sales_motion_key}/publish")
async def publish_motion(sales_motion_key: str, membership: Membership = Depends(get_membership)):
    if not can_publish(membership.role):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Solo owner o admin pueden publicar")
    repository = get_playbook_repository()
    try:
        version_id = repository.publish(membership.company_id, sales_motion_key)
    except PublishError as exc:
        if exc.code == "contradiction":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Hay pasos contradictorios. Edita el borrador antes de publicar.",
            )
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="No hay un borrador para publicar")
    motions, _ = motions_and_stored(repository.list_types(membership.company_id))
    return {"motions": motions, "activated": {sales_motion_key: version_id}}


@router.get("/imports/{import_id}")
async def get_import(import_id: str, membership: Membership = Depends(get_membership)):
    record = get_playbook_repository().get_import(membership.company_id, import_id)
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Importación no encontrada")
    return record


class StructuredStep(BaseModel):
    step_id: Optional[str] = None
    label: str = ""
    criterion: str = ""
    example: Optional[str] = None


class StructuredObjection(BaseModel):
    category: str
    guidance: str = ""
    id: Optional[str] = None  # custom only: the slug the editor got back
    label: Optional[str] = None  # custom only
    trigger: Optional[str] = None  # custom only: how the prospect says it
    meaning: Optional[str] = None
    question: Optional[str] = None
    proof: Optional[str] = None


class StructuredCriterion(BaseModel):
    criterion_id: Optional[str] = None
    label: Optional[str] = None
    why: Optional[str] = None
    good: Optional[str] = None
    bad: Optional[str] = None


class StructuredDraftRequest(BaseModel):
    steps: list[StructuredStep] = Field(default_factory=list)
    objections: list[StructuredObjection] = Field(default_factory=list)
    # None = "not sent": the draft keeps the criteria it has. [] = the manager cleared them.
    qualification: Optional[list[StructuredCriterion]] = None
    base_updated_at: Optional[str] = None
    source_id: Optional[str] = None


def _editor_response(sales_motion_key: str, snapshot: dict) -> dict:
    """The one shape of GET /editor, PUT /draft and DELETE /draft. `source` stays the
    state of what is shown ("draft" | "published" | "empty", which the current editor
    reads); the material it was structured from is `source_doc` ({id, kind, name} | null)."""
    version = snapshot.get("version")
    return {
        "sales_motion_key": sales_motion_key,
        "source": snapshot["state"],
        "source_doc": snapshot.get("source"),
        "version_id": (version or {}).get("id"),
        "updated_at": (version or {}).get("updated_at"),
        "has_live": bool(snapshot.get("has_live")),
        "paused": bool(snapshot.get("paused")),
        "categories": list(OBJECTION_CATEGORIES),
        **editor_view(version),
    }


@router.get("/{sales_motion_key}/editor")
async def get_playbook_editor(
    sales_motion_key: str,
    supabase: Client = Depends(get_supabase),
    membership: Membership = Depends(get_membership),
):
    """The playbook as steps and objection answers. A Head of Sales gets the pending draft
    when there is one (else the live version); a rep only ever reads the live version,
    and only of a flow their role can see (D5)."""
    manager = membership.role in MANAGE_ROLES
    if (
        not manager
        and is_enabled(supabase, membership.company_id, SALES_ROLES_FLAG)
        and not visible_to_role(sales_motion_key, membership.sales_role)
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Playbook no encontrado")
    snapshot = get_playbook_repository().editor_snapshot(membership.company_id, sales_motion_key, include_draft=manager)
    return _editor_response(sales_motion_key, snapshot)


@router.put("/{sales_motion_key}/draft")
async def save_structured_playbook_draft(
    sales_motion_key: str,
    body: StructuredDraftRequest,
    membership: Membership = Depends(get_membership),
):
    """Saves the edited steps and objection answers as the draft: a pending draft is updated
    in place (autosave keeps one row), otherwise a new one is created. `base_updated_at` is
    the updated_at the editor last saw; if the draft has moved since, 409 `stale_draft`.
    Publishing it is the existing POST /{key}/publish. Validation errors are 422 with a
    code the UI translates."""
    _guard(membership)
    try:
        steps = normalize_steps([step.model_dump() for step in body.steps])
        entries = normalize_objections([item.model_dump() for item in body.objections])
        criteria = (
            normalize_qualification([item.model_dump() for item in body.qualification])
            if body.qualification is not None else None
        )
    except PlaybookDraftError as exc:
        detail = {"code": exc.code, "index": exc.index}
        if exc.field:
            detail["field"] = exc.field
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=detail) from exc
    repository = get_playbook_repository()
    try:
        repository.save_draft(
            membership.company_id,
            sales_motion_key,
            steps,
            entries,
            qualification=criteria,
            source_id=body.source_id,
            base_updated_at=body.base_updated_at,
        )
    except StaleDraftError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": exc.code}) from exc
    snapshot = repository.editor_snapshot(membership.company_id, sales_motion_key, include_draft=True)
    return _editor_response(sales_motion_key, snapshot)


@router.delete("/{sales_motion_key}/draft")
async def discard_structured_playbook_draft(
    sales_motion_key: str,
    membership: Membership = Depends(get_membership),
):
    """"Descartar cambios": deletes the pending draft (never a published version) and
    returns the editor as it is now: the live version, or empty."""
    _guard(membership)
    repository = get_playbook_repository()
    repository.discard_draft(membership.company_id, sales_motion_key)
    snapshot = repository.editor_snapshot(membership.company_id, sales_motion_key, include_draft=True)
    return _editor_response(sales_motion_key, snapshot)


def _lifecycle(action: str, sales_motion_key: str, supabase: Client, membership: Membership) -> dict:
    """Runs pause | resume | archive | restore for the company's type and answers like GET
    /playbooks. 409 {detail: {code}} when it does not apply as things are (not_published,
    not_paused, not_archived), 404 when the company has no such type (delete)."""
    _guard(membership)
    repository = get_playbook_repository()
    try:
        repository.set_state(membership.company_id, sales_motion_key, action)
    except LifecycleError as exc:
        if exc.code == "not_found":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Playbook no encontrado") from exc
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": exc.code}) from exc
    return _playbooks_payload(supabase, membership, repository)


@router.post("/{sales_motion_key}/pause")
async def pause_playbook(
    sales_motion_key: str,
    supabase: Client = Depends(get_supabase),
    membership: Membership = Depends(get_membership),
):
    """Owner/admin. New calls stop being evaluated with this playbook; its content stays."""
    return _lifecycle("pause", sales_motion_key, supabase, membership)


@router.post("/{sales_motion_key}/resume")
async def resume_playbook(
    sales_motion_key: str,
    supabase: Client = Depends(get_supabase),
    membership: Membership = Depends(get_membership),
):
    """Owner/admin. A paused playbook evaluates new calls again."""
    return _lifecycle("resume", sales_motion_key, supabase, membership)


@router.delete("/{sales_motion_key}")
async def delete_playbook(
    sales_motion_key: str,
    supabase: Client = Depends(get_supabase),
    membership: Membership = Depends(get_membership),
):
    """Owner/admin. "Eliminar playbook": soft, undoable with POST /{key}/restore. Calls already
    evaluated keep pointing at their version."""
    return _lifecycle("archive", sales_motion_key, supabase, membership)


@router.post("/{sales_motion_key}/restore")
async def restore_playbook(
    sales_motion_key: str,
    supabase: Client = Depends(get_supabase),
    membership: Membership = Depends(get_membership),
):
    """Owner/admin. Undo "Eliminar": back to the state it had (published, paused, empty)."""
    return _lifecycle("restore", sales_motion_key, supabase, membership)


class StructureRequest(BaseModel):
    kind: str
    payload: str = ""
    name: Optional[str] = None


_DEFAULT_SOURCE_NAMES = {
    "es": {"text": "Texto pegado", "pdf": "PDF", "audio": "Audio"},
    "en": {"text": "Pasted text", "pdf": "PDF", "audio": "Audio"},
}


def _unreadable(code: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail={"code": code})


async def _read_source(body: StructureRequest) -> str:
    """The text of what the manager gave us (pasted text, a PDF or an audio recording, read
    the way imports read them). 422 `detail.code`: pdf_encrypted, pdf_has_no_text,
    audio_has_no_speech, stt_unavailable, unsupported_source, empty_source."""
    stt = None
    if body.kind == "audio":
        try:
            spoken = await _audio_text(body.payload)
            stt = lambda _raw, spoken=spoken: spoken
        except Exception:
            stt = None
    record = start_import(
        import_id=f"source:{uuid.uuid4()}", kind=body.kind, payload=body.payload, active_version_id=None, stt=stt,
    )
    if record.get("status") != "ready":
        raise _unreadable(str(record.get("reason") or "unsupported_source"))
    text = str((record.get("draft") or {}).get("text") or "").strip()
    if not text:
        raise _unreadable("empty_source")
    return text


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
    _guard(membership)
    repository = get_playbook_repository()
    text = await _read_source(body)
    lang = detect_language(text)
    routing = routing_enabled(supabase, membership.company_id)
    motions, stored = motions_and_stored(repository.list_types(membership.company_id, include_draft=False))
    candidates = candidate_types(routing, motions, stored, lang)
    source = _keep_source(repository, membership, None, body, text, lang)
    result = await split_source(text, candidates, lang)

    found = {item["key"]: item for item in result["types"]}
    items, reasons = [], {}
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
            "entries": normalize_objections(item["objections"]),
            # A document without criteria must not wipe the ones already in the draft.
            "qualification": criteria or None,
            "ensure": ensure_payload(key, routing=routing, lang=lang),
        })
    existing, merged, filled = _merge_company(repository, membership.company_id, result.get("company"))
    source_id = (source or {}).get("id")
    saved = {"types": [], "knowledge": None}
    if items or filled:
        saved = repository.save_intake(membership.company_id, items, merged if filled else None, source_id)
    types = [
        {
            "sales_motion_key": entry["sales_motion_key"],
            "reason": reasons[entry["sales_motion_key"]],
            "editor": _editor_response(
                entry["sales_motion_key"],
                repository.editor_snapshot(membership.company_id, entry["sales_motion_key"], include_draft=True),
            ),
        }
        for entry in saved["types"]
    ]
    return {
        "source": source,
        "fallback": bool(result["fallback"]),
        "reason": result["reason"],
        "candidates": public_candidates(candidates),
        "types": types,
        "company": _company_payload(saved["knowledge"] or existing, merged, filled),
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
    membership: Membership = Depends(get_membership),
):
    """Turns pasted text, a PDF or an audio recording into steps and objection answers for
    this call type. Creates no version: the caller reviews the result and saves it as the
    draft. The material is kept as `source` so the playbook can link back to it. If the
    model fails the steps come from the line parser and `fallback` is true."""
    _guard(membership)
    repository = get_playbook_repository()
    text = await _read_source(body)
    lang = detect_language(text)
    source = _keep_source(repository, membership, sales_motion_key, body, text, lang)
    result = await structure_source(text, sales_motion_key, lang)
    return {"sales_motion_key": sales_motion_key, **result, "source": source}
