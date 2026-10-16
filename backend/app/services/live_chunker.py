"""Cuts one side's live audio into chunks for a request/response transcriber.

A chunk is a stretch of speech with a little audio before it (so its first syllable isn't cut). It closes once the side has
been quiet for PAUSE_S, or has spoken for MAX_S without a pause. Measured on real recordings (MAI-2 through OpenRouter):
0.3 s / 10 s gave the text of a sentence in 0.75 s after it ended, with the fewest words cut in two.

Pure and synchronous: it works on the audio fed to it (16 kHz PCM16), never on the clock, so it behaves the same when a
restart replays audio faster than real time.
"""

from __future__ import annotations

from array import array
from collections import deque
from dataclasses import dataclass
from typing import Optional

SAMPLE_RATE = 16000
BYTES_PER_SECOND = SAMPLE_RATE * 2
FRAME_S = 0.02
FRAME_BYTES = int(SAMPLE_RATE * FRAME_S) * 2

PAUSE_S = 0.3
MAX_S = 10.0
PRE_ROLL_S = 0.4
# Less speech than this is a click or a breath, not words ("sí" is about 0.3 s).
MIN_SPEECH_S = 0.3
# A chunk of speech shorter than MIN_SPEECH_S waits this long for more speech to join it before it is dropped.
BLIP_WAIT_S = 1.0
# The bubbles ("someone is speaking") show once this much speech has been heard, so a cough doesn't flicker one.
ANNOUNCE_S = 0.15

# What counts as speech: the same as the MAI streaming side (RMS of PCM16; a room's own noise floor raises it).
SPEECH_RMS = 100
SPEECH_RMS_MAX = 250
NOISE_FACTOR = 2.5
NOISE_WINDOW_FRAMES = 1000
NOISE_MIN_FRAMES = 250


@dataclass
class Chunk:
    pcm: bytes
    start_s: float  # when its speech began, in seconds since the side began
    end_s: float  # when its speech ended
    speech_s: float
    trigger: str  # pause | max | end | force

    @property
    def seconds(self) -> float:
        return len(self.pcm) / BYTES_PER_SECOND


def frame_level(frame: bytes) -> float:
    samples = array("h")
    samples.frombytes(frame[: len(frame) - len(frame) % 2])
    if not samples:
        return 0.0
    return (sum(x * x for x in samples) / len(samples)) ** 0.5


class ChunkCutter:
    def __init__(
        self,
        *,
        offset_s: float = 0.0,
        pause_s: float = PAUSE_S,
        max_s: float = MAX_S,
        min_speech_s: float = MIN_SPEECH_S,
        pre_roll_s: float = PRE_ROLL_S,
    ) -> None:
        self.offset_s = offset_s
        self.pause_s = pause_s
        self.max_s = max_s
        self.min_speech_s = min_speech_s
        self.pre_roll_s = pre_roll_s
        self.heard_s = 0.0
        self.levels: deque[float] = deque(maxlen=NOISE_WINDOW_FRAMES)
        self._rest = b""
        self._pre: deque[bytes] = deque()
        self._pre_s = 0.0
        self._reset()

    def _reset(self) -> None:
        self._cur: list[bytes] = []
        self._speech_s = 0.0
        self._quiet_s = 0.0
        self._onset_s: Optional[float] = None
        self._last_loud_end_s = 0.0
        self.announced = False

    @property
    def open(self) -> bool:
        """Speech is being gathered (it may still turn out to be a blip)."""
        return bool(self._cur)

    def threshold(self) -> float:
        if len(self.levels) < NOISE_MIN_FRAMES:
            return SPEECH_RMS
        ordered = sorted(self.levels)
        floor = ordered[len(ordered) // 4]
        return min(SPEECH_RMS_MAX, max(SPEECH_RMS, NOISE_FACTOR * floor))

    def feed(self, pcm: bytes) -> tuple[list[Chunk], Optional[bool]]:
        """Chunks that closed, and whether the side started (True) or stopped (False) speaking in this audio."""
        chunks: list[Chunk] = []
        change: Optional[bool] = None
        data = self._rest + pcm
        usable = len(data) - len(data) % FRAME_BYTES
        self._rest = data[usable:]
        for i in range(0, usable, FRAME_BYTES):
            chunk, said = self._frame(data[i : i + FRAME_BYTES])
            if chunk:
                chunks.append(chunk)
            if said is not None:
                change = said
        return chunks, change

    def flush(self, trigger: str) -> tuple[Optional[Chunk], bool]:
        """The speech gathered so far, closed now (end of the call, or the client asked). Second value: it was announced."""
        was = self.announced
        chunk = None
        if self._cur and self._speech_s >= min(self.min_speech_s, 0.2):
            chunk = self._close(trigger)
        else:
            self._reset()
        return chunk, was

    def _close(self, trigger: str) -> Chunk:
        chunk = Chunk(
            pcm=b"".join(self._cur),
            start_s=self.offset_s + (self._onset_s or 0.0),
            end_s=self.offset_s + self._last_loud_end_s,
            speech_s=self._speech_s,
            trigger=trigger,
        )
        self._reset()
        return chunk

    def _frame(self, frame: bytes) -> tuple[Optional[Chunk], Optional[bool]]:
        start = self.heard_s
        self.heard_s += FRAME_S
        level = frame_level(frame)
        self.levels.append(level)
        loud = level >= self.threshold()
        if not self._cur and not loud:
            self._pre.append(frame)
            self._pre_s += FRAME_S
            while self._pre_s > self.pre_roll_s + 1e-9 and len(self._pre) > 1:
                self._pre.popleft()
                self._pre_s -= FRAME_S
            return None, None
        if not self._cur:
            self._cur = list(self._pre)
            self._pre.clear()
            self._pre_s = 0.0
            self._onset_s = start
        if loud:
            self._speech_s += FRAME_S
            self._quiet_s = 0.0
            self._last_loud_end_s = self.heard_s
        else:
            self._quiet_s += FRAME_S
        self._cur.append(frame)
        said: Optional[bool] = None
        if not self.announced and self._speech_s >= ANNOUNCE_S - 1e-9:
            self.announced = True
            said = True
        if self._speech_s >= self.min_speech_s - 1e-9 and self._quiet_s >= self.pause_s - 1e-9:
            return self._ended(self._close("pause"))
        if len(self._cur) * FRAME_S >= self.max_s - 1e-9:
            # Still speaking: the next chunk begins at once, so the side stays "speaking".
            chunk = self._close("max")
            return chunk, said
        if self._speech_s < self.min_speech_s and self._quiet_s >= BLIP_WAIT_S - 1e-9:
            was = self.announced
            self._reset()
            return None, False if was else None
        return None, said

    def _ended(self, chunk: Chunk) -> tuple[Chunk, Optional[bool]]:
        return chunk, False
