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
# Bake-off on a ~207s Spanish sales call: Standard + pinned language + vocab
# ~8s and same entity recall as Enhanced (~10s). Enhanced + language=auto was ~114s.
BATCH_OPERATING_POINT = "standard"


def _filename_for_content_type(content_type: Optional[str]) -> tuple[str, str]:
    ct = (content_type or "").lower()
    if "wav" in ct:
        return "wav", "audio/wav"
    if "mpeg" in ct or "mp3" in ct:
        return "mp3", "audio/mpeg"
    if "ogg" in ct or "opus" in ct:
        return "ogg", "audio/ogg"
    return "webm", "audio/webm"


def batch_transcription_config(
    *,
    language: str,
    diarization: bool,
    vocab: Optional[list] = None,
) -> dict:
    """Batch v2 job: Standard + pinned language + glossary. Not Enhanced, not bare auto."""
    transcription_config: dict = {
        "language": language,
        "operating_point": BATCH_OPERATING_POINT,
    }
    if diarization:
        transcription_config["diarization"] = "speaker"
        transcription_config["speaker_diarization_config"] = {
            "prefer_current_speaker": True,
            "speaker_sensitivity": 0.4,
        }
    if vocab:
        transcription_config["additional_vocab"] = vocab
    return transcription_config


def _speechmatics_job_error(status_code: int, body: str) -> str:
    try:
        data = json.loads(body or "")
        detail = data.get("detail") or data.get("error")
        if detail:
            return f"Speechmatics rejected the job: {detail}"
    except Exception:
        pass
    return f"Speechmatics job create failed ({status_code})"


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
        diarization: bool = False,
        notification_url: Optional[str] = None,
        extra_vocab: Optional[list] = None,
        language_identification_config: Optional[dict] = None,
    ) -> str:
        """
        Create a Speechmatics transcription job and return the job_id.

        - audio_bytes: upload directly (preferred — avoids fetch failures).
        - audio_url: let Speechmatics fetch from URL.
        - diarization: enable speaker diarization (S1/S2 labels in transcript).
        - notification_url: if set, Speechmatics POSTs the transcript here on
          completion — no polling needed. Omit to use the poll-based flow.
        """
        vocab = extra_vocab
        if vocab is None and user_id:
            from app.services.session_entities import speechmatics_vocab_for_job

            vocab = await speechmatics_vocab_for_job(user_id)
        if vocab:
            logger.info(
                "Speechmatics batch: injected %d vocab terms",
                len(vocab),
                extra=log_domain(DOMAIN_TRANSCRIPTION, "glossary_injected", user_id=user_id, term_count=len(vocab)),
            )

        transcription_config = batch_transcription_config(
            language=language,
            diarization=diarization,
            vocab=vocab,
        )

        config: dict = {"type": "transcription", "transcription_config": transcription_config}
        if language_identification_config:
            config["language_identification_config"] = language_identification_config
        if notification_url:
            config["notification_config"] = [{"url": notification_url, "contents": ["transcript"]}]
        if audio_url:
            config["fetch_data"] = {"url": audio_url}

        if audio_bytes is not None:
            files = {
                "config": (None, json.dumps(config), "application/json"),
                "data_file": (filename, io.BytesIO(audio_bytes), content_type),
            }
        elif audio_url:
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
                diarization=diarization,
                operating_point=transcription_config.get("operating_point"),
                notification=bool(notification_url),
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
                raise RuntimeError(_speechmatics_job_error(resp.status_code, err_body))
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

    def _job_kwargs(
        self,
        audio_bytes: Optional[bytes],
        audio_url: Optional[str],
        content_type: Optional[str],
        language: str,
        user_id: Optional[str],
        diarization: bool = False,
        notification_url: Optional[str] = None,
        extra_vocab: Optional[list] = None,
        language_identification_config: Optional[dict] = None,
    ) -> dict:
        """Build kwargs for create_job from the common transcribe/submit params."""
        if audio_bytes is not None:
            ext, default_ct = _filename_for_content_type(content_type)
            return dict(
                audio_bytes=audio_bytes,
                filename=f"audio.{ext}",
                content_type=content_type or default_ct,
                language=language,
                user_id=user_id,
                diarization=diarization,
                notification_url=notification_url,
                extra_vocab=extra_vocab,
                language_identification_config=language_identification_config,
            )
        elif audio_url:
            return dict(
                audio_url=audio_url,
                language=language,
                user_id=user_id,
                diarization=diarization,
                notification_url=notification_url,
                extra_vocab=extra_vocab,
                language_identification_config=language_identification_config,
            )
        raise ValueError("Either audio_bytes or audio_url required")

    async def submit(
        self,
        audio_url: Optional[str] = None,
        audio_bytes: Optional[bytes] = None,
        content_type: Optional[str] = None,
        language: str = "es",
        user_id: Optional[str] = None,
        diarization: bool = False,
        notification_url: Optional[str] = None,
        extra_vocab: Optional[list] = None,
        language_identification_config: Optional[dict] = None,
    ) -> str:
        """
        Create a job and return the job_id immediately.
        If notification_url is set, Speechmatics will POST the result there — no polling needed.
        If not set, use get_transcript(job_id) after polling get_job_status().
        """
        kwargs = self._job_kwargs(
            audio_bytes,
            audio_url,
            content_type,
            language,
            user_id,
            diarization,
            notification_url,
            extra_vocab,
            language_identification_config,
        )
        return await self.create_job(**kwargs)

    async def transcribe(
        self,
        audio_url: Optional[str] = None,
        audio_bytes: Optional[bytes] = None,
        content_type: Optional[str] = None,
        language: str = "es",
        user_id: Optional[str] = None,
        diarization: bool = False,
        extra_vocab: Optional[list] = None,
        language_identification_config: Optional[dict] = None,
    ) -> str:
        """
        Create job, poll until done, return transcript text.
        Use this for non-webhook flows (WhatsApp, voice memos, etc.).
        For HubSpot calls, prefer submit() + notification_url for push-based completion.
        """
        kwargs = self._job_kwargs(
            audio_bytes,
            audio_url,
            content_type,
            language,
            user_id,
            diarization,
            extra_vocab=extra_vocab,
            language_identification_config=language_identification_config,
        )
        job_id = await self.create_job(**kwargs)

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
