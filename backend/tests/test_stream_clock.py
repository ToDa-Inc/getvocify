import numpy as np

from app.services.stream_clock import RATE, StreamClock


def _pcm(seconds: float, level: float = 0.0) -> bytes:
    return (np.random.default_rng(0).normal(0, level, int(seconds * RATE)) if level else np.zeros(int(seconds * RATE))).astype(np.int16).tobytes()


def _run(clock: StreamClock, mic_s: float, call: bytes) -> bytes:
    """The mic delivered `mic_s` seconds, and then the call's chunk arrives."""
    clock.mic(_pcm(mic_s, 1000))
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
    clock.mic(_pcm(1.2, 1000))  # then the call is 1.1 s late, which after sound is a stall, not lost time
    assert clock.call(_pcm(0.1, 3000)) == _pcm(0.1, 3000)
    assert clock.filled_s == 0
    assert out == _pcm(0.1, 3000)


def test_a_call_far_behind_is_put_back_even_after_sound():
    clock = StreamClock()
    clock.call(_pcm(0.1, 3000))
    clock.mic(_pcm(5, 1000))  # 5 s later no stall explains it
    out = clock.call(_pcm(0.1, 3000))
    assert abs(len(out) // 2 / RATE - 4.9) < 0.25
    assert clock.filled_s > 4


def test_a_call_in_step_with_the_mic_is_untouched():
    clock = StreamClock()
    for _ in range(50):
        clock.mic(_pcm(0.1, 1000))
        chunk = _pcm(0.1)
        assert clock.call(chunk) == chunk
    assert clock.filled_s == 0


def test_the_first_chunk_of_a_call_that_began_after_the_mic_is_placed_where_it_began():
    clock = StreamClock()
    clock.mic(_pcm(0.9, 1000))
    chunk = _pcm(0.1, 3000)  # loud from its very first sample: not quiet, not a stall, simply where the call began
    out = clock.call(chunk)
    assert abs(len(out) // 2 / RATE - 0.9) < 0.05
    assert clock.filled_s > 0.75
    # And only once: later chunks are in step.
    clock.mic(_pcm(0.1, 1000))
    assert clock.call(chunk) == chunk


def test_a_mic_that_loses_audio_is_put_back_on_the_clock_of_the_call():
    clock = StreamClock()
    sent = 0
    # The call is real time; the mic drops 1 s of every 10 s with no gap in its chunks (as measured on a real recording).
    for step in range(100):
        clock.call(_pcm(0.1, 1000))
        if step % 10 != 9:  # the 10th mic chunk of every ten never arrives
            sent += len(clock.mic(_pcm(0.1, 1000))) // 2
    assert abs(sent / RATE - 10) < 0.6
    assert clock.mic_filled_s > 0.5


def test_a_mic_in_step_with_the_call_is_untouched():
    clock = StreamClock()
    for _ in range(50):
        clock.call(_pcm(0.1, 1000))
        chunk = _pcm(0.1, 1000)
        assert clock.mic(chunk) == chunk
    assert clock.mic_filled_s == 0
