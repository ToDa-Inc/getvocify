"""Deepgram Nova-3 pre-recorded STT for HubSpot recordings, uploads, and WhatsApp.

Synchronous listen API (no webhook). Pin language, pass glossary as `keyterm`,
and return Speechmatics-style S1/S2 labels from utterances.
"""

from __future__ import annotations

import logging
from typing import Any, Iterable, Optional
from urllib.parse import urlencode

import httpx

from app.config import settings
from app.logging_config import DOMAIN_TRANSCRIPTION, log_domain
from app.services.session_entities import (
    EntityTerm,
    deepgram_keyterms_for_job,
    resolve_batch_language,
)

logger = logging.getLogger(__name__)

LISTEN_URL = "https://api.deepgram.com/v1/listen"


def listen_query_params(
    *,
    model: str,
    language: str,
    keyterms: Iterable[str],
    diarization: bool,
) -> list[tuple[str, str]]:
    """Nova-3 listen query. `diarize` + `utterances` only — `diarize_model` 400s with `diarize`."""
    params: list[tuple[str, str]] = [
        ("model", model),
        ("language", language),
        ("punctuate", "true"),
        ("smart_format", "true"),
    ]
    if diarization:
        params.append(("diarize", "true"))
        params.append(("utterances", "true"))
    for term in keyterms:
        if term:
            params.append(("keyterm", str(term)))
    return params


def format_deepgram_transcript(payload: dict[str, Any]) -> str:
    """Utterances → S1/S2 text. Fall back to the flat transcript."""
    results = payload.get("results") or {}
    utterances = results.get("utterances") or []
    if utterances:
        lines: list[str] = []
        for utt in utterances:
            text = str(utt.get("transcript") or "").strip()
            if not text:
                continue
            speaker = utt.get("speaker")
            try:
                idx = int(speaker) + 1
            except (TypeError, ValueError):
                idx = 1
            lines.append(f"S{idx}: {text}")
        if lines:
            return "\n".join(lines)

    channels = results.get("channels") or [{}]
    alts = (channels[0].get("alternatives") or [{}])
    return str(alts[0].get("transcript") or "").strip()


class DeepgramBatchService:
    def __init__(self, api_key: Optional[str] = None) -> None:
        self.api_key = api_key or settings.DEEPGRAM_API_KEY

    async def transcribe(
        self,
        audio_bytes: bytes,
        *,
        content_type: str = "audio/wav",
        language: Optional[str] = None,
        user_id: Optional[str] = None,
        extra_terms: Optional[Iterable[EntityTerm]] = None,
        diarization: bool = True,
    ) -> str:
        if not self.api_key:
            raise RuntimeError("DEEPGRAM_API_KEY is not set")
        if not audio_bytes:
            raise RuntimeError("No audio bytes to transcribe")

        lang = resolve_batch_language(language)
        keyterms = await deepgram_keyterms_for_job(user_id, extra_terms)
        model = (getattr(settings, "STT_DEEPGRAM_MODEL", None) or "nova-3").strip() or "nova-3"

        params = listen_query_params(
            model=model,
            language=lang,
            keyterms=keyterms,
            diarization=diarization,
        )
        url = f"{LISTEN_URL}?{urlencode(params)}"
        headers = {
            "Authorization": f"Token {self.api_key}",
            "Content-Type": content_type or "application/octet-stream",
        }
        logger.info(
            "Deepgram listen started",
            extra=log_domain(
                DOMAIN_TRANSCRIPTION,
                "deepgram_listen_start",
                language=lang,
                model=model,
                keyterms=len(keyterms),
                bytes=len(audio_bytes),
            ),
        )
        async with httpx.AsyncClient(timeout=120.0) as http:
            response = await http.post(url, headers=headers, content=audio_bytes)
        try:
            data = response.json()
        except Exception as e:
            raise RuntimeError(
                f"Deepgram returned non-JSON ({response.status_code}): {response.text[:300]}"
            ) from e
        if response.status_code >= 400:
            err = data.get("err_msg") or data.get("error") or data
            raise RuntimeError(f"Deepgram listen failed ({response.status_code}): {err}")

        text = format_deepgram_transcript(data)
        if not text:
            raise RuntimeError("Deepgram returned an empty transcript")
        request_id = ((data.get("metadata") or {}).get("request_id")) or ""
        logger.info(
            "Deepgram listen complete",
            extra=log_domain(
                DOMAIN_TRANSCRIPTION,
                "deepgram_listen_complete",
                request_id=request_id,
                transcript_len=len(text),
                language=lang,
            ),
        )
        return text
