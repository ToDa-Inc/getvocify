"""F07.06: «¿A quién llamo hoy?» carries the contacts get_call_priorities returned, never the model's text."""

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-ask-32bytes+")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-ask-32bytes+")

from datetime import timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import deps
from app.api import ask as ask_api
from app.config import settings
from app.deps import get_membership
from app.services import feature_flags
from app.services.company import Membership
from app.services.crm_copilot import web_sessions
from app.services.crm_copilot.call_actions import CALL_ACTIONS_FLAG, MAX_CALL_TARGETS
from app.services.crm_copilot.tools import CopilotContext, execute_tool
from app.services.llm import client as llm_client
from tests.crm_copilot.test_ask_http import FakeSupabase
from tests.crm_copilot.test_vocify_reads import CO, NOW, _memo, _patch_viewer, _priority_row, _Store


@pytest.fixture(autouse=True)
def _flags(monkeypatch):
    feature_flags.clear_cache()
    web_sessions._sessions.clear()
    monkeypatch.setattr(settings, "ASK_VOCIFY_DATA_TOOLS_ENABLED", True)
    monkeypatch.setattr(settings, CALL_ACTIONS_FLAG, True)
    yield
    feature_flags.clear_cache()
    web_sessions._sessions.clear()


def _connection(provider="hubspot", metadata=None, connection_id="crm-A"):
    return {
        "id": connection_id,
        "company_id": CO,
        "provider": provider,
        "status": "connected",
        "metadata": metadata if metadata is not None else {"portal_id": "1"},
    }


def _store(rows=None, memos=None, connection=None, connected=True, overrides=None):
    rows = rows if rows is not None else [
        _priority_row("p-1", "rep-a", contacted=False),
        _priority_row("p-2", "rep-a", contacted=True, last_call_at=(NOW - timedelta(days=2)).isoformat()),
        _priority_row("p-3", "rep-b", contacted=False),
    ]
    memos = memos if memos is not None else [_memo("m-pain", "rep-a", contact="p-2", intelligence={"pain_confirmed": True})]
    return _Store(
        crm_connections=[connection or _connection()] if connected else [],
        contact_priority_context=rows,
        memos=memos,
        company_feature_flags=overrides or [],
    )


def _ctx(store, user_id="rep-a"):
    return CopilotContext(supabase=store, user_id=user_id, artifacts={})


async def test_the_tool_result_is_unchanged_and_the_targets_ride_on_the_context(monkeypatch):
    _patch_viewer(monkeypatch)
    ctx = _ctx(_store())
    result = await execute_tool("get_call_priorities", {}, ctx)
    assert "_call_targets" not in result
    assert [item["contact_id"] for item in result["items"]] == ["p-2", "p-1"]
    assert ctx.call_targets == [
        {
            "contact_id": "p-2",
            "connection_id": "crm-A",
            "provider": "hubspot",
            "contact_name": "Contacto p-2",
            "reason": "pain_agree_next_step",
            "next_action": "agree_next_step",
            "crm_url": "https://app.hubspot.com/contacts/1/record/0-1/p-2",
        },
        {
            "contact_id": "p-1",
            "connection_id": "crm-A",
            "provider": "hubspot",
            "contact_name": "Contacto p-1",
            "reason": "no_calls_logged",
            "next_action": "log_first_call",
            "crm_url": "https://app.hubspot.com/contacts/1/record/0-1/p-1",
        },
    ]


async def test_another_owners_contact_is_never_a_target(monkeypatch):
    _patch_viewer(monkeypatch)
    ctx = _ctx(_store(), "rep-b")
    await execute_tool("get_call_priorities", {}, ctx)
    assert [row["contact_id"] for row in ctx.call_targets] == ["p-3"]
    boss = _ctx(_store(), "boss")
    await execute_tool("get_call_priorities", {}, boss)
    assert boss.call_targets == []


async def test_a_scheduled_call_and_a_partial_history_are_not_targets(monkeypatch):
    _patch_viewer(monkeypatch)
    future = (NOW + timedelta(days=3)).isoformat()
    partial = {**_priority_row("p-partial", "rep-a", contacted=False), "history_complete": False}
    rows = [
        _priority_row("p-1", "rep-a", contacted=False),
        _priority_row("p-later", "rep-a", contacted=True, last_call_at=(NOW - timedelta(days=1)).isoformat()),
        partial,
    ]
    memos = [_memo("m-meet", "rep-a", contact="p-later", intelligence={"meeting": {"agreed": True, "starts_at": future}})]
    ctx = _ctx(_store(rows=rows, memos=memos))
    result = await execute_tool("get_call_priorities", {}, ctx)
    reasons = {item["contact_id"]: item["reason"] for item in result["items"]}
    assert reasons["p-later"] == "scheduled_no_early_call"
    assert reasons["p-partial"] == "history_partial"
    assert [row["contact_id"] for row in ctx.call_targets] == ["p-1"]


async def test_at_most_five_targets_in_the_tool_order(monkeypatch):
    _patch_viewer(monkeypatch)
    rows = [_priority_row(f"p-{n}", "rep-a", contacted=False) for n in range(1, 9)]
    ctx = _ctx(_store(rows=rows, memos=[]))
    result = await execute_tool("get_call_priorities", {"limit": 20}, ctx)
    assert len(result["items"]) == 8
    assert MAX_CALL_TARGETS == 5
    assert [row["contact_id"] for row in ctx.call_targets] == [item["contact_id"] for item in result["items"][:5]]


async def test_a_pipedrive_target_links_to_the_pipedrive_person(monkeypatch):
    _patch_viewer(monkeypatch)
    connection = _connection("pipedrive", {"api_domain": "https://acme.pipedrive.com"})
    ctx = _ctx(_store(rows=[_priority_row("11", "rep-a", contacted=False)], memos=[], connection=connection))
    await execute_tool("get_call_priorities", {}, ctx)
    assert ctx.call_targets[0]["provider"] == "pipedrive"
    assert ctx.call_targets[0]["crm_url"] == "https://acme.pipedrive.com/person/11"


async def test_a_row_from_another_connection_has_no_crm_link(monkeypatch):
    _patch_viewer(monkeypatch)
    old = {**_priority_row("p-old", "rep-a", contacted=False), "connection_id": "crm-old"}
    ctx = _ctx(_store(rows=[old], memos=[]))
    await execute_tool("get_call_priorities", {}, ctx)
    assert ctx.call_targets[0]["contact_id"] == "p-old"
    assert ctx.call_targets[0]["crm_url"] is None


async def test_no_crm_means_no_targets(monkeypatch):
    _patch_viewer(monkeypatch)
    ctx = _ctx(_store(connected=False))
    result = await execute_tool("get_call_priorities", {}, ctx)
    assert result["coverage"] == "unavailable"
    assert ctx.call_targets == []


class _Reply:
    def __init__(self, content=None, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls or []


def _script(monkeypatch, *replies):
    queue = list(replies)

    class _LLM:
        async def chat_tools(self, _messages, **_kwargs):
            return queue.pop(0)

    monkeypatch.setattr(llm_client, "LLMClient", _LLM)


def _priorities_then(text):
    return (
        _Reply(tool_calls=[{"id": "t1", "name": "get_call_priorities", "arguments": {}}]),
        _Reply(content=text),
    )


async def _web_turn(monkeypatch, store, text="¿A quién llamo hoy?", user_id="rep-a"):
    monkeypatch.setattr(deps, "get_supabase", lambda: store)
    web_sessions.bind_ask_actor(user_id, CO)
    return await web_sessions.live_ask_loop(text)


async def test_the_web_turn_attaches_what_the_tool_returned_not_what_the_model_said(monkeypatch):
    _patch_viewer(monkeypatch)
    _script(monkeypatch, *_priorities_then("Llama a Lucía, a Invento Pérez (p-99) y a Contacto p-3."))
    body = await _web_turn(monkeypatch, _store())
    assert body["text"].startswith("Llama a Lucía")
    assert [row["contact_id"] for row in body["call_targets"]] == ["p-2", "p-1"]
    assert "p-99" not in str(body["call_targets"])
    assert "p-3" not in str(body["call_targets"])


async def test_flag_off_leaves_the_web_turn_as_before(monkeypatch):
    monkeypatch.setattr(settings, CALL_ACTIONS_FLAG, False)
    _patch_viewer(monkeypatch)
    _script(monkeypatch, *_priorities_then("Llama a Contacto p-2."))
    body = await _web_turn(monkeypatch, _store())
    assert body == {"text": "Llama a Contacto p-2."}


async def test_a_company_override_turns_call_actions_on_for_that_company(monkeypatch):
    monkeypatch.setattr(settings, CALL_ACTIONS_FLAG, False)
    _patch_viewer(monkeypatch)
    overrides = [{"company_id": CO, "flag": CALL_ACTIONS_FLAG, "enabled": True}]
    _script(monkeypatch, *_priorities_then("Llama a Contacto p-2."))
    body = await _web_turn(monkeypatch, _store(overrides=overrides))
    assert [row["contact_id"] for row in body["call_targets"]] == ["p-2", "p-1"]


async def test_a_turn_that_did_not_read_priorities_has_no_targets(monkeypatch):
    _patch_viewer(monkeypatch)
    _script(monkeypatch, _Reply(content="Llama a Marina Ruiz."))
    body = await _web_turn(monkeypatch, _store())
    assert "call_targets" not in body


async def test_an_unavailable_read_has_no_targets(monkeypatch):
    _patch_viewer(monkeypatch)
    _script(monkeypatch, *_priorities_then("No puedo leer tu CRM ahora."))
    body = await _web_turn(monkeypatch, _store(connected=False))
    assert "call_targets" not in body


async def test_a_confirmation_turn_has_no_targets(monkeypatch):
    _patch_viewer(monkeypatch)
    _script(
        monkeypatch,
        _Reply(tool_calls=[{"id": "t1", "name": "get_call_priorities", "arguments": {}}]),
        _Reply(tool_calls=[{"id": "t2", "name": "create_note", "arguments": {"contact_id": "p-2", "body": "Llamar hoy"}}]),
    )
    body = await _web_turn(monkeypatch, _store())
    assert body.get("confirmation", {}).get("contact_id") == "p-2"
    assert "call_targets" not in body


async def test_targets_do_not_leak_into_the_next_turn(monkeypatch):
    _patch_viewer(monkeypatch)
    store = _store()
    _script(monkeypatch, *_priorities_then("Llama a Contacto p-2."), _Reply(content="De nada."))
    first = await _web_turn(monkeypatch, store)
    second = await _web_turn(monkeypatch, store, text="gracias")
    assert first["call_targets"]
    assert "call_targets" not in second


TARGETS = [
    {
        "contact_id": "p-2",
        "connection_id": "crm-A",
        "provider": "hubspot",
        "contact_name": "Lucía Pérez",
        "reason": "pain_agree_next_step",
        "next_action": "agree_next_step",
        "crm_url": "https://app.hubspot.com/contacts/1/record/0-1/p-2",
    },
]


def _client(user_id="user-a") -> TestClient:
    app = FastAPI()
    app.include_router(ask_api.router)
    app.dependency_overrides[get_membership] = lambda: Membership(
        id="m", company_id=CO, user_id=user_id, role="member", status="active",
    )
    return TestClient(app)


@pytest.fixture
def _http():
    ask_api._TURNS.clear()
    ask_api._OPERATIONS.clear()
    yield
    ask_api.set_ask_store(None)
    ask_api.set_ask_loop(None)
    ask_api._TURNS.clear()
    ask_api._OPERATIONS.clear()


def test_the_public_turn_carries_the_targets_and_a_reload_returns_them(_http):
    async def loop(_text):
        return {"text": "Llama a Lucía.", "call_targets": TARGETS}

    ask_api.set_ask_store(web_sessions.SupabaseAskStore(FakeSupabase()))
    ask_api.set_ask_loop(loop)
    client = _client()
    posted = client.post("/api/v1/ask/conversations/conv-1/turns", json={"client_turn_id": "w1", "text": "¿A quién llamo hoy?"})
    assert posted.status_code == 200
    assert posted.json()["call_targets"] == TARGETS
    fetched = client.get(f"/api/v1/ask/conversations/conv-1/turns/{posted.json()['turn_id']}")
    assert fetched.json()["call_targets"] == TARGETS
    replay = client.post("/api/v1/ask/conversations/conv-1/turns", json={"client_turn_id": "w1", "text": "otra"})
    assert replay.json()["call_targets"] == TARGETS


def test_a_turn_without_targets_has_no_call_targets_key(_http):
    async def loop(_text):
        return {"text": "Hola."}

    ask_api.set_ask_loop(loop)
    body = _client().post("/api/v1/ask/conversations/conv-1/turns", json={"client_turn_id": "w2", "text": "hola"}).json()
    assert "call_targets" not in body
