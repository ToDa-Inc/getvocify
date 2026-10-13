import numpy as np
import pytest

pytest.importorskip("livekit")

from app.services.echo_canceller import RATE, EchoCanceller


def _voice(seconds: float, seed: int, level: float = 3000) -> np.ndarray:
    """Speech-like: noise shaped by a syllable-rate envelope."""
    rng = np.random.default_rng(seed)
    t = np.arange(int(seconds * RATE)) / RATE
    envelope = (np.sin(2 * np.pi * 3.0 * t) > 0).astype(float) * 0.8 + 0.2
    return rng.normal(0, level, t.size) * envelope


def _shift(x: np.ndarray, ms: int) -> np.ndarray:
    """`x` that much later (earlier when negative), same length."""
    s = RATE * ms // 1000
    return np.concatenate([np.zeros(s), x])[: x.size] if s >= 0 else np.concatenate([x[-s:], np.zeros(-s)])


def _run(mic: np.ndarray, call: np.ndarray, **options) -> tuple[np.ndarray, EchoCanceller]:
    canceller = EchoCanceller(**options)
    out = []
    step = RATE // 10
    for i in range(0, mic.size, step):
        canceller.call(call[i : i + step].astype(np.int16).tobytes())
        out.append(canceller.mic(mic[i : i + step].astype(np.int16).tobytes()))
    out.append(canceller.flush())
    return np.frombuffer(b"".join(out), dtype=np.int16).astype(float), canceller


def _rms(x: np.ndarray) -> float:
    return float(np.sqrt(np.mean(x**2))) if x.size else 0.0


def _meeting(seconds: int, talk_s: int, echo_ms: int) -> tuple[np.ndarray, np.ndarray]:
    """The other side talks for `talk_s`, the mic hears it `echo_ms` later through the room, then the rep talks."""
    call = np.zeros(seconds * RATE)
    rep = np.zeros(seconds * RATE)
    call[: talk_s * RATE] = _voice(talk_s, 1)
    rep[(talk_s + 2) * RATE :] = _voice(seconds - talk_s - 2, 2)
    mic = np.clip(rep + 0.4 * _shift(call, echo_ms), -32768, 32767)
    return mic, call


def test_the_call_heard_through_speakers_is_taken_out_and_the_rep_is_kept():
    mic, call = _meeting(12, 6, 60)
    out, _ = _run(mic, call, max_gain=1)
    assert out.size == mic.size
    # Only the call's echo (after the canceller has had 2 s to learn the room): mostly gone.
    assert _rms(out[3 * RATE : 6 * RATE]) < 0.25 * _rms(mic[3 * RATE : 6 * RATE])
    # Only the rep: still there.
    assert _rms(out[9 * RATE : 12 * RATE]) > 0.6 * _rms(mic[9 * RATE : 12 * RATE])


@pytest.mark.parametrize("call_late_ms", [500, -800])
def test_call_audio_far_from_its_echo_is_lined_up(call_late_ms):
    # Two separate captures: the call's audio reaches us half a second after the mic heard it (or 0.8 s before).
    mic, call = _meeting(30, 24, 60)
    out, canceller = _run(mic, _shift(call, call_late_ms), max_gain=1)
    assert abs(canceller.stats["lag_ms"] - (60 - call_late_ms)) <= 20
    assert canceller.stats["realigned"] == 1
    # Once lined up (a few measures in), the echo is mostly gone, wherever the output sits in time.
    hold = max(canceller._hold, 0)
    late = out[hold:][16 * RATE : 24 * RATE]
    assert _rms(late) < 0.25 * _rms(mic[16 * RATE : 24 * RATE])


def test_the_delay_is_measured_when_one_side_arrives_ahead_of_the_other():
    # Over a socket the sides come chunk by chunk: here the call's audio is always half a second behind the mic's.
    mic, call = _meeting(20, 16, 60)
    canceller = EchoCanceller(max_gain=1)
    step = RATE // 10
    behind = 5
    for i in range(0, mic.size + behind * step, step):
        if i < mic.size:
            canceller.mic(mic[i : i + step].astype(np.int16).tobytes())
        j = i - behind * step
        if 0 <= j < call.size:
            canceller.call(call[j : j + step].astype(np.int16).tobytes())
    assert canceller.stats["lag_ms"] == 60


def test_one_clear_measure_is_enough_to_line_up_at_the_start():
    # The browser's mic hears the call ~390 ms after the call audio arrives: lined up after one measure, not three.
    mic, call = _meeting(12, 10, 390)
    _, canceller = _run(mic[: 4 * RATE], call[: 4 * RATE], max_gain=1)
    assert canceller.stats["realigned"] == 1
    assert abs(canceller.stats["lag_ms"] - 390) <= 20


def test_without_call_audio_the_mic_passes_through():
    mic = _voice(3, 3)
    out, _ = _run(mic, np.zeros_like(mic), max_gain=1)
    assert _rms(out[RATE:]) > 0.6 * _rms(mic[RATE:])


def test_a_quiet_mic_is_raised_and_a_loud_one_left_alone():
    quiet = _voice(4, 5, level=100)
    out, _ = _run(quiet, np.zeros_like(quiet))
    assert _rms(out[RATE:]) > 6 * _rms(quiet[RATE:])
    loud = np.clip(_voice(4, 6, level=6000), -32767, 32767)
    out, _ = _run(loud, np.zeros_like(loud))
    assert np.abs(out).max() < 32767
    assert _rms(out[RATE:]) == pytest.approx(_rms(loud[RATE : out.size]), rel=0.1)


def test_the_mic_never_waits_long_for_late_call_audio():
    canceller = EchoCanceller()
    voice = _voice(3, 4).astype(np.int16)
    out = b"".join(canceller.mic(voice[i : i + 1600].tobytes()) for i in range(0, voice.size, 1600))
    # No call audio at all: the mic still comes out, at most MAX_WAIT_MS behind.
    assert len(out) // 2 >= voice.size - RATE * 1400 // 1000
    # The call audio that turns up late lines up after the stretch the mic already went through.
    canceller.call(np.zeros(RATE * 4, dtype=np.int16).tobytes())
    assert canceller.stats["late_ms"] > 0
