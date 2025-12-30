"""
Supabase Storage service for audio file management
"""

import uuid
from datetime import datetime, timedelta
from supabase import Client
from app.config import settings
from typing import BinaryIO


class StorageService:
    """Service for managing audio files in Supabase Storage"""
    
    BUCKET_NAME = "voice-memos"
    
    def __init__(self, supabase: Client):
        self.supabase = supabase
    
    async def upload_audio(
        self,
        audio_bytes: bytes,
        user_id: str,
        content_type: str = "audio/webm"
    ) -> str:
        """
        Upload audio file to Supabase Storage
        
        Returns:
            Public URL of the uploaded file
        """
        # Generate unique filename
        file_id = str(uuid.uuid4())
        filename = f"{user_id}/{file_id}.webm"
        
        # Upload to storage
        response = self.supabase.storage.from_(self.BUCKET_NAME).upload(
            path=filename,
            file=audio_bytes,
            file_options={
                "content-type": content_type,
                "upsert": False
            }
        )
        
        if response.error:
            raise Exception(f"Storage upload failed: {response.error}")
        
        # Get public URL
        url_response = self.supabase.storage.from_(self.BUCKET_NAME).get_public_url(filename)
        
        return url_response
    
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


