"""Live call transcription, one stream per side: Deepgram Nova-3, or Speechmatics per language.

The client streams both sides as AddChannelAudio (`rep` = mic, `prospect` = the call).
Deepgram Nova-3 `multi` transcribes Spanish and English, mixed, and settles text fastest; a
profile with a language it can't transcribe well (Catalan) goes to Speechmatics instead.
There, each side starts in the profile's main language. When the profile lists languages that
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
from array import array
import json
import logging
import os
import re
import unicodedata
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional
from urllib.parse import urlencode

import websockets

from app.config import settings
from app.services.glossary import GlossaryService
from app.services.live_report import LiveReport
from app.services.session_entities import EntityTerm, normalize_stt_languages
from app.services.transcript_sanitize import sanitize_transcript
from app.services.stt_channels import speechmatics_words
from app.services.usage import record_stt_usage

logger = logging.getLogger(__name__)

SPEECHMATICS_RT_URL = "wss://eu2.rt.speechmatics.com/v2"
DEEPGRAM_LIVE_URL = "wss://api.deepgram.com/v1/listen"
# MAI-Transcribe-2-Streaming through Vercel AI Gateway (no Azure quota needed). Its protocol:
# one start frame, raw PCM in binary frames, an audio-done frame; transcript parts come back.
MAI_GATEWAY_URL = "wss://ai-gateway.vercel.sh/v4/ai/transcription-model?ai-model-id=microsoft/mai-transcribe-2-streaming"
MAI_RATE = 24000
# The gateway closes a session after 25 minutes: a side moves to a fresh one before that.
MAI_SESSION_S = 24 * 60.0
# MAI is billed per second of audio sent: a side only sends while someone on it is speaking.
# Loud enough to send (RMS, about -50 dBFS: room noise stays under it, a soft voice doesn't).
SPEECH_RMS = 100
# Kept before speech starts, so its first syllable isn't cut, and sent on after it stops.
PRE_ROLL_S = 0.3
HANG_S = 0.6
# A side that stays quiet still sends a moment of silence, or the gateway closes after 5 minutes.
KEEPALIVE_S = 60.0
# Nova-3 `multi` code-switches between these; a profile with any other goes to Speechmatics.
DEEPGRAM_MULTI = {"en", "es", "fr", "de", "hi", "ru", "pt", "ja", "it", "nl"}
MAX_KEYTERMS = 50
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


def sound_key(word: str) -> str:
    """How a word sounds in Spanish, spelled one way: C/K/QU, B/V, Z/S and soft C, LL/Y,
    a final Y as I, a silent H, doubled letters once. Koby, Cobi, Covi and Cobee all read "kobi"."""
    w = unicodedata.normalize("NFD", word.lower())
    w = "".join(c for c in w if unicodedata.category(c) != "Mn")
    w = re.sub(r"[^a-zñ]", "", w)
    w = re.sub(r"c(?=[ei])", "s", w)
    w = re.sub(r"qu(?=[ei])", "k", w)
    w = w.replace("ch", "#").replace("ll", "y")
    w = w.translate(str.maketrans({"c": "k", "q": "k", "z": "s", "v": "b", "w": "b", "h": ""}))
    w = w.replace("#", "ch")
    w = re.sub(r"y$", "i", w)
    w = re.sub(r"ee$", "i", w)
    return re.sub(r"(.)\1+", r"\1", w)


# Everyday words a term must not sound like, or every "bale" would become a company called Vale.
_COMMON_SOUNDS = {
    sound_key(w)
    for w in (
        "vale bueno claro pues cosa como pero para esto esta este todo nada bien sabes hola gracias "
        "entonces porque donde cuando ahora mismo solo tambien tiene tienen hace hacer puede poder "
        "quiero quieres creo tengo vamos venga perfecto genial exacto verdad mira oye dime digo dice "
        "cada mucho poco mejor peor tipo caso semana mes dias tiempo empresa cliente clientes equipo "
        "llamada correo precio coste venta ventas datos parte otra otro otros otras gente "
        "molt també però perquè doncs aquí això això sí bé gràcies setmana "
        "that this have with what about okay yeah sure right well just like know think good great"
    ).split()
}
_WORD = re.compile(r"[^\W\d_]{4,}")


def glossary_terms(vocab: list[dict[str, Any]]) -> list[EntityTerm]:
    """The glossary's words and what they sound like, for fixing a bubble's text as it arrives."""
    return [
        EntityTerm(canonical=v["content"], aliases=tuple(v.get("sounds_like") or ()), kind="glossary")
        for v in vocab
        if v.get("content")
    ]


def glossary_sounds(terms: list[EntityTerm]) -> dict[str, str]:
    """Sound of each one-word term and listed sound-alike, to the term. Left out: words under four
    letters, ones that sound like an everyday word, and sounds two terms share."""
    sounds: dict[str, str] = {}
    clashes: set[str] = set()
    for term in terms:
        if " " in term.canonical.strip():
            continue
        for spelling in (term.canonical, *term.aliases):
            key = sound_key(spelling)
            if len(key) < 4 or key in _COMMON_SOUNDS or " " in spelling.strip():
                continue
            if sounds.get(key, term.canonical) != term.canonical:
                clashes.add(key)
            sounds[key] = term.canonical
    return {k: v for k, v in sounds.items() if k not in clashes}


def apply_glossary(text: str, terms: list[EntityTerm], sounds: Optional[dict[str, str]] = None) -> str:
    """The glossary's spelling for its words: listed sound-alikes exactly ("Vosify" for Vocify),
    then any word that sounds exactly like a term or a sound-alike ("Koby" for Cobee, listed as
    "Cobi"). A word that only resembles one is never changed."""
    if not terms or not text:
        return text
    text = sanitize_transcript(text, terms).text
    if not sounds:
        return text
    return _WORD.sub(lambda m: sounds.get(sound_key(m.group(0)), m.group(0)), text)


def live_provider(profile: list[str]) -> str:
    """Deepgram Nova-3 transcribes Spanish and English, mixed, and settles text fastest. A
    profile with a language it can't transcribe well (Catalan) stays on Speechmatics, which
    also checks each side's language and switches mid-call."""
    if not settings.DEEPGRAM_API_KEY:
        return "speechmatics"
    return "deepgram" if all(code in DEEPGRAM_MULTI for code in detection_languages(profile)) else "speechmatics"


class LiveStream:
    """One side's realtime session with one provider. Audio fed before it is ready waits in
    order. Results go to `on_event` as {"kind": partial|final|utterance_end|error|warning,
    "transcript", "start", "end", "words"}, in seconds since the side began."""

    provider = ""

    def __init__(
        self,
        label: str,
        language: str,
        domain: Optional[str],
        *,
        vocab: list[dict[str, Any]],
        offset_s: float,
        on_event: Callable[["LiveStream", dict[str, Any]], Awaitable[None]],
    ) -> None:
        self.label = label
        self.language = language
        self.domain = domain
        self.vocab = vocab
        self.offset_s = offset_s
        self.on_event = on_event
        self.queue: asyncio.Queue = asyncio.Queue()
        self.ready = asyncio.Event()
        self.finished = asyncio.Event()
        self.started_at: Optional[float] = None
        self.ended_at: Optional[float] = None
        self.task: Optional[asyncio.Task] = None
        # A restarted side's stream first catches up on replayed audio: not timed until it is live.
        self.live_from_s = 0.0
        # Seconds of audio fed so far, for providers whose results carry no times.
        self.fed_s = 0.0

    def feed(self, pcm: bytes) -> None:
        self.fed_s += len(pcm) / BYTES_PER_SECOND
        self.queue.put_nowait(pcm)

    def force_end(self) -> None:
        self.queue.put_nowait("force")

    def end(self) -> None:
        self.queue.put_nowait(None)

    def start(self, api_key: str) -> None:
        self.task = asyncio.create_task(self._run(api_key))

    def billed_seconds(self) -> float:
        if not self.started_at:
            return 0.0
        return (self.ended_at or time.monotonic()) - self.started_at

    async def _run(self, api_key: str) -> None:
        try:
            async with websockets.connect(
                self.url(), additional_headers=self.headers(api_key), subprotocols=self.subprotocols(api_key)
            ) as ws:
                await self.opened(ws)
                await asyncio.gather(self._send(ws), self._receive(ws))
        except Exception as e:
            logger.error("%s %s stream (%s) failed: %s", self.provider, self.label, self.language, e)
            await self.on_event(self, {"kind": "error", "reason": str(e)})
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
                await ws.send(json.dumps(self.end_message(seq)))
                return
            if item == "force":
                message = self.force_message()
                if message:
                    await ws.send(json.dumps(message))
                continue
            seq += 1
            await ws.send(self.frame(item))

    async def _receive(self, ws: Any) -> None:
        async for raw in ws:
            if isinstance(raw, bytes):
                continue
            for event in self.events(json.loads(raw)):
                await self.on_event(self, event)
                if event["kind"] in ("done", "error"):
                    return

    def subprotocols(self, api_key: str) -> Optional[list[str]]:
        return None

    def frame(self, pcm: bytes) -> bytes:
        return pcm

    # Per provider
    def url(self) -> str: raise NotImplementedError
    def headers(self, api_key: str) -> dict[str, str]: raise NotImplementedError
    async def opened(self, ws: Any) -> None: raise NotImplementedError
    def end_message(self, seq: int) -> dict[str, Any]: raise NotImplementedError
    def force_message(self) -> Optional[dict[str, Any]]: raise NotImplementedError
    def events(self, data: dict[str, Any]) -> list[dict[str, Any]]: raise NotImplementedError


class SpeechmaticsStream(LiveStream):
    provider = "speechmatics"

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

    def url(self) -> str:
        return f"{SPEECHMATICS_RT_URL}/{self.language}"

    def headers(self, api_key: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {api_key}"}

    async def opened(self, ws: Any) -> None:
        await ws.send(
            json.dumps(
                {
                    "message": "StartRecognition",
                    "audio_format": {"type": "raw", "encoding": "pcm_s16le", "sample_rate": 16000},
                    "transcription_config": self.config(),
                }
            )
        )

    def end_message(self, seq: int) -> dict[str, Any]:
        return {"message": "EndOfStream", "last_seq_no": seq}

    def force_message(self) -> dict[str, Any]:
        return {"message": "ForceEndOfUtterance"}

    def events(self, data: dict[str, Any]) -> list[dict[str, Any]]:
        kind = data.get("message")
        meta = data.get("metadata") or {}
        start, end = meta.get("start_time"), meta.get("end_time")
        at = (start + self.offset_s) if isinstance(start, (int, float)) else None
        until = (end + self.offset_s) if isinstance(end, (int, float)) else at
        if kind == "RecognitionStarted":
            self.started_at = time.monotonic()
            self.ready.set()
            return []
        if kind in ("AddPartialTranscript", "AddTranscript"):
            return [
                {
                    "kind": "final" if kind == "AddTranscript" else "partial",
                    "transcript": meta.get("transcript", ""),
                    "words": speechmatics_words(data, self.offset_s),
                    "start": at,
                    "end": until,
                }
            ]
        if kind == "EndOfUtterance":
            return [{"kind": "utterance_end", "forced": bool(meta.get("forced") or data.get("forced")), "start": at, "end": until}]
        if kind == "Error":
            return [{"kind": "error", "reason": data.get("reason", "Unknown error")}]
        if kind == "Warning":
            return [{"kind": "warning", "reason": data.get("reason")}]
        if kind == "EndOfTranscript":
            return [{"kind": "done"}]
        return []


class DeepgramStream(LiveStream):
    """Nova-3 `multi`: Spanish and English (and the other languages it code-switches), mixed."""

    provider = "deepgram"

    def url(self) -> str:
        params: list[tuple[str, str]] = [
            ("model", "nova-3"),
            ("language", "multi" if self.language in DEEPGRAM_MULTI else self.language),
            ("encoding", "linear16"),
            ("sample_rate", "16000"),
            ("channels", "1"),
            ("interim_results", "true"),
            ("smart_format", "true"),
            ("punctuate", "true"),
            ("endpointing", "300"),
        ]
        params += [("keyterm", v["content"]) for v in self.vocab[:MAX_KEYTERMS] if v.get("content")]
        return f"{DEEPGRAM_LIVE_URL}?{urlencode(params)}"

    def headers(self, api_key: str) -> dict[str, str]:
        return {"Authorization": f"Token {api_key}"}

    async def opened(self, ws: Any) -> None:
        self.started_at = time.monotonic()
        self.ready.set()

    def end_message(self, seq: int) -> dict[str, Any]:
        return {"type": "CloseStream"}

    def force_message(self) -> dict[str, Any]:
        return {"type": "Finalize"}

    def events(self, data: dict[str, Any]) -> list[dict[str, Any]]:
        kind = data.get("type")
        if kind == "Results":
            alternative = ((data.get("channel") or {}).get("alternatives") or [{}])[0]
            start = float(data.get("start") or 0.0) + self.offset_s
            final = bool(data.get("is_final"))
            words = [
                {
                    "text": str(w.get("punctuated_word") or w.get("word") or ""),
                    "speaker": None,
                    "is_punct": False,
                    "start_ms": int((float(w.get("start") or 0.0) + self.offset_s) * 1000),
                    "end_ms": int((float(w.get("end") or 0.0) + self.offset_s) * 1000),
                }
                for w in alternative.get("words") or []
            ]
            out = [
                {
                    "kind": "final" if final else "partial",
                    "transcript": alternative.get("transcript") or "",
                    "words": words,
                    "start": start,
                    "end": start + float(data.get("duration") or 0.0),
                }
            ]
            if final and data.get("speech_final") and alternative.get("transcript"):
                out.append({"kind": "utterance_end", "forced": False, "start": out[0]["start"], "end": out[0]["end"]})
            return out
        if kind == "Error":
            return [{"kind": "error", "reason": data.get("description") or data.get("message") or "Deepgram error"}]
        return []


class Upsampler:
    """16 kHz to 24 kHz PCM16 by linear interpolation (3 samples out per 2 in). The last sample
    of each chunk starts the next, so chunk edges join without a gap."""

    def __init__(self) -> None:
        self.last: Optional[int] = None

    def __call__(self, pcm: bytes) -> bytes:
        samples = array("h")
        samples.frombytes(pcm[: len(pcm) - len(pcm) % 2])
        if not samples:
            return b""
        if self.last is not None:
            samples.insert(0, self.last)
        out = array("h")
        k = 0
        while 2 * k < 3 * (len(samples) - 1):
            j, frac = divmod(2 * k, 3)
            a = samples[j]
            out.append(a + (samples[j + 1] - a) * frac // 3)
            k += 1
        self.last = samples[-1]
        return out.tobytes()


def speech_level(pcm: bytes) -> float:
    """RMS of a PCM16 chunk."""
    samples = array("h")
    samples.frombytes(pcm[: len(pcm) - len(pcm) % 2])
    if not samples:
        return 0.0
    return (sum(x * x for x in samples) / len(samples)) ** 0.5


class MaiStream(LiveStream):
    """MAI-Transcribe-2-Streaming via Vercel AI Gateway: 60 languages detected as they are spoken,
    Catalan included, so no language checks or restarts are needed."""

    provider = "mai"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.upsample = Upsampler()
        self.last_end = self.offset_s
        # All audio this side heard (times come from it) and what is held back while it's quiet.
        self.heard_s = 0.0
        self.quiet: list[bytes] = []
        self.hang = 0.0
        self.sent_at_s = 0.0
        # A word the last delta may not have finished, and when the words now changing first showed.
        self.carry = ""
        self.shown_at: Optional[float] = None

    def url(self) -> str:
        return MAI_GATEWAY_URL

    def headers(self, api_key: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {api_key}"}

    def subprotocols(self, api_key: str) -> Optional[list[str]]:
        return ["ai-gateway-transcription.v1", f"ai-gateway-auth.{api_key}"]

    async def opened(self, ws: Any) -> None:
        await ws.send(json.dumps({"type": "transcription-stream.start", "inputAudioFormat": {"type": "audio/pcm", "rate": MAI_RATE}}))
        self.started_at = time.monotonic()
        self.ready.set()

    def frame(self, pcm: bytes) -> bytes:
        return self.upsample(pcm)

    def feed(self, pcm: bytes) -> None:
        """Sends speech (with a little before and after it); holds silence back."""
        seconds = len(pcm) / BYTES_PER_SECOND
        self.heard_s += seconds
        loud = speech_level(pcm) >= SPEECH_RMS
        send = loud or self.hang > 1e-6
        self.hang = HANG_S if loud else self.hang - seconds
        if send:
            for held in self.quiet:
                super().feed(held)
            self.quiet.clear()
            super().feed(pcm)
            self.sent_at_s = self.heard_s
            return
        self.quiet.append(pcm)
        while len(self.quiet) > 1 and sum(len(p) for p in self.quiet) / BYTES_PER_SECOND > PRE_ROLL_S:
            self.quiet.pop(0)
        if self.heard_s - self.sent_at_s >= KEEPALIVE_S:
            super().feed(bytes(len(pcm)))
            self.sent_at_s = self.heard_s

    def billed_seconds(self) -> float:
        return self.fed_s

    def end_message(self, seq: int) -> dict[str, Any]:
        return {"type": "transcription-stream.audio-done"}

    def force_message(self) -> Optional[dict[str, Any]]:
        return None  # the gateway has no commit; MAI settles on its own

    def events(self, data: dict[str, Any]) -> list[dict[str, Any]]:
        """`transcript-delta` is newly settled text (it can end mid-word: "acuer" + "das");
        `transcript-partial` is only the still-changing end after it. Neither carries times, so
        a sentence ends where the audio fed so far ends."""
        kind = data.get("type")
        now = time.monotonic()
        if kind == "transcript-delta":
            settled = self._settle(data.get("delta") or "")
            if not settled:
                return []
            start, end = self.last_end, max(self.last_end, self.offset_s + self.heard_s)
            self.last_end = end
            event = {"kind": "final", "transcript": settled, "words": [], "start": start, "end": end, "timed": False}
            if self.shown_at is not None:
                event["settle_s"] = now - self.shown_at
            self.shown_at = now if self.carry.strip() else None
            return [event]
        if kind == "transcript-partial":
            text = (self.carry + (data.get("text") or "")).strip()
            if not text:
                return []
            if self.shown_at is None:
                self.shown_at = now
            end = max(self.last_end, self.offset_s + self.heard_s)
            return [{"kind": "partial", "transcript": text, "words": [], "start": self.last_end, "end": end, "timed": False}]
        if kind in ("transcript-final", "finish"):
            # The whole item again: already sent as deltas; only a held last word is left.
            rest, self.carry = self.carry.strip(), ""
            out = []
            if rest:
                end = max(self.last_end, self.offset_s + self.heard_s)
                out.append({"kind": "final", "transcript": rest, "words": [], "start": self.last_end, "end": end, "timed": False})
                self.last_end = end
            if kind == "finish":
                out.append({"kind": "done"})
            return out
        if kind == "error":
            error = data.get("error")
            reason = error.get("message") if isinstance(error, dict) else str(error or "MAI error")
            return [{"kind": "error", "reason": reason}]
        return []

    def _settle(self, delta: str) -> str:
        """Settled text up to a whole word. The last word waits for the next delta, which may
        continue it, unless punctuation closes it."""
        text = self.carry + delta
        cut = len(text) if text[-1:] in ".,;:!?…" else text.rfind(" ")
        if cut <= 0:
            self.carry = text
            return ""
        settled, self.carry = text[:cut], text[cut:]
        return settled.strip()


STREAMS: dict[str, type[LiveStream]] = {"speechmatics": SpeechmaticsStream, "deepgram": DeepgramStream, "mai": MaiStream}
# How long a provider's session may last before a side moves to a fresh one.
SESSION_LIMITS_S = {"mai": MAI_SESSION_S}


class ChannelSessions:
    """Both sides of a call, each in its own stream: Deepgram, or Speechmatics with language
    checks when the profile has a language Deepgram can't transcribe."""

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
        self.keys = {
            "speechmatics": settings.SPEECHMATICS_API_KEY
            or os.environ.get("SPEECHMATICS_API_KEY")
            or os.environ.get("SPEECHNATICS_API_KEY"),
            "deepgram": settings.DEEPGRAM_API_KEY,
            "mai": settings.AI_GATEWAY_API_KEY,
        }
        rule = live_provider(self.profile)
        # LIVE_STT_PROVIDER tries a provider on every call; the profile's rule is the comparison.
        forced = (settings.LIVE_STT_PROVIDER or "").strip().lower()
        self.provider = forced if forced in STREAMS and self.keys.get(forced) else rule
        start_language, start_domain = session_language(language, self.profile)
        self.detect = (
            detect
            and self.provider == "speechmatics"
            and bool(settings.DEEPGRAM_API_KEY)
            and needs_detection(self.profile, start_language, start_domain)
        )
        self.vocab = GlossaryService().format_for_speechmatics(glossary) if glossary else []
        self.terms = glossary_terms(self.vocab)
        self.sounds = glossary_sounds(self.terms)
        self.sides = {label: SideLanguage(start_language, start_domain) for label in labels}
        self.buffers = {label: PcmBuffer() for label in labels}
        self.active: dict[str, LiveStream] = {}
        self.streams: list[LiveStream] = []
        self.checks: set[asyncio.Task] = set()
        self.send_lock = asyncio.Lock()
        self.closing = False
        # The other provider on the same audio, for the call's report only.
        other = rule if rule != self.provider else ("speechmatics" if self.provider == "deepgram" else "deepgram")
        self.shadow_provider = other if settings.LIVE_COMPARE_STT and self.keys[other] else None
        providers = [self.provider] + ([self.shadow_provider] if self.shadow_provider else [])
        self.report = LiveReport(labels, providers=providers, service=service)
        self.shadows: dict[str, LiveStream] = {}
        # Streams replaced by a fresh session of the same provider: their last results still count.
        self.retiring: set[LiveStream] = set()

    async def run(self) -> None:
        await self._send({"type": "connected", "model": "realtime", "mode": "copilot_channels", "provider": self.provider})
        if not self.keys[self.provider]:
            await self._send({"type": "Error", "provider": self.provider, "error": f"{self.provider} API key not configured"})
            return
        logger.info(
            "Live channels: %s on %s in %s (language checks %s, profile %s)",
            self.labels,
            self.provider,
            self.sides[self.labels[0]].language,
            "on" if self.detect else "off",
            self.profile,
        )
        for label in self.labels:
            side = self.sides[label]
            self.active[label] = self._open(label, side.language, side.domain, offset_s=0.0)
            if self.shadow_provider:
                shadow = STREAMS[self.shadow_provider](
                    label, side.language, side.domain, vocab=self.vocab, offset_s=0.0, on_event=self._on_shadow
                )
                shadow.start(self.keys[self.shadow_provider] or "")
                self.shadows[label] = shadow
        limit = SESSION_LIMITS_S.get(self.provider)
        if limit:
            for label in self.labels:
                task = asyncio.create_task(self._roll_over(label, limit))
                self.checks.add(task)
                task.add_done_callback(self.checks.discard)
        try:
            await self._read_client()
        finally:
            await self._finish()

    async def _roll_over(self, label: str, limit: float) -> None:
        """Moves a side to a fresh session before the provider ends it, without a gap."""
        while not self.closing:
            await asyncio.sleep(limit)
            if self.closing:
                return
            old = self.active[label]
            side = self.sides[label]
            fresh = self._open(label, side.language, side.domain, offset_s=self.report.heard(label))
            self.active[label] = fresh
            self.retiring.add(old)
            old.end()
            logger.info("Live channels: %s moved to a fresh %s session at %.0fs", label, self.provider, fresh.offset_s)

    def _open(self, label: str, language: str, domain: Optional[str], *, offset_s: float) -> LiveStream:
        stream = STREAMS[self.provider](label, language, domain, vocab=self.vocab, offset_s=offset_s, on_event=self._on_stream)
        stream.start(self.keys[self.provider] or "")
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
        for stream in [*self.active.values(), *self.shadows.values()]:
            stream.end()
        current = list(self.active.values())
        try:
            await asyncio.wait_for(asyncio.gather(*(s.finished.wait() for s in current)), FINISH_TIMEOUT_S)
        except asyncio.TimeoutError:
            logger.warning("Live channels: a stream did not finish in %ss", FINISH_TIMEOUT_S)
        if self.shadows:
            await asyncio.wait({s.task for s in self.shadows.values() if s.task}, timeout=3.0)
        for task in self.checks:
            task.cancel()
        try:
            await self._send({"type": "EndOfTranscript"})
        except Exception:
            pass
        for stream in [*self.streams, *self.shadows.values()]:
            if stream.task and not stream.task.done():
                stream.task.cancel()
            seconds = stream.billed_seconds()
            if seconds:
                # Fire and forget: the ledger writes in a thread, other calls keep streaming.
                tier = "enhanced" if stream.provider == "speechmatics" else ""
                record_stt_usage(stream.provider, "realtime", seconds, channels=1, tier=tier)
            if isinstance(stream, MaiStream):
                logger.info("Live channels: %s sent %.0fs of %.0fs to MAI", stream.label, stream.fed_s, stream.heard_s)
        self.report.log(self.user_id, {label: side.language for label, side in self.sides.items()})

    async def _send(self, payload: dict[str, Any]) -> None:
        async with self.send_lock:
            await self.client.send_json(payload)

    async def _on_shadow(self, stream: LiveStream, event: dict[str, Any]) -> None:
        if event["kind"] in ("partial", "final") and event.get("end") is not None and (event.get("transcript") or "").strip():
            self.report.result(
                stream.provider,
                stream.label,
                final=event["kind"] == "final",
                start=event.get("start"),
                end=event["end"],
                text=apply_glossary(event.get("transcript") or "", self.terms, self.sounds),
                timed=event.get("timed", True),
                settle_s=event.get("settle_s"),
            )
        elif event["kind"] == "error":
            logger.warning("Live comparison %s %s stopped: %s", stream.provider, stream.label, event.get("reason"))

    async def _on_stream(self, stream: LiveStream, event: dict[str, Any]) -> None:
        if self.active.get(stream.label) is not stream and stream not in self.retiring:
            return  # replaced by a stream in the side's real language
        kind = event["kind"]
        if kind in ("partial", "final"):
            transcript = apply_glossary(event.get("transcript") or "", self.terms, self.sounds)
            words = event.get("words") or []
            if not transcript and not words:
                return
            final = kind == "final"
            payload: dict[str, Any] = {
                "type": "Results",
                "provider": stream.provider,
                "is_final": final,
                "channel": {"alternatives": [{"transcript": transcript, "confidence": 0.99 if final else 0.5}]},
                "audio_channel": stream.label,
                "language": stream.language,
            }
            if words:
                payload["words"] = words
            if event.get("start") is not None:
                payload["start"] = event["start"]
                payload["end"] = event.get("end", event["start"])
            await self._send(payload)
            if "end" in payload:
                self.report.result(
                    stream.provider,
                    stream.label,
                    final=final,
                    start=payload["start"],
                    end=payload["end"],
                    text=transcript,
                    timed=event.get("timed", True) and payload["end"] > stream.live_from_s,
                    settle_s=event.get("settle_s"),
                )
            if final and transcript.strip() and "start" in payload:
                self._after_final(stream.label, payload["start"], payload["end"])
        elif kind == "utterance_end":
            await self._send(
                {
                    "type": "EndOfUtterance",
                    "forced": event.get("forced", False),
                    "start_time": event.get("start"),
                    "end_time": event.get("end"),
                    "audio_channel": stream.label,
                }
            )
        elif kind == "error":
            reason = event.get("reason") or "Unknown error"
            logger.error("%s %s error: %s", stream.provider, stream.label, reason)
            await self._send({"type": "Error", "provider": stream.provider, "error": reason})
        elif kind == "warning":
            logger.warning("%s %s warning: %s", stream.provider, stream.label, event.get("reason"))

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
