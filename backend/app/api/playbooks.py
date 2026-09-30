"""Playbook import API. Members cannot write. Imports never publish."""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from supabase import Client

from app.deps import get_membership, get_supabase
from app.services.playbooks.api_support import (
    MANAGE_ROLES,
    SALES_ROLES_FLAG,
    audio_text,
    editor_response,
    require_manager,
    set_playbook_transcriber,
)
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
from app.services.playbooks.motion import goal_for, visible_to_role
from app.services.playbooks.repository import (
    PlaybookRepository,
    get_playbook_repository,
    set_playbook_repository,
)
from app.services.playbooks.routing import build_details, motions_and_stored
from app.services.playbooks.structured import (
    PlaybookDraftError,
    normalize_objections,
    normalize_qualification,
    normalize_steps,
)
from app.services.playbooks.versions import LifecycleError, PublishError, StaleDraftError, can_publish


logger = logging.getLogger(__name__)

__all__ = ["router", "set_playbook_repository", "set_playbook_transcriber"]

router = APIRouter(prefix="/api/v1/playbooks", tags=["playbooks"])

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


@router.post("/imports")
async def create_import(body: ImportRequest, membership: Membership = Depends(get_membership)):
    require_manager(membership)
    repository = get_playbook_repository()
    stt = None
    if body.kind == "audio":
        try:
            spoken = await audio_text(body.payload)
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
    return editor_response(sales_motion_key, snapshot)


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
    require_manager(membership)
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
    return editor_response(sales_motion_key, snapshot)


@router.delete("/{sales_motion_key}/draft")
async def discard_structured_playbook_draft(
    sales_motion_key: str,
    membership: Membership = Depends(get_membership),
):
    """"Descartar cambios": deletes the pending draft (never a published version) and
    returns the editor as it is now: the live version, or empty."""
    require_manager(membership)
    repository = get_playbook_repository()
    repository.discard_draft(membership.company_id, sales_motion_key)
    snapshot = repository.editor_snapshot(membership.company_id, sales_motion_key, include_draft=True)
    return editor_response(sales_motion_key, snapshot)


def _lifecycle(action: str, sales_motion_key: str, supabase: Client, membership: Membership) -> dict:
    """Runs pause | resume | archive | restore for the company's type and answers like GET
    /playbooks. 409 {detail: {code}} when it does not apply as things are (not_published,
    not_paused, not_archived), 404 when the company has no such type (delete)."""
    require_manager(membership)
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
