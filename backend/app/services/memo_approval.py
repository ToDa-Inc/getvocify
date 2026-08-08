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
from app.services.crm_config import CRMConfigurationService
from app.services.crm_providers import (
    AmbiguousPrimaryCRMError,
    UnsupportedCRMProviderError,
    build_crm_provider,
    resolve_sync_connection,
)
from app.services.hubspot.token_refresh import ensure_hubspot_connection_tokens_fresh
from app.services.hubspot.deal_field_names import normalize_hubspot_allowed_deal_fields
from app.services.hubspot.types import SyncResult

logger = logging.getLogger(__name__)


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

    try:
        crm_connection = resolve_sync_connection(supabase, user_id)
    except AmbiguousPrimaryCRMError as e:
        raise ValueError(e.message) from e

    if not crm_connection:
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

    if crm_connection.get("provider") == "hubspot":
        try:
            crm_connection = await ensure_hubspot_connection_tokens_fresh(supabase, crm_connection)
        except ValueError as e:
            raise ValueError(str(e)) from e

    extraction = MemoExtraction(**extraction_data)
    deal_id: Optional[str] = None
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

    config_service = CRMConfigurationService(supabase)
    config = await config_service.get_configuration(
        user_id, connection_id=str(crm_connection["id"])
    )
    allowed_fields = (
        config.allowed_deal_fields if config
        else ["dealname", "amount", "description", "closedate"]
    )
    if crm_connection.get("provider") == "salesforce":
        allowed_fields = (
            config.allowed_deal_fields if config
            else ["Name", "Amount", "CloseDate", "StageName", "Description"]
        )
    elif crm_connection.get("provider") == "hubspot":
        # Config or DB may still list Salesforce-style names; HubSpot API requires lowercase keys.
        allowed_fields = normalize_hubspot_allowed_deal_fields(allowed_fields)

    if config is not None:
        auto_create_companies = config.auto_create_companies
        auto_create_contacts = config.auto_create_contacts
        auto_create_contact_company = False
    else:
        profile_result = (
            supabase.table("user_profiles")
            .select("auto_create_contact_company")
            .eq("id", user_id)
            .single()
            .execute()
        )
        profile = profile_result.data or {}
        auto_create_contact_company = bool(profile.get("auto_create_contact_company", False))
        auto_create_companies = None
        auto_create_contacts = None

    if deal_id and not is_new_deal:
        auto_create_contact_company = False
        auto_create_companies = False
        auto_create_contacts = False

    try:
        provider = build_crm_provider(supabase, crm_connection)
    except UnsupportedCRMProviderError as e:
        raise ValueError(str(e)) from e

    default_stage = config.default_stage_name if config else None
    default_pipeline_id = (config.default_pipeline_id or None) if config else None
    default_stage_id = (config.default_stage_id or None) if config else None

    sync_result = await provider.sync_memo(
        memo_id=memo_id,
        user_id=user_id,
        connection_id=crm_connection["id"],
        extraction=extraction,
        deal_id=deal_id,
        is_new_deal=is_new_deal,
        allowed_fields=allowed_fields,
        transcript=memo_data.get("transcript"),
        auto_create_contact_company=auto_create_contact_company,
        auto_create_companies=auto_create_companies,
        auto_create_contacts=auto_create_contacts,
        default_stage_name=default_stage,
        default_pipeline_id=default_pipeline_id,
        default_stage_id=default_stage_id,
    )

    if not sync_result.success:
        logger.error(
            "❌ Approve memo core sync failed",
            extra=log_domain(
                DOMAIN_MEMO, "approve_core_failed", memo_id=memo_id, error=sync_result.error or "unknown"
            ),
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
