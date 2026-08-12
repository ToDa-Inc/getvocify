"""
Real-time transcription WebSocket endpoint
Proxies audio stream to Speechmatics (Deepgram disabled)

Modes (query param `mode`):
  - default / memo: plain STT (diarization none) — recording page
  - enroll: speaker ID capture (get_speakers) for one-script voice enrollment
  - copilot: live speaker diarization + inject enrolled rep identifiers
"""

from __future__ import annotations

import asyncio
import json
import logging
import ssl
import os
import certifi
from typing import Any, List, Optional

# GLOBAL SURGICAL FIX: Force use of certifi certificates for macOS
os.environ["SSL_CERT_FILE"] = certifi.where()
os.environ["WEBSOCKETS_CA_BUNDLE"] = certifi.where()


def _patched_create_default_context(*args, **kwargs):
    ctx = ssl._orig_create_default_context(*args, **kwargs)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


if not hasattr(ssl, "_orig_create_default_context"):
    ssl._orig_create_default_context = ssl.create_default_context
    ssl.create_default_context = _patched_create_default_context
    ssl._create_default_https_context = ssl._create_unverified_context

import websockets
from fastapi import APIRouter, WebSocket

from app.config import settings
from app.deps import get_supabase
from app.services.glossary import GlossaryService
from app.services.voice_enrollment import REP_LABEL, VoiceEnrollmentService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/transcription", tags=["transcription"])

VALID_MODES = {"default", "memo", "enroll", "copilot"}


def _extract_words(data: dict) -> list[dict[str, Any]]:
    """Pull word-level content + speaker from Speechmatics results[]."""
    words: list[dict[str, Any]] = []
    for item in data.get("results") or []:
        if not isinstance(item, dict):
            continue
        if item.get("type") not in (None, "word"):
            # Keep punctuation attached as text without speaker votes
            if item.get("type") == "punctuation":
                alts = item.get("alternatives") or []
                content = (alts[0] or {}).get("content") if alts else None
                if content:
                    words.append({"text": str(content), "speaker": None, "is_punct": True})
            continue
        alts = item.get("alternatives") or []
        if not alts:
            continue
        alt = alts[0] if isinstance(alts[0], dict) else {}
        content = alt.get("content")
        if not content:
            continue
        speaker = alt.get("speaker")
        words.append(
            {
                "text": str(content),
                "speaker": str(speaker) if speaker else None,
                "is_punct": False,
            }
        )
    return words


def _identifiers_from_speakers_result(data: dict) -> list[str]:
    """Collect opaque speaker_identifiers from SpeakersResult."""
    out: list[str] = []
    speakers = data.get("speakers") or data.get("results") or []
    if isinstance(speakers, dict):
        speakers = [speakers]
    for sp in speakers:
        if not isinstance(sp, dict):
            continue
        ids = sp.get("speaker_identifiers") or sp.get("identifiers") or []
        if isinstance(ids, str):
            ids = [ids]
        for ident in ids:
            s = str(ident).strip()
            if s and s not in out:
                out.append(s)
    return out


class SpeechmaticsProxy:
    """
    Surgical Proxy for Speechmatics Real-time API.
    Handles bi-directional streaming between Client and Speechmatics.
    """

    def __init__(
        self,
        language: str = "multi",
        glossary: Optional[List[dict]] = None,
        *,
        mode: str = "default",
        enrolled_speaker: Optional[dict[str, Any]] = None,
    ):
        self.language = "es" if language == "multi" else language
        self.glossary = glossary or []
        self.mode = mode if mode in VALID_MODES else "default"
        self.enrolled_speaker = enrolled_speaker
        self.api_key = (
            settings.SPEECHMATICS_API_KEY
            or os.environ.get("SPEECHMATICS_API_KEY")
            or os.environ.get("SPEECHNATICS_API_KEY")
        )
        self.base_url = "wss://eu2.rt.speechmatics.com/v2"
        self.ws = None
        self.recognition_started = asyncio.Event()

    def _build_transcription_config(self, target_lang: str) -> dict[str, Any]:
        use_speaker = self.mode in ("enroll", "copilot")
        cfg: dict[str, Any] = {
            "language": target_lang,
            "operating_point": "enhanced",
            "diarization": "speaker" if use_speaker else "none",
            "enable_partials": True,
            # 0.7 was too aggressive for speakerphone — finals were early/garbled.
            # Speechmatics voice-agent guidance ~1.5s; keep enroll a bit snappier.
            "max_delay": 1.2 if self.mode == "enroll" else (1.8 if use_speaker else 1.5),
            "max_delay_mode": "flexible",
            "conversation_config": {
                "end_of_utterance_silence_trigger": 0.8 if use_speaker else 0.6,
            },
        }

        if self.mode == "enroll":
            # get_speakers must live under speaker_diarization_config (not transcription_config root)
            cfg["speaker_diarization_config"] = {
                "get_speakers": True,
                "max_speakers": 2,
            }
        elif self.mode == "copilot":
            # Only use schema-accepted keys on eu2 RT — undocumented
            # speakers_sensitivity / speaker_sensitivity cause 1003 protocol_error.
            speaker_cfg: dict[str, Any] = {
                "prefer_current_speaker": True,
                "max_speakers": 2,
            }
            if self.enrolled_speaker:
                speaker_cfg["speakers"] = [
                    {
                        "label": self.enrolled_speaker.get("label") or REP_LABEL,
                        "speaker_identifiers": self.enrolled_speaker["speaker_identifiers"],
                    }
                ]
            cfg["speaker_diarization_config"] = speaker_cfg

        if self.glossary:
            service = GlossaryService()
            cfg["additional_vocab"] = service.format_for_speechmatics(self.glossary)

        return cfg

    async def proxy_session(self, client_ws: WebSocket, audio_queue: asyncio.Queue):
        if not self.api_key:
            logger.error("SPEECHMATICS_API_KEY IS NOT SET IN THE BACKEND.")
            await client_ws.send_json(
                {
                    "type": "Error",
                    "provider": "speechmatics",
                    "error": "Speechmatics API key not configured",
                }
            )
            return

        target_lang = "es" if self.language == "multi" else self.language
        connection_url = f"{self.base_url}/{target_lang}"
        logger.info(
            "Speechmatics connecting to %s (mode=%s enrolled=%s)",
            connection_url,
            self.mode,
            bool(self.enrolled_speaker),
        )

        try:
            async with websockets.connect(
                connection_url,
                additional_headers={"Authorization": f"Bearer {self.api_key}"},
            ) as sm_ws:
                logger.info("Speechmatics connection handshake successful")

                config = {
                    "message": "StartRecognition",
                    "audio_format": {
                        "type": "raw",
                        "encoding": "pcm_s16le",
                        "sample_rate": 16000,
                    },
                    "transcription_config": self._build_transcription_config(target_lang),
                }
                if self.glossary:
                    logger.info(
                        "Injected %d glossary terms into Speechmatics", len(self.glossary)
                    )

                await sm_ws.send(json.dumps(config))
                self.recognition_started = asyncio.Event()

                async def send_audio():
                    await self.recognition_started.wait()
                    logger.info("Speechmatics recognition started, now streaming audio")

                    while True:
                        audio_chunk = await audio_queue.get()
                        if audio_chunk is None:
                            await sm_ws.send(
                                json.dumps({"message": "EndOfStream", "last_seq_no": 0})
                            )
                            break
                        if isinstance(audio_chunk, dict):
                            await sm_ws.send(json.dumps(audio_chunk))
                            continue
                        await sm_ws.send(audio_chunk)

                async def receive_transcripts():
                    async for message in sm_ws:
                        data = json.loads(message)
                        msg_type = data.get("message")

                        if msg_type == "RecognitionStarted":
                            self.recognition_started.set()
                            logger.info("Speechmatics RecognitionStarted received")
                            if self.mode == "enroll":
                                await sm_ws.send(
                                    json.dumps({"message": "GetSpeakers", "final": True})
                                )

                        elif msg_type in ("AddPartialTranscript", "AddTranscript"):
                            transcript = data.get("metadata", {}).get("transcript", "")
                            words = _extract_words(data) if self.mode in ("enroll", "copilot") else []
                            if not transcript and not words:
                                continue
                            response: dict[str, Any] = {
                                "type": "Results",
                                "provider": "speechmatics",
                                "is_final": msg_type == "AddTranscript",
                                "channel": {
                                    "alternatives": [
                                        {
                                            "transcript": transcript
                                            or " ".join(
                                                w["text"]
                                                for w in words
                                                if not w.get("is_punct")
                                            ),
                                            "confidence": 0.99
                                            if msg_type == "AddTranscript"
                                            else 0.5,
                                        }
                                    ]
                                },
                            }
                            if words:
                                response["words"] = words
                            await client_ws.send_json(response)

                        elif msg_type == "EndOfUtterance":
                            meta = data.get("metadata") or {}
                            await client_ws.send_json(
                                {
                                    "type": "EndOfUtterance",
                                    "forced": bool(meta.get("forced") or data.get("forced")),
                                    "start_time": meta.get("start_time"),
                                    "end_time": meta.get("end_time"),
                                }
                            )

                        elif msg_type == "SpeakersResult":
                            identifiers = _identifiers_from_speakers_result(data)
                            logger.info(
                                "SpeakersResult received (%d identifiers) mode=%s",
                                len(identifiers),
                                self.mode,
                            )
                            # Never echo raw identifiers except in enroll mode to the enrolling client
                            await client_ws.send_json(
                                {
                                    "type": "SpeakersResult",
                                    "speaker_identifiers": identifiers
                                    if self.mode == "enroll"
                                    else [],
                                    "count": len(identifiers),
                                }
                            )

                        elif msg_type == "Error":
                            reason = data.get("reason", "Unknown error")
                            logger.error("Speechmatics error: %s", reason)
                            await client_ws.send_json(
                                {
                                    "type": "Error",
                                    "provider": "speechmatics",
                                    "error": reason,
                                }
                            )

                        elif msg_type == "Warning":
                            logger.warning(
                                "Speechmatics warning: %s", data.get("reason")
                            )

                await asyncio.gather(send_audio(), receive_transcripts())

        except Exception as e:
            logger.error("Speechmatics session error: %s", e)
            await client_ws.send_json(
                {
                    "type": "Error",
                    "provider": "speechmatics",
                    "error": str(e),
                }
            )


class SpeechmaticsOnlyProxy:
    """Real-time transcription via Speechmatics only (Deepgram disabled)."""

    def __init__(
        self,
        language: str = "multi",
        glossary: Optional[List[dict]] = None,
        *,
        mode: str = "default",
        enrolled_speaker: Optional[dict[str, Any]] = None,
    ):
        self.language = language
        self.glossary = glossary or []
        self.mode = mode
        self.sm_queue: asyncio.Queue = asyncio.Queue()
        self.sm_proxy = SpeechmaticsProxy(
            language,
            glossary=self.glossary,
            mode=mode,
            enrolled_speaker=enrolled_speaker,
        )

    async def proxy_session(self, client_ws: WebSocket):
        try:
            await client_ws.send_json(
                {"type": "connected", "model": "realtime", "mode": self.mode}
            )

            async def client_to_queue():
                try:
                    while True:
                        msg = await client_ws.receive()
                        if msg["type"] == "websocket.disconnect":
                            break
                        if "bytes" in msg:
                            await self.sm_queue.put(msg["bytes"])
                        elif "text" in msg:
                            data = json.loads(msg["text"])
                            msg_type = data.get("type") or data.get("message")
                            if msg_type in ("Finalize", "ForceEndOfUtterance"):
                                await self.sm_queue.put(
                                    {"message": "ForceEndOfUtterance"}
                                )
                            elif msg_type == "CloseStream":
                                break
                finally:
                    await self.sm_queue.put(None)

            await asyncio.gather(
                client_to_queue(),
                self.sm_proxy.proxy_session(client_ws, self.sm_queue),
            )

        except Exception as e:
            logger.error("Speechmatics proxy session error: %s", e)
        finally:
            logger.info("Speechmatics proxy session finished")


@router.websocket("/live")
async def live_transcription(websocket: WebSocket):
    """
    FastAPI WebSocket entry point for real-time transcription (Speechmatics).
    """
    await websocket.accept()
    language = websocket.query_params.get("language", "multi")
    user_id = websocket.query_params.get("user_id")
    session_vocab_raw = websocket.query_params.get("session_vocab") or ""
    mode = (websocket.query_params.get("mode") or "default").strip().lower()
    if mode not in VALID_MODES:
        mode = "default"

    glossary: list = []
    if user_id:
        try:
            glossary_service = GlossaryService()
            glossary = await glossary_service.get_user_glossary(user_id)
            logger.info("Loaded %d glossary terms for user %s", len(glossary), user_id)
        except Exception as e:
            logger.error("Failed to load glossary: %s", e)

    if session_vocab_raw:
        seen = {
            (g.get("target_word") or g.get("term") or "").strip().lower()
            for g in glossary
            if isinstance(g, dict)
        }
        for part in session_vocab_raw.split("|"):
            term = part.strip()
            if not term or term.lower() in seen:
                continue
            seen.add(term.lower())
            glossary.append({"target_word": term, "phonetic_hints": []})

    enrolled_speaker = None
    if mode == "copilot" and user_id and user_id != "anonymous":
        try:
            enrolled_speaker = VoiceEnrollmentService(
                get_supabase()
            ).get_identifiers_for_stt(user_id)
            if enrolled_speaker:
                logger.info(
                    "Loaded voice enrollment for user %s (%d ids)",
                    user_id,
                    len(enrolled_speaker.get("speaker_identifiers") or []),
                )
        except Exception as e:
            logger.error("Failed to load voice enrollment: %s", e)

    proxy = SpeechmaticsOnlyProxy(
        language=language,
        glossary=glossary,
        mode=mode,
        enrolled_speaker=enrolled_speaker,
    )
    await proxy.proxy_session(websocket)
