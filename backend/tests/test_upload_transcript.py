import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.api import memos
from app.api.memos import UploadTranscriptRequest, upload_transcript_and_extract


def _run(source_type):
    supabase = MagicMock()
    insert = supabase.table.return_value.insert
    insert.return_value.execute.return_value.data = [{"id": "memo-1"}]
    extract = AsyncMock()
    with (
        patch("app.services.transcript_sanitize.sanitize_user_transcript", AsyncMock(side_effect=lambda t, *_: t)),
        patch.object(memos, "_curated_field_specs_for_primary_crm", AsyncMock(return_value=None)),
        patch.object(memos, "start_extraction_from_transcript", extract),
    ):
        asyncio.run(
            upload_transcript_and_extract(
                UploadTranscriptRequest(transcript="You: hola\n\nThem: qué tal", source_type=source_type),
                supabase=supabase,
                user_id="user-1",
            )
        )
    return insert.call_args.args[0], extract.call_args.kwargs["source_type"]


def test_meeting_source_is_persisted_and_extracted_as_meeting():
    row, extracted = _run("meeting_transcript")
    assert row["source_type"] == "meeting_transcript"
    assert extracted == "meeting_transcript"


def test_unknown_or_missing_source_falls_back_to_voice_memo():
    for source_type in (None, "whatsapp"):
        row, extracted = _run(source_type)
        assert row["source_type"] == "voice_memo"
        assert extracted == "voice_memo"
