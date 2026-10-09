"""Memo responses carry the capture channel so the rep home can label a conversation."""

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-memo-rows-32")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-memo-rows-32")

from app.api.memos import _memo_from_row  # noqa: E402


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


def test_a_memo_with_no_measured_duration_still_loads():
    # Some rows have audio_duration NULL; one of them used to fail the whole list (500).
    assert _memo_from_row(_row(audio_duration=None)).audioDuration == 0.0


def test_one_unreadable_row_does_not_empty_the_list(monkeypatch):
    import asyncio

    from app.api import memos as memos_api

    class _Q:
        def __init__(self, rows):
            self.rows = rows

        def __getattr__(self, _name):
            return lambda *a, **k: self

        def execute(self):
            return type("R", (), {"data": self.rows})()

    good = _row()
    broken = _row(id="00000000-0000-0000-0000-000000000002", created_at=None)

    class _Supabase:
        def table(self, _name):
            return _Q([good, broken])

    monkeypatch.setattr(memos_api, "load_viewer_scope", lambda *_a: (None, [], {}))
    monkeypatch.setattr(memos_api, "effective_visibility", lambda *_a: "own")
    monkeypatch.setattr(memos_api, "resolve_list_user_ids", lambda **_k: ["rep-1"])
    result = asyncio.run(memos_api.list_memos(
        supabase=_Supabase(), user_id="rep-1", limit=20, offset=0, hubspot_deal_id=None,
        hubspot_contact_id=None, scope="me", author_user_id=None, memo_status=None, reached_only=False,
    ))
    assert [str(m.id) for m in result] == [good["id"]]


def test_attendees_are_returned_on_a_meeting_memo():
    body = _memo_from_row(
        _row(interaction_kind="meeting", attendees=[{"email": "marta@client.com", "name": "Marta Ruiz"}])
    ).model_dump(mode="json")
    assert body["attendees"] == [{"email": "marta@client.com", "name": "Marta Ruiz"}]


def test_a_memo_without_attendees_returns_an_empty_list():
    assert _memo_from_row(_row()).model_dump(mode="json")["attendees"] == []
    assert _memo_from_row(_row(attendees=None)).model_dump(mode="json")["attendees"] == []
