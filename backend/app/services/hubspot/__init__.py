"""
HubSpot CRM integration service layer.

This module provides a complete interface to HubSpot's CRM API,
including schema discovery, object CRUD operations, associations,
and synchronization orchestration.
"""

from .client import HubSpotClient
from .exceptions import (
    HubSpotError,
    HubSpotAuthError,
    HubSpotScopeError,
    HubSpotNotFoundError,
    HubSpotConflictError,
    HubSpotRateLimitError,
    HubSpotServerError,
    HubSpotValidationError,
)
from .types import (
    HubSpotProperty,
    HubSpotPipelineStage,
    HubSpotPipeline,
    CRMSchema,
    HubSpotContact,
    HubSpotCompany,
    HubSpotDeal,
    CreateObjectRequest,
    UpdateObjectRequest,
    SearchRequest,
    FilterGroup,
    Filter,
    ValidationResult,
    SyncResult,
)
from .validation import HubSpotValidationService
from .schema import HubSpotSchemaService
from .search import HubSpotSearchService
from .contacts import HubSpotContactService
from .companies import HubSpotCompanyService
from .deals import HubSpotDealService
from .associations import HubSpotAssociationService
from .sync import HubSpotSyncService
from .matching import HubSpotMatchingService
from .preview import HubSpotPreviewService

__all__ = [
    # Client
    "HubSpotClient",
    # Exceptions
    "HubSpotError",
    "HubSpotAuthError",
    "HubSpotScopeError",
    "HubSpotNotFoundError",
    "HubSpotConflictError",
    "HubSpotRateLimitError",
    "HubSpotServerError",
    "HubSpotValidationError",
    # Types
    "HubSpotProperty",
    "HubSpotPipelineStage",
    "HubSpotPipeline",
    "CRMSchema",
    "HubSpotContact",
    "HubSpotCompany",
    "HubSpotDeal",
    "CreateObjectRequest",
    "UpdateObjectRequest",
    "SearchRequest",
    "FilterGroup",
    "Filter",
    "ValidationResult",
    "SyncResult",
    # Services
    "HubSpotValidationService",
    "HubSpotSchemaService",
    "HubSpotSearchService",
    "HubSpotContactService",
    "HubSpotCompanyService",
    "HubSpotDealService",
    "HubSpotAssociationService",
    "HubSpotSyncService",
    "HubSpotMatchingService",
    "HubSpotPreviewService",
]

