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
    allowed_line_item_fields: list[str] = Field(
        default=["name", "quantity", "price"],
        description="List of line item fields AI can create/update"
    )
    auto_create_contacts: bool = Field(
        default=True,
        description="Automatically create contacts if not found"
    )
    auto_create_companies: bool = Field(
        default=True,
        description="Automatically create companies if not found"
    )
    lost_reasons: list[str] = Field(
        default=["No budget", "No response", "Chose a competitor", "Bad timing", "Not a fit"],
        description="Configured Lost reasons shown in the extension's Lost picker (plus a UI-only 'Other')",
    )
    lost_reason_deal_property: Optional[str] = Field(
        None,
        description=(
            "Confirmed override for the deal property that stores the portal's "
            "closed-lost reason. Leave unset to let sync auto-detect it from the "
            "live deal schema on every call (see resolve_lost_reason_property)."
        ),
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
    allowed_line_item_fields: list[str] = Field(
        default_factory=lambda: ["name", "quantity", "price"]
    )
    auto_create_contacts: bool
    auto_create_companies: bool
    lost_reasons: list[str] = Field(
        default_factory=lambda: ["No budget", "No response", "Chose a competitor", "Bad timing", "Not a fit"]
    )
    lost_reason_deal_property: Optional[str] = None
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

