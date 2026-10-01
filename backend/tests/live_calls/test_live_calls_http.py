"""/api/v1/live-calls: the extension reports the open record, the desktop starts calls."""

import asyncio
import json
import time
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import live_calls as api
from app.deps import get_membership, get_supabase
from app.services.company import Membership
from app.services.live_calls.hub import LiveCallHub

MEMBERSHIP = Membership(id="member-1", company_id="co-1", user_id="rep-1", role="member", status="active")


class _Memos:
    def __init__(self):
        self.updates = []

    def table(self, name):
        assert name == "memos"
        return self

    def update(self, payload):
        self._payload, self._filters = payload, {}
        return self

    def eq(self, col, val):
        self._filters[col] = val
        return self

    def execute(self):
        self.updates.append((self._payload, dict(self._filters)))
        return SimpleNamespace(data=[{}])


@pytest.fixture
def hub(monkeypatch):
    fresh = LiveCallHub()
    monkeypatch.setattr(api, "live_call_hub", fresh)
    return fresh


@pytest.fixture
def db():
    return _Memos()


@pytest.fixture
def reserved(monkeypatch):
    calls = []

    def fake_reserve(_sb, **kwargs):
        calls.append(kwargs)
        return SimpleNamespace(memo_id="memo-1", capture_id="memo-1")

    monkeypatch.setattr(api, "reserve_capture", fake_reserve)
    monkeypatch.setattr(api, "live_version_id", lambda *_a, **_k: "pv-1")
    return calls


@pytest.fixture
def portal(monkeypatch):
    connections = {"hubspot": {"metadata": {"portal_id": 147506535}}}
    monkeypatch.setattr(api, "get_crm_connection", lambda _sb, _u, provider: connections.get(provider))
    return connections


@pytest.fixture
def client(hub, db, reserved, portal):
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[get_membership] = lambda: MEMBERSHIP
    app.dependency_overrides[get_supabase] = lambda: db
    return TestClient(app)


def _presence(client, **over):
    body = {"provider": "hubspot", "object_type": "contact", "record_id": "901", "account_id": "147506535", **over}
    return client.put("/api/v1/live-calls/presence", json=body)


def test_call_started_on_a_contact_reserves_the_capture_with_that_contact(client, reserved):
    assert _presence(client).status_code == 200
    res = client.post("/api/v1/live-calls/start", json={"client_capture_id": "cap-1"})
    call = res.json()["call"]
    assert (call["contact_id"], call["contact_source"], call["memo_id"]) == ("901", "page", "memo-1")
    assert reserved[0]["hubspot_contact_id"] == "901"
    assert reserved[0]["interaction_kind"] == "call"
    assert reserved[0]["client_capture_id"] == "cap-1"


def test_start_is_idempotent_while_live(client, reserved):
    _presence(client)
    first = client.post("/api/v1/live-calls/start", json={"client_capture_id": "cap-1"}).json()["call"]
    second = client.post("/api/v1/live-calls/start", json={"client_capture_id": "cap-2"}).json()["call"]
    assert first["id"] == second["id"]
    assert len(reserved) == 1


def test_record_from_another_portal_is_ignored(client, reserved):
    _presence(client, account_id="999")
    call = client.post("/api/v1/live-calls/start", json={"client_capture_id": "cap-1"}).json()["call"]
    assert call["contact_id"] is None
    assert reserved[0]["hubspot_contact_id"] is None


def test_deal_page_needs_a_pick_and_the_pick_reaches_the_memo(client, db):
    _presence(client, object_type="deal", record_id="55")
    call = client.post("/api/v1/live-calls/start", json={"client_capture_id": "cap-1"}).json()["call"]
    assert call["needs_contact"] is True and call["record"]["object_type"] == "deal"

    picked = client.patch("/api/v1/live-calls/current", json={"provider": "hubspot", "contact_id": "77"}).json()["call"]
    assert (picked["contact_id"], picked["contact_source"]) == ("77", "picked")
    assert db.updates == [({"hubspot_contact_id": "77"}, {"id": "memo-1", "user_id": "rep-1"})]


def test_pipedrive_contact_is_live_only(client, reserved, db, portal):
    portal["pipedrive"] = {"metadata": {"company_domain": "acme"}}
    _presence(client, provider="pipedrive", account_id="acme")
    call = client.post("/api/v1/live-calls/start", json={"client_capture_id": "cap-1"}).json()["call"]
    assert (call["provider"], call["contact_id"]) == ("pipedrive", "901")
    assert reserved[0]["hubspot_contact_id"] is None
    client.patch("/api/v1/live-calls/current", json={"provider": "pipedrive", "contact_id": "5"})
    assert db.updates == []


def test_start_without_capture_and_end(client, reserved):
    call = client.post("/api/v1/live-calls/start", json={}).json()["call"]
    assert call["memo_id"] is None and reserved == []
    ended = client.post("/api/v1/live-calls/current/end").json()["call"]
    assert ended["status"] == "ended"
    again = client.post("/api/v1/live-calls/start", json={}).json()["call"]
    assert again["id"] != call["id"]


def test_end_and_pick_without_a_call_are_404(client):
    assert client.post("/api/v1/live-calls/current/end").status_code == 404
    assert client.patch("/api/v1/live-calls/current", json={"provider": "hubspot", "contact_id": "1"}).status_code == 404


def test_presence_validation(client):
    assert _presence(client, record_id="1 OR 1").status_code == 422
    assert _presence(client, object_type="ticket").status_code == 422
    assert _presence(client, provider="salesforce").status_code == 422


def test_current_shows_presence_and_call(client):
    assert client.get("/api/v1/live-calls/current").json() == {"presence": None, "call": None}
    _presence(client)
    assert client.get("/api/v1/live-calls/current").json()["presence"]["record_id"] == "901"


async def test_stream_sends_snapshot_then_updates(hub):
    from app.services.live_calls.state import RecordPresence

    stream = api.live_call_stream(hub, "rep-1", heartbeat_s=5)
    first = json.loads((await asyncio.wait_for(stream.__anext__(), timeout=1)).removeprefix("data: "))
    assert first == {"type": "snapshot", "presence": None, "call": None}
    hub.set_presence("rep-1", RecordPresence("hubspot", "contact", "5", None, time.time()))
    second = json.loads((await asyncio.wait_for(stream.__anext__(), timeout=1)).removeprefix("data: "))
    assert second["type"] == "update" and second["presence"]["record_id"] == "5"
    await stream.aclose()
    assert hub.subscriber_count("rep-1") == 0


async def test_stream_heartbeat_when_idle(hub):
    stream = api.live_call_stream(hub, "rep-1", heartbeat_s=0.01)
    await stream.__anext__()
    assert await asyncio.wait_for(stream.__anext__(), timeout=1) == ": keepalive\n\n"
    await stream.aclose()


def test_list_page_after_a_record_clears_the_contact(client, reserved):
    _presence(client)
    assert client.put("/api/v1/live-calls/presence", json={"provider": "hubspot"}).status_code == 200
    call = client.post("/api/v1/live-calls/start", json={"client_capture_id": "cap-1"}).json()["call"]
    assert call["contact_id"] is None
    assert reserved[0]["hubspot_contact_id"] is None


def test_half_a_record_is_rejected(client):
    assert client.put("/api/v1/live-calls/presence", json={"provider": "hubspot", "object_type": "contact"}).status_code == 422
    assert client.put("/api/v1/live-calls/presence", json={"provider": "hubspot", "record_id": "5"}).status_code == 422
