"""
Deepgram transcription service
"""

import asyncio
from deepgram import DeepgramClient, PrerecordedOptions, FileSource
from app.config import settings
from app.models.memo import TranscriptionResult
from typing import Optional


class TranscriptionService:
    """Service for transcribing audio using Deepgram"""
    
    def __init__(self):
        self.client = DeepgramClient(settings.DEEPGRAM_API_KEY)
    
    async def transcribe(
        self,
        audio_bytes: bytes,
        mime_type: str = "audio/webm"
    ) -> TranscriptionResult:
        """
        Transcribe audio file using Deepgram Nova-2 model
        
        Args:
            audio_bytes: Audio file bytes
            mime_type: MIME type of the audio file
            
        Returns:
            TranscriptionResult with transcript, confidence, and duration
        """
        try:
            # Create file source
            payload: FileSource = {
                "buffer": audio_bytes,
            }
            
            # Configure options for best accuracy
            options = PrerecordedOptions(
                model="nova-2",
                language="en",
                punctuate=True,
                paragraphs=True,
                diarize=False,  # Speaker diarization (optional)
                smart_format=True,
            )
            
            # Transcribe
            response = self.client.listen.rest.v("1").transcribe_file(
                payload,
                options
            )
            
            # Extract results
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


