"""A Vocify call stuck in `transcribing` is transcribed again from its stored recording, at most twice.

Before, every memo stuck in `transcribing` was failed with "Audio is not stored", including calls whose
WAV sits in the call-recordings bucket: a restart mid-transcription lost the call's memo.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import recovery
from app.services.recovery import AUDIO_NOT_STORED, RECORDING_KEEPS_FAILING, RecoveryService
from app.services.telephony import call_processor


class _Query:
    def __init__(self, db, table):
        self.db = db
        self.table = table
        self.filters = []
        self.fields = None
        self.one = False

    def select(self, *_a):
        return self

    def update(self, fields):
        self.fields = fields
        return self

    def eq(self, column, value):
        self.filters.append((column, value))
        return self

    def limit(self, *_a):
        return self

    def single(self):
        self.one = True
        return self

    def execute(self):
        if self.fields is not None:
            self.db.updates.append((self.table, self.fields, self.filters))
            return SimpleNamespace(data=[])
        rows = self.db.rows.get(self.table, [])
        return SimpleNamespace(data=(rows[0] if rows else None) if self.one else rows)


class _Db:
    def __init__(self, memo, calls=()):
        self.rows = {"memos": [memo], "outbound_calls": list(calls)}
        self.updates = []

    def table(self, name):
        return _Query(self, name)

    def memo_updates(self):
        return [fields for table, fields, _ in self.updates if table == "memos"]


def _memo(**overrides):
    values = {
        "id": "m1",
        "user_id": "u1",
        "status": "transcribing",
        "source": "vocify_call",
        "recording_path": "u1/CA1.wav",
        "pipeline_meta": {"stages": [{"name": "download"}]},
        "audio_duration": 61,
    }
    return {**values, **overrides}


@pytest.fixture(autouse=True)
def _clean():
    call_processor._transcribing.clear()
    yield
    call_processor._transcribing.clear()


async def _recover(db, *, audio=b"RIFF", download_error=None):
    download = MagicMock(return_value=audio, side_effect=download_error)
    process = AsyncMock()
    with (
        patch("app.services.storage.StorageService.download_call_recording", download),
        patch.object(call_processor, "process_vocify_call_background", process),
    ):
        ok = await RecoveryService(db).recover_memo("m1")
        for task in list(recovery._background):
            await task
    return SimpleNamespace(ok=ok, download=download, process=process)


async def test_an_interrupted_call_is_transcribed_again_from_its_stored_recording():
    db = _Db(_memo(), calls=[{"carrier_call_id": "CA1", "recording_duration": 343}])

    result = await _recover(db)

    assert result.ok is True
    result.download.assert_called_once_with("u1/CA1.wav")
    result.process.assert_awaited_once_with("m1", "u1", "CA1", b"RIFF", 343.0, db)
    [update] = db.memo_updates()
    assert update["pipeline_meta"] == {"stages": [{"name": "download"}], "recovery_attempts": 1}
    assert update["processing_started_at"]
    assert "status" not in update


async def test_the_recording_path_is_found_on_the_call_when_the_memo_has_none():
    db = _Db(_memo(recording_path=None), calls=[{"recording_path": "u1/CA2.wav", "carrier_call_id": "CA2"}])

    result = await _recover(db)

    assert result.ok is True
    result.download.assert_called_once_with("u1/CA2.wav")


async def test_a_recording_that_keeps_breaking_is_failed_after_two_attempts():
    db = _Db(_memo(pipeline_meta={"recovery_attempts": RecoveryService.MAX_RECORDING_RECOVERIES}))

    result = await _recover(db)

    assert result.ok is False
    result.process.assert_not_awaited()
    assert db.memo_updates() == [
        {"status": "failed", "error_message": RECORDING_KEEPS_FAILING, "processing_started_at": None}
    ]


async def test_an_unreadable_recording_is_counted_and_left_for_the_next_sweep():
    db = _Db(_memo(pipeline_meta={"recovery_attempts": 1}))

    result = await _recover(db, download_error=RuntimeError("storage down"))

    assert result.ok is False
    result.process.assert_not_awaited()
    [update] = db.memo_updates()
    assert update["pipeline_meta"]["recovery_attempts"] == 2
    assert "status" not in update


async def test_a_call_still_being_transcribed_here_is_left_alone():
    call_processor._transcribing.add("m1")
    db = _Db(_memo())

    result = await _recover(db)

    assert result.ok is True
    result.download.assert_not_called()
    assert db.updates == []


async def test_a_call_without_a_stored_recording_fails_as_before():
    db = _Db(_memo(recording_path=None), calls=[])

    result = await _recover(db)

    assert result.ok is False
    result.download.assert_not_called()
    assert db.memo_updates() == [
        {"status": "failed", "error_message": AUDIO_NOT_STORED, "processing_started_at": None}
    ]


async def test_a_voice_memo_stuck_transcribing_fails_as_before():
    db = _Db(_memo(source="voice_memo", recording_path=None))

    result = await _recover(db)

    assert result.ok is False
    result.download.assert_not_called()
    assert db.memo_updates() == [
        {"status": "failed", "error_message": AUDIO_NOT_STORED, "processing_started_at": None}
    ]


async def test_the_transcribing_mark_is_cleared_when_processing_ends():
    with (
        patch.object(call_processor, "transcribe_audio", AsyncMock(side_effect=RuntimeError("stt down"))),
        patch.object(call_processor, "persist_pipeline_meta", MagicMock()),
    ):
        await call_processor.process_vocify_call_background("m9", "u1", "CA9", b"RIFF", 10.0, MagicMock())

    assert not call_processor.is_transcribing("m9")
