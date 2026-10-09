"""Playbooks: "Vuestra empresa", what Vocify knows about the company, once (ICP, value story, proof, competitors).

Registered before app.api.playbooks so /company is never read as a `/{sales_motion_key}` route."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from supabase import Client

from app.deps import get_membership, get_supabase
from app.services.company import Membership
from app.services.playbooks.api_support import StructureRequest, fill_failed, product_context, read_source
from app.services.playbooks.fill import FillError, fill_company
from app.services.playbooks.knowledge import StaleKnowledgeError, normalize_knowledge, sections
from app.services.playbooks.repository import get_playbook_repository
from app.services.playbooks.versions import can_publish

router = APIRouter(prefix="/api/v1/playbooks", tags=["playbooks"])


def _company_response(row: Optional[dict]) -> dict:
    data = normalize_knowledge((row or {}).get("data"))
    return {"knowledge": data, "updated_at": (row or {}).get("updated_at"), "sections": sections(data)}


@router.get("/company")
async def get_company_knowledge(membership: Membership = Depends(get_membership)):
    """What Vocify knows about this company (any member of it). Empty, with updated_at null,
    when nothing was saved yet."""
    return _company_response(get_playbook_repository().get_knowledge(membership.company_id))


def _require_editor(membership: Membership) -> None:
    if not can_publish(membership.role):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Solo owner o admin pueden editar Vuestra empresa")


class CompanyKnowledgeRequest(BaseModel):
    knowledge: dict
    base_updated_at: Optional[str] = None


@router.put("/company")
async def put_company_knowledge(
    body: CompanyKnowledgeRequest,
    membership: Membership = Depends(get_membership),
):
    """Owner/admin. Replaces the company's knowledge; it takes effect at once (no draft).
    Unknown keys are dropped and long texts clipped. `base_updated_at` from the last read: if
    someone saved since, 409 `stale_knowledge`."""
    _require_editor(membership)
    try:
        row = get_playbook_repository().save_knowledge(
            membership.company_id, normalize_knowledge(body.knowledge), base_updated_at=body.base_updated_at,
        )
    except StaleKnowledgeError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": exc.code}) from exc
    return _company_response(row)


class CompanyFillRequest(StructureRequest):
    base_updated_at: Optional[str] = None
    # A "Completar" on one item or some fields: only that part may change (see fill.restrict_company).
    scope: Optional[dict] = None


@router.post("/company/fill")
async def fill_company_knowledge(
    body: CompanyFillRequest,
    supabase: Client = Depends(get_supabase),
    membership: Membership = Depends(get_membership),
):
    """Owner/admin. "Dile a Vocify" for the company's notes: the request (text, a PDF or an audio
    note) is applied to what is stored and saved at once, like a PUT (same 409 `stale_knowledge`).
    -> the GET shape plus `filled` (keys that changed) and `summary`. 422 `fill_failed` when the
    model could not do it; nothing is saved."""
    _require_editor(membership)
    repository = get_playbook_repository()
    text = await read_source(body)
    existing = (repository.get_knowledge(membership.company_id) or {}).get("data")
    try:
        result = await fill_company(text, existing, product_context(supabase, membership.company_id), scope=body.scope)
    except FillError as exc:
        raise fill_failed() from exc
    row = None
    if result["filled"]:
        try:
            row = repository.save_knowledge(membership.company_id, result["knowledge"], base_updated_at=body.base_updated_at)
        except StaleKnowledgeError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": exc.code}) from exc
    else:
        row = repository.get_knowledge(membership.company_id)
    return {**_company_response(row), "filled": result["filled"], "summary": result["summary"]}

