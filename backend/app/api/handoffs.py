"""POST /handoffs, GET /handoffs (T3): SDR->AE handoff on "meeting agendada". Behind
HANDOFF_ENABLED; the CRM owner change is a further, independently-flagged effect
(HANDOFF_CRM_OWNER_ENABLED, D7)."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from supabase import Client

from app.deps import get_membership, get_supabase
from app.services.company import Membership
from app.services.crm_providers.errors import AmbiguousPrimaryCRMError
from app.services.crm_providers.resolve import resolve_sync_connection_for_company
from app.services.feature_flags import is_enabled
from app.services.handoffs import (
    ACTIVE,
    HandoffError,
    ae_membership_row,
    active_handoffs_for_ae,
    active_handoffs_for_sdr,
    create_handoff,
    resolve_ae,
    resolve_owner_for_general,
    valid_ae,
)
from app.services.handoffs_crm import apply_owner_handoff
from app.services.meetings.crm_writer import writer_from_connection

router = APIRouter(prefix="/api/v1", tags=["handoffs"])

FLAG = "HANDOFF_ENABLED"
CRM_OWNER_FLAG = "HANDOFF_CRM_OWNER_ENABLED"


class HandoffRequest(BaseModel):
    contact_id: str = Field(..., min_length=1)
    connection_id: Optional[str] = None
    deal_id: Optional[str] = None
    ae_user_id: Optional[str] = None
    memo_id: Optional[str] = None
    meeting_starts_at: Optional[str] = None


def _connection(supabase: Client, company_id: str, connection_id: str) -> Optional[dict]:
    rows = (
        supabase.table("crm_connections")
        .select("*")
        .eq("id", connection_id)
        .eq("company_id", company_id)
        .limit(1)
        .execute()
    ).data or []
    return rows[0] if rows else None


def _resolve_connection_for_handoff(supabase: Client, *, company_id: str, connection_id: Optional[str]) -> dict:
    """The connection this handoff writes to: the one named in the request, verified to
    belong to this company (404 otherwise), or - same as F14's accept.py - the company's
    single connected CRM when none is named."""
    if connection_id:
        connection = _connection(supabase, company_id, connection_id)
        if not connection:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conexión CRM no encontrada")
        return connection
    try:
        connection = resolve_sync_connection_for_company(supabase, company_id)
    except AmbiguousPrimaryCRMError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    if not connection:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conexión CRM no encontrada")
    return connection


def _meeting_booked_stage(supabase: Client, connection_id: str) -> Optional[dict]:
    """The company's meeting-booked stage for this CRM (same as F14's, D6/D7). None moves nothing."""
    rows = (
        supabase.table("crm_configurations")
        .select("meeting_booked_pipeline_id,meeting_booked_stage_id")
        .eq("connection_id", str(connection_id))
        .limit(1)
        .execute()
    ).data or []
    row = rows[0] if rows else {}
    pipeline_id, stage_id = row.get("meeting_booked_pipeline_id"), row.get("meeting_booked_stage_id")
    if not pipeline_id or not stage_id:
        return None
    return {"pipeline_id": str(pipeline_id), "stage_id": str(stage_id)}


def _resolve_ae_for(
    supabase: Client, membership: Membership, requested_ae_user_id: Optional[str]
) -> str:
    """D2/T3: SDR asks (or falls back to its routed AE, or the company's sole active AE);
    a General with no route - or who names themselves - keeps the deal (self_owned), it
    does not get asked to pick one."""
    sales_role = membership.sales_role
    if sales_role == "ae":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Un AE no puede traspasar un deal")
    if sales_role == "sdr":
        try:
            return resolve_ae(
                membership,
                requested_ae_user_id,
                supabase=supabase,
                company_id=membership.company_id,
            )
        except HandoffError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": exc.code}) from exc
    ae_user_id = resolve_owner_for_general(membership, requested_ae_user_id)
    if not ae_user_id or str(ae_user_id) == str(membership.user_id):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": "self_owned"})
    return ae_user_id


@router.post("/handoffs")
async def create_handoff_endpoint(
    body: HandoffRequest,
    membership: Membership = Depends(get_membership),
    supabase: Client = Depends(get_supabase),
):
    if not is_enabled(supabase, membership.company_id, FLAG):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")

    connection = _resolve_connection_for_handoff(supabase, company_id=membership.company_id, connection_id=body.connection_id)
    connection_id = str(connection["id"])

    ae_user_id = _resolve_ae_for(supabase, membership, body.ae_user_id)

    ae_row = ae_membership_row(supabase, company_id=membership.company_id, ae_user_id=ae_user_id)
    if not valid_ae(ae_row):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": "invalid_ae"})

    row = create_handoff(
        supabase,
        company_id=membership.company_id,
        connection_id=connection_id,
        contact_id=body.contact_id,
        sdr_user_id=membership.user_id,
        ae_user_id=ae_user_id,
        deal_id=body.deal_id,
        source_memo_id=body.memo_id,
        meeting_starts_at=body.meeting_starts_at,
    )

    if row.get("skipped"):
        return {"handoff": None, "crm_owner_status": None}

    crm_owner_status = row.get("crm_owner_status")
    if row.get("created") and is_enabled(supabase, membership.company_id, CRM_OWNER_FLAG):
        crm_owner_status = _apply_crm_owner_effect(
            supabase,
            company_id=membership.company_id,
            connection_id=connection_id,
            handoff_id=row.get("id"),
            ae_user_id=ae_user_id,
            deal_id=body.deal_id,
            contact_id=body.contact_id,
        )

    return {
        "id": row.get("id"),
        "status": row.get("status", ACTIVE),
        "sdr_user_id": membership.user_id,
        "ae_user_id": ae_user_id,
        "contact_id": body.contact_id,
        "deal_id": body.deal_id,
        "created": bool(row.get("created")),
        "crm_owner_status": crm_owner_status,
    }


def _apply_crm_owner_effect(
    supabase: Client,
    *,
    company_id: str,
    connection_id: str,
    handoff_id: Optional[str],
    ae_user_id: str,
    deal_id: Optional[str],
    contact_id: str,
) -> str:
    connection = _connection(supabase, company_id, connection_id)
    if not connection:
        return "skipped"
    crm_owner_status = apply_owner_handoff(
        supabase,
        connection=connection,
        ae_user_id=ae_user_id,
        deal_id=deal_id,
        contact_id=contact_id,
    )
    if handoff_id:
        (
            supabase.table("deal_handoffs")
            .update({"crm_owner_status": crm_owner_status})
            .eq("id", handoff_id)
            .execute()
        )
    stage = _meeting_booked_stage(supabase, connection_id)
    if stage and deal_id:
        writer = writer_from_connection(connection, deal_id=str(deal_id))
        if writer:
            writer.change_stage(stage)
    return crm_owner_status


@router.get("/handoffs")
async def list_handoffs_endpoint(
    role: str = Query(...),
    membership: Membership = Depends(get_membership),
    supabase: Client = Depends(get_supabase),
):
    if not is_enabled(supabase, membership.company_id, FLAG):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")
    if role not in {"ae", "sdr"}:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid role")
    if role == "ae":
        rows = active_handoffs_for_ae(supabase, company_id=membership.company_id, ae_user_id=membership.user_id)
    else:
        rows = active_handoffs_for_sdr(supabase, company_id=membership.company_id, sdr_user_id=membership.user_id)
    return {"handoffs": rows}
