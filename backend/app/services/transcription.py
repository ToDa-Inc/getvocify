"""
Transcription service (Deepgram batch - disabled when DEEPGRAM_API_KEY not set).
Real-time uses Speechmatics only.
"""

import asyncio
from app.config import settings
from app.models.memo import TranscriptionResult
from typing import Optional


class TranscriptionService:
    """Service for transcribing audio using Deepgram (batch). Disabled when DEEPGRAM_API_KEY is not set."""
    
    def __init__(self):
        self.client = None
        if settings.DEEPGRAM_API_KEY:
            from deepgram import DeepgramClient
            self.client = DeepgramClient(api_key=settings.DEEPGRAM_API_KEY)
    
    async def transcribe(
        self,
        audio_bytes: bytes,
        mime_type: str = "audio/webm"
    ) -> TranscriptionResult:
        """
        Transcribe audio file using Deepgram Nova-2 model.
        Raises if Deepgram is disabled (DEEPGRAM_API_KEY not set).
        """
        if not self.client:
            raise Exception(
                "Deepgram is disabled. Use recording with real-time transcription (Speechmatics) "
                "or provide transcript when creating the memo."
            )
        try:
            # Transcribe using the new v5.x API
            # model="nova-2" is valid for MediaTranscribeRequestModel
            response = self.client.listen.v1.media.transcribe_file(
                request=audio_bytes,
                model="nova-2",
                language="en",
                punctuate=True,
                paragraphs=True,
                diarize=False,
                smart_format=True,
            )
            
            # Extract results from the response
            if not response.results:
                raise Exception("No transcription results returned")
            
            result = response.results.channels[0].alternatives[0]
            
            transcript = result.transcript or ""
            confidence = result.confidence or 0.0
            duration = response.metadata.duration or 0.0
            
            return TranscriptionResult(
                transcript=transcript,
                confidence=confidence,
                duration=duration
            )
            
        except Exception as e:
            raise Exception(f"Transcription failed: {str(e)}")


