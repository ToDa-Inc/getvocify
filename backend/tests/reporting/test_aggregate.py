"""F13 snapshot: attempts are not conversations, and a missing close is not zero."""

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-reports-32b")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-reports-32b")

from app.services.reporting.aggregate import build_snapshot

START = "2026-09-21T22:00:00Z"
END = "2026-09-22T22:00:00Z"


def _snapshot(**overrides):
    base = dict(
        scope="self",
        period_start=START,
        period_end=END,
        timezone="Europe/Madrid",
        interactions=[],
        outcomes={"coverage": "complete", "won": 0, "lost": 0},
        adherence_parts=None,
    )
    base.update(overrides)
    return build_snapshot(**base)


def test_a_voicemail_is_an_attempt_and_a_conversation_is_connected():
    snapshot = _snapshot(interactions=[
        {"captured_at": "2026-09-22T10:00:00Z", "screening": "voicemail", "connected": False, "memo_id": "m-1"},
        {"captured_at": "2026-09-22T11:00:00Z", "screening": None, "connected": True, "meeting_agreed": True, "memo_id": "m-2"},
        {"captured_at": "2026-09-23T11:00:00Z", "screening": None, "connected": True, "memo_id": "outside"},
    ])
    assert snapshot["metrics"]["attempts"] == 2
    assert snapshot["metrics"]["connected_calls"] == 1
    assert snapshot["metrics"]["meetings_agreed"] == 1
    assert snapshot["metrics"]["deals_won"] == 0
    assert snapshot["examples"] == ["m-1", "m-2"]


def test_unavailable_closes_are_null_and_an_empty_period_invents_no_coaching():
    missing = _snapshot(
        interactions=[{"captured_at": "2026-09-22T10:00:00Z", "connected": True, "meeting_agreed": True}],
        outcomes={"coverage": "unavailable"},
    )
    assert missing["metrics"]["deals_won"] is None
    assert missing["metrics"]["meetings_agreed"] == 1
    assert missing["coverage"]["crm_outcomes"] == "unavailable"
    empty = _snapshot()
    assert empty["metrics"]["attempts"] == 0
    assert empty["metrics"]["connected_calls"] == 0
    assert empty["metrics"]["adherence"] is None
    assert empty["coaching"] is None
    pooled = _snapshot(adherence_parts=[
        {"met_steps": 1, "missed_steps": 0, "unknown_steps": 0, "not_applicable_steps": 0},
        {"met_steps": 1, "missed_steps": 3, "unknown_steps": 0, "not_applicable_steps": 0},
    ])
    assert pooled["metrics"]["adherence"] == 2 / 5
