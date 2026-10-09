"""/api/v1/calendar: flag off -> 404. Connect goes Google/Microsoft -> our callback ->
Recall calendar, replacing the rep's previous calendar and keeping their switch. The
switch saves and resyncs upcoming meetings. Disconnect deletes the Recall calendar."""

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-recall-3232b")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-recall-3232b")

from unittest.mock import AsyncMock, patch
from urllib.parse import parse_qs, urlparse

import httpx
import respx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import calendar as api
from app.config import settings
from app.deps import get_membership, get_supabase
from app.services import feature_flags
from app.services.company import Membership
from app.services.meetings import calendar_bots

RECALL = "https://eu-central-1.recall.ai"
MEMBERSHIP = Membership(id="member-1", company_id="co-1", user_id="rep-1", role="member", status="active")


class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, store, table):
        self._rows = store.setdefault(table, [])
        self._filters = []
        self._mode = "select"
        self._payload = None

    def select(self, *_a, **_k):
        return self

    def eq(self, column, value):
        self._filters.append((column, value))
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
        return all(row.get(c) == v for c, v in self._filters)

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
            return _Result([dict(r) for r in self._rows if self._match(r)])
        if self._mode == "delete":
            self._rows[:] = [r for r in self._rows if not self._match(r)]
            return _Result([])
        return _Result([dict(r) for r in self._rows if self._match(r)])


class _Supabase:
    def __init__(self, tables=None):
        self.tables = tables or {}

    def table(self, name):
        return _Query(self.tables, name)


def _client(supabase) -> TestClient:
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[get_supabase] = lambda: supabase
    app.dependency_overrides[get_membership] = lambda: MEMBERSHIP
    return TestClient(app, follow_redirects=False)


def _connection(**overrides):
    row = {
        "id": "conn-1",
        "user_id": "rep-1",
        "company_id": "co-1",
        "platform": "google_calendar",
        "recall_calendar_id": "cal-old",
        "email": "ana@acme.es",
        "status": "connected",
        "auto_join": False,
    }
    row.update(overrides)
    return row


def setup_function():
    settings.RECALL_API_KEY = "key-1"
    settings.GOOGLE_CALENDAR_CLIENT_ID = "gid"
    settings.GOOGLE_CALENDAR_CLIENT_SECRET = "gsecret"
    feature_flags._cache.clear()


def teardown_function():
    settings.RECALL_API_KEY = None
    settings.GOOGLE_CALENDAR_CLIENT_ID = None
    settings.GOOGLE_CALENDAR_CLIENT_SECRET = None
    feature_flags._cache.clear()


def _flag(on: bool):
    return patch.object(api, "is_enabled", return_value=on)


def test_flag_off_is_404():
    with _flag(False):
        assert _client(_Supabase()).get("/api/v1/calendar").status_code == 404


def test_state_lists_configured_providers_and_the_connection():
    supabase = _Supabase({"calendar_connections": [_connection()]})
    with _flag(True):
        body = _client(supabase).get("/api/v1/calendar").json()
    assert body == {
        "providers": ["google"],
        "connection": {"platform": "google_calendar", "email": "ana@acme.es", "status": "connected", "auto_join": False},
    }


def test_authorize_an_unconfigured_provider_is_503():
    with _flag(True):
        response = _client(_Supabase()).get("/api/v1/calendar/microsoft/authorize")
    assert response.status_code == 503


def _state_for(provider="google"):
    url = calendar_bots.build_authorize_url(calendar_bots.PROVIDERS[provider], user_id="rep-1", company_id="co-1")
    return parse_qs(urlparse(url).query)["state"][0]


@respx.mock
def test_callback_connects_replaces_the_old_calendar_and_keeps_the_switch():
    supabase = _Supabase({"calendar_connections": [_connection()]})
    token = respx.post("https://oauth2.googleapis.com/token").mock(
        return_value=httpx.Response(200, json={"access_token": "at", "refresh_token": "rt-1"})
    )
    create = respx.post(f"{RECALL}/api/v2/calendars/").mock(
        return_value=httpx.Response(201, json={"id": "cal-new", "status": "connecting", "platform_email": None})
    )
    delete_old = respx.delete(f"{RECALL}/api/v2/calendars/cal-old/").mock(return_value=httpx.Response(204))

    response = _client(supabase).get(f"/api/v1/calendar/google/callback?code=abc&state={_state_for()}")

    assert response.status_code == 302
    assert response.headers["location"].endswith("/dashboard/settings/calling?calendar=connected")
    assert token.called and delete_old.called
    sent = create.calls.last.request
    assert b'"oauth_refresh_token": "rt-1"' in sent.content or b'"oauth_refresh_token":"rt-1"' in sent.content
    [row] = supabase.tables["calendar_connections"]
    assert row["recall_calendar_id"] == "cal-new"
    assert row["auto_join"] is False
    assert row["status"] == "connecting"


def test_callback_when_the_rep_says_no_goes_back_with_the_reason():
    response = _client(_Supabase()).get("/api/v1/calendar/google/callback?error=access_denied")
    assert response.status_code == 302
    query = parse_qs(urlparse(response.headers["location"]).query)
    assert query == {"calendar": ["error"], "error": ["access_denied"]}


def test_callback_with_a_forged_state_saves_nothing():
    supabase = _Supabase()
    response = _client(supabase).get("/api/v1/calendar/google/callback?code=abc&state=forged")
    assert parse_qs(urlparse(response.headers["location"]).query)["error"] == ["invalid_state"]
    assert supabase.tables.get("calendar_connections", []) == []


def test_switch_saves_and_resyncs_upcoming_meetings():
    supabase = _Supabase({"calendar_connections": [_connection()]})
    sync = AsyncMock()
    with _flag(True), patch.object(calendar_bots, "sync_calendar", sync):
        response = _client(supabase).patch("/api/v1/calendar", json={"auto_join": True})
    assert response.status_code == 200
    assert response.json()["connection"]["auto_join"] is True
    assert supabase.tables["calendar_connections"][0]["auto_join"] is True
    sync.assert_awaited_once()
    assert sync.call_args.args[2]["auto_join"] is True


def test_switch_without_a_calendar_is_404():
    with _flag(True):
        response = _client(_Supabase()).patch("/api/v1/calendar", json={"auto_join": True})
    assert response.status_code == 404


@respx.mock
def test_disconnect_deletes_the_recall_calendar_and_the_row():
    supabase = _Supabase({"calendar_connections": [_connection()]})
    delete = respx.delete(f"{RECALL}/api/v2/calendars/cal-old/").mock(return_value=httpx.Response(204))
    with _flag(True):
        response = _client(supabase).delete("/api/v1/calendar")
    assert response.status_code == 204
    assert delete.called
    assert supabase.tables["calendar_connections"] == []
