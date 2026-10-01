"""/api/v1/live-calls: the desktop starts a call with the CRM pages on screen."""

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
from app.services.live_calls.state import start_call

MEMBERSHIP = Membership(id="member-1", company_id="co-1", user_id="rep-1", role="member", status="active")
HS = "https://app-eu1.hubspot.com/contacts/147506535"
CONTACT = f"{HS}/record/0-1/901"


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
def connections(monkeypatch):
    rows = {"hubspot": {"metadata": {"portal_id": 147506535}}}
    monkeypatch.setattr(api, "get_crm_connection", lambda _sb, _u, provider: rows.get(provider))
    return rows


@pytest.fixture
def client(hub, db, reserved, connections):
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[get_membership] = lambda: MEMBERSHIP
    app.dependency_overrides[get_supabase] = lambda: db
    return TestClient(app)


def _start(client, *urls, capture="cap-1"):
    body = {"page_urls": list(urls)}
    if capture:
        body["client_capture_id"] = capture
    return client.post("/api/v1/live-calls/start", json=body)


def test_contact_on_screen_is_the_contact_and_on_the_memo(client, reserved):
    call = _start(client, CONTACT).json()["call"]
    assert (call["contact_id"], call["contact_source"], call["memo_id"]) == ("901", "page", "memo-1")
    assert reserved[0]["hubspot_contact_id"] == "901"
    assert reserved[0]["interaction_kind"] == "call"
    assert reserved[0]["client_capture_id"] == "cap-1"


def test_calling_window_in_front_is_skipped(client):
    calling = "https://app-eu1.hubspot.com/calling-integration-popup-ui/147506535"
    assert _start(client, calling, CONTACT).json()["call"]["contact_id"] == "901"


def test_list_in_front_means_no_contact(client, reserved):
    call = _start(client, f"{HS}/objects/0-1/views/all/list", CONTACT).json()["call"]
    assert call["contact_id"] is None and call["needs_contact"] is True
    assert reserved[0]["hubspot_contact_id"] is None


def test_start_is_idempotent_while_live(client, reserved):
    first = _start(client, CONTACT).json()["call"]
    second = _start(client, f"{HS}/record/0-1/902", capture="cap-2").json()["call"]
    assert first["id"] == second["id"] and second["contact_id"] == "901"
    assert len(reserved) == 1


def test_other_portal_is_ignored(client, reserved):
    call = _start(client, "https://app.hubspot.com/contacts/999/record/0-1/901").json()["call"]
    assert call["contact_id"] is None
    assert reserved[0]["hubspot_contact_id"] is None


def test_deal_page_needs_a_pick_and_the_pick_reaches_the_memo(client, db):
    call = _start(client, f"{HS}/record/0-3/55").json()["call"]
    assert call["needs_contact"] is True and call["record"]["object_type"] == "deal"
    picked = client.patch("/api/v1/live-calls/current", json={"provider": "hubspot", "contact_id": "77"}).json()["call"]
    assert (picked["contact_id"], picked["contact_source"]) == ("77", "picked")
    assert db.updates == [({"hubspot_contact_id": "77"}, {"id": "memo-1", "user_id": "rep-1"})]


def test_pipedrive_contact_is_live_only(client, reserved, db, connections):
    connections["pipedrive"] = {"metadata": {"company_domain": "acme"}}
    call = _start(client, "https://acme.pipedrive.com/person/42").json()["call"]
    assert (call["provider"], call["contact_id"]) == ("pipedrive", "42")
    assert reserved[0]["hubspot_contact_id"] is None
    client.patch("/api/v1/live-calls/current", json={"provider": "pipedrive", "contact_id": "5"})
    assert db.updates == []


def test_no_pages_no_capture_and_end(client, reserved):
    call = _start(client, capture=None).json()["call"]
    assert call["contact_id"] is None and call["memo_id"] is None and reserved == []
    assert client.post("/api/v1/live-calls/current/end").json()["call"]["status"] == "ended"
    assert _start(client, capture=None).json()["call"]["id"] != call["id"]


def test_end_and_pick_without_a_call_are_404(client):
    assert client.post("/api/v1/live-calls/current/end").status_code == 404
    assert client.patch("/api/v1/live-calls/current", json={"provider": "hubspot", "contact_id": "1"}).status_code == 404


def test_validation(client):
    assert client.post("/api/v1/live-calls/start", json={"page_urls": ["x"] * 21}).status_code == 422
    assert client.patch("/api/v1/live-calls/current", json={"provider": "hubspot", "contact_id": "1 OR 1"}).status_code == 422


def test_current(client):
    assert client.get("/api/v1/live-calls/current").json() == {"call": None}
    _start(client, CONTACT)
    assert client.get("/api/v1/live-calls/current").json()["call"]["contact_id"] == "901"


async def test_stream_sends_snapshot_then_updates(hub):
    stream = api.live_call_stream(hub, "rep-1", heartbeat_s=5)
    first = json.loads((await asyncio.wait_for(stream.__anext__(), timeout=1)).removeprefix("data: "))
    assert first == {"type": "snapshot", "call": None}
    hub.publish("rep-1", start_call("c9", None, time.time()))
    second = json.loads((await asyncio.wait_for(stream.__anext__(), timeout=1)).removeprefix("data: "))
    assert second["type"] == "update" and second["call"]["id"] == "c9"
    await stream.aclose()
    assert hub.subscriber_count("rep-1") == 0


async def test_stream_heartbeat_when_idle(hub):
    stream = api.live_call_stream(hub, "rep-1", heartbeat_s=0.01)
    await stream.__anext__()
    assert await asyncio.wait_for(stream.__anext__(), timeout=1) == ": keepalive\n\n"
    await stream.aclose()
