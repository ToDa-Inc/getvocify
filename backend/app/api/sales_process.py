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
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from supabase import Client

from app.api.playbooks import _playbooks_changed
from app.deps import get_membership, get_supabase
from app.services.company import Membership
from app.services.feature_flags import is_enabled
from app.services.playbooks.api_support import require_manager
from app.services.playbooks.catalog import catalog_label, catalog_order, catalog_types
from app.services.playbooks.repository import PlaybookRepository, get_playbook_repository
from app.services.playbooks.versions import LifecycleError
from app.services.sales_process.logic import slug_key, stage_for
from app.services.sales_process.store import SalesProcessStore, SalesProcessUnavailable, get_sales_process_store

logger = logging.getLogger(__name__)

FLAG = "SALES_PROCESS_ENABLED"
MAX_TYPES = 20
MAX_NAME = 60

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


class ProcessType(BaseModel):
    key: Optional[str] = Field(default=None, max_length=80)
    label: str = Field(max_length=MAX_NAME)
    stage: Literal["first_contact", "deal"]
    recognize: Optional[str] = Field(default=None, max_length=300)


class ProcessRequest(BaseModel):
    types: list[ProcessType] = Field(min_length=1, max_length=MAX_TYPES)


def _present_types(repository: PlaybookRepository, placed: set[str], company_id: str) -> dict[str, dict]:
    """The company's types that exist: it has a version of them, a name of its own for them, or it placed them in its process
    (a type created empty is still a type; a catalog type nobody created is not)."""
    return {
        key: row
        for key, row in repository.list_types(company_id).items()
        if row.get("status") != "missing" or row.get("label") or key in placed
    }


def process_view(repository: PlaybookRepository, store: SalesProcessStore, company_id: str) -> list[dict]:
    """The company's types in process order. A type the company never placed (an older one) follows the placed ones, in the
    order the catalog gives them, with the stage its role implies."""
    rows = store.list_process(company_id)
    placed = {r["key"] for r in rows}
    present = _present_types(repository, placed, company_id)
    ordered = [r["key"] for r in rows if r["key"] in present] + sorted((key for key in present if key not in placed), key=catalog_order)
    return [
        {
            "key": key,
            "label": present[key].get("label") or catalog_label(key, "es") or key,
            "stage": stage_for(key, rows),
            "recognize": present[key].get("recognize"),
            "position": index + 1,
            "step_count": present[key].get("step_count", 0),
            "status": present[key].get("status"),
        }
        for index, key in enumerate(ordered)
    ]


def apply_process(repository: PlaybookRepository, store: SalesProcessStore, company_id: str, wanted: list[ProcessType]) -> None:
    """Makes the company's types exactly `wanted`, in that order. New names get a fresh key (never a catalog key, which
    would bring that catalog type's behaviour with it); a type that is not in the list is archived and leaves every
    member's list. Raises ValueError("duplicate_name") when two names are the same."""
    names = [t.label.strip().casefold() for t in wanted]
    if "" in names or len(set(names)) != len(names):
        raise ValueError("duplicate_name" if "" not in names else "empty_name")
    present = _present_types(repository, {r["key"] for r in store.list_process(company_id)}, company_id)
    taken = set(present) | {t["key"] for t in catalog_types()}
    rows: list[dict] = []
    for position, item in enumerate(wanted, start=1):
        label = item.label.strip()
        key = item.key if item.key in present else None
        recognize = (item.recognize or "").strip() or None
        if key is None:
            key = slug_key(label, taken)
            taken.add(key)
            repository.add_type(company_id, key, label, label=label, recognize=recognize)
        else:
            repository.set_meta(company_id, key, label=label, recognize=recognize)
        rows.append({"key": key, "position": position, "stage": item.stage})
    kept = {r["key"] for r in rows}
    for key in present:
        if key not in kept:
            try:
                repository.set_state(company_id, key, "archive")
            except LifecycleError:
                logger.info("type %s could not be archived", key)
            store.drop_type(company_id, key)
    store.replace_process(company_id, rows)


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
        apply_process(repository, store, membership.company_id, body.types)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail={"code": str(exc)}) from exc
    _playbooks_changed(membership.company_id)
    return {"types": process_view(repository, store, membership.company_id)}
