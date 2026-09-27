"""
CRM configuration service for managing user preferences.
"""

from uuid import UUID
from typing import Optional
from supabase import Client
from fastapi import HTTPException, status

from app.models.crm_config import (
    CRMConfigurationRequest,
    CRMConfigurationResponse,
)
from app.services.hoy.crm_state import queue_states_enabled as _queue_states_enabled


def _meeting_booked_stage(config: CRMConfigurationRequest) -> dict:
    """A stage without its pipeline cannot be applied safely, so neither is stored."""
    pipeline = (config.meeting_booked_pipeline_id or "").strip() or None
    stage = (config.meeting_booked_stage_id or "").strip() or None
    if not (pipeline and stage):
        pipeline = stage = None
    return {"meeting_booked_pipeline_id": pipeline, "meeting_booked_stage_id": stage}


def _normalize_queue_states(config: CRMConfigurationRequest, *, provider: Optional[str]) -> dict:
    """Pipedrive always uses deal_stage. A state cannot sit in both booked and ended."""
    source = (config.queue_state_source or "deal_stage").strip() or "deal_stage"
    if (provider or "").lower() == "pipedrive" or source not in {"deal_stage", "lead_status"}:
        source = "deal_stage"
    booked: list[str] = []
    seen: set[str] = set()
    for raw in config.queue_booked_states or []:
        value = str(raw or "").strip()
        if value and value not in seen:
            booked.append(value)
            seen.add(value)
    ended: list[str] = []
    ended_seen: set[str] = set()
    for raw in config.queue_ended_states or []:
        value = str(raw or "").strip()
        if value and value not in seen and value not in ended_seen:
            ended.append(value)
            ended_seen.add(value)
    return {
        "queue_state_source": source,
        "queue_booked_states": booked,
        "queue_ended_states": ended,
    }


def _response_from_row(config_data: dict, *, company_id: Optional[str], supabase: Client) -> CRMConfigurationResponse:
    return CRMConfigurationResponse(
        id=UUID(config_data["id"]),
        connection_id=UUID(config_data["connection_id"]),
        default_pipeline_id=config_data.get("default_pipeline_id") or "",
        default_pipeline_name=config_data.get("default_pipeline_name") or "",
        default_stage_id=config_data.get("default_stage_id") or "",
        default_stage_name=config_data.get("default_stage_name") or "",
        allowed_deal_fields=config_data.get("allowed_deal_fields") or ["dealname", "amount", "description", "closedate"],
        allowed_contact_fields=config_data.get("allowed_contact_fields") or ["firstname", "lastname", "email", "phone"],
        allowed_company_fields=config_data.get("allowed_company_fields") or ["name", "domain"],
        allowed_line_item_fields=config_data.get("allowed_line_item_fields") or ["name", "quantity", "price"],
        auto_create_contacts=config_data.get("auto_create_contacts", True),
        auto_create_companies=config_data.get("auto_create_companies", True),
        lost_reasons=config_data.get("lost_reasons") or [
            "No budget", "No response", "Chose a competitor", "Bad timing", "Not a fit",
        ],
        lost_reason_deal_property=config_data.get("lost_reason_deal_property"),
        lost_lead_status_value=config_data.get("lost_lead_status_value"),
        on_hold_lead_status_value=config_data.get("on_hold_lead_status_value"),
        auto_sync_hubspot_calls=bool(config_data.get("auto_sync_hubspot_calls", False)),
        meeting_booked_pipeline_id=config_data.get("meeting_booked_pipeline_id"),
        meeting_booked_stage_id=config_data.get("meeting_booked_stage_id"),
        queue_state_source=config_data.get("queue_state_source") or "deal_stage",
        queue_booked_states=list(config_data.get("queue_booked_states") or []),
        queue_ended_states=list(config_data.get("queue_ended_states") or []),
        queue_states_enabled=_queue_states_enabled(supabase, company_id or config_data.get("company_id")),
        created_at=config_data.get("created_at") or "",
        updated_at=config_data.get("updated_at") or "",
    )


class CRMConfigurationService:
    """
    Service for managing CRM configurations.
    
    Handles CRUD operations for user CRM preferences including:
    - Pipeline and stage selection
    - Field whitelists
    - Auto-create settings
    """
    
    def __init__(self, supabase: Client):
        self.supabase = supabase
    
    async def get_configuration(
        self,
        user_id: str,
        connection_id: Optional[str] = None,
        provider: Optional[str] = None,
    ) -> Optional[CRMConfigurationResponse]:
        """
        Get user's CRM configuration for a connection.

        Resolution when connection_id is omitted:
        - If provider is set (e.g. \"hubspot\"): first connected row for that provider.
        - Else: primary/single connection via resolve_sync_connection (memo pipeline).
        """
        if not connection_id:
            if provider:
                from app.services.company import get_company_id_for_user

                company_id = get_company_id_for_user(self.supabase, user_id)
                if not company_id:
                    return None
                conn_result = (
                    self.supabase.table("crm_connections")
                    .select("id")
                    .eq("company_id", company_id)
                    .eq("provider", provider)
                    .eq("status", "connected")
                    .limit(1)
                    .execute()
                )
                if not conn_result.data:
                    return None
                connection_id = conn_result.data[0]["id"]
            else:
                from app.services.crm_providers.errors import AmbiguousPrimaryCRMError
                from app.services.crm_providers.resolve import resolve_sync_connection

                try:
                    row = resolve_sync_connection(self.supabase, user_id)
                except AmbiguousPrimaryCRMError:
                    return None
                if not row:
                    return None
                connection_id = str(row["id"])
        
        # Get configuration
        try:
            result = self.supabase.table("crm_configurations").select("*").eq(
                "connection_id", connection_id
            ).single().execute()
            
            if not result.data:
                return None
        except Exception as e:
            # Handle case where no configuration exists (PGRST116 error)
            error_str = str(e)
            if "no rows" in error_str.lower() or "PGRST116" in error_str:
                return None
            # Re-raise other errors
            raise
        
        config_data = result.data
        return _response_from_row(config_data, company_id=None, supabase=self.supabase)
    
    async def save_configuration(
        self,
        user_id: str,
        connection_id: str,
        config: CRMConfigurationRequest,
    ) -> CRMConfigurationResponse:
        """
        Save or update CRM configuration.
        
        Args:
            user_id: User ID
            connection_id: CRM connection ID
            config: Configuration data
            
        Returns:
            Saved configuration
            
        Raises:
            HTTPException if connection doesn't exist or belongs to another user
        """
        # Verify connection exists and belongs to user
        from app.services.company import get_company_id_for_user

        company_id = get_company_id_for_user(self.supabase, user_id)
        if not company_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No active company membership",
            )
        conn_result = self.supabase.table("crm_connections").select("*").eq(
            "id", connection_id
        ).eq("company_id", company_id).single().execute()
        
        if not conn_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="CRM connection not found",
            )
        provider = (conn_result.data.get("provider") or "").lower() or None

        # Prepare configuration data
        config_data = {
            "connection_id": connection_id,
            "user_id": user_id,
            "company_id": company_id,
            "default_pipeline_id": config.default_pipeline_id,
            "default_pipeline_name": config.default_pipeline_name,
            "default_stage_id": config.default_stage_id,
            "default_stage_name": config.default_stage_name,
            "allowed_deal_fields": config.allowed_deal_fields,
            "allowed_contact_fields": config.allowed_contact_fields,
            "allowed_company_fields": config.allowed_company_fields,
            "allowed_line_item_fields": config.allowed_line_item_fields,
            "auto_create_contacts": config.auto_create_contacts,
            "auto_create_companies": config.auto_create_companies,
            "lost_reasons": config.lost_reasons,
            "lost_reason_deal_property": config.lost_reason_deal_property,
            "lost_lead_status_value": config.lost_lead_status_value,
            "on_hold_lead_status_value": config.on_hold_lead_status_value,
            "auto_sync_hubspot_calls": config.auto_sync_hubspot_calls,
            **_meeting_booked_stage(config),
            **_normalize_queue_states(config, provider=provider),
        }
        
        # Upsert configuration
        result = self.supabase.table("crm_configurations").upsert(
            config_data,
            on_conflict="connection_id",
        ).execute()
        
        if not result.data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to save configuration",
            )
        
        saved_config = result.data[0]
        return _response_from_row(saved_config, company_id=company_id, supabase=self.supabase)
    
    async def is_configured(
        self,
        user_id: str,
        connection_id: Optional[str] = None,
    ) -> bool:
        """
        Check if user has configured their CRM.
        
        Args:
            user_id: User ID
            connection_id: Optional connection ID
            
        Returns:
            True if configured, False otherwise
        """
        config = await self.get_configuration(user_id, connection_id)
        return config is not None

