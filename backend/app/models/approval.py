"""
Models for approval flow and deal matching.
"""

from pydantic import BaseModel, Field
from typing import Optional
from uuid import UUID


class DealMatch(BaseModel):
    """A potential matching deal from HubSpot"""
    deal_id: str
    deal_name: str
    company_name: Optional[str] = None
    contact_name: Optional[str] = None
    amount: Optional[str] = None
    stage: Optional[str] = None
    last_updated: str
    match_confidence: float = Field(ge=0.0, le=1.0, description="Confidence score 0-1")
    match_reason: str = Field(..., description="Why this deal was matched")


class ProposedUpdate(BaseModel):
    """A proposed field update"""
    field_name: str
    field_label: str
    current_value: Optional[str] = None
    new_value: str
    extraction_confidence: float = Field(ge=0.0, le=1.0)


class ApprovalPreview(BaseModel):
    """Preview of what will be synced to CRM"""
    memo_id: UUID
    transcript_summary: str = Field(..., description="First 200 chars of transcript")
    
    # Deal matching
    matched_deals: list[DealMatch] = Field(default_factory=list)
    selected_deal: Optional[DealMatch] = None
    is_new_deal: bool = False
    
    # Proposed changes
    proposed_updates: list[ProposedUpdate] = Field(default_factory=list)
    
    # Contact/Company if creating
    new_contact: Optional[dict] = None
    new_company: Optional[dict] = None


class ApproveRequest(BaseModel):
    """Request to approve and sync"""
    deal_id: Optional[str] = Field(None, description="Deal ID to update (None = create new)")
    is_new_deal: bool = Field(default=False, description="Whether to create a new deal")
    extraction: Optional[dict] = Field(None, description="Optional edited extraction data")

