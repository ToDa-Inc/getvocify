"""The company's types as an ordered process: reading it and making it what the Head of Sales asked for."""

from __future__ import annotations

import logging
from typing import Literal, Optional

from pydantic import BaseModel, Field

from app.services.playbooks.catalog import catalog_label, catalog_order, catalog_types
from app.services.playbooks.repository import PlaybookRepository
from app.services.playbooks.versions import LifecycleError
from app.services.sales_process.logic import slug_key, stage_for
from app.services.sales_process.store import SalesProcessStore

logger = logging.getLogger(__name__)

MAX_TYPES = 20
MAX_NAME = 60


class ProcessType(BaseModel):
    key: Optional[str] = Field(default=None, max_length=80)
    label: str = Field(max_length=MAX_NAME)
    stage: Literal["first_contact", "deal", "other"]
    # What the call must achieve ("create interest and agree a meeting") and what kind of call it is ("a first phone contact").
    # Both are required for a type of the sales funnel; a call outside it needs neither. The description is `recognize`.
    goal: Optional[str] = Field(default=None, max_length=160)
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
            "goal": next((r.get("goal") for r in rows if r["key"] == key), None),
            "position": index + 1,
            "step_count": present[key].get("step_count", 0),
            "status": present[key].get("status"),
        }
        for index, key in enumerate(ordered)
    ]


def apply_process(repository: PlaybookRepository, store: SalesProcessStore, company_id: str, wanted: list[ProcessType]) -> None:
    """Makes the company's types exactly `wanted`, in that order. New names get a fresh key (never a catalog key, which
    would bring that catalog type's behaviour with it); a type that is not in the list is archived and leaves every
    member's list. Raises ValueError (`duplicate_name`, `empty_name`, `goal_required`, `description_required`) before changing anything."""
    names = [t.label.strip().casefold() for t in wanted]
    if "" in names or len(set(names)) != len(names):
        raise ValueError("duplicate_name" if "" not in names else "empty_name")
    for item in wanted:
        if item.stage != "other":
            if not (item.goal or "").strip():
                raise ValueError("goal_required")
            if not (item.recognize or "").strip():
                raise ValueError("description_required")
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
        rows.append({"key": key, "position": position, "stage": item.stage, "goal": (item.goal or "").strip() or None})
    kept = {r["key"] for r in rows}
    for key in present:
        if key not in kept:
            try:
                repository.set_state(company_id, key, "archive")
            except LifecycleError:
                logger.info("type %s could not be archived", key)
            store.drop_type(company_id, key)
    store.replace_process(company_id, rows)
