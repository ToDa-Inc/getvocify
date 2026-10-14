"""A call placed from HubSpot's own widget, Aircall or Ringover is screened like a Vocify-placed one:
a voicemail or a ring-out is kept with what was heard, never extracted and never failed."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.hubspot.call_log import HUBSPOT_DISPOSITION_GUID
from app.services.hubspot.calls import unanswered_outcome
from app.services.hubspot.call_processor import process_hubspot_call_background


@pytest.mark.parametrize(
    "props, expected",
    [
        ({"hs_call_status": "NO_ANSWER"}, "no_response"),
        ({"hs_call_status": "busy"}, "no_response"),
        ({"hs_call_status": "FAILED"}, "no_response"),
        ({"hs_call_status": "COMPLETED"}, None),
        ({"hs_call_status": "COMPLETED", "hs_call_disposition": HUBSPOT_DISPOSITION_GUID["voicemail"]}, "voicemail"),
        ({"hs_call_disposition": HUBSPOT_DISPOSITION_GUID["no_answer"].upper()}, "no_response"),
        ({"hs_call_disposition": HUBSPOT_DISPOSITION_GUID["connected"]}, None),
        ({}, None),
    ],
)
def test_what_the_phone_system_says_about_the_call(props, expected):
    assert unanswered_outcome(props) == expected


def _run(props, *, transcript=""):
    """process_hubspot_call_background with HubSpot, storage and speech-to-text stood in for."""
    supabase = MagicMock()
    supabase.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = (
        SimpleNamespace(data=[{"id": "m1", "user_id": "u1"}])
    )
    finalize = AsyncMock()
    extract = AsyncMock()
    update_row = MagicMock()
    stt = SimpleNamespace(text=transcript, confidence=0.9, diarization=True, channels=1)
    with patch("app.services.pipeline_lease.acquire_pipeline_run", return_value="run-1"), patch(
        "app.services.pipeline_lease.release_pipeline_run"
    ), patch("app.services.pipeline_lease.update_memo_row", update_row), patch(
        "app.services.hubspot.call_processor.get_call_engagement",
        new=AsyncMock(return_value={"properties": props}),
    ), patch(
        "app.services.hubspot.call_processor.download_recording",
        new=AsyncMock(return_value=(b"RIFF", "audio/wav")),
    ), patch(
        "app.services.storage.StorageService.upload_call_recording", new=AsyncMock(return_value="path")
    ), patch(
        "app.services.hubspot.call_processor.get_call_associations", new=AsyncMock(return_value=([], []))
    ), patch(
        "app.services.hubspot.call_processor.transcribe_audio", new=AsyncMock(return_value=stt)
    ), patch(
        "app.services.hubspot.call_processor.sanitize_user_transcript",
        new=AsyncMock(side_effect=lambda text, *_a, **_k: text),
    ), patch("app.services.hubspot.call_processor.persist_pipeline_meta"), patch(
        "app.services.hubspot.call_processor.finalize_screened_out_memo", new=finalize
    ), patch("app.api.memos.start_extraction_from_transcript", new=extract), patch(
        "app.services.hubspot.auto_sync.maybe_auto_approve_hubspot_call", new=AsyncMock()
    ):
        asyncio.run(process_hubspot_call_background("m1", "u1", "token", "999", supabase))
    return finalize, extract, update_row


def test_a_ring_out_has_no_recording_and_is_kept_not_failed():
    finalize, extract, update_row = _run({"hs_call_status": "NO_ANSWER", "hs_call_duration": "0"})

    assert finalize.call_args.args[4] == "no_response"
    extract.assert_not_called()
    assert not any(call.args[2].get("status") == "failed" for call in update_row.call_args_list)


def test_a_connected_call_with_no_recording_is_still_a_failure():
    """The status says the call connected, so a missing recording is a real problem, not a missed call."""
    finalize, extract, update_row = _run({"hs_call_status": "COMPLETED"})

    finalize.assert_not_called()
    assert any(call.args[2].get("status") == "failed" for call in update_row.call_args_list)


def test_a_voicemail_with_a_recording_is_screened_out_with_its_transcript():
    props = {
        "hs_call_status": "COMPLETED",
        "hs_call_recording_url": "https://x/rec.wav",
        "hs_call_duration": "41000",
    }
    finalize, extract, _ = _run(props, transcript="SPEAKER: S1\nNo estoy disponible, deje su mensaje después del tono.")

    assert finalize.call_args.args[4] == "voicemail"
    assert "deje su mensaje" in finalize.call_args.args[2]
    extract.assert_not_called()


def test_a_real_conversation_is_extracted():
    props = {
        "hs_call_status": "COMPLETED",
        "hs_call_recording_url": "https://x/rec.wav",
        "hs_call_duration": "95000",
    }
    transcript = (
        "S1: Hola Toni, te llamo de Vocify.\nS2: Hola, cuéntame.\n"
        "S1: Quería saber si tenéis proceso para registrar llamadas.\n"
        "S2: Sí, ahora usamos notas manuales en HubSpot.\n"
        "S1: Perfecto, podemos automatizar eso.\nS2: Me interesa, mándame info."
    )
    finalize, extract, _ = _run(props, transcript=transcript)

    finalize.assert_not_called()
    assert extract.call_args.kwargs["extra_update"]["screening_outcome"] == "connected"


def test_the_phone_system_saying_voicemail_beats_a_one_sided_monologue():
    props = {
        "hs_call_recording_url": "https://x/rec.wav",
        "hs_call_duration": "50000",
        "hs_call_disposition": HUBSPOT_DISPOSITION_GUID["voicemail"],
    }
    finalize, extract, _ = _run(
        props, transcript="SPEAKER: S1\nHola, soy Dani de Vocify, te llamo por lo de la demo que comentamos ayer."
    )

    assert finalize.call_args.args[4] == "voicemail"
    extract.assert_not_called()
