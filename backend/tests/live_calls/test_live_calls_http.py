"""/api/v1/live-calls: the Mac app sends the CRM pages on screen."""

import asyncio
import json
import time

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


@pytest.fixture
def hub(monkeypatch):
    fresh = LiveCallHub()
    monkeypatch.setattr(api, "live_call_hub", fresh)
    return fresh


@pytest.fixture
def connections(monkeypatch):
    rows = {"hubspot": {"metadata": {"portal_id": 147506535}}}
    monkeypatch.setattr(api, "get_crm_connection", lambda _sb, _u, provider: rows.get(provider))
    return rows


@pytest.fixture
def names(monkeypatch):
    seen = []

    async def hubspot(contact_id, *, supabase, user_id):
        seen.append(("hubspot", contact_id, user_id))
        return {"contactName": "zadarma test"}

    async def pipedrive(person_id, *, supabase, user_id):
        seen.append(("pipedrive", person_id, user_id))
        return {"contactName": "Ana Pérez"}

    monkeypatch.setattr(api, "get_contact_context_for_extension", hubspot)
    monkeypatch.setattr(api, "get_pipedrive_person_context", pipedrive)
    return seen


@pytest.fixture
def contexts(monkeypatch):
    """HubSpot record context, at the boundary that reads HubSpot (app.api.crm)."""
    from app.api import crm as crm_api

    rows = {"contacts": {}, "deals": {}, "companies": {}}

    def loader(kind):
        async def load(record_id, *, supabase, user_id):
            return rows[kind].get(record_id) or {}

        return load

    monkeypatch.setattr(crm_api, "get_contact_context_for_extension", loader("contacts"))
    monkeypatch.setattr(crm_api, "get_deal_context_for_prefill", loader("deals"))
    monkeypatch.setattr(crm_api, "get_company_context_for_extension", loader("companies"))
    return rows


@pytest.fixture
def client(hub, connections, names, contexts):
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[get_membership] = lambda: MEMBERSHIP
    app.dependency_overrides[get_supabase] = lambda: object()
    return TestClient(app)


def _start(client, *urls, kind=None):
    body = {"page_urls": list(urls)}
    if kind:
        body["kind"] = kind
    return client.post("/api/v1/live-calls/start", json=body)


def _preview(client, *urls):
    return client.post("/api/v1/live-calls/preview", json={"page_urls": list(urls)}).json()


def test_preview_names_the_contact_and_starts_nothing(client, hub, names):
    preview = _preview(client, CONTACT)
    assert preview == {
        "provider": "hubspot",
        "contact_id": "901",
        "contact_name": "zadarma test",
        "record": {"provider": "hubspot", "object_type": "contact", "record_id": "901", "account_id": "147506535"},
        "needs_contact": False,
        "callee": None,
        "contacts_count": 0,
    }
    assert names == [("hubspot", "901", "rep-1")]
    assert hub.current("rep-1") is None


def test_preview_without_a_contact_asks(client, names):
    assert _preview(client, f"{HS}/objects/0-1/views/all/list")["needs_contact"] is True
    deal = _preview(client, f"{HS}/record/0-3/55")
    assert deal["needs_contact"] is True and deal["record"]["object_type"] == "deal" and deal["contact_name"] is None
    assert names == []


def test_preview_pipedrive_name(client, connections):
    connections["pipedrive"] = {"metadata": {"company_domain": "acme"}}
    preview = _preview(client, "https://acme.pipedrive.com/person/42")
    assert (preview["provider"], preview["contact_id"], preview["contact_name"]) == ("pipedrive", "42", "Ana Pérez")


def test_preview_survives_a_failed_name_lookup(client, monkeypatch):
    async def broken(*_a, **_k):
        raise RuntimeError("HubSpot down")

    monkeypatch.setattr(api, "get_contact_context_for_extension", broken)
    preview = _preview(client, CONTACT)
    assert (preview["contact_id"], preview["contact_name"]) == ("901", None)


def test_start_takes_the_contact_on_screen_and_the_kind(client):
    call = _start(client, CONTACT, kind="meeting").json()["call"]
    assert (call["contact_id"], call["contact_source"], call["kind"]) == ("901", "page", "meeting")
    assert _start(client).json()["call"]["id"] == call["id"]


def test_calling_window_in_front_is_skipped(client):
    calling = "https://app-eu1.hubspot.com/calling-integration-popup-ui/147506535"
    assert _start(client, calling, CONTACT).json()["call"]["contact_id"] == "901"


def test_list_in_front_means_no_contact(client):
    call = _start(client, f"{HS}/objects/0-1/views/all/list", CONTACT).json()["call"]
    assert call["contact_id"] is None and call["needs_contact"] is True


def test_other_portal_is_ignored(client):
    assert _start(client, "https://app.hubspot.com/contacts/999/record/0-1/901").json()["call"]["contact_id"] is None


def test_pick_end_and_restart(client):
    call = _start(client, f"{HS}/record/0-3/55").json()["call"]
    assert call["needs_contact"] is True and call["kind"] == "call"
    picked = client.patch("/api/v1/live-calls/current", json={"provider": "hubspot", "contact_id": "77"}).json()["call"]
    assert (picked["contact_id"], picked["contact_source"]) == ("77", "picked")
    assert client.post("/api/v1/live-calls/current/end").json()["call"]["status"] == "ended"
    assert _start(client).json()["call"]["id"] != call["id"]


def test_end_and_pick_without_a_call_are_404(client):
    assert client.post("/api/v1/live-calls/current/end").status_code == 404
    assert client.patch("/api/v1/live-calls/current", json={"provider": "hubspot", "contact_id": "1"}).status_code == 404


def test_validation(client):
    assert client.post("/api/v1/live-calls/start", json={"page_urls": ["x"] * 21}).status_code == 422
    assert client.post("/api/v1/live-calls/start", json={"kind": "visit"}).status_code == 422
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


def test_preview_offers_the_contact_on_screen_to_call(client, contexts):
    contexts["contacts"]["901"] = {"contactId": "901", "contactName": "zadarma test", "contactPhone": "600 111 222"}
    preview = _preview(client, CONTACT)
    assert preview["callee"] == {"contact_id": "901", "name": "zadarma test", "phone": "+34600111222"}
    assert preview["contacts_count"] == 1


def test_preview_contact_without_a_phone_is_named_but_not_dialable(client, contexts):
    contexts["contacts"]["901"] = {"contactId": "901", "contactName": "zadarma test", "contactPhone": None}
    assert _preview(client, CONTACT)["callee"] == {"contact_id": "901", "name": "zadarma test", "phone": None}


def test_preview_deal_with_one_contact_offers_that_contact(client, contexts):
    contexts["deals"]["55"] = {
        "contactId": "77",
        "contactName": "Ana Ruiz",
        "contactPhone": "+34 600 111 222",
        "contacts": [{"contact_id": "77", "name": "Ana Ruiz", "phone": "+34 600 111 222"}],
    }
    preview = _preview(client, f"{HS}/record/0-3/55")
    assert preview["callee"] == {"contact_id": "77", "name": "Ana Ruiz", "phone": "+34600111222"}
    assert preview["contacts_count"] == 1
    # The meeting contact still waits for the rep to pick one on a deal page.
    assert preview["needs_contact"] is True and preview["contact_id"] is None


def test_preview_deal_with_several_contacts_offers_nobody(client, contexts):
    contexts["deals"]["55"] = {
        "contactId": None,
        "contacts": [{"contact_id": "77", "name": "Ana"}, {"contact_id": "78", "name": "Luis"}],
    }
    preview = _preview(client, f"{HS}/record/0-3/55")
    assert (preview["callee"], preview["contacts_count"]) == (None, 2)


def test_preview_company_uses_its_one_contact(client, contexts):
    contexts["companies"]["12"] = {
        "contactId": "80",
        "contactName": "Eva",
        "contactPhone": "+447700900123",
        "contacts": [{"contact_id": "80", "name": "Eva", "phone": "+447700900123"}],
    }
    assert _preview(client, f"{HS}/record/0-2/12")["callee"] == {"contact_id": "80", "name": "Eva", "phone": "+447700900123"}


def test_preview_other_portal_offers_nobody(client, contexts):
    contexts["contacts"]["901"] = {"contactId": "901", "contactName": "x", "contactPhone": "+34600111222"}
    preview = _preview(client, "https://app.hubspot.com/contacts/999/record/0-1/901")
    assert (preview["callee"], preview["contacts_count"]) == (None, 0)


def test_preview_pipedrive_is_not_dialable_yet(client, connections):
    connections["pipedrive"] = {"metadata": {"company_domain": "acme"}}
    preview = _preview(client, "https://acme.pipedrive.com/person/42")
    assert preview["contact_name"] == "Ana Pérez" and preview["callee"] is None


def test_preview_unreadable_phone_is_dropped(client, contexts):
    contexts["contacts"]["901"] = {"contactId": "901", "contactName": "x", "contactPhone": "call me"}
    assert _preview(client, CONTACT)["callee"]["phone"] is None
