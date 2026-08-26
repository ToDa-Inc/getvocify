"""
Recovery service for stuck memo processing tasks.

Handles recovery of memos that got stuck in processing states
due to server restarts or crashes.
"""

import logging
from datetime import datetime, timedelta
from supabase import Client
from typing import List

from app.services.extraction import ExtractionService
from app.logging_config import log_domain, DOMAIN_RECOVERY
logger = logging.getLogger(__name__)


class RecoveryService:
    """Service for recovering stuck memo processing tasks"""
    
    STUCK_THRESHOLD_MINUTES = 5  # Consider stuck if processing > 5 minutes
    
    def __init__(self, supabase: Client):
        self.supabase = supabase
    
    async def find_stuck_memos(self) -> List[dict]:
        """
        Find memos that are stuck in processing states.
        
        Returns:
            List of memo records that need recovery
        """
        threshold = datetime.utcnow() - timedelta(minutes=self.STUCK_THRESHOLD_MINUTES)
        threshold_iso = threshold.isoformat()
        
        # Find memos stuck in transcribing or extracting
        result = self.supabase.table("memos").select("*").in_(
            "status", ["transcribing", "extracting"]
        ).not_.is_("processing_started_at", "null").lt(
            "processing_started_at", threshold_iso
        ).execute()
        
        return result.data or []
    
    async def recover_memo(self, memo_id: str) -> bool:
        """
        Recover a single stuck memo by re-queuing its processing.
        
        Args:
            memo_id: Memo ID to recover
            
        Returns:
            True if recovery was successful, False otherwise
        """
        # Get memo details
        memo_result = self.supabase.table("memos").select("*").eq("id", memo_id).single().execute()
        
        if not memo_result.data:
            return False
        
        memo_data = memo_result.data
        status = memo_data.get("status")
        audio_url = memo_data.get("audio_url")
        transcript = memo_data.get("transcript")
        logger.debug(
            "Recover memo attempt",
            extra=log_domain(DOMAIN_RECOVERY, "recover_memo", memo_id=memo_id, from_status=status),
        )
        # Determine recovery action based on status
        if status == "transcribing":
            # We no longer store audio - cannot recover transcribing memos
            # (audio was processed in-memory and is gone after crash)
            self.supabase.table("memos").update({
                "status": "failed",
                "error_message": "Processing interrupted. Audio is not stored. Please record again.",
                "processing_started_at": None,
            }).eq("id", memo_id).execute()
            return False
            
        elif status == "extracting":
            # Re-queue extraction only
            if not transcript:
                # No transcript, mark as failed
                self.supabase.table("memos").update({
                    "status": "failed",
                    "error_message": "Transcript missing for extraction recovery",
                    "processing_started_at": None,
                }).eq("id", memo_id).execute()
                return False
            
            # Re-queue extraction with the same multi-object field specs as live extract.
            # extract_memo_async acquires the lease; a live run is skipped, not stacked.
            from app.api.memos import _call_date_from_memo, _curated_field_specs_for_primary_crm, extract_memo_async
            from app.services.extraction import ExtractionService
            import asyncio
            
            user_id = memo_data.get("user_id")
            field_specs = None
            try:
                field_specs = await _curated_field_specs_for_primary_crm(self.supabase, user_id)
            except Exception:
                field_specs = None
            
            extraction_service = ExtractionService()
            source_type = memo_data.get("source_type") or memo_data.get("source") or "voice_memo"
            if source_type not in ("voice_memo", "meeting_transcript", "hubspot_call"):
                source_type = "voice_memo"
            
            asyncio.create_task(
                extract_memo_async(
                    memo_id,
                    user_id,
                    transcript,
                    self.supabase,
                    extraction_service,
                    field_specs,
                    source_type=source_type,
                    trigger="recovery",
                    call_date=_call_date_from_memo(memo_data),
                )
            )
            logger.info(
                "🔄 Recover memo: re-queued extraction",
                extra=log_domain(DOMAIN_RECOVERY, "recover_memo", memo_id=memo_id, from_status=status, to_status="extracting"),
            )
            return True

        elif status == "pending_transcript":
            # Legacy rows: transcript ready but never confirmed — auto-extract
            if not transcript:
                self.supabase.table("memos").update({
                    "status": "failed",
                    "error_message": "Transcript missing for legacy pending_transcript recovery",
                    "processing_started_at": None,
                }).eq("id", memo_id).execute()
                return False

            from app.api.memos import start_extraction_from_transcript

            user_id = memo_data.get("user_id")
            source_type = memo_data.get("source_type") or memo_data.get("source") or "voice_memo"
            if source_type not in ("voice_memo", "meeting_transcript", "hubspot_call"):
                source_type = "voice_memo"

            await start_extraction_from_transcript(
                memo_id,
                user_id,
                transcript,
                self.supabase,
                source_type=source_type,
            )
            logger.info(
                "🔄 Recover memo: auto-extracted legacy pending_transcript",
                extra=log_domain(DOMAIN_RECOVERY, "recover_memo", memo_id=memo_id, from_status=status, to_status="extracting"),
            )
            return True
        
        return False
    
    async def recover_all_stuck_memos(self) -> dict:
        """
        Recover all stuck memos.
        
        Returns:
            Dictionary with recovery statistics
        """
        from app.services.pipeline_lease import reap_expired_leases

        reap_expired_leases()
        stuck_memos = await self.find_stuck_memos()
        
        recovered = 0
        failed = 0
        
        for memo in stuck_memos:
            success = await self.recover_memo(memo["id"])
            if success:
                recovered += 1
            else:
                failed += 1
        
        return {
            "found": len(stuck_memos),
            "recovered": recovered,
            "failed": failed,
        }
