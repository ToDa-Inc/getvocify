"""
CRM configuration models for user preferences and settings.
"""

from pydantic import BaseModel, Field
from typing import Optional
from uuid import UUID


class CRMConfigurationRequest(BaseModel):
    """Request to save CRM configuration"""
    default_pipeline_id: str = Field(..., description="HubSpot pipeline ID")
    default_pipeline_name: str = Field(..., description="HubSpot pipeline name")
    default_stage_id: str = Field(..., description="Default stage ID for new deals")
    default_stage_name: str = Field(..., description="Default stage name")
    allowed_deal_fields: list[str] = Field(
        default=["dealname", "amount", "description", "closedate"],
        description="List of deal fields AI can update"
    )
    allowed_contact_fields: list[str] = Field(
        default=["firstname", "lastname", "email", "phone"],
        description="List of contact fields AI can update"
    )
    allowed_company_fields: list[str] = Field(
        default=["name", "domain"],
        description="List of company fields AI can update"
    )
    auto_create_contacts: bool = Field(
        default=True,
        description="Automatically create contacts if not found"
    )
    auto_create_companies: bool = Field(
        default=True,
        description="Automatically create companies if not found"
    )


class CRMConfigurationResponse(BaseModel):
    """CRM configuration response"""
    id: UUID
    connection_id: UUID
    default_pipeline_id: str
    default_pipeline_name: str
    default_stage_id: str
    default_stage_name: str
    allowed_deal_fields: list[str]
    allowed_contact_fields: list[str]
    allowed_company_fields: list[str]
    auto_create_contacts: bool
    auto_create_companies: bool
    is_configured: bool = True
    created_at: str
    updated_at: str


class PipelineOption(BaseModel):
    """Pipeline option for selection"""
    id: str
    label: str
    stages: list["StageOption"] = Field(default_factory=list)


class StageOption(BaseModel):
    """Stage option within a pipeline"""
    id: str
    label: str
    display_order: int

