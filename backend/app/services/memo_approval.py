"""
Core memo approval and CRM sync logic.
Shared by HTTP API and WhatsApp processor.
"""

import logging
from datetime import datetime
from typing import Optional, Union

from supabase import Client

from app.logging_config import log_domain, DOMAIN_MEMO
from app.models.memo import Memo, MemoExtraction, ApproveMemoRequest

logger = logging.getLogger(__name__)
from app.services.crm_config import CRMConfigurationService
from app.services.crm_updates import CRMUpdatesService
from app.services.hubspot import (
    HubSpotClient,
    HubSpotSchemaService,
    HubSpotSearchService,
    HubSpotDealService,
    HubSpotMatchingService,
    HubSpotContactService,
    HubSpotCompanyService,
    HubSpotAssociationService,
    HubSpotTasksService,
    HubSpotSyncService,
    SyncResult,
)


async def approve_memo_core(
    supabase: Client,
    memo_id: str,
    user_id: str,
    payload: Optional[ApproveMemoRequest] = None,
) -> Union[Memo, SyncResult]:
    """
    Approve memo and sync to CRM (if connected).
    Idempotent: returns existing result if already approved with same extraction.
    """
    memo_result = (
        supabase.table("memos")
        .select("*")
        .eq("id", memo_id)
        .eq("user_id", user_id)
        .single()
        .execute()
    )
    if not memo_result.data:
        raise ValueError("Memo not found")

    memo_data = memo_result.data
    extraction_data = (
        payload.extraction.model_dump() if payload and payload.extraction
        else memo_data.get("extraction")
    )
    if not extraction_data:
        raise ValueError("No extraction data available")

    logger.info(
        "📋 Approve memo core started",
        extra=log_domain(DOMAIN_MEMO, "approve_core", memo_id=memo_id),
    )
    if memo_data.get("status") == "approved" and memo_data.get("approved_at"):
        if not (payload and payload.extraction):
            updated = supabase.table("memos").select("*").eq("id", memo_id).single().execute()
            m = updated.data
            return Memo(
                id=m["id"],
                userId=m["user_id"],
                audioUrl=m.get("audio_url") or "",
                audioDuration=m["audio_duration"],
                status=m["status"],
                transcript=m.get("transcript"),
                transcriptConfidence=m.get("transcript_confidence"),
                extraction=m.get("extraction"),
                errorMessage=m.get("error_message"),
                createdAt=m["created_at"],
                processedAt=m.get("processed_at"),
                approvedAt=m.get("approved_at"),
            )

    crm_result = (
        supabase.table("crm_connections")
        .select("*")
        .eq("user_id", user_id)
        .eq("status", "connected")
        .limit(1)
        .execute()
    )

    if not crm_result.data:
        supabase.table("memos").update({
            "status": "approved",
            "approved_at": datetime.utcnow().isoformat(),
            "extraction": extraction_data,
        }).eq("id", memo_id).execute()
        updated = supabase.table("memos").select("*").eq("id", memo_id).single().execute()
        m = updated.data
        return Memo(
            id=m["id"],
            userId=m["user_id"],
            audioUrl=m.get("audio_url") or "",
            audioDuration=m["audio_duration"],
            status=m["status"],
            transcript=m.get("transcript"),
            transcriptConfidence=m.get("transcript_confidence"),
            extraction=m.get("extraction"),
            errorMessage=m.get("error_message"),
            createdAt=m["created_at"],
            processedAt=m.get("processed_at"),
            approvedAt=m.get("approved_at"),
        )

    crm_connection = crm_result.data[0]
    config_service = CRMConfigurationService(supabase)
    config = await config_service.get_configuration(user_id)
    allowed_fields = (
        config.allowed_deal_fields if config
        else ["dealname", "amount", "description", "closedate"]
    )

    client = HubSpotClient(crm_connection["access_token"])
    schema_service = HubSpotSchemaService(client, supabase, crm_connection["id"])
    search_service = HubSpotSearchService(client)
    deal_service = HubSpotDealService(client, search_service, schema_service)
    association_service = HubSpotAssociationService(client)
    crm_updates_service = CRMUpdatesService(supabase)

    sync_service = HubSpotSyncService(
        client=client,
        contacts=HubSpotContactService(client, search_service),
        companies=HubSpotCompanyService(client, search_service),
        deals=deal_service,
        associations=association_service,
        tasks=HubSpotTasksService(client),
        crm_updates=crm_updates_service,
        supabase=supabase,
    )

    extraction = MemoExtraction(**extraction_data)
    deal_id = None
    is_new_deal = False
    if payload:
        if payload.is_new_deal:
            is_new_deal = True
        else:
            deal_id = payload.deal_id or memo_data.get("matched_deal_id")
            is_new_deal = False
    else:
        deal_id = memo_data.get("matched_deal_id")
        is_new_deal = bool(memo_data.get("is_new_deal", False) if not deal_id else False)

    sync_result = await sync_service.sync_memo(
        memo_id=memo_id,
        user_id=user_id,
        connection_id=crm_connection["id"],
        extraction=extraction,
        deal_id=deal_id,
        is_new_deal=is_new_deal,
        allowed_fields=allowed_fields,
        transcript=memo_data.get("transcript"),
    )

    if not sync_result.success:
        logger.error(
            "❌ Approve memo core sync failed",
            extra=log_domain(DOMAIN_MEMO, "approve_core_failed", memo_id=memo_id, error=sync_result.error or "unknown"),
        )
        raise ValueError(sync_result.error or "Failed to sync to CRM")

    logger.info(
        "✅ Approve memo core complete",
        extra=log_domain(DOMAIN_MEMO, "approve_core_complete", memo_id=memo_id, deal_id=sync_result.deal_id),
    )
    supabase.table("memos").update({
        "status": "approved",
        "approved_at": datetime.utcnow().isoformat(),
        "extraction": extraction_data,
    }).eq("id", memo_id).execute()

    return sync_result
