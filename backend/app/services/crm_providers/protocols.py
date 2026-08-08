"""
CRM provider contracts (ISP): callers depend on narrow methods, not concrete HubSpot/Salesforce types.
"""

from __future__ import annotations

from typing import Any, Optional, Protocol, Union
from uuid import UUID

from app.models.approval import ApprovalPreview, DealMatch
from app.models.memo import MemoExtraction
from app.services.hubspot.types import SyncResult


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
        transcript: Optional[str] = None,
        auto_create_contact_company: bool = False,
        auto_create_companies: Optional[bool] = None,
        auto_create_contacts: Optional[bool] = None,
        default_stage_name: Optional[str] = None,
        default_pipeline_id: Optional[str] = None,
        default_stage_id: Optional[str] = None,
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
        default_stage_name: Optional[str] = None,
        default_pipeline_id: Optional[str] = None,
        default_stage_id: Optional[str] = None,
    ) -> ApprovalPreview: ...


class CRMDealMatchProtocol(Protocol):
    """Find candidate deals/opportunities for matcher UI."""

    async def find_matching_deals(
        self,
        extraction: MemoExtraction,
        limit: int = 3,
        pipeline_id: Optional[str] = None,
    ) -> list[DealMatch]: ...


class CRMFieldSpecsProtocol(Protocol):
    """Curated field metadata for LLM extraction (allowed deal-like fields)."""

    async def get_curated_field_specs(self, allowed_fields: list[str]) -> list[dict[str, Any]]: ...
