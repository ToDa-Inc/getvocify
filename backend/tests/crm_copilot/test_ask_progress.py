"""Ask shows what it is doing (Lista 3 review fix): live steps while the turn runs,
steps and question kept with the answer, and memory scoped to one conversation."""

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-ask-progress-32")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-ask-progress-32")

from app.api import ask as ask_api
from app.services.crm_copilot import web_sessions
from app.services.crm_copilot.web_sessions import (
    _encode_completed_body,
    _turn_from_row,
    progress_end,
    progress_get,
    progress_start,
    progress_step,
    session_key,
)
from tests.crm_copilot.test_ask_http import _client


def test_progress_appends_running_steps_and_updates_them_in_place():
    key = ("u", "conv", "t1")
    progress_start(key)
    try:
        progress_step(key, {"tool": "search_contacts", "state": "running", "detail": "Marc"})
        progress_step(key, {"tool": "search_contacts", "state": "done", "detail": "Marc"})
        progress_step(key, {"tool": "list_notes", "state": "running", "detail": ""})
        assert progress_get(key) == {"steps": [
            {"tool": "search_contacts", "state": "done", "detail": "Marc"},
            {"tool": "list_notes", "state": "running", "detail": ""},
        ]}
    finally:
        progress_end(key)
    assert progress_get(key) is None
    progress_step(key, {"tool": "x", "state": "running", "detail": ""})  # ended: ignored
    assert progress_get(key) is None


def test_the_progress_endpoint_only_shows_the_callers_own_running_turn():
    progress_start(("user-a", "conv-1", "t-live"))
    try:
        progress_step(("user-a", "conv-1", "t-live"), {"tool": "get_contact", "state": "running", "detail": ""})
        own = _client("user-a").get("/api/v1/ask/conversations/conv-1/progress", params={"client_turn_id": "t-live"}).json()
        assert own == {"running": True, "steps": [{"tool": "get_contact", "state": "running", "detail": ""}]}
        other = _client("user-b").get("/api/v1/ask/conversations/conv-1/progress", params={"client_turn_id": "t-live"}).json()
        assert other == {"running": False, "steps": []}
    finally:
        progress_end(("user-a", "conv-1", "t-live"))


def test_a_finished_turn_carries_its_steps_and_clears_its_progress():
    async def loop(_text: str):
        return {"text": "Hecho.", "steps": [{"tool": "search_contacts", "state": "done", "detail": "Ana"}]}

    ask_api.set_ask_loop(loop)
    try:
        client = _client("user-a")
        body = client.post(
            "/api/v1/ask/conversations/conv-9/turns", json={"client_turn_id": "t-9", "text": "¿Y Ana?"},
        ).json()
        assert body["steps"] == [{"tool": "search_contacts", "state": "done", "detail": "Ana"}]
        assert progress_get(("user-a", "conv-9", "t-9")) is None
    finally:
        ask_api.set_ask_loop(None)


def test_question_and_steps_survive_storage():
    stored = _encode_completed_body({
        "text": "Hecho.", "question": "¿Y Ana?", "steps": [{"tool": "get_contact", "state": "done", "detail": ""}],
    })
    turn = _turn_from_row({"id": "t", "status": "completed", "body": stored})
    assert turn["question"] == "¿Y Ana?"
    assert turn["steps"] == [{"tool": "get_contact", "state": "done", "detail": ""}]


def test_memory_is_per_conversation():
    assert session_key("u", "conv-1") != session_key("u", "conv-2")
    assert session_key("u", "") == "u"  # WhatsApp and old callers: one session per user, as before


def test_binding_keeps_the_conversation_for_the_loop():
    web_sessions.bind_ask_actor("u", "co", conversation_id="conv-3", progress_key=("u", "conv-3", "t"))
    assert web_sessions._actor["conversation_id"] == "conv-3"
    assert web_sessions._actor["progress_key"] == ("u", "conv-3", "t")
