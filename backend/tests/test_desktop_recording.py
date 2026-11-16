"""A desktop call's audio is kept by the live service and attached to its memo, never transcribed again."""

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


class FakeTable:
    def __init__(self, db):
        self.db = db

    def update(self, payload):
        self.payload = payload
        return self

    def eq(self, column, value):
        self.id = value
        return self

    def execute(self):
        self.db.memos[self.id] = self.payload


class FakeSupabase:
    def __init__(self):
        self.storage = FakeStorage()
        self.memos = {}

    def table(self, name):
        assert name == "memos"
        return FakeTable(self)


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


def _no_transcription(monkeypatch):
    async def transcribe_audio(*args, **kwargs):
        raise AssertionError("a desktop call is not transcribed a second time")

    monkeypatch.setattr("app.services.stt_batch.transcribe_audio", transcribe_audio)


def test_the_recording_is_attached_to_the_memo_without_transcribing_it(monkeypatch, quick):
    _no_transcription(monkeypatch)
    db = FakeSupabase()
    path = _stored(db, "u1", "cap-12345678", 1_700_000_000_000, 1_700_000_300_000)
    asyncio.run(desktop_recording.attach_recording(db, "m1", user_id="u1", capture_id="cap-12345678", sent_at_ms=1_700_000_301_000))
    assert db.memos["m1"] == {"recording_path": path, "audio_duration": 300.0}


def test_a_call_whose_connection_came_back_is_put_back_together_in_order(monkeypatch, quick):
    _no_transcription(monkeypatch)
    db = FakeSupabase()
    _stored(db, "u1", "cap-12345678", 1_700_000_000_000, 1_700_000_100_000)
    _stored(db, "u1", "cap-12345678", 1_700_000_110_000, 1_700_000_200_000)
    asyncio.run(desktop_recording.attach_recording(db, "m1", user_id="u1", capture_id="cap-12345678", sent_at_ms=1_700_000_201_000))
    path = db.memos["m1"]["recording_path"]
    assert path.startswith("u1/live-cap-12345678-call.") and path in db.storage.store
    assert channels_of(db.storage.store[path]) == 2 and db.memos["m1"]["audio_duration"] == 190.0


def test_no_recording_leaves_the_memo_as_it_is(quick, monkeypatch):
    monkeypatch.setattr(desktop_recording, "WAIT_S", 0.05)
    db = FakeSupabase()
    asyncio.run(desktop_recording.attach_recording(db, "m1", user_id="u1", capture_id="cap-12345678", sent_at_ms=1))
    assert db.memos == {}
