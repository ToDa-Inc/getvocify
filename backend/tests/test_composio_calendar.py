"""Google Calendar through Composio: Google events read through Composio's proxy become
Recall-shaped events, Vocify schedules the Recall bots itself (one per company per meeting),
and connect / disconnect go through Composio accounts owned by the Vocify user."""

import asyncio
import json
import os
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch
from urllib.parse import parse_qs, urlparse

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-recall-3232b")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-recall-3232b")

import httpx
import respx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import calendar as api
from app.config import settings
from app.deps import get_membership, get_supabase
from app.integrations.composio_client import BASE_URL as COMPOSIO
from app.integrations.recall_client import RecallClient
from app.services.company import Membership
from app.services.meetings import calendar_bots
from app.services.meetings import composio_calendar as cc

RECALL = "https://eu-central-1.recall.ai"
NOW = datetime.now(timezone.utc).replace(microsecond=0)
START = NOW + timedelta(days=1)
MEMBERSHIP = Membership(id="member-1", company_id="co-1", user_id="rep-1", role="member", status="active")


class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, store, table):
        self._rows = store.setdefault(table, [])
        self._filters = []
        self._mode, self._payload = "select", None

    def select(self, *_a, **_k):
        return self

    def eq(self, column, value):
        self._filters.append(lambda r: r.get(column) == value)
        return self

    def neq(self, column, value):
        self._filters.append(lambda r: r.get(column) != value)
        return self

    def limit(self, _n):
        return self

    def update(self, payload):
        self._mode, self._payload = "update", payload
        return self

    def upsert(self, payload, on_conflict):
        self._mode, self._payload, self._conflict = "upsert", payload, on_conflict
        return self

    def delete(self):
        self._mode = "delete"
        return self

    def _match(self, row):
        return all(f(row) for f in self._filters)

    def execute(self):
        if self._mode == "upsert":
            for row in self._rows:
                if row.get(self._conflict) == self._payload.get(self._conflict):
                    row.update(self._payload)
                    return _Result([dict(row)])
            row = {"id": f"conn-{len(self._rows) + 1}", **self._payload}
            self._rows.append(row)
            return _Result([dict(row)])
        if self._mode == "update":
            for row in self._rows:
                if self._match(row):
                    row.update(self._payload)
            return _Result([])
        if self._mode == "delete":
            self._rows[:] = [r for r in self._rows if not self._match(r)]
            return _Result([])
        return _Result([dict(r) for r in self._rows if self._match(r)])


class _Supabase:
    def __init__(self, tables=None):
        self.tables = tables or {}

    def table(self, name):
        return _Query(self.tables, name)


def setup_function():
    settings.RECALL_API_KEY = "key-1"
    settings.COMPOSIO_API_KEY = "ak-test"
    settings.COMPOSIO_GOOGLE_CALENDAR_AUTH_CONFIG_ID = "ac_google"


def teardown_function():
    settings.RECALL_API_KEY = None
    settings.COMPOSIO_API_KEY = None
    settings.COMPOSIO_GOOGLE_CALENDAR_AUTH_CONFIG_ID = None


def _connection(**overrides):
    row = {
        "id": "conn-1",
        "user_id": "rep-1",
        "company_id": "co-1",
        "platform": "google_calendar",
        "recall_calendar_id": cc.marker_id("rep-1"),
        "email": "ana@acme.es",
        "status": "connected",
        "auto_join": True,
    }
    row.update(overrides)
    return row


def _google(**overrides):
    event = {
        "id": "g1",
        "status": "confirmed",
        "summary": "Demo con Lucía",
        "start": {"dateTime": START.isoformat()},
        "end": {"dateTime": (START + timedelta(minutes=30)).isoformat()},
        "hangoutLink": "https://meet.google.com/abc-defg-hij",
        "organizer": {"email": "ana@acme.es"},
        "attendees": [
            {"email": "ana@acme.es", "self": True, "responseStatus": "accepted"},
            {"email": "lucia@cliente.com", "responseStatus": "needsAction"},
        ],
    }
    event.update(overrides)
    return event


def _event(**overrides):
    return cc.to_event(_google(**overrides), "rep-1")


def _bot(bot_id, event, *, user_id="rep-1", key=None):
    return {
        "id": bot_id,
        "metadata": {
            "source": "calendar",
            "user_id": user_id,
            "company_id": "co-1",
            "calendar_event_id": event["id"],
            "calendar_key": key or calendar_bots.deduplication_key(event, "co-1"),
        },
    }


# --- Google events --------------------------------------------------------------------


def test_a_google_event_reads_like_a_recall_event():
    event = _event()
    assert event["id"] == "gcal:rep-1:g1"
    assert event["meeting_url"] == "https://meet.google.com/abc-defg-hij"
    assert event["is_deleted"] is False
    assert calendar_bots.should_join(event, calendar_email="ana@acme.es", now=NOW)


def test_meeting_link_from_zoom_in_the_description_and_never_any_link():
    zoom = _event(hangoutLink=None, description='Únete: <a href="https://acme.zoom.us/j/123?pwd=x">aquí</a>')
    assert zoom["meeting_url"] == "https://acme.zoom.us/j/123?pwd=x"
    other = _event(hangoutLink=None, location="https://example.com/sala")
    assert other["meeting_url"] is None


def test_a_cancelled_google_event_is_deleted():
    assert _event(status="cancelled")["is_deleted"] is True


# --- bots -----------------------------------------------------------------------------


def _bots_route(bots):
    return respx.get(f"{RECALL}/api/v1/bot/").mock(return_value=httpx.Response(200, json={"results": bots, "next": None}))


@respx.mock
def test_an_outside_meeting_gets_a_bot_scheduled_for_its_start():
    _bots_route([])
    create = respx.post(f"{RECALL}/api/v1/bot/").mock(return_value=httpx.Response(201, json={"id": "bot-1"}))
    event = _event()
    asyncio.run(cc.apply_bots(RecallClient(), _connection(), [event], NOW))
    sent = json.loads(create.calls.last.request.content)
    assert sent["meeting_url"] == "https://meet.google.com/abc-defg-hij"
    assert datetime.fromisoformat(sent["join_at"]) == START
    assert sent["metadata"]["source"] == "calendar"
    assert sent["metadata"]["calendar_event_id"] == "gcal:rep-1:g1"
    assert sent["metadata"]["calendar_key"] == calendar_bots.deduplication_key(event, "co-1")


@respx.mock
def test_a_meeting_a_teammate_already_has_a_bot_for_gets_no_second_one():
    event = _event()
    teammate_event = {**event, "id": "gcal:rep-2:g1"}
    _bots_route([_bot("bot-9", teammate_event, user_id="rep-2", key=calendar_bots.deduplication_key(event, "co-1"))])
    create = respx.post(f"{RECALL}/api/v1/bot/")
    asyncio.run(cc.apply_bots(RecallClient(), _connection(), [event], NOW))
    assert not create.called


@respx.mock
def test_a_moved_meeting_replaces_its_bot():
    event = _event()
    _bots_route([_bot("bot-old", event, key="old-time-key")])
    delete = respx.delete(f"{RECALL}/api/v1/bot/bot-old/").mock(return_value=httpx.Response(204))
    create = respx.post(f"{RECALL}/api/v1/bot/").mock(return_value=httpx.Response(201, json={"id": "bot-new"}))
    asyncio.run(cc.apply_bots(RecallClient(), _connection(), [event], NOW))
    assert delete.called and create.called


@respx.mock
def test_switch_off_or_cancelled_removes_the_bot_before_the_meeting():
    event = _event()
    _bots_route([_bot("bot-1", event)])
    delete = respx.delete(f"{RECALL}/api/v1/bot/bot-1/").mock(return_value=httpx.Response(204))
    asyncio.run(cc.apply_bots(RecallClient(), _connection(auto_join=False), [event], NOW))
    assert delete.called


@respx.mock
def test_an_internal_meeting_gets_no_bot():
    _bots_route([])
    create = respx.post(f"{RECALL}/api/v1/bot/")
    internal = _event(attendees=[{"email": "ana@acme.es", "self": True}, {"email": "toni@acme.es"}])
    asyncio.run(cc.apply_bots(RecallClient(), _connection(), [internal], NOW))
    assert not create.called


@respx.mock
def test_sync_reads_the_primary_calendar_through_composio_and_stores_it():
    respx.get(f"{COMPOSIO}/connected_accounts").mock(
        return_value=httpx.Response(200, json={"items": [{"id": "ca_1", "status": "ACTIVE"}]})
    )
    proxy = respx.post(f"{COMPOSIO}/tools/execute/proxy").mock(
        return_value=httpx.Response(200, json={"status": 200, "data": {"items": [_google()]}})
    )
    _bots_route([])
    respx.post(f"{RECALL}/api/v1/bot/").mock(return_value=httpx.Response(201, json={"id": "bot-1"}))
    store = AsyncMock()
    with patch.object(cc.calendar_events, "store_events", store):
        asyncio.run(cc.sync(_Supabase(), RecallClient(), _connection()))
    sent = json.loads(proxy.calls.last.request.content)
    assert sent["connected_account_id"] == "ca_1"
    assert sent["endpoint"] == "https://www.googleapis.com/calendar/v3/calendars/primary/events"
    [stored] = store.call_args.args[2]
    assert stored["id"] == "gcal:rep-1:g1"


@respx.mock
def test_sync_without_a_composio_account_marks_the_calendar_disconnected():
    respx.get(f"{COMPOSIO}/connected_accounts").mock(return_value=httpx.Response(200, json={"items": []}))
    supabase = _Supabase({"calendar_connections": [_connection()]})
    asyncio.run(cc.sync(supabase, RecallClient(), _connection()))
    assert supabase.tables["calendar_connections"][0]["status"] == "disconnected"


# --- API ------------------------------------------------------------------------------


def _client(supabase) -> TestClient:
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[get_supabase] = lambda: supabase
    app.dependency_overrides[get_membership] = lambda: MEMBERSHIP
    return TestClient(app, follow_redirects=False)


def test_google_is_offered_with_composio_alone():
    assert calendar_bots.available_providers() == ["google"]


@respx.mock
def test_authorize_sends_the_rep_to_composio_with_our_callback():
    link = respx.post(f"{COMPOSIO}/connected_accounts/link").mock(
        return_value=httpx.Response(201, json={"redirect_url": "https://connect.composio.dev/link/lk_1", "connected_account_id": "ca_1"})
    )
    with patch.object(api, "is_enabled", return_value=True):
        response = _client(_Supabase()).get("/api/v1/calendar/google/authorize")
    assert response.json() == {"redirect_url": "https://connect.composio.dev/link/lk_1"}
    sent = json.loads(link.calls.last.request.content)
    assert sent["auth_config_id"] == "ac_google" and sent["user_id"] == "rep-1"
    callback = urlparse(sent["callback_url"])
    assert callback.path == "/api/v1/calendar/google/callback"
    state = parse_qs(callback.query)["state"][0]
    assert calendar_bots.decode_state(state, calendar_bots.PROVIDERS["google"]) == ("rep-1", "co-1")


def _state():
    return calendar_bots.make_state(calendar_bots.PROVIDERS["google"], user_id="rep-1", company_id="co-1")


@respx.mock
def test_callback_connects_and_replaces_a_recall_calendar():
    old = _connection(recall_calendar_id="cal-old", auto_join=True, email="old@acme.es")
    supabase = _Supabase({"calendar_connections": [old]})
    respx.get(f"{COMPOSIO}/connected_accounts").mock(
        return_value=httpx.Response(200, json={"items": [{"id": "ca_new"}, {"id": "ca_older"}]})
    )
    respx.post(f"{COMPOSIO}/tools/execute/proxy").mock(
        return_value=httpx.Response(200, json={"status": 200, "data": {"id": "Ana@Acme.es"}})
    )
    drop_account = respx.delete(f"{COMPOSIO}/connected_accounts/ca_older").mock(return_value=httpx.Response(200, json={}))
    drop_recall = respx.delete(f"{RECALL}/api/v2/calendars/cal-old/").mock(return_value=httpx.Response(204))
    with patch.object(api, "_sync_upcoming", AsyncMock()):
        response = _client(supabase).get(
            f"/api/v1/calendar/google/callback?state={_state()}&status=success&connected_account_id=ca_new"
        )
    assert response.headers["location"].endswith("/dashboard/settings/calendar?calendar=connected")
    [row] = supabase.tables["calendar_connections"]
    assert row["recall_calendar_id"] == cc.marker_id("rep-1")
    assert row["email"] == "ana@acme.es" and row["status"] == "connected" and row["auto_join"] is True
    assert drop_account.called and drop_recall.called


@respx.mock
def test_callback_with_an_account_that_is_not_the_reps_saves_nothing():
    supabase = _Supabase()
    respx.get(f"{COMPOSIO}/connected_accounts").mock(return_value=httpx.Response(200, json={"items": [{"id": "ca_mine"}]}))
    response = _client(supabase).get(
        f"/api/v1/calendar/google/callback?state={_state()}&status=success&connected_account_id=ca_someone_else"
    )
    assert parse_qs(urlparse(response.headers["location"]).query)["error"] == ["not_connected"]
    assert supabase.tables.get("calendar_connections", []) == []


def test_callback_when_the_rep_says_no():
    response = _client(_Supabase()).get(f"/api/v1/calendar/google/callback?state={_state()}&status=failed")
    assert parse_qs(urlparse(response.headers["location"]).query)["error"] == ["access_denied"]


@respx.mock
def test_disconnect_removes_upcoming_bots_the_composio_account_and_the_row():
    supabase = _Supabase({"calendar_connections": [_connection()]})
    event = _event()
    _bots_route([_bot("bot-1", event)])
    delete_bot = respx.delete(f"{RECALL}/api/v1/bot/bot-1/").mock(return_value=httpx.Response(204))
    respx.get(f"{COMPOSIO}/connected_accounts").mock(return_value=httpx.Response(200, json={"items": [{"id": "ca_1"}]}))
    delete_account = respx.delete(f"{COMPOSIO}/connected_accounts/ca_1").mock(return_value=httpx.Response(200, json={}))
    with patch.object(api, "is_enabled", return_value=True):
        response = _client(supabase).delete("/api/v1/calendar")
    assert response.status_code == 204
    assert delete_bot.called and delete_account.called
    assert supabase.tables["calendar_connections"] == []
