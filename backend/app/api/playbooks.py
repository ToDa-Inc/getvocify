"""Playbook import API. Members cannot write. Imports never publish."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Literal, Optional

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
from app.services.playbooks import channel_types
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
    # Types by channel: the channels the type belongs to (instead of a role rule), and how to recognise it.
    channels: Optional[list[Literal["call", "meeting"]]] = Field(default=None, max_length=2)
    recognize: Optional[str] = Field(default=None, max_length=300)


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
    if key and is_enabled(supabase, membership.company_id, channel_types.FLAG):
        return _create_by_channel(supabase, membership, repository, key, body)
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


def _by_channel_rule(key: str, applies_to: Optional[dict], channels: Optional[list[str]]) -> dict:
    """Types by channel: the rule a type is saved with. No role ever; the channels given win, else the
    rule's, else the catalog's. A type with no channel at all is 422 channel_required."""
    try:
        rule = validate_applies_to(applies_to) if applies_to is not None else default_applies_to(key)
    except RuleError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail={"code": exc.code}) from exc
    rule = {**(rule or {"contact": "any", "deal_stages": []}), "role": "any"}
    if channels:
        rule["channels"] = list(dict.fromkeys(channels))
    rule["channels"] = [channel for channel in rule.get("channels") or [] if channel in channel_types.CHANNELS]
    if not rule["channels"]:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail={"code": "channel_required"})
    return validate_applies_to(rule)


def _require_by_channel(supabase: Client, membership: Membership) -> None:
    """The types-by-channel endpoints are not there for a company without the flag."""
    if not is_enabled(supabase, membership.company_id, channel_types.FLAG):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")


def _create_by_channel(supabase: Client, membership: Membership, repository: PlaybookRepository, key: str, body: TypeRequest):
    rule = _by_channel_rule(key, body.applies_to, body.channels)
    label = body.name.strip() or catalog_label(key) or None
    try:
        repository.add_type(
            membership.company_id, key, body.name or key, label=label, applies_to=rule,
            **({"recognize": body.recognize} if body.recognize is not None else {}),
        )
    except PublishError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="La tipología necesita una clave") from exc
    return _playbooks_payload(supabase, membership, repository)


class TypeEdit(BaseModel):
    """Types by channel: what Settings edits on a type. Only the fields sent change."""
    label: Optional[str] = Field(default=None, max_length=80)
    channels: Optional[list[Literal["call", "meeting"]]] = Field(default=None, min_length=1, max_length=2)
    recognize: Optional[str] = Field(default=None, max_length=300)


@router.patch("/{sales_motion_key}/type")
async def edit_type(
    sales_motion_key: str,
    body: TypeEdit,
    supabase: Client = Depends(get_supabase),
    membership: Membership = Depends(get_membership),
):
    _require_by_channel(supabase, membership)
    if not can_publish(membership.role):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Solo owner o admin pueden cambiar una tipología")
    repository = get_playbook_repository()
    key = sales_motion_key.strip()
    row = repository.list_types(membership.company_id, include_draft=False).get(key)
    if not key or row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tipología no encontrada")
    meta: dict[str, Any] = {}
    if body.label is not None:
        meta["label"] = body.label.strip() or None
    if body.recognize is not None:
        meta["recognize"] = body.recognize
    if body.channels is not None:
        meta["applies_to"] = _by_channel_rule(key, row.get("applies_to"), body.channels)
    if meta:
        repository.set_meta(membership.company_id, key, **meta)
    return _playbooks_payload(supabase, membership, repository)


class RecognizeDraftRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)
    channels: list[Literal["call", "meeting"]] = Field(default_factory=list, max_length=2)
    language: Literal["es", "en"] = "es"


_RECOGNIZE_SYSTEM = """You help a sales team describe one kind of sales conversation so an AI can recognise it from a transcript.
Write ONE short sentence (max 25 words) saying what makes this kind of conversation different: who the other side is
and where the relationship stands. No steps, no advice. Write it in the requested language.
Return only JSON: {"recognize": "<sentence>"}"""


async def _ask_recognize(messages: list[dict]) -> Any:
    from app.config import settings
    from app.services.llm import LLMClient

    return await LLMClient().chat_json(
        messages, model=settings.COPILOT_MODEL, temperature=0.2, timeout=8.0, max_retries=0, reasoning_effort="minimal",
    )


@router.post("/types/recognize")
async def draft_recognize(
    body: RecognizeDraftRequest,
    supabase: Client = Depends(get_supabase),
    membership: Membership = Depends(get_membership),
):
    """Vocify's draft of a type's "how to recognise it" sentence, from its name and channels. The
    person edits or keeps it; nothing is saved here. {recognize: null} when the model fails."""
    _require_by_channel(supabase, membership)
    if not can_publish(membership.role):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Solo owner o admin pueden cambiar una tipología")
    channels = ", ".join(body.channels) or "call or meeting"
    language = "Spanish" if body.language == "es" else "English"
    messages = [
        {"role": "system", "content": _RECOGNIZE_SYSTEM},
        {"role": "user", "content": f"Type name: {body.name.strip()}\nChannel: {channels}\nLanguage: {language}"},
    ]
    try:
        raw = await _ask_recognize(messages)
    except Exception:
        logger.warning("recognize draft failed", exc_info=True)
        return {"recognize": None}
    sentence = " ".join(str((raw or {}).get("recognize") or "").split()) if isinstance(raw, dict) else ""
    return {"recognize": sentence[:300] or None}


STATS_DAYS = 30
_STATS_LIMIT = 5000


@router.get("/type-stats")
async def type_stats(
    supabase: Client = Depends(get_supabase),
    membership: Membership = Depends(get_membership),
):
    """Per type, the company's interactions in the last 30 days and how many a person changed after
    Vocify typed them (a manual pin that names what it replaced). What a manager reads to see which
    type's sentence needs work."""
    require_manager(membership)
    _require_by_channel(supabase, membership)
    since = (datetime.now(timezone.utc) - timedelta(days=STATS_DAYS)).isoformat()
    rows = (
        supabase.table("memos")
        .select("sales_motion_key,pipeline_meta")
        .eq("company_id", str(membership.company_id))
        .gte("created_at", since)
        .limit(_STATS_LIMIT)
        .execute()
    ).data or []
    out: dict[str, dict[str, int]] = {}
    for row in rows:
        key = row.get("sales_motion_key")
        if not key:
            continue
        entry = out.setdefault(str(key), {"count": 0, "corrected": 0})
        entry["count"] += 1
        meta = row.get("pipeline_meta")
        pin = meta.get("playbook_pin") if isinstance(meta, dict) else None
        if isinstance(pin, dict) and pin.get("source") == "manual" and pin.get("changed_from"):
            entry["corrected"] += 1
    return {"days": STATS_DAYS, "types": out}


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
    if is_enabled(supabase, membership.company_id, channel_types.FLAG):
        # Types by channel: every member sees every type (no role), each with its channels and sentence,
        # and Settings says whether detection runs (it needs the call reading too).
        for key, detail in details.items():
            detail["channels"] = sorted(channel_types.type_channels(key, types[key].get("applies_to")) & channel_types.CHANNELS)
            detail["recognize"] = types[key].get("recognize")
        on = channel_types.enabled(supabase, membership.company_id)
        return {"motions": motions, "details": details, "type_detection": {"by_channel": on, "call_reading": on or is_enabled(
            supabase, membership.company_id, channel_types.CALL_READING_FLAG)}}
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
