"""Ask over SSE: real events, one run per client turn, confirm runs the stored operation."""

import asyncio
import json
import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-ask-32bytes+")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-ask-32bytes+")

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import ask as ask_api
from app.deps import get_membership
from app.services.company import Membership
from app.services.crm_copilot import web_sessions as ws

BASE = "/api/v1/ask/conversations/conv-1"


def _client(user_id="user-a", role="member") -> TestClient:
    app = FastAPI()
    app.include_router(ask_api.router)
    app.dependency_overrides[get_membership] = lambda: Membership(
        id="m", company_id="co-1", user_id=user_id, role=role, status="active",
    )
    return TestClient(app)


def setup_function():
    ask_api._TURNS.clear()
    ask_api._OPERATIONS.clear()
    ws._sessions.clear()
    ask_api.set_ask_store(None)
    ask_api.set_ask_loop(None)


def teardown_function():
    ask_api.set_ask_loop(None)
    ask_api.set_ask_store(None)


def _events(response) -> list[dict]:
    out = []
    for block in response.text.split("\n\n"):
        for line in block.splitlines():
            if line.startswith("data:"):
                out.append(json.loads(line[5:].strip()))
    return out


def _stream(client, text="¿Qué pasó con Marina?", turn="t-1"):
    return client.post(f"{BASE}/turns/stream", json={"client_turn_id": turn, "text": text})


def test_the_stream_sends_turn_progress_content_final_and_done():
    async def loop(text, confirm=None, on_event=None):
        await on_event({"type": "state", "state": "understanding"})
        await on_event({"type": "tool_start", "call_id": "c1", "tool": "deal_story"})
        await on_event({"type": "tool_result", "call_id": "c1", "tool": "deal_story", "ok": True, "coverage": "complete", "n": 2})
        await on_event({"type": "content", "delta": "Marina "})
        await on_event({"type": "content", "delta": "sigue."})
        return {
            "text": "Marina sigue [1].",
            "evidence": [{"id": "ev-1", "quote": "caro", "memo_id": "m1"}],
            "coverage_note": {"level": "partial", "n": 2, "n_analysed": 1},
        }

    ask_api.set_ask_loop(loop)
    response = _stream(_client())
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["x-accel-buffering"] == "no"
    kinds = [e["type"] for e in _events(response)]
    assert kinds == ["turn", "state", "tool_start", "tool_result", "content", "content", "final", "done"]
    events = _events(response)
    final = next(e for e in events if e["type"] == "final")
    assert final["text"] == "Marina sigue [1]."
    assert final["evidence"][0]["quote"] == "caro"
    assert final["coverage_note"]["level"] == "partial"
    done = events[-1]
    assert done["status"] == "completed"


def test_the_same_client_turn_runs_the_loop_once_and_replays_the_answer():
    calls = []

    async def loop(text, confirm=None, on_event=None):
        calls.append(text)
        return {"text": "Listo."}

    ask_api.set_ask_loop(loop)
    client = _client()
    first = _events(_stream(client))
    second = _events(_stream(client, text="otra"))
    assert calls == ["¿Qué pasó con Marina?"]
    assert first[0]["turn_id"] == second[0]["turn_id"]
    assert second[0]["replayed"] is True
    assert [e["type"] for e in second][-2:] == ["final", "done"]
    assert second[-2]["text"] == "Listo."


def test_a_failed_loop_ends_with_a_retryable_error_and_a_failed_turn():
    async def loop(text, confirm=None, on_event=None):
        return None

    ask_api.set_ask_loop(loop)
    events = _events(_stream(_client()))
    assert events[-2]["type"] == "error" and events[-2]["retryable"] is True
    assert events[-1] == {"type": "done", "turn_id": events[0]["turn_id"], "status": "failed"}


def test_a_loop_that_raises_is_a_failed_turn_not_a_broken_stream():
    async def loop(text, confirm=None, on_event=None):
        raise RuntimeError("boom")

    ask_api.set_ask_loop(loop)
    events = _events(_stream(_client()))
    assert events[-1]["status"] == "failed"


def test_a_loop_without_events_still_streams_its_final_text():
    async def loop(text):
        return {"text": "Hola."}

    ask_api.set_ask_loop(loop)
    events = _events(_stream(_client()))
    assert [e["type"] for e in events] == ["turn", "final", "done"]


def test_the_public_turn_never_exposes_the_stored_tool_or_arguments():
    async def loop(text, confirm=None, on_event=None):
        return {
            "text": "Tarea: Llamar",
            "confirmation": {"operation_id": "op-1", "revision": 1, "contact_id": "c1", "tool": "create_task", "args": {"subject": "Llamar"}},
        }

    ask_api.set_ask_loop(loop)
    client = _client()
    events = _events(_stream(client))
    confirm = next(e for e in events if e["type"] == "confirm")
    assert confirm["operation_id"] == "op-1" and "tool" not in confirm and "args" not in confirm
    turn_id = events[0]["turn_id"]
    fetched = client.get(f"{BASE}/turns/{turn_id}").json()
    assert "tool" not in fetched["confirmation"] and "args" not in fetched["confirmation"]


def test_confirm_runs_the_stored_operation_and_reports_the_real_result(monkeypatch):
    ran = []

    async def loop(text, confirm=None, on_event=None):
        return {
            "text": "Tarea: Llamar",
            "confirmation": {"operation_id": "op-1", "revision": 1, "contact_id": "c1", "tool": "create_task", "args": {"subject": "Llamar"}},
        }

    async def execute(operation):
        ran.append(operation["tool"])
        return {"status": "succeeded", "applied": True, "url": "https://hs/t/1"}

    monkeypatch.setattr(ws, "execute_stored_operation", execute)
    ask_api.set_ask_loop(loop)
    client = _client()
    _stream(client)
    body = {"revision": 1, "contact_id": "c1"}
    first = client.post(f"{BASE}/operations/op-1/confirm", json=body)
    second = client.post(f"{BASE}/operations/op-1/confirm", json=body)
    assert first.status_code == 200
    assert first.json()["status"] == "succeeded" and first.json()["url"] == "https://hs/t/1"
    assert second.json()["replayed"] is True
    assert ran == ["create_task"]


def test_a_failed_write_is_reported_and_can_be_retried(monkeypatch):
    outcomes = [{"status": "failed", "applied": False}, {"status": "succeeded", "applied": True}]

    async def loop(text, confirm=None, on_event=None):
        return {"text": "x", "confirmation": {"operation_id": "op-2", "revision": 1, "contact_id": "c1", "tool": "create_note", "args": {}}}

    async def execute(operation):
        return outcomes.pop(0)

    monkeypatch.setattr(ws, "execute_stored_operation", execute)
    ask_api.set_ask_loop(loop)
    client = _client()
    _stream(client, turn="t-2")
    body = {"revision": 1, "contact_id": "c1"}
    failed = client.post(f"{BASE}/operations/op-2/confirm", json=body)
    assert failed.json()["status"] == "failed" and failed.json()["applied"] is False
    retry = client.post(f"{BASE}/operations/op-2/confirm", json=body)
    assert retry.json()["status"] == "succeeded"


def test_an_uncertain_write_is_not_retried_blindly(monkeypatch):
    async def loop(text, confirm=None, on_event=None):
        return {"text": "x", "confirmation": {"operation_id": "op-3", "revision": 1, "contact_id": "c1", "tool": "create_note", "args": {}}}

    async def execute(operation):
        return {"status": "uncertain", "applied": False}

    monkeypatch.setattr(ws, "execute_stored_operation", execute)
    ask_api.set_ask_loop(loop)
    client = _client()
    _stream(client, turn="t-3")
    body = {"revision": 1, "contact_id": "c1"}
    assert client.post(f"{BASE}/operations/op-3/confirm", json=body).json()["status"] == "uncertain"
    assert client.post(f"{BASE}/operations/op-3/confirm", json=body).status_code == 409


def test_conversations_list_get_and_delete_are_scoped_to_the_user():
    async def loop(text, confirm=None, on_event=None):
        return {"text": f"Respuesta a {text}"}

    ask_api.set_ask_loop(loop)
    mine = _client("user-a")
    mine.post("/api/v1/ask/conversations/conv-1/turns", json={"client_turn_id": "a", "text": "Primera pregunta"})
    mine.post("/api/v1/ask/conversations/conv-1/turns", json={"client_turn_id": "b", "text": "Segunda"})
    mine.post("/api/v1/ask/conversations/conv-2/turns", json={"client_turn_id": "c", "text": "Otra charla"})
    listing = mine.get("/api/v1/ask/conversations").json()["conversations"]
    assert {c["id"] for c in listing} == {"conv-1", "conv-2"}
    first = next(c for c in listing if c["id"] == "conv-1")
    assert first["title"] == "Primera pregunta" and first["turns"] == 2
    detail = mine.get("/api/v1/ask/conversations/conv-1").json()
    assert [t["question"] for t in detail["turns"]] == ["Primera pregunta", "Segunda"]
    assert detail["turns"][0]["text"] == "Respuesta a Primera pregunta"
    stranger = _client("user-b")
    assert stranger.get("/api/v1/ask/conversations").json()["conversations"] == []
    assert stranger.get("/api/v1/ask/conversations/conv-1").status_code == 404
    assert stranger.delete("/api/v1/ask/conversations/conv-1").status_code == 404
    assert mine.delete("/api/v1/ask/conversations/conv-1").status_code == 204
    assert mine.get("/api/v1/ask/conversations/conv-1").status_code == 404


@pytest.mark.asyncio
async def test_the_turn_finishes_even_if_nobody_reads_the_stream():
    finished = asyncio.Event()

    async def loop(text, confirm=None, on_event=None):
        await asyncio.sleep(0.01)
        finished.set()
        return {"text": "Hecho."}

    ask_api.set_ask_loop(loop)
    membership = Membership(id="m", company_id="co-1", user_id="user-a", role="member", status="active")
    turn = ask_api._accept(membership, "conv-1", "t-x", "hola")
    queue, task = ask_api._start_turn(turn, "hola", membership, "conv-1")
    await asyncio.wait_for(task, 2)
    assert finished.is_set()
    stored = ask_api._TURNS[("user-a", "conv-1", "t-x")]
    assert stored["status"] == "completed" and stored["text"] == "Hecho."


def test_a_confirmed_write_is_saved_on_the_turn_so_a_reload_shows_it_applied(monkeypatch):
    async def loop(text, confirm=None, on_event=None):
        return {"text": "Nota: llamar", "confirmation": {"operation_id": "op-9", "revision": 1, "contact_id": "c1", "tool": "create_note", "args": {}}}

    async def execute(operation):
        return {"status": "succeeded", "applied": True}

    monkeypatch.setattr(ws, "execute_stored_operation", execute)
    ask_api.set_ask_loop(loop)
    client = _client()
    turn_id = _events(_stream(client, turn="t-9"))[0]["turn_id"]
    client.post(f"{BASE}/operations/op-9/confirm", json={"revision": 1, "contact_id": "c1"})
    reloaded = client.get(f"{BASE}/turns/{turn_id}").json()
    assert reloaded["confirmation"]["applied"] is True


def test_a_failed_write_is_saved_as_failed_so_a_reload_offers_a_retry_not_success(monkeypatch):
    async def loop(text, confirm=None, on_event=None):
        return {"text": "Nota", "confirmation": {"operation_id": "op-8", "revision": 1, "contact_id": "c1", "tool": "create_note", "args": {}}}

    async def execute(operation):
        return {"status": "failed", "applied": False}

    monkeypatch.setattr(ws, "execute_stored_operation", execute)
    ask_api.set_ask_loop(loop)
    client = _client()
    turn_id = _events(_stream(client, turn="t-8"))[0]["turn_id"]
    client.post(f"{BASE}/operations/op-8/confirm", json={"revision": 1, "contact_id": "c1"})
    confirmation = client.get(f"{BASE}/turns/{turn_id}").json()["confirmation"]
    assert confirmation["applied"] is False and confirmation["state"] == "failed"


def test_the_crm_link_of_a_saved_write_survives_a_reload(monkeypatch):
    async def loop(text, confirm=None, on_event=None):
        return {"text": "Nota", "confirmation": {"operation_id": "op-7", "revision": 1, "contact_id": "c1", "tool": "create_note", "args": {}}}

    async def execute(operation):
        return {"status": "succeeded", "applied": True, "url": "https://crm.example/note/1"}

    monkeypatch.setattr(ws, "execute_stored_operation", execute)
    ask_api.set_ask_loop(loop)
    client = _client()
    turn_id = _events(_stream(client, turn="t-7"))[0]["turn_id"]
    client.post(f"{BASE}/operations/op-7/confirm", json={"revision": 1, "contact_id": "c1"})
    assert client.get(f"{BASE}/turns/{turn_id}").json()["confirmation"]["url"] == "https://crm.example/note/1"


def test_delete_all_removes_only_the_callers_conversations():
    async def loop(text, confirm=None, on_event=None):
        return {"text": "ok"}

    ask_api.set_ask_loop(loop)
    mine, other = _client("user-a"), _client("user-b")
    for c, cid, tid in ((mine, "c1", "a"), (mine, "c2", "b"), (other, "c1", "x")):
        c.post(f"/api/v1/ask/conversations/{cid}/turns", json={"client_turn_id": tid, "text": "hola"})
    assert mine.delete("/api/v1/ask/conversations").status_code == 204
    assert mine.get("/api/v1/ask/conversations").json()["conversations"] == []
    assert len(other.get("/api/v1/ask/conversations").json()["conversations"]) == 1
    assert mine.delete("/api/v1/ask/conversations").status_code == 204  # nothing left is not an error


def test_suggestions_come_from_the_accounts_data(monkeypatch):
    from app.deps import get_supabase
    from tests.crm_copilot.fakes import FakeSupabase

    seen = {}

    def fake_compute(supabase, **kwargs):
        seen.update(kwargs)
        return ["next_actions", "objections"]

    monkeypatch.setattr(ask_api.suggestions, "compute", fake_compute)
    monkeypatch.setattr(ask_api, "_member_ids", lambda supabase, membership: ["user-a", "user-c"])
    monkeypatch.setattr(ask_api, "_has_hubspot", lambda supabase, user_id: True)
    app = FastAPI()
    app.include_router(ask_api.router)
    app.dependency_overrides[get_membership] = lambda: Membership(id="m", company_id="co-1", user_id="user-a", role="admin", status="active")
    app.dependency_overrides[get_supabase] = lambda: FakeSupabase()
    body = TestClient(app).get("/api/v1/ask/suggestions").json()
    assert body == {"suggestions": ["next_actions", "objections"]}
    assert seen["role"] == "admin" and seen["has_crm"] is True and seen["member_ids"] == ["user-a", "user-c"]


def test_a_failure_computing_suggestions_shows_none_rather_than_breaking_the_panel(monkeypatch):
    from app.deps import get_supabase
    from tests.crm_copilot.fakes import FakeSupabase

    def boom(*a, **k):
        raise RuntimeError("db down")

    monkeypatch.setattr(ask_api.suggestions, "compute", boom)
    monkeypatch.setattr(ask_api, "_member_ids", lambda supabase, membership: ["user-a"])
    monkeypatch.setattr(ask_api, "_has_hubspot", lambda supabase, user_id: False)
    app = FastAPI()
    app.include_router(ask_api.router)
    app.dependency_overrides[get_membership] = lambda: Membership(id="m", company_id="co-1", user_id="user-a", role="member", status="active")
    app.dependency_overrides[get_supabase] = lambda: FakeSupabase()
    assert TestClient(app).get("/api/v1/ask/suggestions").json() == {"suggestions": []}
