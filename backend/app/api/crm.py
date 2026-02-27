"""
CRM integration API endpoints
"""

from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import RedirectResponse
from uuid import UUID
from typing import Any, Optional

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
)
from supabase import Client


router = APIRouter(prefix="/api/v1/crm", tags=["crm"])


def get_hubspot_client_from_connection(
    user_id: str,
    supabase: Client,
) -> HubSpotClient:
    """
    Get HubSpot client from user's connection.
    
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
    
    access_token = connection["access_token"]
    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="HubSpot access token is missing",
        )
    
    return HubSpotClient(access_token)


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
async def get_hubspot_deal_schema(
    supabase: Client = Depends(get_supabase),
    user_id: str = Depends(get_user_id),
):
    """
    Get HubSpot deal schema (properties and pipelines).
    
    Used by frontend to build dynamic forms for field mapping.
    Uses database caching to avoid repeated API calls.
    
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
    
    schema = await schema_service.get_deal_schema()
    
    return schema


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
    config = await config_service.get_configuration(user_id)
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
    config = await config_service.get_configuration(user_id)
    
    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="CRM not configured. Please complete onboarding.",
        )
    
    return config


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

    ctx: dict = {"companyName": None, "contactName": None, "contactEmail": None, "raw_extraction": {}}

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

        company_ids = await association_service.get_associations("deals", deal_id, "companies")
        if company_ids:
            comp = await company_service.get(company_ids[0])
            ctx["companyName"] = comp.properties.get("name") or ctx["companyName"]

        contact_ids = await association_service.get_associations("deals", deal_id, "contacts")
        if contact_ids:
            contact = await contact_service.get(contact_ids[0])
            cprops = contact.properties
            first = cprops.get("firstname") or ""
            last = cprops.get("lastname") or ""
            ctx["contactName"] = f"{first} {last}".strip() or None
            ctx["contactEmail"] = cprops.get("email") or None
    except Exception:
        pass
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

