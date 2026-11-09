"""A desktop call's audio is kept by the live service and its memo is written from the whole call."""

import asyncio
import subprocess

import numpy as np
import pytest

from app.services import desktop_recording
from app.services.live_chunker import SAMPLE_RATE
from app.services.live_recording import CallRecorder


class FakeBucket:
    def __init__(self, store):
        self.store = store

    def upload(self, path, file, file_options=None):
        self.store[path] = bytes(file)

    def list(self, folder, options=None):
        search = (options or {}).get("search", "")
        return [{"name": p.split("/", 1)[1]} for p in self.store if p.startswith(folder + "/") and search in p]

    def download(self, path):
        return self.store[path]


class FakeStorage:
    def __init__(self):
        self.store = {}

    def from_(self, bucket):
        assert bucket == "call-recordings"
        return FakeBucket(self.store)


class FakeSupabase:
    def __init__(self):
        self.storage = FakeStorage()


def tone(seconds, hz):
    t = np.arange(int(seconds * SAMPLE_RATE)) / SAMPLE_RATE
    return (np.sin(2 * np.pi * hz * t) * 8000).astype("<i2").tobytes()


def channels_of(audio: bytes) -> int:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=channels", "-of", "csv=p=0", "-"], input=audio, capture_output=True)
    return int(out.stdout.decode().strip())


def test_a_session_is_stored_as_one_stereo_file_with_both_sides_in_step():
    db = FakeSupabase()
    rec = CallRecorder.for_session("user-1", "cap-12345678", ["prospect", "rep"])
    rec.write("rep", tone(4.0, 220))
    rec.write("prospect", tone(3.0, 440))  # a side that ended a moment early is filled with silence
    path = asyncio.run(rec.finish(db))
    assert path and path.startswith("user-1/live-cap-12345678-") and path.endswith((".ogg", ".flac"))
    assert channels_of(db.storage.store[path]) == 2


def test_no_recording_without_an_id_or_a_signed_in_rep_or_both_sides():
    assert CallRecorder.for_session("user-1", None, ["prospect", "rep"]) is None
    assert CallRecorder.for_session(None, "cap-12345678", ["prospect", "rep"]) is None
    assert CallRecorder.for_session("user-1", "cap-12345678", ["rep"]) is None
    assert CallRecorder.for_session("user-1", "../../etc", ["prospect", "rep"]) is None


def test_a_session_too_short_to_hold_speech_is_not_stored():
    db = FakeSupabase()
    rec = CallRecorder.for_session("user-1", "cap-12345678", ["prospect", "rep"])
    rec.write("rep", tone(1.0, 220))
    assert asyncio.run(rec.finish(db)) is None and db.storage.store == {}


@pytest.fixture
def quick(monkeypatch):
    monkeypatch.setattr(desktop_recording, "POLL_S", 0.01)


def _stored(db, user, cap, start, end):
    rec = CallRecorder(user, cap)
    rec.started_ms = start
    rec.write("rep", tone(4.0, 220))
    rec.write("prospect", tone(4.0, 440))
    path = asyncio.run(rec.finish(db))
    # Name it as if it ran from start to end.
    data = db.storage.store.pop(path)
    ext = path.rsplit(".", 1)[1]
    new = f"{user}/live-{cap}-{start}-{end}.{ext}"
    db.storage.store[new] = data
    return new


def test_the_memo_is_written_from_the_whole_call(monkeypatch, quick):
    db = FakeSupabase()
    path = _stored(db, "u1", "cap-12345678", 1_700_000_000_000, 1_700_000_300_000)
    seen = {}

    async def transcribe_audio(audio, **kwargs):
        seen.update(kwargs, channels=channels_of(audio))

        class R:
            text = "SPEAKER: S1\nHola Gabriel, ¿qué tal?\n\nSPEAKER: S2\nBien, todo lo tenemos interno."
            model = "microsoft/mai-transcribe-2"

        return R()

    monkeypatch.setattr("app.services.stt_batch.transcribe_audio", transcribe_audio)
    whole = asyncio.run(desktop_recording.whole_call_transcript(
        db, user_id="u1", capture_id="cap-12345678", sent_at_ms=1_700_000_301_000, live_transcript="SPEAKER: S1\nHola"))
    assert whole and "todo lo tenemos interno" in whole.transcript and whole.recording_path == path
    assert seen["source"] == "desktop_call" and seen["rep_channel"] == 0 and seen["channels"] == 2


def test_a_call_whose_connection_came_back_is_put_back_together_in_order(monkeypatch, quick):
    db = FakeSupabase()
    _stored(db, "u1", "cap-12345678", 1_700_000_000_000, 1_700_000_100_000)
    _stored(db, "u1", "cap-12345678", 1_700_000_110_000, 1_700_000_200_000)
    lengths = []

    async def transcribe_audio(audio, **kwargs):
        lengths.append(len(audio))

        class R:
            text = "SPEAKER: S1\nUno dos tres."
            model = "m"

        return R()

    monkeypatch.setattr("app.services.stt_batch.transcribe_audio", transcribe_audio)
    whole = asyncio.run(desktop_recording.whole_call_transcript(
        db, user_id="u1", capture_id="cap-12345678", sent_at_ms=1_700_000_201_000, live_transcript=""))
    assert whole and whole.recording_path == "u1/live-cap-12345678-call." + whole.recording_path.rsplit(".", 1)[1]
    assert len(lengths) == 1  # one transcription of the joined call


def test_no_recording_keeps_the_live_transcript(quick, monkeypatch):
    monkeypatch.setattr(desktop_recording, "WAIT_S", 0.05)
    whole = asyncio.run(desktop_recording.whole_call_transcript(
        FakeSupabase(), user_id="u1", capture_id="cap-12345678", sent_at_ms=1, live_transcript="x"))
    # (wait_s is long in production; here the poll finds nothing and the deadline is what ends it)
    assert whole is None


def test_a_whole_call_much_shorter_than_the_live_one_is_not_trusted(monkeypatch, quick):
    db = FakeSupabase()
    _stored(db, "u1", "cap-12345678", 1_700_000_000_000, 1_700_000_300_000)

    async def transcribe_audio(audio, **kwargs):
        class R:
            text = "SPEAKER: S1\nHola."
            model = "m"

        return R()

    monkeypatch.setattr("app.services.stt_batch.transcribe_audio", transcribe_audio)
    live = "SPEAKER: S1\n" + " ".join(["palabra"] * 80)
    assert asyncio.run(desktop_recording.whole_call_transcript(
        db, user_id="u1", capture_id="cap-12345678", sent_at_ms=1_700_000_301_000, live_transcript=live)) is None
