"""GET the stored meeting proposal. POST accept / omit / correct / reconcile.
POST /meetings/bot (T14) sends a Recall.ai bot into a video meeting."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.api.handoffs import CRM_OWNER_FLAG, _apply_crm_owner_effect
from app.config import settings
from app.deps import get_membership, get_supabase
from app.models.meetings import MeetingProposalAcceptRequest, MeetingProposalReconcileRequest
from app.services.company import Membership
from app.services.crm_providers.errors import AmbiguousPrimaryCRMError
from app.services.crm_providers.resolve import resolve_sync_connection_for_company
from app.services.feature_flags import is_enabled
from app.services.handoffs import HandoffError, ae_membership_row, create_handoff, resolve_ae, valid_ae
from app.services.meetings.accept import WriterFactory, accept_meeting_proposal, reconcile_meeting_proposal
from app.services.meetings.proposals import latest_proposal
from app.services.meetings.recall_bot import reserve_recall_capture

HANDOFF_FLAG = "HANDOFF_ENABLED"
RECALL_BOT_FLAG = "RECALL_BOT_ENABLED"

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["meetings"])


class CreateMeetingBotRequest(BaseModel):
    meeting_url: str = Field(min_length=1)
    contact_id: Optional[str] = None
    connection_id: Optional[str] = None


class MeetingBotResponse(BaseModel):
    capture_id: str
    memo_id: str
    bot_id: str
    status: str


@router.post("/meetings/bot", response_model=MeetingBotResponse)
async def create_meeting_bot(
    body: CreateMeetingBotRequest,
    membership: Membership = Depends(get_membership),
    supabase=Depends(get_supabase),
):
    if not is_enabled(supabase, membership.company_id, RECALL_BOT_FLAG):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")
    if not settings.RECALL_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Recall.ai no está configurado",
        )

    from app.integrations.recall_client import RecallClient, RecallClientError, is_allowed_meeting_url

    if not is_allowed_meeting_url(body.meeting_url):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="El enlace debe ser una reunión de Zoom, Meet o Teams (https)",
        )

    client = RecallClient()
    try:
        bot = await client.create_bot(
            body.meeting_url,
            metadata={"source": "manual", "user_id": membership.user_id, "company_id": membership.company_id},
        )
    except RecallClientError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    bot_id = str((bot or {}).get("id") or "")
    if not bot_id:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Recall no devolvió un bot_id",
        )

    # The capture can only be reserved once the bot exists (its id is the reservation
    # key, D1/C01), so this can't happen before create_bot. A bot with no capture behind
    # it would sit in the meeting recording nothing usable - better to cancel it and
    # fail the request than leave an orphan.
    try:
        identity = reserve_recall_capture(
            supabase,
            user_id=membership.user_id,
            company_id=membership.company_id,
            started_at=datetime.now(timezone.utc),
            bot_id=bot_id,
            sales_role=membership.sales_role,
            contact_id=body.contact_id,
        )
    except Exception as exc:
        await client.delete_bot(bot_id)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="No se pudo reservar la captura para el bot",
        ) from exc

    return MeetingBotResponse(
        capture_id=identity.capture_id,
        memo_id=identity.memo_id,
        bot_id=bot_id,
        status=identity.status,
    )

_WRITER_FACTORY: WriterFactory | None = None


def set_meeting_writer_factory(factory: WriterFactory | None) -> None:
    global _WRITER_FACTORY
    _WRITER_FACTORY = factory


@router.get("/memos/{memo_id}/meeting-proposal")
async def get_meeting_proposal(
    memo_id: str,
    membership: Membership = Depends(get_membership),
    supabase=Depends(get_supabase),
):
    try:
        memo = (
            supabase.table("memos")
            .select("id,company_id")
            .eq("id", memo_id)
            .execute()
        )
        rows = (
            supabase.table("meeting_proposals")
            .select("*")
            .eq("memo_id", memo_id)
            .execute()
        )
    except Exception:
        return {"proposal": None}
    found = memo.data or []
    if not found or found[0].get("company_id") != membership.company_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Memo no encontrado")
    return {"proposal": latest_proposal(rows.data or [])}


@router.post("/memos/{memo_id}/meeting-proposal/accept")
async def accept_meeting_proposal_route(
    memo_id: str,
    payload: MeetingProposalAcceptRequest,
    membership: Membership = Depends(get_membership),
    supabase=Depends(get_supabase),
):
    result = accept_meeting_proposal(
        supabase,
        company_id=membership.company_id,
        memo_id=memo_id,
        decision=payload.decision,
        proposal_id=payload.proposal_id,
        starts_at=payload.starts_at,
        writer_factory=_WRITER_FACTORY,
    )
    if payload.decision in ("accept", "corrected") and membership.sales_role == "sdr":
        _maybe_create_handoff(
            supabase,
            membership=membership,
            memo_id=memo_id,
            proposal_id=payload.proposal_id,
            corrected_starts_at=payload.starts_at if payload.decision == "corrected" else None,
        )
    return result


def _accepted_starts_at(supabase, *, memo_id: str, proposal_id: str) -> Optional[str]:
    """The agreed time of the proposal just accepted (newest revision), for the AE's card."""
    rows = (
        supabase.table("meeting_proposals")
        .select("*")
        .eq("memo_id", memo_id)
        .execute()
    ).data or []
    matches = [row for row in rows if row.get("proposal_id") == proposal_id]
    if not matches:
        return None
    newest = max(matches, key=lambda item: str(item.get("created_at") or item.get("input_revision") or ""))
    return newest.get("starts_at")


def _maybe_create_handoff(
    supabase,
    *,
    membership: Membership,
    memo_id: str,
    proposal_id: Optional[str] = None,
    corrected_starts_at: Optional[str] = None,
) -> None:
    """D6/F14: accepting a meeting proposal is one of the two moments a handoff is
    created. Best-effort - a failure here must never turn an accepted meeting into an
    error response. The handoff carries the agreed time so the AE sees the meeting in
    their Hoy on the day."""
    if not is_enabled(supabase, membership.company_id, HANDOFF_FLAG):
        return
    try:
        memo_rows = (
            supabase.table("memos")
            .select("id,hubspot_contact_id,hubspot_deal_id,matched_deal_id")
            .eq("id", memo_id)
            .execute()
        ).data or []
        memo = memo_rows[0] if memo_rows else None
        contact_id = memo and memo.get("hubspot_contact_id")
        if not memo or not contact_id:
            return
        try:
            connection = resolve_sync_connection_for_company(supabase, membership.company_id)
        except AmbiguousPrimaryCRMError:
            return
        if not connection:
            return
        ae_user_id = resolve_ae(membership, supabase=supabase, company_id=membership.company_id)
        ae_row = ae_membership_row(supabase, company_id=membership.company_id, ae_user_id=ae_user_id)
        if not valid_ae(ae_row):
            return
        deal_id = memo.get("hubspot_deal_id") or memo.get("matched_deal_id")
        connection_id = str(connection["id"])
        starts_at = corrected_starts_at
        if not starts_at and proposal_id:
            try:
                starts_at = _accepted_starts_at(supabase, memo_id=memo_id, proposal_id=proposal_id)
            except Exception:
                starts_at = None
        row = create_handoff(
            supabase,
            company_id=membership.company_id,
            connection_id=connection_id,
            contact_id=str(contact_id),
            sdr_user_id=membership.user_id,
            ae_user_id=ae_user_id,
            deal_id=str(deal_id) if deal_id else None,
            source_memo_id=str(memo_id),
            meeting_starts_at=starts_at,
        )
        if row.get("created") and is_enabled(supabase, membership.company_id, CRM_OWNER_FLAG):
            _apply_crm_owner_effect(
                supabase,
                company_id=membership.company_id,
                connection_id=connection_id,
                handoff_id=row.get("id"),
                ae_user_id=ae_user_id,
                deal_id=str(deal_id) if deal_id else None,
                contact_id=str(contact_id),
            )
    except HandoffError:
        # No AE routed yet (D2): the SDR completes the handoff explicitly from Hoy/the
        # contact panel, where a missing AE opens the picker instead of failing silently.
        return
    except Exception:
        logger.warning("Handoff-on-accept failed for memo %s", memo_id, exc_info=True)


@router.post("/memos/{memo_id}/meeting-proposal/reconcile")
async def reconcile_meeting_proposal_route(
    memo_id: str,
    payload: MeetingProposalReconcileRequest,
    membership: Membership = Depends(get_membership),
    supabase=Depends(get_supabase),
):
    return reconcile_meeting_proposal(
        supabase,
        company_id=membership.company_id,
        memo_id=memo_id,
        proposal_id=payload.proposal_id,
        writer_factory=_WRITER_FACTORY,
    )
