import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.api import memos
from app.api.memos import UploadTranscriptRequest, upload_transcript_and_extract


def _run(source_type, speakers_verified=False, notes=None):
    supabase = MagicMock()
    insert = supabase.table.return_value.insert
    insert.return_value.execute.return_value.data = [{"id": "memo-1"}]
    extract = AsyncMock()
    with (
        patch("app.services.transcript_sanitize.sanitize_user_transcript", AsyncMock(side_effect=lambda t, *_, **__: t)),
        patch.object(memos, "_curated_field_specs_for_primary_crm", AsyncMock(return_value=None)),
        patch.object(memos, "start_extraction_from_transcript", extract),
    ):
        asyncio.run(
            upload_transcript_and_extract(
                UploadTranscriptRequest(
                    transcript="SPEAKER: S1\nhola\n\nSPEAKER: S2\nqué tal",
                    source_type=source_type,
                    speakers_verified=speakers_verified,
                    notes=notes,
                ),
                supabase=supabase,
                user_id="user-1",
            )
        )
    _run.last_notes = extract.call_args.kwargs.get("user_notes")
    return insert.call_args.args[0], extract.call_args.kwargs["source_type"], extract.call_args.kwargs["extra_update"]


def test_meeting_source_is_persisted_and_extracted_as_meeting():
    row, extracted, _ = _run("meeting_transcript")
    assert row["source_type"] == "meeting_transcript"
    assert extracted == "meeting_transcript"


def test_unknown_or_missing_source_falls_back_to_voice_memo():
    for source_type in (None, "whatsapp"):
        row, extracted, _ = _run(source_type)
        assert row["source_type"] == "voice_memo"
        assert extracted == "voice_memo"


def test_desktop_channel_capture_is_marked_verified():
    *_, update = _run("meeting_transcript", speakers_verified=True)
    assert update["transcript_stt_meta"]["speakers"] == "channels"
    *_, update = _run("meeting_transcript")
    assert "speakers" not in update["transcript_stt_meta"]


def test_rep_notes_are_stored_and_sent_to_extraction():
    row, *_ = _run("meeting_transcript", notes="  Presupuesto 5k\n- decide Jorge  ")
    assert row["user_notes"] == "Presupuesto 5k\n- decide Jorge"
    assert _run.last_notes == "Presupuesto 5k\n- decide Jorge"


def test_memos_without_notes_never_write_the_column():
    row, *_ = _run("meeting_transcript", notes="   ")
    assert "user_notes" not in row
    assert _run.last_notes is None


# A Vocify call from the desktop: its live transcript becomes the call's memo at hang-up.

import pytest
from fastapi import HTTPException

SID = "CA84c0f5f9031df5f6534fa6ed4c8f64b7"
CALL = {"carrier_call_id": SID, "user_id": "user-1", "memo_id": None, "hubspot_contact_id": "901", "hubspot_deal_id": "55"}


def _run_call(call_row, *, claim="memo-1", outcome="connected"):
    supabase = MagicMock()
    insert = supabase.table.return_value.insert
    insert.return_value.execute.return_value.data = [{"id": "memo-1"}]
    extract, finalize = AsyncMock(), AsyncMock()
    with (
        patch("app.services.transcript_sanitize.sanitize_user_transcript", AsyncMock(side_effect=lambda t, *_, **__: t)),
        patch.object(memos, "_curated_field_specs_for_primary_crm", AsyncMock(return_value=None)),
        patch.object(memos, "start_extraction_from_transcript", extract),
        patch.object(memos, "find_user_call", MagicMock(return_value=call_row)),
        patch.object(memos, "claim_call_memo", MagicMock(return_value=claim)),
        patch.object(memos, "classify_call_outcome", MagicMock(return_value=outcome)),
        patch.object(memos, "finalize_screened_out_memo", finalize),
    ):
        res = asyncio.run(
            upload_transcript_and_extract(
                UploadTranscriptRequest(
                    transcript="SPEAKER: Rep\nhola\n\nSPEAKER: Prospect\nqué tal",
                    source_type="meeting_transcript",
                    speakers_verified=True,
                    call_sid=SID,
                    call_duration_seconds=65,
                ),
                supabase=supabase,
                user_id="user-1",
            )
        )
    return res, insert, extract, finalize


def test_live_call_transcript_becomes_the_calls_memo():
    res, insert, extract, _ = _run_call(dict(CALL))
    row = insert.call_args.args[0]
    assert (row["source"], row["hubspot_contact_id"], row["hubspot_deal_id"]) == ("vocify_call", "901", "55")
    assert extract.call_args.kwargs["source_type"] == "vocify_call"
    assert res.id == "memo-1"


def test_when_the_recording_already_made_the_memo_nothing_new_is_created():
    res, insert, extract, _ = _run_call({**CALL, "memo_id": "rec-memo"})
    assert res.id == "rec-memo"
    insert.assert_not_called()
    extract.assert_not_called()


def test_losing_the_race_returns_the_winning_memo_without_extracting():
    res, _, extract, _ = _run_call(dict(CALL), claim="rec-memo")
    assert res.id == "rec-memo"
    extract.assert_not_called()


def test_a_voicemail_is_screened_out_not_extracted():
    _, _, extract, finalize = _run_call(dict(CALL), outcome="voicemail")
    extract.assert_not_called()
    assert finalize.await_args.args[4] == "voicemail"


def test_someone_elses_call_is_refused():
    with pytest.raises(HTTPException) as err:
        _run_call(None)
    assert err.value.status_code == 404
