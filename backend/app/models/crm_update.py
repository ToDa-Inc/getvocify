"""
Pydantic models for CRM Update tracking
"""

from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from datetime import datetime
from uuid import UUID


class CRMUpdateBase(BaseModel):
    """Base CRM update model"""
    memo_id: UUID
    crm_connection_id: UUID
    action_type: str = Field(..., description="Type of action: create_deal, update_deal, etc.")
    resource_type: str = Field(..., description="CRM resource type: deal, contact, company, etc.")
    data: Dict[str, Any] = Field(default_factory=dict, description="Data sent to CRM")
    status: str = Field(default="pending", description="pending, success, failed, retrying")


class CRMUpdateCreate(CRMUpdateBase):
    """Model for creating a new CRM update record"""
    user_id: str


class CRMUpdateUpdate(BaseModel):
    """Model for updating CRM update status"""
    resource_id: Optional[str] = None
    response: Optional[Dict[str, Any]] = None
    status: Optional[str] = None
    error_message: Optional[str] = None
    retry_count: Optional[int] = None
    completed_at: Optional[datetime] = None


class CRMUpdate(CRMUpdateBase):
    """Full CRM update model returned by API"""
    id: UUID
    user_id: str
    resource_id: Optional[str] = None
    response: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    retry_count: int = 0
    created_at: datetime
    completed_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


