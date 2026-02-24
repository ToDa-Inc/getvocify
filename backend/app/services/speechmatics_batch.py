"""
Speechmatics Batch Transcription API.
For file-based (non-realtime) audio transcription.
"""

import asyncio
import io
import json
import logging
import time
from typing import Optional

import httpx

from app.config import settings
from app.logging_config import log_domain, DOMAIN_TRANSCRIPTION
from app.metrics import record_transcription_duration

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

    def _auth_headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}"}

    async def create_job(
        self,
        *,
        audio_url: Optional[str] = None,
        audio_bytes: Optional[bytes] = None,
        filename: str = "audio.ogg",
        content_type: str = "audio/ogg",
        language: str = "es",
        user_id: Optional[str] = None,
    ) -> str:
        """
        Create a transcription job.
        Pass audio_bytes to upload file directly (recommended, avoids fetch failures).
        Or pass audio_url for Speechmatics to fetch from URL.
        API expects multipart/form-data with config and optional data_file.
        When user_id is provided, fetches user glossary and adds additional_vocab for custom vocabulary.
        """
        transcription_config: dict = {
            "language": language,
            "operating_point": "enhanced",
        }
        if user_id:
            from app.services.glossary import GlossaryService
            glossary_svc = GlossaryService()
            glossary = await glossary_svc.get_user_glossary(user_id)
            if glossary:
                transcription_config["additional_vocab"] = glossary_svc.format_for_speechmatics(glossary)
                logger.info(
                    "Speechmatics batch: injected %d glossary terms",
                    len(glossary),
                    extra=log_domain(DOMAIN_TRANSCRIPTION, "glossary_injected", user_id=user_id, term_count=len(glossary)),
                )
        if audio_bytes is not None:
            config = {
                "type": "transcription",
                "transcription_config": transcription_config,
            }
            files = {
                "config": (None, json.dumps(config), "application/json"),
                "data_file": (filename, io.BytesIO(audio_bytes), content_type),
            }
        elif audio_url:
            config = {
                "type": "transcription",
                "transcription_config": transcription_config,
                "fetch_data": {"url": audio_url},
            }
            files = {"config": (None, json.dumps(config), "application/json")}
        else:
            raise ValueError("Either audio_bytes or audio_url required")

        logger.info(
            "🎙️ Speechmatics job create",
            extra=log_domain(
                DOMAIN_TRANSCRIPTION,
                "job_create",
                has_bytes=audio_bytes is not None,
                has_url=audio_url is not None,
                audio_filename=filename,
                content_type=content_type,
                language=language,
                audio_len_bytes=len(audio_bytes) if audio_bytes else None,
            ),
        )
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{self.base_url}/jobs",
                headers=self._auth_headers(),
                files=files,
            )
            if resp.status_code >= 400:
                err_body = resp.text[:500] if resp.text else ""
                logger.error(
                    "❌ Speechmatics create_job failed",
                    extra=log_domain(DOMAIN_TRANSCRIPTION, "job_create_failed", status=resp.status_code, error=err_body),
                )
            resp.raise_for_status()
            data = resp.json()
            job_id = data.get("id") or (data.get("job", {}) or {}).get("id")
            logger.info(
                "✅ Speechmatics job created",
                extra=log_domain(DOMAIN_TRANSCRIPTION, "job_created", job_id=job_id),
            )
            if not job_id:
                logger.error("Speechmatics create_job unexpected response: %s", data)
                raise ValueError(f"Speechmatics response missing job id: {list(data.keys())}")
            return job_id

    async def get_job_status(self, job_id: str) -> str:
        """Get job status: done, running, rejected, etc."""
        job = await self._get_job(job_id)
        return job.get("status", "unknown")

    async def _get_job(self, job_id: str) -> dict:
        """Fetch full job details. V2 API may return {"job": {...}} or {...}."""
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{self.base_url}/jobs/{job_id}",
                headers=self._auth_headers(),
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("job", data)

    async def get_transcript(self, job_id: str) -> str:
        """
        Get transcript text from completed job.
        Raises if job not done or transcript format unexpected.
        """
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{self.base_url}/jobs/{job_id}/transcript",
                params={"format": "txt"},
                headers=self._auth_headers(),
            )
            resp.raise_for_status()
            return resp.text

    async def transcribe(
        self,
        audio_url: Optional[str] = None,
        audio_bytes: Optional[bytes] = None,
        content_type: Optional[str] = None,
        language: str = "es",
        user_id: Optional[str] = None,
    ) -> str:
        """
        Create job, poll until done, return transcript.
        Prefer audio_bytes (no URL fetch). Fall back to audio_url for fetch_data.
        Pass user_id to inject user glossary (additional_vocab) for custom vocabulary.
        """
        if audio_bytes is not None:
            ext = "ogg" if "ogg" in (content_type or "") or "opus" in (content_type or "") else "webm"
            ct = content_type or "audio/ogg"
            job_id = await self.create_job(
                audio_bytes=audio_bytes,
                filename=f"audio.{ext}",
                content_type=ct,
                language=language,
                user_id=user_id,
            )
        elif audio_url:
            job_id = await self.create_job(audio_url=audio_url, language=language, user_id=user_id)
        else:
            raise ValueError("Either audio_bytes or audio_url required")

        _transcribe_start = time.perf_counter()
        poll_count = 0
        for _ in range(MAX_POLL_ATTEMPTS):
            poll_count += 1
            status = await self.get_job_status(job_id)
            if status == "done":
                logger.info(
                    "✅ Speechmatics transcript ready",
                    extra=log_domain(DOMAIN_TRANSCRIPTION, "transcript_ready", job_id=job_id, poll_count=poll_count),
                )
                t0 = time.perf_counter()
                transcript = await self.get_transcript(job_id)
                total_elapsed = time.perf_counter() - _transcribe_start
                record_transcription_duration(total_elapsed, "whatsapp")
                elapsed_ms = (time.perf_counter() - t0) * 1000
                logger.info(
                    "✅ Speechmatics transcribe complete",
                    extra=log_domain(
                        DOMAIN_TRANSCRIPTION,
                        "transcribe_complete",
                        job_id=job_id,
                        transcript_len=len(transcript),
                        poll_count=poll_count,
                        fetch_ms=round(elapsed_ms, 2),
                    ),
                )
                return transcript
            if status == "rejected":
                job = await self._get_job(job_id)
                errors = job.get("errors", [])
                msgs = [e.get("message", str(e)) for e in errors] if errors else ["unknown"]
                err_detail = "; ".join(msgs[:3])
                logger.error(
                    "❌ Speechmatics job rejected",
                    extra=log_domain(DOMAIN_TRANSCRIPTION, "job_rejected", job_id=job_id, errors=err_detail, poll_count=poll_count),
                )
                raise Exception(f"Speechmatics job rejected: {err_detail}")
            if poll_count <= 2 or poll_count % 10 == 0:
                logger.debug(
                    "Speechmatics polling",
                    extra=log_domain(DOMAIN_TRANSCRIPTION, "polling", job_id=job_id, poll_count=poll_count, status=status),
                )
            await asyncio.sleep(POLL_INTERVAL_SEC)

        logger.error(
            "❌ Speechmatics job timed out",
            extra=log_domain(DOMAIN_TRANSCRIPTION, "job_timeout", job_id=job_id, poll_count=poll_count),
        )
        raise Exception(f"Speechmatics job timed out: {job_id}")
