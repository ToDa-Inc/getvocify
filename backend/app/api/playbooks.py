"""Playbook import API. Members cannot write. Imports never publish."""

from __future__ import annotations

import asyncio
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.deps import get_membership
from app.services.company import Membership
from app.services.playbooks.imports import start_import
from app.services.playbooks.store import MemoryPlaybookStore
from app.services.playbooks.versions import PublishError, can_publish

router = APIRouter(prefix="/api/v1/playbooks", tags=["playbooks"])

_IMPORTS: dict[str, dict] = {}
_MOTIONS: dict[str, dict[str, str]] = {}
_LATEST: dict[tuple[str, str], dict] = {}
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
    return MemoryPlaybookStore(_MOTIONS, _IMPORTS, _LATEST)


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
        existing=store.get_import(body.import_id),
        stt=stt,
    )
    if body.sales_motion_key:
        record = {**record, "sales_motion_key": body.sales_motion_key}
    store.save_import(membership.company_id, record, body.sales_motion_key)
    return record


@router.get("")
async def list_playbooks(membership: Membership = Depends(get_membership)):
    return {"motions": get_playbook_store().motions(membership.company_id)}


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
    return {"motions": updated}


@router.get("/imports/{import_id}")
async def get_import(import_id: str, membership: Membership = Depends(get_membership)):
    del membership
    record = get_playbook_store().get_import(import_id)
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Importación no encontrada")
    return record
