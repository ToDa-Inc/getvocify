"""Playbook import API. Members cannot write. Imports never publish."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.deps import get_membership
from app.services.company import Membership
from app.services.playbooks.imports import start_import
from app.services.playbooks.versions import can_publish

router = APIRouter(prefix="/api/v1/playbooks", tags=["playbooks"])

_IMPORTS: dict[str, dict] = {}


class ImportRequest(BaseModel):
    import_id: str
    kind: str
    payload: str = ""
    active_version_id: Optional[str] = None


def _guard(membership: Membership) -> None:
    if not can_publish(membership.role):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Solo owner o admin pueden importar un playbook")


@router.post("/imports")
async def create_import(body: ImportRequest, membership: Membership = Depends(get_membership)):
    _guard(membership)
    record = start_import(
        import_id=body.import_id,
        kind=body.kind,
        payload=body.payload,
        active_version_id=body.active_version_id,
        existing=_IMPORTS.get(body.import_id),
    )
    _IMPORTS[body.import_id] = record
    return record


@router.get("/imports/{import_id}")
async def get_import(import_id: str, membership: Membership = Depends(get_membership)):
    del membership
    record = _IMPORTS.get(import_id)
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Importación no encontrada")
    return record
