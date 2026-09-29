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
from app.services.playbooks.imports import start_import
from app.services.playbooks.motion import goal_for, visible_to_role
from app.services.playbooks.structure import detect_language, set_playbook_structure_llm, structure_source
from app.services.playbooks.structured import (
    OBJECTION_CATEGORIES,
    PlaybookDraftError,
    editor_view,
    normalize_objections,
    normalize_steps,
)
from app.services.playbooks.store import MemoryPlaybookStore
from app.services.playbooks.versions import PublishError, can_publish

SALES_ROLES_FLAG = "SALES_ROLES_ENABLED"
MANAGE_ROLES = frozenset({"owner", "admin"})

logger = logging.getLogger(__name__)

__all__ = ["router", "set_playbook_store", "set_playbook_transcriber", "set_playbook_structure_llm"]

router = APIRouter(prefix="/api/v1/playbooks", tags=["playbooks"])

_IMPORTS: dict[str, dict] = {}
_MOTIONS: dict[str, dict[str, str]] = {}
_LATEST: dict[tuple[str, str], dict] = {}
_ACTIVATED: dict[tuple[str, str], str] = {}
_STRUCTURED: dict[tuple[str, str], dict] = {}
_PUBLISHED_VERSIONS: dict[tuple[str, str], dict] = {}
_store = None
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


def get_playbook_store():
    if _store is not None:
        return _store
    return MemoryPlaybookStore(_MOTIONS, _IMPORTS, _LATEST, _ACTIVATED, _STRUCTURED, _PUBLISHED_VERSIONS)


def set_playbook_store(store) -> None:
    global _store
    _store = store


class TypeRequest(BaseModel):
    type_key: str
    name: str = ""


@router.post("/types")
async def create_type(body: TypeRequest, membership: Membership = Depends(get_membership)):
    try:
        motions = get_playbook_store().add_type(
            membership.company_id,
            body.type_key,
            body.name or body.type_key,
            membership.role,
        )
    except PublishError as exc:
        if exc.code == "forbidden":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Solo owner o admin pueden añadir una tipología")
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="La tipología necesita una clave")
    return {"motions": motions}


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
    store = get_playbook_store()
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
        existing=store.get_import(membership.company_id, body.import_id),
        stt=stt,
    )
    if body.sales_motion_key:
        record = {**record, "sales_motion_key": body.sales_motion_key}
    store.save_import(membership.company_id, record, body.sales_motion_key)
    return record


@router.get("")
async def list_playbooks(
    supabase: Client = Depends(get_supabase),
    membership: Membership = Depends(get_membership),
):
    motions = get_playbook_store().motions(membership.company_id)
    if not is_enabled(supabase, membership.company_id, SALES_ROLES_FLAG):
        return {"motions": motions}
    if membership.role not in MANAGE_ROLES:
        motions = {
            key: status_
            for key, status_ in motions.items()
            if visible_to_role(key, membership.sales_role)
        }
    goals = {key: goal_for(key) for key in motions if goal_for(key)}
    return {"motions": motions, "goals": goals}


@router.post("/{sales_motion_key}/publish")
async def publish_motion(sales_motion_key: str, membership: Membership = Depends(get_membership)):
    try:
        updated = get_playbook_store().publish(membership.company_id, sales_motion_key, membership.role)
    except PublishError as exc:
        if exc.code == "forbidden":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Solo owner o admin pueden publicar")
        if exc.code == "contradiction":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Hay pasos contradictorios. Edita el borrador antes de publicar.",
            )
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="No hay un borrador para publicar")
    return {"motions": updated, "activated": get_playbook_store().activated(membership.company_id)}


@router.get("/imports/{import_id}")
async def get_import(import_id: str, membership: Membership = Depends(get_membership)):
    record = get_playbook_store().get_import(membership.company_id, import_id)
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


class StructuredDraftRequest(BaseModel):
    steps: list[StructuredStep] = Field(default_factory=list)
    objections: list[StructuredObjection] = Field(default_factory=list)


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
    store = get_playbook_store()
    source, version = store.editor_version(membership.company_id, sales_motion_key, include_draft=manager)
    view = editor_view(version)
    return {
        "sales_motion_key": sales_motion_key,
        "source": source,
        "version_id": (version or {}).get("id"),
        "categories": list(OBJECTION_CATEGORIES),
        **view,
    }


@router.put("/{sales_motion_key}/draft")
async def save_structured_playbook_draft(
    sales_motion_key: str,
    body: StructuredDraftRequest,
    membership: Membership = Depends(get_membership),
):
    """Saves the edited steps and objection answers as a new draft. Publishing it is the
    existing POST /{key}/publish. Validation errors are 422 with a code the UI translates."""
    _guard(membership)
    try:
        steps = normalize_steps([step.model_dump() for step in body.steps])
        entries = normalize_objections([item.model_dump() for item in body.objections])
    except PlaybookDraftError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": exc.code, "index": exc.index},
        ) from exc
    version = get_playbook_store().save_structured_draft(membership.company_id, sales_motion_key, steps, entries)
    return {
        "sales_motion_key": sales_motion_key,
        "source": "draft",
        "version_id": version.get("id"),
        "categories": list(OBJECTION_CATEGORIES),
        **editor_view({"steps": steps, "entries": entries}),
    }


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
    store = get_playbook_store()
    import_id = f"source:{uuid.uuid4()}"
    stt = None
    if body.kind == "audio":
        try:
            spoken = await _audio_text(body.payload)
            stt = lambda _raw, spoken=spoken: spoken
        except Exception:
            stt = None
    record = start_import(
        import_id=import_id, kind=body.kind, payload=body.payload, active_version_id=None, stt=stt,
    )
    if record.get("status") != "ready":
        raise _unreadable(str(record.get("reason") or "unsupported_source"))
    text = str((record.get("draft") or {}).get("text") or "").strip()
    if not text:
        raise _unreadable("empty_source")

    lang = detect_language(text)
    name = (body.name or "").strip()[:200] or _DEFAULT_SOURCE_NAMES[lang].get(body.kind, body.kind)
    try:
        source = store.save_source(membership.company_id, sales_motion_key, body.kind, name, text)
    except Exception:  # keeping the original is a courtesy; it never blocks structuring
        logger.exception("playbook source not saved")
        source = None
    result = await structure_source(text, sales_motion_key, lang)
    return {"sales_motion_key": sales_motion_key, **result, "source": source}
