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
    object_type: Literal["contacts", "companies", "deals"]
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

