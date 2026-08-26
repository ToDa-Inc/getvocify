"""
Supabase Storage service for audio file management
"""

import uuid
from datetime import datetime, timedelta
from supabase import Client
from app.config import settings
from typing import BinaryIO, Optional

# Private, unlike BUCKET_NAME ('voice-memos'). Call audio is personal data:
# HubSpot playback goes through short-lived signed URLs, never a public URL.
CALL_RECORDINGS_BUCKET = "call-recordings"


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

    async def upload_call_recording(
        self,
        audio_bytes: bytes,
        user_id: str,
        call_sid: str,
    ) -> str:
        """Store a call recording and return its storage path (not a URL)."""
        path = f"{user_id}/{call_sid}.wav"
        self.supabase.storage.from_(CALL_RECORDINGS_BUCKET).upload(
            path=path,
            file=audio_bytes,
            file_options={"content-type": "audio/wav", "upsert": "true"},
        )
        return path

    def signed_call_recording_url(self, path: str, expires_in: int = 3600) -> str:
        """Time-limited URL. Supabase Storage honours Range and returns 206,
        which HubSpot's player requires for seeking."""
        res = self.supabase.storage.from_(CALL_RECORDINGS_BUCKET).create_signed_url(
            path, expires_in
        )
        # supabase-py has used both spellings across versions.
        url = None
        if isinstance(res, dict):
            url = res.get("signedURL") or res.get("signedUrl") or res.get("signed_url")
        if not url:
            raise RuntimeError(f"could not sign recording URL for {path}")
        return str(url)


