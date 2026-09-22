"""Playbook import API. Members cannot write. Imports never publish."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.deps import get_membership
from app.services.company import Membership
from app.services.playbooks.imports import start_import
from app.services.playbooks.versions import PublishError, accept_publish, can_publish

router = APIRouter(prefix="/api/v1/playbooks", tags=["playbooks"])

_IMPORTS: dict[str, dict] = {}
_MOTIONS: dict[str, dict[str, str]] = {}


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
    record = start_import(
        import_id=body.import_id,
        kind=body.kind,
        payload=body.payload,
        active_version_id=body.active_version_id,
        existing=_IMPORTS.get(body.import_id),
    )
    _IMPORTS[body.import_id] = record
    if body.sales_motion_key and record.get("status") == "ready" and not record.get("published"):
        company = _MOTIONS.setdefault(membership.company_id, {})
        if company.get(body.sales_motion_key) != "published":
            company[body.sales_motion_key] = "draft"
    return record


@router.get("")
async def list_playbooks(membership: Membership = Depends(get_membership)):
    return {"motions": dict(_MOTIONS.get(membership.company_id) or {})}


@router.post("/{sales_motion_key}/publish")
async def publish_motion(sales_motion_key: str, membership: Membership = Depends(get_membership)):
    motions = dict(_MOTIONS.get(membership.company_id) or {})
    try:
        updated = accept_publish(motions, sales_motion_key, membership.role)
    except PublishError as exc:
        if exc.code == "forbidden":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Solo owner o admin pueden publicar")
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="No hay un borrador para publicar")
    _MOTIONS.setdefault(membership.company_id, {})[sales_motion_key] = "published"
    return {"motions": updated}


@router.get("/imports/{import_id}")
async def get_import(import_id: str, membership: Membership = Depends(get_membership)):
    del membership
    record = _IMPORTS.get(import_id)
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Importación no encontrada")
    return record
