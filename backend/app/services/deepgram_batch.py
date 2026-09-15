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
DEEPGRAM_MODEL = "nova-3"


def listen_query_params(
    *,
    model: str,
    language: str,
    keyterms: Iterable[str],
    diarization: bool,
    multichannel: bool = False,
) -> list[tuple[str, str]]:
    """Nova-3 listen query. `diarize` + `utterances` only — `diarize_model` 400s with `diarize`."""
    params: list[tuple[str, str]] = [
        ("model", model),
        ("language", language),
        ("punctuate", "true"),
        ("smart_format", "true"),
    ]
    if multichannel:
        params.append(("multichannel", "true"))
        params.append(("utterances", "true"))
    elif diarization:
        params.append(("diarize", "true"))
        params.append(("utterances", "true"))
    for term in keyterms:
        if term:
            params.append(("keyterm", str(term)))
    return params


def mean_utterance_confidence(payload: dict[str, Any]) -> Optional[float]:
    utterances = (payload.get("results") or {}).get("utterances") or []
    values: list[float] = []
    for utt in utterances:
        raw = utt.get("confidence")
        if raw is None:
            continue
        try:
            values.append(float(raw))
        except (TypeError, ValueError):
            continue
    if not values:
        return None
    return sum(values) / len(values)


def format_deepgram_transcript(
    payload: dict[str, Any],
    *,
    multichannel: bool = False,
) -> tuple[str, Optional[float]]:
    """Utterances → S1/S2 text. Fall back to the flat transcript."""
    results = payload.get("results") or {}
    utterances = results.get("utterances") or []
    if utterances:
        rows: list[tuple[float, str]] = []
        for utt in utterances:
            text = str(utt.get("transcript") or "").strip()
            if not text:
                continue
            if multichannel and utt.get("channel") is not None:
                try:
                    idx = int(utt["channel"]) + 1
                except (TypeError, ValueError):
                    idx = 1
            else:
                try:
                    idx = int(utt.get("speaker")) + 1
                except (TypeError, ValueError):
                    idx = 1
            start = float(utt.get("start") or 0.0)
            rows.append((start, f"S{idx}: {text}"))
        if multichannel:
            rows.sort(key=lambda row: row[0])
        if rows:
            return "\n".join(line for _, line in rows), mean_utterance_confidence(payload)

    channels = results.get("channels") or [{}]
    alts = (channels[0].get("alternatives") or [{}])
    return str(alts[0].get("transcript") or "").strip(), mean_utterance_confidence(payload)


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
        multichannel: bool = False,
    ) -> tuple[str, Optional[float]]:
        if not self.api_key:
            raise RuntimeError("DEEPGRAM_API_KEY is not set")
        if not audio_bytes:
            raise RuntimeError("No audio bytes to transcribe")

        lang = resolve_batch_language(language, user_id=user_id)
        keyterms = await deepgram_keyterms_for_job(user_id, extra_terms)

        params = listen_query_params(
            model=DEEPGRAM_MODEL,
            language=lang,
            keyterms=keyterms,
            diarization=diarization,
            multichannel=multichannel,
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
                model=DEEPGRAM_MODEL,
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

        text, confidence = format_deepgram_transcript(data, multichannel=multichannel)
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
        return text, confidence
