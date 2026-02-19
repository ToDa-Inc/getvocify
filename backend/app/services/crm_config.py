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
    ) -> Optional[CRMConfigurationResponse]:
        """
        Get user's CRM configuration.
        
        Args:
            user_id: User ID
            connection_id: Optional connection ID (if not provided, finds first HubSpot connection)
            
        Returns:
            Configuration if found, None otherwise
        """
        # If no connection_id provided, find user's HubSpot connection
        if not connection_id:
            conn_result = self.supabase.table("crm_connections").select("id").eq(
                "user_id", user_id
            ).eq("provider", "hubspot").eq("status", "connected").limit(1).execute()
            
            if not conn_result.data:
                return None
            
            connection_id = conn_result.data[0]["id"]
        
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
            auto_create_contacts=config_data.get("auto_create_contacts", True),
            auto_create_companies=config_data.get("auto_create_companies", True),
            created_at=config_data.get("created_at") or "",
            updated_at=config_data.get("updated_at") or "",
        )
    
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
        conn_result = self.supabase.table("crm_connections").select("*").eq(
            "id", connection_id
        ).eq("user_id", user_id).single().execute()
        
        if not conn_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="CRM connection not found",
            )
        
        # Prepare configuration data
        config_data = {
            "connection_id": connection_id,
            "user_id": user_id,
            "default_pipeline_id": config.default_pipeline_id,
            "default_pipeline_name": config.default_pipeline_name,
            "default_stage_id": config.default_stage_id,
            "default_stage_name": config.default_stage_name,
            "allowed_deal_fields": config.allowed_deal_fields,
            "allowed_contact_fields": config.allowed_contact_fields,
            "allowed_company_fields": config.allowed_company_fields,
            "auto_create_contacts": config.auto_create_contacts,
            "auto_create_companies": config.auto_create_companies,
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
        
        return CRMConfigurationResponse(
            id=UUID(saved_config["id"]),
            connection_id=UUID(saved_config["connection_id"]),
            default_pipeline_id=saved_config["default_pipeline_id"],
            default_pipeline_name=saved_config["default_pipeline_name"],
            default_stage_id=saved_config["default_stage_id"],
            default_stage_name=saved_config["default_stage_name"],
            allowed_deal_fields=saved_config["allowed_deal_fields"],
            allowed_contact_fields=saved_config["allowed_contact_fields"],
            allowed_company_fields=saved_config["allowed_company_fields"],
            auto_create_contacts=saved_config["auto_create_contacts"],
            auto_create_companies=saved_config["auto_create_companies"],
            created_at=saved_config["created_at"],
            updated_at=saved_config["updated_at"],
        )
    
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

