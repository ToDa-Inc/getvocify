"""Playbooks v2 fase 2: the call-type catalog, the "when it applies" rule of a type, the CRM
stages a rule can name, and correcting which playbook a recording was evaluated with. Also the
qualification templates (BANT, MEDDIC, MEDDPICC).

Registered before app.api.playbooks so /catalog, /deal-stages and /qualification-templates are
never read as a `/{sales_motion_key}` route.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, model_validator
from supabase import Client

from app.services.captures import interaction_kind_of
from app.services.playbooks import channel_types
from app.services.playbooks.api_support import MANAGE_ROLES
from app.deps import get_membership, get_supabase, get_user_id
from app.services.company import Membership
from app.services.playbooks.catalog import (
    INTERNAL_KEY,
    RuleError,
    catalog_order,
    catalog_types,
    is_catalog,
    qualification_templates,
    validate_applies_to,
)
from app.services.playbooks.live import live_version_id
from app.services.playbooks.repository import get_playbook_repository
from app.services.playbooks.routing import merge_pin_meta, motions_and_stored
from app.services.playbooks.type_classifier import READING_SOURCE
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


@router.get("/qualification-templates")
async def get_qualification_templates(membership: Membership = Depends(get_membership)):
    """Ready-made "what has to come out of the call" methods (BANT, CHAMP, ANUM, GPCT for SDRs; MEDDIC,
    MEDDPICC, SPICED, BANT for AEs), each with the roles it is offered for and its criteria (es/en)."""
    del membership
    return {"templates": qualification_templates()}


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
    repository = get_playbook_repository()
    if not key or (key not in repository.list_types(membership.company_id, include_draft=False) and not is_catalog(key)):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Playbook no encontrado")
    try:
        rule = validate_applies_to(body.applies_to)
    except RuleError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail={"code": exc.code}) from exc
    repository.set_meta(membership.company_id, key, applies_to=rule)
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
    """A new type, a new channel (types by channel only), or both. At least one."""
    sales_motion_key: Optional[str] = Field(default=None, max_length=64)
    interaction_kind: Optional[Literal["call", "meeting"]] = None

    @model_validator(mode="after")
    def _one_change(self) -> "MemoPlaybookRequest":
        # A blank key is still a request (answered 409 not_published, as before); no field at all is not.
        if self.sales_motion_key is None and not self.interaction_kind:
            raise ValueError("sales_motion_key or interaction_kind is required")
        return self


def _load_memo(supabase: Client, memo_id: str) -> Optional[dict]:
    rows = (supabase.table("memos").select("*").eq("id", str(memo_id)).limit(1).execute()).data or []
    return rows[0] if rows else None


def _is_author(memo: dict, membership: Membership) -> bool:
    return str(memo.get("user_id") or "") == str(membership.user_id)


def _is_manager_of(memo: dict, membership: Membership) -> bool:
    return membership.role in MANAGE_ROLES and str(memo.get("company_id") or "") == str(membership.company_id)


def _published_options(membership: Membership) -> list[dict]:
    motions, stored = motions_and_stored(get_playbook_repository().list_types(membership.company_id, include_draft=False))
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
    view = {
        "sales_motion_key": memo.get("sales_motion_key") or None,
        "playbook_version_id": memo.get("playbook_version_id") or None,
        # The author or a manager can always correct what the call was.
        "can_change": bool(can_edit),
        # Named by the call reading and not confirmed by anyone yet.
        "suggested": _pin_source(memo) == READING_SOURCE,
        # Interna last, as on the list chip: it has no playbook, so it needs no published one.
        "options": [*_published_options(membership), {"key": INTERNAL_KEY, "label": None}],
    }
    if channel_types.enabled(supabase, str(memo.get("company_id") or membership.company_id)):
        kind = interaction_kind_of(memo)
        view["options"] = [*_channel_options(str(membership.company_id), kind), {"key": INTERNAL_KEY, "label": None}]
        view["interaction_kind"] = kind
        view["can_change_channel"] = bool(can_edit) and kind in channel_types.CHANNELS
    return view


def _channel_options(company_id: str, kind: str) -> list[dict]:
    types = get_playbook_repository().list_types(company_id, include_draft=False)
    return [{"key": key, "label": (types.get(key) or {}).get("label") or None} for key in channel_types.candidates(types, kind)]


def _pin_source(memo: dict) -> Optional[str]:
    meta = memo.get("pipeline_meta")
    pin = meta.get("playbook_pin") if isinstance(meta, dict) else None
    return pin.get("source") if isinstance(pin, dict) else None


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
    company_id = str(memo.get("company_id") or membership.company_id)
    if channel_types.enabled(supabase, company_id):
        return _change_by_channel(supabase, memo, body, company_id, membership)
    if body.interaction_kind:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": "channel_change_unavailable"})
    key = (body.sales_motion_key or "").strip()
    # `internal` has no playbook: it is never scored, so it needs no live version.
    version: Optional[str] = None
    if key != INTERNAL_KEY:
        live = live_version_id(supabase, company_id, key) if key else None
        if not live:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": "not_published"})
        version = str(live)
    update: dict[str, Any] = {
        "sales_motion_key": key,
        "playbook_version_id": version,
        "pipeline_meta": merge_pin_meta(
            memo.get("pipeline_meta"), "manual", changed_from=memo.get("sales_motion_key"), changed_by=str(membership.user_id),
        ),
    }
    supabase.table("memos").update(update).eq("id", str(memo["id"])).execute()
    _requeue(supabase, {**memo, **update})
    return {"sales_motion_key": key, "playbook_version_id": version, "status": "requeued"}


def _change_by_channel(supabase: Client, memo: dict, body: MemoPlaybookRequest, company_id: str, membership: Membership) -> dict:
    """Types by channel: a type of the memo's channel (new channel when it changes too), with or
    without a playbook, or Interna. A channel change alone keeps a type that belongs to the new
    channel, else clears it (the person picks one next). C04 and the score run again only when a
    playbook was or is involved."""
    kind = body.interaction_kind or interaction_kind_of(memo)
    before_version = memo.get("playbook_version_id") or None
    candidates = channel_types.candidates(get_playbook_repository().list_types(company_id, include_draft=False), kind)
    current = memo.get("sales_motion_key") or None
    key = (body.sales_motion_key or "").strip() or None
    if key is None and not body.interaction_kind:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": "not_a_type_of_channel"})
    if key and key != INTERNAL_KEY and key not in candidates:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": "not_a_type_of_channel"})
    if key is None and current and current != INTERNAL_KEY and current not in candidates:
        update: dict[str, Any] = {
            "sales_motion_key": None,
            "playbook_version_id": None,
            "pipeline_meta": merge_pin_meta(
                memo.get("pipeline_meta"), "manual", changed_from=current, changed_by=str(membership.user_id),
            ),
        }
    elif key:
        update = channel_types.pin_fields(
            supabase, company_id, key, "manual", memo.get("pipeline_meta"),
            changed_from=current, changed_by=str(membership.user_id),
        )
    else:
        update = {}
    if body.interaction_kind:
        update["interaction_kind"] = body.interaction_kind
    if update:
        supabase.table("memos").update(update).eq("id", str(memo["id"])).execute()
    after = {**memo, **update}
    after_version = after.get("playbook_version_id") or None
    requeue = bool(before_version or after_version) and (
        after.get("sales_motion_key") != current or after_version != before_version
    )
    if requeue:
        _requeue(supabase, after)
    return {
        "sales_motion_key": after.get("sales_motion_key") or None,
        "playbook_version_id": after.get("playbook_version_id") or None,
        "interaction_kind": interaction_kind_of(after),
        "status": "requeued" if requeue else "saved",
    }
