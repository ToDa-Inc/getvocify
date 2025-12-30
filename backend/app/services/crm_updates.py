"""
CRM Updates service for tracking what was pushed to CRM
"""

from datetime import datetime
from supabase import Client
from typing import Dict, Any, Optional
from app.models.crm_update import CRMUpdateCreate, CRMUpdateUpdate


class CRMUpdatesService:
    """Service for creating and tracking CRM updates"""
    
    def __init__(self, supabase: Client):
        self.supabase = supabase
    
    async def create_update(
        self,
        memo_id: str,
        user_id: str,
        crm_connection_id: str,
        action_type: str,
        resource_type: str,
        data: Dict[str, Any]
    ) -> str:
        """
        Create a CRM update record
        
        Returns:
            The created CRM update ID
        """
        update_data = {
            "memo_id": memo_id,
            "user_id": user_id,
            "crm_connection_id": crm_connection_id,
            "action_type": action_type,
            "resource_type": resource_type,
            "data": data,
            "status": "pending",
        }
        
        result = self.supabase.table("crm_updates").insert(update_data).execute()
        
        if not result.data:
            raise Exception("Failed to create CRM update record")
        
        return result.data[0]["id"]
    
    async def mark_success(
        self,
        update_id: str,
        resource_id: str,
        response: Optional[Dict[str, Any]] = None
    ) -> None:
        """Mark a CRM update as successful"""
        self.supabase.table("crm_updates").update({
            "status": "success",
            "resource_id": resource_id,
            "response": response or {},
            "completed_at": datetime.utcnow().isoformat(),
        }).eq("id", update_id).execute()
    
    async def mark_failed(
        self,
        update_id: str,
        error_message: str,
        retry_count: Optional[int] = None
    ) -> None:
        """Mark a CRM update as failed"""
        update_data = {
            "status": "failed",
            "error_message": error_message,
            "completed_at": datetime.utcnow().isoformat(),
        }
        
        if retry_count is not None:
            update_data["retry_count"] = retry_count
        
        self.supabase.table("crm_updates").update(update_data).eq("id", update_id).execute()
    
    async def mark_retrying(
        self,
        update_id: str,
        retry_count: int
    ) -> None:
        """Mark a CRM update as retrying"""
        self.supabase.table("crm_updates").update({
            "status": "retrying",
            "retry_count": retry_count,
        }).eq("id", update_id).execute()
    
    async def get_memo_updates(self, memo_id: str) -> list[Dict[str, Any]]:
        """Get all CRM updates for a memo"""
        result = self.supabase.table("crm_updates").select("*").eq("memo_id", memo_id).order("created_at", desc=False).execute()
        return result.data or []


