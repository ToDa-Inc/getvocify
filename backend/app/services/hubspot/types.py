"""
Pydantic models for HubSpot API types.

Mirrors HubSpot's API response structures and request formats.
"""

from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Any, Literal, Optional, Union
from datetime import datetime


# ============================================================================
# SCHEMA TYPES
# ============================================================================

class PropertyOption(BaseModel):
    """Option for enumeration properties"""
    label: str
    value: str
    hidden: bool = False
    description: Optional[str] = None


class HubSpotProperty(BaseModel):
    """HubSpot object property definition"""
    name: str
    label: str
    type: str  # string, number, date, datetime, enumeration, etc.
    fieldType: str = "text"  # text, textarea, select, checkbox, etc.
    groupName: str = "dealinformation"  # HubSpot may omit in some responses
    options: list[PropertyOption] = Field(default_factory=list)
    required: bool = False
    readOnlyValue: bool = False
    hidden: bool = False
    description: Optional[str] = None
    fill_policy: Optional[Literal["identity", "strategy", "research", "call_note", "explicit"]] = None
    
    class Config:
        # HubSpot uses camelCase in API responses
        populate_by_name = True


class HubSpotPipelineStage(BaseModel):
    """Deal pipeline stage"""
    id: str
    label: str
    displayOrder: int
    metadata: dict[str, Any] = Field(default_factory=dict)
    
    class Config:
        populate_by_name = True


class HubSpotPipeline(BaseModel):
    """Deal pipeline with stages"""
    id: str
    label: str
    displayOrder: int
    stages: list[HubSpotPipelineStage] = Field(default_factory=list)
    archived: bool = False
    
    class Config:
        populate_by_name = True


class CRMSchema(BaseModel):
    """
    Combined schema for frontend consumption.
    
    Contains all properties and pipelines for an object type.
    """
    object_type: Literal["contacts", "companies", "deals", "line_items"]
    properties: list[HubSpotProperty] = Field(default_factory=list)
    pipelines: list[HubSpotPipeline] = Field(default_factory=list)


# ============================================================================
# OBJECT TYPES
# ============================================================================

class HubSpotObject(BaseModel):
    """Base class for HubSpot CRM objects"""
    id: str
    properties: dict[str, Any] = Field(default_factory=dict)
    createdAt: datetime
    updatedAt: datetime
    archived: bool = False
    
    class Config:
        populate_by_name = True


class HubSpotContact(HubSpotObject):
    """HubSpot contact record"""
    pass


class HubSpotCompany(HubSpotObject):
    """HubSpot company record"""
    pass


class HubSpotDeal(HubSpotObject):
    """HubSpot deal record"""
    pass


# ============================================================================
# REQUEST TYPES
# ============================================================================

class AssociationTo(BaseModel):
    """Target object for an association (HubSpot format)"""
    id: Union[str, int]  # HubSpot accepts string or int for object IDs


class AssociationTypeSpec(BaseModel):
    """Association type specification (HubSpot format)"""
    associationCategory: str = "HUBSPOT_DEFINED"
    associationTypeId: int  # 3 = deal-to-contact, 5 = deal-to-company


class AssociationSpec(BaseModel):
    """Specification for creating an association (HubSpot create-object format)"""
    to: AssociationTo
    types: list[AssociationTypeSpec]


class CreateObjectRequest(BaseModel):
    """Request body for creating a HubSpot object"""
    properties: dict[str, Any] = Field(default_factory=dict)
    associations: list[AssociationSpec] = Field(default_factory=list)


class UpdateObjectRequest(BaseModel):
    """Request body for updating a HubSpot object"""
    properties: dict[str, Any] = Field(default_factory=dict)


# ============================================================================
# SEARCH TYPES
# ============================================================================

class Filter(BaseModel):
    """Single filter condition"""
    propertyName: str
    operator: Literal[
        "EQ",           # Equals
        "NEQ",          # Not equals
        "LT",           # Less than
        "LTE",          # Less than or equal
        "GT",           # Greater than
        "GTE",          # Greater than or equal
        "BETWEEN",      # Between two values
        "IN",           # In list
        "NOT_IN",       # Not in list
        "HAS_PROPERTY", # Property has value
        "NOT_HAS_PROPERTY", # Property is null
        "CONTAINS_TOKEN",   # Contains token (text search)
        "NOT_CONTAINS_TOKEN",
    ]
    value: Optional[str | int | float | list[str | int | float]] = None


class FilterGroup(BaseModel):
    """Group of filters (AND logic within group)"""
    filters: list[Filter] = Field(default_factory=list)


class SearchRequest(BaseModel):
    """Request body for searching HubSpot objects"""
    filterGroups: list[FilterGroup] = Field(default_factory=list)
    properties: list[str] = Field(default_factory=list)  # Properties to return
    limit: int = Field(default=10, ge=1, le=100)
    after: Optional[str] = None  # Pagination cursor


class SearchResponse(BaseModel):
    """Response from HubSpot search API"""
    results: list[dict[str, Any]] = Field(default_factory=list)
    paging: Optional[dict[str, Any]] = None


# ============================================================================
# VALIDATION & SYNC TYPES
# ============================================================================

class ValidationResult(BaseModel):
    """Result of token validation"""
    valid: bool
    portal_id: Optional[str] = None
    region: Optional[str] = "na1"  # eu1, na1, etc.
    ui_domain: Optional[str] = None
    scopes_ok: bool = False
    error: Optional[str] = None
    error_code: Optional[str] = None


class SyncResult(BaseModel):
    """Result of syncing a memo to HubSpot"""
    memo_id: str
    success: bool = False
    company_id: Optional[str] = None
    contact_id: Optional[str] = None
    deal_id: Optional[str] = None
    deal_name: Optional[str] = None
    deal_url: Optional[str] = None
    error: Optional[str] = None
    error_code: Optional[str] = None
    # MINOR degradation: call_outcome was requested and the guaranteed
    # record (see outcome_failed below) succeeded, but a secondary write
    # didn't - e.g. hs_lead_status has no valid mapped value for this
    # account (or the mapped value was deleted/renamed since configuring -
    # see call_outcome.py:resolve_lead_status_value), no closed-lost stage
    # configured on this pipeline, or no lost-reason property found on the
    # portal's deals. The outcome IS still visible in HubSpot (in the Lost
    # reason note, or via the On Hold follow-up task); this is a
    # non-blocking heads-up, shown as a banner UNDER the normal "Sync
    # Successful" screen (see popup.js renderSuccess). None when
    # call_outcome wasn't requested, or nothing degraded.
    outcome_warning: Optional[str] = None
    # CRITICAL failure: call_outcome was requested but nothing was recorded
    # anywhere. For Lost specifically this means the reason note itself
    # failed to write (see call_outcome.py:_ensure_lost_reason_note) - the
    # one guaranteed record for that outcome. Unlike outcome_warning, the
    # extension must NOT present this as success (see popup.js
    # renderSuccess) - the rep needs to know the outcome they just picked
    # did not stick, even though the rest of the memo (deal/contact/notes
    # from Steps 1-7) synced fine (success=True at the top level is still
    # correct - only the outcome step failed).
    outcome_failed: Optional[str] = None
    # Task sync summary for the extension success screen (non-blocking).
    tasks_requested_count: int = 0
    tasks_created_count: int = 0
    tasks_warning: Optional[str] = None

