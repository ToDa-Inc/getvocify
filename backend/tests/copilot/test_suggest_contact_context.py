"""F12: optional contact_id on /copilot/suggest resolves into SuggestContext only."""

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-copilot-32-chars")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-copilot-32-chars")

from app.services.copilot.context import resolve_suggest_context


def test_missing_contact_id_does_not_add_a_contact():
    ctx = resolve_suggest_context(None, call_mode="speakerphone")
    assert ctx.contact_id is None
    assert ctx.live_assist_kind == "call"

    blank = resolve_suggest_context("   ", call_mode="meeting")
    assert blank.contact_id is None
    assert blank.live_assist_kind == "meeting"


def test_contact_id_42_is_on_the_context_object():
    ctx = resolve_suggest_context("42", call_mode="speakerphone")
    assert ctx.contact_id == "42"
    assert ctx.live_assist_kind == "call"

    meeting = resolve_suggest_context("42", call_mode="meeting")
    assert meeting.contact_id == "42"
    assert meeting.live_assist_kind == "meeting"
