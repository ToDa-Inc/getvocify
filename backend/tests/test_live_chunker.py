from array import array

from app.services.live_chunker import (
    BYTES_PER_SECOND,
    MAX_S,
    PAUSE_S,
    PRE_ROLL_S,
    SPEECH_RMS_MAX,
    ChunkCutter,
)


def tone(seconds: float, level: int = 3000) -> bytes:
    n = int(seconds * 16000)
    return array("h", [level if i % 2 else -level for i in range(n)]).tobytes()


def quiet(seconds: float) -> bytes:
    return bytes(int(seconds * 16000) * 2)


def run(cutter: ChunkCutter, *parts: bytes):
    chunks, changes = [], []
    for part in parts:
        # the client sends 100 ms pieces
        for i in range(0, len(part), 3200):
            out, change = cutter.feed(part[i : i + 3200])
            chunks += out
            if change is not None:
                changes.append(change)
    return chunks, changes


def test_a_chunk_closes_after_the_pause_and_keeps_a_little_before_the_speech():
    cutter = ChunkCutter()
    chunks, changes = run(cutter, quiet(1.0), tone(1.0), quiet(0.5))
    assert len(chunks) == 1
    chunk = chunks[0]
    assert chunk.trigger == "pause"
    assert abs(chunk.start_s - 1.0) < 0.03 and abs(chunk.end_s - 2.0) < 0.03
    # pre-roll + speech + the pause that closed it
    assert abs(chunk.seconds - (PRE_ROLL_S + 1.0 + PAUSE_S)) < 0.05
    # someone started speaking, then stopped
    assert changes == [True, False]


def test_continuous_speech_is_cut_at_the_maximum_and_goes_on():
    cutter = ChunkCutter()
    chunks, _ = run(cutter, tone(25.0))
    assert [c.trigger for c in chunks] == ["max", "max"]
    assert all(abs(c.seconds - MAX_S) < 0.05 for c in chunks)
    last, _ = cutter.flush("end")
    assert last is not None and abs(last.seconds - 5.0) < 0.1 and last.trigger == "end"


def test_a_click_is_not_speech_and_does_not_show_as_someone_speaking():
    cutter = ChunkCutter()
    chunks, changes = run(cutter, quiet(0.5), tone(0.1), quiet(2.0))
    assert chunks == [] and changes == []
    assert not cutter.open


def test_a_short_word_is_still_a_chunk():
    cutter = ChunkCutter()
    chunks, _ = run(cutter, quiet(0.6), tone(0.35), quiet(0.6))
    assert len(chunks) == 1 and chunks[0].speech_s >= 0.3


def test_a_blip_joins_the_speech_that_follows_it_within_a_second():
    cutter = ChunkCutter()
    chunks, _ = run(cutter, quiet(0.6), tone(0.2), quiet(0.5), tone(1.0), quiet(0.5))
    assert len(chunks) == 1
    assert chunks[0].speech_s > 1.1


def test_the_end_of_the_call_closes_the_speech_gathered_so_far():
    cutter = ChunkCutter()
    run(cutter, quiet(0.6), tone(0.8))
    chunk, announced = cutter.flush("end")
    assert chunk is not None and announced
    assert abs(chunk.end_s - 1.4) < 0.03
    assert cutter.flush("end")[0] is None


def test_a_stream_that_began_later_times_its_chunks_from_its_offset():
    cutter = ChunkCutter(offset_s=30.0)
    chunks, _ = run(cutter, quiet(1.0), tone(1.0), quiet(0.5))
    assert abs(chunks[0].start_s - 31.0) < 0.03 and abs(chunks[0].end_s - 32.0) < 0.03


def test_a_noisy_room_raises_what_counts_as_speech_but_speech_still_cuts_chunks():
    cutter = ChunkCutter()
    run(cutter, tone(6.0, level=200))  # steady noise, above the base level
    assert 100 < cutter.threshold() <= SPEECH_RMS_MAX
    chunks, _ = run(cutter, tone(1.0, level=3000), tone(0.6, level=200))
    assert chunks and chunks[-1].trigger == "pause"
