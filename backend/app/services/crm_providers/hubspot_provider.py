"""
HubSpot adapter: implements CRM protocols by delegating to existing hubspot services.
"""

from __future__ import annotations

from typing import Any, Optional, Union
from uuid import UUID

from supabase import Client

from app.models.approval import ApprovalPreview, DealMatch
from app.models.memo import MemoExtraction
from app.services.crm_updates import CRMUpdatesService
from app.services.hubspot import (
    HubSpotAssociationService,
    HubSpotClient,
    HubSpotCompanyService,
    HubSpotContactService,
    HubSpotDealService,
    HubSpotMatchingService,
    HubSpotPreviewService,
    HubSpotSchemaService,
    HubSpotSearchService,
    HubSpotSyncService,
    HubSpotTasksService,
    SyncResult,
)


class HubSpotCRMProvider:
    """Thin facade over HubSpot services for multi-CRM orchestration."""

    def __init__(self, supabase: Client, connection: dict[str, Any]) -> None:
        self._supabase = supabase
        self._connection = connection
        self._client = HubSpotClient(connection["access_token"])
        self._connection_id = str(connection["id"])

    def _schema_service(self) -> HubSpotSchemaService:
        return HubSpotSchemaService(self._client, self._supabase, self._connection_id)

    def _search_service(self) -> HubSpotSearchService:
        return HubSpotSearchService(self._client)

    def _deal_service(self) -> HubSpotDealService:
        return HubSpotDealService(self._client, self._search_service(), self._schema_service())

    def _sync_service(self) -> HubSpotSyncService:
        search = self._search_service()
        return HubSpotSyncService(
            client=self._client,
            contacts=HubSpotContactService(self._client, search),
            companies=HubSpotCompanyService(self._client, search),
            deals=self._deal_service(),
            associations=HubSpotAssociationService(self._client),
            tasks=HubSpotTasksService(self._client),
            crm_updates=CRMUpdatesService(self._supabase),
            supabase=self._supabase,
        )

    def _preview_service(self) -> HubSpotPreviewService:
        search = self._search_service()
        schema = self._schema_service()
        deals = self._deal_service()
        return HubSpotPreviewService(
            self._client,
            deals,
            schema,
            associations=HubSpotAssociationService(self._client),
            contact_service=HubSpotContactService(self._client, search),
            company_service=HubSpotCompanyService(self._client, search),
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
        transcript: Optional[str] = None,
        auto_create_contact_company: bool = False,
        auto_create_companies: Optional[bool] = None,
        auto_create_contacts: Optional[bool] = None,
        default_stage_name: Optional[str] = None,
        default_pipeline_id: Optional[str] = None,
        default_stage_id: Optional[str] = None,
    ) -> SyncResult:
        # default_stage_name is a label; Salesforce resolves labels via picklist lookup.
        # HubSpot's CRM Configuration screen already stores canonical IDs, so we use
        # default_pipeline_id/default_stage_id directly (no ambiguous name resolution).
        del default_stage_name
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
            default_pipeline_id=default_pipeline_id,
            default_stage_id=default_stage_id,
        )

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
    ) -> ApprovalPreview:
        del default_stage_name  # HubSpot Configuration stores canonical IDs, not names
        return await self._preview_service().build_preview(
            memo_id=memo_id,
            transcript=transcript,
            extraction=extraction,
            matched_deals=matched_deals,
            selected_deal_id=selected_deal_id,
            allowed_fields=allowed_fields,
            default_pipeline_id=default_pipeline_id,
            default_stage_id=default_stage_id,
        )

    async def find_matching_deals(
        self,
        extraction: MemoExtraction,
        limit: int = 3,
        pipeline_id: Optional[str] = None,
    ) -> list[DealMatch]:
        matching = HubSpotMatchingService(self._client, self._search_service())
        return await matching.find_matching_deals(extraction, limit=limit, pipeline_id=pipeline_id)

    async def get_curated_field_specs(self, allowed_fields: list[str]) -> list[dict[str, Any]]:
        return await self._schema_service().get_curated_field_specs("deals", allowed_fields)
