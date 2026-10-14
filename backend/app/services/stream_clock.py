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
"""

from __future__ import annotations

import numpy as np

RATE = 16000
# Behind the mic by more than this, after quiet, the call was quiet for that long.
HOLE_MIN_S = 0.4
# Behind by more than this, no stall explains it, whatever the call last sounded like.
HOLE_SURE_S = 3.0
# The last 100 ms of a call chunk below this is quiet (16-bit RMS).
QUIET_RMS = 300.0


class StreamClock:
    """One per call. Tell it what the mic delivered, pass what the call delivered through it."""

    def __init__(self) -> None:
        self._mic = 0
        self._call = 0
        self._quiet = False  # unknown until a chunk of the call has been heard
        self.filled_s = 0.0

    def heard_mic(self, pcm: bytes) -> None:
        self._mic += len(pcm) // 2

    def call(self, pcm: bytes) -> bytes:
        """The call's chunk, with the silence it missed put back in front of it."""
        samples = np.frombuffer(pcm[: len(pcm) - len(pcm) % 2], dtype=np.int16)
        # The chunk that just arrived ends about where the mic's samples do.
        behind = self._mic - samples.size - self._call
        fill = 0
        if behind > RATE * HOLE_MIN_S and (self._quiet or behind > RATE * HOLE_SURE_S):
            fill = behind
            self.filled_s += fill / RATE
        tail = samples[-RATE // 10 :]
        self._quiet = bool(tail.size) and float(np.sqrt(np.mean(tail.astype(np.float64) ** 2))) < QUIET_RMS
        self._call += fill + samples.size
        return bytes(fill * 2) + pcm if fill else pcm
