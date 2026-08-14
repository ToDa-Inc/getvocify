"""Salesforce adapter implementing CRM protocols."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional, Union
from uuid import UUID

from supabase import Client

from app.models.approval import ApprovalPreview, DealMatch
from app.models.memo import MemoExtraction
from app.services.crm_updates import CRMUpdatesService
from app.services.hubspot.types import SyncResult
from app.services.salesforce.client import SalesforceClient
from app.services.salesforce.matching import SalesforceMatchingService
from app.services.salesforce.opportunities import SalesforceOpportunityService
from app.services.salesforce.preview import SalesforcePreviewService
from app.services.salesforce.schema import SalesforceSchemaService
from app.services.salesforce.search import SalesforceSearchService
from app.services.salesforce.sync import SalesforceSyncService


def _parse_expires_at(raw: Any) -> Optional[datetime]:
    if not raw:
        return None
    try:
        s = str(raw).replace("Z", "+00:00")
        return datetime.fromisoformat(s)
    except Exception:
        return None


class SalesforceCRMProvider:
    def __init__(self, supabase: Client, connection: dict[str, Any]) -> None:
        self._supabase = supabase
        self._connection = connection
        meta = connection.get("metadata") or {}
        instance_url = meta.get("instance_url") or ""
        if not instance_url:
            raise ValueError("Salesforce connection missing instance_url in metadata")
        self._connection_id = str(connection["id"])
        self._client = SalesforceClient(
            instance_url=instance_url,
            access_token=connection["access_token"],
            refresh_token=connection.get("refresh_token"),
            connection_id=self._connection_id,
            supabase=supabase,
            token_expires_at=_parse_expires_at(connection.get("token_expires_at")),
        )

    def _search(self) -> SalesforceSearchService:
        return SalesforceSearchService(self._client)

    def _schema(self) -> SalesforceSchemaService:
        return SalesforceSchemaService(self._client, self._supabase, self._connection_id)

    def _opportunities(self) -> SalesforceOpportunityService:
        return SalesforceOpportunityService(self._client, self._schema())

    def _sync_service(self) -> SalesforceSyncService:
        return SalesforceSyncService(
            self._client,
            self._supabase,
            CRMUpdatesService(self._supabase),
        )

    def _preview_service(self) -> SalesforcePreviewService:
        sch = self._schema()
        return SalesforcePreviewService(
            self._client,
            self._opportunities(),
            sch,
            self._search(),
        )

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
    ) -> SyncResult:
        # Salesforce opportunities use a flat picklist (StageName), not pipeline+stage IDs.
        del default_pipeline_id, default_stage_id
        del create_note  # Salesforce path does not create HubSpot-style notes here
        del allowed_contact_fields, allowed_company_fields, allowed_line_item_fields
        del contact_id, company_id  # HubSpot contact-first anchors; not used for SF yet
        if skip_deal:
            # Salesforce doesn't support contact-first sync yet: an Opportunity is
            # always required. Fail loudly instead of silently creating one while the
            # preview told the user "Contact only (no deal)" - a visible error beats a
            # sync that does something different from what was promised.
            return SyncResult(
                memo_id=str(memo_id),
                success=False,
                error=(
                    "Salesforce doesn't support contact-only sync yet. "
                    "An Opportunity is required - select or create one to sync this memo."
                ),
                error_code="SKIP_DEAL_UNSUPPORTED",
            )
        return await self._sync_service().sync_memo(
            memo_id=memo_id,
            user_id=user_id,
            connection_id=connection_id,
            extraction=extraction,
            deal_id=deal_id,
            is_new_deal=is_new_deal,
            allowed_fields=allowed_fields,
            transcript=transcript,
            auto_create_contact_company=auto_create_contact_company,
            auto_create_companies=auto_create_companies,
            auto_create_contacts=auto_create_contacts,
            default_stage_name=default_stage_name,
        )

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
    ) -> ApprovalPreview:
        del default_pipeline_id, default_stage_id
        del allowed_contact_fields, allowed_company_fields, allowed_line_item_fields
        del selected_contact, contact_candidates, create_new_deal
        return await self._preview_service().build_preview(
            memo_id=memo_id,
            transcript=transcript,
            extraction=extraction,
            matched_deals=matched_deals,
            selected_deal_id=selected_deal_id,
            allowed_fields=allowed_fields,
            default_stage_name=default_stage_name,
        )

    async def find_matching_deals(
        self,
        extraction: MemoExtraction,
        limit: int = 3,
        pipeline_id: Optional[str] = None,
    ) -> list[DealMatch]:
        m = SalesforceMatchingService(self._client, self._search())
        return await m.find_matching_deals(extraction, limit=limit, pipeline_id=pipeline_id)

    async def resolve_contact_anchor(
        self,
        extraction: MemoExtraction,
        limit_deals: int = 5,
        pipeline_id: Optional[str] = None,
        preferred_contact_id: Optional[str] = None,
    ) -> None:
        del extraction, limit_deals, pipeline_id, preferred_contact_id
        return None

    async def resolve_identity(
        self,
        extraction: MemoExtraction,
        limit_deals: int = 5,
        pipeline_id: Optional[str] = None,
        preferred_contact_id: Optional[str] = None,
    ):
        del extraction, limit_deals, pipeline_id, preferred_contact_id
        return None

    async def get_curated_field_specs(self, allowed_fields: list[str]) -> list[dict[str, Any]]:
        return await self._schema().get_curated_field_specs(allowed_fields)

    async def get_extraction_field_specs(
        self,
        allowed_deal_fields: Optional[list[str]] = None,
        allowed_contact_fields: Optional[list[str]] = None,
        allowed_company_fields: Optional[list[str]] = None,
        allowed_line_item_fields: Optional[list[str]] = None,
    ) -> list[dict[str, Any]]:
        # Salesforce: deal/opportunity fields only for now (line items N/A).
        del allowed_contact_fields, allowed_company_fields, allowed_line_item_fields
        if not allowed_deal_fields:
            return []
        return await self.get_curated_field_specs(allowed_deal_fields)
