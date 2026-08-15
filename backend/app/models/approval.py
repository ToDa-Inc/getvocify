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
    contact_email: Optional[str] = None
    amount: Optional[str] = None
    stage: Optional[str] = None
    last_updated: str
    match_confidence: float = Field(ge=0.0, le=1.0, description="Confidence score 0-1")
    match_reason: str = Field(..., description="Why this deal was matched")


class ContactMatch(BaseModel):
    """Resolved HubSpot contact used as the identity anchor for approval/sync."""
    contact_id: str
    email: str = ""
    name: Optional[str] = None
    phone: Optional[str] = None
    jobtitle: Optional[str] = None
    company_id: Optional[str] = None
    company_name: Optional[str] = None
    match_confidence: float = Field(ge=0.0, le=1.0, default=0.98)
    match_reason: str = Field(default="Contact email match")


class ProposedUpdate(BaseModel):
    """A proposed field update"""
    field_name: str
    field_label: str
    current_value: Optional[str] = None
    new_value: str
    extraction_confidence: float = Field(ge=0.0, le=1.0)
    field_type: Optional[str] = Field(None, description="HubSpot schema type for inline edit")
    options: Optional[list[dict]] = Field(None, description="Enum options {value, label} for dropdowns")
    object_type: Optional[str] = Field(
        None,
        description="CRM object this field belongs to: deals | contacts | companies | line_items | task",
    )


class AvailableField(BaseModel):
    """Field available to add (in allowed_*_fields but not in proposed_updates)"""
    name: str
    label: str
    type: str = "string"
    options: Optional[list[dict]] = None
    object_type: Optional[str] = Field(
        default="deals",
        description="CRM object this field belongs to",
    )


class CallOutcomeAvailability(BaseModel):
    """
    Per-outcome gate for the extension's Converted/On Hold/Lost buttons -
    computed fresh on every preview (see
    hubspot/call_outcome.py:compute_call_outcome_availability), never just
    trusted from saved configuration.

    - converted: needs no per-account setup (reuses HubSpot's own
      'Open Deal' hs_lead_status default) - False only if that default
      itself is missing from this portal's live schema (rare).
    - on_hold / lost: each requires the admin to map one of THEIR OWN
      EXISTING hs_lead_status values to that meaning, from the HubSpot
      Configuration screen - Vocify never creates HubSpot picklist options
      itself (see call_outcome.py module docstring). False when unmapped,
      or when the mapped value no longer exists in the live schema (the
      client deleted/renamed it since configuring) - never silently write
      an invalid value, never show a button that would then no-op.
    """
    converted: bool = False
    on_hold: bool = False
    lost: bool = False


class ApprovalPreview(BaseModel):
    """Preview of what will be synced to CRM"""
    memo_id: UUID
    transcript_summary: str = Field(..., description="First 200 chars of transcript")
    transcript: Optional[str] = Field(None, description="Full transcript for review")
    
    # Deal matching
    matched_deals: list[DealMatch] = Field(default_factory=list)
    selected_deal: Optional[DealMatch] = None
    is_new_deal: bool = False
    # Contact-first identity. Deals are optional when this is set.
    selected_contact: Optional[ContactMatch] = None
    contact_candidates: list[ContactMatch] = Field(
        default_factory=list,
        description="Ambiguous contact matches requiring user confirmation",
    )
    skip_deal: bool = Field(
        default=False,
        description="True when syncing contact/company without creating or updating a deal",
    )

    # Proposed changes
    proposed_updates: list[ProposedUpdate] = Field(default_factory=list)
    available_fields: list[AvailableField] = Field(
        default_factory=list,
        description="Fields in allowed_*_fields not yet in proposed_updates (for Add field)",
    )
    # Allowlists used for this preview (so UI can show what is in scope)
    allowed_deal_fields: list[str] = Field(default_factory=list)
    allowed_contact_fields: list[str] = Field(default_factory=list)
    allowed_company_fields: list[str] = Field(default_factory=list)
    allowed_line_item_fields: list[str] = Field(default_factory=list)

    # Contact/Company if creating
    new_contact: Optional[dict] = None
    new_company: Optional[dict] = None

    # Call outcome (Converted / On Hold / Lost). Configured reasons for the
    # Lost picker - set from crm_configurations.lost_reasons in the API layer,
    # not by build_preview itself, so the extension gets the list in the same
    # round-trip as everything else instead of a separate config fetch.
    # "Other" (free text) is UI-only and deliberately not included here.
    lost_reasons: list[str] = Field(default_factory=list)
    # Per-outcome gate - see CallOutcomeAvailability above. Set from the API
    # layer (app/api/memos.py) alongside lost_reasons, same round-trip
    # reasoning: the extension must not show a button for an outcome that
    # isn't available for this account - never offer one and fail after the
    # rep clicks it.
    call_outcome_availability: CallOutcomeAvailability = Field(default_factory=CallOutcomeAvailability)


class ApproveRequest(BaseModel):
    """Request to approve and sync"""
    deal_id: Optional[str] = Field(None, description="Deal ID to update (None = create new)")
    is_new_deal: bool = Field(default=False, description="Whether to create a new deal")
    extraction: Optional[dict] = Field(None, description="Optional edited extraction data")


class PreviewRequest(BaseModel):
    """Request body for preview with optional edited extraction"""
    deal_id: Optional[str] = Field(None, description="Deal ID to update (None = create new)")
    create_new_deal: bool = Field(default=False, description="Force create-new-deal preview mode")
    contact_id: Optional[str] = Field(
        None,
        description="Explicit HubSpot contact ID (page context or candidate pick)",
    )
    extraction: Optional[dict] = Field(None, description="Edited extraction data (overrides stored)")

