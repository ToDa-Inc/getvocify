"""Playbooks v2 fase 2: the call-type catalog, the "when it applies" rule of a type, and the CRM
stages a rule can name.

Registered before app.api.playbooks so /catalog and /deal-stages are never read as a
`/{sales_motion_key}` route.
"""

from __future__ import annotations

import logging
import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from supabase import Client

from app.api.playbooks import get_playbook_store
from app.deps import get_membership, get_supabase
from app.services.company import Membership
from app.services.playbooks.catalog import RuleError, catalog_types, is_catalog, validate_applies_to
from app.services.playbooks.versions import can_publish

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/playbooks", tags=["playbooks"])

DEAL_STAGES_TTL = 300.0
_STAGES_CACHE: dict[str, tuple[float, list[dict]]] = {}


def clear_deal_stages_cache() -> None:
    _STAGES_CACHE.clear()


@router.get("/catalog")
async def get_catalog(membership: Membership = Depends(get_membership)):
    """The call types Vocify ships: role, goal, default rule, name and starter steps (es/en)."""
    del membership
    return {"types": catalog_types()}


class RuleRequest(BaseModel):
    applies_to: dict


@router.put("/{sales_motion_key}/rule")
async def put_rule(
    sales_motion_key: str,
    body: RuleRequest,
    membership: Membership = Depends(get_membership),
):
    if not can_publish(membership.role):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Solo owner o admin pueden cambiar cuándo se aplica")
    key = sales_motion_key.strip()
    store = get_playbook_store()
    if not key or (key not in store.motions(membership.company_id) and not is_catalog(key)):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Playbook no encontrado")
    try:
        rule = validate_applies_to(body.applies_to)
    except RuleError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail={"code": exc.code}) from exc
    store.save_type_meta(membership.company_id, key, applies_to=rule)
    return {"sales_motion_key": key, "applies_to": rule}


async def _crm_stages(supabase: Client, user_id: str) -> list[dict]:
    """The deal stages of the company's connected CRM (HubSpot, else Pipedrive), flattened.
    With more than one pipeline a stage is named "Pipeline · Stage". Raises when there is
    no connection or the CRM does not answer."""
    from app.api import crm, crm_pipedrive

    last: Optional[Exception] = None
    for read in (crm.get_hubspot_pipelines, crm_pipedrive.pipedrive_pipelines):
        try:
            pipelines = await read(supabase=supabase, user_id=user_id)
        except Exception as exc:
            last = exc
            continue
        many = len(pipelines) > 1
        out: list[dict] = []
        seen: set[str] = set()
        for pipeline in pipelines:
            for stage in sorted(pipeline.stages, key=lambda s: getattr(s, "displayOrder", 0) or getattr(s, "display_order", 0) or 0):
                stage_id = str(stage.id)
                if stage_id in seen:
                    continue
                seen.add(stage_id)
                label = str(stage.label or stage_id)
                out.append({"id": stage_id, "label": f"{pipeline.label} · {label}" if many else label})
        return out
    raise last or RuntimeError("no CRM connected")


@router.get("/deal-stages")
async def get_deal_stages(
    supabase: Client = Depends(get_supabase),
    membership: Membership = Depends(get_membership),
):
    """Stages a rule can name. [] with no CRM connected, or when reading it fails."""
    company_id = str(membership.company_id)
    hit = _STAGES_CACHE.get(company_id)
    if hit and time.monotonic() - hit[0] < DEAL_STAGES_TTL:
        return {"stages": hit[1]}
    try:
        stages = await _crm_stages(supabase, membership.user_id)
    except Exception:
        logger.info("deal stages unavailable", exc_info=True)
        return {"stages": []}
    if stages:
        _STAGES_CACHE[company_id] = (time.monotonic(), stages)
    return {"stages": stages}
