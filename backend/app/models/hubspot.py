"""
Pydantic models for HubSpot CRM integration API
"""

from pydantic import BaseModel, Field
from typing import Optional, Any
from uuid import UUID


class ConnectHubSpotRequest(BaseModel):
    """Request to connect HubSpot Private App"""
    access_token: str = Field(..., description="HubSpot Private App access token")


class ConnectHubSpotResponse(BaseModel):
    """Response from connecting HubSpot"""
    connection_id: UUID
    status: str
    portal_id: Optional[str] = None


class TestConnectionResponse(BaseModel):
    """Response from testing HubSpot connection"""
    valid: bool
    portal_id: Optional[str] = None
    scopes_ok: bool = False
    error: Optional[str] = None
    error_code: Optional[str] = None


class HubSpotConnection(BaseModel):
    """HubSpot connection details"""
    id: UUID
    user_id: UUID
    provider: str = "hubspot"
    status: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str
    updated_at: str


class CreateDealRequest(BaseModel):
    """Request to create a HubSpot deal"""
    deal_name: str = Field(..., description="Deal name (required)")
    amount: Optional[str] = Field(None, description="Deal amount")
    description: Optional[str] = Field(None, description="Deal description")


class UpdateDealRequest(BaseModel):
    """Request to update a HubSpot deal"""
    deal_name: Optional[str] = Field(None, description="Deal name")
    amount: Optional[str] = Field(None, description="Deal amount")
    description: Optional[str] = Field(None, description="Deal description")

