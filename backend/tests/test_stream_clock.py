import numpy as np

from app.services.stream_clock import RATE, StreamClock


def _pcm(seconds: float, level: float = 0.0) -> bytes:
    return (np.random.default_rng(0).normal(0, level, int(seconds * RATE)) if level else np.zeros(int(seconds * RATE))).astype(np.int16).tobytes()


def _run(clock: StreamClock, mic_s: float, call: bytes) -> bytes:
    """The mic delivered `mic_s` seconds, and then the call's chunk arrives."""
    clock.heard_mic(_pcm(mic_s, 1000))
    return clock.call(call)


def test_a_call_that_hands_over_its_quiet_in_a_fraction_of_real_time_is_put_back_on_the_mic_clock():
    clock = StreamClock()
    sent = 0
    # The mic is real time; the call delivers 0.1 s of quiet every 0.35 s for 10 s (what a Mac does before anything plays).
    for step in range(1, int(10 / 0.35) + 1):
        out = _run(clock, 0.35, _pcm(0.1))
        sent += len(out) // 2
    # After the first chunk (when it is not yet known to be quiet) it is put back within a stall's length of the mic.
    assert abs(sent / RATE - 10) < 1.0
    assert 6.5 < clock.filled_s < 7.6  # 10 s on the mic less the 2.9 s of quiet the call handed over


def test_a_call_that_stalls_in_the_middle_of_sound_is_left_as_it_is():
    clock = StreamClock()
    out = clock.call(_pcm(0.1, 3000))  # sound
    clock.heard_mic(_pcm(1.2, 1000))  # then the call is 1.1 s late, which after sound is a stall, not lost time
    assert clock.call(_pcm(0.1, 3000)) == _pcm(0.1, 3000)
    assert clock.filled_s == 0
    assert out == _pcm(0.1, 3000)


def test_a_call_far_behind_is_put_back_even_after_sound():
    clock = StreamClock()
    clock.call(_pcm(0.1, 3000))
    clock.heard_mic(_pcm(5, 1000))  # 5 s later no stall explains it
    out = clock.call(_pcm(0.1, 3000))
    assert abs(len(out) // 2 / RATE - 4.9) < 0.25
    assert clock.filled_s > 4


def test_a_call_in_step_with_the_mic_is_untouched():
    clock = StreamClock()
    for _ in range(50):
        clock.heard_mic(_pcm(0.1, 1000))
        chunk = _pcm(0.1)
        assert clock.call(chunk) == chunk
    assert clock.filled_s == 0
