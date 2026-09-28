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
