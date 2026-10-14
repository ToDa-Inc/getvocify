"""
Recovery service for stuck memo processing tasks.

Handles recovery of memos that got stuck in processing states
due to server restarts or crashes.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from supabase import Client
from typing import List, Tuple

from app.services.extraction import ExtractionService
from app.logging_config import log_domain, DOMAIN_RECOVERY
logger = logging.getLogger(__name__)

AUDIO_NOT_STORED = "Processing interrupted. Audio is not stored. Please record again."
RECORDING_KEEPS_FAILING = (
    "Transcription was interrupted again. The call recording is kept: use Re-transcribe to try once more."
)

# Re-transcription tasks started by recovery, held so they are not garbage-collected mid-run.
_background: set = set()


class RecoveryService:
    """Service for recovering stuck memo processing tasks"""
    
    STUCK_THRESHOLD_MINUTES = 5  # Consider stuck if processing > 5 minutes
    # A call whose stored recording is re-transcribed this many times without finishing is failed instead.
    MAX_RECORDING_RECOVERIES = 2
    
    def __init__(self, supabase: Client):
        self.supabase = supabase

    def _update(self, memo_id: str, fields: dict) -> None:
        self.supabase.table("memos").update(fields).eq("id", memo_id).execute()

    async def _fail(self, memo_id: str, message: str) -> None:
        await asyncio.to_thread(
            self._update,
            memo_id,
            {"status": "failed", "error_message": message, "processing_started_at": None},
        )
    
    async def find_stuck_memos(self) -> List[dict]:
        """
        Find memos that are stuck in processing states.
        
        Returns:
            List of memo records that need recovery
        """
        threshold = datetime.utcnow() - timedelta(minutes=self.STUCK_THRESHOLD_MINUTES)
        threshold_iso = threshold.isoformat()
        
        # Find memos stuck in transcribing or extracting
        result = await asyncio.to_thread(
            lambda: self.supabase.table("memos").select("*").in_(
                "status", ["transcribing", "extracting"]
            ).not_.is_("processing_started_at", "null").lt(
                "processing_started_at", threshold_iso
            ).execute()
        )
        
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
        memo_result = await asyncio.to_thread(
            lambda: self.supabase.table("memos").select("*").eq("id", memo_id).single().execute()
        )
        
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
            source = (memo_data.get("source") or memo_data.get("source_type") or "").strip()
            if source == "vocify_call":
                return await self._retranscribe_call_recording(memo_data)
            # Voice memos are transcribed in memory: after a crash their audio is gone.
            await self._fail(memo_id, AUDIO_NOT_STORED)
            return False
            
        elif status == "extracting":
            # Re-queue extraction only
            if not transcript:
                # No transcript, mark as failed
                await self._fail(memo_id, "Transcript missing for extraction recovery")
                return False
            
            # Re-queue extraction with the same multi-object field specs as live extract.
            # extract_memo_async acquires the lease; a live run is skipped, not stacked.
            from app.api.memos import _call_date_from_memo, _curated_field_specs_for_primary_crm, extract_memo_async
            from app.services.extraction import ExtractionService
            
            user_id = memo_data.get("user_id")
            field_specs = None
            try:
                field_specs = await _curated_field_specs_for_primary_crm(self.supabase, user_id)
            except Exception:
                field_specs = None
            
            extraction_service = ExtractionService()
            source_type = memo_data.get("source_type") or memo_data.get("source") or "voice_memo"
            if source_type == "recall_bot":  # T14: a bot-recorded meeting, same as a manual meeting_transcript
                source_type = "meeting_transcript"
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
                await self._fail(memo_id, "Transcript missing for legacy pending_transcript recovery")
                return False

            from app.api.memos import start_extraction_from_transcript

            user_id = memo_data.get("user_id")
            source_type = memo_data.get("source_type") or memo_data.get("source") or "voice_memo"
            if source_type == "recall_bot":  # T14: a bot-recorded meeting, same as a manual meeting_transcript
                source_type = "meeting_transcript"
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

    def _load_call_recording(self, memo_id: str, path: str) -> Tuple[bytes, dict]:
        """The call's WAV from storage, and its outbound_calls row (sid, duration) when there is one."""
        from app.services.storage import StorageService

        audio = StorageService(self.supabase).download_call_recording(path)
        found = (
            self.supabase.table("outbound_calls")
            .select("carrier_call_id,recording_duration")
            .eq("memo_id", memo_id)
            .limit(1)
            .execute()
        )
        return audio, (found.data or [None])[0] or {}

    async def _retranscribe_call_recording(self, memo: dict) -> bool:
        """A Vocify call interrupted mid-transcription: its recording is stored, so transcribe it again.

        Each attempt is counted in pipeline_meta.recovery_attempts, so a recording that keeps breaking
        the pipeline is failed (and left for Re-transcribe) instead of retried forever.
        """
        from app.services.memo_playback import recording_path_for_memo
        from app.services.telephony.call_processor import is_transcribing, process_vocify_call_background

        memo_id = str(memo["id"])
        if is_transcribing(memo_id):
            return True  # a long call still being transcribed by this process, not a stuck one

        path = await asyncio.to_thread(recording_path_for_memo, memo, self.supabase)
        if not path:
            await self._fail(memo_id, AUDIO_NOT_STORED)
            return False

        meta = memo.get("pipeline_meta") if isinstance(memo.get("pipeline_meta"), dict) else {}
        attempts = int(meta.get("recovery_attempts") or 0)
        if attempts >= self.MAX_RECORDING_RECOVERIES:
            logger.warning(
                "Recover memo: call recording re-transcribed %s times without finishing; failing it",
                attempts,
                extra=log_domain(DOMAIN_RECOVERY, "recover_memo", memo_id=memo_id, from_status="transcribing", to_status="failed"),
            )
            await self._fail(memo_id, RECORDING_KEEPS_FAILING)
            return False

        # Counted before anything can fail, and the stuck clock restarts: the next sweep looks again
        # only if this attempt is lost too.
        await asyncio.to_thread(
            self._update,
            memo_id,
            {
                "processing_started_at": datetime.now(timezone.utc).isoformat(),
                "pipeline_meta": {**meta, "recovery_attempts": attempts + 1},
            },
        )
        try:
            audio, call = await asyncio.to_thread(self._load_call_recording, memo_id, path)
        except Exception:
            # Left transcribing: the next sweep tries again while attempts remain.
            logger.warning(
                "Recover memo: could not load call recording %s",
                path,
                exc_info=True,
                extra=log_domain(DOMAIN_RECOVERY, "recover_memo", memo_id=memo_id, from_status="transcribing"),
            )
            return False

        call_sid = str(call.get("carrier_call_id") or "recovery")
        duration = float(call.get("recording_duration") or memo.get("audio_duration") or 1.0)
        task = asyncio.create_task(
            process_vocify_call_background(memo_id, memo["user_id"], call_sid, audio, duration, self.supabase)
        )
        _background.add(task)
        task.add_done_callback(_background.discard)
        logger.warning(
            "🔄 Recover memo: re-transcribing the stored call recording (attempt %s)",
            attempts + 1,
            extra=log_domain(DOMAIN_RECOVERY, "recover_memo", memo_id=memo_id, from_status="transcribing", to_status="transcribing"),
        )
        return True
    
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
