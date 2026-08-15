"""
CRM provider contracts (ISP): callers depend on narrow methods, not concrete HubSpot/Salesforce types.
"""

from __future__ import annotations

from typing import Any, Optional, Protocol, Union
from uuid import UUID

from app.models.approval import ApprovalPreview, DealMatch
from app.models.memo import MemoExtraction
from app.services.hubspot.types import CallOutcomeCapability, SyncResult


class CRMExtractionSyncProtocol(Protocol):
    """Sync approved memo extraction to this CRM."""

    async def sync_memo(
        self,
        memo_id: Union[UUID, str],
        user_id: str,
        connection_id: Union[UUID, str],
        extraction: MemoExtraction,
        deal_id: Optional[str] = None,
        is_new_deal: bool = False,
        allowed_fields: Optional[list[str]] = None,
        allowed_contact_fields: Optional[list[str]] = None,
        allowed_company_fields: Optional[list[str]] = None,
        allowed_line_item_fields: Optional[list[str]] = None,
        transcript: Optional[str] = None,
        auto_create_contact_company: bool = False,
        auto_create_companies: Optional[bool] = None,
        auto_create_contacts: Optional[bool] = None,
        default_stage_name: Optional[str] = None,
        default_pipeline_id: Optional[str] = None,
        default_stage_id: Optional[str] = None,
        create_note: bool = True,
        contact_id: Optional[str] = None,
        company_id: Optional[str] = None,
        skip_deal: bool = False,
        call_outcome: Optional[str] = None,
        lost_reason: Optional[str] = None,
        lost_reason_deal_property: Optional[str] = None,
    ) -> SyncResult: ...


class CRMPreviewProtocol(Protocol):
    """Build approval preview for this CRM."""

    async def build_preview(
        self,
        memo_id: UUID,
        transcript: str,
        extraction: MemoExtraction,
        matched_deals: list[DealMatch],
        selected_deal_id: Optional[str],
        allowed_fields: Optional[list[str]],
        allowed_contact_fields: Optional[list[str]] = None,
        allowed_company_fields: Optional[list[str]] = None,
        allowed_line_item_fields: Optional[list[str]] = None,
        default_stage_name: Optional[str] = None,
        default_pipeline_id: Optional[str] = None,
        default_stage_id: Optional[str] = None,
        selected_contact: Optional[Any] = None,
        contact_candidates: Optional[Any] = None,
        create_new_deal: bool = False,
    ) -> ApprovalPreview: ...


class CRMDealMatchProtocol(Protocol):
    """Find candidate deals/opportunities for matcher UI."""

    async def find_matching_deals(
        self,
        extraction: MemoExtraction,
        limit: int = 3,
        pipeline_id: Optional[str] = None,
    ) -> list[DealMatch]: ...

    async def resolve_contact_anchor(
        self,
        extraction: MemoExtraction,
        limit_deals: int = 5,
        pipeline_id: Optional[str] = None,
        preferred_contact_id: Optional[str] = None,
    ) -> Any: ...

    async def resolve_identity(
        self,
        extraction: MemoExtraction,
        limit_deals: int = 5,
        pipeline_id: Optional[str] = None,
        preferred_contact_id: Optional[str] = None,
    ) -> Any: ...


class CRMCallOutcomeCapabilityProtocol(Protocol):
    """Whether this connection can currently record call outcomes - see
    app/services/hubspot/call_outcome.py:ensure_call_outcome_capability."""

    async def ensure_call_outcome_capability(self) -> CallOutcomeCapability: ...


class CRMFieldSpecsProtocol(Protocol):
    """Curated field metadata for LLM extraction (allowed CRM fields)."""

    async def get_curated_field_specs(self, allowed_fields: list[str]) -> list[dict[str, Any]]: ...

    async def get_extraction_field_specs(
        self,
        allowed_deal_fields: Optional[list[str]] = None,
        allowed_contact_fields: Optional[list[str]] = None,
        allowed_company_fields: Optional[list[str]] = None,
        allowed_line_item_fields: Optional[list[str]] = None,
    ) -> list[dict[str, Any]]: ...
