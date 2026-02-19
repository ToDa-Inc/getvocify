"""
Supabase Storage service for audio file management
"""

import uuid
from datetime import datetime, timedelta
from supabase import Client
from app.config import settings
from typing import BinaryIO, Optional


class StorageService:
    """Service for managing audio files in Supabase Storage"""
    
    BUCKET_NAME = "voice-memos"
    
    def __init__(self, supabase: Client):
        self.supabase = supabase
    
    _EXTENSION_BY_MIME: dict = {
        "audio/webm": "webm",
        "audio/ogg": "ogg",
        "audio/opus": "ogg",
        "audio/mpeg": "mp3",
        "audio/mp4": "m4a",
        "audio/wav": "wav",
    }

    async def upload_audio(
        self,
        audio_bytes: bytes,
        user_id: str,
        content_type: str = "audio/webm",
        file_extension: Optional[str] = None,
    ) -> str:
        """
        Upload audio file to Supabase Storage

        Args:
            file_extension: Override extension (e.g. "ogg" for WhatsApp voice notes).
                If None, derived from content_type.
        Returns:
            Public URL of the uploaded file
        """
        ext = file_extension or self._EXTENSION_BY_MIME.get(
            content_type.split(";")[0].strip(), "webm"
        )
        file_id = str(uuid.uuid4())
        filename = f"{user_id}/{file_id}.{ext}"
        
        # Upload to storage
        try:
            self.supabase.storage.from_(self.BUCKET_NAME).upload(
                path=filename,
                file=audio_bytes,
                file_options={
                    "content-type": content_type,
                    "upsert": False
                }
            )
        except Exception as e:
            # If it's already a 400/404/500 from Supabase, it will raise here
            raise Exception(f"Storage upload failed: {str(e)}")
        
        # Get public URL
        url_response = self.supabase.storage.from_(self.BUCKET_NAME).get_public_url(filename)
        
        return str(url_response)
    
    async def delete_audio(self, audio_url: str) -> None:
        """Delete audio file from storage"""
        # Extract path from URL
        # Supabase URLs format: https://{project}.supabase.co/storage/v1/object/public/{bucket}/{path}
        try:
            parts = audio_url.split("/public/")
            if len(parts) < 2:
                return
            
            path = parts[1]
            self.supabase.storage.from_(self.BUCKET_NAME).remove([path])
        except Exception as e:
            # Log error but don't fail
            print(f"Failed to delete audio: {e}")


