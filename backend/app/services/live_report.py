"""How a live call's transcription performed, written to the service's logs when the call ends.

Speed is measured per side as the time between the audio reaching the service and the text
for it coming back: a partial's lag is how long the bubble waits for words, a final's is how
long until they stop changing. Network time to and from the Mac is not in it.

With LIVE_COMPARE_STT on, each side's audio also goes to the other provider (Speechmatics or
Deepgram) in parallel and its text and speed are logged next to the one the call uses, so both
can be read against the same call. The other provider never reaches the client.
"""

from __future__ import annotations

import bisect
import json
import logging
import time
import uuid
from typing import Any, Optional
logger = logging.getLogger(__name__)

BYTES_PER_SECOND = 16000 * 2
# Log lines stay well under the platform's per-line limit.
LOG_CHUNK = 6000


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
        # Providers without word times (MAI): from words first showing to settling.
        self.settle_lags: list[float] = []
        self.finals: list[tuple[float, float, str]] = []

    def summary(self) -> dict[str, Any]:
        return {
            "partial_lag_s": percentiles(self.partial_lags),
            "final_lag_s": percentiles(self.final_lags),
            "settle_s": percentiles(self.settle_lags),
            "words": sum(len(text.split()) for _, _, text in self.finals),
        }


class LiveReport:
    def __init__(self, labels: list[str], *, providers: list[str], service: str = "live") -> None:
        """`providers`: the one the call uses first, then the one compared with it, if any."""
        self.labels = labels
        self.providers = providers
        self.compare = len(providers) > 1
        self.service = service
        # What the Mac measured: the delay the rep sees, network included.
        self.client: Optional[dict[str, Any]] = None
        self.started = time.monotonic()
        self.clocks = {label: AudioClock() for label in labels}
        self.tracks: dict[str, dict[str, Track]] = {provider: {label: Track() for label in labels} for provider in providers}
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
        settle_s: Optional[float] = None,
    ) -> None:
        track = self.tracks.get(provider, {}).get(label)
        if track is None or end is None:
            return
        if timed:
            lag = self.clocks[label].lag(end, time.monotonic())
            if lag is not None:
                (track.final_lags if final else track.partial_lags).append(lag)
        if settle_s is not None:
            track.settle_lags.append(settle_s)
        if final and text.strip():
            track.finals.append((round(start if start is not None else end, 2), round(end, 2), text.strip()))

    def from_client(self, data: dict[str, Any]) -> None:
        lags = data.get("lag_s")
        if isinstance(lags, dict) and len(json.dumps(lags)) < 4000:
            self.client = {"lag_s": lags, "reconnects": data.get("reconnects")}

    def restarted(self, label: str, language: str, from_s: float) -> None:
        """The call's provider sends this side's text from `from_s` again, in `language`."""
        self.restarts.append({"side": label, "language": language, "from_s": round(from_s, 1)})
        track = self.tracks[self.providers[0]][label]
        track.finals = [f for f in track.finals if f[0] < from_s]

    def summary(self, languages: dict[str, str]) -> dict[str, Any]:
        return {
            "service": self.service,
            "provider": self.providers[0],
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

    def log(self, user_id: Optional[str], languages: dict[str, str]) -> None:
        """Writes the report to the service's logs: one summary line, then each side's text."""
        call = uuid.uuid4().hex[:8]
        logger.info("Live report %s user=%s %s", call, user_id, json.dumps(self.summary(languages)))
        if not self.compare:
            return
        for provider, sides in self.tracks.items():
            for label, track in sides.items():
                # One line per chunk: a line per sentence hits the platform's log rate limit.
                text = " ".join(f"[{start:.1f}] {words}" for start, _, words in sorted(track.finals))
                parts = [text[i : i + LOG_CHUNK] for i in range(0, len(text), LOG_CHUNK)] or [""]
                for n, part in enumerate(parts, 1):
                    logger.info("Live transcript %s %s %s %d/%d %s", call, provider, label, n, len(parts), part)
