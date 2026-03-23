"""Salesforce OAuth, schema, configuration (mounted under /api/v1/crm)."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import RedirectResponse

from app.config import settings
from app.deps import get_supabase, get_user_id
from app.models.approval import DealMatch
from app.models.crm_config import CRMConfigurationRequest, CRMConfigurationResponse, StageOption
from app.models.salesforce_crm import SalesforceConnectionOut
from app.models.hubspot import TestConnectionResponse
from app.services.crm_config import CRMConfigurationService
from app.services.hubspot.types import CRMSchema, HubSpotProperty, PropertyOption
from app.services.salesforce.client import SalesforceClient
from app.services.salesforce.oauth import (
    build_authorize_url,
    decode_state,
    exchange_code_for_tokens,
    salesforce_oauth_enabled,
)
from app.services.salesforce.schema import SalesforceSchemaService
from app.services.salesforce.search import SalesforceSearchService
from app.services.salesforce.validation import SalesforceValidationService
from supabase import Client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/salesforce", tags=["crm", "salesforce"])


def _get_salesforce_connection_row(supabase: Client, user_id: str) -> dict[str, Any]:
    r = (
        supabase.table("crm_connections")
        .select("*")
        .eq("user_id", user_id)
        .eq("provider", "salesforce")
        .eq("status", "connected")
        .limit(1)
        .execute()
    )
    if not r.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Salesforce connection not found",
        )
    return r.data[0]


def _sf_client_from_row(row: dict[str, Any], supabase: Client) -> SalesforceClient:
    meta = row.get("metadata") or {}
    instance_url = meta.get("instance_url") or ""
    if not instance_url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Salesforce connection missing instance_url",
        )
    expires_raw = row.get("token_expires_at")
    expires_at = None
    if expires_raw:
        try:
            expires_at = datetime.fromisoformat(str(expires_raw).replace("Z", "+00:00"))
        except Exception:
            pass
    return SalesforceClient(
        instance_url=instance_url,
        access_token=row["access_token"],
        refresh_token=row.get("refresh_token"),
        connection_id=str(row["id"]),
        supabase=supabase,
        token_expires_at=expires_at,
    )


@router.get("/authorize")
async def salesforce_authorize(
    supabase: Client = Depends(get_supabase),
    user_id: str = Depends(get_user_id),
):
    if not salesforce_oauth_enabled():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Salesforce OAuth not configured.",
        )
    try:
        user_profile = supabase.table("user_profiles").select("id").eq("id", user_id).single().execute()
        if not user_profile.data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User profile not found")
    except HTTPException:
        raise
    except Exception as e:
        if "no rows" in str(e).lower() or "PGRST116" in str(e):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User profile not found")
        raise
    try:
        return {"redirect_url": build_authorize_url(user_id)}
    except RuntimeError as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e))


@router.get("/callback")
async def salesforce_callback(
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
    supabase: Client = Depends(get_supabase),
):
    frontend_url = settings.FRONTEND_URL.rstrip("/")
    ok = f"{frontend_url}/dashboard/integrations?salesforce=connected"
    bad = f"{frontend_url}/dashboard/integrations?salesforce=error"

    if error:
        return RedirectResponse(url=f"{bad}&error={error}", status_code=302)
    if not code or not state:
        return RedirectResponse(url=f"{bad}&error=missing_params", status_code=302)
    user_id = decode_state(state)
    if not user_id:
        return RedirectResponse(url=f"{bad}&error=invalid_state", status_code=302)
    try:
        token_data = await exchange_code_for_tokens(code)
    except Exception as e:
        logger.exception("Salesforce OAuth token exchange failed: %s", e)
        return RedirectResponse(url=f"{bad}&error=token_exchange_failed", status_code=302)

    access_token = token_data.get("access_token")
    refresh_token = token_data.get("refresh_token")
    instance_url = (token_data.get("instance_url") or "").rstrip("/")
    if not access_token or not instance_url:
        return RedirectResponse(url=f"{bad}&error=no_token", status_code=302)

    expires_at = None
    if token_data.get("expires_in"):
        expires_at = (datetime.utcnow() + timedelta(seconds=int(token_data["expires_in"]))).isoformat()

    client = SalesforceClient(
        instance_url=instance_url,
        access_token=access_token,
        refresh_token=refresh_token,
        connection_id=None,
        supabase=None,
    )
    validation = await SalesforceValidationService(client).validate()
    if not validation.valid:
        logger.warning("Salesforce post-OAuth validation failed: %s", validation.error)
        return RedirectResponse(url=f"{bad}&error=validation_failed", status_code=302)

    connection_data = {
        "user_id": user_id,
        "provider": "salesforce",
        "status": "connected",
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_expires_at": expires_at,
        "metadata": {"instance_url": instance_url},
    }
    try:
        supabase.table("crm_connections").upsert(connection_data, on_conflict="user_id,provider").execute()
    except Exception as e:
        logger.exception("Salesforce OAuth save to crm_connections failed: %s", e)
        return RedirectResponse(url=f"{bad}&error=save_failed", status_code=302)

    return RedirectResponse(url=ok, status_code=302)


@router.delete("/disconnect")
async def salesforce_disconnect(
    supabase: Client = Depends(get_supabase),
    user_id: str = Depends(get_user_id),
):
    existing = (
        supabase.table("crm_connections")
        .select("id")
        .eq("user_id", user_id)
        .eq("provider", "salesforce")
        .limit(1)
        .execute()
    )
    sf_id = existing.data[0]["id"] if existing.data else None
    supabase.table("crm_connections").delete().eq("user_id", user_id).eq("provider", "salesforce").execute()
    if sf_id:
        prof = (
            supabase.table("user_profiles")
            .select("primary_crm_connection_id")
            .eq("id", user_id)
            .maybe_single()
            .execute()
        )
        pid = (prof.data or {}).get("primary_crm_connection_id") if prof and prof.data else None
        if pid and str(pid) == str(sf_id):
            supabase.table("user_profiles").update({"primary_crm_connection_id": None}).eq("id", user_id).execute()
    return {"success": True}


@router.get("/connection", response_model=SalesforceConnectionOut)
async def get_salesforce_connection(
    supabase: Client = Depends(get_supabase),
    user_id: str = Depends(get_user_id),
):
    row = _get_salesforce_connection_row(supabase, user_id)
    return SalesforceConnectionOut(
        id=UUID(row["id"]),
        user_id=UUID(row["user_id"]),
        provider=row["provider"],
        status=row["status"],
        metadata=row.get("metadata") or {},
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


@router.post("/test", response_model=TestConnectionResponse)
async def test_salesforce(
    supabase: Client = Depends(get_supabase),
    user_id: str = Depends(get_user_id),
):
    try:
        row = _get_salesforce_connection_row(supabase, user_id)
        client = _sf_client_from_row(row, supabase)
        v = await SalesforceValidationService(client).validate()
        return TestConnectionResponse(
            valid=v.valid,
            portal_id=v.organization_id,
            scopes_ok=v.valid,
            error=v.error,
            error_code="VALIDATION_FAILED" if not v.valid else None,
        )
    except HTTPException as e:
        return TestConnectionResponse(valid=False, error=e.detail, error_code="NOT_CONNECTED")


@router.get("/stages", response_model=list[StageOption])
async def salesforce_stages(
    supabase: Client = Depends(get_supabase),
    user_id: str = Depends(get_user_id),
):
    row = _get_salesforce_connection_row(supabase, user_id)
    client = _sf_client_from_row(row, supabase)
    schema = SalesforceSchemaService(client, supabase, str(row["id"]))
    picklist = await schema.get_stage_picklist_values()
    return [
        StageOption(id=p["value"], label=p["label"], display_order=i)
        for i, p in enumerate(picklist)
    ]


@router.get("/schema", response_model=CRMSchema)
async def salesforce_opportunity_schema(
    supabase: Client = Depends(get_supabase),
    user_id: str = Depends(get_user_id),
):
    row = _get_salesforce_connection_row(supabase, user_id)
    client = _sf_client_from_row(row, supabase)
    schema_svc = SalesforceSchemaService(client, supabase, str(row["id"]))
    d = await schema_svc.describe_opportunity()
    props: list[HubSpotProperty] = []
    for f in d.get("fields") or []:
        fname = f.get("name")
        if not fname or f.get("type") in ("base64", "address"):
            continue
        if not f.get("updateable") and fname not in ("Name",):
            continue
        try:
            opts = []
            for pv in f.get("picklistValues") or []:
                if not pv.get("active", True):
                    continue
                opts.append(
                    PropertyOption(
                        label=pv.get("label") or "",
                        value=pv.get("value") or "",
                        hidden=False,
                    )
                )
            props.append(
                HubSpotProperty(
                    name=fname,
                    label=f.get("label") or fname,
                    type=f.get("type") or "string",
                    fieldType="text",
                    options=opts,
                    readOnlyValue=not f.get("updateable", True),
                )
            )
        except Exception:
            continue
    return CRMSchema(object_type="deals", properties=props, pipelines=[])


@router.get("/configuration", response_model=CRMConfigurationResponse)
async def get_salesforce_configuration(
    supabase: Client = Depends(get_supabase),
    user_id: str = Depends(get_user_id),
):
    svc = CRMConfigurationService(supabase)
    config = await svc.get_configuration(user_id, provider="salesforce")
    if not config:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="CRM not configured.")
    return config


@router.post("/configure", response_model=CRMConfigurationResponse)
async def configure_salesforce(
    request: CRMConfigurationRequest,
    supabase: Client = Depends(get_supabase),
    user_id: str = Depends(get_user_id),
):
    try:
        user_profile = supabase.table("user_profiles").select("id").eq("id", user_id).single().execute()
        if not user_profile.data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User profile not found")
    except HTTPException:
        raise
    except Exception as e:
        if "no rows" in str(e).lower() or "PGRST116" in str(e):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User profile not found")
        raise

    conn = (
        supabase.table("crm_connections")
        .select("id")
        .eq("user_id", user_id)
        .eq("provider", "salesforce")
        .eq("status", "connected")
        .limit(1)
        .execute()
    )
    if not conn.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Salesforce not connected")
    connection_id = conn.data[0]["id"]

    svc = CRMConfigurationService(supabase)
    config = await svc.save_configuration(user_id, connection_id, request)

    row = _get_salesforce_connection_row(supabase, user_id)
    client = _sf_client_from_row(row, supabase)
    await SalesforceSchemaService(client, supabase, str(row["id"])).describe_opportunity()
    return config


@router.get("/search/opportunities", response_model=list[DealMatch])
async def search_salesforce_opportunities(
    q: str,
    supabase: Client = Depends(get_supabase),
    user_id: str = Depends(get_user_id),
):
    row = _get_salesforce_connection_row(supabase, user_id)
    client = _sf_client_from_row(row, supabase)
    cfg = await CRMConfigurationService(supabase).get_configuration(user_id, provider="salesforce")
    stage_filter = cfg.default_stage_name if cfg else None
    search = SalesforceSearchService(client)
    records = await search.find_opportunities_by_term(q, limit=10, stage_filter=stage_filter)
    if not records and stage_filter:
        records = await search.find_opportunities_by_term(q, limit=10, stage_filter=None)
    out: list[DealMatch] = []
    for rec in records:
        out.append(
            DealMatch(
                deal_id=rec["Id"],
                deal_name=rec.get("Name") or "Opportunity",
                amount=str(rec["Amount"]) if rec.get("Amount") is not None else None,
                stage=rec.get("StageName"),
                last_updated=str(rec.get("LastModifiedDate") or ""),
                match_confidence=1.0,
                match_reason="Manual Search",
            )
        )
    return out
