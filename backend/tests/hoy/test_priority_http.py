"""F04 list: the route selects context rows for the caller's company."""

import os
from datetime import datetime, timezone

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-hoy-32bytes++")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-hoy-32bytes++")

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import MockTransport, Request, Response

from app.api import contact_priorities as api
from app.deps import get_membership, get_supabase
from app.services.company import Membership
from app.services.hoy.assigned import connection_assigned_fetch, parse_assigned_page
from app.services.hoy.context import fold_context

NOW = datetime(2026, 9, 22, 10, 0, tzinfo=timezone.utc)
COMPANY = "11111111-1111-1111-1111-111111111111"


class _Result:
    def __init__(self, data):
        self.data = data


class _AnyOf:
    def __init__(self, values):
        self.values = set(values)

    def __eq__(self, other):
        return other in self.values


class _Query:
    def __init__(self, store, name: str):
        self._store = store
        self._name = name
        self._rows = store.tables.setdefault(name, [])
        self._filters = []
        self._pending_upsert = None
        self._on_conflict = None

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, column, value):
        self._filters.append((column, value))
        return self

    def in_(self, column, values):
        self._filters.append((column, _AnyOf(values)))
        return self

    def order(self, *_args, **_kwargs):
        return self

    def delete(self):
        self._delete = True
        return self

    def limit(self, *_args, **_kwargs):
        return self

    def upsert(self, payload, on_conflict=None):
        self._pending_upsert = payload if isinstance(payload, list) else [payload]
        self._on_conflict = on_conflict
        return self

    def execute(self):
        if self._pending_upsert is not None:
            key_fields = (self._on_conflict or "").split(",")
            table = self._store.tables.setdefault(self._name, [])
            for incoming in self._pending_upsert:
                match = None
                for index, existing in enumerate(table):
                    if all(existing.get(field) == incoming.get(field) for field in key_fields if field):
                        match = index
                        break
                if match is None:
                    table.append(dict(incoming))
                else:
                    table[match] = {**table[match], **incoming}
            self._pending_upsert = None
            return _Result([])
        rows = list(self._rows)
        for column, value in self._filters:
            rows = [row for row in rows if value == row.get(column)]
        if getattr(self, "_delete", False):
            self._store.tables[self._name] = [row for row in self._rows if row not in rows]
            return _Result([])
        return _Result(rows)


class _Supabase:
    def __init__(self):
        self.tables = {"crm_connections": [], "contact_priority_context": []}

    def table(self, name):
        return _Query(self, name)


def _client(user_id: str, role: str = "member", company_id: str = "co-1") -> TestClient:
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[get_membership] = lambda: Membership(
        id="m", company_id=company_id, user_id=user_id, role=role, status="active",
    )
    app.dependency_overrides[get_supabase] = lambda: STORE
    return TestClient(app)


def _row(**overrides) -> dict:
    row = {
        "company_id": "co-1",
        "connection_id": "crm-A",
        "contact_id": "1",
        "deal_id": "",
        "owner_user_id": "user-a",
        "owner_ambiguous": False,
        "coverage": "complete",
        "history_complete": True,
        "observed_at": "2026-09-22T09:00:00Z",
        "payload": {},
    }
    row.update(overrides)
    return row


STORE = _Supabase()


def setup_function():
    STORE.tables = {"crm_connections": [], "contact_priority_context": []}
    api._CLOCK[0] = NOW
    api.set_assigned_fetch_factory(None)
    api.set_fold_members(lambda _supabase, _company_id: [
        {"user_id": "user-a", "email": "ana@vocify.test", "name": "Ana"},
    ])


def test_priority_clock_advances_after_import():
    from app.api import contact_priorities as api

    api._CLOCK[0] = api._CLOCK_DEFAULT
    first = api._now()
    assert api._CLOCK[0] is api._CLOCK_DEFAULT
    later = api._now()
    assert later >= first


def test_no_connection_is_not_an_empty_complete_list():
    STORE.tables["crm_connections"] = [{"company_id": "co-1", "status": "expired"}]
    STORE.tables["contact_priority_context"] = [
        _row(payload={"pain_confirmed": True, "pain_at": "2026-09-20T10:00:00Z"}),
    ]
    body = _client("user-a").get("/api/v1/contact-priorities").json()
    assert body["items"] == []
    assert body["coverage"] == "unavailable"
    assert body["title"] == "title_connect_crm"


def test_rows_drive_empty_partial_and_the_personal_list():
    STORE.tables["crm_connections"] = [{"company_id": "co-1", "status": "connected", "provider": "hubspot"}]
    STORE.tables["contact_priority_context"] = [_row(
        contact_id="9",
        payload={"meeting_agreed": True, "pain_confirmed": True, "pain_at": "2026-09-20T10:00:00Z"},
    )]
    empty = _client("user-a").get("/api/v1/contact-priorities").json()
    assert empty["items"] == []
    assert empty["title"] == "title_none_now"
    assert empty["action"] == "open_contacts"

    STORE.tables["contact_priority_context"] = [_row(
        contact_id="8",
        owner_user_id="user-b",
        coverage="partial",
        history_complete=False,
        payload={"last_call_at": None},
    )]
    partial = _client("user-a").get("/api/v1/contact-priorities").json()
    assert partial["items"] == []
    assert partial["title"] == "title_history_partial"
    assert partial["observed_at"] == "2026-09-22T09:00:00Z"

    STORE.tables["contact_priority_context"] = [
        _row(contact_id="1", owner_user_id="user-b", payload={"last_call_at": None}),
        _row(contact_id="2", owner_ambiguous=True, owner_user_id=None, payload={}),
        _row(
            contact_id="42",
            deal_id="deal-7",
            payload={
                "pain_confirmed": True,
                "pain_at": "2026-09-20T10:00:00Z",
                "evidence_refs": ["ev-1"],
                "meeting_agreed": False,
            },
        ),
        _row(company_id="co-2", contact_id="99", payload={"pain_confirmed": True, "pain_at": "2026-09-20T10:00:00Z"}),
    ]
    page = _client("user-a").get("/api/v1/contact-priorities").json()
    assert [row["contact_id"] for row in page["items"]] == ["42"]
    assert page["items"][0]["reason"] == "pain_agree_next_step"
    assert "Tier" not in page["items"][0]["reason"]


def test_empty_cache_with_hubspot_token_fetches_once_and_cached_rows_skip_crm():
    calls: list[str] = []

    def handler(request: Request) -> Response:
        calls.append(str(request.url))
        if request.url.path == "/crm/v3/owners":
            return Response(200, json={"results": [{"id": "101", "email": "ana@vocify.test"}]})
        return Response(
            200,
            json={
                "results": [{"id": "77", "properties": {"hubspot_owner_id": "101", "notes_last_contacted": None}}],
            },
        )

    client = httpx.Client(transport=MockTransport(handler))
    api.set_assigned_fetch_factory(lambda connection: connection_assigned_fetch(connection, client=client))
    STORE.tables["crm_connections"] = [{
        "id": "crm-A",
        "company_id": "co-1",
        "status": "connected",
        "provider": "hubspot",
        "access_token": "pat-test",
        "metadata": {"portal_id": "123"},
    }]
    http = _client("user-a")
    first = http.get("/api/v1/contact-priorities").json()
    assert len(calls) == 2
    assert "contacts/search" in calls[1]
    assert first["items"][0]["contact_id"] == "77"
    assert STORE.tables["contact_priority_context"]

    calls.clear()
    second = http.get("/api/v1/contact-priorities").json()
    assert calls == []
    assert second["items"][0]["contact_id"] == "77"


def test_a_complete_empty_crm_is_not_the_same_as_no_priority_candidates():
    def handler(_request: Request) -> Response:
        return Response(200, json={"results": []})

    client = httpx.Client(transport=MockTransport(handler))
    api.set_assigned_fetch_factory(lambda connection: connection_assigned_fetch(connection, client=client))
    STORE.tables["crm_connections"] = [{
        "id": "crm-A",
        "company_id": "co-1",
        "status": "connected",
        "provider": "hubspot",
        "access_token": "pat-test",
    }]
    onboarding = _client("user-a").get("/api/v1/contact-priorities").json()
    assert onboarding["items"] == []
    assert onboarding["coverage"] == "complete"
    assert onboarding["title"] == "title_no_assigned"
    assert onboarding["action"] == "review_assignment"

    STORE.tables["contact_priority_context"] = [_row(
        contact_id="9",
        observed_at="2026-09-22T09:50:00Z",
        payload={"meeting_agreed": True, "pain_confirmed": True, "pain_at": "2026-09-20T10:00:00Z"},
    )]
    none_now = _client("user-a").get("/api/v1/contact-priorities").json()
    assert none_now["items"] == []
    assert none_now["title"] == "title_none_now"
    assert none_now["action"] == "open_contacts"


def test_forbidden_fetch_is_not_an_empty_complete_list():
    def handler(_request: Request) -> Response:
        return Response(403, json={"message": "denied"})

    client = httpx.Client(transport=MockTransport(handler))
    api.set_assigned_fetch_factory(lambda connection: connection_assigned_fetch(connection, client=client))
    STORE.tables["crm_connections"] = [{
        "id": "crm-A",
        "company_id": "co-1",
        "status": "connected",
        "provider": "hubspot",
        "access_token": "pat-test",
    }]
    body = _client("user-a").get("/api/v1/contact-priorities").json()
    assert body["items"] == []
    assert body["coverage"] == "forbidden"
    assert body["title"] == "title_history_partial"
    assert STORE.tables["contact_priority_context"] == []


def test_a_crm_server_error_is_unavailable_not_a_crash():
    client = httpx.Client(transport=MockTransport(lambda _request: Response(500, json={"message": "boom"})))
    api.set_assigned_fetch_factory(lambda connection: connection_assigned_fetch(connection, client=client))
    STORE.tables["crm_connections"] = [{
        "id": "crm-A",
        "company_id": "co-1",
        "status": "connected",
        "provider": "hubspot",
        "access_token": "pat-test",
    }]
    response = _client("user-a").get("/api/v1/contact-priorities")
    assert response.status_code == 200
    assert response.json()["coverage"] == "unavailable"


def test_an_expired_hubspot_token_is_refreshed_before_reading(monkeypatch):
    seen_tokens: list[str | None] = []

    def handler(request: Request) -> Response:
        seen_tokens.append(request.headers.get("Authorization"))
        if request.url.path == "/crm/v3/owners":
            return Response(200, json={"results": [{"id": "101", "email": "ana@vocify.test"}]})
        return Response(200, json={"results": []})

    monkeypatch.setattr(
        "app.services.hubspot.oauth.refresh_hubspot_tokens",
        lambda _refresh: {"access_token": "new-token", "expires_in": 1800},
    )
    client = httpx.Client(transport=MockTransport(handler))
    api.set_assigned_fetch_factory(lambda connection: connection_assigned_fetch(connection, client=client))
    STORE.tables["crm_connections"] = [{
        "id": "crm-A",
        "company_id": "co-1",
        "status": "connected",
        "provider": "hubspot",
        "access_token": "old-token",
        "refresh_token": "refresh-me",
        "token_expires_at": "2026-09-22T08:00:00Z",
    }]
    _client("user-a").get("/api/v1/contact-priorities")
    assert seen_tokens
    assert set(seen_tokens) == {"Bearer new-token"}


def test_pain_heard_on_a_vocify_call_ranks_the_contact_first():
    STORE.tables["crm_connections"] = [{"company_id": "co-1", "status": "connected", "provider": "hubspot"}]
    STORE.tables["contact_priority_context"] = [
        _row(contact_id="7", observed_at="2026-09-22T09:50:00Z", payload={"contacted": False}),
        _row(contact_id="42", observed_at="2026-09-22T09:50:00Z", payload={"contacted": True}),
    ]
    STORE.tables["memos"] = [
        {"id": "memo-1", "company_id": "co-1", "hubspot_contact_id": "42", "created_at": "2026-09-21T10:00:00Z",
         "extraction": {"intelligence": {"pain_confirmed": True}}},
        {"id": "memo-x", "company_id": "co-2", "hubspot_contact_id": "7", "created_at": "2026-09-21T10:00:00Z",
         "extraction": {"intelligence": {"pain_confirmed": True}}},
    ]
    body = _client("user-a").get("/api/v1/contact-priorities").json()
    assert [row["contact_id"] for row in body["items"]] == ["42", "7"]
    assert body["items"][0]["reason"] == "pain_agree_next_step"
    assert body["items"][0]["evidence_refs"] == ["memo-1"]
    assert body["items"][1]["reason"] == "no_calls_logged"


def test_a_stale_cache_answers_at_once_and_refreshes_behind():
    calls: list[str] = []

    def handler(request: Request) -> Response:
        calls.append(request.url.path)
        if request.url.path == "/crm/v3/owners":
            return Response(200, json={"results": [{"id": "101", "email": "ana@vocify.test"}]})
        return Response(200, json={"results": [{"id": "77", "properties": {"hubspot_owner_id": "101"}}]})

    client = httpx.Client(transport=MockTransport(handler))
    api.set_assigned_fetch_factory(lambda connection: connection_assigned_fetch(connection, client=client))
    STORE.tables["crm_connections"] = [{
        "id": "crm-A", "company_id": "co-1", "status": "connected", "provider": "hubspot", "access_token": "pat-test",
    }]
    STORE.tables["contact_priority_context"] = [_row(contact_id="5", observed_at="2026-09-22T07:00:00Z")]
    body = _client("user-a").get("/api/v1/contact-priorities").json()
    assert [row["contact_id"] for row in body["items"]] == ["5"]
    assert body["stale"] is True
    assert "/crm/v3/objects/contacts/search" in calls
    assert [row["contact_id"] for row in STORE.tables["contact_priority_context"]] == ["77"]


def test_a_folded_unfinished_page_is_what_the_route_returns():
    page = parse_assigned_page(
        "hubspot",
        {
            "results": [{"id": "42", "properties": {"hubspot_owner_id": "101"}}],
            "paging": {"next": {"after": "100"}},
        },
        connection_id="crm-A",
        observed_at="2026-09-22T09:00:00Z",
        owner_emails={"101": "ana@vocify.test"},
    )
    STORE.tables["crm_connections"] = [{"company_id": COMPANY, "status": "connected"}]
    STORE.tables["contact_priority_context"] = fold_context(
        company_id=COMPANY,
        pages=[page],
        members=[{"user_id": "user-a", "email": "ana@vocify.test"}],
    )
    body = _client("user-a", company_id=COMPANY).get("/api/v1/contact-priorities").json()
    assert body["items"][0]["contact_id"] == "42"
    assert body["items"][0]["never_called"] is False
    assert body["coverage"] == "partial"
    assert body["title"] == "title_history_partial"
