"""Keeps the two sides of a call on one clock.

A call's two streams (the rep's mic and what the computer plays) are sent in real time, and each side's transcript is
timed from its own first sample, so a sample count is a time. That only holds while a side delivers a second of audio
per second. The call's side does not always: a computer that plays nothing hands over its audio in a fraction of real
time until something plays (measured on a Mac: 11 s of audio in the first 20 s of a recording), and a loopback that skips
quiet hands over nothing at all. The call's transcript then runs seconds behind the mic's, so a word the mic heard from the
speakers is timed seconds away from the same word on the call's side, and neither the echo removal nor the text filter that
drops it, nor the order of the saved memo, can line the two up.

The mic's own count of samples is the clock (both sides of one call arrive together). A call that is behind it after a
stretch of quiet was quiet for that long, so the time is put back as silence. After sound it is not (a stall delivers the
audio late, it does not lose it), unless it is so far behind that no stall is.

The mic can lose audio too, and then it is the mic that falls behind the call. Measured on a real recording in the app:
the mic delivered 1.3 s less audio than time elapsed within 10 s (3 s over 110 s) with no gap in its chunks (the page's
audio thread dropped blocks while the machine was busy), while the call stayed within 0.1 s of real time. Every lost
fraction of a second moved the mic against the call's audio, the delay the echo removal had locked was no longer
right from then on, and by 45 s there was no match left within a second and a half. A page stall delays both sides
alike, so a mic behind the call by this much lost audio, and the time is put back as silence in front of its next chunk.
"""

from __future__ import annotations

import numpy as np

RATE = 16000
# Behind the mic by more than this, after quiet, the call was quiet for that long.
HOLE_MIN_S = 0.4
# Behind by more than this, no stall explains it, whatever the call last sounded like.
HOLE_SURE_S = 3.0
# The mic behind the call by more than this lost audio (chunks of both sides arrive together, within a few hundred ms).
MIC_LOST_MIN_S = 0.35
# The last 100 ms of a call chunk below this is quiet (16-bit RMS).
QUIET_RMS = 300.0


class StreamClock:
    """One per call. Tell it what the mic delivered, pass what the call delivered through it."""

    def __init__(self) -> None:
        self._mic = 0
        self._call = 0
        self._quiet = False  # unknown until a chunk of the call has been heard
        self.filled_s = 0.0
        self.mic_filled_s = 0.0

    def mic(self, pcm: bytes) -> bytes:
        """The mic's chunk, with the audio it lost put back as silence in front of it."""
        samples = len(pcm) // 2
        lost = self._call - self._mic - samples
        fill = 0
        if lost > RATE * MIC_LOST_MIN_S:
            fill = lost
            self.mic_filled_s += fill / RATE
        self._mic += fill + samples
        return bytes(fill * 2) + pcm if fill else pcm

    def call(self, pcm: bytes) -> bytes:
        """The call's chunk, with the silence it missed put back in front of it."""
        samples = np.frombuffer(pcm[: len(pcm) - len(pcm) % 2], dtype=np.int16)
        # The chunk that just arrived ends about where the mic's samples do.
        behind = self._mic - samples.size - self._call
        fill = 0
        # The very first chunk is where the call began: whatever the mic had heard before it, the call did not exist yet.
        first = self._call == 0
        if behind > RATE * HOLE_MIN_S and (first or self._quiet or behind > RATE * HOLE_SURE_S):
            fill = behind
            self.filled_s += fill / RATE
        tail = samples[-RATE // 10 :]
        self._quiet = bool(tail.size) and float(np.sqrt(np.mean(tail.astype(np.float64) ** 2))) < QUIET_RMS
        self._call += fill + samples.size
        return bytes(fill * 2) + pcm if fill else pcm
