"""/api/v1/live-calls: extension reports dialer events, clients read the call."""

import asyncio
import json
from dataclasses import replace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import live_calls as api
from app.deps import get_membership, get_supabase
from app.services.company import Membership
from app.services.live_calls.hub import LiveCallHub
from app.services.live_calls.resolve import ResolvedContact

MEMBERSHIP = Membership(id="member-1", company_id="co-1", user_id="rep-1", role="member", status="active")


@pytest.fixture
def hub(monkeypatch):
    fresh = LiveCallHub()
    monkeypatch.setattr(api, "live_call_hub", fresh)
    return fresh


@pytest.fixture
def lookup(monkeypatch):
    mock = AsyncMock(return_value=None)
    monkeypatch.setattr(api, "hubspot_contact_by_phone", mock)
    return mock


@pytest.fixture
def client(hub, lookup):
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[get_membership] = lambda: MEMBERSHIP
    app.dependency_overrides[get_supabase] = lambda: object()
    return TestClient(app)


def _post(client, **body):
    return client.post("/api/v1/live-calls/events", json=body)


def test_started_on_contact_page_is_assigned_without_lookup(client, lookup):
    res = _post(
        client,
        event="started",
        external_call_id="ext-1",
        to_number="+34600111222",
        page_object_type="contact",
        page_record_id="901",
    )
    assert res.status_code == 200
    call = res.json()["call"]
    assert call["contact_id"] == "901"
    assert call["contact_source"] == "page"
    assert call["status"] == "dialing"
    lookup.assert_not_awaited()


def test_started_without_contact_page_resolves_by_phone(client, lookup):
    lookup.return_value = ResolvedContact(contact_id="77", name="María López")
    res = _post(
        client,
        event="started",
        external_call_id="ext-2",
        to_number="+34600111222",
        page_object_type="deal",
        page_record_id="55",
    )
    assert res.status_code == 200
    assert res.json()["call"]["contact_id"] is None
    lookup.assert_awaited_once()
    assert lookup.await_args.args[1:] == ("rep-1", "+34600111222")

    current = client.get("/api/v1/live-calls/current").json()["call"]
    assert current["contact_id"] == "77"
    assert current["contact_name"] == "María López"
    assert current["contact_source"] == "phone"
    assert current["page_object_type"] == "deal"


def test_lookup_is_only_run_once_per_call(client, lookup):
    _post(client, event="started", external_call_id="ext-3", to_number="+34600111222")
    _post(client, event="answered", external_call_id="ext-3")
    _post(client, event="ended", external_call_id="ext-3", end_status="COMPLETED")
    assert lookup.await_count == 1
    current = client.get("/api/v1/live-calls/current").json()["call"]
    assert current["status"] == "ended"
    assert current["end_status"] == "COMPLETED"


def test_lookup_result_is_dropped_when_another_call_started(hub, client, lookup):
    async def slow_lookup(_supabase, _user, _phone):
        # Simulate the rep dialing again before the first lookup returns.
        hub.publish("rep-1", replace(hub.current("rep-1"), external_call_id="ext-newer"))
        return ResolvedContact(contact_id="77")

    lookup.side_effect = slow_lookup
    _post(client, event="started", external_call_id="ext-4", to_number="+34600111222")
    current = client.get("/api/v1/live-calls/current").json()["call"]
    assert current["external_call_id"] == "ext-newer"
    assert current["contact_id"] is None


def test_current_is_null_without_a_call(client):
    assert client.get("/api/v1/live-calls/current").json() == {"call": None}


def test_rejects_non_numeric_record_id(client):
    res = _post(client, event="started", external_call_id="x", page_object_type="contact", page_record_id="1 OR 1")
    assert res.status_code == 422


def test_rejects_unknown_event(client):
    assert _post(client, event="ringing", external_call_id="x").status_code == 422


async def test_stream_sends_snapshot_then_changes(hub):
    from app.services.live_calls.state import LiveCallEvent, apply_event

    stream = api.live_call_stream(hub, "rep-1", heartbeat_s=5)
    first = await asyncio.wait_for(stream.__anext__(), timeout=1)
    assert json.loads(first.removeprefix("data: ")) == {"type": "snapshot", "call": None}

    call = apply_event(
        None,
        LiveCallEvent(
            provider="hubspot",
            source="hubspot_calling_sdk",
            event="started",
            external_call_id="ext-9",
            occurred_at=1.0,
            page_object_type="contact",
            page_record_id="5",
        ),
    )
    hub.publish("rep-1", call)
    second = await asyncio.wait_for(stream.__anext__(), timeout=1)
    payload = json.loads(second.removeprefix("data: "))
    assert payload["type"] == "call"
    assert payload["call"]["contact_id"] == "5"
    await stream.aclose()
    assert hub.subscriber_count("rep-1") == 0


async def test_stream_heartbeat_when_idle(hub):
    stream = api.live_call_stream(hub, "rep-1", heartbeat_s=0.01)
    await stream.__anext__()
    assert await asyncio.wait_for(stream.__anext__(), timeout=1) == ": keepalive\n\n"
    await stream.aclose()


def test_lookup_runs_when_a_late_start_brings_the_number(client, lookup):
    lookup.return_value = ResolvedContact(contact_id="31")
    _post(client, event="answered", external_call_id="ext-5")
    lookup.assert_not_awaited()
    _post(client, event="started", external_call_id="ext-5", to_number="+34600111222")
    lookup.assert_awaited_once()
    assert client.get("/api/v1/live-calls/current").json()["call"]["contact_id"] == "31"
