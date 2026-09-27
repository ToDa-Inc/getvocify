"""GET the stored meeting proposal. POST accept / omit / correct / reconcile."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.handoffs import CRM_OWNER_FLAG, _apply_crm_owner_effect
from app.deps import get_membership, get_supabase
from app.models.meetings import MeetingProposalAcceptRequest, MeetingProposalReconcileRequest
from app.services.company import Membership
from app.services.crm_providers.errors import AmbiguousPrimaryCRMError
from app.services.crm_providers.resolve import resolve_sync_connection_for_company
from app.services.feature_flags import is_enabled
from app.services.handoffs import HandoffError, ae_membership_row, create_handoff, resolve_ae, valid_ae
from app.services.meetings.accept import WriterFactory, accept_meeting_proposal, reconcile_meeting_proposal
from app.services.meetings.proposals import latest_proposal

HANDOFF_FLAG = "HANDOFF_ENABLED"

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["meetings"])

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
        _maybe_create_handoff(supabase, membership=membership, memo_id=memo_id)
    return result


def _maybe_create_handoff(supabase, *, membership: Membership, memo_id: str) -> None:
    """D6/F14: accepting a meeting proposal is one of the two moments a handoff is
    created. Best-effort - a failure here must never turn an accepted meeting into an
    error response."""
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
        ae_user_id = resolve_ae(membership)
        ae_row = ae_membership_row(supabase, company_id=membership.company_id, ae_user_id=ae_user_id)
        if not valid_ae(ae_row):
            return
        deal_id = memo.get("hubspot_deal_id") or memo.get("matched_deal_id")
        connection_id = str(connection["id"])
        row = create_handoff(
            supabase,
            company_id=membership.company_id,
            connection_id=connection_id,
            contact_id=str(contact_id),
            sdr_user_id=membership.user_id,
            ae_user_id=ae_user_id,
            deal_id=str(deal_id) if deal_id else None,
            source_memo_id=str(memo_id),
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
