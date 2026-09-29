"""SupabaseAskStore keeps the question, lists a user's conversations, and restores memory."""

import json

from app.services.crm_copilot.web_sessions import SupabaseAskStore
from tests.crm_copilot.fakes import FakeSupabase


def _row(rid, user, conv, status, body, created):
    return {"id": rid, "user_id": user, "conversation_id": conv, "client_turn_id": rid, "status": status, "body": body, "created_at": created}


def _done(question, text, **extra):
    return json.dumps({"__vocify_turn__": 1, "text": text, "question": question, **extra})


def test_a_completed_turn_keeps_its_question_and_evidence():
    db = FakeSupabase(copilot_web_turns=[_row("t1", "u", "c", "completed", _done("¿Qué pasó?", "Nada [1].", evidence=[{"id": "ev-1"}]), "2026-09-28T10:00:00Z")])
    turns = SupabaseAskStore(db).list_turns(user_id="u", conversation_id="c")
    assert turns[0]["question"] == "¿Qué pasó?" and turns[0]["text"] == "Nada [1]."
    assert turns[0]["evidence"] == [{"id": "ev-1"}]


def test_a_pending_turn_shows_its_question_not_a_blank():
    db = FakeSupabase(copilot_web_turns=[_row("t1", "u", "c", "pending", "¿Y ahora?", "2026-09-28T10:00:00Z")])
    turn = SupabaseAskStore(db).list_turns(user_id="u")[0]
    assert turn["question"] == "¿Y ahora?"


def test_listing_never_crosses_users_and_is_oldest_first():
    db = FakeSupabase(copilot_web_turns=[
        _row("t2", "u", "c", "pending", "segunda", "2026-09-28T11:00:00Z"),
        _row("t1", "u", "c", "pending", "primera", "2026-09-28T10:00:00Z"),
        _row("t3", "other", "c", "pending", "ajena", "2026-09-28T12:00:00Z"),
    ])
    assert [t["question"] for t in SupabaseAskStore(db).list_turns(user_id="u")] == ["primera", "segunda"]


def test_latest_memory_comes_from_the_newest_completed_turn():
    db = FakeSupabase(copilot_web_turns=[
        _row("t1", "u", "c", "completed", _done("a", "x", memory={"last_contact_id": "old"}), "2026-09-28T10:00:00Z"),
        _row("t2", "u", "c", "completed", _done("b", "y", memory={"last_contact_id": "new"}), "2026-09-28T11:00:00Z"),
        _row("t3", "u", "c", "pending", "c", "2026-09-28T12:00:00Z"),
    ])
    assert SupabaseAskStore(db).latest_memory(user_id="u", conversation_id="c") == {"last_contact_id": "new"}


def test_delete_removes_only_that_users_conversation():
    db = FakeSupabase(copilot_web_turns=[
        _row("t1", "u", "c", "pending", "a", "2026-09-28T10:00:00Z"),
        _row("t2", "u", "d", "pending", "b", "2026-09-28T10:00:00Z"),
        _row("t3", "other", "c", "pending", "c", "2026-09-28T10:00:00Z"),
    ])
    SupabaseAskStore(db).delete_conversation(user_id="u", conversation_id="c")
    assert {r["id"] for r in db.tables["copilot_web_turns"]} == {"t2", "t3"}
