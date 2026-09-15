from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services.memo_playback import (
    can_retranscribe,
    playback_audio_url,
    recording_path_for_memo,
)


def test_signed_recording_path_wins_over_empty_audio_url():
    url = playback_audio_url(
        {"recording_path": "u1/CA1.wav", "audio_url": ""},
        sign=lambda path: f"https://signed/{path}",
    )
    assert url == "https://signed/u1/CA1.wav"


def test_missing_path_uses_legacy_audio_url():
    url = playback_audio_url(
        {"recording_path": None, "audio_url": "https://public/note.webm"},
        sign=lambda path: f"https://signed/{path}",
    )
    assert url == "https://public/note.webm"


def test_sign_failure_hides_player():
    def boom(_path):
        raise RuntimeError("sign failed")

    url = playback_audio_url(
        {"recording_path": "u1/CA1.wav", "audio_url": "https://legacy"},
        sign=boom,
    )
    assert url == ""


def test_retranscribe_vocify_needs_path():
    assert can_retranscribe({"source": "vocify_call", "recording_path": "u/1.wav"})
    assert not can_retranscribe({"source": "vocify_call", "recording_path": ""})


def test_retranscribe_hubspot_allows_engagement_or_path():
    assert can_retranscribe(
        {"source": "hubspot_call", "hubspot_engagement_id": "123"}
    )
    assert can_retranscribe({"source": "hubspot_call", "recording_path": "u/hs_1.wav"})
    assert not can_retranscribe({"source": "voice_memo", "recording_path": "x"})


def test_vocify_path_falls_back_to_outbound_calls():
    q = MagicMock()
    q.select.return_value = q
    q.eq.return_value = q
    q.limit.return_value = q
    q.execute.return_value = SimpleNamespace(data=[{"recording_path": "u1/CA9.wav"}])
    supabase = MagicMock()
    supabase.table.return_value = q
    path = recording_path_for_memo(
        {"id": "m1", "source": "vocify_call", "recording_path": None},
        supabase,
    )
    assert path == "u1/CA9.wav"


def test_retranscribe_rejected_when_approved():
    assert not can_retranscribe(
        {
            "source": "vocify_call",
            "recording_path": "u/1.wav",
            "status": "approved",
        }
    )
