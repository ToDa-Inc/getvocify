"""
HubSpot adapter: implements CRM protocols by delegating to existing hubspot services.
"""

from __future__ import annotations

from typing import Any, Optional, Union
from uuid import UUID

from supabase import Client

from app.models.approval import ApprovalPreview, CallOutcomeAvailability, DealMatch
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
from app.services.hubspot.call_outcome import compute_call_outcome_availability


class HubSpotCRMProvider:
    """Thin facade over HubSpot services for multi-CRM orchestration."""

    def __init__(self, supabase: Client, connection: dict[str, Any]) -> None:
        from app.services.hubspot.oauth import ensure_fresh_hubspot_connection

        self._supabase = supabase
        self._connection = ensure_fresh_hubspot_connection(supabase, connection)
        self._client = HubSpotClient(self._connection["access_token"])
        self._connection_id = str(self._connection["id"])

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
        lost_lead_status_value: Optional[str] = None,
        on_hold_lead_status_value: Optional[str] = None,
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
            allowed_contact_fields=allowed_contact_fields,
            allowed_company_fields=allowed_company_fields,
            allowed_line_item_fields=allowed_line_item_fields,
            transcript=transcript,
            auto_create_contact_company=auto_create_contact_company,
            auto_create_companies=auto_create_companies,
            auto_create_contacts=auto_create_contacts,
            default_pipeline_id=default_pipeline_id,
            default_stage_id=default_stage_id,
            create_note=create_note,
            contact_id=contact_id,
            company_id=company_id,
            skip_deal=skip_deal,
            call_outcome=call_outcome,
            lost_reason=lost_reason,
            lost_reason_deal_property=lost_reason_deal_property,
            lost_lead_status_value=lost_lead_status_value,
            on_hold_lead_status_value=on_hold_lead_status_value,
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
        selected_contact=None,
        contact_candidates=None,
        create_new_deal: bool = False,
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
            allowed_contact_fields=allowed_contact_fields,
            allowed_company_fields=allowed_company_fields,
            allowed_line_item_fields=allowed_line_item_fields,
            selected_contact=selected_contact,
            contact_candidates=contact_candidates,
            create_new_deal=create_new_deal,
        )

    async def find_matching_deals(
        self,
        extraction: MemoExtraction,
        limit: int = 3,
        pipeline_id: Optional[str] = None,
    ) -> list[DealMatch]:
        matching = HubSpotMatchingService(
            self._client,
            self._search_service(),
            HubSpotAssociationService(self._client),
        )
        return await matching.find_matching_deals(extraction, limit=limit, pipeline_id=pipeline_id)

    async def resolve_contact_anchor(
        self,
        extraction: MemoExtraction,
        limit_deals: int = 5,
        pipeline_id: Optional[str] = None,
        preferred_contact_id: Optional[str] = None,
    ):
        matching = HubSpotMatchingService(
            self._client,
            self._search_service(),
            HubSpotAssociationService(self._client),
        )
        return await matching.resolve_contact_anchor(
            extraction,
            limit_deals=limit_deals,
            pipeline_id=pipeline_id,
            preferred_contact_id=preferred_contact_id,
        )

    async def resolve_identity(
        self,
        extraction: MemoExtraction,
        limit_deals: int = 5,
        pipeline_id: Optional[str] = None,
        preferred_contact_id: Optional[str] = None,
    ):
        matching = HubSpotMatchingService(
            self._client,
            self._search_service(),
            HubSpotAssociationService(self._client),
        )
        return await matching.resolve_identity(
            extraction,
            limit_deals=limit_deals,
            pipeline_id=pipeline_id,
            preferred_contact_id=preferred_contact_id,
        )

    async def get_call_outcome_availability(
        self,
        lost_lead_status_value: Optional[str] = None,
        on_hold_lead_status_value: Optional[str] = None,
    ) -> CallOutcomeAvailability:
        return await compute_call_outcome_availability(
            schema_service=self._schema_service(),
            lost_lead_status_value=lost_lead_status_value,
            on_hold_lead_status_value=on_hold_lead_status_value,
        )

    async def get_curated_field_specs(self, allowed_fields: list[str]) -> list[dict[str, Any]]:
        return await self._schema_service().get_curated_field_specs("deals", allowed_fields)

    async def get_extraction_field_specs(
        self,
        allowed_deal_fields: Optional[list[str]] = None,
        allowed_contact_fields: Optional[list[str]] = None,
        allowed_company_fields: Optional[list[str]] = None,
        allowed_line_item_fields: Optional[list[str]] = None,
    ) -> list[dict[str, Any]]:
        return await self._schema_service().get_multi_object_field_specs(
            allowed_deal_fields=allowed_deal_fields,
            allowed_contact_fields=allowed_contact_fields,
            allowed_company_fields=allowed_company_fields,
            allowed_line_item_fields=allowed_line_item_fields,
        )
