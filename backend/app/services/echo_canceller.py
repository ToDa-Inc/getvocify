"""Takes the call out of the rep's microphone when the meeting plays through speakers.

The desktop app captures both sides of a meeting natively: the mic (`rep`) and what the computer plays (`prospect`),
as 16 kHz mono PCM16. Through speakers the mic hears the call too, and the transcription then gives the other person's
words to the rep. Three steps:

1. Lining up. WebRTC's echo canceller only removes an echo whose reference (the call) reached it 0 to ~500 ms before
   the echo itself (measured on a real call: outside that window it removes ~5 dB instead of ~33 dB). How late the mic
   hears the call differs per computer: a Mac reading both on one clock hears it a steady 21 ms *before* the call
   audio arrives; two separate captures (Windows) can be hundreds of ms apart either way. So the delay is measured
   from the audio itself (GCC-PHAT, as anarlog does) and whichever side is ahead is held back just enough for the call
   to lead its echo by `LEAD_MS`. A new delay restarts the canceller, which learns the room again in about a second.
2. WebRTC's echo canceller (AEC3), with the call as its reference.
3. Level. A native mic has no automatic gain: on a MacBook it peaks ~14x lower than the browser's, and the speech
   threshold then drops the rep's quieter words. The cleaned mic is raised towards `TARGET_PEAK`, by at most
   `MAX_GAIN`, from its own loudest recent sound, so it never clips. (After the canceller: raising it before would
   change the echo the canceller is learning.)

It fails open: without the call's audio it only levels the mic.
"""

from __future__ import annotations

import numpy as np

RATE = 16000
FRAME = RATE // 100  # AEC3 works in 10 ms frames
# Where the call should sit before its echo, inside the 0-500 ms the canceller handles.
LEAD_MS = 150
# Neither side is held back longer than this (the mic when the call audio is late, the call when it is early).
MAX_HOLD_MS = 1000
# The held-back mic never waits longer than this for its call audio: past it, it goes on uncleaned (the call is late).
MAX_WAIT_MS = 1200

# Measuring the delay: over each `MEASURE_S` of both sides, lags up to `MAX_LAG_MS`. The stretches never overlap, so
# agreeing measures are separate evidence (overlapping ones once agreed on a wrong delay from one odd moment).
MEASURE_S = 3
MAX_LAG_MS = 1000
# A measure counts when the call is playing, the mic hears something, and the correlation peak stands out this much.
CALL_RMS = 300.0
MIC_RMS = 40.0
CONFIDENCE = 12.0
# Before any delay is taken, one measure this clear is enough: on a real call the echo measured 69 to 191, the one
# wrong delay ever taken 48.6. (Three agreeing measures take 9 s, and the call's echo goes through meanwhile.)
SURE = 60.0
# A new delay is taken after this many measures agree (within `AGREE_MS`), and only if it moves the lead this much.
AGREE = 3
AGREE_MS = 30
MOVE_MS = 60

TARGET_PEAK = 16000.0
MAX_GAIN = 8.0
# The loudest recent sound fades by half every `PEAK_HALF_LIFE_S`, so a loud moment lowers the gain only for a while.
PEAK_HALF_LIFE_S = 10.0


def _rms(x: np.ndarray) -> float:
    return float(np.sqrt(np.mean(x.astype(np.float64) ** 2))) if x.size else 0.0


def measure_lag(mic: np.ndarray, call: np.ndarray, max_lag: int) -> tuple[int, float]:
    """How many samples later the mic hears the call (negative: earlier), and how clearly (peak over mean)."""
    n = 1 << int(np.ceil(np.log2(mic.size + call.size)))
    cross = np.fft.rfft(mic.astype(np.float64), n) * np.conj(np.fft.rfft(call.astype(np.float64), n))
    cross /= np.abs(cross) + 1e-9
    corr = np.fft.irfft(cross, n)
    corr = np.abs(np.concatenate([corr[-max_lag:], corr[: max_lag + 1]]))
    best = int(np.argmax(corr))
    return best - max_lag, float(corr[best] / (corr.mean() + 1e-12))


class EchoCanceller:
    """One per recording. Feed both sides as they arrive; take the cleaned mic from `mic()`."""

    def __init__(self, *, lead_ms: int = LEAD_MS, max_gain: float = MAX_GAIN) -> None:
        from livekit import rtc

        self._rtc = rtc
        self._lead = RATE * lead_ms // 1000
        self._max_hold = RATE * MAX_HOLD_MS // 1000
        # Until a delay is measured: the call audio is taken to arrive with its echo (lag 0).
        self._hold = self._lead
        self._apm = self._new_apm()
        # The call by its own sample index: kept from MAX_HOLD behind the mic, so the hold can shrink again.
        self._ref = np.zeros(0, dtype=np.int16)
        self._ref_pos = 0
        self._mic = np.zeros(0, dtype=np.int16)  # mic not yet processed
        self._mic_pos = 0  # sample index of _mic[0]
        # Call audio still to come for a stretch the mic already went through without it: dropped when it arrives.
        self._late = 0
        # The last few seconds of each side as received, ending at sample `_heard[side]`.
        self._recent = {"mic": np.zeros(0, dtype=np.int16), "call": np.zeros(0, dtype=np.int16)}
        self._heard = {"mic": 0, "call": 0}
        self._next_measure = RATE * MEASURE_S
        self._votes: list[int] = []
        self._locked = False
        self._max_gain = max_gain
        self._peak = TARGET_PEAK / max_gain
        self._gain = max_gain
        self.stats = {"late_ms": 0, "lag_ms": None, "realigned": 0, "gain": max_gain}

    @staticmethod
    def _new_apm():
        from livekit import rtc

        return rtc.AudioProcessingModule(echo_cancellation=True, high_pass_filter=True)

    def _remember(self, side: str, samples: np.ndarray) -> None:
        # More than one stretch: the sides arrive chunk by chunk, so one is usually a little ahead of the other.
        keep = RATE * (MEASURE_S + MAX_WAIT_MS // 1000 + 1)
        self._recent[side] = np.concatenate([self._recent[side], samples])[-keep:]
        self._heard[side] += samples.size

    def call(self, pcm: bytes) -> None:
        samples = np.frombuffer(pcm, dtype=np.int16)
        self._remember("call", samples)
        if self._late:
            skip = min(self._late, samples.size)
            samples = samples[skip:]
            self._late -= skip
        self._ref = np.concatenate([self._ref, samples])

    def mic(self, pcm: bytes, *, wait: bool = True) -> bytes:
        """The mic audio that is ready, cleaned and leveled, in 10 ms frames: `_hold` behind the input when positive."""
        samples = np.frombuffer(pcm, dtype=np.int16)
        if samples.size:
            self._remember("mic", samples)
            self._measure()
        self._mic = np.concatenate([self._mic, samples])
        out: list[np.ndarray] = []
        while self._mic.size >= FRAME:
            # The reference for this frame is the call `_hold` later (earlier when negative): wait for it, unless told not to.
            start = self._mic_pos + self._hold - self._ref_pos
            if start < 0:
                # Older call audio than is kept (the call is held back further than before, or not heard yet): silence.
                self._ref = np.concatenate([np.zeros(-start, dtype=np.int16), self._ref])
                self._ref_pos += start
                start = 0
            if self._ref.size < start + FRAME:
                if wait and self._mic.size < RATE * MAX_WAIT_MS // 1000:
                    break
                missing = start + FRAME - self._ref.size
                self._ref = np.concatenate([self._ref, np.zeros(missing, dtype=np.int16)])
                self._late += missing
                self.stats["late_ms"] += missing * 1000 // RATE
            ref = self._ref[start : start + FRAME]
            frame = self._mic[:FRAME]
            self._mic = self._mic[FRAME:]
            self._mic_pos += FRAME
            # Older call audio is kept as far back as the hold may still shrink.
            drop = max(0, start + FRAME - self._max_hold)
            self._ref = self._ref[drop:]
            self._ref_pos += drop
            self._apm.process_reverse_stream(self._rtc.AudioFrame(ref.tobytes(), RATE, 1, FRAME))
            f = self._rtc.AudioFrame(frame.tobytes(), RATE, 1, FRAME)
            self._apm.process_stream(f)
            out.append(self._level(np.frombuffer(bytes(f.data), dtype=np.int16)))
        return np.concatenate(out).tobytes() if out else b""

    def flush(self) -> bytes:
        return self.mic(b"", wait=False)

    def _measure(self) -> None:
        """Every MEASURE_S of mic: where the call's echo sits in it, over the stretch both sides have."""
        if self._heard["mic"] < self._next_measure:
            return
        self._next_measure = self._heard["mic"] + RATE * MEASURE_S
        # The same stretch of both sides, ending where the side that is behind ends.
        end = min(self._heard["mic"], self._heard["call"])
        span = RATE * MEASURE_S
        window = {}
        for side, recent in self._recent.items():
            stop = recent.size - (self._heard[side] - end)
            if stop < span:
                return  # not enough of this side kept for that stretch yet
            window[side] = recent[stop - span : stop]
        mic, call = window["mic"], window["call"]
        if _rms(call) < CALL_RMS or _rms(mic) < MIC_RMS:
            return
        lag, confidence = measure_lag(mic, call, RATE * MAX_LAG_MS // 1000)
        if confidence < CONFIDENCE:
            return
        self._votes = [v for v in self._votes if abs(v - lag) <= RATE * AGREE_MS // 1000] + [lag]
        if len(self._votes) < AGREE and (self._locked or confidence < SURE):
            return
        self._locked = True
        lag = int(np.median(self._votes))
        self.stats["lag_ms"] = lag * 1000 // RATE
        # Negative: the call arrives that much too early, so it is the call that is held back.
        hold = int(np.clip(self._lead - lag, -self._max_hold, self._max_hold))
        if abs(hold - self._hold) >= RATE * MOVE_MS // 1000:
            self._hold = hold
            self._apm = self._new_apm()
            self.stats["realigned"] += 1

    def _level(self, frame: np.ndarray) -> np.ndarray:
        decay = 0.5 ** (frame.size / RATE / PEAK_HALF_LIFE_S)
        self._peak = max(float(np.abs(frame).max(initial=0)), self._peak * decay)
        # Only ever raised: a mic that is loud already stays as it is.
        gain = float(np.clip(TARGET_PEAK / max(self._peak, 1.0), 1.0, self._max_gain))
        # Lowered at once (a louder sound must never clip), raised across the frame (so it never clicks).
        ramp = np.linspace(self._gain, gain, frame.size, endpoint=False) if gain > self._gain else gain
        self._gain = gain
        self.stats["gain"] = round(gain, 2)
        return np.clip(frame * ramp, -32768, 32767).astype(np.int16)
