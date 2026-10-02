"""Live call transcription with one Speechmatics stream per side, each in its own language.

The client streams both sides as AddChannelAudio (`rep` = mic, `prospect` = the call).
Each side starts in the profile's main language. When the profile lists languages that
start can't transcribe (e.g. Catalan for a Spanish rep), a few seconds of that side's
speech go through Deepgram language ID; if it is confidently another language, that side
restarts in it and its buffered audio is replayed, so nothing said is lost. The client is
told with ChannelReset to drop that side's text from `from` on, which the new stream sends again.

Speechmatics realtime has no language ID and Deepgram streaming has none either; Deepgram's
file LID needs ~4 s of speech and answers in ~0.2 s.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional

import websockets

from app.config import settings
from app.services.glossary import GlossaryService
from app.services.live_report import DeepgramShadow, LiveReport
from app.services.session_entities import normalize_stt_languages
from app.services.stt_channels import speechmatics_words
from app.services.usage import record_stt_usage

logger = logging.getLogger(__name__)

SPEECHMATICS_RT_URL = "wss://eu2.rt.speechmatics.com/v2"
BYTES_PER_SECOND = 16000 * 2
# Seconds of a side's speech at which its language is checked while it is still unknown.
OPENING_CHECKS_S = (4.0, 10.0, 20.0)
# Once known, checked again after this much more speech: calls do change language.
RECHECK_EVERY_S = 45.0
# Speech sent to language ID per check.
WINDOW_S = 8.0
# Deepgram's confidence needed before a side restarts in another language.
SWITCH_CONFIDENCE = 0.85
# Audio kept per side so a restart can replay what was said.
BUFFER_S = 90.0
# Speechmatics takes replayed audio faster than real time (34 s back in ~4 s).
REPLAY_CHUNK_BYTES = 3200
FINISH_TIMEOUT_S = 8.0


def session_language(code: str, profile: list[str]) -> tuple[str, Optional[str]]:
    """Speechmatics language and domain for a detected language."""
    if code == "es" or (code == "en" and "es" in profile):
        # Spanish reps take calls in English too: the bilingual pack transcribes both.
        return "es", "bilingual-en"
    return code, None


def covered_languages(language: str, domain: Optional[str]) -> set[str]:
    return {"es", "en"} if domain == "bilingual-en" else {language}


def detection_languages(profile: list[str]) -> list[str]:
    langs = normalize_stt_languages(profile)
    if "es" in langs and "en" not in langs:
        langs.append("en")
    return langs


def needs_detection(profile: list[str], language: str, domain: Optional[str]) -> bool:
    """Only when the profile has a language the starting stream can't transcribe."""
    return bool(set(detection_languages(profile)) - covered_languages(language, domain))


@dataclass
class SideLanguage:
    """One side's language and when to check it, from the finals it has produced."""

    language: str
    domain: Optional[str]
    spans: list[tuple[float, float]] = field(default_factory=list)
    next_check: float = OPENING_CHECKS_S[0]
    opening: bool = True
    attempts: int = 0
    checking: bool = False

    def speech(self) -> float:
        return sum(end - start for start, end in self.spans)

    def add_final(self, start: float, end: float) -> None:
        if end > start:
            self.spans.append((start, end))

    def due(self) -> bool:
        return not self.checking and self.speech() >= self.next_check

    def window(self) -> Optional[tuple[float, float]]:
        """The latest speech, up to WINDOW_S of it, as one span of the side's audio."""
        if not self.spans:
            return None
        total = 0.0
        first = self.spans[-1][0]
        for start, end in reversed(self.spans):
            first = start
            total += end - start
            if total >= WINDOW_S:
                break
        return first, self.spans[-1][1]

    def switch_to(self, code: Optional[str], confidence: float) -> Optional[str]:
        """The language to restart in, or None to keep going."""
        if not code or confidence < SWITCH_CONFIDENCE:
            return None
        return None if code in covered_languages(self.language, self.domain) else code

    def checked(self, confident: bool) -> None:
        self.checking = False
        if self.opening:
            self.attempts += 1
            if confident or self.attempts >= len(OPENING_CHECKS_S):
                self.opening = False
            else:
                self.next_check = OPENING_CHECKS_S[self.attempts]
                return
        self.next_check = self.speech() + RECHECK_EVERY_S

    def restarted(self, language: str, domain: Optional[str], from_s: float) -> None:
        """The new stream sends this side's text from `from_s` again: count it once."""
        self.language, self.domain = language, domain
        self.spans = [span for span in self.spans if span[0] < from_s]


class PcmBuffer:
    """The last BUFFER_S of one side's audio, addressed in seconds since that side began."""

    def __init__(self, keep_s: float = BUFFER_S) -> None:
        self.keep = int(keep_s * BYTES_PER_SECOND)
        self.data = bytearray()
        self.dropped = 0

    def append(self, pcm: bytes) -> None:
        self.data.extend(pcm)
        excess = len(self.data) - self.keep
        if excess > 0:
            excess -= excess % 2
            del self.data[:excess]
            self.dropped += excess

    @property
    def start_s(self) -> float:
        return self.dropped / BYTES_PER_SECOND

    def slice(self, from_s: float, to_s: Optional[float] = None) -> tuple[bytes, float]:
        """Audio from `from_s` (or the oldest kept) to `to_s` (or now), and where it starts."""
        start = max(int(from_s * BYTES_PER_SECOND), self.dropped)
        start -= start % 2
        end = len(self.data) + self.dropped if to_s is None else int(to_s * BYTES_PER_SECOND)
        end = min(end, len(self.data) + self.dropped)
        return bytes(self.data[start - self.dropped : max(start, end) - self.dropped]), start / BYTES_PER_SECOND


class SpeechmaticsStream:
    """One side's realtime session. Audio fed before it is ready waits in order."""

    def __init__(
        self,
        label: str,
        language: str,
        domain: Optional[str],
        *,
        vocab: list[dict[str, Any]],
        offset_s: float,
        on_message: Callable[["SpeechmaticsStream", dict[str, Any]], Awaitable[None]],
    ) -> None:
        self.label = label
        self.language = language
        self.domain = domain
        self.vocab = vocab
        self.offset_s = offset_s
        self.on_message = on_message
        self.queue: asyncio.Queue = asyncio.Queue()
        self.ready = asyncio.Event()
        self.finished = asyncio.Event()
        self.started_at: Optional[float] = None
        self.ended_at: Optional[float] = None
        self.task: Optional[asyncio.Task] = None
        # A restarted side's stream first catches up on replayed audio: not timed until it is live.
        self.live_from_s = 0.0

    def config(self) -> dict[str, Any]:
        cfg: dict[str, Any] = {
            "language": self.language,
            "operating_point": "enhanced",
            "enable_partials": True,
            "max_delay": 1.5,
            "max_delay_mode": "flexible",
            "conversation_config": {"end_of_utterance_silence_trigger": 0.6},
            "diarization": "none",
        }
        if self.domain:
            cfg["domain"] = self.domain
        if self.vocab:
            cfg["additional_vocab"] = self.vocab
        return cfg

    def feed(self, pcm: bytes) -> None:
        self.queue.put_nowait(pcm)

    def force_end(self) -> None:
        self.queue.put_nowait({"message": "ForceEndOfUtterance"})

    def end(self) -> None:
        self.queue.put_nowait(None)

    def start(self, api_key: str) -> None:
        self.task = asyncio.create_task(self._run(api_key))

    async def _run(self, api_key: str) -> None:
        url = f"{SPEECHMATICS_RT_URL}/{self.language}"
        try:
            async with websockets.connect(url, additional_headers={"Authorization": f"Bearer {api_key}"}) as ws:
                await ws.send(
                    json.dumps(
                        {
                            "message": "StartRecognition",
                            "audio_format": {"type": "raw", "encoding": "pcm_s16le", "sample_rate": 16000},
                            "transcription_config": self.config(),
                        }
                    )
                )
                await asyncio.gather(self._send(ws), self._receive(ws))
        except Exception as e:
            logger.error("Speechmatics %s stream (%s) failed: %s", self.label, self.language, e)
            await self.on_message(self, {"message": "Error", "reason": str(e)})
        finally:
            self.ended_at = time.monotonic()
            self.ready.set()
            self.finished.set()

    async def _send(self, ws: Any) -> None:
        await self.ready.wait()
        seq = 0
        while True:
            item = await self.queue.get()
            if item is None:
                await ws.send(json.dumps({"message": "EndOfStream", "last_seq_no": seq}))
                return
            if isinstance(item, dict):
                await ws.send(json.dumps(item))
                continue
            seq += 1
            await ws.send(item)

    async def _receive(self, ws: Any) -> None:
        async for raw in ws:
            data = json.loads(raw)
            kind = data.get("message")
            if kind == "RecognitionStarted":
                self.started_at = time.monotonic()
                self.ready.set()
                continue
            await self.on_message(self, data)
            if kind in ("EndOfTranscript", "Error"):
                return

    def billed_seconds(self) -> float:
        if not self.started_at:
            return 0.0
        return (self.ended_at or time.monotonic()) - self.started_at


class ChannelSessions:
    """Both sides of a call, each in its own stream, with language checks when the profile needs them."""

    def __init__(
        self,
        client_ws: Any,
        *,
        labels: list[str],
        language: str,
        profile_languages: Optional[list[str]],
        glossary: list[dict],
        detect: bool,
        user_id: Optional[str] = None,
        service: str = "live",
    ) -> None:
        self.client = client_ws
        self.user_id = user_id
        self.labels = labels
        self.profile = normalize_stt_languages(profile_languages)
        self.api_key = (
            settings.SPEECHMATICS_API_KEY
            or os.environ.get("SPEECHMATICS_API_KEY")
            or os.environ.get("SPEECHNATICS_API_KEY")
        )
        start_language, start_domain = session_language(language, self.profile)
        self.detect = (
            detect
            and bool(settings.DEEPGRAM_API_KEY)
            and needs_detection(self.profile, start_language, start_domain)
        )
        self.vocab = GlossaryService().format_for_speechmatics(glossary) if glossary else []
        self.sides = {label: SideLanguage(start_language, start_domain) for label in labels}
        self.buffers = {label: PcmBuffer() for label in labels}
        self.active: dict[str, SpeechmaticsStream] = {}
        self.streams: list[SpeechmaticsStream] = []
        self.checks: set[asyncio.Task] = set()
        self.send_lock = asyncio.Lock()
        self.closing = False
        compare = settings.LIVE_COMPARE_DEEPGRAM and bool(settings.DEEPGRAM_API_KEY)
        self.report = LiveReport(labels, compare=compare, service=service)
        self.shadows: dict[str, DeepgramShadow] = {}

    async def run(self) -> None:
        await self._send({"type": "connected", "model": "realtime", "mode": "copilot_channels"})
        if not self.api_key:
            await self._send({"type": "Error", "provider": "speechmatics", "error": "Speechmatics API key not configured"})
            return
        logger.info(
            "Live channels: %s in %s (language checks %s, profile %s)",
            self.labels,
            self.sides[self.labels[0]].language,
            "on" if self.detect else "off",
            self.profile,
        )
        for label in self.labels:
            side = self.sides[label]
            self.active[label] = self._open(label, side.language, side.domain, offset_s=0.0)
            if self.report.compare:
                keyterms = [v["content"] for v in self.vocab if v.get("content")]
                self.shadows[label] = DeepgramShadow(
                    label, side.language, keyterms, settings.DEEPGRAM_API_KEY or "", self.report
                )
        try:
            await self._read_client()
        finally:
            await self._finish()

    def _open(self, label: str, language: str, domain: Optional[str], *, offset_s: float) -> SpeechmaticsStream:
        stream = SpeechmaticsStream(label, language, domain, vocab=self.vocab, offset_s=offset_s, on_message=self._on_stream)
        stream.start(self.api_key or "")
        self.streams.append(stream)
        return stream

    async def _read_client(self) -> None:
        while True:
            msg = await self.client.receive()
            if msg["type"] == "websocket.disconnect":
                return
            text = msg.get("text")
            if not text:
                continue
            try:
                data = json.loads(text)
            except ValueError:
                continue
            kind = data.get("type") or data.get("message")
            channel = data.get("channel")
            if kind == "AddChannelAudio" and channel in self.active and isinstance(data.get("data"), str):
                try:
                    pcm = base64.b64decode(data["data"])
                except ValueError:
                    continue
                self.buffers[channel].append(pcm)
                self.active[channel].feed(pcm)
                self.report.audio(channel, len(pcm))
                if channel in self.shadows:
                    self.shadows[channel].feed(pcm)
            elif kind in ("Finalize", "ForceEndOfUtterance"):
                for label in [channel] if channel in self.active else list(self.active):
                    self.active[label].force_end()
            elif kind == "ClientReport":
                self.report.from_client(data)
            elif kind == "CloseStream":
                return

    async def _finish(self) -> None:
        self.closing = True
        for stream in self.active.values():
            stream.end()
        for shadow in self.shadows.values():
            shadow.end()
        current = list(self.active.values())
        try:
            await asyncio.wait_for(asyncio.gather(*(s.finished.wait() for s in current)), FINISH_TIMEOUT_S)
        except asyncio.TimeoutError:
            logger.warning("Live channels: a stream did not finish in %ss", FINISH_TIMEOUT_S)
        if self.shadows:
            await asyncio.wait({s.task for s in self.shadows.values()}, timeout=3.0)
        for task in self.checks:
            task.cancel()
        try:
            await self._send({"type": "EndOfTranscript"})
        except Exception:
            pass
        for stream in self.streams:
            if stream.task and not stream.task.done():
                stream.task.cancel()
            seconds = stream.billed_seconds()
            if seconds:
                # Fire and forget: the ledger writes in a thread, other calls keep streaming.
                record_stt_usage("speechmatics", "realtime", seconds, channels=1, tier="enhanced")
        for shadow in self.shadows.values():
            shadow.task.cancel()
            if shadow.billed_seconds():
                record_stt_usage("deepgram", "realtime", shadow.billed_seconds(), channels=1)
        languages = {label: side.language for label, side in self.sides.items()}
        asyncio.get_running_loop().run_in_executor(None, self.report.save, self.user_id, languages)

    async def _send(self, payload: dict[str, Any]) -> None:
        async with self.send_lock:
            await self.client.send_json(payload)

    async def _on_stream(self, stream: SpeechmaticsStream, data: dict[str, Any]) -> None:
        if self.active.get(stream.label) is not stream:
            return  # replaced by a stream in the side's real language
        kind = data.get("message")
        offset = stream.offset_s
        if kind in ("AddPartialTranscript", "AddTranscript"):
            meta = data.get("metadata") or {}
            transcript = meta.get("transcript", "")
            words = speechmatics_words(data, offset)
            if not transcript and not words:
                return
            final = kind == "AddTranscript"
            payload: dict[str, Any] = {
                "type": "Results",
                "provider": "speechmatics",
                "is_final": final,
                "channel": {"alternatives": [{"transcript": transcript, "confidence": 0.99 if final else 0.5}]},
                "audio_channel": stream.label,
                "language": stream.language,
            }
            if words:
                payload["words"] = words
            if isinstance(meta.get("start_time"), (int, float)):
                payload["start"] = meta["start_time"] + offset
                payload["end"] = meta.get("end_time", meta["start_time"]) + offset
            await self._send(payload)
            if "end" in payload:
                self.report.result(
                    "speechmatics",
                    stream.label,
                    final=final,
                    start=payload["start"],
                    end=payload["end"],
                    text=transcript,
                    timed=payload["end"] > stream.live_from_s,
                )
            if final and transcript.strip() and "start" in payload:
                self._after_final(stream.label, payload["start"], payload["end"])
        elif kind == "EndOfUtterance":
            meta = data.get("metadata") or {}
            await self._send(
                {
                    "type": "EndOfUtterance",
                    "forced": bool(meta.get("forced") or data.get("forced")),
                    "start_time": meta.get("start_time", 0) + offset if meta.get("start_time") is not None else None,
                    "end_time": meta.get("end_time", 0) + offset if meta.get("end_time") is not None else None,
                    "audio_channel": stream.label,
                }
            )
        elif kind == "Error":
            reason = data.get("reason", "Unknown error")
            logger.error("Speechmatics %s error: %s", stream.label, reason)
            await self._send({"type": "Error", "provider": "speechmatics", "error": reason})
        elif kind == "Warning":
            logger.warning("Speechmatics %s warning: %s", stream.label, data.get("reason"))

    def _after_final(self, label: str, start: float, end: float) -> None:
        side = self.sides[label]
        side.add_final(start, end)
        if self.detect and side.due():
            side.checking = True
            task = asyncio.create_task(self._check(label))
            self.checks.add(task)
            task.add_done_callback(self.checks.discard)

    async def _check(self, label: str) -> None:
        side = self.sides[label]
        span = side.window()
        if span is None:
            side.checked(False)
            return
        pcm, _ = self.buffers[label].slice(max(0.0, span[0] - 0.2), span[1] + 0.2)
        try:
            from app.services.deepgram_batch import DeepgramBatchService

            code, confidence = await DeepgramBatchService().detect_pcm_language(
                pcm, languages=detection_languages(self.profile)
            )
        except Exception as e:
            logger.warning("Live language check failed for %s: %s", label, e)
            side.checked(False)
            return
        logger.info("Live language %s: %s (%.2f) over %.1fs, stream %s", label, code, confidence, len(pcm) / BYTES_PER_SECOND, side.language)
        target = side.switch_to(code, confidence)
        # While the side's language was unknown, restart from its first word; later, from this speech.
        from_s = self.buffers[label].start_s if side.opening else span[0]
        side.checked(confidence >= SWITCH_CONFIDENCE)
        if target:
            await self._restart(label, target, from_s)

    async def _restart(self, label: str, code: str, from_s: float) -> None:
        language, domain = session_language(code, self.profile)
        old = self.active[label]
        # Connect first: until the new stream is ready the old one keeps transcribing,
        # and if it can't start, nothing changes.
        stream = self._open(label, language, domain, offset_s=0.0)
        try:
            await asyncio.wait_for(stream.ready.wait(), FINISH_TIMEOUT_S)
        except asyncio.TimeoutError:
            pass
        if self.closing or stream.finished.is_set() or stream.started_at is None or self.active.get(label) is not old:
            stream.end()
            logger.warning("Live language %s: could not start %s, staying in %s", label, language, old.language)
            return
        replay, replay_from = self.buffers[label].slice(from_s)
        stream.offset_s = replay_from
        stream.live_from_s = self.report.heard(label)
        for i in range(0, len(replay), REPLAY_CHUNK_BYTES):
            stream.feed(replay[i : i + REPLAY_CHUNK_BYTES])
        # Same tick as the replay: new audio lands after it, in order.
        self.active[label] = stream
        self.sides[label].restarted(language, domain, replay_from)
        self.report.restarted(label, language, replay_from)
        old.end()
        logger.info("Live language %s: restarted in %s from %.1fs", label, language, replay_from)
        await self._send({"type": "ChannelReset", "audio_channel": label, "from": replay_from, "language": language})
