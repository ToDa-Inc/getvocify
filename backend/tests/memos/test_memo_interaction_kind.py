"""Memo responses carry the capture channel so the rep home can label a conversation."""

from app.api.memos import _memo_from_row


def _row(**extra):
    return {
        "id": "00000000-0000-0000-0000-000000000001",
        "user_id": "rep-1",
        "audio_url": "",
        "audio_duration": 840,
        "status": "approved",
        "created_at": "2026-09-22T10:00:00+00:00",
        **extra,
    }


def test_stored_interaction_kind_is_returned():
    assert _memo_from_row(_row(interaction_kind="visit")).interactionKind == "visit"
    assert _memo_from_row(_row(interaction_kind="meeting")).interactionKind == "meeting"


def test_rows_from_before_the_column_are_classified_by_origin():
    assert _memo_from_row(_row(source="vocify_call")).interactionKind == "call"
    assert _memo_from_row(_row(source="whatsapp")).interactionKind == "visit"
    assert _memo_from_row(_row(source_type="meeting_transcript")).interactionKind == "meeting"


def test_interaction_kind_is_in_the_json():
    body = _memo_from_row(_row(interaction_kind="call")).model_dump(mode="json")
    assert body["interactionKind"] == "call"
