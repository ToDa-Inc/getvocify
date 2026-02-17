"""
Voice memo API endpoints
"""

import asyncio
from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from uuid import UUID
from typing import Optional, List, Union
from app.deps import get_supabase, get_user_id
from app.services.storage import StorageService
from app.services.transcription import TranscriptionService
from app.services.extraction import ExtractionService
from app.services.glossary import GlossaryService
from app.services.crm_updates import CRMUpdatesService
from app.services.crm_config import CRMConfigurationService
from app.services.hubspot import (
    HubSpotClient,
    HubSpotSchemaService,
    HubSpotSearchService,
    HubSpotDealService,
    HubSpotMatchingService,
    HubSpotPreviewService,
    HubSpotContactService,
    HubSpotCompanyService,
    HubSpotAssociationService,
    HubSpotSyncService,
    SyncResult,
)
from app.models.memo import Memo, MemoCreate, MemoUpdate, UploadResponse, MemoExtraction, ApproveMemoRequest
from app.models.crm_update import CRMUpdate
from app.models.approval import ApprovalPreview, DealMatch
from supabase import Client
from typing import Optional, List
from datetime import datetime


router = APIRouter(prefix="/api/v1/memos", tags=["memos"])


async def extract_memo_async(
    memo_id: str,
    user_id: str,
    transcript: str,
    supabase: Client,
    extraction_service: ExtractionService,
    field_specs: Optional[list[dict]] = None
):
    """
    Background task to extract structured data from pre-transcribed memo
    """
    from datetime import datetime
    
    try:
        # Mark processing started
        supabase.table("memos").update({
            "status": "extracting",
            "processing_started_at": datetime.utcnow().isoformat(),
        }).eq("id", memo_id).execute()
        
        # Fetch user glossary for LLM correction
        glossary_service = GlossaryService(supabase)
        glossary = await glossary_service.get_user_glossary(user_id)
        glossary_text = glossary_service.format_for_llm(glossary)

        # Extract structured data
        extraction = await extraction_service.extract(
            transcript, 
            field_specs, 
            glossary_text=glossary_text
        )
        
        # Update with extraction and mark as pending_review
        supabase.table("memos").update({
            "status": "pending_review",
            "extraction": extraction.model_dump(),
            "processed_at": datetime.utcnow().isoformat(),
            "processing_started_at": None,  # Clear on success
        }).eq("id", memo_id).execute()
        
    except Exception as e:
        # Update status to failed and clear processing_started_at
        supabase.table("memos").update({
            "status": "failed",
            "error_message": str(e),
            "processing_started_at": None,
        }).eq("id", memo_id).execute()


async def process_memo_async(
    memo_id: str,
    user_id: str,
    audio_url: str,
    supabase: Client,
    transcription_service: TranscriptionService,
    extraction_service: ExtractionService,
    field_specs: Optional[list[dict]] = None
):
    """
    Background task to process memo: transcribe → extract → update status
    """
    from datetime import datetime
    
    try:
        # Mark processing started
        supabase.table("memos").update({
            "status": "transcribing",
            "processing_started_at": datetime.utcnow().isoformat(),
        }).eq("id", memo_id).execute()
        
        # Fetch user glossary for LLM correction
        glossary_service = GlossaryService(supabase)
        glossary = await glossary_service.get_user_glossary(user_id)
        glossary_text = glossary_service.format_for_llm(glossary)

        # Download audio from storage
        # ... parts ...
        parts = audio_url.split("/public/voice-memos/")
        if len(parts) < 2:
            raise Exception("Invalid audio URL")
        
        path = parts[1]
        audio_response = supabase.storage.from_("voice-memos").download(path)
        
        if not audio_response:
            raise Exception("Failed to download audio")
        
        # audio_response is bytes
        audio_bytes = audio_response
        
        # Transcribe
        transcription = await transcription_service.transcribe(audio_bytes)
        
        # Update with transcript
        supabase.table("memos").update({
            "status": "extracting",
            "transcript": transcription.transcript,
            "transcript_confidence": transcription.confidence,
        }).eq("id", memo_id).execute()
        
        # Extract structured data
        extraction = await extraction_service.extract(transcription.transcript, field_specs, glossary_text=glossary_text)
        
        # Update with extraction and mark as pending_review
        supabase.table("memos").update({
            "status": "pending_review",
            "extraction": extraction.model_dump(),
            "processed_at": datetime.utcnow().isoformat(),
            "processing_started_at": None,  # Clear on success
        }).eq("id", memo_id).execute()
        
    except Exception as e:
        # Update status to failed and clear processing_started_at
        supabase.table("memos").update({
            "status": "failed",
            "error_message": str(e),
            "processing_started_at": None,
        }).eq("id", memo_id).execute()


@router.post("/upload", response_model=UploadResponse)
async def upload_memo(
    audio: UploadFile = File(...),
    transcript: Optional[str] = Form(None),
    supabase: Client = Depends(get_supabase),
    user_id: str = Depends(get_user_id),
):
    """
    Upload audio file and start processing pipeline
    
    Flow:
    1. Store audio in Supabase Storage
    2. Create memo record with status 'uploading' or 'extracting' (if transcript provided)
    3. Start background processing:
       - If transcript provided: Skip Deepgram, go directly to extraction
       - If no transcript: Transcribe → Extract
    4. Return memo ID for polling
    
    Args:
        audio: Audio file to upload
        transcript: Optional pre-transcribed text (from real-time WebSocket)
    """
    # Validate file type
    if not audio.content_type or not audio.content_type.startswith("audio/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be an audio file"
        )
    
    # Read audio bytes
    audio_bytes = await audio.read()
    
    # Validate file size (10MB max)
    max_size = 10 * 1024 * 1024
    if len(audio_bytes) > max_size:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File too large. Maximum size is {max_size / 1024 / 1024}MB"
        )
    
    # Upload to storage
    storage_service = StorageService(supabase)
    audio_url = await storage_service.upload_audio(
        audio_bytes,
        user_id,
        audio.content_type
    )
    
    # Get audio duration (rough estimate: 1MB ≈ 1 minute for webm)
    # In production, use ffprobe or similar
    estimated_duration = len(audio_bytes) / (1024 * 1024) * 60  # rough estimate
    
    # Get user's CRM configuration to know which fields to extract
    config_service = CRMConfigurationService(supabase)
    config = await config_service.get_configuration(user_id)
    allowed_fields = config.allowed_deal_fields if config else None
    
    # Get curated field specs for high-accuracy extraction
    field_specs = None
    if allowed_fields:
        try:
            client, connection_id = get_hubspot_client_from_connection(user_id, supabase)
            schema_service = HubSpotSchemaService(client, supabase, connection_id)
            field_specs = await schema_service.get_curated_field_specs("deals", allowed_fields)
        except Exception:
            # Fallback to None if connection fails
            field_specs = None

    # If transcript is provided, skip transcription step
    if transcript and transcript.strip():
        # Create memo record in database
        result = supabase.table("memos").insert({
            "user_id": user_id,
            "audio_url": audio_url,
            "audio_duration": estimated_duration,
            "status": "extracting",
            "transcript": transcript.strip(),
            "transcript_confidence": 1.0, # High confidence for pre-transcribed text
        }).execute()
        
        memo_id = result.data[0]["id"]
        
        # Start extraction directly (skip transcription)
        extraction_service = ExtractionService()
        asyncio.create_task(
            extract_memo_async(memo_id, user_id, transcript.strip(), supabase, extraction_service, field_specs)
        )
        
        return UploadResponse(
            id=str(memo_id),
            status="extracting",
            statusUrl=f"/api/v1/memos/{memo_id}"
        )
    else:
        # No transcript provided - use normal flow
        # Create memo record in database
        result = supabase.table("memos").insert({
            "user_id": user_id,
            "audio_url": audio_url,
            "audio_duration": estimated_duration,
            "status": "uploading",
        }).execute()
        
        memo_id = result.data[0]["id"]
        
        # Start background processing (transcribe → extract)
        transcription_service = TranscriptionService()
        extraction_service = ExtractionService()
        
        asyncio.create_task(
            process_memo_async(
                memo_id,
                user_id,
                audio_url,
                supabase,
                transcription_service,
                extraction_service,
                field_specs
            )
        )
        
        return UploadResponse(
            id=str(memo_id),
            status="uploading",
            statusUrl=f"/api/v1/memos/{memo_id}"
        )


@router.get("/{memo_id}", response_model=Memo)
async def get_memo(
    memo_id: UUID,
    supabase: Client = Depends(get_supabase),
    user_id: str = Depends(get_user_id),
):
    """Get a single memo by ID"""
    result = supabase.table("memos").select("*").eq("id", str(memo_id)).eq("user_id", user_id).execute()
    
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Memo not found"
        )
    
    memo_data = result.data[0]
    
    # Convert to Memo model
    return Memo(
        id=memo_data["id"],
        userId=memo_data["user_id"],
        audioUrl=memo_data.get("audio_url") or "",
        audioDuration=memo_data["audio_duration"],
        status=memo_data["status"],
        transcript=memo_data.get("transcript"),
        transcriptConfidence=memo_data.get("transcript_confidence"),
        extraction=memo_data.get("extraction"),
        errorMessage=memo_data.get("error_message"),
        createdAt=memo_data["created_at"],
        processedAt=memo_data.get("processed_at"),
        approvedAt=memo_data.get("approved_at"),
    )


@router.get("", response_model=list[Memo])
async def list_memos(
    supabase: Client = Depends(get_supabase),
    user_id: str = Depends(get_user_id),
    limit: int = 20,
    offset: int = 0,
):
    """List user's memos"""
    result = supabase.table("memos").select("*").eq("user_id", user_id).order("created_at", desc=True).limit(limit).offset(offset).execute()
    
    memos = []
    for memo_data in result.data:
        memos.append(Memo(
            id=memo_data["id"],
            userId=memo_data["user_id"],
            audioUrl=memo_data.get("audio_url") or "",
            audioDuration=memo_data["audio_duration"],
            status=memo_data["status"],
            transcript=memo_data.get("transcript"),
            transcriptConfidence=memo_data.get("transcript_confidence"),
            extraction=memo_data.get("extraction"),
            errorMessage=memo_data.get("error_message"),
            createdAt=memo_data["created_at"],
            processedAt=memo_data.get("processed_at"),
            approvedAt=memo_data.get("approved_at"),
        ))
    
    return memos


@router.post("/{memo_id}/approve", response_model=Union[Memo, SyncResult])
async def approve_memo(
    memo_id: UUID,
    payload: Optional[ApproveMemoRequest] = None,
    supabase: Client = Depends(get_supabase),
    user_id: str = Depends(get_user_id),
):
    """
    Approve a memo and push to CRM
    
    If extraction is provided in payload, it will be used instead of the stored extraction.
    This allows users to edit the extraction before approving.
    
    Idempotency: If memo is already approved and extraction hasn't changed, returns existing result.
    
    When HubSpot integration is implemented, this will:
    1. Get user's CRM connection
    2. Map extraction to CRM fields
    3. Push to CRM (create/update deal, contact, etc.)
    4. Create CRM update records for audit trail
    """
    # Get memo
    memo_result = supabase.table("memos").select("*").eq("id", str(memo_id)).eq("user_id", user_id).single().execute()
    
    if not memo_result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Memo not found"
        )
    
    memo_data = memo_result.data
    
    # Use provided extraction (if edited) or stored extraction
    if payload and payload.extraction:
        extraction_data = payload.extraction.model_dump()
    else:
        extraction_data = memo_data.get("extraction")
    
    if not extraction_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No extraction data available. Please wait for processing to complete."
        )
    
    # Idempotency check: If already approved and extraction hasn't changed, return existing
    if memo_data.get("status") == "approved" and memo_data.get("approved_at"):
        # Check if extraction was edited (re-approval with changes)
        if payload and payload.extraction:
            # Extraction was edited, allow re-approval
            pass
        else:
            # Same extraction, already approved - return existing memo (idempotent)
            return Memo(
                id=memo_data["id"],
                userId=memo_data["user_id"],
                audioUrl=memo_data.get("audio_url") or "",
                audioDuration=memo_data["audio_duration"],
                status=memo_data["status"],
                transcript=memo_data.get("transcript"),
                transcriptConfidence=memo_data.get("transcript_confidence"),
                extraction=memo_data.get("extraction"),
                errorMessage=memo_data.get("error_message"),
                createdAt=memo_data["created_at"],
                processedAt=memo_data.get("processed_at"),
                approvedAt=memo_data.get("approved_at"),
            )
    
    # Get user's CRM connection
    crm_result = supabase.table("crm_connections").select("*").eq(
        "user_id", user_id
    ).eq("status", "connected").limit(1).execute()
    
    if not crm_result.data:
        # No CRM connected - just mark as approved without pushing
        supabase.table("memos").update({
            "status": "approved",
            "approved_at": datetime.utcnow().isoformat(),
            "extraction": extraction_data,
        }).eq("id", str(memo_id)).execute()
    else:
        # CRM connected - sync to HubSpot
        crm_connection = crm_result.data[0]
        
        if crm_connection["provider"] == "hubspot":
            # Get configuration
            config_service = CRMConfigurationService(supabase)
            config = await config_service.get_configuration(user_id)
            allowed_fields = config.allowed_deal_fields if config else ["dealname", "amount", "description", "closedate"]
            
            # Initialize HubSpot services
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
                crm_updates=crm_updates_service,
                supabase=supabase,
            )
            
            # Parse extraction
            extraction = MemoExtraction(**extraction_data)
            
            # Determine deal_id and is_new_deal
            # Priority: 1. Payload, 2. Database
            deal_id = None
            is_new_deal = False
            
            if payload:
                if payload.is_new_deal:
                    is_new_deal = True
                    deal_id = None
                else:
                    deal_id = payload.deal_id or memo_data.get("matched_deal_id")
                    is_new_deal = False
            else:
                deal_id = memo_data.get("matched_deal_id")
                is_new_deal = memo_data.get("is_new_deal", False) if not deal_id else False
            
            # Sync to HubSpot
            sync_result = await sync_service.sync_memo(
                memo_id=str(memo_id),
                user_id=user_id,
                connection_id=crm_connection["id"],
                extraction=extraction,
                deal_id=deal_id,
                is_new_deal=is_new_deal,
                allowed_fields=allowed_fields,
            )
            
            if not sync_result.success:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=sync_result.error or "Failed to sync to CRM",
                )
            
            # Mark memo as approved
            supabase.table("memos").update({
                "status": "approved",
                "approved_at": datetime.utcnow().isoformat(),
                "extraction": extraction_data,
            }).eq("id", str(memo_id)).execute()
            
            return sync_result
        
        # Mark memo as approved for non-HubSpot (not implemented)
        supabase.table("memos").update({
            "status": "approved",
            "approved_at": datetime.utcnow().isoformat(),
            "extraction": extraction_data,
        }).eq("id", str(memo_id)).execute()
    
    # Return updated memo for non-HubSpot cases
    updated_result = supabase.table("memos").select("*").eq("id", str(memo_id)).single().execute()
    updated_memo = updated_result.data
    
    return Memo(
        id=updated_memo["id"],
        userId=updated_memo["user_id"],
        audioUrl=updated_memo["audio_url"],
        audioDuration=updated_memo["audio_duration"],
        status=updated_memo["status"],
        transcript=updated_memo.get("transcript"),
        transcriptConfidence=updated_memo.get("transcript_confidence"),
        extraction=updated_memo.get("extraction"),
        errorMessage=updated_memo.get("error_message"),
        createdAt=updated_memo["created_at"],
        processedAt=updated_memo.get("processed_at"),
        approvedAt=updated_memo.get("approved_at"),
    )


@router.get("/{memo_id}/crm-updates", response_model=List[CRMUpdate])
async def get_memo_crm_updates(
    memo_id: UUID,
    supabase: Client = Depends(get_supabase),
    user_id: str = Depends(get_user_id),
):
    """Get all CRM updates for a memo"""
    # Verify memo belongs to user
    memo_result = supabase.table("memos").select("id").eq("id", str(memo_id)).eq("user_id", user_id).execute()
    
    if not memo_result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Memo not found"
        )
    
    # Get CRM updates
    crm_updates_service = CRMUpdatesService(supabase)
    updates_data = await crm_updates_service.get_memo_updates(str(memo_id))
    
    updates = []
    for update_data in updates_data:
        updates.append(CRMUpdate(
            id=update_data["id"],
            memo_id=update_data["memo_id"],
            user_id=update_data["user_id"],
            crm_connection_id=update_data["crm_connection_id"],
            action_type=update_data["action_type"],
            resource_type=update_data["resource_type"],
            data=update_data["data"],
            status=update_data["status"],
            resource_id=update_data.get("resource_id"),
            response=update_data.get("response"),
            error_message=update_data.get("error_message"),
            retry_count=update_data.get("retry_count", 0),
            created_at=update_data["created_at"],
            completed_at=update_data.get("completed_at"),
        ))
    
    return updates


def get_hubspot_client_from_connection(
    user_id: str,
    supabase: Client,
) -> tuple[HubSpotClient, str]:
    """Get HubSpot client and connection ID from user's connection"""
    try:
        result = supabase.table("crm_connections").select("*").eq(
            "user_id", user_id
        ).eq("provider", "hubspot").eq("status", "connected").single().execute()
        
        if not result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="HubSpot connection not found",
            )
        
        connection = result.data
        return HubSpotClient(connection["access_token"]), connection["id"]
    except Exception as e:
        error_str = str(e)
        if "no rows" in error_str.lower() or "PGRST116" in error_str:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="HubSpot connection not found",
            )
        raise


@router.post("/{memo_id}/match", response_model=list[DealMatch])
async def match_memo_to_deals(
    memo_id: UUID,
    supabase: Client = Depends(get_supabase),
    user_id: str = Depends(get_user_id),
):
    """
    Find matching HubSpot deals for a memo.
    
    Searches for existing deals based on company name, contact info,
    or deal name from the extraction.
    
    Returns top 3 matches with confidence scores.
    """
    # Get memo
    memo_result = supabase.table("memos").select("*").eq("id", str(memo_id)).eq("user_id", user_id).single().execute()
    
    if not memo_result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Memo not found",
        )
    
    memo_data = memo_result.data
    extraction_data = memo_data.get("extraction")
    
    if not extraction_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Memo extraction not available. Please wait for processing to complete.",
        )
    
    # Check if HubSpot is connected
    try:
        conn_result = supabase.table("crm_connections").select("*").eq(
            "user_id", user_id
        ).eq("provider", "hubspot").eq("status", "connected").single().execute()
        
        if not conn_result.data:
            return []  # No matches if not connected
            
        access_token = conn_result.data["access_token"]
    except Exception as e:
        error_str = str(e)
        if "no rows" in error_str.lower() or "PGRST116" in error_str:
            return []  # No matches if not connected
        raise
    
    # Get configuration for pipeline filter
    config_service = CRMConfigurationService(supabase)
    config = await config_service.get_configuration(user_id)
    pipeline_id = config.default_pipeline_id if config else None
    
    # Initialize services
    client = HubSpotClient(access_token)
    search_service = HubSpotSearchService(client)
    matching_service = HubSpotMatchingService(client, search_service)
    
    # Parse extraction
    extraction = MemoExtraction(**extraction_data)
    
    # Find matches
    matches = await matching_service.find_matching_deals(
        extraction,
        limit=3,
        pipeline_id=pipeline_id,
    )
    
    return matches


@router.get("/{memo_id}/preview", response_model=ApprovalPreview)
async def get_approval_preview(
    memo_id: UUID,
    deal_id: Optional[str] = None,
    supabase: Client = Depends(get_supabase),
    user_id: str = Depends(get_user_id),
):
    """
    Get approval preview showing what will be updated in CRM.
    
    Shows proposed field changes comparing extraction to current deal.
    If deal_id is None, shows preview for creating a new deal.
    
    Args:
        memo_id: Memo ID
        deal_id: Optional deal ID to update (None or empty = create new)
    """
    # Handle empty string from query param
    if deal_id == "":
        deal_id = None
        
    # Get memo
    memo_result = supabase.table("memos").select("*").eq("id", str(memo_id)).eq("user_id", user_id).single().execute()
    
    if not memo_result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Memo not found",
        )
    
    memo_data = memo_result.data
    extraction_data = memo_data.get("extraction")
    transcript = memo_data.get("transcript", "")
    
    if not extraction_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Memo extraction not available",
        )
    
    # Check if HubSpot is connected
    try:
        conn_result = supabase.table("crm_connections").select("*").eq(
            "user_id", user_id
        ).eq("provider", "hubspot").eq("status", "connected").single().execute()
        
        if not conn_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="HubSpot connection not found",
            )
        
        connection_id = conn_result.data["id"]
        access_token = conn_result.data["access_token"]
    except Exception as e:
        error_str = str(e)
        if "no rows" in error_str.lower() or "PGRST116" in error_str:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="HubSpot connection not found",
            )
        raise
    
    # Get configuration
    config_service = CRMConfigurationService(supabase)
    config = await config_service.get_configuration(user_id)
    allowed_fields = config.allowed_deal_fields if config else ["dealname", "amount", "description", "closedate"]
    
    # Initialize services
    client = HubSpotClient(access_token)
    schema_service = HubSpotSchemaService(client, supabase, connection_id)
    search_service = HubSpotSearchService(client)
    deal_service = HubSpotDealService(client, search_service, schema_service)
    preview_service = HubSpotPreviewService(client, deal_service, schema_service)
    
    # Get matches
    matching_service = HubSpotMatchingService(client, search_service)
    extraction = MemoExtraction(**extraction_data)
    pipeline_id = config.default_pipeline_id if config else None
    matches = await matching_service.find_matching_deals(extraction, limit=3, pipeline_id=pipeline_id)
    
    # Build preview
    preview = await preview_service.build_preview(
        memo_id=memo_id,
        transcript=transcript,
        extraction=extraction,
        matched_deals=matches,
        selected_deal_id=deal_id,
        allowed_fields=allowed_fields,
    )
    
    # If a deal was explicitly selected, persist it to the memo record
    if deal_id:
        supabase.table("memos").update({
            "matched_deal_id": deal_id,
            "matched_deal_name": preview.selected_deal.deal_name if preview.selected_deal else None,
            "is_new_deal": False
        }).eq("id", str(memo_id)).execute()
    elif deal_id == "": # Explicitly "Create New"
        supabase.table("memos").update({
            "matched_deal_id": None,
            "matched_deal_name": None,
            "is_new_deal": True
        }).eq("id", str(memo_id)).execute()
    
    return preview


@router.post("/{memo_id}/cleanup-orphans")
async def cleanup_orphans(
    memo_id: UUID,
    supabase: Client = Depends(get_supabase),
    user_id: str = Depends(get_user_id),
):
    """
    Clean up orphaned CRM records for a memo.
    
    Finds company/contact records created for this memo that don't have
    an associated deal (orphans) and optionally deletes them from HubSpot.
    
    This is useful when a sync fails partway through, leaving orphaned records.
    """
    # Verify memo belongs to user
    memo_result = supabase.table("memos").select("*").eq("id", str(memo_id)).eq("user_id", user_id).single().execute()
    
    if not memo_result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Memo not found",
        )
    
    memo_data = memo_result.data
    
    # Check if HubSpot is connected
    try:
        conn_result = supabase.table("crm_connections").select("*").eq(
            "user_id", user_id
        ).eq("provider", "hubspot").eq("status", "connected").single().execute()
        
        if not conn_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="HubSpot connection not found",
            )
        
        connection_id = conn_result.data["id"]
        access_token = conn_result.data["access_token"]
    except Exception as e:
        error_str = str(e)
        if "no rows" in error_str.lower() or "PGRST116" in error_str:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="HubSpot connection not found",
            )
        raise
    
    # Get CRM updates for this memo
    crm_updates_service = CRMUpdatesService(supabase)
    updates_data = await crm_updates_service.get_memo_updates(str(memo_id))
    
    # Find successful company/contact creations without successful deal creation
    company_id = None
    contact_id = None
    deal_created = False
    
    for update in updates_data:
        if update.get("status") == "success":
            action_type = update.get("action_type")
            data = update.get("data", {})
            
            if action_type == "upsert_company" and "company_id" in data:
                company_id = data["company_id"]
            elif action_type == "upsert_contact" and "contact_id" in data:
                contact_id = data["contact_id"]
            elif action_type in ["create_deal", "update_deal"]:
                deal_created = True
    
    # If deal was created, no orphans exist
    if deal_created:
        return {
            "message": "No orphans found - deal was successfully created",
            "orphans_cleaned": 0,
        }
    
    # Clean up orphans
    cleaned = []
    
    if company_id:
        try:
            client = HubSpotClient(access_token)
            await client.delete(f"/crm/v3/objects/companies/{company_id}")
            cleaned.append({"type": "company", "id": company_id})
        except Exception as e:
            # Log but don't fail
            pass
    
    if contact_id:
        try:
            client = HubSpotClient(access_token)
            await client.delete(f"/crm/v3/objects/contacts/{contact_id}")
            cleaned.append({"type": "contact", "id": contact_id})
        except Exception as e:
            # Log but don't fail
            pass
    
    return {
        "message": f"Cleaned up {len(cleaned)} orphaned records",
        "orphans_cleaned": len(cleaned),
        "cleaned": cleaned,
    }


@router.post("/{memo_id}/reject", response_model=Memo)
async def reject_memo(
    memo_id: UUID,
    supabase: Client = Depends(get_supabase),
    user_id: str = Depends(get_user_id),
):
    """
    Reject a memo.
    
    Marks the memo as rejected. No CRM update happens.
    This is a final state - rejected memos cannot be approved later.
    """
    # Get memo
    memo_result = supabase.table("memos").select("*").eq("id", str(memo_id)).eq("user_id", user_id).single().execute()
    
    if not memo_result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Memo not found",
        )
    
    memo_data = memo_result.data
    
    # Check if already rejected
    if memo_data.get("status") == "rejected":
        # Already rejected, return existing (idempotent)
        return Memo(
            id=memo_data["id"],
            userId=memo_data["user_id"],
            audioUrl=memo_data.get("audio_url") or "",
            audioDuration=memo_data["audio_duration"],
            status=memo_data["status"],
            transcript=memo_data.get("transcript"),
            transcriptConfidence=memo_data.get("transcript_confidence"),
            extraction=memo_data.get("extraction"),
            errorMessage=memo_data.get("error_message"),
            createdAt=memo_data["created_at"],
            processedAt=memo_data.get("processed_at"),
            approvedAt=memo_data.get("approved_at"),
        )
    
    # Check if already approved (cannot reject approved memos)
    if memo_data.get("status") == "approved":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot reject an already approved memo",
        )
    
    # Update status to rejected
    from datetime import datetime
    supabase.table("memos").update({
        "status": "rejected",
    }).eq("id", str(memo_id)).execute()
    
    # Return updated memo
    updated_result = supabase.table("memos").select("*").eq("id", str(memo_id)).single().execute()
    updated_memo = updated_result.data
    
    return Memo(
        id=updated_memo["id"],
        userId=updated_memo["user_id"],
        audioUrl=updated_memo["audio_url"],
        audioDuration=updated_memo["audio_duration"],
        status=updated_memo["status"],
        transcript=updated_memo.get("transcript"),
        transcriptConfidence=updated_memo.get("transcript_confidence"),
        extraction=updated_memo.get("extraction"),
        errorMessage=updated_memo.get("error_message"),
        createdAt=updated_memo["created_at"],
        processedAt=updated_memo.get("processed_at"),
        approvedAt=updated_memo.get("approved_at"),
    )


@router.delete("/{memo_id}")
async def delete_memo(
    memo_id: UUID,
    supabase: Client = Depends(get_supabase),
    user_id: str = Depends(get_user_id),
):
    """
    Delete a memo and its audio file.
    
    Permanently removes the memo record and associated audio file from storage.
    CRM updates are preserved for audit trail.
    """
    # Get memo
    memo_result = supabase.table("memos").select("*").eq("id", str(memo_id)).eq("user_id", user_id).single().execute()
    
    if not memo_result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Memo not found",
        )
    
    memo_data = memo_result.data
    audio_url = memo_data.get("audio_url")
    
    # Delete audio file from storage
    if audio_url:
        try:
            from app.services.storage import StorageService
            storage_service = StorageService(supabase)
            await storage_service.delete_audio(audio_url)
        except Exception as e:
            # Log error but continue with memo deletion
            print(f"Failed to delete audio file: {e}")
    
    # Delete memo record
    supabase.table("memos").delete().eq("id", str(memo_id)).execute()
    
    return {"success": True, "message": "Memo deleted"}


@router.post("/{memo_id}/re-extract", response_model=Memo)
async def re_extract_memo(
    memo_id: UUID,
    supabase: Client = Depends(get_supabase),
    user_id: str = Depends(get_user_id),
):
    """
    Re-extract structured data from a memo's transcript.
    
    Re-runs the GPT-5-mini extraction on the existing transcript.
    Useful when the initial extraction was incorrect or incomplete.
    
    Requires:
    - Memo must have a transcript
    - Memo must not be approved (to prevent overwriting approved data)
    """
    # Get memo
    memo_result = supabase.table("memos").select("*").eq("id", str(memo_id)).eq("user_id", user_id).single().execute()
    
    if not memo_result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Memo not found",
        )
    
    memo_data = memo_result.data
    transcript = memo_data.get("transcript")
    
    if not transcript:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Memo does not have a transcript. Cannot re-extract.",
        )
    
    # Check if already approved (prevent overwriting approved data)
    if memo_data.get("status") == "approved":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot re-extract an approved memo. Please reject it first if you need to change the extraction.",
        )
    
    # Get user's CRM configuration for field specs
    config_service = CRMConfigurationService(supabase)
    config = await config_service.get_configuration(user_id)
    allowed_fields = config.allowed_deal_fields if config else None
    
    # Get curated field specs
    field_specs = None
    if allowed_fields:
        try:
            client, connection_id = get_hubspot_client_from_connection(user_id, supabase)
            schema_service = HubSpotSchemaService(client, supabase, connection_id)
            field_specs = await schema_service.get_curated_field_specs("deals", allowed_fields)
        except Exception:
            # Fallback to None if connection fails
            field_specs = None
    
    # Fetch user glossary for LLM correction
    glossary_service = GlossaryService(supabase)
    glossary = await glossary_service.get_user_glossary(user_id)
    glossary_text = glossary_service.format_for_llm(glossary)

    # Re-run extraction
    extraction_service = ExtractionService()
    extraction = await extraction_service.extract(transcript, field_specs, glossary_text=glossary_text)
    
    # Update memo with new extraction
    from datetime import datetime
    supabase.table("memos").update({
        "status": "pending_review",
        "extraction": extraction.model_dump(),
        "processed_at": datetime.utcnow().isoformat(),
    }).eq("id", str(memo_id)).execute()
    
    # Return updated memo
    updated_result = supabase.table("memos").select("*").eq("id", str(memo_id)).single().execute()
    updated_memo = updated_result.data
    
    return Memo(
        id=updated_memo["id"],
        userId=updated_memo["user_id"],
        audioUrl=updated_memo["audio_url"],
        audioDuration=updated_memo["audio_duration"],
        status=updated_memo["status"],
        transcript=updated_memo.get("transcript"),
        transcriptConfidence=updated_memo.get("transcript_confidence"),
        extraction=updated_memo.get("extraction"),
        errorMessage=updated_memo.get("error_message"),
        createdAt=updated_memo["created_at"],
        processedAt=updated_memo.get("processed_at"),
        approvedAt=updated_memo.get("approved_at"),
    )

