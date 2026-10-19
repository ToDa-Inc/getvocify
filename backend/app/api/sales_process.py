"""The company's own sales process (spec 2026-10-17-proceso-de-venta-editable-design): the interaction types it names and
orders, what each one is for, and which of them each member runs.

Owner/admin only and dark behind SALES_PROCESS_ENABLED (404 without it). Until the tables of migration 084 exist the answer
is 503 `not_activated`. A type is still a playbook type (its steps, objections and versions are what they always were); this
adds its place in the process and its `stage`.

  GET /sales-process     the types in order: {key, label, stage, recognize, position, step_count, status}
  PUT /sales-process     the whole list: creates, renames, orders, describes and removes types in one go
"""

from __future__ import annotations

import functools
import logging

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from supabase import Client

from app.api.playbooks import _playbooks_changed
from app.deps import get_membership, get_supabase
from app.services.company import CompanyService, Membership
from app.services.feature_flags import is_enabled
from app.services.playbooks.api_support import require_manager
from app.services.playbooks.repository import PlaybookRepository, get_playbook_repository
from app.services.sales_process.members import set_member_types
from app.services.sales_process.process import MAX_NAME, MAX_TYPES, ProcessRequest, ProcessType, apply_process, process_view, within_scope  # noqa: F401 (re-exported)
from app.services.sales_process.store import SalesProcessStore, SalesProcessUnavailable, get_sales_process_store

logger = logging.getLogger(__name__)

FLAG = "SALES_PROCESS_ENABLED"
router = APIRouter(prefix="/api/v1/sales-process", tags=["sales-process"])


def _gate(supabase: Client, membership: Membership) -> SalesProcessStore:
    require_manager(membership)
    if not is_enabled(supabase, membership.company_id, FLAG):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return get_sales_process_store(supabase)


def _mapped(fn):
    """Runs the handler in the threadpool (its database calls are synchronous) and turns "tables missing" into a calm 503."""

    @functools.wraps(fn)
    async def wrapper(*args, **kwargs):
        try:
            return await run_in_threadpool(fn, *args, **kwargs)
        except SalesProcessUnavailable as exc:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail={"code": "not_activated"}) from exc

    return wrapper


@router.get("")
@_mapped
def get_process(supabase: Client = Depends(get_supabase), membership: Membership = Depends(get_membership)):
    store = _gate(supabase, membership)
    return {"types": process_view(get_playbook_repository(), store, membership.company_id)}


@router.put("")
@_mapped
def put_process(body: ProcessRequest, supabase: Client = Depends(get_supabase), membership: Membership = Depends(get_membership)):
    """The whole list at once. -> {types} as GET shows them."""
    store = _gate(supabase, membership)
    repository = get_playbook_repository()
    try:
        wanted = within_scope(process_view(repository, store, membership.company_id), body.scope, body.types)
        apply_process(repository, store, membership.company_id, wanted)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail={"code": str(exc)}) from exc
    _playbooks_changed(membership.company_id)
    return {"types": process_view(repository, store, membership.company_id)}


class MemberTypes(BaseModel):
    types: Optional[list[str]] = None


@router.get("/members")
@_mapped
def get_member_types(supabase: Client = Depends(get_supabase), membership: Membership = Depends(get_membership)):
    """What each member and each pending invitation runs: {members: {user_id: types | null}, invitations: {...}}. null = all."""
    return _gate(supabase, membership).list_member_types(membership.company_id)


@router.put("/members/{member_id}")
@_mapped
def put_member_types(
    member_id: str, body: MemberTypes, supabase: Client = Depends(get_supabase), membership: Membership = Depends(get_membership),
):
    """Sets the types a member runs (`member_id` is the member row, as in the team page) -> {types, sales_role}. The role the
    rest of the product reads is written from them."""
    store = _gate(supabase, membership)
    return set_member_types(store, get_playbook_repository(), CompanyService(supabase), membership, membership.company_id, member_id, body.types)
