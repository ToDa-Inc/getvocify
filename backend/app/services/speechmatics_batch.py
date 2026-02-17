"""
Speechmatics Batch Transcription API.
For file-based (non-realtime) audio transcription.
"""

import asyncio
import json
import logging
from typing import Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

BATCH_BASE_URL = "https://eu1.asr.api.speechmatics.com/v2"
POLL_INTERVAL_SEC = 3
MAX_POLL_ATTEMPTS = 60  # ~3 minutes max wait


class SpeechmaticsBatchService:
    """
    Batch transcription via Speechmatics Jobs API.
    Creates job with fetch_data URL, polls until done, returns transcript text.
    """

    def __init__(self) -> None:
        self.api_key = (
            settings.SPEECHMATICS_API_KEY
            or getattr(settings, "SPEECHMATICS_API_KEY", None)
        )
        self.base_url = BATCH_BASE_URL

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def create_job(self, audio_url: str, language: str = "es") -> str:
        """
        Create a transcription job. Speechmatics will fetch audio from the URL.

        Returns:
            Job ID for polling
        """
        config = {
            "type": "transcription",
            "transcription_config": {
                "language": language,
                "operating_point": "enhanced",
            },
            "fetch_data": {"url": audio_url},
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{self.base_url}/jobs",
                headers=self._headers(),
                json={"config": config},
            )
            resp.raise_for_status()
            data = resp.json()
            return data["job"]["id"]

    async def get_job_status(self, job_id: str) -> str:
        """Get job status: done, running, rejected, etc."""
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{self.base_url}/jobs/{job_id}",
                headers=self._headers(),
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("job", {}).get("status", "unknown")

    async def get_transcript(self, job_id: str) -> str:
        """
        Get transcript text from completed job.
        Raises if job not done or transcript format unexpected.
        """
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{self.base_url}/jobs/{job_id}/transcript",
                params={"format": "txt"},
                headers=self._headers(),
            )
            resp.raise_for_status()
            return resp.text

    async def transcribe(self, audio_url: str, language: str = "es") -> str:
        """
        Create job, poll until done, return transcript.
        Raises on failure or timeout.
        """
        job_id = await self.create_job(audio_url, language)
        logger.info("Speechmatics batch job created: %s", job_id)

        for _ in range(MAX_POLL_ATTEMPTS):
            status = await self.get_job_status(job_id)
            if status == "done":
                return await self.get_transcript(job_id)
            if status == "rejected":
                raise Exception(f"Speechmatics job rejected: {job_id}")
            await asyncio.sleep(POLL_INTERVAL_SEC)

        raise Exception(f"Speechmatics job timed out: {job_id}")
