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
    normalize_stt_languages,
    resolve_batch_language,
    stt_first_pass_covers,
)

logger = logging.getLogger(__name__)

LISTEN_URL = "https://api.deepgram.com/v1/listen"
DEEPGRAM_MODEL = "nova-3"
# Enough speech for LID; not a second full-file transcribe.
DETECT_PREFIX_BYTES = 2_500_000


def _wav_data_region(audio: bytes) -> tuple[bytes, int, int, int] | None:
    """fmt payload, data offset, data length, frame size. None if not a WAVE file."""
    if len(audio) < 44 or audio[:4] != b"RIFF" or audio[8:12] != b"WAVE":
        return None
    offset = 12
    fmt = b""
    while offset + 8 <= len(audio):
        cid = audio[offset : offset + 4]
        size = int.from_bytes(audio[offset + 4 : offset + 8], "little")
        payload = offset + 8
        if cid == b"fmt ":
            fmt = audio[payload : payload + min(size, 16)]
        elif cid == b"data":
            if len(fmt) < 16:
                return None
            channels = int.from_bytes(fmt[2:4], "little") or 1
            bits = int.from_bytes(fmt[14:16], "little") or 16
            frame = max(1, channels * bits // 8)
            return fmt, payload, min(size, len(audio) - payload), frame
        offset = payload + size + (size & 1)
    return None


def _wav_from_pcm(fmt: bytes, pcm: bytes) -> bytes:
    return (
        b"RIFF"
        + (36 + len(pcm)).to_bytes(4, "little")
        + b"WAVE"
        + b"fmt "
        + (16).to_bytes(4, "little")
        + fmt[:16]
        + b"data"
        + len(pcm).to_bytes(4, "little")
        + pcm
    )


def detect_audio_windows(audio_bytes: bytes, window: int = DETECT_PREFIX_BYTES) -> list[bytes]:
    """Start / mid / end slices. WAVE mid/end keep a valid header so the vendor can decode them."""
    data = audio_bytes or b""
    if not data:
        return []
    wav = _wav_data_region(data)
    if wav:
        fmt, data_off, data_len, frame = wav
        pcm = data[data_off : data_off + data_len]
        if len(pcm) <= window:
            return [data]
        win = max(frame, window - (window % frame))
        mid = ((len(pcm) - win) // 2) // frame * frame
        end = (len(pcm) - win) // frame * frame
        out: list[bytes] = []
        for start in (0, mid, end):
            chunk = _wav_from_pcm(fmt, pcm[start : start + win])
            if chunk not in out:
                out.append(chunk)
        return out
    if len(data) <= window:
        return [data]
    mid = (len(data) - window) // 2
    end = len(data) - window
    out = []
    for start in (0, mid, end):
        chunk = data[start : start + window]
        if chunk not in out:
            out.append(chunk)
    return out


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


def detect_query_params(*, model: str, languages: list[str]) -> list[tuple[str, str]]:
    """Restrict Deepgram LID to the user's selected codes. No language= pin."""
    params: list[tuple[str, str]] = [("model", model)]
    for code in normalize_stt_languages(languages):
        params.append(("detect_language", code))
    return params


def language_from_deepgram_detect(
    payload: dict[str, Any],
    allowed: list[str],
    *,
    first_lang: str = "",
) -> Optional[str]:
    """Pick a profile language from Deepgram channel LID. Prefer one the first pass missed."""
    allowed_set = set(normalize_stt_languages(allowed))
    found: list[str] = []
    for channel in (payload.get("results") or {}).get("channels") or []:
        raw = str(channel.get("detected_language") or "").strip().lower()
        code = raw.split("-")[0]
        if code in allowed_set:
            found.append(code)
    if not found:
        return None
    if first_lang:
        uncovered = [code for code in found if not stt_first_pass_covers(first_lang, code)]
        if uncovered:
            return uncovered[0]
    return found[0]


def alternative_confidence(payload: dict[str, Any]) -> Optional[float]:
    channels = (payload.get("results") or {}).get("channels") or [{}]
    raw = ((channels[0].get("alternatives") or [{}])[0] or {}).get("confidence")
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


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
            return (
                "\n".join(line for _, line in rows),
                mean_utterance_confidence(payload) or alternative_confidence(payload),
            )

    channels = results.get("channels") or [{}]
    alts = (channels[0].get("alternatives") or [{}])
    return (
        str(alts[0].get("transcript") or "").strip(),
        mean_utterance_confidence(payload) or alternative_confidence(payload),
    )


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

    async def detect_language(
        self,
        audio_bytes: bytes,
        *,
        content_type: str = "audio/wav",
        languages: list[str],
        first_lang: str = "",
    ) -> Optional[str]:
        """Audio LID restricted to `languages`. Start/mid/end windows. Nova-3, then Nova-2 if 400."""
        if not self.api_key:
            raise RuntimeError("DEEPGRAM_API_KEY is not set")
        langs = normalize_stt_languages(languages)
        if len(langs) <= 1:
            return langs[0] if langs else None
        if not audio_bytes:
            return None
        last_error: Optional[Exception] = None
        found: list[str] = []
        for chunk in detect_audio_windows(audio_bytes):
            picked = None
            for model in (DEEPGRAM_MODEL, "nova-2"):
                params = detect_query_params(model=model, languages=langs)
                url = f"{LISTEN_URL}?{urlencode(params)}"
                headers = {
                    "Authorization": f"Token {self.api_key}",
                    "Content-Type": content_type or "application/octet-stream",
                }
                try:
                    async with httpx.AsyncClient(timeout=60.0) as http:
                        response = await http.post(url, headers=headers, content=chunk)
                    data = response.json()
                except Exception as e:
                    last_error = e
                    continue
                if response.status_code >= 400:
                    last_error = RuntimeError(
                        f"Deepgram detect failed ({response.status_code}): "
                        f"{data.get('err_msg') or data.get('error') or data}"
                    )
                    if response.status_code == 400:
                        continue
                    raise last_error
                picked = language_from_deepgram_detect(data, langs, first_lang=first_lang)
                break
            if picked:
                found.append(picked)
                if first_lang and not stt_first_pass_covers(first_lang, picked):
                    logger.info(
                        "Deepgram language detect allowed=%s first=%s picked=%s (uncovered window)",
                        langs,
                        first_lang or None,
                        picked,
                    )
                    return picked
        if found:
            logger.info(
                "Deepgram language detect allowed=%s first=%s picked=%s windows=%s",
                langs,
                first_lang or None,
                found[0],
                found,
            )
            return found[0]
        if last_error:
            logger.warning("Deepgram language detect skipped: %s", last_error)
        return None
