"""F01.03 — audio privado, tiempos y transcripción incompleta."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.api.captures import router as captures_router
from app.api.transcription import _extract_words
from app.deps import get_membership, get_supabase
from app.services.captures import (
    MAX_AUDIO_BYTES,
    store_capture_audio,
)
from app.services.memo_playback import can_retranscribe
from tests.captures.test_lifecycle import (
    CLIENT_CAPTURE,
    COMPANY_A,
    STARTED_AT,
    USER_A,
    _membership,
    fake_db,
    reserve_capture,
)


def test_extract_words_keeps_offsets_in_milliseconds():
    words = _extract_words(
        {
            "results": [
                {
                    "type": "word",
                    "start_time": 0,
                    "end_time": 1.25,
                    "alternatives": [{"content": "Buenos", "speaker": "S1"}],
                }
            ]
        }
    )
    assert words[0]["text"] == "Buenos"
    assert words[0]["start_ms"] == 0
    assert words[0]["end_ms"] == 1250
    assert words[0]["speaker"] == "S1"


def test_store_audio_rejects_oversize_and_bad_format_without_replacing_a_path():
    supabase, store = fake_db(
        [
            {
                "id": "memo-1",
                "user_id": USER_A,
                "recording_path": "kept/previous.wav",
                "audio_status": "partial",
            }
        ]
    )
    try:
        store_capture_audio(
            supabase,
            user_id=USER_A,
            capture_id="memo-1",
            audio=b"RIFFxxxx",
            content_type="audio/mpeg",
            byte_length=8,
        )
        raise AssertionError("format should be rejected")
    except HTTPException as exc:
        assert exc.status_code == 422
    assert store[0]["recording_path"] == "kept/previous.wav"

    try:
        store_capture_audio(
            supabase,
            user_id=USER_A,
            capture_id="memo-1",
            audio=b"RIFF",
            content_type="audio/wav",
            byte_length=MAX_AUDIO_BYTES + 1,
        )
        raise AssertionError("size should be rejected")
    except HTTPException as exc:
        assert exc.status_code == 413
    assert store[0]["recording_path"] == "kept/previous.wav"


def test_partial_transcript_with_complete_audio_does_not_start_extraction():
    supabase, store = fake_db()
    reserved = reserve_capture(
        supabase,
        user_id=USER_A,
        company_id=COMPANY_A,
        client_capture_id=CLIENT_CAPTURE,
        started_at=STARTED_AT,
        interaction_kind="meeting",
    )
    from app.services.captures import complete_capture

    done = complete_capture(
        supabase,
        user_id=USER_A,
        company_id=COMPANY_A,
        capture_id=reserved.capture_id,
        transcript="Buenos",
        audio_duration=12.0,
        turns=[{"id": "turn-1", "speaker_role": "rep", "start_ms": 0, "end_ms": 1250, "text": "Buenos días"}],
        transcript_complete=False,
        audio_status="complete",
    )
    assert done.should_start_pipeline is False
    assert done.needs_batch_stt is True
    assert store[0]["transcript_complete"] is False
    assert store[0]["capture_turns"][0]["start_ms"] == 0


def test_desktop_recording_can_be_played_back_from_private_path():
    assert can_retranscribe(
        {"source": "desktop", "recording_path": "user/memo-1.wav", "status": "pending_review"}
    )
    assert not can_retranscribe({"source": "desktop", "recording_path": "", "status": "pending_review"})


def test_put_audio_uses_private_bucket_and_reports_partial():
    supabase, rows = fake_db()
    uploads = []

    class Bucket:
        def upload(self, path, file, file_options):
            uploads.append({"path": path, "file": file, "options": file_options})

    supabase.storage.from_.return_value = Bucket()
    reserved = reserve_capture(
        supabase,
        user_id=USER_A,
        company_id=COMPANY_A,
        client_capture_id=CLIENT_CAPTURE,
        started_at=STARTED_AT,
        interaction_kind="meeting",
    )
    app = FastAPI()
    app.include_router(captures_router)
    app.dependency_overrides[get_supabase] = lambda: supabase
    app.dependency_overrides[get_membership] = lambda: _membership(USER_A, COMPANY_A)
    client = TestClient(app)
    res = client.put(
        f"/api/v1/captures/{reserved.capture_id}/audio",
        content=b"RIFF....WAVEfmt ",
        headers={"content-type": "audio/wav"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["audio_status"] == "partial"
    assert body["capture_id"] == reserved.capture_id
    assert uploads and uploads[0]["path"].endswith(".wav")
    assert rows[0]["recording_path"] == uploads[0]["path"]
