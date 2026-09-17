"""Pipedrive OAuth, schema, configuration (mounted under /api/v1/crm)."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Optional
from urllib.parse import quote_plus, urlparse
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from supabase import Client

from app.config import settings
from app.deps import get_supabase, get_user_id
from app.models.approval import ContactMatch, DealMatch
from app.models.crm_config import CRMConfigurationRequest, CRMConfigurationResponse, StageOption
from app.models.hubspot import TestConnectionResponse
from app.models.pipedrive_crm import PipedriveConnectionOut
from app.services.company_scope import require_company_id, require_crm_connection, require_crm_write_access
from app.services.crm_config import CRMConfigurationService
from app.services.hubspot.types import CRMSchema, HubSpotPipeline, HubSpotPipelineStage, HubSpotProperty, PropertyOption
from app.services.pipedrive.client import PipedriveClient
from app.services.pipedrive.oauth import (
    build_authorize_url,
    decode_state,
    exchange_code_for_tokens,
    pipedrive_oauth_enabled,
)
from app.services.pipedrive.schema import PipedriveSchemaService, expand_schema_fields, field_key, field_label
from app.services.pipedrive.page_context import assoc_id, contact_from_person, deal_raw_extraction, person_names
from app.services.pipedrive.search import PipedriveSearchService, primary_email, primary_phone
from app.services.pipedrive.validation import PipedriveValidationService
from app.services.session_entities import load_stt_profile, vocab_for_hubspot_context

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/pipedrive", tags=["crm", "pipedrive"])


def _get_pipedrive_connection_row(supabase: Client, user_id: str) -> dict[str, Any]:
    row = require_crm_connection(supabase, user_id, "pipedrive", detail="Pipedrive connection not found")
    if row.get("status") != "connected":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pipedrive connection not found")
    return row


def _pd_client_from_row(row: dict[str, Any], supabase: Client) -> PipedriveClient:
    meta = row.get("metadata") or {}
    api_domain = meta.get("api_domain") or ""
    if not api_domain:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Pipedrive connection missing api_domain",
        )
    expires_raw = row.get("token_expires_at")
    expires_at = None
    if expires_raw:
        try:
            expires_at = datetime.fromisoformat(str(expires_raw).replace("Z", "+00:00"))
        except Exception:
            pass
    return PipedriveClient(
        api_domain=api_domain,
        access_token=row["access_token"],
        refresh_token=row.get("refresh_token"),
        connection_id=str(row["id"]),
        supabase=supabase,
        token_expires_at=expires_at,
    )


@router.get("/authorize")
async def pipedrive_authorize(
    supabase: Client = Depends(get_supabase),
    user_id: str = Depends(get_user_id),
):
    require_crm_write_access(supabase, user_id)
    if not pipedrive_oauth_enabled():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Pipedrive OAuth not configured.",
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
async def pipedrive_callback(
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
    error_description: Optional[str] = None,
    supabase: Client = Depends(get_supabase),
):
    frontend_url = settings.FRONTEND_URL.rstrip("/")
    ok = f"{frontend_url}/dashboard/integrations?pipedrive=connected"
    bad = f"{frontend_url}/dashboard/integrations?pipedrive=error"

    if error:
        q = f"error={quote_plus(error)}"
        if error_description:
            q += f"&error_description={quote_plus(error_description)}"
        return RedirectResponse(url=f"{bad}&{q}", status_code=302)
    if not code or not state:
        return RedirectResponse(url=f"{bad}&error=missing_params", status_code=302)
    user_id = decode_state(state)
    if not user_id:
        return RedirectResponse(url=f"{bad}&error=invalid_state", status_code=302)
    try:
        token_data = await exchange_code_for_tokens(code)
    except Exception as e:
        logger.exception("Pipedrive OAuth token exchange failed: %s", e)
        return RedirectResponse(url=f"{bad}&error=token_exchange_failed", status_code=302)

    access_token = token_data.get("access_token")
    refresh_token = token_data.get("refresh_token")
    api_domain = (token_data.get("api_domain") or "").rstrip("/")
    if not access_token or not api_domain:
        return RedirectResponse(url=f"{bad}&error=no_token", status_code=302)

    expires_at = None
    if token_data.get("expires_in") is not None:
        expires_at = (datetime.utcnow() + timedelta(seconds=int(token_data["expires_in"]))).isoformat()

    client = PipedriveClient(
        api_domain=api_domain,
        access_token=access_token,
        refresh_token=refresh_token,
        connection_id=None,
        supabase=None,
    )
    validation = await PipedriveValidationService(client).validate()
    if not validation.valid:
        logger.warning("Pipedrive post-OAuth validation failed: %s", validation.error)
        return RedirectResponse(url=f"{bad}&error=validation_failed", status_code=302)

    me = validation.user or {}
    host = urlparse(api_domain).hostname or ""
    company_domain = me.get("company_domain")
    if not company_domain and host.endswith(".pipedrive.com"):
        company_domain = host.split(".")[0]

    company_id = require_company_id(supabase, user_id)
    connection_data = {
        "user_id": user_id,
        "company_id": company_id,
        "provider": "pipedrive",
        "status": "connected",
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_expires_at": expires_at,
        "metadata": {
            "api_domain": api_domain,
            "company_domain": company_domain,
            "pipedrive_user_id": me.get("id"),
            "pipedrive_company_id": me.get("company_id"),
            "user_email": me.get("email"),
            "user_name": me.get("name"),
            "scope": token_data.get("scope"),
        },
    }
    try:
        supabase.table("crm_connections").upsert(connection_data, on_conflict="company_id,provider").execute()
    except Exception as e:
        logger.exception("Pipedrive OAuth save to crm_connections failed: %s", e)
        return RedirectResponse(url=f"{bad}&error=save_failed", status_code=302)

    return RedirectResponse(url=ok, status_code=302)


@router.delete("/disconnect")
async def pipedrive_disconnect(
    supabase: Client = Depends(get_supabase),
    user_id: str = Depends(get_user_id),
):
    company_id = require_crm_write_access(supabase, user_id)
    existing = (
        supabase.table("crm_connections")
        .select("id")
        .eq("company_id", company_id)
        .eq("provider", "pipedrive")
        .limit(1)
        .execute()
    )
    pd_id = existing.data[0]["id"] if existing.data else None
    supabase.table("crm_connections").delete().eq("company_id", company_id).eq("provider", "pipedrive").execute()
    if pd_id:
        comp = (
            supabase.table("companies")
            .select("primary_crm_connection_id")
            .eq("id", company_id)
            .maybe_single()
            .execute()
        )
        pid = (comp.data or {}).get("primary_crm_connection_id") if comp and comp.data else None
        if pid and str(pid) == str(pd_id):
            supabase.table("companies").update({"primary_crm_connection_id": None}).eq("id", company_id).execute()
    return {"success": True}


@router.get("/connection", response_model=PipedriveConnectionOut)
async def get_pipedrive_connection(
    supabase: Client = Depends(get_supabase),
    user_id: str = Depends(get_user_id),
):
    row = _get_pipedrive_connection_row(supabase, user_id)
    return PipedriveConnectionOut(
        id=UUID(row["id"]),
        user_id=UUID(row["user_id"]),
        provider=row["provider"],
        status=row["status"],
        metadata=row.get("metadata") or {},
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


@router.post("/test", response_model=TestConnectionResponse)
async def test_pipedrive(
    supabase: Client = Depends(get_supabase),
    user_id: str = Depends(get_user_id),
):
    try:
        row = _get_pipedrive_connection_row(supabase, user_id)
        client = _pd_client_from_row(row, supabase)
        v = await PipedriveValidationService(client).validate()
        return TestConnectionResponse(
            valid=v.valid,
            portal_id=str((v.user or {}).get("company_id") or "") or None,
            scopes_ok=v.valid,
            error=v.error,
            error_code="VALIDATION_FAILED" if not v.valid else None,
        )
    except HTTPException as e:
        return TestConnectionResponse(valid=False, error=e.detail, error_code="NOT_CONNECTED")


@router.get("/pipelines", response_model=list[HubSpotPipeline])
async def pipedrive_pipelines(
    supabase: Client = Depends(get_supabase),
    user_id: str = Depends(get_user_id),
):
    row = _get_pipedrive_connection_row(supabase, user_id)
    client = _pd_client_from_row(row, supabase)
    schema = PipedriveSchemaService(client, supabase, str(row["id"]))
    pipelines = await schema.list_pipelines()
    stages = await schema.list_stages()
    by_pipe: dict[str, list[HubSpotPipelineStage]] = {}
    for s in stages:
        pid = str(s.get("pipeline_id") or "")
        by_pipe.setdefault(pid, []).append(
            HubSpotPipelineStage(
                id=str(s.get("id")),
                label=s.get("name") or str(s.get("id")),
                displayOrder=int(s.get("order_nr") or 0),
            )
        )
    return [
        HubSpotPipeline(
            id=str(p.get("id")),
            label=p.get("name") or str(p.get("id")),
            displayOrder=int(p.get("order_nr") or 0),
            stages=by_pipe.get(str(p.get("id")), []),
        )
        for p in pipelines
    ]


@router.get("/stages", response_model=list[StageOption])
async def pipedrive_stages(
    pipeline_id: Optional[str] = None,
    supabase: Client = Depends(get_supabase),
    user_id: str = Depends(get_user_id),
):
    row = _get_pipedrive_connection_row(supabase, user_id)
    client = _pd_client_from_row(row, supabase)
    schema = PipedriveSchemaService(client, supabase, str(row["id"]))
    stages = await schema.list_stages(pipeline_id)
    return [
        StageOption(
            id=str(s.get("id")),
            label=s.get("name") or str(s.get("id")),
            display_order=int(s.get("order_nr") or 0),
        )
        for s in stages
    ]


def _fields_to_properties(fields: list[dict[str, Any]]) -> list[HubSpotProperty]:
    props: list[HubSpotProperty] = []
    for f in fields:
        key = field_key(f)
        if not key:
            continue
        opts = []
        for o in f.get("options") or []:
            if not isinstance(o, dict):
                continue
            opts.append(
                PropertyOption(
                    label=o.get("label") or str(o.get("id") or ""),
                    value=str(o.get("id") if o.get("id") is not None else o.get("label") or ""),
                    hidden=False,
                )
            )
        writable = f.get("is_writable")
        read_only = writable is False if writable is not None else bool(f.get("edit_flag") is False)
        props.append(
            HubSpotProperty(
                name=key,
                label=field_label(f),
                type=f.get("field_type") or "string",
                fieldType="text",
                options=opts,
                readOnlyValue=read_only,
            )
        )
    return props


@router.get("/schema", response_model=CRMSchema)
async def pipedrive_schema(
    object_type: str = Query("deals"),
    refresh: bool = False,
    supabase: Client = Depends(get_supabase),
    user_id: str = Depends(get_user_id),
):
    if object_type not in ("deals", "contacts", "companies"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="object_type must be deals|contacts|companies")
    row = _get_pipedrive_connection_row(supabase, user_id)
    client = _pd_client_from_row(row, supabase)
    schema_svc = PipedriveSchemaService(client, supabase, str(row["id"]))
    fields = expand_schema_fields(await schema_svc.list_fields(object_type, use_cache=not refresh))
    pipelines: list[HubSpotPipeline] = []
    if object_type == "deals":
        raw_p = await schema_svc.list_pipelines()
        raw_s = await schema_svc.list_stages()
        by_pipe: dict[str, list[HubSpotPipelineStage]] = {}
        for s in raw_s:
            pid = str(s.get("pipeline_id") or "")
            by_pipe.setdefault(pid, []).append(
                HubSpotPipelineStage(
                    id=str(s.get("id")),
                    label=s.get("name") or str(s.get("id")),
                    displayOrder=int(s.get("order_nr") or 0),
                )
            )
        pipelines = [
            HubSpotPipeline(
                id=str(p.get("id")),
                label=p.get("name") or str(p.get("id")),
                displayOrder=int(p.get("order_nr") or 0),
                stages=by_pipe.get(str(p.get("id")), []),
            )
            for p in raw_p
        ]
    return CRMSchema(object_type=object_type, properties=_fields_to_properties(fields), pipelines=pipelines)


@router.get("/configuration", response_model=CRMConfigurationResponse)
async def get_pipedrive_configuration(
    supabase: Client = Depends(get_supabase),
    user_id: str = Depends(get_user_id),
):
    svc = CRMConfigurationService(supabase)
    config = await svc.get_configuration(user_id, provider="pipedrive")
    if not config:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="CRM not configured.")
    return config


@router.post("/configure", response_model=CRMConfigurationResponse)
async def configure_pipedrive(
    request: CRMConfigurationRequest,
    supabase: Client = Depends(get_supabase),
    user_id: str = Depends(get_user_id),
):
    require_crm_write_access(supabase, user_id)
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
        .eq("company_id", require_company_id(supabase, user_id))
        .eq("provider", "pipedrive")
        .eq("status", "connected")
        .limit(1)
        .execute()
    )
    if not conn.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pipedrive not connected")
    connection_id = conn.data[0]["id"]

    svc = CRMConfigurationService(supabase)
    config = await svc.save_configuration(user_id, connection_id, request)
    return config


@router.get("/search/deals", response_model=list[DealMatch])
async def search_pipedrive_deals(
    q: str,
    supabase: Client = Depends(get_supabase),
    user_id: str = Depends(get_user_id),
):
    row = _get_pipedrive_connection_row(supabase, user_id)
    client = _pd_client_from_row(row, supabase)
    records = await PipedriveSearchService(client).search_deals(q, limit=10)
    return [
        DealMatch(
            deal_id=str(rec["id"]),
            deal_name=rec.get("title") or "Deal",
            amount=str(rec["value"]) if rec.get("value") is not None else None,
            stage=str(rec.get("stage_id")) if rec.get("stage_id") is not None else None,
            last_updated=str(rec.get("update_time") or rec.get("updated_at") or ""),
            match_confidence=1.0,
            match_reason="Manual Search",
        )
        for rec in records
        if rec.get("id") is not None
    ]


@router.get("/search/persons", response_model=list[ContactMatch])
async def search_pipedrive_persons(
    q: str,
    supabase: Client = Depends(get_supabase),
    user_id: str = Depends(get_user_id),
):
    row = _get_pipedrive_connection_row(supabase, user_id)
    client = _pd_client_from_row(row, supabase)
    records = await PipedriveSearchService(client).search_persons(q, limit=10)
    return [
        ContactMatch(
            contact_id=str(rec["id"]),
            name=rec.get("name"),
            email=primary_email(rec) or "",
            phone=primary_phone(rec),
            match_confidence=1.0,
            match_reason="Manual Search",
        )
        for rec in records
        if rec.get("id") is not None
    ]


@router.get("/search/organizations")
async def search_pipedrive_organizations(
    q: str,
    supabase: Client = Depends(get_supabase),
    user_id: str = Depends(get_user_id),
):
    row = _get_pipedrive_connection_row(supabase, user_id)
    client = _pd_client_from_row(row, supabase)
    records = await PipedriveSearchService(client).search_organizations(q, limit=10)
    return [
        {"id": str(rec["id"]), "name": rec.get("name")}
        for rec in records
        if rec.get("id") is not None
    ]


def _session_vocab(
    supabase: Client,
    user_id: str,
    *,
    first_name: Optional[str] = None,
    last_name: Optional[str] = None,
    company_name: Optional[str] = None,
    deal_name: Optional[str] = None,
    extra_names: Optional[list] = None,
) -> list[str]:
    profile = load_stt_profile(supabase, user_id)
    return vocab_for_hubspot_context(
        first_name=first_name,
        last_name=last_name,
        company_name=company_name,
        deal_name=deal_name,
        extra_names=extra_names,
        caller_name=profile.get("full_name"),
        seller_company=profile.get("company_name"),
    )


@router.get("/deals/{deal_id}/context")
async def get_pipedrive_deal_context(
    deal_id: str,
    supabase: Client = Depends(get_supabase),
    user_id: str = Depends(get_user_id),
):
    empty = {
        "companyName": None,
        "companyId": None,
        "contactName": None,
        "contactEmail": None,
        "contactPhone": None,
        "contactId": None,
        "contacts": [],
        "raw_extraction": {},
        "sessionVocab": [],
        "dealId": deal_id,
    }
    try:
        row = _get_pipedrive_connection_row(supabase, user_id)
        search = PipedriveSearchService(_pd_client_from_row(row, supabase))
        deal = await search.get_deal(deal_id)
        if not deal:
            return empty
        person_id = assoc_id(deal.get("person_id"))
        org_id = assoc_id(deal.get("org_id"))
        person: dict = {}
        org: dict = {}
        if person_id:
            try:
                person = await search.get_person(person_id)
            except Exception:
                person = {}
        if org_id:
            try:
                org = await search.get_organization(org_id)
            except Exception:
                org = {}
        company_name = (org.get("name") if org else None) or (
            (deal.get("org_id") or {}).get("name") if isinstance(deal.get("org_id"), dict) else None
        )
        contact = contact_from_person(person, company_id=org_id, company_name=company_name) if person else None
        contacts = [contact] if contact else []
        first, last, _ = person_names(person) if person else ("", "", None)
        raw = deal_raw_extraction(deal)
        return {
            "companyName": company_name,
            "companyId": org_id,
            "contactName": (contact or {}).get("name"),
            "contactEmail": (contact or {}).get("email"),
            "contactPhone": (contact or {}).get("phone"),
            "contactId": (contact or {}).get("contact_id"),
            "contacts": contacts,
            "raw_extraction": raw,
            "sessionVocab": _session_vocab(
                supabase,
                user_id,
                first_name=first,
                last_name=last,
                company_name=company_name,
                deal_name=raw.get("dealname"),
                extra_names=[c.get("name") for c in contacts[:4]],
            ),
            "dealId": deal_id,
        }
    except HTTPException:
        raise
    except Exception:
        return empty


@router.get("/persons/{person_id}/context")
async def get_pipedrive_person_context(
    person_id: str,
    supabase: Client = Depends(get_supabase),
    user_id: str = Depends(get_user_id),
):
    empty = {
        "contactId": person_id,
        "contactName": None,
        "contactEmail": None,
        "contactPhone": None,
        "companyId": None,
        "companyName": None,
        "sessionVocab": [],
    }
    try:
        row = _get_pipedrive_connection_row(supabase, user_id)
        search = PipedriveSearchService(_pd_client_from_row(row, supabase))
        person = await search.get_person(person_id)
        if not person:
            return empty
        org_id = assoc_id(person.get("org_id"))
        company_name = None
        if org_id:
            try:
                org = await search.get_organization(org_id)
                company_name = org.get("name")
            except Exception:
                company_name = None
        if not company_name:
            org = person.get("org_id")
            company_name = org.get("name") if isinstance(org, dict) else person.get("org_name")
        first, last, name = person_names(person)
        return {
            "contactId": person_id,
            "contactName": name,
            "contactEmail": primary_email(person) or None,
            "contactPhone": primary_phone(person),
            "companyId": org_id,
            "companyName": company_name,
            "sessionVocab": _session_vocab(
                supabase, user_id, first_name=first, last_name=last, company_name=company_name
            ),
        }
    except HTTPException:
        raise
    except Exception:
        return empty


@router.get("/organizations/{org_id}/context")
async def get_pipedrive_org_context(
    org_id: str,
    supabase: Client = Depends(get_supabase),
    user_id: str = Depends(get_user_id),
):
    empty = {
        "companyId": org_id,
        "companyName": None,
        "contactId": None,
        "contactName": None,
        "contactEmail": None,
        "contactPhone": None,
        "contacts": [],
        "sessionVocab": [],
    }
    try:
        row = _get_pipedrive_connection_row(supabase, user_id)
        search = PipedriveSearchService(_pd_client_from_row(row, supabase))
        org = await search.get_organization(org_id)
        if not org:
            return empty
        company_name = org.get("name")
        contacts: list[dict] = []
        try:
            for person in await search.persons_for_org(org_id, limit=5):
                c = contact_from_person(person, company_id=org_id, company_name=company_name)
                if c:
                    contacts.append(c)
        except Exception:
            contacts = []
        primary = contacts[0] if len(contacts) == 1 else None
        first = last = ""
        if primary:
            src = next((p for p in contacts if p.get("contact_id") == primary["contact_id"]), None)
            if src and src.get("name"):
                parts = str(src["name"]).split(None, 1)
                first = parts[0]
                last = parts[1] if len(parts) > 1 else ""
        return {
            "companyId": org_id,
            "companyName": company_name,
            "contactId": (primary or {}).get("contact_id"),
            "contactName": (primary or {}).get("name"),
            "contactEmail": (primary or {}).get("email"),
            "contactPhone": (primary or {}).get("phone"),
            "contacts": contacts,
            "sessionVocab": _session_vocab(
                supabase,
                user_id,
                first_name=first,
                last_name=last,
                company_name=company_name,
                extra_names=[c.get("name") for c in contacts[:4]],
            ),
        }
    except HTTPException:
        raise
    except Exception:
        return empty
