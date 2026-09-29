"""Playbooks v2 fase 2: the call-type catalog, the "when it applies" rule of a type, the CRM
stages a rule can name, and correcting which playbook a recording was evaluated with.

Registered before app.api.playbooks so /catalog and /deal-stages are never read as a
`/{sales_motion_key}` route.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from supabase import Client

from app.api.playbooks import MANAGE_ROLES, get_playbook_store
from app.deps import get_membership, get_supabase, get_user_id
from app.services.company import Membership
from app.services.playbooks.catalog import RuleError, catalog_order, catalog_types, is_catalog, validate_applies_to
from app.services.playbooks.routing import merge_pin_meta, routing_enabled
from app.services.playbooks.versions import can_publish

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/playbooks", tags=["playbooks"])
memo_router = APIRouter(prefix="/api/v1/memos", tags=["playbooks"])

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


# -- T10: the playbook a recording was evaluated with -------------------------------------


class MemoPlaybookRequest(BaseModel):
    sales_motion_key: str


def _load_memo(supabase: Client, memo_id: str) -> Optional[dict]:
    rows = (supabase.table("memos").select("*").eq("id", str(memo_id)).limit(1).execute()).data or []
    return rows[0] if rows else None


def _is_author(memo: dict, membership: Membership) -> bool:
    return str(memo.get("user_id") or "") == str(membership.user_id)


def _is_manager_of(memo: dict, membership: Membership) -> bool:
    return membership.role in MANAGE_ROLES and str(memo.get("company_id") or "") == str(membership.company_id)


def _published_options(membership: Membership) -> list[dict]:
    store = get_playbook_store()
    motions = store.motions(membership.company_id)
    stored = store.details(membership.company_id)
    keys = sorted((key for key, state in motions.items() if state == "published"), key=catalog_order)
    return [{"key": key, "label": (stored.get(key) or {}).get("label") or None} for key in keys]


@memo_router.get("/{memo_id}/playbook")
async def get_memo_playbook(
    memo_id: str,
    supabase: Client = Depends(get_supabase),
    membership: Membership = Depends(get_membership),
    user_id: str = Depends(get_user_id),
):
    """What the recording was evaluated as, and whether this viewer can change it."""
    memo = _load_memo(supabase, memo_id)
    if not memo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Memo not found")
    can_edit = _is_author(memo, membership) or _is_manager_of(memo, membership)
    if not can_edit:
        # Not ours to change, but a teammate or an AE with a handoff may still read it: same
        # rule as GET /memos/{id} (404 when it is not readable for this viewer).
        from app.api.memos import _require_viewable_memo

        _require_viewable_memo(supabase, str(memo_id), user_id)
    return {
        "sales_motion_key": memo.get("sales_motion_key") or None,
        "playbook_version_id": memo.get("playbook_version_id") or None,
        "can_change": bool(can_edit and routing_enabled(supabase, membership.company_id)),
        "options": _published_options(membership),
    }


def _requeue(supabase: Client, memo: dict) -> None:
    """C04 and the score for the new pin, through the same path a fresh extraction uses:
    the pin is part of the memo's input revision, so C04 is no longer current and runs again,
    and coaching is republished when it stores (or straight away when C04 is off)."""
    extraction = memo.get("extraction") if isinstance(memo.get("extraction"), dict) else {}
    memo_id = str(memo["id"])
    try:
        from app.services.memo_extraction_hooks import run_post_extraction_hooks

        run_post_extraction_hooks(supabase, memo_id=memo_id, extraction=extraction, memo=memo)
    except Exception:
        logger.exception("playbook change: post-extraction hooks failed", extra={"memo_id": memo_id})
    try:
        from app.services.intelligence.worker import record_enqueue

        record_enqueue(supabase, memo)
    except Exception:
        logger.exception("playbook change: C04 enqueue failed", extra={"memo_id": memo_id})


@memo_router.post("/{memo_id}/playbook")
async def change_memo_playbook(
    memo_id: str,
    body: MemoPlaybookRequest,
    supabase: Client = Depends(get_supabase),
    membership: Membership = Depends(get_membership),
):
    """Author or manager: pin the memo to the active version of another type and run C04
    and scoring again against it."""
    memo = _load_memo(supabase, memo_id)
    if not memo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Memo not found")
    if not (_is_author(memo, membership) or _is_manager_of(memo, membership)):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Solo el autor o un manager pueden cambiar el playbook")
    key = body.sales_motion_key.strip()
    from app.services.captures import active_playbook_version

    company_id = str(memo.get("company_id") or membership.company_id)
    version = active_playbook_version(supabase, company_id, key) if key else None
    if not version:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": "not_published"})
    update: dict[str, Any] = {
        "sales_motion_key": key,
        "playbook_version_id": str(version),
        "pipeline_meta": merge_pin_meta(
            memo.get("pipeline_meta"), "manual", changed_from=memo.get("sales_motion_key"), changed_by=str(membership.user_id),
        ),
    }
    supabase.table("memos").update(update).eq("id", str(memo["id"])).execute()
    _requeue(supabase, {**memo, **update})
    return {"sales_motion_key": key, "playbook_version_id": str(version), "status": "requeued"}
