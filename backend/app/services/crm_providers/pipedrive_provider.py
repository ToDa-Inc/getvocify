"""Pipedrive adapter implementing CRM protocols."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional, Union
from uuid import UUID

from supabase import Client

from app.models.approval import ApprovalPreview, CallOutcomeAvailability, DealMatch
from app.models.memo import MemoExtraction
from app.services.crm_updates import CRMUpdatesService
from app.services.hubspot.types import SyncResult
from app.services.pipedrive.client import PipedriveClient
from app.services.pipedrive.identity import PipedriveIdentityService
from app.services.pipedrive.matching import PipedriveMatchingService
from app.services.pipedrive.preview import PipedrivePreviewService
from app.services.pipedrive.schema import PipedriveSchemaService
from app.services.pipedrive.search import PipedriveSearchService
from app.services.pipedrive.sync import PipedriveSyncService
from app.services.crm_providers.coverage import read_contact_emails


async def read_emails(fetch_ids, fetch_one, *, connection_id: str, observed_at: str) -> dict:
    return await read_contact_emails(
        fetch_ids,
        fetch_one,
        connection_id=connection_id,
        observed_at=observed_at,
    )


def _parse_expires_at(raw: Any) -> Optional[datetime]:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except Exception:
        return None


class PipedriveCRMProvider:
    def __init__(self, supabase: Client, connection: dict[str, Any]) -> None:
        self._supabase = supabase
        self._connection = connection
        meta = connection.get("metadata") or {}
        api_domain = meta.get("api_domain") or ""
        if not api_domain:
            raise ValueError("Pipedrive connection missing api_domain in metadata")
        self._connection_id = str(connection["id"])
        self._client = PipedriveClient(
            api_domain=api_domain,
            access_token=connection["access_token"],
            refresh_token=connection.get("refresh_token"),
            connection_id=self._connection_id,
            supabase=supabase,
            token_expires_at=_parse_expires_at(connection.get("token_expires_at")),
        )

    def _search(self) -> PipedriveSearchService:
        return PipedriveSearchService(self._client)

    def _schema(self) -> PipedriveSchemaService:
        return PipedriveSchemaService(self._client, self._supabase, self._connection_id)

    def _identity(self) -> PipedriveIdentityService:
        return PipedriveIdentityService(self._search())

    def _sync_service(self) -> PipedriveSyncService:
        return PipedriveSyncService(self._client, self._supabase, CRMUpdatesService(self._supabase))

    def _preview_service(self) -> PipedrivePreviewService:
        return PipedrivePreviewService(self._search(), self._schema())

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
        stage_confirm: bool = False,
        commitment_tasks: Optional[list] = None,
    ) -> SyncResult:
        del allowed_contact_fields, allowed_company_fields, allowed_line_item_fields
        del lost_reason, lost_reason_deal_property, lost_lead_status_value, on_hold_lead_status_value
        if call_outcome:
            return SyncResult(
                memo_id=str(memo_id),
                success=False,
                error="Call outcome (Converted/On Hold/Lost) isn't supported for Pipedrive yet.",
                error_code="CALL_OUTCOME_UNSUPPORTED",
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
            default_pipeline_id=default_pipeline_id,
            default_stage_id=default_stage_id,
            create_note=create_note,
            contact_id=contact_id,
            company_id=company_id,
            skip_deal=skip_deal,
            stage_confirm=stage_confirm,
            commitment_tasks=commitment_tasks,
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
        include_unchanged: bool = False,
        skip_deal: bool = False,
        stage_confirm: bool = False,
        meeting_booked_stage: Optional[dict[str, str]] = None,
        commitment_tasks: Optional[list] = None,
    ) -> ApprovalPreview:
        del create_new_deal, include_unchanged
        return await self._preview_service().build_preview(
            memo_id=memo_id,
            transcript=transcript,
            extraction=extraction,
            matched_deals=matched_deals,
            selected_deal_id=selected_deal_id,
            allowed_fields=allowed_fields,
            allowed_contact_fields=allowed_contact_fields,
            allowed_company_fields=allowed_company_fields,
            allowed_line_item_fields=allowed_line_item_fields,
            default_stage_name=default_stage_name,
            default_pipeline_id=default_pipeline_id,
            default_stage_id=default_stage_id,
            selected_contact=selected_contact,
            contact_candidates=contact_candidates,
            skip_deal=skip_deal,
            stage_confirm=stage_confirm,
            meeting_booked_stage=meeting_booked_stage,
            commitment_tasks=commitment_tasks,
        )

    async def find_matching_deals(
        self,
        extraction: MemoExtraction,
        limit: int = 3,
        pipeline_id: Optional[str] = None,
    ) -> list[DealMatch]:
        return await PipedriveMatchingService(self._search()).find_matching_deals(
            extraction, limit=limit, pipeline_id=pipeline_id
        )

    async def resolve_contact_anchor(
        self,
        extraction: MemoExtraction,
        limit_deals: int = 5,
        pipeline_id: Optional[str] = None,
        preferred_contact_id: Optional[str] = None,
    ):
        return await self._identity().resolve_contact_anchor(
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
        return await self._identity().resolve_identity(
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
        del lost_lead_status_value, on_hold_lead_status_value
        return CallOutcomeAvailability(converted=False, on_hold=False, lost=False)

    async def get_curated_field_specs(self, allowed_fields: list[str]) -> list[dict[str, Any]]:
        return await self._schema().get_curated_field_specs(allowed_fields)

    async def get_extraction_field_specs(
        self,
        allowed_deal_fields: Optional[list[str]] = None,
        allowed_contact_fields: Optional[list[str]] = None,
        allowed_company_fields: Optional[list[str]] = None,
        allowed_line_item_fields: Optional[list[str]] = None,
    ) -> list[dict[str, Any]]:
        del allowed_line_item_fields
        specs: list[dict[str, Any]] = []
        if allowed_deal_fields:
            specs.extend(await self._schema().get_curated_field_specs(allowed_deal_fields, "deals"))
        if allowed_contact_fields:
            specs.extend(await self._schema().get_curated_field_specs(allowed_contact_fields, "contacts"))
        if allowed_company_fields:
            specs.extend(await self._schema().get_curated_field_specs(allowed_company_fields, "companies"))
        return specs
