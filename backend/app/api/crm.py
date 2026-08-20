"""
CRM integration API endpoints
"""

import asyncio
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from uuid import UUID
from typing import Any, Literal, Optional

from app.config import settings
from app.deps import get_supabase, get_user_id
from app.services.hubspot import (
    HubSpotClient,
    HubSpotValidationService,
    HubSpotSchemaService,
    HubSpotSearchService,
    HubSpotContactService,
    HubSpotCompanyService,
    HubSpotDealService,
    HubSpotAssociationService,
    HubSpotSyncService,
)
from app.services.crm_updates import CRMUpdatesService
from app.services.crm_config import CRMConfigurationService
from app.services.preview_targets import unique_associated_contact_id
from app.models.hubspot import (
    ConnectHubSpotRequest,
    ConnectHubSpotResponse,
    TestConnectionResponse,
    HubSpotConnection,
    CreateDealRequest,
    UpdateDealRequest,
)
from app.models.crm_config import (
    CRMConfigurationRequest,
    CRMConfigurationResponse,
    PipelineOption,
    StageOption,
)
from app.models.approval import DealMatch
from app.services.hubspot.types import CRMSchema
from app.services.hubspot.oauth import (
    oauth_enabled,
    build_authorize_url,
    decode_state,
    exchange_code_for_tokens,
    ensure_fresh_hubspot_connection,
)
from app.services.hubspot.calls import (
    get_call_engagement,
    list_recent_recordings,
    list_recordings_for_record,
)
from app.services.hubspot.call_processor import (
    initiate_hubspot_call_memo,
    process_hubspot_call_background,
)
from supabase import Client


router = APIRouter(prefix="/api/v1/crm", tags=["crm"])


def get_hubspot_client_from_connection(
    user_id: str,
    supabase: Client,
) -> HubSpotClient:
    """
    Get HubSpot client from user's connection.
    Refreshes OAuth access_token when expired (HubSpot tokens last ~30 min).
    
    Raises:
        HTTPException if no connection exists or token is invalid
    """
    # Get user's HubSpot connection
    result = supabase.table("crm_connections").select("*").eq(
        "user_id", user_id
    ).eq("provider", "hubspot").single().execute()
    
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="HubSpot connection not found. Please connect your HubSpot account first.",
        )
    
    connection = result.data
    
    if connection["status"] != "connected":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"HubSpot connection status: {connection['status']}",
        )

    try:
        connection = ensure_fresh_hubspot_connection(supabase, connection)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"HubSpot authorization expired. Please reconnect HubSpot. ({e})",
        ) from e
    
    access_token = connection.get("access_token")
    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="HubSpot access token is missing",
        )
    
    return HubSpotClient(access_token)


def _hubspot_access_token(user_id: str, supabase: Client) -> str:
    result = (
        supabase.table("crm_connections")
        .select("id, access_token, refresh_token, token_expires_at, status")
        .eq("user_id", user_id)
        .eq("provider", "hubspot")
        .single()
        .execute()
    )
    if not result.data or result.data.get("status") != "connected":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="HubSpot connection not found. Please connect your HubSpot account first.",
        )
    try:
        connection = ensure_fresh_hubspot_connection(supabase, result.data)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"HubSpot authorization expired. Please reconnect HubSpot. ({e})",
        ) from e
    token = (connection.get("access_token") or "").strip()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="HubSpot access token is missing",
        )
    return token


def _join_memo_state(
    supabase: Client,
    user_id: str,
    recordings: list[dict],
) -> list[dict]:
    call_ids = [r["call_id"] for r in recordings if r.get("call_id")]
    if not call_ids:
        return recordings
    memos_res = (
        supabase.table("memos")
        .select("id, status, hubspot_engagement_id")
        .eq("user_id", user_id)
        .in_("hubspot_engagement_id", call_ids)
        .execute()
    )
    by_call: dict[str, dict] = {}
    for row in memos_res.data or []:
        eid = str(row.get("hubspot_engagement_id") or "")
        if eid:
            by_call[eid] = row
    out = []
    for rec in recordings:
        m = by_call.get(rec["call_id"])
        out.append({
            **rec,
            "memo_id": str(m["id"]) if m else None,
            "memo_status": m.get("status") if m else None,
        })
    return out


async def _recordings_for_record(
    user_id: str,
    supabase: Client,
    from_object_type: str,
    record_id: str,
) -> list[dict]:
    client = get_hubspot_client_from_connection(user_id, supabase)
    items = await list_recordings_for_record(client, from_object_type, record_id)
    return _join_memo_state(supabase, user_id, items)


def _query_call_memo(supabase: Client, user_id: str, field: str, value: str) -> dict:
    """Shared logic: find the most recent hubspot_call memo by deal or contact ID."""
    from datetime import timezone as _tz

    cutoff = (datetime.now(_tz.utc) - timedelta(hours=24)).isoformat()
    r = (
        supabase.table("memos")
        .select("id,status")
        .eq("user_id", user_id)
        .eq(field, value)
        .eq("source", "hubspot_call")
        .gte("created_at", cutoff)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    if not r.data:
        return {"status": "waiting"}
    row = r.data[0]
    st = row.get("status")
    # failed/rejected → keep watching; approved → surface so extension can skip gracefully
    if st in ("failed", "rejected"):
        return {"status": "waiting"}
    return {"status": st, "memo_id": str(row["id"])}



@router.get("/hubspot/deals/{deal_id}/call-memo")
async def get_hubspot_call_memo_for_deal(
    deal_id: str,
    supabase: Client = Depends(get_supabase),
    user_id: str = Depends(get_user_id),
):
    """Poll for a HubSpot call memo created by webhook for this deal (DB only)."""
    return _query_call_memo(supabase, user_id, "hubspot_deal_id", deal_id)


@router.get("/hubspot/contacts/{contact_id}/call-memo")
async def get_hubspot_call_memo_for_contact(
    contact_id: str,
    supabase: Client = Depends(get_supabase),
    user_id: str = Depends(get_user_id),
):
    """Poll for a HubSpot call memo created by webhook for this contact (DB only)."""
    return _query_call_memo(supabase, user_id, "hubspot_contact_id", contact_id)


@router.get("/hubspot/deals/{deal_id}/recordings")
async def list_hubspot_recordings_for_deal(
    deal_id: str,
    supabase: Client = Depends(get_supabase),
    user_id: str = Depends(get_user_id),
):
    """HubSpot calls with recordings linked to this deal, plus Vocify memo state."""
    return await _recordings_for_record(user_id, supabase, "deals", deal_id)


@router.get("/hubspot/contacts/{contact_id}/recordings")
async def list_hubspot_recordings_for_contact(
    contact_id: str,
    supabase: Client = Depends(get_supabase),
    user_id: str = Depends(get_user_id),
):
    """HubSpot calls with recordings linked to this contact, plus Vocify memo state."""
    return await _recordings_for_record(user_id, supabase, "contacts", contact_id)


@router.get("/hubspot/companies/{company_id}/recordings")
async def list_hubspot_recordings_for_company(
    company_id: str,
    supabase: Client = Depends(get_supabase),
    user_id: str = Depends(get_user_id),
):
    """HubSpot calls with recordings linked to this company, plus Vocify memo state."""
    return await _recordings_for_record(user_id, supabase, "companies", company_id)


@router.get("/hubspot/recordings")
async def list_recent_hubspot_recordings(
    supabase: Client = Depends(get_supabase),
    user_id: str = Depends(get_user_id),
    limit: int = Query(20, ge=1, le=50),
):
    """Newest HubSpot calls with recordings across the portal."""
    client = get_hubspot_client_from_connection(user_id, supabase)
    items = await list_recent_recordings(client, limit=limit)
    return _join_memo_state(supabase, user_id, items)


@router.post("/hubspot/calls/{call_id}/process")
async def process_hubspot_call(
    call_id: str,
    supabase: Client = Depends(get_supabase),
    user_id: str = Depends(get_user_id),
):
    """
    Start (or retry) transcription for a HubSpot call recording.
    Idempotent on hubspot_engagement_id; retries failed memos.
    """
    client = get_hubspot_client_from_connection(user_id, supabase)
    access_token = _hubspot_access_token(user_id, supabase)

    eng = await get_call_engagement(client, call_id)
    if not eng:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Call not found")
    props = eng.get("properties") or {}
    if not (props.get("hs_call_recording_url") or "").strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This call has no recording yet.",
        )

    memo_id, created = await initiate_hubspot_call_memo(
        supabase, user_id, call_id, access_token
    )
    if not memo_id:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not create memo for this call",
        )

    should_process = created
    memo_row = (
        supabase.table("memos")
        .select("status")
        .eq("id", memo_id)
        .single()
        .execute()
    )
    current_status = (memo_row.data or {}).get("status") if memo_row.data else "transcribing"

    if not created and current_status == "failed":
        supabase.table("memos").update(
            {
                "status": "transcribing",
                "error_message": None,
                "processing_started_at": datetime.utcnow().isoformat(),
            }
        ).eq("id", memo_id).execute()
        should_process = True
        current_status = "transcribing"

    if should_process:
        asyncio.create_task(
            process_hubspot_call_background(
                memo_id, user_id, access_token, call_id, supabase
            )
        )

    return {
        "memo_id": memo_id,
        "status": current_status,
        "created": created,
        "processing_started": should_process,
    }


@router.get("/hubspot/contacts/{contact_id}/context")
async def get_contact_context_for_extension(
    contact_id: str,
    supabase: Client = Depends(get_supabase),
    user_id: str = Depends(get_user_id),
):
    """Contact (+ company) context for extension header / session vocab / identity lock."""
    empty = {
        "contactId": contact_id,
        "contactName": None,
        "contactEmail": None,
        "contactPhone": None,
        "companyId": None,
        "companyName": None,
        "sessionVocab": [],
    }
    try:
        client = get_hubspot_client_from_connection(user_id, supabase)
        search_service = HubSpotSearchService(client)
        contact_service = HubSpotContactService(client, search_service)
        contact = await contact_service.get(contact_id)
        props = contact.properties or {}
        first = props.get("firstname") or ""
        last = props.get("lastname") or ""
        name = f"{first} {last}".strip() or None
        email = props.get("email") or None
        phone = props.get("phone") or props.get("mobilephone") or None
        company_id = None
        company_name = None
        try:
            from app.services.hubspot.associations import HubSpotAssociationService
            from app.services.hubspot.companies import HubSpotCompanyService

            associations = HubSpotAssociationService(client)
            company_ids = await associations.get_associations("contacts", contact_id, "companies")
            if company_ids:
                company_id = str(company_ids[0])
                company_service = HubSpotCompanyService(client, search_service)
                comp = await company_service.get(company_id)
                company_name = (comp.properties or {}).get("name")
        except Exception:
            pass
        from app.services.session_entities import load_stt_profile, vocab_for_hubspot_context

        profile = load_stt_profile(supabase, user_id)
        vocab = vocab_for_hubspot_context(
            first_name=first,
            last_name=last,
            company_name=company_name,
            caller_name=profile.get("full_name"),
            seller_company=profile.get("company_name"),
        )
        return {
            "contactId": contact_id,
            "contactName": name,
            "contactEmail": email,
            "contactPhone": phone,
            "companyId": company_id,
            "companyName": company_name,
            "sessionVocab": vocab,
        }
    except Exception:
        return empty


@router.get("/hubspot/companies/{company_id}/context")
async def get_company_context_for_extension(
    company_id: str,
    supabase: Client = Depends(get_supabase),
    user_id: str = Depends(get_user_id),
):
    """Company (+ associated contacts) for extension page lock / session vocab."""
    empty = {
        "companyId": company_id,
        "companyName": None,
        "contactId": None,
        "contactName": None,
        "contactEmail": None,
        "contactPhone": None,
        "contacts": [],
        "sessionVocab": [],
    }
    try:
        client = get_hubspot_client_from_connection(user_id, supabase)
        search_service = HubSpotSearchService(client)
        company_service = HubSpotCompanyService(client, search_service)
        contact_service = HubSpotContactService(client, search_service)
        from app.services.hubspot.associations import HubSpotAssociationService

        company = await company_service.get(company_id)
        company_name = (company.properties or {}).get("name") or None
        associations = HubSpotAssociationService(client)
        contact_ids = await associations.get_associations("companies", company_id, "contacts")
        contacts_out: list[dict] = []
        for cid in (contact_ids or [])[:5]:
            try:
                contact = await contact_service.get(str(cid))
                props = contact.properties or {}
                first = props.get("firstname") or ""
                last = props.get("lastname") or ""
                name = f"{first} {last}".strip() or None
                contacts_out.append(
                    {
                        "contact_id": str(cid),
                        "name": name,
                        "email": props.get("email") or None,
                        "phone": props.get("phone") or props.get("mobilephone") or None,
                        "company_id": company_id,
                        "company_name": company_name,
                    }
                )
            except Exception:
                continue

        primary = next(
            (c for c in contacts_out if c["contact_id"] == unique_associated_contact_id(contacts_out)),
            None,
        )
        from app.services.session_entities import load_stt_profile, vocab_for_hubspot_context

        profile = load_stt_profile(supabase, user_id)
        vocab = vocab_for_hubspot_context(
            company_name=company_name,
            extra_names=[c.get("name") for c in contacts_out[:4]],
            caller_name=profile.get("full_name"),
            seller_company=profile.get("company_name"),
        )
        return {
            "companyId": company_id,
            "companyName": company_name,
            "contactId": primary["contact_id"] if primary else None,
            "contactName": primary["name"] if primary else None,
            "contactEmail": primary["email"] if primary else None,
            "contactPhone": primary["phone"] if primary else None,
            "contacts": contacts_out,
            "sessionVocab": vocab,
        }
    except Exception:
        return empty


@router.post("/hubspot/connect", response_model=ConnectHubSpotResponse)
async def connect_hubspot(
    request: ConnectHubSpotRequest,
    supabase: Client = Depends(get_supabase),
    user_id: str = Depends(get_user_id),
):
    """
    Connect HubSpot Private App.
    
    Validates the access token and stores the connection.
    
    Requires:
    - User must exist in user_profiles table (created via signup)
    - Valid HubSpot Private App access token
    """
    # Verify user exists in user_profiles (our source of truth)
    # This ensures users are created via our signup flow, not directly via Supabase auth
    try:
        user_profile = supabase.table("user_profiles").select("id").eq("id", user_id).single().execute()
        if not user_profile.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User profile not found. Please sign up first to create your account.",
            )
    except Exception as e:
        # Handle case where user doesn't exist (Supabase returns APIError for .single() with 0 rows)
        error_str = str(e)
        if "no rows" in error_str.lower() or "PGRST116" in error_str:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User profile not found. Please sign up first to create your account.",
            )
        # Re-raise other errors
        raise
    
    # Validate HubSpot token
    client = HubSpotClient(request.access_token)
    validation_service = HubSpotValidationService(client)
    
    validation_result = await validation_service.validate()
    
    if not validation_result.valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=validation_result.error or "Invalid HubSpot access token",
        )
    
    # Store or update connection
    connection_data = {
        "user_id": user_id,
        "provider": "hubspot",
        "status": "connected",
        "access_token": request.access_token,
        "refresh_token": None,  # Private apps don't have refresh tokens
        "token_expires_at": None,  # Private app tokens don't expire
        "metadata": {
            "portal_id": validation_result.portal_id,
            "region": validation_result.region,
            "ui_domain": validation_result.ui_domain,
        },
    }
    
    # Upsert (update if exists, insert if not)
    try:
        result = supabase.table("crm_connections").upsert(
            connection_data,
            on_conflict="user_id,provider",
        ).execute()
    except Exception as e:
        error_msg = str(e)
        # Check for foreign key violation (shouldn't happen if user_profiles check passed)
        if "foreign key constraint" in error_msg.lower() or "23503" in error_msg:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"User not found in auth.users. This should not happen if user_profiles exists. Error: {error_msg}",
            )
        # Re-raise other errors
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save HubSpot connection: {error_msg}",
        )
    
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save HubSpot connection",
        )
    
    connection = result.data[0]
    
    return ConnectHubSpotResponse(
        connection_id=UUID(connection["id"]),
        status=connection["status"],
        portal_id=validation_result.portal_id,
    )


@router.get("/hubspot/authorize")
async def hubspot_authorize(
    supabase: Client = Depends(get_supabase),
    user_id: str = Depends(get_user_id),
):
    """
    Get HubSpot OAuth authorize URL.
    
    Returns JSON with redirect_url. Frontend should redirect user there.
    Requires authentication.
    """
    if not oauth_enabled():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="HubSpot OAuth not configured. Use Private App token flow instead.",
        )
    try:
        user_profile = supabase.table("user_profiles").select("id").eq("id", user_id).single().execute()
        if not user_profile.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User profile not found. Please sign up first.",
            )
    except HTTPException:
        raise
    except Exception as e:
        if "no rows" in str(e).lower() or "PGRST116" in str(e):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User profile not found. Please sign up first.",
            )
        raise
    try:
        redirect_url = build_authorize_url(user_id)
        return {"redirect_url": redirect_url}
    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e),
        )


@router.get("/hubspot/callback")
async def hubspot_callback(
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
    supabase: Client = Depends(get_supabase),
):
    """
    HubSpot OAuth callback. HubSpot redirects here after user authorizes.
    
    Exchanges code for tokens, stores connection, redirects to frontend.
    """
    frontend_url = settings.FRONTEND_URL.rstrip("/")
    success_url = f"{frontend_url}/dashboard/integrations?hubspot=connected"
    error_url = f"{frontend_url}/dashboard/integrations?hubspot=error"

    if error:
        return RedirectResponse(url=f"{error_url}&error={error}", status_code=302)
    if not code or not state:
        return RedirectResponse(url=f"{error_url}&error=missing_params", status_code=302)

    user_id = decode_state(state)
    if not user_id:
        return RedirectResponse(url=f"{error_url}&error=invalid_state", status_code=302)

    try:
        token_data = await exchange_code_for_tokens(code)
    except Exception as e:
        return RedirectResponse(
            url=f"{error_url}&error=token_exchange_failed",
            status_code=302,
        )

    access_token = token_data.get("access_token")
    refresh_token = token_data.get("refresh_token")
    expires_in = token_data.get("expires_in")

    if not access_token:
        return RedirectResponse(url=f"{error_url}&error=no_token", status_code=302)

    token_expires_at = None
    if expires_in:
        token_expires_at = (datetime.utcnow() + timedelta(seconds=int(expires_in))).isoformat()

    validation_service = HubSpotValidationService(HubSpotClient(access_token))
    validation_result = await validation_service.validate()
    if not validation_result.valid:
        return RedirectResponse(url=f"{error_url}&error=validation_failed", status_code=302)

    connection_data = {
        "user_id": user_id,
        "provider": "hubspot",
        "status": "connected",
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_expires_at": token_expires_at,
        "metadata": {
            "portal_id": validation_result.portal_id,
            "region": validation_result.region or "na1",
            "ui_domain": validation_result.ui_domain,
        },
    }

    try:
        supabase.table("crm_connections").upsert(
            connection_data,
            on_conflict="user_id,provider",
        ).execute()
    except Exception:
        return RedirectResponse(url=f"{error_url}&error=save_failed", status_code=302)

    return RedirectResponse(url=success_url, status_code=302)


@router.post("/hubspot/test", response_model=TestConnectionResponse)
async def test_hubspot_connection(
    supabase: Client = Depends(get_supabase),
    user_id: str = Depends(get_user_id),
):
    """
    Test HubSpot connection.
    
    Validates the stored token and checks required scopes.
    
    Requires:
    - User must exist in user_profiles table
    """
    # Verify user exists in user_profiles (our source of truth)
    try:
        user_profile = supabase.table("user_profiles").select("id").eq("id", user_id).single().execute()
        if not user_profile.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User profile not found. Please sign up first.",
            )
    except Exception as e:
        error_str = str(e)
        if "no rows" in error_str.lower() or "PGRST116" in error_str:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User profile not found. Please sign up first.",
            )
        raise
    
    try:
        client = get_hubspot_client_from_connection(user_id, supabase)
        validation_service = HubSpotValidationService(client)
        
        result = await validation_service.validate()
        
        return TestConnectionResponse(
            valid=result.valid,
            portal_id=result.portal_id,
            scopes_ok=result.scopes_ok,
            error=result.error,
            error_code=result.error_code,
        )
        
    except HTTPException:
        raise
    except Exception as e:
        return TestConnectionResponse(
            valid=False,
            error=str(e),
            error_code="TEST_FAILED",
        )


@router.get("/hubspot/connection", response_model=HubSpotConnection)
async def get_hubspot_connection(
    supabase: Client = Depends(get_supabase),
    user_id: str = Depends(get_user_id),
):
    """
    Get user's HubSpot connection details.
    
    Requires:
    - User must exist in user_profiles table
    """
    # Verify user exists in user_profiles (our source of truth)
    try:
        user_profile = supabase.table("user_profiles").select("id").eq("id", user_id).single().execute()
        if not user_profile.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User profile not found. Please sign up first.",
            )
    except Exception as e:
        error_str = str(e)
        if "no rows" in error_str.lower() or "PGRST116" in error_str:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User profile not found. Please sign up first.",
            )
        raise
    
    result = supabase.table("crm_connections").select("*").eq(
        "user_id", user_id
    ).eq("provider", "hubspot").single().execute()
    
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="HubSpot connection not found",
        )
    
    connection = result.data
    
    return HubSpotConnection(
        id=UUID(connection["id"]),
        user_id=UUID(connection["user_id"]),
        provider=connection["provider"],
        status=connection["status"],
        metadata=connection.get("metadata", {}),
        created_at=connection["created_at"],
        updated_at=connection["updated_at"],
    )


@router.delete("/hubspot/disconnect")
async def disconnect_hubspot(
    supabase: Client = Depends(get_supabase),
    user_id: str = Depends(get_user_id),
):
    """Disconnect HubSpot (delete connection)"""
    result = supabase.table("crm_connections").delete().eq(
        "user_id", user_id
    ).eq("provider", "hubspot").execute()
    
    return {"success": True, "message": "HubSpot disconnected"}


@router.get("/hubspot/schema", response_model=CRMSchema)
async def get_hubspot_schema(
    object_type: Literal["deals", "contacts", "companies", "line_items"] = "deals",
    refresh: bool = False,
    supabase: Client = Depends(get_supabase),
    user_id: str = Depends(get_user_id),
):
    """
    Get HubSpot schema (properties and pipelines) for an object type.
    
    Used by frontend to build field allowlists for deals, contacts, companies, line items.
    Uses database caching to avoid repeated API calls unless refresh=true
    (pull from HubSpot again after new properties are added).
    
    Requires:
    - User must exist in user_profiles table
    - HubSpot connection must be established
    """
    # Verify user exists in user_profiles (our source of truth)
    try:
        user_profile = supabase.table("user_profiles").select("id").eq("id", user_id).single().execute()
        if not user_profile.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User profile not found. Please sign up first.",
            )
    except Exception as e:
        error_str = str(e)
        if "no rows" in error_str.lower() or "PGRST116" in error_str:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User profile not found. Please sign up first.",
            )
        raise
    
    # Get connection for schema caching
    try:
        conn_result = supabase.table("crm_connections").select("id").eq(
            "user_id", user_id
        ).eq("provider", "hubspot").eq("status", "connected").single().execute()
        
        if not conn_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="HubSpot connection not found",
            )
        
        connection_id = conn_result.data["id"]
    except Exception as e:
        error_str = str(e)
        if "no rows" in error_str.lower() or "PGRST116" in error_str:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="HubSpot connection not found",
            )
        raise
    
    client = get_hubspot_client_from_connection(user_id, supabase)
    schema_service = HubSpotSchemaService(client, supabase, connection_id)
    
    try:
        schema = await schema_service.get_schema(object_type, use_cache=not refresh)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to fetch HubSpot {object_type} schema: {e}",
        ) from e

    from app.services.extraction_policy import annotate_schema_fill_policies

    return annotate_schema_fill_policies(schema)


@router.get("/hubspot/pipelines", response_model=list[PipelineOption])
async def get_hubspot_pipelines(
    supabase: Client = Depends(get_supabase),
    user_id: str = Depends(get_user_id),
):
    """
    Get all HubSpot pipelines for deal selection during onboarding.
    
    Returns pipelines with their stages for user to choose from.
    
    Requires:
    - User must exist in user_profiles table
    - HubSpot connection must be established
    """
    # Verify user exists
    try:
        user_profile = supabase.table("user_profiles").select("id").eq("id", user_id).single().execute()
        if not user_profile.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User profile not found. Please sign up first.",
            )
    except Exception as e:
        error_str = str(e)
        if "no rows" in error_str.lower() or "PGRST116" in error_str:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User profile not found. Please sign up first.",
            )
        raise
    
    # Get connection
    try:
        conn_result = supabase.table("crm_connections").select("id").eq(
            "user_id", user_id
        ).eq("provider", "hubspot").eq("status", "connected").single().execute()
        
        if not conn_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="HubSpot connection not found",
            )
        
        connection_id = conn_result.data["id"]
    except Exception as e:
        error_str = str(e)
        if "no rows" in error_str.lower() or "PGRST116" in error_str:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="HubSpot connection not found",
            )
        raise
    
    client = get_hubspot_client_from_connection(user_id, supabase)
    schema_service = HubSpotSchemaService(client, supabase, connection_id)
    
    schema = await schema_service.get_deal_schema()
    
    # Convert to PipelineOption format
    pipelines = []
    for pipeline in schema.pipelines:
        stages = [
            StageOption(
                id=stage.id,
                label=stage.label,
                display_order=stage.displayOrder,
            )
            for stage in pipeline.stages
        ]
        
        pipelines.append(PipelineOption(
            id=pipeline.id,
            label=pipeline.label,
            stages=stages,
        ))
    
    return pipelines


@router.get("/hubspot/search/deals", response_model=list[DealMatch])
async def search_hubspot_deals(
    q: str,
    supabase: Client = Depends(get_supabase),
    user_id: str = Depends(get_user_id),
):
    """
    Search for HubSpot deals by name.
    
    Used as an escape hatch when AI matching doesn't find the right deal.
    """
    # Get client
    client = get_hubspot_client_from_connection(user_id, supabase)
    search_service = HubSpotSearchService(client)
    
    # Get configuration for pipeline filter
    config_service = CRMConfigurationService(supabase)
    config = await config_service.get_configuration(user_id, provider="hubspot")
    pipeline_id = config.default_pipeline_id if config else None

    # Search: try with default pipeline first; if no results, retry without pipeline
    results = await search_service.search_deals_by_query(q, limit=10, pipeline_id=pipeline_id)
    if not results and pipeline_id:
        results = await search_service.search_deals_by_query(q, limit=10, pipeline_id=None)
    
    # Convert to DealMatch
    matches = []
    for deal_data in results:
        props = deal_data.get("properties", {})
        matches.append(DealMatch(
            deal_id=deal_data["id"],
            deal_name=props.get("dealname", "Unnamed Deal"),
            amount=props.get("amount"),
            stage=props.get("dealstage"),
            last_updated=props.get("hs_lastmodifieddate", ""),
            match_confidence=1.0,  # Manual search is 100% intentional
            match_reason="Manual Search",
        ))
        
    return matches


@router.get("/hubspot/configuration", response_model=CRMConfigurationResponse)
async def get_hubspot_configuration(
    supabase: Client = Depends(get_supabase),
    user_id: str = Depends(get_user_id),
):
    """
    Get user's HubSpot configuration.
    
    Returns configuration if exists, 404 if not configured yet.
    """
    config_service = CRMConfigurationService(supabase)
    config = await config_service.get_configuration(user_id, provider="hubspot")

    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="CRM not configured. Please complete onboarding.",
        )

    return config


@router.put("/primary")
async def set_primary_crm_connection(
    connection_id: UUID = Query(..., description="crm_connections.id to use for memo sync"),
    supabase: Client = Depends(get_supabase),
    user_id: str = Depends(get_user_id),
):
    """Set which connected CRM is used for memo sync when multiple are connected."""
    conn = (
        supabase.table("crm_connections")
        .select("id")
        .eq("id", str(connection_id))
        .eq("user_id", user_id)
        .eq("status", "connected")
        .single()
        .execute()
    )
    if not conn.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connection not found")
    supabase.table("user_profiles").update({"primary_crm_connection_id": str(connection_id)}).eq(
        "id", user_id
    ).execute()
    return {"success": True, "primary_crm_connection_id": str(connection_id)}


@router.post("/hubspot/configure", response_model=CRMConfigurationResponse)
async def configure_hubspot(
    request: CRMConfigurationRequest,
    supabase: Client = Depends(get_supabase),
    user_id: str = Depends(get_user_id),
):
    """
    Save HubSpot configuration (onboarding step).
    
    Stores user's pipeline, stage, and field preferences.
    
    Requires:
    - User must exist in user_profiles table
    - HubSpot connection must be established
    """
    # Verify user exists
    try:
        user_profile = supabase.table("user_profiles").select("id").eq("id", user_id).single().execute()
        if not user_profile.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User profile not found. Please sign up first.",
            )
    except Exception as e:
        error_str = str(e)
        if "no rows" in error_str.lower() or "PGRST116" in error_str:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User profile not found. Please sign up first.",
            )
        raise
    
    # Get connection
    conn_result = supabase.table("crm_connections").select("id").eq(
        "user_id", user_id
    ).eq("provider", "hubspot").eq("status", "connected").single().execute()
    
    if not conn_result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="HubSpot connection not found. Please connect your HubSpot account first.",
        )
    
    connection_id = conn_result.data["id"]
    
    # Save configuration
    config_service = CRMConfigurationService(supabase)
    config = await config_service.save_configuration(user_id, connection_id, request)
    
    # Cache schema after configuration
    client = get_hubspot_client_from_connection(user_id, supabase)
    schema_service = HubSpotSchemaService(client, supabase, connection_id)
    
    # Pre-fetch and cache deal schema
    await schema_service.get_deal_schema(use_cache=False)
    
    return config


@router.put("/hubspot/configure", response_model=CRMConfigurationResponse)
async def update_hubspot_configuration(
    request: CRMConfigurationRequest,
    supabase: Client = Depends(get_supabase),
    user_id: str = Depends(get_user_id),
):
    """
    Update HubSpot configuration.
    
    Same as POST /configure but semantically clearer for updates.
    """
    return await configure_hubspot(request, supabase, user_id)


@router.get("/connections")
async def list_connections(
    supabase: Client = Depends(get_supabase),
    user_id: str = Depends(get_user_id),
):
    """List all CRM connections for the user"""
    result = supabase.table("crm_connections").select("*").eq(
        "user_id", user_id
    ).execute()

    connections = []
    for conn in result.data or []:
        connections.append({
            "id": conn["id"],
            "provider": conn["provider"],
            "status": conn["status"],
            "created_at": conn["created_at"],
        })

    return {"connections": connections}


@router.get("/preferences")
async def get_crm_preferences(
    supabase: Client = Depends(get_supabase),
    user_id: str = Depends(get_user_id),
):
    """Primary CRM connection id when multiple providers are connected."""
    prof = (
        supabase.table("user_profiles")
        .select("primary_crm_connection_id")
        .eq("id", user_id)
        .maybe_single()
        .execute()
    )
    pid = (prof.data or {}).get("primary_crm_connection_id") if prof and prof.data else None
    return {"primary_crm_connection_id": str(pid) if pid else None}


@router.post("/hubspot/deals")
async def create_hubspot_deal(
    request: CreateDealRequest,
    supabase: Client = Depends(get_supabase),
    user_id: str = Depends(get_user_id),
):
    """
    Create a simple HubSpot deal (for testing).
    
    Requires:
    - User must exist in user_profiles table
    - HubSpot connection must be established
    """
    # Verify user exists in user_profiles
    try:
        user_profile = supabase.table("user_profiles").select("id").eq("id", user_id).single().execute()
        if not user_profile.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User profile not found. Please sign up first.",
            )
    except Exception as e:
        error_str = str(e)
        if "no rows" in error_str.lower() or "PGRST116" in error_str:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User profile not found. Please sign up first.",
            )
        raise
    
    # Get HubSpot client and services
    client = get_hubspot_client_from_connection(user_id, supabase)
    schema_service = HubSpotSchemaService(client)
    search_service = HubSpotSearchService(client)
    deal_service = HubSpotDealService(client, search_service, schema_service)
    
    # Prepare deal properties
    properties = {
        "dealname": request.deal_name,
    }
    
    if request.amount:
        properties["amount"] = request.amount
    
    if request.description:
        properties["description"] = request.description
    
    # Create the deal
    try:
        deal = await deal_service.create(properties)
        return {
            "success": True,
            "deal": {
                "id": deal.id,
                "dealname": deal.properties.get("dealname"),
                "amount": deal.properties.get("amount"),
                "properties": deal.properties,
            }
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create deal: {str(e)}",
        )


@router.get("/hubspot/deals/{deal_id}/context")
async def get_deal_context_for_prefill(
    deal_id: str,
    supabase: Client = Depends(get_supabase),
    user_id: str = Depends(get_user_id),
):
    """
    Get deal context (deal + company + contact) for pre-filling extraction form.
    Used when user records from extension while on a HubSpot deal page.
    """
    try:
        user_profile = supabase.table("user_profiles").select("id").eq("id", user_id).single().execute()
        if not user_profile.data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User profile not found")
    except Exception as e:
        if "no rows" in str(e).lower() or "PGRST116" in str(e):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User profile not found")
        raise

    client = get_hubspot_client_from_connection(user_id, supabase)
    search_service = HubSpotSearchService(client)
    schema_service = HubSpotSchemaService(client)
    deal_service = HubSpotDealService(client, search_service, schema_service)
    association_service = HubSpotAssociationService(client)
    contact_service = HubSpotContactService(client, search_service)
    company_service = HubSpotCompanyService(client, search_service)

    ctx: dict = {"companyName": None, "companyId": None, "contactName": None, "contactEmail": None, "raw_extraction": {}}

    def _parse_amount(v: Any) -> Optional[float]:
        if v is None: return None
        try: return float(v)
        except (ValueError, TypeError): return None

    def _timestamp_to_iso(ts: Any) -> Optional[str]:
        if ts is None: return None
        try:
            ms = int(ts)
            return datetime.utcfromtimestamp(ms / 1000).strftime("%Y-%m-%d")
        except (ValueError, TypeError): return None

    try:
        deal = await deal_service.get(
            deal_id,
            properties=["dealname", "amount", "dealstage", "closedate", "description", "hs_next_step"],
        )
        props = deal.properties
        ctx["raw_extraction"] = {
            "dealname": props.get("dealname"),
            "amount": _parse_amount(props.get("amount")),
            "closedate": _timestamp_to_iso(props.get("closedate")) or props.get("closedate"),
            "dealstage": props.get("dealstage"),
            "hs_next_step": props.get("hs_next_step"),
        }
        ctx["companyName"] = None
        ctx["contactName"] = None
        ctx["contactEmail"] = None
        ctx["contactId"] = None
        ctx["contacts"] = []

        company_ids = await association_service.get_associations("deals", deal_id, "companies")
        if company_ids:
            ctx["companyId"] = str(company_ids[0])
            comp = await company_service.get(company_ids[0])
            ctx["companyName"] = comp.properties.get("name") or ctx["companyName"]

        contact_ids = await association_service.get_associations("deals", deal_id, "contacts")
        contacts_out: list[dict] = []
        for cid in (contact_ids or [])[:5]:
            try:
                contact = await contact_service.get(str(cid))
                cprops = contact.properties or {}
                first = cprops.get("firstname") or ""
                last = cprops.get("lastname") or ""
                contacts_out.append(
                    {
                        "contact_id": str(cid),
                        "name": f"{first} {last}".strip() or None,
                        "email": cprops.get("email") or None,
                        "phone": cprops.get("phone") or cprops.get("mobilephone") or None,
                        "company_id": ctx.get("companyId"),
                        "company_name": ctx.get("companyName"),
                    }
                )
            except Exception:
                continue
        ctx["contacts"] = contacts_out
        locked = unique_associated_contact_id(contacts_out)
        if locked:
            primary = next((c for c in contacts_out if c["contact_id"] == locked), None)
            if primary:
                ctx["contactId"] = locked
                ctx["contactName"] = primary.get("name")
                ctx["contactEmail"] = primary.get("email")
                ctx["contactPhone"] = primary.get("phone")
        elif contacts_out:
            ctx["contactName"] = None
            ctx["contactEmail"] = None
    except Exception:
        pass
    from app.services.session_entities import load_stt_profile, vocab_for_hubspot_context

    profile = load_stt_profile(supabase, user_id)
    contact_name = ctx.get("contactName") or ""
    parts = contact_name.split(None, 1)
    vocab = vocab_for_hubspot_context(
        first_name=parts[0] if parts else None,
        last_name=parts[1] if len(parts) > 1 else None,
        company_name=ctx.get("companyName"),
        deal_name=(ctx.get("raw_extraction") or {}).get("dealname"),
        extra_names=[c.get("name") for c in (ctx.get("contacts") or [])[:4]],
        caller_name=profile.get("full_name"),
        seller_company=profile.get("company_name"),
    )
    ctx["sessionVocab"] = vocab
    ctx["dealId"] = deal_id
    return ctx


@router.patch("/hubspot/deals/{deal_id}")
async def update_hubspot_deal(
    deal_id: str,
    request: UpdateDealRequest,
    supabase: Client = Depends(get_supabase),
    user_id: str = Depends(get_user_id),
):
    """
    Update a HubSpot deal with new properties.
    
    Requires:
    - User must exist in user_profiles table
    - HubSpot connection must be established
    """
    # Verify user exists in user_profiles
    try:
        user_profile = supabase.table("user_profiles").select("id").eq("id", user_id).single().execute()
        if not user_profile.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User profile not found. Please sign up first.",
            )
    except Exception as e:
        error_str = str(e)
        if "no rows" in error_str.lower() or "PGRST116" in error_str:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User profile not found. Please sign up first.",
            )
        raise
    
    # Get HubSpot client and services
    client = get_hubspot_client_from_connection(user_id, supabase)
    schema_service = HubSpotSchemaService(client)
    search_service = HubSpotSearchService(client)
    deal_service = HubSpotDealService(client, search_service, schema_service)
    
    # Prepare update properties (only include non-None values)
    properties = {}
    
    if request.deal_name:
        properties["dealname"] = request.deal_name
    
    if request.amount:
        properties["amount"] = request.amount
    
    if request.description:
        properties["description"] = request.description
    
    if not properties:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one property must be provided for update",
        )
    
    # Update the deal
    try:
        deal = await deal_service.update(deal_id, properties)
        return {
            "success": True,
            "deal": {
                "id": deal.id,
                "dealname": deal.properties.get("dealname"),
                "amount": deal.properties.get("amount"),
                "description": deal.properties.get("description"),
            }
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update deal: {str(e)}",
        )

