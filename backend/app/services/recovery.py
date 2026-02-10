"""
Recovery service for stuck memo processing tasks.

Handles recovery of memos that got stuck in processing states
due to server restarts or crashes.
"""

from datetime import datetime, timedelta
from supabase import Client
from typing import List
from app.services.transcription import TranscriptionService
from app.services.extraction import ExtractionService
from app.services.crm_config import CRMConfigurationService


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
        
        # Determine recovery action based on status
        if status == "transcribing":
            # Re-queue full processing pipeline
            if not audio_url:
                # No audio URL, mark as failed
                self.supabase.table("memos").update({
                    "status": "failed",
                    "error_message": "Audio URL missing for recovery",
                    "processing_started_at": None,
                }).eq("id", memo_id).execute()
                return False
            
            # Re-queue transcription + extraction
            from app.api.memos import process_memo_async
            from app.services.transcription import TranscriptionService
            from app.services.extraction import ExtractionService
            import asyncio
            
            # Get user's CRM config for field specs
            user_id = memo_data.get("user_id")
            config_service = CRMConfigurationService(self.supabase)
            config = await config_service.get_configuration(user_id)
            allowed_fields = config.allowed_deal_fields if config else None
            
            field_specs = None
            if allowed_fields:
                try:
                    from app.api.memos import get_hubspot_client_from_connection
                    client, connection_id = get_hubspot_client_from_connection(user_id, self.supabase)
                    from app.services.hubspot import HubSpotSchemaService
                    schema_service = HubSpotSchemaService(client, self.supabase, connection_id)
                    field_specs = await schema_service.get_curated_field_specs("deals", allowed_fields)
                except Exception:
                    field_specs = None
            
            transcription_service = TranscriptionService()
            extraction_service = ExtractionService()
            
            asyncio.create_task(
                process_memo_async(
                    memo_id,
                    audio_url,
                    self.supabase,
                    transcription_service,
                    extraction_service,
                    field_specs
                )
            )
            return True
            
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
            
            # Re-queue extraction
            from app.api.memos import extract_memo_async
            from app.services.extraction import ExtractionService
            import asyncio
            
            # Get user's CRM config for field specs
            user_id = memo_data.get("user_id")
            config_service = CRMConfigurationService(self.supabase)
            config = await config_service.get_configuration(user_id)
            allowed_fields = config.allowed_deal_fields if config else None
            
            field_specs = None
            if allowed_fields:
                try:
                    from app.api.memos import get_hubspot_client_from_connection
                    client, connection_id = get_hubspot_client_from_connection(user_id, self.supabase)
                    from app.services.hubspot import HubSpotSchemaService
                    schema_service = HubSpotSchemaService(client, self.supabase, connection_id)
                    field_specs = await schema_service.get_curated_field_specs("deals", allowed_fields)
                except Exception:
                    field_specs = None
            
            extraction_service = ExtractionService()
            
            asyncio.create_task(
                extract_memo_async(
                    memo_id,
                    transcript,
                    self.supabase,
                    extraction_service,
                    field_specs
                )
            )
            return True
        
        return False
    
    async def recover_all_stuck_memos(self) -> dict:
        """
        Recover all stuck memos.
        
        Returns:
            Dictionary with recovery statistics
        """
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
