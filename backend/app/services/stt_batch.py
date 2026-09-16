"""Batch (file) STT router: Deepgram Nova-3, Speechmatics Standard as fallback.

Live copilot stays on Speechmatics WebSocket. HubSpot recordings, uploads,
and WhatsApp go through this module.

Default: Deepgram. If listen fails and a Speechmatics key is set, retry once
with Standard + pinned language + glossary (the bake-off recipe). Sanitize
still runs after STT in the memo pipeline.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Iterable, Optional

from app.config import settings
from app.services.pipeline_meta import record_stage
from app.services.session_entities import (
    EntityTerm,
    normalize_stt_languages,
    resolve_batch_language,
    resolve_profile_stt_languages,
    set_batch_stt_language,
    speechmatics_batch_language,
    stt_first_pass_covers,
)

logger = logging.getLogger(__name__)

_SNIPPET_CHARS = 1800
_DETECT_TIMEOUT_SEC = 8.0


@dataclass(frozen=True)
class BatchTranscript:
    text: str
    confidence: Optional[float] = None
    diarization: str = "speaker"
    channels: int = 1


def wav_channel_count(audio_bytes: bytes) -> int:
    if not audio_bytes or len(audio_bytes) < 24:
        return 1
    if audio_bytes[:4] != b"RIFF" or audio_bytes[8:12] != b"WAVE":
        return 1
    n = int.from_bytes(audio_bytes[22:24], "little")
    return n if n > 0 else 1


def use_channel_stt(audio_bytes: bytes, *, source: str = "") -> bool:
    if (source or "").strip() == "vocify_call":
        return True
    return wav_channel_count(audio_bytes) >= 2

STT_LANGUAGE_LABELS = {
    "es": "Spanish",
    "en": "English",
    "fr": "French",
    "de": "German",
    "it": "Italian",
    "pt": "Portuguese",
    "ca": "Catalan",
}

_DETECT_SYSTEM = (
    "You pick the spoken language of a sales-call ASR transcript. "
    "ASR may have used the wrong language. Reply JSON only."
)


def language_code_from_payload(payload: Any, allowed: list[str]) -> Optional[str]:
    allowed_set = {str(c).strip().lower() for c in allowed}
    if not isinstance(payload, dict) or not allowed_set:
        return None
    raw = payload.get("language") or payload.get("code") or payload.get("lang")
    code = str(raw or "").strip().lower()
    if code in allowed_set:
        return code
    return None


def should_detect_stt_language(first_lang: str, allowed: list[str]) -> bool:
    """Classify only when a selected language is not covered by the first STT pass."""
    allowed = normalize_stt_languages(allowed)
    if len(allowed) <= 1:
        return False
    return any(not stt_first_pass_covers(first_lang, code) for code in allowed)


def should_rerun_stt(first_lang: str, picked: Optional[str], allowed: list[str]) -> bool:
    """Second Deepgram pass only when the pin is allowed and not already covered."""
    if not picked or picked not in allowed:
        return False
    return not stt_first_pass_covers(first_lang, picked)


def _detect_user_prompt(snippet: str, allowed: list[str]) -> str:
    options = ", ".join(
        f"{code} ({STT_LANGUAGE_LABELS.get(code, code)})" for code in allowed
    )
    return (
        f"Allowed languages (pick exactly one): {options}\n"
        "ASR may have used the wrong language. If mixed, pick the dominant one.\n"
        'Reply {"language": "<code>"}.\n\n'
        f"TRANSCRIPT:\n{snippet}\n"
    )


async def detect_audio_language(
    audio_bytes: bytes,
    allowed: list[str],
    *,
    content_type: str = "audio/wav",
    first_lang: str = "",
) -> Optional[str]:
    """Vendor LID on a prefix, restricted to the user's selected languages."""
    allowed = normalize_stt_languages(allowed)
    if len(allowed) <= 1:
        return allowed[0] if allowed else None
    try:
        from app.services.deepgram_batch import DeepgramBatchService

        return await DeepgramBatchService().detect_language(
            audio_bytes,
            content_type=content_type,
            languages=allowed,
            first_lang=first_lang,
        )
    except Exception as e:
        logger.warning("STT audio language detect skipped: %s", e)
        return None


async def detect_stt_language(transcript: str, allowed: list[str]) -> Optional[str]:
    """flash-lite fallback: pick one of the user's selected STT languages."""
    allowed = normalize_stt_languages(allowed)
    if len(allowed) <= 1:
        return allowed[0] if allowed else None
    snippet = (transcript or "").strip()
    if len(snippet) < 40:
        return None
    snippet = snippet[:_SNIPPET_CHARS]
    try:
        from app.services.llm import LLMClient

        model = (
            (getattr(settings, "STT_LANGUAGE_DETECT_MODEL", None) or "").strip()
            or "google/gemini-3.5-flash-lite"
        )
        llm = LLMClient(model=model)
        payload = await llm.chat_json(
            [
                {"role": "system", "content": _DETECT_SYSTEM},
                {"role": "user", "content": _detect_user_prompt(snippet, allowed)},
            ],
            model=model,
            temperature=0.0,
            timeout=_DETECT_TIMEOUT_SEC,
            max_retries=0,
        )
        picked = language_code_from_payload(payload, allowed)
        logger.info("STT language detect (%s) allowed=%s picked=%s", model, allowed, picked)
        return picked
    except Exception as e:
        logger.warning("STT language detect skipped: %s", e)
        return None


async def transcribe_bytes(
    audio_bytes: bytes,
    *,
    content_type: str = "audio/wav",
    language: Optional[str] = None,
    user_id: Optional[str] = None,
    extra_terms: Optional[Iterable[EntityTerm]] = None,
    diarization: bool = True,
    source: str = "",
) -> str:
    result = await transcribe_audio(
        audio_bytes,
        content_type=content_type,
        language=language,
        user_id=user_id,
        extra_terms=extra_terms,
        diarization=diarization,
        source=source,
    )
    return result.text


async def transcribe_audio(
    audio_bytes: bytes,
    *,
    content_type: str = "audio/wav",
    language: Optional[str] = None,
    user_id: Optional[str] = None,
    extra_terms: Optional[Iterable[EntityTerm]] = None,
    diarization: bool = True,
    source: str = "",
) -> BatchTranscript:
    provider = (getattr(settings, "STT_PROVIDER", None) or "deepgram").strip().lower()
    profile_langs = resolve_profile_stt_languages(language, user_id=user_id)
    lang = resolve_batch_language(language, user_id=user_id)
    sm_lang, sm_lang_id = speechmatics_batch_language(profile_langs)
    channel = use_channel_stt(audio_bytes, source=source)
    t0 = time.perf_counter()
    try:
        result = await _transcribe_once(
            audio_bytes,
            content_type=content_type,
            provider=provider,
            lang=lang,
            sm_lang=sm_lang,
            sm_lang_id=sm_lang_id,
            user_id=user_id,
            extra_terms=extra_terms,
            diarization=diarization,
            t0=t0,
            multichannel=channel,
        )
        used_lang = lang if provider != "speechmatics" else sm_lang
        if should_detect_stt_language(used_lang, profile_langs):
            picked = await detect_audio_language(
                audio_bytes,
                profile_langs,
                content_type=content_type,
                first_lang=used_lang,
            )
            if should_rerun_stt(used_lang, picked, profile_langs) and picked:
                logger.info(
                    "STT re-pin %s → %s after language detect",
                    used_lang,
                    picked,
                )
                result = await _transcribe_once(
                    audio_bytes,
                    content_type=content_type,
                    provider=provider,
                    lang=picked,
                    sm_lang=picked,
                    sm_lang_id=None,
                    user_id=user_id,
                    extra_terms=extra_terms,
                    diarization=diarization,
                    t0=time.perf_counter(),
                    multichannel=channel,
                )
                used_lang = picked
        set_batch_stt_language(used_lang)
        return result
    except Exception as e:
        if channel:
            logger.warning("Channel STT failed, falling back to speaker: %s", e)
            try:
                result = await _transcribe_once(
                    audio_bytes,
                    content_type=content_type,
                    provider=provider,
                    lang=lang,
                    sm_lang=sm_lang,
                    sm_lang_id=sm_lang_id,
                    user_id=user_id,
                    extra_terms=extra_terms,
                    diarization=True,
                    t0=time.perf_counter(),
                    multichannel=False,
                )
                set_batch_stt_language(lang if provider != "speechmatics" else sm_lang)
                return result
            except Exception:
                pass
        record_stage(
            "stt",
            t0,
            provider=provider,
            language=lang,
            error=str(e)[:500],
        )
        raise


def _speechmatics_key_set() -> bool:
    return bool((getattr(settings, "SPEECHMATICS_API_KEY", None) or "").strip())


def _should_fallback_to_speechmatics(error: Exception) -> bool:
    msg = str(error or "").strip().lower()
    if "no audio bytes" in msg:
        return False
    return _speechmatics_key_set()


async def _transcribe_speechmatics(
    audio_bytes: bytes,
    *,
    content_type: str,
    sm_lang: str,
    sm_lang_id: Optional[dict],
    user_id: Optional[str],
    extra_terms: Optional[Iterable[EntityTerm]],
    diarization: bool,
    t0: float,
    fallback_from: Optional[str] = None,
    multichannel: bool = False,
) -> BatchTranscript:
    from app.services.speechmatics_batch import BATCH_OPERATING_POINT, SpeechmaticsBatchService
    from app.services.session_entities import format_terms_for_speechmatics

    extra_vocab = format_terms_for_speechmatics(extra_terms or [])
    text = await SpeechmaticsBatchService().transcribe(
        audio_bytes=audio_bytes,
        content_type=content_type,
        language=sm_lang,
        language_identification_config=sm_lang_id,
        user_id=user_id,
        diarization=diarization,
        extra_vocab=extra_vocab,
        channel=multichannel,
    )
    record_stage(
        "stt",
        t0,
        provider="speechmatics",
        model=BATCH_OPERATING_POINT,
        language=sm_lang,
        expected_languages=(sm_lang_id or {}).get("expected_languages"),
        fallback_from=fallback_from,
    )
    return BatchTranscript(
        text=text,
        diarization="channel" if multichannel else ("speaker" if diarization else "none"),
        channels=2 if multichannel else 1,
    )


async def _transcribe_once(
    audio_bytes: bytes,
    *,
    content_type: str,
    provider: str,
    lang: str,
    sm_lang: str,
    sm_lang_id: Optional[dict],
    user_id: Optional[str],
    extra_terms: Optional[Iterable[EntityTerm]],
    diarization: bool,
    t0: float,
    multichannel: bool = False,
) -> BatchTranscript:
    if provider == "speechmatics":
        return await _transcribe_speechmatics(
            audio_bytes,
            content_type=content_type,
            sm_lang=sm_lang,
            sm_lang_id=sm_lang_id,
            user_id=user_id,
            extra_terms=extra_terms,
            diarization=diarization,
            t0=t0,
            multichannel=multichannel,
        )

    from app.services.deepgram_batch import DEEPGRAM_MODEL, DeepgramBatchService

    try:
        text, confidence = await DeepgramBatchService().transcribe(
            audio_bytes=audio_bytes,
            content_type=content_type,
            language=lang,
            user_id=user_id,
            extra_terms=extra_terms,
            diarization=diarization,
            multichannel=multichannel,
        )
    except Exception as e:
        if not _should_fallback_to_speechmatics(e):
            raise
        logger.warning(
            "Deepgram listen failed; falling back to Speechmatics Standard: %s",
            e,
        )
        record_stage(
            "stt",
            t0,
            provider="deepgram",
            model=DEEPGRAM_MODEL,
            language=lang,
            error=str(e)[:500],
            fallback="speechmatics",
        )
        return await _transcribe_speechmatics(
            audio_bytes,
            content_type=content_type,
            sm_lang=sm_lang,
            sm_lang_id=sm_lang_id,
            user_id=user_id,
            extra_terms=extra_terms,
            diarization=diarization,
            t0=time.perf_counter(),
            fallback_from="deepgram",
            multichannel=multichannel,
        )

    record_stage(
        "stt",
        t0,
        provider="deepgram",
        model=DEEPGRAM_MODEL,
        language=lang,
    )
    return BatchTranscript(
        text=text,
        confidence=confidence,
        diarization="channel" if multichannel else ("speaker" if diarization else "none"),
        channels=2 if multichannel else 1,
    )
