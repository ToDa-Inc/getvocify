"""Batch (file) STT router: Deepgram Nova-3 or Speechmatics.

Live copilot stays on Speechmatics WebSocket. HubSpot recordings, uploads,
and WhatsApp go through this module.
"""

from __future__ import annotations

import time
from typing import Iterable, Optional

from app.config import settings
from app.services.pipeline_meta import record_stage
from app.services.session_entities import EntityTerm, resolve_batch_language


async def transcribe_bytes(
    audio_bytes: bytes,
    *,
    content_type: str = "audio/wav",
    language: Optional[str] = None,
    user_id: Optional[str] = None,
    extra_terms: Optional[Iterable[EntityTerm]] = None,
    diarization: bool = True,
) -> str:
    provider = (getattr(settings, "STT_PROVIDER", None) or "deepgram").strip().lower()
    lang = resolve_batch_language(language, user_id=user_id)
    t0 = time.perf_counter()
    try:
        if provider == "speechmatics":
            from app.services.speechmatics_batch import SpeechmaticsBatchService
            from app.services.session_entities import format_terms_for_speechmatics

            extra_vocab = format_terms_for_speechmatics(extra_terms or [])
            sm_lang = lang if lang != "multi" else "es"
            text = await SpeechmaticsBatchService().transcribe(
                audio_bytes=audio_bytes,
                content_type=content_type,
                language=sm_lang,
                user_id=user_id,
                diarization=diarization,
                extra_vocab=extra_vocab,
            )
            record_stage(
                "stt",
                t0,
                provider="speechmatics",
                model="batch",
                language=sm_lang,
            )
            return text

        from app.services.deepgram_batch import DEEPGRAM_MODEL, DeepgramBatchService

        text = await DeepgramBatchService().transcribe(
            audio_bytes=audio_bytes,
            content_type=content_type,
            language=lang,
            user_id=user_id,
            extra_terms=extra_terms,
            diarization=diarization,
        )
        record_stage(
            "stt",
            t0,
            provider="deepgram",
            model=DEEPGRAM_MODEL,
            language=lang,
        )
        return text
    except Exception as e:
        record_stage(
            "stt",
            t0,
            provider=provider,
            language=lang,
            error=str(e)[:500],
        )
        raise
