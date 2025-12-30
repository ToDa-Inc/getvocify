"""
Voice memo API endpoints
"""

import asyncio
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from uuid import UUID
from app.deps import get_supabase, get_user_id
from app.services.storage import StorageService
from app.services.transcription import TranscriptionService
from app.services.extraction import ExtractionService
from app.services.crm_updates import CRMUpdatesService
from app.models.memo import Memo, MemoCreate, MemoUpdate, UploadResponse, MemoExtraction, ApproveMemoRequest
from app.models.crm_update import CRMUpdate
from supabase import Client
from typing import Optional, List
from datetime import datetime


router = APIRouter(prefix="/api/v1/memos", tags=["memos"])


async def process_memo_async(
    memo_id: str,
    audio_url: str,
    supabase: Client,
    transcription_service: TranscriptionService,
    extraction_service: ExtractionService
):
    """
    Background task to process memo: transcribe → extract → update status
    """
    try:
        # Update status to transcribing
        supabase.table("memos").update({
            "status": "transcribing"
        }).eq("id", memo_id).execute()
        
        # Download audio from storage
        # Extract path from URL
        # Supabase URLs format: https://{project}.supabase.co/storage/v1/object/public/{bucket}/{path}
        parts = audio_url.split("/public/")
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
        extraction = await extraction_service.extract(transcription.transcript)
        
        # Update with extraction and mark as pending_review
        from datetime import datetime
        supabase.table("memos").update({
            "status": "pending_review",
            "extraction": extraction.model_dump(),
            "processed_at": datetime.utcnow().isoformat(),
        }).eq("id", memo_id).execute()
        
    except Exception as e:
        # Update status to failed
        supabase.table("memos").update({
            "status": "failed",
            "error_message": str(e)
        }).eq("id", memo_id).execute()


@router.post("/upload", response_model=UploadResponse)
async def upload_memo(
    audio: UploadFile = File(...),
    supabase: Client = Depends(get_supabase),
    user_id: str = Depends(get_user_id),
):
    """
    Upload audio file and start processing pipeline
    
    Flow:
    1. Store audio in Supabase Storage
    2. Create memo record with status 'uploading'
    3. Start background processing (transcribe → extract)
    4. Return memo ID for polling
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
    
    # Create memo record
    memo_data = {
        "user_id": user_id,
        "audio_url": audio_url,
        "audio_duration": estimated_duration,
        "status": "uploading",
    }
    
    result = supabase.table("memos").insert(memo_data).execute()
    
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create memo record"
        )
    
    memo_id = result.data[0]["id"]
    
    # Start background processing
    transcription_service = TranscriptionService()
    extraction_service = ExtractionService()
    
    # Run processing in background
    asyncio.create_task(
        process_memo_async(
            memo_id,
            audio_url,
            supabase,
            transcription_service,
            extraction_service
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
        audioUrl=memo_data["audio_url"],
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
            audioUrl=memo_data["audio_url"],
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


@router.post("/{memo_id}/approve", response_model=Memo)
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
    
    When HubSpot integration is implemented, this will:
    1. Get user's CRM connection
    2. Map extraction to CRM fields
    3. Push to CRM (create/update deal, contact, etc.)
    4. Create CRM update records for audit trail
    """
    # Get memo
    memo_result = supabase.table("memos").select("*").eq("id", str(memo_id)).eq("user_id", user_id).execute()
    
    if not memo_result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Memo not found"
        )
    
    memo_data = memo_result.data[0]
    
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
    
    # Get user's CRM connection (for now, just check if exists)
    # TODO: When HubSpot service is implemented, use it here
    crm_result = supabase.table("crm_connections").select("*").eq("user_id", user_id).eq("status", "connected").limit(1).execute()
    
    if not crm_result.data:
        # No CRM connected - just mark as approved without pushing
        supabase.table("memos").update({
            "status": "approved",
            "approved_at": datetime.utcnow().isoformat(),
            "extraction": extraction_data,  # Update extraction if edited
        }).eq("id", str(memo_id)).execute()
    else:
        # CRM connected - push to CRM and track updates
        crm_connection = crm_result.data[0]
        crm_updates_service = CRMUpdatesService(supabase)
        
        # TODO: When HubSpot service is implemented:
        # hubspot_service = HubSpotService(crm_connection)
        # 
        # # Create/update deal
        # if extraction_data.get("companyName") or extraction_data.get("dealAmount"):
        #     deal_data = map_extraction_to_hubspot_deal(extraction_data)
        #     update_id = await crm_updates_service.create_update(
        #         str(memo_id), user_id, crm_connection["id"],
        #         "create_deal" if not existing_deal else "update_deal",
        #         "deal", deal_data
        #     )
        #     try:
        #         result = await hubspot_service.create_or_update_deal(deal_data)
        #         await crm_updates_service.mark_success(update_id, result["id"], result)
        #     except Exception as e:
        #         await crm_updates_service.mark_failed(update_id, str(e))
        # 
        # # Create/update contact
        # if extraction_data.get("contactName"):
        #     contact_data = map_extraction_to_hubspot_contact(extraction_data)
        #     update_id = await crm_updates_service.create_update(
        #         str(memo_id), user_id, crm_connection["id"],
        #         "create_contact", "contact", contact_data
        #     )
        #     try:
        #         result = await hubspot_service.create_or_update_contact(contact_data)
        #         await crm_updates_service.mark_success(update_id, result["id"], result)
        #     except Exception as e:
        #         await crm_updates_service.mark_failed(update_id, str(e))
        
        # For now, just mark as approved
        # When HubSpot integration is added, the above code will execute
        supabase.table("memos").update({
            "status": "approved",
            "approved_at": datetime.utcnow().isoformat(),
            "extraction": extraction_data,
        }).eq("id", str(memo_id)).execute()
    
    # Return updated memo
    updated_result = supabase.table("memos").select("*").eq("id", str(memo_id)).execute()
    updated_memo = updated_result.data[0]
    
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

