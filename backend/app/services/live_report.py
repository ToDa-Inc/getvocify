"""How a live call's transcription performed, saved once the call ends (live_call_reports).

Speed is measured per side as the time between the audio reaching the service and the text
for it coming back: a partial's lag is how long the bubble waits for words, a final's is how
long until they stop changing. Network time to and from the Mac is not in it.

With LIVE_COMPARE_DEEPGRAM on, each side's audio also goes to Deepgram Nova-3 in parallel and
its text and speed are saved next to Speechmatics', so both can be read against the same call.
Deepgram never reaches the client: the call keeps running on Speechmatics only.
"""

from __future__ import annotations

import asyncio
import bisect
import json
import logging
import time
from typing import Any, Optional
from urllib.parse import urlencode

import websockets

logger = logging.getLogger(__name__)

BYTES_PER_SECOND = 16000 * 2
DEEPGRAM_LIVE_URL = "wss://api.deepgram.com/v1/listen"
# Nova-3 `multi` code-switches between these; anything else is transcribed in its own language.
DEEPGRAM_MULTI = {"en", "es", "fr", "de", "hi", "ru", "pt", "ja", "it", "nl"}
MAX_KEYTERMS = 50


def percentiles(values: list[float]) -> Optional[dict[str, float]]:
    if not values:
        return None
    ordered = sorted(values)

    def at(q: float) -> float:
        return round(ordered[min(len(ordered) - 1, int(q * len(ordered)))], 2)

    return {"p50": at(0.5), "p90": at(0.9), "max": round(ordered[-1], 2), "n": len(ordered)}


class AudioClock:
    """When each second of one side's audio reached the service."""

    def __init__(self) -> None:
        self.seconds: list[float] = []
        self.times: list[float] = []
        self.total = 0.0

    def add(self, nbytes: int, now: float) -> None:
        self.total += nbytes / BYTES_PER_SECOND
        self.seconds.append(self.total)
        self.times.append(now)

    def lag(self, audio_end_s: float, now: float) -> Optional[float]:
        """Seconds since the audio up to `audio_end_s` had arrived."""
        i = bisect.bisect_left(self.seconds, audio_end_s - 0.01)
        if i >= len(self.times):
            return None
        return max(0.0, now - self.times[i])


class Track:
    """One provider on one side: its lags and its final text."""

    def __init__(self) -> None:
        self.partial_lags: list[float] = []
        self.final_lags: list[float] = []
        self.finals: list[tuple[float, float, str]] = []

    def summary(self) -> dict[str, Any]:
        return {
            "partial_lag_s": percentiles(self.partial_lags),
            "final_lag_s": percentiles(self.final_lags),
            "words": sum(len(text.split()) for _, _, text in self.finals),
        }


class LiveReport:
    def __init__(self, labels: list[str], *, compare: bool, service: str = "live") -> None:
        self.labels = labels
        self.compare = compare
        self.service = service
        # What the Mac measured: the delay the rep sees, network included.
        self.client: Optional[dict[str, Any]] = None
        self.started = time.monotonic()
        self.clocks = {label: AudioClock() for label in labels}
        self.tracks: dict[str, dict[str, Track]] = {
            provider: {label: Track() for label in labels}
            for provider in (["speechmatics", "deepgram"] if compare else ["speechmatics"])
        }
        self.restarts: list[dict[str, Any]] = []

    def audio(self, label: str, nbytes: int) -> None:
        self.clocks[label].add(nbytes, time.monotonic())

    def heard(self, label: str) -> float:
        return self.clocks[label].total

    def result(
        self,
        provider: str,
        label: str,
        *,
        final: bool,
        start: Optional[float],
        end: Optional[float],
        text: str,
        timed: bool = True,
    ) -> None:
        track = self.tracks.get(provider, {}).get(label)
        if track is None or end is None:
            return
        if timed:
            lag = self.clocks[label].lag(end, time.monotonic())
            if lag is not None:
                (track.final_lags if final else track.partial_lags).append(lag)
        if final and text.strip():
            track.finals.append((round(start if start is not None else end, 2), round(end, 2), text.strip()))

    def from_client(self, data: dict[str, Any]) -> None:
        lags = data.get("lag_s")
        if isinstance(lags, dict) and len(json.dumps(lags)) < 4000:
            self.client = {"lag_s": lags, "reconnects": data.get("reconnects")}

    def restarted(self, label: str, language: str, from_s: float) -> None:
        """Speechmatics sends this side's text from `from_s` again, in `language`."""
        self.restarts.append({"side": label, "language": language, "from_s": round(from_s, 1)})
        track = self.tracks["speechmatics"][label]
        track.finals = [f for f in track.finals if f[0] < from_s]

    def summary(self, languages: dict[str, str]) -> dict[str, Any]:
        return {
            "service": self.service,
            "client": self.client,
            "duration_s": round(time.monotonic() - self.started, 1),
            "audio_s": {label: round(clock.total, 1) for label, clock in self.clocks.items()},
            "languages": languages,
            "restarts": self.restarts,
            "providers": {
                provider: {label: track.summary() for label, track in sides.items()}
                for provider, sides in self.tracks.items()
            },
        }

    def save(self, user_id: Optional[str], languages: dict[str, str]) -> None:
        """Blocking: run in a thread. Never raises."""
        report = self.summary(languages)
        logger.info("Live report: %s", json.dumps(report))
        if self.compare:
            report["transcripts"] = {
                provider: {label: track.finals for label, track in sides.items()}
                for provider, sides in self.tracks.items()
            }
        try:
            from app.deps import get_supabase

            get_supabase().table("live_call_reports").insert(
                {"user_id": user_id if user_id and user_id != "anonymous" else None, "report": report}
            ).execute()
        except Exception as e:
            logger.warning("Live report not saved: %s", e)


class DeepgramShadow:
    """One side's audio to Deepgram Nova-3, results to the report only. Failures stay here."""

    def __init__(self, label: str, language: str, keyterms: list[str], api_key: str, report: LiveReport) -> None:
        self.label = label
        self.language = "multi" if language in DEEPGRAM_MULTI else language
        self.keyterms = keyterms[:MAX_KEYTERMS]
        self.api_key = api_key
        self.report = report
        self.queue: asyncio.Queue = asyncio.Queue()
        self.started_at: Optional[float] = None
        self.ended_at: Optional[float] = None
        self.task = asyncio.create_task(self._run())

    def feed(self, pcm: bytes) -> None:
        self.queue.put_nowait(pcm)

    def end(self) -> None:
        self.queue.put_nowait(None)

    def url(self) -> str:
        params: list[tuple[str, str]] = [
            ("model", "nova-3"),
            ("language", self.language),
            ("encoding", "linear16"),
            ("sample_rate", "16000"),
            ("channels", "1"),
            ("interim_results", "true"),
            ("smart_format", "true"),
            ("punctuate", "true"),
            ("endpointing", "300"),
        ]
        params += [("keyterm", term) for term in self.keyterms]
        return f"{DEEPGRAM_LIVE_URL}?{urlencode(params)}"

    async def _run(self) -> None:
        try:
            async with websockets.connect(self.url(), additional_headers={"Authorization": f"Token {self.api_key}"}) as ws:
                self.started_at = time.monotonic()
                await asyncio.gather(self._send(ws), self._receive(ws))
        except Exception as e:
            logger.warning("Deepgram comparison %s (%s) stopped: %s", self.label, self.language, e)
        finally:
            self.ended_at = time.monotonic()

    async def _send(self, ws: Any) -> None:
        while True:
            item = await self.queue.get()
            if item is None:
                await ws.send(json.dumps({"type": "CloseStream"}))
                return
            await ws.send(item)

    async def _receive(self, ws: Any) -> None:
        async for raw in ws:
            data = json.loads(raw)
            if data.get("type") != "Results":
                continue
            alternatives = (data.get("channel") or {}).get("alternatives") or [{}]
            text = alternatives[0].get("transcript") or ""
            if not text:
                continue
            start = float(data.get("start") or 0.0)
            self.report.result(
                "deepgram",
                self.label,
                final=bool(data.get("is_final")),
                start=start,
                end=start + float(data.get("duration") or 0.0),
                text=text,
            )

    def billed_seconds(self) -> float:
        if not self.started_at:
            return 0.0
        return (self.ended_at or time.monotonic()) - self.started_at
