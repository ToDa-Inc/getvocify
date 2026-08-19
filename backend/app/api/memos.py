"""
Voice memo API endpoints
"""

import asyncio
import logging
import time
from httpcore import ReadError as HttpcoreReadError
from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException, status, Body
from pydantic import BaseModel
from fastapi.responses import JSONResponse
from uuid import UUID
from typing import Optional, List, Union
from app.deps import get_supabase, get_user_id
from app.services.storage import StorageService
from app.services.extraction import ExtractionService
from app.services.glossary import GlossaryService
from app.services.crm_updates import CRMUpdatesService
from app.services.crm_config import CRMConfigurationService
from app.services.memo_approval import approve_memo_core, CRMSyncError
from app.services.preview_targets import resolve_preview_deal_selection
from app.services.memo_crm import get_memo_crm_or_none_with_hubspot_refresh
from app.services.hubspot import HubSpotClient, SyncResult
from app.services.hubspot.deal_field_names import normalize_hubspot_allowed_deal_fields
from app.models.memo import Memo, MemoCreate, MemoUpdate, UploadResponse, MemoExtraction, ApproveMemoRequest
from app.models.crm_update import CRMUpdate
from app.models.approval import ApprovalPreview, DealMatch, PreviewRequest
from app.logging_config import log_domain, DOMAIN_MEMO
from app.metrics import record_transcription_duration
from supabase import Client
from typing import Optional, List
from datetime import datetime, timedelta, timezone


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/memos", tags=["memos"])


_DEAL_STAGE_INFERENCE_HINT = (
    "Infer which pipeline stage this deal should be in based on what was actually "
    "discussed (e.g. a demo was scheduled -> appointment stage; a contract was sent "
    "-> contract stage; they just said thanks with no forward motion -> leave as-is). "
    "Only set this if the conversation clearly implies a stage; return null rather "
    "than guessing."
)


async def _curated_field_specs_for_primary_crm(
    supabase: Client,
    user_id: str,
) -> Optional[list]:
    """
    Field specs for LLM extraction from the user's primary (or sole) CRM.

    Deal stage is always requested from the LLM, regardless of the user's Editable
    Fields selection: which stage a deal should be in is something to infer from the
    conversation on every memo, not a fixed field that has to be opted into - the
    user reviews and can change the AI's guess in the approval screen either way.
    """
    config_service = CRMConfigurationService(supabase)
    try:
        config = await config_service.get_configuration(user_id)
    except Exception:
        config = None
    if not config:
        return None
    allowed_fields = list(config.allowed_deal_fields or [])
    try:
        provider, conn = await get_memo_crm_or_none_with_hubspot_refresh(supabase, user_id)
    except HTTPException:
        return None
    if not provider:
        return None
    stage_field = "StageName" if (conn or {}).get("provider") == "salesforce" else "dealstage"
    if stage_field not in allowed_fields:
        allowed_fields.append(stage_field)
    try:
        get_specs = getattr(provider, "get_extraction_field_specs", None)
        if callable(get_specs):
            specs = await get_specs(
                allowed_deal_fields=allowed_fields,
                allowed_contact_fields=config.allowed_contact_fields,
                allowed_company_fields=config.allowed_company_fields,
                allowed_line_item_fields=getattr(config, "allowed_line_item_fields", None),
            )
        else:
            specs = await provider.get_curated_field_specs(allowed_fields)
    except Exception:
        return None
    for spec in specs:
        if spec.get("name") == stage_field:
            existing_desc = (spec.get("description") or "").strip()
            spec["description"] = (
                f"{_DEAL_STAGE_INFERENCE_HINT} {existing_desc}".strip()
                if existing_desc else _DEAL_STAGE_INFERENCE_HINT
            )
    return specs


def _memo_from_row(memo_data: dict) -> Memo:
    """Build Memo from DB row, with defensive handling for malformed data."""
    extraction = memo_data.get("extraction")
    if extraction is not None and isinstance(extraction, dict):
        try:
            MemoExtraction.model_validate(extraction)
        except Exception as e:
            logger.warning("Memo %s has malformed extraction, omitting: %s", memo_data.get("id"), e)
            extraction = None
    try:
        return Memo(
            id=memo_data["id"],
            userId=memo_data["user_id"],
            audioUrl=memo_data.get("audio_url") or "",
            audioDuration=memo_data["audio_duration"],
            status=memo_data["status"],
            transcript=memo_data.get("transcript"),
            transcriptConfidence=memo_data.get("transcript_confidence"),
            extraction=extraction,
            errorMessage=memo_data.get("error_message"),
            createdAt=memo_data["created_at"],
            processedAt=memo_data.get("processed_at"),
            approvedAt=memo_data.get("approved_at"),
            pipelineMeta=memo_data.get("pipeline_meta") or None,
            source=memo_data.get("source") or memo_data.get("source_type"),
            hubspotEngagementId=memo_data.get("hubspot_engagement_id"),
            hubspotContactId=memo_data.get("hubspot_contact_id"),
            hubspotDealId=memo_data.get("hubspot_deal_id") or memo_data.get("matched_deal_id"),
        )
    except Exception as e:
        logger.exception("Failed to build Memo from row %s: %s", memo_data.get("id"), e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to load memo data",
        ) from e


async def extract_memo_async(
    memo_id: str,
    user_id: str,
    transcript: str,
    supabase: Client,
    extraction_service: ExtractionService,
    field_specs: Optional[list[dict]] = None,
    source_type: str = "voice_memo",
):
    """
    Background task to extract structured data from pre-transcribed memo.
    source_type ('voice_memo' | 'meeting_transcript') adjusts LLM prompt context.
    """
    from datetime import datetime
    from app.services.pipeline_meta import persist_pipeline_meta, pipeline_run

    stages: list = []
    try:
        logger.info(
            "📝 Extract memo async started",
            extra=log_domain(DOMAIN_MEMO, "extract_async_started", memo_id=memo_id, user_id=user_id),
        )
        supabase.table("memos").update({
            "status": "extracting",
            "processing_started_at": datetime.utcnow().isoformat(),
        }).eq("id", memo_id).execute()
        
        # Fetch user glossary for LLM correction
        glossary_service = GlossaryService(supabase)
        glossary = await glossary_service.get_user_glossary(user_id)

        from app.services.extraction_context import load_extraction_llm_context
        from app.services.session_entities import load_stt_profile
        from app.services.transcript_sanitize import prepare_transcript_for_extraction_async

        product_context, existing_values = await load_extraction_llm_context(
            supabase, user_id, memo_id=memo_id, field_specs=field_specs
        )
        profile = load_stt_profile(supabase, user_id)

        with pipeline_run() as stages:
            transcript, glossary_text = await prepare_transcript_for_extraction_async(
                transcript,
                glossary,
                existing_values,
                extra_names=[profile.get("full_name"), profile.get("company_name")],
            )
            extraction = await extraction_service.extract(
                transcript,
                field_specs,
                glossary_text=glossary_text,
                source_context=source_type,
                product_context=product_context,
                existing_values=existing_values,
            )

        supabase.table("memos").update({
            "status": "pending_review",
            "transcript": transcript,
            "extraction": extraction.model_dump(),
            "processed_at": datetime.utcnow().isoformat(),
            "processing_started_at": None,  # Clear on success
        }).eq("id", memo_id).execute()
        persist_pipeline_meta(supabase, memo_id, stages)
        logger.info(
            "✅ Extract memo async complete",
            extra=log_domain(DOMAIN_MEMO, "extract_async_complete", memo_id=memo_id),
        )
        
    except Exception as e:
        logger.exception(
            "❌ Extract memo async failed",
            extra=log_domain(DOMAIN_MEMO, "extract_async_failed", memo_id=memo_id, error=str(e)),
        )
        supabase.table("memos").update({
            "status": "failed",
            "error_message": str(e),
            "processing_started_at": None,
        }).eq("id", memo_id).execute()
        persist_pipeline_meta(supabase, memo_id, stages)


async def process_memo_async(
    memo_id: str,
    user_id: str,
    audio_bytes: bytes,
    content_type: str,
    supabase: Client,
):
    """
    Background task to process memo: transcribe (Deepgram Nova-3) → update status.
    No audio storage - transcribe directly from in-memory bytes.
    """
    from datetime import datetime
    from app.services.pipeline_meta import persist_pipeline_meta, pipeline_run
    from app.services.stt_batch import transcribe_bytes

    stages: list = []
    try:
        logger.info(
            "🚀 Process memo async started (batch STT)",
            extra=log_domain(DOMAIN_MEMO, "process_async_started", memo_id=memo_id, user_id=user_id),
        )
        supabase.table("memos").update({
            "status": "transcribing",
            "processing_started_at": datetime.utcnow().isoformat(),
        }).eq("id", memo_id).execute()

        t0 = time.perf_counter()
        with pipeline_run() as stages:
            transcript_text = await transcribe_bytes(
                audio_bytes,
                content_type=content_type,
                user_id=user_id,
                diarization=True,
            )
            from app.services.transcript_sanitize import sanitize_user_transcript

            transcript_text = await sanitize_user_transcript(
                transcript_text, user_id, supabase
            )
        record_transcription_duration(time.perf_counter() - t0, "upload")

        supabase.table("memos").update({
            "status": "pending_transcript",
            "transcript": transcript_text,
            "transcript_confidence": 0.95,
            "processing_started_at": None,  # Clear on success
        }).eq("id", memo_id).execute()
        persist_pipeline_meta(supabase, memo_id, stages)
        logger.info(
            "✅ Process memo async complete",
            extra=log_domain(DOMAIN_MEMO, "process_async_complete", memo_id=memo_id),
        )
        
    except Exception as e:
        logger.exception(
            "❌ Process memo async failed",
            extra=log_domain(DOMAIN_MEMO, "process_async_failed", memo_id=memo_id, error=str(e)),
        )
        supabase.table("memos").update({
            "status": "failed",
            "error_message": str(e),
            "processing_started_at": None,
        }).eq("id", memo_id).execute()
        persist_pipeline_meta(supabase, memo_id, stages)


@router.post("/upload", response_model=UploadResponse)
async def upload_memo(
    audio: UploadFile = File(...),
    transcript: Optional[str] = Form(None),
    supabase: Client = Depends(get_supabase),
    user_id: str = Depends(get_user_id),
):
    """
    Upload audio and/or transcript. No audio storage - transcript only.
    
    Flow:
    - If transcript provided: Create memo with transcript, go directly to extraction (no storage)
    - If no transcript: Transcribe from bytes in memory → Extract (no storage)
    """
    # Read audio bytes (needed for transcription when no transcript)
    audio_bytes = await audio.read()
    
    # Validate file size (10MB max) when we have audio
    max_size = 10 * 1024 * 1024
    if len(audio_bytes) > max_size:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File too large. Maximum size is {max_size / 1024 / 1024}MB"
        )
    
    field_specs = await _curated_field_specs_for_primary_crm(supabase, user_id)

    if transcript and transcript.strip():
        logger.info(
            "📤 Upload memo with transcript",
            extra=log_domain(DOMAIN_MEMO, "upload", user_id=user_id, has_transcript=True),
        )
        from app.services.transcript_sanitize import sanitize_user_transcript

        transcript = await sanitize_user_transcript(transcript.strip(), user_id, supabase)
        estimated_duration = len(transcript) / 15  # rough: ~15 chars/sec speech
        result = supabase.table("memos").insert({
            "user_id": user_id,
            "audio_url": "",
            "audio_duration": estimated_duration,
            "status": "pending_transcript",
            "transcript": transcript,
            "transcript_confidence": 1.0,
        }).execute()
        
        memo_id = result.data[0]["id"]
        logger.info(
            "✅ Upload memo created (transcript) - awaiting transcript review",
            extra=log_domain(DOMAIN_MEMO, "upload_complete", memo_id=memo_id, user_id=user_id),
        )
        return UploadResponse(
            id=str(memo_id),
            status="pending_transcript",
            statusUrl=f"/api/v1/memos/{memo_id}"
        )
    else:
        # No transcript - transcribe from bytes via Speechmatics batch
        from app.config import settings
        if not settings.SPEECHMATICS_API_KEY:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Transcript required. Speechmatics is disabled. Use recording with real-time transcription (Speechmatics) or provide transcript."
            )
        if not audio.content_type or not audio.content_type.startswith("audio/"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File must be an audio file when transcript is not provided"
            )
        
        logger.info(
            "📤 Upload memo with audio",
            extra=log_domain(DOMAIN_MEMO, "upload", user_id=user_id, has_transcript=False, audio_len=len(audio_bytes)),
        )
        estimated_duration = len(audio_bytes) / (1024 * 1024) * 60
        result = supabase.table("memos").insert({
            "user_id": user_id,
            "audio_url": "",
            "audio_duration": estimated_duration,
            "status": "uploading",
        }).execute()
        
        memo_id = result.data[0]["id"]
        logger.info(
            "✅ Upload memo created (audio)",
            extra=log_domain(DOMAIN_MEMO, "upload_complete", memo_id=memo_id, user_id=user_id),
        )
        
        asyncio.create_task(
            process_memo_async(
                memo_id,
                user_id,
                audio_bytes,
                audio.content_type or "audio/webm",
                supabase,
            )
        )
        
        return UploadResponse(
            id=str(memo_id),
            status="uploading",
            statusUrl=f"/api/v1/memos/{memo_id}"
        )


class UploadTranscriptRequest(BaseModel):
    """Transcript-only upload (from real-time transcription or meeting transcript paste)"""
    transcript: str
    source_type: Optional[str] = None  # 'voice_memo' | 'meeting_transcript', default voice_memo


@router.post("/upload-transcript", response_model=UploadResponse)
async def upload_transcript_only(
    body: UploadTranscriptRequest,
    supabase: Client = Depends(get_supabase),
    user_id: str = Depends(get_user_id),
):
    """
    Create memo from transcript only (no audio).
    Use when real-time transcription (Speechmatics/Deepgram) already produced the transcript.
    """
    transcript = (body.transcript or "").strip()
    if not transcript:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Transcript is required",
        )
    from app.services.transcript_sanitize import sanitize_user_transcript

    transcript = await sanitize_user_transcript(transcript, user_id, supabase)
    source_type = body.source_type or "voice_memo"
    if source_type not in ("voice_memo", "meeting_transcript"):
        source_type = "voice_memo"

    field_specs = await _curated_field_specs_for_primary_crm(supabase, user_id)

    estimated_duration = len(transcript) / 15
    result = supabase.table("memos").insert({
        "user_id": user_id,
        "audio_url": "",
        "audio_duration": estimated_duration,
        "status": "pending_transcript",
        "transcript": transcript,
        "transcript_confidence": 1.0,
        "source_type": source_type,
    }).execute()
    
    memo_id = result.data[0]["id"]
    
    return UploadResponse(
        id=str(memo_id),
        status="pending_transcript",
        statusUrl=f"/api/v1/memos/{memo_id}"
    )


@router.post("/upload-and-extract", response_model=UploadResponse)
async def upload_transcript_and_extract(
    body: UploadTranscriptRequest,
    supabase: Client = Depends(get_supabase),
    user_id: str = Depends(get_user_id),
):
    """
    Create memo from transcript and start AI extraction in one call.
    Use when the user has already reviewed the transcript (e.g. RecordPage "Accept & Continue").
    Returns immediately with status "extracting"; extraction runs in background.
    """
    transcript = (body.transcript or "").strip()
    if not transcript:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Transcript is required",
        )
    from app.services.transcript_sanitize import sanitize_user_transcript

    transcript = await sanitize_user_transcript(transcript, user_id, supabase)

    field_specs = await _curated_field_specs_for_primary_crm(supabase, user_id)

    estimated_duration = len(transcript) / 15
    result = supabase.table("memos").insert({
        "user_id": user_id,
        "audio_url": "",
        "audio_duration": estimated_duration,
        "status": "extracting",
        "transcript": transcript,
        "transcript_confidence": 1.0,
        "processing_started_at": datetime.utcnow().isoformat(),
    }).execute()

    memo_id = result.data[0]["id"]

    extraction_service = ExtractionService()
    asyncio.create_task(
        extract_memo_async(str(memo_id), user_id, transcript, supabase, extraction_service, field_specs)
    )

    return UploadResponse(
        id=str(memo_id),
        status="extracting",
        statusUrl=f"/api/v1/memos/{memo_id}"
    )


@router.get("", response_model=list[Memo])
async def list_memos(
    supabase: Client = Depends(get_supabase),
    user_id: str = Depends(get_user_id),
    limit: int = 20,
    offset: int = 0,
    hubspot_deal_id: Optional[str] = None,
    hubspot_contact_id: Optional[str] = None,
):
    """
    List user's memos.

    Optional HubSpot filters (for the extension on a deal/contact page):
    - hubspot_deal_id: memos from calls on that deal, or approved against it
    - hubspot_contact_id: memos from calls on that contact
    """
    limit = max(1, min(limit, 50))
    offset = max(0, offset)

    q = (
        supabase.table("memos")
        .select("*")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .limit(limit)
        .offset(offset)
    )

    deal_id = (hubspot_deal_id or "").strip() or None
    contact_id = (hubspot_contact_id or "").strip() or None

    if deal_id:
        # Call memos linked at ingest + memos later matched/approved to this deal
        q = q.or_(f"hubspot_deal_id.eq.{deal_id},matched_deal_id.eq.{deal_id}")
    elif contact_id:
        q = q.eq("hubspot_contact_id", contact_id)

    result = q.execute()
    memos = [_memo_from_row(memo_data) for memo_data in (result.data or [])]
    return memos


class UsageWeeklyDay(BaseModel):
    day: str
    memos: int


class UsageActivity(BaseModel):
    action: str
    company: str
    time: str
    type: str  # "memo" | "sync"


class UsageResponse(BaseModel):
    total_memos: int
    approved_count: int
    this_week_memos: int
    this_week_approved: int
    time_saved_hours: float
    this_week_time_saved_hours: float
    accuracy_pct: Optional[float] = None  # approved / (approved + rejected) * 100
    weekly: List[UsageWeeklyDay]
    recent_activity: List[UsageActivity]


@router.get("/usage", response_model=UsageResponse)
async def get_usage(
    supabase: Client = Depends(get_supabase),
    user_id: str = Depends(get_user_id),
):
    """Aggregated usage stats for the current user (real data from memos)."""
    result = supabase.table("memos").select("id,status,created_at,audio_duration,extraction").eq("user_id", user_id).order("created_at", desc=True).limit(2000).execute()
    rows = result.data or []

    now = datetime.now(timezone.utc)
    week_start = now - timedelta(days=now.weekday(), hours=now.hour, minutes=now.minute, seconds=now.second, microseconds=0)
    week_start_naive = week_start.replace(tzinfo=None).isoformat() if week_start.tzinfo else week_start.isoformat()

    total_memos = len(rows)
    approved_count = sum(1 for r in rows if r.get("status") == "approved")
    rejected_count = sum(1 for r in rows if r.get("status") == "rejected")
    this_week_memos = 0
    this_week_approved = 0
    time_saved_sec = 0.0
    this_week_time_sec = 0.0
    day_counts = {i: 0 for i in range(7)}  # 0=Monday .. 6=Sunday

    for r in rows:
        created = r.get("created_at")
        if created:
            try:
                dt = datetime.fromisoformat(created.replace("Z", "+00:00")) if isinstance(created, str) else created
                if dt.tzinfo:
                    dt = dt.replace(tzinfo=None)
                created_naive = dt.isoformat() if hasattr(dt, "isoformat") else str(created)
                if created_naive >= week_start_naive:
                    this_week_memos += 1
                    if r.get("status") == "approved":
                        this_week_approved += 1
                days_ago = (now.replace(tzinfo=None) - dt).days if hasattr(dt, "__sub__") else 0
                if 0 <= days_ago < 7:
                    weekday = dt.weekday()
                    day_counts[weekday] = day_counts.get(weekday, 0) + 1
            except Exception:
                pass
        dur = r.get("audio_duration") or 0
        try:
            dur_f = float(dur)
        except (TypeError, ValueError):
            dur_f = 0.0
        time_saved_sec += dur_f
        if created:
            try:
                dt = datetime.fromisoformat(created.replace("Z", "+00:00")) if isinstance(created, str) else created
                if dt.tzinfo:
                    dt = dt.replace(tzinfo=None)
                if (now.replace(tzinfo=None) - dt).days < 7:
                    this_week_time_sec += dur_f
            except Exception:
                pass

    day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    weekly = [UsageWeeklyDay(day=day_names[i], memos=day_counts.get(i, 0)) for i in range(7)]

    recent = []
    for r in rows[:15]:
        created = r.get("created_at") or ""
        ext = r.get("extraction") or {}
        company = (ext.get("companyName") or ext.get("company_name") or "").strip() or "Untitled memo"
        status = r.get("status") or ""
        action = "Synced to CRM" if status == "approved" else "Created memo"
        recent.append(UsageActivity(action=action, company=company, time=created, type="sync" if status == "approved" else "memo"))

    accuracy_pct = None
    if approved_count + rejected_count > 0:
        accuracy_pct = round(100.0 * approved_count / (approved_count + rejected_count), 1)

    return UsageResponse(
        total_memos=total_memos,
        approved_count=approved_count,
        this_week_memos=this_week_memos,
        this_week_approved=this_week_approved,
        time_saved_hours=round(time_saved_sec * 5 / 3600, 1),
        this_week_time_saved_hours=round(this_week_time_sec * 5 / 3600, 1),
        accuracy_pct=accuracy_pct,
        weekly=weekly,
        recent_activity=recent,
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
    return _memo_from_row(memo_data)


# Maps SyncResult.error_code (set in sync.py / salesforce_provider.py) to an HTTP
# status for the /approve endpoint. Only codes that represent a predictable,
# user-actionable business failure get a 4xx here - anything else (API_ERROR,
# UNKNOWN_ERROR, SF_SYNC_FAILED, or an unrecognized code) defaults to 500,
# matching prior behavior for those genuinely opaque/operational failures.
_CRM_SYNC_ERROR_STATUS: dict[Optional[str], int] = {
    # Request was well-formed, but the current CRM connection can't satisfy it
    # (Salesforce requires an Opportunity; the caller asked to skip it). This is
    # a conflict between the request's intent and the connection's capabilities,
    # not a malformed body - 422 is reserved for that (FastAPI emits it itself
    # for pydantic validation errors), so 409 is the accurate fit here.
    "SKIP_DEAL_UNSUPPORTED": status.HTTP_409_CONFLICT,
    # Same class of conflict as SKIP_DEAL_UNSUPPORTED above: the rep marked a
    # call outcome, but the connected CRM (Salesforce, for now) has no
    # implementation for it yet - see salesforce_provider.py.
    "CALL_OUTCOME_UNSUPPORTED": status.HTTP_409_CONFLICT,
    # The CRM connection's token is invalid or lacks a required scope. Same
    # class of problem as "you need to reconnect" - 401 signals that directly
    # instead of a misleading 500.
    "AUTH_ERROR": status.HTTP_401_UNAUTHORIZED,
    "SCOPE_ERROR": status.HTTP_401_UNAUTHORIZED,
}


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
    
    try:
        return await approve_memo_core(supabase, str(memo_id), user_id, payload)
    except CRMSyncError as e:
        # A predictable business failure from the CRM provider (e.g. "Salesforce
        # needs a deal") is not a server bug: a 500 hides it in the same bucket as
        # real crashes and monitoring can't tell them apart. Map the SyncResult's
        # own error_code (never invented here, only forwarded) to a 4xx, and fall
        # back to 500 only for codes that are genuinely opaque/operational.
        status_code = _CRM_SYNC_ERROR_STATUS.get(e.error_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        return JSONResponse(
            status_code=status_code,
            content={"detail": str(e), "error_code": e.error_code},
        )
    except ValueError as e:
        detail = str(e)
        if "Memo not found" in detail:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail) from e
        if "No extraction" in detail:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail) from e
        if "Multiple CRMs" in detail or "primary CRM" in detail.lower():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail) from e
        if "Unsupported CRM provider" in detail:
            raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=detail) from e
        if (
            "HubSpot authorization expired" in detail
            or "Could not refresh HubSpot" in detail
            or (
                "Authentication failed" in detail
                and (
                    "expired" in detail.lower()
                    or "oauth" in detail.lower()
                )
            )
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=detail if "HubSpot" in detail else "HubSpot session expired. Disconnect and reconnect in Integrations.",
            ) from e
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=detail,
        ) from e


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
    """Get HubSpot client and connection ID from user's connection (refreshes OAuth token if needed)."""
    from app.services.hubspot.oauth import ensure_fresh_hubspot_connection

    try:
        result = supabase.table("crm_connections").select("*").eq(
            "user_id", user_id
        ).eq("provider", "hubspot").eq("status", "connected").single().execute()
        
        if not result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="HubSpot connection not found",
            )
        
        connection = ensure_fresh_hubspot_connection(supabase, result.data)
        return HubSpotClient(connection["access_token"]), connection["id"]
    except HTTPException:
        raise
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
    memo_status = memo_data.get("status", "unknown")
    
    if not extraction_data:
        status_hint = ""
        if memo_status in ("uploading", "transcribing", "extracting"):
            status_hint = f" Memo is still processing (status: {memo_status})."
        elif memo_status == "failed":
            status_hint = " Processing failed. Use Re-extract if you have a transcript."
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Memo extraction not available.{status_hint}",
        )
    
    try:
        provider, conn = await get_memo_crm_or_none_with_hubspot_refresh(supabase, user_id)
    except HTTPException:
        return []
    if not provider or not conn:
        return []

    config_service = CRMConfigurationService(supabase)
    config = await config_service.get_configuration(user_id, connection_id=str(conn["id"]))
    pipeline_id = config.default_pipeline_id if config else None

    extraction = MemoExtraction(**extraction_data)
    matches = await provider.find_matching_deals(extraction, limit=3, pipeline_id=pipeline_id)
    logger.info(
        "🔍 Match memo to deals",
        extra=log_domain(DOMAIN_MEMO, "match", memo_id=str(memo_id), match_count=len(matches)),
    )
    return matches


@router.get("/{memo_id}/preview", response_model=ApprovalPreview)
async def get_approval_preview(
    memo_id: UUID,
    deal_id: Optional[str] = None,
    create_new_deal: bool = False,
    contact_id: Optional[str] = None,
    supabase: Client = Depends(get_supabase),
    user_id: str = Depends(get_user_id),
):
    """
    Get approval preview showing what will be updated in CRM.

    Contact-first: email / unique phone / unique name auto-lock the contact.
    Ambiguous name/phone matches return contact_candidates for confirmation.
    With a locked contact and zero linked deals (and create_new_deal=false),
    preview is contact/company-only (skip_deal).
    """
    # Handle empty string from query param
    if deal_id == "":
        deal_id = None
    if contact_id == "":
        contact_id = None
        
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
    
    try:
        provider, conn = await get_memo_crm_or_none_with_hubspot_refresh(supabase, user_id)
    except HTTPException as e:
        raise HTTPException(
            status_code=e.status_code,
            detail=e.detail,
        ) from e
    if not provider or not conn:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="CRM connection not found",
        )

    config_service = CRMConfigurationService(supabase)
    config = await config_service.get_configuration(user_id, connection_id=str(conn["id"]))
    if conn.get("provider") == "salesforce":
        default_fields = ["Name", "Amount", "CloseDate", "StageName", "Description"]
    else:
        default_fields = ["dealname", "amount", "description", "closedate"]
    allowed_fields = (config.allowed_deal_fields or default_fields) if config else default_fields
    if conn.get("provider") == "hubspot":
        allowed_fields = normalize_hubspot_allowed_deal_fields(allowed_fields)
    allowed_contact_fields = (
        list(config.allowed_contact_fields) if config and config.allowed_contact_fields else []
    )
    allowed_company_fields = (
        list(config.allowed_company_fields) if config and config.allowed_company_fields else []
    )
    allowed_line_item_fields = (
        list(getattr(config, "allowed_line_item_fields", None) or [])
        if config
        else []
    )

    extraction = MemoExtraction(**extraction_data)
    pipeline_id = config.default_pipeline_id if config else None
    matches = await provider.find_matching_deals(extraction, limit=5, pipeline_id=pipeline_id)

    identity = await provider.resolve_identity(
        extraction,
        limit_deals=5,
        pipeline_id=pipeline_id,
        preferred_contact_id=contact_id,
    )
    # Salesforce stub returns None
    if identity is None:
        anchor = None
        contact_candidates = []
        selected_contact = None
    else:
        anchor = identity.selected
        contact_candidates = list(identity.candidates or [])
        selected_contact = anchor.to_contact_match() if anchor else None
    if anchor and anchor.deal_matches:
        seen: set[str] = set()
        merged: list = []
        for d in list(anchor.deal_matches) + list(matches):
            if d.deal_id in seen:
                continue
            seen.add(d.deal_id)
            merged.append(d)
        matches = merged[:5]

    selected_deal_id, create_new = resolve_preview_deal_selection(
        deal_id=deal_id,
        create_new_deal=bool(create_new_deal),
        has_selected_contact=selected_contact is not None,
        has_contact_candidates=bool(contact_candidates),
        linked_deal_count=len(anchor.deal_matches) if anchor else 0,
    )

    try:
        logger.info(
            "👁️ Get approval preview",
            extra=log_domain(
                DOMAIN_MEMO,
                "preview",
                memo_id=str(memo_id),
                deal_id=selected_deal_id,
                contact_id=selected_contact.contact_id if selected_contact else None,
            ),
        )
        preview = await provider.build_preview(
            memo_id=memo_id,
            transcript=transcript,
            extraction=extraction,
            matched_deals=matches,
            selected_deal_id=selected_deal_id,
            allowed_fields=allowed_fields,
            allowed_contact_fields=allowed_contact_fields,
            allowed_company_fields=allowed_company_fields,
            allowed_line_item_fields=allowed_line_item_fields,
            default_stage_name=config.default_stage_name if config else None,
            default_pipeline_id=config.default_pipeline_id if config else None,
            default_stage_id=config.default_stage_id if config else None,
            selected_contact=selected_contact,
            contact_candidates=contact_candidates,
            create_new_deal=create_new,
        )
    except Exception as e:
        logger.exception("Preview failed for memo %s: %s", memo_id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to build preview: {str(e)}",
        ) from e

    # Lost reasons for the extension's Lost picker - set here (not inside
    # build_preview, which is provider-generic) so the extension gets them
    # in the same round-trip as everything else. Falls back to the same
    # default crm_configurations ships with when there's no config row yet.
    preview.lost_reasons = list(
        config.lost_reasons if config and config.lost_reasons else
        ["No budget", "No response", "Chose a competitor", "Bad timing", "Not a fit"]
    )
    # Per-outcome gate (see compute_call_outcome_availability) - each button
    # only appears once its hs_lead_status mapping is configured AND still
    # valid against the live schema. Failure here (e.g. HubSpot API hiccup)
    # must not break the whole preview, so it degrades to "unavailable"
    # rather than raising.
    try:
        preview.call_outcome_availability = await provider.get_call_outcome_availability(
            lost_lead_status_value=config.lost_lead_status_value if config else None,
            on_hold_lead_status_value=config.on_hold_lead_status_value if config else None,
        )
    except Exception as e:
        logger.warning("Call outcome availability check failed for memo %s: %s", memo_id, e)

    # If a deal was explicitly selected, persist it to the memo record
    if deal_id:
        supabase.table("memos").update({
            "matched_deal_id": deal_id,
            "matched_deal_name": preview.selected_deal.deal_name if preview.selected_deal else None,
            "is_new_deal": False
        }).eq("id", str(memo_id)).execute()
    elif create_new_deal:
        supabase.table("memos").update({
            "matched_deal_id": None,
            "matched_deal_name": None,
            "is_new_deal": True
        }).eq("id", str(memo_id)).execute()
    
    return preview


@router.post("/{memo_id}/preview", response_model=ApprovalPreview)
async def post_approval_preview(
    memo_id: UUID,
    payload: Optional[PreviewRequest] = None,
    supabase: Client = Depends(get_supabase),
    user_id: str = Depends(get_user_id),
):
    """
    Get approval preview with optional edited extraction.
    Use this when the user has edited extraction in the UI before confirming.
    """
    deal_id = payload.deal_id if payload else None
    create_new_deal = bool(payload.create_new_deal) if payload else False
    contact_id = payload.contact_id if payload else None
    if deal_id == "":
        deal_id = None
    if contact_id == "":
        contact_id = None

    memo_result = supabase.table("memos").select("*").eq("id", str(memo_id)).eq("user_id", user_id).single().execute()
    if not memo_result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Memo not found")

    memo_data = memo_result.data
    extraction_data = payload.extraction if (payload and payload.extraction) else memo_data.get("extraction")
    transcript = memo_data.get("transcript", "")

    if not extraction_data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Memo extraction not available")

    try:
        provider, conn = await get_memo_crm_or_none_with_hubspot_refresh(supabase, user_id)
    except HTTPException as e:
        raise HTTPException(
            status_code=e.status_code,
            detail=e.detail,
        ) from e
    if not provider or not conn:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="CRM connection not found")

    config_service = CRMConfigurationService(supabase)
    config = await config_service.get_configuration(user_id, connection_id=str(conn["id"]))
    if conn.get("provider") == "salesforce":
        default_fields = ["Name", "Amount", "CloseDate", "StageName", "Description"]
    else:
        default_fields = ["dealname", "amount", "description", "closedate"]
    allowed_fields = (config.allowed_deal_fields or default_fields) if config else default_fields
    if conn.get("provider") == "hubspot":
        allowed_fields = normalize_hubspot_allowed_deal_fields(allowed_fields)

    extraction = MemoExtraction(**extraction_data)
    pipeline_id = config.default_pipeline_id if config else None
    matches = await provider.find_matching_deals(extraction, limit=5, pipeline_id=pipeline_id)
    identity = await provider.resolve_identity(
        extraction,
        limit_deals=5,
        pipeline_id=pipeline_id,
        preferred_contact_id=contact_id,
    )
    if identity is None:
        anchor = None
        contact_candidates = []
        selected_contact = None
    else:
        anchor = identity.selected
        contact_candidates = list(identity.candidates or [])
        selected_contact = anchor.to_contact_match() if anchor else None
    if anchor and anchor.deal_matches:
        seen: set[str] = set()
        merged: list = []
        for d in list(anchor.deal_matches) + list(matches):
            if d.deal_id in seen:
                continue
            seen.add(d.deal_id)
            merged.append(d)
        matches = merged[:5]

    selected_deal_id, create_new = resolve_preview_deal_selection(
        deal_id=deal_id,
        create_new_deal=create_new_deal,
        has_selected_contact=selected_contact is not None,
        has_contact_candidates=bool(contact_candidates),
        linked_deal_count=len(anchor.deal_matches) if anchor else 0,
    )

    try:
        preview = await provider.build_preview(
            memo_id=memo_id,
            transcript=transcript,
            extraction=extraction,
            matched_deals=matches,
            selected_deal_id=selected_deal_id,
            allowed_fields=allowed_fields,
            allowed_contact_fields=(
                list(config.allowed_contact_fields) if config and config.allowed_contact_fields else []
            ),
            allowed_company_fields=(
                list(config.allowed_company_fields) if config and config.allowed_company_fields else []
            ),
            allowed_line_item_fields=(
                list(getattr(config, "allowed_line_item_fields", None) or []) if config else []
            ),
            default_stage_name=config.default_stage_name if config else None,
            default_pipeline_id=config.default_pipeline_id if config else None,
            default_stage_id=config.default_stage_id if config else None,
            selected_contact=selected_contact,
            contact_candidates=contact_candidates,
            create_new_deal=create_new,
        )
    except Exception as e:
        logger.exception("Preview failed for memo %s: %s", memo_id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to build preview: {str(e)}",
        ) from e

    preview.lost_reasons = list(
        config.lost_reasons if config and config.lost_reasons else
        ["No budget", "No response", "Chose a competitor", "Bad timing", "Not a fit"]
    )
    try:
        preview.call_outcome_availability = await provider.get_call_outcome_availability(
            lost_lead_status_value=config.lost_lead_status_value if config else None,
            on_hold_lead_status_value=config.on_hold_lead_status_value if config else None,
        )
    except Exception as e:
        logger.warning("Call outcome availability check failed for memo %s: %s", memo_id, e)

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
        from app.services.hubspot.oauth import ensure_fresh_hubspot_connection

        conn_result = supabase.table("crm_connections").select("*").eq(
            "user_id", user_id
        ).eq("provider", "hubspot").eq("status", "connected").single().execute()
        
        if not conn_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="HubSpot connection not found",
            )
        
        connection = ensure_fresh_hubspot_connection(supabase, conn_result.data)
        connection_id = connection["id"]
        access_token = connection["access_token"]
    except HTTPException:
        raise
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
    crm_updates rows for this memo are removed too (ON DELETE CASCADE on
    crm_updates.memo_id) - this is intentional, not a bug: if a user deletes a
    memo (including for a data-deletion/GDPR request), its audit trail should
    not survive the memo. There is currently no separate, PII-free record of
    "a sync happened" that outlives the memo - if that's ever needed, it has
    to be a distinct table that doesn't key off personal data, not a change to
    this cascade. Tracked as debt, not implemented.
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


class ConfirmTranscriptRequest(BaseModel):
    """Request body for confirming transcript (optionally with user edits)"""
    transcript: Optional[str] = None  # If provided, updates memo transcript before extraction


_TRANSIENT_NETWORK_ERRORS = (HttpcoreReadError, ConnectionError, OSError)
try:
    import httpx
    _TRANSIENT_NETWORK_ERRORS = _TRANSIENT_NETWORK_ERRORS + (httpx.ReadError, httpx.ConnectError)
except ImportError:
    pass


@router.post("/{memo_id}/confirm-transcript")
async def confirm_transcript(
    memo_id: UUID,
    body: ConfirmTranscriptRequest = Body(default=ConfirmTranscriptRequest()),
    supabase: Client = Depends(get_supabase),
    user_id: str = Depends(get_user_id),
):
    """
    User has reviewed the transcript. Optionally accept transcript edits, then trigger AI extraction.
    
    Flow: Step 1 (review transcript) -> user clicks Continue -> this endpoint -> extraction runs -> Step 2 (edit fields).
    """
    max_retries = 3
    last_error = None
    for attempt in range(max_retries):
        try:
            memo_result = supabase.table("memos").select("*").eq("id", str(memo_id)).eq("user_id", user_id).single().execute()

            if not memo_result.data:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Memo not found")

            memo_data = memo_result.data
            if memo_data.get("status") == "extracting":
                return {"status": "extracting", "message": "AI extraction started"}

            if memo_data.get("status") != "pending_transcript":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Memo is not awaiting transcript review. Status: " + str(memo_data.get("status")),
                )

            transcript = (body.transcript or "").strip() or memo_data.get("transcript") or ""
            if not transcript:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Transcript is required",
                )

            field_specs = await _curated_field_specs_for_primary_crm(supabase, user_id)

            # Update transcript + status (avoids duplicate work on retry)
            from datetime import datetime
            update_payload = {"status": "extracting", "processing_started_at": datetime.utcnow().isoformat()}
            if body.transcript is not None and body.transcript.strip():
                update_payload["transcript"] = body.transcript.strip()

            supabase.table("memos").update(update_payload).eq("id", str(memo_id)).execute()

            source_type = memo_data.get("source_type") or memo_data.get("source") or "voice_memo"
            if source_type not in ("voice_memo", "meeting_transcript", "hubspot_call"):
                source_type = "voice_memo"
            extraction_service = ExtractionService()
            asyncio.create_task(
                extract_memo_async(
                    str(memo_id), user_id, transcript, supabase,
                    extraction_service, field_specs, source_type=source_type,
                )
            )

            return {"status": "extracting", "message": "AI extraction started"}

        except HTTPException:
            raise
        except _TRANSIENT_NETWORK_ERRORS as e:
            last_error = e
            if attempt < max_retries - 1:
                await asyncio.sleep(0.5 * (attempt + 1))
            else:
                logger.warning("confirm-transcript: connection reset/network error after %d retries: %s", max_retries, e)
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Temporary network error. Please try again.",
                ) from e


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
    
    field_specs = await _curated_field_specs_for_primary_crm(supabase, user_id)

    # Fetch user glossary for LLM correction
    glossary_service = GlossaryService(supabase)
    glossary = await glossary_service.get_user_glossary(user_id)

    # Clear previous error before retry
    from datetime import datetime
    supabase.table("memos").update({
        "status": "extracting",
        "error_message": None,
    }).eq("id", str(memo_id)).execute()

    source_type = memo_data.get("source_type") or memo_data.get("source") or "voice_memo"
    if source_type not in ("voice_memo", "meeting_transcript", "hubspot_call"):
        source_type = "voice_memo"
        from app.services.pipeline_meta import persist_pipeline_meta, pipeline_run
        from app.services.extraction_context import load_extraction_llm_context
        from app.services.session_entities import load_stt_profile
        from app.services.transcript_sanitize import prepare_transcript_for_extraction_async

        product_context, existing_values = await load_extraction_llm_context(
            supabase, user_id, memo_data=memo_data, field_specs=field_specs
        )
        profile = load_stt_profile(supabase, user_id)
        with pipeline_run() as stages:
            transcript, glossary_text = await prepare_transcript_for_extraction_async(
                transcript,
                glossary,
                existing_values,
                extra_names=[profile.get("full_name"), profile.get("company_name")],
            )
            try:
                extraction_service = ExtractionService()
                extraction = await extraction_service.extract(
                    transcript, field_specs,
                    glossary_text=glossary_text,
                    source_context=source_type,
                    product_context=product_context,
                    existing_values=existing_values,
                )
            except Exception as e:
                err_msg = str(e)
                logger.exception("Re-extract failed for memo %s: %s", memo_id, e)
                hint = " Check OPENROUTER_API_KEY in backend .env and restart the server." if "401" in err_msg else ""
                supabase.table("memos").update({
                    "status": "failed",
                    "error_message": f"Extraction failed: {err_msg}",
                }).eq("id", str(memo_id)).execute()
                persist_pipeline_meta(supabase, str(memo_id), stages)
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Re-extraction failed: {err_msg}{hint}",
                ) from e

        supabase.table("memos").update({
            "status": "pending_review",
            "transcript": transcript,
            "extraction": extraction.model_dump(),
            "processed_at": datetime.utcnow().isoformat(),
            "error_message": None,
        }).eq("id", str(memo_id)).execute()
        persist_pipeline_meta(supabase, str(memo_id), stages)
        
        updated_result = supabase.table("memos").select("*").eq("id", str(memo_id)).single().execute()
        return _memo_from_row(updated_result.data)


@router.post("/{memo_id}/re-transcribe", response_model=Memo)
async def re_transcribe_memo(
    memo_id: UUID,
    supabase: Client = Depends(get_supabase),
    user_id: str = Depends(get_user_id),
):
    """
    Re-download a HubSpot call recording and run STT again.

    Uses the user's current call-language settings. HubSpot recordings are
    re-fetched from HubSpot; uploaded voice memos do not keep audio after STT.
    """
    memo_result = (
        supabase.table("memos")
        .select("*")
        .eq("id", str(memo_id))
        .eq("user_id", user_id)
        .single()
        .execute()
    )
    if not memo_result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Memo not found")

    memo_data = memo_result.data
    if memo_data.get("status") == "approved":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot re-transcribe an approved memo. Reject it first if you need a new transcript.",
        )

    call_id = (memo_data.get("hubspot_engagement_id") or "").strip()
    source = (memo_data.get("source") or memo_data.get("source_type") or "").strip()
    if not call_id or source != "hubspot_call":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Re-transcribe is only available for HubSpot call recordings.",
        )

    if memo_data.get("status") in ("transcribing", "uploading", "extracting"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This memo is already being processed.",
        )

    from app.services.hubspot.oauth import ensure_fresh_hubspot_connection
    from app.services.hubspot.call_processor import process_hubspot_call_background

    conn_result = (
        supabase.table("crm_connections")
        .select("id, access_token, refresh_token, token_expires_at, status")
        .eq("user_id", user_id)
        .eq("provider", "hubspot")
        .limit(1)
        .execute()
    )
    rows = conn_result.data or []
    if not rows or rows[0].get("status") != "connected":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="HubSpot connection not found. Please connect your HubSpot account first.",
        )
    try:
        connection = ensure_fresh_hubspot_connection(supabase, rows[0])
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"HubSpot authorization expired. Please reconnect HubSpot. ({e})",
        ) from e
    access_token = (connection.get("access_token") or "").strip()
    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="HubSpot access token is missing",
        )

    supabase.table("memos").update(
        {
            "status": "transcribing",
            "transcript": None,
            "transcript_confidence": None,
            "extraction": None,
            "error_message": None,
            "processed_at": None,
            "processing_started_at": datetime.now(timezone.utc).isoformat(),
        }
    ).eq("id", str(memo_id)).execute()

    asyncio.create_task(
        process_hubspot_call_background(
            str(memo_id), user_id, access_token, call_id, supabase
        )
    )

    updated_result = (
        supabase.table("memos").select("*").eq("id", str(memo_id)).single().execute()
    )
    return _memo_from_row(updated_result.data)

